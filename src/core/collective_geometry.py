# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""The geometry of a collective group, computed once and shared.

A multicast-target component whose isle declares the collective contract slots
forms a GROUP: its instances, placed on a power-of-two aligned box of the mesh,
reduce and multicast among themselves through address windows the tile's stamper
matches. Everything about that group that is derived from the SoC description and
the isle header - the per-instance bases, the wildcard mask, the dimension-ordered
decomposition into a column phase and a row phase, the column heads, the windows -
used to live in the Python header of universal_tile.sv.mako, where only the tile
could read it. It lives here so that the tile template and the placement report
(noc_placement_checker.py) derive the SAME facts from the same code; the tile's
output is byte-identical to what the inline version produced (checked 2026-09-04).

Ground rules this encodes, each with the failure it prevents:
  * FlooNoC's collective mask is a wildcard over the address: it spans exactly
    2^popcount(mask) members, so an instance set that is not a power-of-two,
    stride-aligned box would silently include ghost members - refused.
  * A sequential (value) reduction merges at most TWO contributions per node,
    so a 2D group reduces in two dimension-ordered 1D phases: every instance
    into its own column head, the heads along their row into instance 0
    (reference behaviour: MAGIA's column-then-row software phases). The
    barrier and the multicast are n-ary by construction and take the full mask.
  * Every windowed slot sits on a beat boundary of its channel: the machinery
    consumes the beat at channel width, and a sub-width store landing in the
    high half is reduced as garbage (the barrier at 'h1_FFFC never converged).
"""

from dataclasses import dataclass, field
from typing import Optional


# (op, alias window base, alias window last byte, group base, member mask,
#  collective mask, slot offset, kind) - kind is one of col, row, barrier, mcast.
Window = tuple[str, int, int, int, int, int, int, str]


@dataclass
class CollectiveGeometry:
    bases: list[int]                 # per-instance bases, enumeration order
    coords: list[tuple[int, int]]    # per-instance (x, y), same order, from the boxes
    c0: int                          # the group's minimum base (instance 0)
    stride: int                      # distance between consecutive bases
    mask: int                        # wildcard mask spanning the whole group
    y_mask: int                      # the column (1D chain) part of the mask
    x_mask: int                      # the row part
    y_dim: int
    x_dim: int
    two_phase: bool                  # both dimensions non-degenerate
    alias: int                       # OffloadCollAliasBase
    slots: dict[str, int]            # collect, collect_col, barrier, mcast, wide (those declared)
    windows: list[Window] = field(default_factory=list)

    @property
    def heads(self) -> list[int]:
        """Indices of the column heads: the instances at the bottom of each column."""
        return [i for i, b in enumerate(self.bases) if ((b - self.c0) & self.y_mask) == 0]

    def column_of(self, idx: int) -> list[int]:
        """Indices of the instances sharing a column with instance idx."""
        return [i for i, b in enumerate(self.bases)
                if ((b - self.c0) & self.x_mask) == ((self.bases[idx] - self.c0) & self.x_mask)]


def _to_int(v) -> int:
    return int(str(v), 0)


def placement_items(comp) -> list:
    pl = comp.placement if isinstance(comp.placement, dict) else {}
    logical = pl.get("logical")
    return logical if isinstance(logical, list) else ([logical] if logical else [])


def instance_bases_and_coords(comp, fixed_params: dict = None) -> tuple[Optional[list[int]], list[tuple[int, int]]]:
    """Per-instance bases and coordinates, in the enumeration order the generator uses.

    Bases come in both schema forms - an explicit list, or a scalar base plus
    size_per_instance repeated over the placement box - and the box enumerates
    column-fastest (y varies first), which is what makes the 1D chains geometric
    columns. Returns (None, coords) when the component has no per-instance form.

    The stride may also come from the isle header: an IP that derives its window from
    an ordinal declares 'InstanceIdStride', and the schema copies it into
    size_per_instance - but only in the validation phase, AFTER the tiles are rendered
    (ollivander.py, phase 1 before phase 2). The tile template therefore passes the
    header's fixed parameters here and the same rule is applied directly, so the
    stamper decision does not depend on the phase order (found 2026-09-05: the PULP
    array's stamper was silently skipped and its alias writes reached the chimney).
    """
    items = placement_items(comp)
    coords: list[tuple[int, int]] = []
    for it in items:
        bx = it.get("box") if isinstance(it, dict) else None
        if bx:
            for x in range(bx["x_start"], bx["x_end"] + 1):
                for y in range(bx["y_start"], bx["y_end"] + 1):
                    coords.append((x, y))
        elif isinstance(it, dict) and "x" in it and "y" in it:
            coords.append((int(it["x"]), int(it["y"])))
    slv = (comp.interfaces or {}).get("axi_slave")
    slv = slv[0] if isinstance(slv, list) else slv
    bases = slv.get("base_addr") if slv else None
    if isinstance(bases, list):
        return [_to_int(b) for b in bases], coords
    stride_src = (slv.get("size_per_instance") if slv else None) or (fixed_params or {}).get("InstanceIdStride")
    if bases is not None and stride_src:
        n = sum((it["box"]["x_end"] - it["box"]["x_start"] + 1) * (it["box"]["y_end"] - it["box"]["y_start"] + 1)
                for it in items if isinstance(it, dict) and it.get("box"))
        if n > 1:
            b0, stride = _to_int(bases), _to_int(stride_src)
            return [b0 + i * stride for i in range(n)], coords
    return None, coords


def collective_geometry(comp, fixed_params: dict, narrow_red_on: bool,
                        narrow_beat_bytes: int, wide_beat_bytes: int) -> Optional[CollectiveGeometry]:
    """The group of `comp`, or None when the isle declares no barrier slot or the
    component has fewer than two instances (no group, no stamper).

    Raises ValueError, at generation, for every geometry the collectives cannot
    carry - with the message the tile template has always printed.
    """
    fx = fixed_params or {}
    boff = fx.get("OffloadBarrierOffs")
    if boff is None:
        return None
    bases, coords = instance_bases_and_coords(comp, fx)
    if bases is None or len(bases) < 2:
        return None
    mask = 0
    for b in bases:
        mask |= b ^ bases[0]
    if len(bases) != (1 << bin(mask).count("1")):
        raise ValueError(
            f"[COLLECTIVE] component '{comp.name}': its {len(bases)} instance bases do not form "
            f"a wildcard-expressible group (mask 0x{mask:x} spans {1 << bin(mask).count('1')} "
            f"members). Re-place the instances on a power-of-two aligned box, or disable the "
            f"narrow reduction.")
    c0 = min(bases)
    slots = {"barrier": _to_int(boff)}
    for name, key in (("collect", "OffloadCollectOffs"), ("collect_col", "OffloadCollectColOffs"),
                      ("mcast", "OffloadMcastOffs"), ("wide", "OffloadWideOffs")):
        if fx.get(key) is not None:
            slots[name] = _to_int(fx[key])
    if "wide" in slots and slots["wide"] % wide_beat_bytes:
        raise ValueError(
            f"[COLLECTIVE] '{comp.name}': OffloadWideOffs {hex(slots['wide'])} is not aligned to the "
            f"wide beat ({wide_beat_bytes} bytes). The wide landing is a whole 512-bit beat written by the "
            f"cluster's DMA; an unaligned offset degrades into strobed narrow beats.")
    for name, key in (("collect", "OffloadCollectOffs"), ("collect_col", "OffloadCollectColOffs"),
                      ("barrier", "OffloadBarrierOffs"), ("mcast", "OffloadMcastOffs")):
        o = slots.get(name)
        if o is not None and o % narrow_beat_bytes:
            raise ValueError(
                f"[COLLECTIVE] component '{comp.name}': {key}=0x{o:x} is not aligned to the "
                f"narrow beat ({narrow_beat_bytes} bytes). FlooNoC reduces the beat at channel width, so a "
                f"sub-width store landing in the high half is silently reduced as garbage.")
    alias = _to_int(fx.get("OffloadCollAliasBase"))
    stride = sorted(bases)[1] - c0
    ydims = set()
    for it in placement_items(comp):
        bx = it.get("box") if isinstance(it, dict) else None
        if bx:
            ydims.add(bx["y_end"] - bx["y_start"] + 1)
    if len(ydims) != 1:
        raise ValueError(
            f"[COLLECTIVE] component '{comp.name}': the dimension-ordered reduction needs one "
            f"uniform placement-box height, got {sorted(ydims)}. Re-place the instances or "
            f"disable the narrow reduction.")
    y_dim = ydims.pop()
    y_mask = (stride * y_dim - 1) & ~(stride - 1)
    if y_mask & ~mask:
        raise ValueError(
            f"[COLLECTIVE] component '{comp.name}': the column mask 0x{y_mask:x} escapes the "
            f"group mask 0x{mask:x} - the address enumeration is not column-fastest, so the "
            f"1D chains would not be geometric columns. Check the placement/base ordering.")
    x_mask = mask & ~y_mask
    x_dim = 1 << bin(x_mask).count("1")
    if x_dim * y_dim != len(bases):
        raise ValueError(
            f"[COLLECTIVE] component '{comp.name}': {y_dim} rows x {x_dim} "
            f"columns does not cover the {len(bases)} instances - the box is not a full grid.")
    two_phase = (y_dim > 1) and (x_mask != 0)
    geo = CollectiveGeometry(bases=bases, coords=coords, c0=c0, stride=stride, mask=mask,
                             y_mask=y_mask, x_mask=x_mask, y_dim=y_dim, x_dim=x_dim,
                             two_phase=two_phase, alias=alias, slots=slots)
    coff, ccoff = slots.get("collect"), slots.get("collect_col")
    if narrow_red_on and coff is not None and ccoff is not None:
        if two_phase:
            geo.windows += [
                ("IntAdd", alias + ccoff, alias + ccoff + 3, c0, mask,   y_mask, ccoff, "col"),
                ("IntAdd", alias + coff,  alias + coff + 3,  c0, x_mask, x_mask, coff, "row"),
            ]
        else:
            # One dimension is degenerate: the whole group already is a 1D chain,
            # one window onto the final slot suffices.
            geo.windows.append(("IntAdd", alias + coff, alias + coff + 3, c0, mask, mask, coff, "row"))
    # Barrier: parallel (n-ary) op, full group mask, always available.
    geo.windows.append(("LsbAnd", alias + slots["barrier"], alias + slots["barrier"] + 3, c0, mask, mask,
                        slots["barrier"], "barrier"))
    # Multicast: one member writes, the network replicates to the whole group and
    # each destination lands it at its OWN copy of the slot; the destination the
    # stamp carries is the group's minimum corner, where the mask expansion starts.
    if "mcast" in slots:
        geo.windows.append(("Multicast", alias + slots["mcast"], alias + slots["mcast"] + 3, c0, mask, mask,
                            slots["mcast"], "mcast"))
    return geo

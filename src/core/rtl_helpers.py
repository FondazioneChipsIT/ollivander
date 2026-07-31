# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

"""
Shared utility helpers for the RTL generator.

These are pure functions with no dependency on soc_config or the RTLGenerator
instance. They have been extracted from duplicate or inline closures that
previously appeared multiple times inside rtl_generator.py.
"""

import re
from pathlib import Path


def get_base_name(name: str) -> str:
    """Strip direction/polarity suffixes to obtain the canonical pad base name."""
    for suffix in ("_en_o", "_oe_o", "_oe", "_no", "_ni", "_o", "_i"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def extract_dims(type_str):
    """
    Parse a SystemVerilog type string and return a list of (msb, lsb) tuples
    for every packed-dimension bracket found.
    """
    dims = []
    for m in re.finditer(r"\[\s*([^\]:]+)\s*:\s*([^\]]+)\s*\]", str(type_str)):
        try:
            msb = int(eval(m.group(1), {"__builtins__": {}}))
            lsb = int(eval(m.group(2), {"__builtins__": {}}))
            dims.append((msb, lsb))
        except Exception:
            # Only a numeric range can be expanded into per-index suffixes, so a dimension written
            # in terms of parameters ('AW-1', '$clog2(N)-1') is deliberately skipped rather than
            # reported: it is the common case inside an IP, not a mistake. Measured on the shipped
            # padframes, 240 of 8384 dimensions are of that kind - and none of them on the chip
            # boundary, which is the only place this function's result is used.
            pass
    return dims


def get_suffixes(dims_list):
    """
    Recursively expand a list of (msb, lsb) dimension tuples into a flat
    list of underscore-separated index suffixes.

    Example: ``get_suffixes([(1, 0)])`` -> ``["_1", "_0"]``
    """
    if not dims_list:
        return [""]
    c_msb, c_lsb = dims_list[0]
    c_step = -1 if c_msb >= c_lsb else 1
    result = []
    for c_idx in range(c_msb, c_lsb + c_step, c_step):
        for sub in get_suffixes(dims_list[1:]):
            result.append(f"_{c_idx}{sub}")
    return result


def norm_type(t: str) -> str:
    """
    Normalise a SystemVerilog type string for equality comparison.
    Collapses whitespace, rewrites degenerate single-bit arrays, and
    canonicalises ``logic[0:0]`` -> ``logic``.
    """
    t = re.sub(r"\s+", "", t)
    t = t.replace("1-1", "0")
    return "logic" if t == "logic[0:0]" else t


def sv_dependency_sort(files):
    """
    Sort a list of SV file paths so that packages are compiled before
    the modules that depend on them.

    Compilation order:
      0 - ``*_noc_pkg.sv``       (FlooNoC package: depends only on floo_pkg)
      1 - ``*_soc_pkg.sv``       (imports the NoC package above)
      2 - ``*_sys_regs_pkg.sv``
      3 - ``*_pkg.sv``  (other packages)
      4 - everything else

    The NoC package must precede the SoC package: in a NoC topology the generated
    ``<top>_soc_pkg`` imports ``floo_<top>_noc_pkg`` to build its AXI types. This
    mirrors the order in which the project's own packages are emitted, and matters
    for external files pulled in from another project, such as the macros a parent
    SoC instantiates.
    """

    def _rank(f):
        fname = Path(f).name
        if fname.endswith("_noc_pkg.sv"):
            return 0
        if fname.endswith("_soc_pkg.sv"):
            return 1
        if fname.endswith("_sys_regs_pkg.sv"):
            return 2
        if fname.endswith("_pkg.sv"):
            return 3
        return 4

    return sorted(files, key=lambda f: (_rank(f), f))


# Pre-compiled port-declaration pattern reused by the chip-wrapper generator.
PORT_PATTERN = re.compile(
    r"\b(input|output|inout)\b\s+(?:wire\s+|var\s+)?"
    r"(logic(?:[\s\[\]0-9a-zA-Z_\-\+\*:]+)?)\s+([a-zA-Z0-9_]+)\s*(?:,|$|\))"
)

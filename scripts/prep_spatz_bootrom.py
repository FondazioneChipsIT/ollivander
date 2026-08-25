#!/usr/bin/env python3
"""
Build the spatz cluster's bootrom for the address map THIS project actually has,
by driving the IP's own meta-generation flow from a configuration generated here.

Invoked once from the dependency registry:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/prep_spatz_bootrom.py {bender_work}"

The whole sequence lives here rather than as shell in the registry because every
step is CONDITIONAL on a fact this script alone establishes - whether the SoC has
a spatz cluster at all, of its own or inside a nested macro. Expressed in YAML,
that condition became the same `if [ -f ... ]` guard repeated on every line, and
the host-prerequisite diagnostics did not fit at all.

WHY THIS EXISTS
---------------
spatz generates its bootrom from an hjson configuration: clustergen renders
`test/bootdata_bootrom.cc` (a symlink into `src/generated/`) from that file,
riscv32-gcc compiles it together with `test/bootrom.S`, and generate_bootrom.py
wraps the binary into `src/generated/bootrom.sv` - the file our Bender manifest
already carries and `spatz_cluster` already instantiates internally. Consuming
the artifacts checked into the IP instead means consuming a bootrom built for
the IP's own default map: its BOOTDATA bakes `tcdm_start`, `hartid_base`,
`core_count` and the global-memory window of a DIFFERENT SoC, which is what the
bootrom repairs in patch_spatz.py work around. Generating the configuration
here removes the mismatch at its source instead of repairing its consequences.

This is the consumption model of the reference integration too: astral hand-writes
its own wrapper around `spatz_cluster` (the generated wrapper bakes the cluster
identity as constants and can serve exactly one instance at one base, so it is
not an integration API) and invokes ONLY the IP's `bootrom` target from its own
hjson. Our `spatz_cluster_isle.sv` is the analogue of that hand-written wrapper.

WHERE THE VALUES COME FROM
--------------------------
From the generator's OWN OUTPUT, never re-derived: the phase that renders
`generated/` runs before the dependency pre-build steps, and pre-build commands
inherit the project directory as their working directory, so every artifact read
below is on disk by the time this script runs. Reading the output rather than
re-computing from the SoC description is what keeps a single source of truth: the
value that lands in the bootrom is by construction the value that landed in RTL.

  generated/doc/*_map.csv        component name -> isle type (which component IS
                                 the spatz cluster, and how many there are)
  generated/sw/*_map.h           resolved base address and size, per component
  generated/hw/*_soc_pkg.sv      resolved bus widths
  generated/hw/*_<comp>_isle.sv  the isle's own contract: core count, hart base,
                                 TCDM geometry (OffloadCtrlOffs)

The base configuration is the STOCK one shipped by the IP itself
(cfg/spatz_cluster.default.dram.hjson) - never a local copy and never a local
template: a frozen duplicate silently rots at the first revision bump, while
reading the IP's own file inherits its microarchitectural defaults for free and
narrows the drift surface to the KEY NAMES touched below. Every such key is
checked for existence, and a missing one is a hard error: a renamed key must stop
generation, not quietly produce a wrong configuration.

A CLUSTER THIS PROJECT ONLY NESTS
---------------------------------
A project may compile spatz WITHOUT declaring a cluster of its own, because it
nests a macro that contains one (super_noc nests the crux macro). The bootrom
module still comes from THIS project's spatz checkout and still ends up in its
RTL, so skipping generation would leave it built for the IP's default map - a
cluster wired at one base carrying a ROM that believes it sits at another. The
values are then read from the MACRO's own generated isle wrapper, which is both
the file that DEFINES the nested cluster and a file this project compiles: it
carries the hardwired identity the isle drives (`cluster_base_addr_i`), the
contract localparams, and the PMA cached region that is the cluster's view of
the global memory.

SINGLE INSTANCE ONLY
--------------------
The generated bootrom bakes ONE cluster base, and spatz - unlike snitch_cluster -
has no alias region, so one payload image cannot address "itself" across
instances. Multi-instance spatz is therefore an IP-level limitation, not an
integration choice, and this script refuses a configuration that declares more
than one spatz cluster rather than letting the second instance mis-boot silently.
"""

import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import hjson

from host_tools import require as require_host_tool

ISLE_TYPE = "spatz_cluster_isle"
STOCK_CFG = "hw/system/spatz_cluster/cfg/spatz_cluster.default.dram.hjson"
OUT_CFG = "hw/system/spatz_cluster/cfg/spatz_cluster.ollivander.hjson"


def die(msg):
    print(f"[ERROR] gen_spatz_cfg: {msg}", file=sys.stderr)
    sys.exit(1)


def one(pattern, where):
    """Exactly one match, or a hard error naming what was looked for."""
    hits = sorted(Path(".").glob(pattern))
    if len(hits) != 1:
        die(f"expected exactly one {where} matching '{pattern}', found {len(hits)}")
    return hits[0]


def map_csv_components():
    """{component name: isle type} from the generated address-map CSV."""
    path = one("generated/doc/*_map.csv", "address map")
    with path.open(newline="") as f:
        return {row["Component"]: row["Type"] for row in csv.DictReader(f)
                if row.get("Component")}


def map_h_defines():
    """{macro: int} from the generated software address-map header."""
    path = one("generated/sw/*_map.h", "software map header")
    out = {}
    for m in re.finditer(r"#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)", path.read_text()):
        out[m.group(1)] = int(m.group(2), 0)
    return out


def sv_localparams(path):
    """{name: int} for the plain integer localparams/parameters of one SV file.

    Deliberately narrow: only decimal and sized-hex literals with no expression,
    which is what every value read here is declared as. A value that stops
    matching (because the declaration became an expression) shows up as a missing
    key, and the caller turns that into a hard error.
    """
    text = path.read_text()
    out = {}
    pat = (r"\b(?:localparam|parameter)\b\s+(?:int\s+unsigned|logic|bit|longint\s+unsigned)?\s*"
           r"(\w+)\s*=\s*(?:\d*'h([0-9a-fA-F_]+)|(\d+))\s*[,;)]")
    for m in re.finditer(pat, text):
        name, hexv, decv = m.group(1), m.group(2), m.group(3)
        out[name] = int(hexv.replace("_", ""), 16) if hexv else int(decv)
    return out


def need(d, key, where):
    if key not in d:
        die(f"'{key}' not found in {where} - the contract it belongs to has changed")
    return d[key]


def instantiated_value(comp, param, fallback, pkg):
    """The value a parameter ACTUALLY has on the isle instance in the SoC top.

    A project may override any isle parameter from its `parameters` block, and the
    generator emits that override in the TOP's instantiation, not in the wrapper's
    declared defaults - so the wrapper's default is the value only when the top
    stays silent. Reading the default alone would silently ignore, say, a
    hand-picked core count and bake a wrong core_count into the bootrom.

    Precedence: a numeric override in the top, else a symbolic override resolved
    through the SoC package, else the wrapper's default. A symbolic override this
    reader cannot resolve is a hard error, never a guess.
    """
    top = one("generated/hw/*_soc_pkg.sv", "SoC package").with_name(
        one("generated/hw/*_soc_pkg.sv", "SoC package").name.replace("_soc_pkg", ""))
    if not top.is_file():
        die(f"the generated SoC top is missing: {top}")
    text = top.read_text()
    # The instantiation of the isle wrapper: from its header to the instance name.
    m = re.search(rf"\w*_{re.escape(comp)}_isle\s*#\((.*?)\)\s*i_{re.escape(comp)}\b",
                  text, re.DOTALL)
    if not m:
        die(f"no instantiation of the '{comp}' isle found in {top.name}")
    ov = re.search(rf"\.\s*{re.escape(param)}\s*\(\s*([^)\s]+)\s*\)", m.group(1))
    if not ov:
        return fallback
    raw = ov.group(1)
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    m_hex = re.fullmatch(r"\d*'h([0-9a-fA-F_]+)", raw)
    if m_hex:
        return int(m_hex.group(1).replace("_", ""), 16)
    if raw in pkg:
        return pkg[raw]
    die(f"the top overrides '{param}' with '{raw}', which this reader cannot "
        f"resolve to a number - resolve it before generating the configuration")


def write_cfg(stock, bender_work, cl_updates, dram, num_cores, tcdm_bytes, label):
    """Apply the integration set over the IP's stock configuration and write it."""
    cfg = hjson.load(stock.open())
    cl = cfg["cluster"]
    for key in cl_updates:
        need(cl, key, "the IP's stock cluster configuration")
    cl.update(cl_updates)

    need(cl, "tcdm", "the IP's stock cluster configuration")
    cl["tcdm"]["size"] = tcdm_bytes // 1024

    # Absent from the stock configuration on purpose (they are integration
    # features): the isle drives both, so the generated flow must know about them.
    cl["axi_isolate_enable"] = True
    cl["sw_rst_enable"] = True

    # The core count is the LENGTH of the cores array, which clustergen turns into
    # 'nr_cores' for the bootrom: replicate the base entry instead of editing a
    # scalar, so every per-core microarchitectural setting is preserved.
    cores = need(cl, "cores", "the IP's stock cluster configuration")
    if not cores:
        die("the stock configuration declares no cores to replicate")
    cl["cores"] = [dict(cores[0]) for _ in range(num_cores)]

    need(cfg, "dram", "the IP's stock configuration")
    cfg["dram"]["address"], cfg["dram"]["length"] = dram

    out = bender_work / "spatz" / OUT_CFG
    out.write_text(hjson.dumps(cfg, indent=2) + "\n")
    print(f"  -> spatz configuration ({label}): base {cl_updates['cluster_base_addr']:#x}, "
          f"{num_cores} cores, hartid {cl_updates['cluster_base_hartid']:#x}, "
          f"tcdm {tcdm_bytes // 1024} KiB, "
          f"global mem [{dram[0]:#x}, {dram[0] + dram[1]:#x})")
    print(f"  -> written to {out}")
    build_bootrom(bender_work, out)


def run(cmd, cwd, extra_env=None):
    """One step of the IP's flow, with its failure attributed to this script."""
    env = dict(os.environ, **(extra_env or {}))
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    if subprocess.run(cmd, cwd=cwd, env=env).returncode != 0:
        die(f"'{' '.join(str(c) for c in cmd)}' failed in {cwd}")


def build_bootrom(bender_work, cfg_path):
    """Run the IP's own generation flow over the configuration just written.

    Reached only when a configuration exists, which is the whole reason this lives
    in a script: every step below is conditional on the SoC having a spatz cluster,
    and in YAML that condition was the same file test repeated on each line.
    """
    root = (bender_work / "spatz").resolve()
    cluster = root / "hw" / "system" / "spatz_cluster"
    opcodes = root / "sw" / "toolchain" / "riscv-opcodes"
    make = os.environ.get("MAKE", "make")
    py = sys.executable
    # 1. encoding.h, which the bootrom sources include, is GENERATED from a repo the
    #    IP clones itself. Both steps are guarded by their own artifact rather than
    #    by make's timestamps: the IP's rule for the header declares no dependency
    #    on the clone (so asking for it alone on a fresh tree fails), and the
    #    registry's re-pin rewrites the .version file on every run, which would
    #    leave it newer than an existing clone and send `git clone` at a live path.
    if not opcodes.is_dir():
        run([make, "-C", str(root), "sw/toolchain/riscv-opcodes"], cwd=root)
    header = opcodes / "encoding.h"
    if not (header.is_file() and header.stat().st_size):
        # Its generator invokes bare `python`, absent on this host class: the venv's
        # bin goes on PATH for this step only.
        run([make, "-C", str(root), "sw/toolchain/riscv-opcodes/encoding.h", f"PYTHON={py}"],
            cwd=root, extra_env={"PATH": f"{Path(py).parent}:{os.environ.get('PATH', '')}"})
    # 2. clustergen renders the wrapper and the BOOTDATA, then riscv32-gcc and
    #    generate_bootrom.py turn them into src/generated/bootrom.sv - the file the
    #    manifest already carries. This REWRITES that file, so it must precede any
    #    patch script: a repair applied earlier would be erased here.
    run([make, "-C", str(cluster), f"SPATZ_CLUSTER_CFG={cfg_path.name}",
         f"GCC_INSTALL_DIR={require_host_tool('spatz-gcc')}", f"PYTHON={py}",
         "generate", "bootrom"], cwd=cluster)


def generate_for_nested(bender_work, stock):
    """Configure the cluster this project only NESTS (see the module docstring).

    The macro's generated isle wrapper is the file that defines it, and the paths
    to the macro's generated sources are listed in this project's own manifest, so
    the wrapper is found from there rather than guessed from a directory layout.
    """
    manifest = Path("Bender.yml")
    if not manifest.is_file():
        print("  -> no spatz cluster and no manifest to inspect, nothing to generate")
        return
    # Matched by FILE NAME only, with no assumption whatsoever about the directory:
    # the output tree is the project's own choice (OUT_DIR, and the env config's
    # component paths), so the manifest is followed rather than second-guessed. The
    # suffix is the generator's own naming convention for an exported isle wrapper.
    hits = sorted({Path(m) for m in re.findall(
        r"[^\s\"'#]+_spatz_cluster_isle\.sv", manifest.read_text())})
    hits = [h for h in hits if h.is_file()]
    if not hits:
        print("  -> no spatz cluster in this SoC and none nested, nothing to generate")
        return
    if len(hits) > 1:
        die(f"{len(hits)} nested spatz clusters compiled ({', '.join(map(str, hits))}): "
            f"one generated bootrom cannot serve several bases")
    wrapper = hits[0]
    isle = sv_localparams(wrapper)
    text = wrapper.read_text()

    def hardwired(pattern, what):
        m = re.search(pattern, text)
        if not m:
            die(f"{what} not found in {wrapper.name}: the nested cluster's identity "
                f"cannot be read, and guessing it would build a wrong bootrom")
        return int(m.group(1).replace("_", ""), 16)

    # The identity the macro's isle drives into the cluster, and the cluster's own
    # view of global memory (its PMA cached region, the boot memory of the macro).
    base = hardwired(r"\.cluster_base_addr_i\s*\(\s*\d*'h([0-9a-fA-F_]+)", "the cluster base")
    hart = hardwired(r"\.hart_base_id_i\s*\(\s*\d*'h([0-9a-fA-F_]+)", "the hart base")
    mem_base = hardwired(r"cached_regions\[1\]\s*=\s*'\{base:\s*\d*'h([0-9a-fA-F_]+)",
                         "the global-memory region base")
    mask = hardwired(r"cached_regions\[1\][^;]*mask:\s*\d*'h([0-9a-fA-F_]+)",
                     "the global-memory region mask")
    # A PMA mask covers its region: the size is the complement within the width.
    mem_len = ((~mask) & ((1 << 48) - 1)) + 1

    num_cores = need(isle, "NumCores", f"{wrapper.name}")
    tcdm_bytes = need(isle, "OffloadCtrlOffs", f"{wrapper.name}")
    # Widths come from the MACRO's package, not the parent's: the two need not
    # agree (super_noc carries a 5-bit AXI user field where the crux macro carries
    # 10), and the cluster was elaborated against the macro's geometry. The package
    # is identified the same way the wrapper was - by NAME, through the manifest -
    # so a project that gathers several macros' sources into one directory is still
    # served correctly: the macro's module prefix comes off the wrapper's own file
    # name, and its package is that prefix's.
    prefix = wrapper.name[:-len("_spatz_cluster_isle.sv")]
    pkg_hits = sorted({Path(m) for m in re.findall(
        rf"[^\s\"'#]*{re.escape(prefix)}_soc_pkg\.sv", manifest.read_text())})
    pkg_hits = [p for p in pkg_hits if p.is_file()]
    if len(pkg_hits) != 1:
        die(f"expected exactly one '{prefix}_soc_pkg.sv' in the manifest to read "
            f"the nested cluster's bus widths from, found {len(pkg_hits)}")
    pkg = sv_localparams(pkg_hits[0])
    data_width = need(pkg, "AxiDataWidth", "the SoC package")
    updates = {
        "cluster_base_addr": base,
        "cluster_base_hartid": hart,
        "addr_width": need(pkg, "AxiAddrWidth", "the macro's SoC package"),
        "data_width": data_width,
        "user_width": need(pkg, "AxiUserWidth", "the macro's SoC package"),
        "id_width_in": need(isle, "AxiInIdWidth", f"{wrapper.name}"),
        "id_width_out": need(isle, "IwcAxiIdOutWidth", f"{wrapper.name}"),
        "dma_data_width": data_width,
        "axi_cdc_enable": True,
    }
    write_cfg(stock, bender_work, updates, (mem_base, mem_len), num_cores, tcdm_bytes,
              f"nested in {wrapper.parent.parent.parent.name}")


def main():
    if len(sys.argv) < 2:
        die("usage: gen_spatz_cfg.py <bender_work>")
    bender_work = Path(sys.argv[1])

    stock = bender_work / "spatz" / STOCK_CFG
    if not stock.is_file():
        die(f"the IP's stock configuration is missing: {stock}")

    # --- which component is the spatz cluster, and is there exactly one? -------
    comps = map_csv_components()
    spatz = [name for name, typ in comps.items() if typ == ISLE_TYPE]
    if not spatz:
        return generate_for_nested(bender_work, stock)
    if len(spatz) > 1:
        die(f"{len(spatz)} spatz clusters declared ({', '.join(spatz)}), but the "
            f"generated bootrom bakes ONE cluster base and spatz has no alias "
            f"region: a second instance would mis-boot silently. Multi-instance "
            f"spatz needs IP-side support (see docs/developer/wip, section 3.10)")
    comp = spatz[0]

    # The boot/work memory the cluster sees as its global memory: the project's L2.
    l2 = [name for name, typ in comps.items() if typ.endswith("l2_isle")]
    if len(l2) != 1:
        die(f"expected exactly one l2_isle component to map as global memory, "
            f"found {len(l2)}")

    # --- resolved values, read from the generator's own output -----------------
    defs = map_h_defines()
    pkg = sv_localparams(one("generated/hw/*_soc_pkg.sv", "SoC package"))
    isle = sv_localparams(one(f"generated/hw/*_{comp}_isle.sv", "isle wrapper"))

    def addr_of(name):
        hits = [k for k in defs if k.endswith(f"_{name.upper()}_BASE_ADDR")]
        if len(hits) != 1:
            die(f"no unique base-address define for '{name}' in the map header")
        key = hits[0]
        return defs[key], defs[key.replace("_BASE_ADDR", "_SIZE")]

    cluster_base, _cluster_size = addr_of(comp)
    l2_base, l2_size = addr_of(l2[0])

    addr_width = need(pkg, "AxiAddrWidth", "the SoC package")
    data_width = need(pkg, "AxiDataWidth", "the SoC package")
    user_width = need(pkg, "AxiUserWidth", "the SoC package")
    id_in = need(isle, "AxiInIdWidth", "the isle wrapper")
    id_out = need(isle, "IwcAxiIdOutWidth", "the isle wrapper")
    # The core count is user-overridable from the SoC description, so it must come
    # from the instance, not from the wrapper's default: it becomes the bootrom's
    # own core_count, and a stale value there is a wrong bootrom, silently.
    num_cores = instantiated_value(comp, "NumCores",
                                   need(isle, "NumCores", "the isle wrapper"), pkg)
    hart_base = need(isle, "OffloadHartBase", "the isle wrapper")
    # The isle's contract places the cluster peripherals right after the TCDM, so
    # that offset IS the TCDM size; the hjson wants it in KiB.
    tcdm_bytes = need(isle, "OffloadCtrlOffs", "the isle wrapper")

    # --- integration fields, over the IP's own stock configuration -------------
    integration = {
        "cluster_base_addr": cluster_base,
        "cluster_base_hartid": hart_base,
        "addr_width": addr_width,
        "data_width": data_width,
        "user_width": user_width,
        "id_width_in": id_in,
        "id_width_out": id_out,
        # The ROM's word width comes from this field (generate_bootrom.py), and the
        # cluster reads the ROM over its own data bus: a wider ROM word would be
        # silently truncated on the way out, which is the whole reason the shipped
        # 512-bit ROM needs a slicing repair when consumed as is.
        "dma_data_width": data_width,
        # The cluster runs in its own clock domain in every project that has one.
        "axi_cdc_enable": True,
    }
    # The window the cluster treats as global memory, baked into BOOTDATA: the
    # stock value points at a DRAM this SoC does not have, and a window that
    # misses the boot memory leaves the cores unable to fetch from it.
    write_cfg(stock, bender_work, integration, (l2_base, l2_size), num_cores,
              tcdm_bytes, f"for '{comp}'")


if __name__ == "__main__":
    main()

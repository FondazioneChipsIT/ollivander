#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Drop spatz's dead tcdm_interface verification cluster from its Bender manifest.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_spatz.py {bender_work}"

spatz carries its own copy of the tcdm_interface verification cluster: the
spatz_tcdm_test class package (driver, monitor, random master/slave) plus the two
testbenches that consume it. Nothing in a generated SoC references any of them.

It is removed for BOTH simulators rather than filtered out of the Verilator file
list alone: Verilator cannot elaborate the class package, QuestaSim merely tolerates
it, and neither needs it. The package and its consumers go TOGETHER - removing the
package alone leaves QuestaSim compiling testbenches whose classes have vanished,
which is exactly how this gets got wrong.

It also repairs the cluster BOOTROM (hw/system/spatz_cluster/src/generated/bootrom.sv)
on two independent counts, both found by the offload bring-up (wip 2.2 phase 2b):

1. PC-RELATIVE ENTRY SEQUENCE. The shipped ROM bakes its generation
   config's absolute TCDM base into BOOTDATA and derives the entry-point register's
   address from it - wrong at any other instantiation base, unfixable-by-value for
   two instances. The words at offsets 'hbc-'hd4 are replaced with hand-assembled
   PC-relative arithmetic (auipc t2, -'h10; addi t2, t2, -'h64; lw t2, (t2); jr t2;
   nops), which lands on cluster_base + 'h2_0058 (CLUSTER_BOOT_CONTROL's entry
   point) for every instance at any base - spatz_cluster_isle.sv places the ROM at
   cluster_base + 'h3_0000 via BootAddr for exactly this arithmetic. Upstream
   candidate: adopt a PC-relative bootrom like snitch_cluster's.

2. SUB-LINE ADDRESS SLICING. The ROM returns whole 512-bit lines and
   ignores addr[5:0] BY DESIGN, expecting a 512-bit reader to slice; our isle runs
   the cluster's DMA bus at the SoC's 64-bit width, so the connection silently
   truncates rdata to the line's low 64 bits and EVERY instruction fetch returns
   word 0/1 of its 64-byte line (the cores then execute a branch-free stream of
   accidental ALU ops and march linearly through the ROM into the data - observed
   with instruction-port probes). The repair latches addr[5:0]
   and shifts the line by the byte offset, making the ROM correct for ANY reader
   width. Upstream candidate: same shift, or a width assertion at the boundary.

3. spatz_cc's tracer opens its trace file from an 'initial' block that first waits
   for a clock edge, so that 'hart_id_i' has a value before it lands in the file
   name. That event control is a TIMING construct, and Verilator refuses to build a
   hierarchically verilated block ('--lib-create') out of a subtree that uses
   timing: it is what killed super_noc's nested Crux macro tile after 35 minutes of
   build, and only there - the same RTL is fine when it is the top, which is why the
   crossbar family never saw it. snitch_cluster already carries the repair upstream
   (its own tracer wraps the equivalent '#0' in 'ifndef VERILATOR'); spatz is an
   older fork and lacks it, so we apply the same guard. Note the pragma above the
   block is 'pragma translate_off', which Verilator does NOT honour - that is
   precisely why upstream needed the explicit guard rather than relying on it.
   Declared consequence: without the wait, 'hart_id_i' reads as 0 in the two-state
   world at time 0, so the per-hart trace file names can collapse onto hart 0 under
   Verilator. A diagnostic loss, no effect on the simulated behaviour, and the same
   one upstream accepted. Upstream candidate: the guard, or a name built from a
   parameter instead of a port.

The mechanics match the in-registry patch engine: replacements apply on freshly
ledger-restored sources, every touched file is recorded in the checkout's
.ollivander_patched, and a search string that no longer matches is reported as a
stale patch. The bootrom entries lived as two inline registry patches until the
slicing repair pushed the set past the three-per-dependency limit (registry rule),
at which point everything moved here.
"""

import sys
from pathlib import Path

MANIFEST = "Bender.yml"
BOOTROM = "hw/system/spatz_cluster/src/generated/bootrom.sv"
SPATZ_CC = "hw/ip/spatz_cc/src/spatz_cc.sv"

PATCHES = [
    # Bootrom repair 1: PC-relative entry sequence (see module docstring).
    (BOOTROM,
     "0185a383_10500073_30461073",
     "ffff0397_10500073_30461073"),
    (BOOTROM,
     "ffdff06f_10500073_00038067_0003a383_00038393_05838393_01c383b3_0205ae03",
     "ffdff06f_10500073_00000013_00000013_00000013_00038067_0003a383_f9c38393"),
    # Bootrom repair 2: sub-line slicing (see module docstring). Three coordinated
    # replacements: declare the byte-offset register, capture it with the line
    # address, and shift the line by it on the way out.
    (BOOTROM,
     "  logic [AddrBits-1:0] addr_q;",
     "  logic [AddrBits-1:0] addr_q;\n  logic [5:0] addr_low_q;"),
    (BOOTROM,
     "      addr_q <= addr_i[AddrBits-1+6:6];",
     "      addr_q <= addr_i[AddrBits-1+6:6];\n      addr_low_q <= addr_i[5:0];"),
    (BOOTROM,
     "  assign rdata_o = (addr_q < RomSize) ? mem[addr_q] : '0;",
     "  assign rdata_o = (addr_q < RomSize) ? (mem[addr_q] >> (addr_low_q * 8)) : '0;"),
    # Tracer repair: keep the timing construct out of Verilator's way (see docstring).
    # The line occurs once in the whole spatz checkout, so a one-line search is unambiguous.
    (SPATZ_CC,
     "    @(posedge clk_i);",
     "`ifndef VERILATOR\n    @(posedge clk_i);\n`endif"),
    (MANIFEST,
     "    - target: simulation\n      files:\n"
     "        - hw/ip/tcdm_interface/src/tcdm_test.sv\n"
     "    - target: test\n      files:\n        # Level 0\n"
     "        - hw/ip/tcdm_interface/test/reqrsp_to_tcdm_tb.sv\n"
     "        - hw/ip/tcdm_interface/test/tcdm_mux_tb.sv",
     "    - target: simulation\n      files: []"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_spatz.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "spatz"
    if not root.is_dir():
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for spatz: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace, 1), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for spatz: '{search.strip()[:60]}' no longer "
                  f"occurs in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_spatz: {len(PATCHES) - stale} replacements in {len(touched)} files"
          + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

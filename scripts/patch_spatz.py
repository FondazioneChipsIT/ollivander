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

The cluster BOOTROM is NO LONGER repaired here. It used to be, on two counts, and
both are now structurally impossible instead of patched away: the registry runs the
IP's own meta-generation (clustergen) over a configuration generated from THIS
project's resolved values, so the ROM is built with the project's own cluster base
in its BOOTDATA (nothing left to correct) and with a word width equal to the SoC's
data bus, so the reader no longer truncates a wider line (nothing left to slice).
The one repair that could not be config-driven survives, because it is not in a
generated file:

1. spatz_cc's tracer opens its trace file from an 'initial' block that first waits
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
stale patch.
"""

import sys
from pathlib import Path

MANIFEST = "Bender.yml"
SPATZ_CC = "hw/ip/spatz_cc/src/spatz_cc.sv"

PATCHES = [
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

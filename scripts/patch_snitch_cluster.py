#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Drop snitch_cluster's dead verification collateral from its Bender manifest.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_snitch_cluster.py {bender_work}"

Five file groups, all of them verification collateral that a generated SoC never
instantiates, and all removed for BOTH simulators. The asymmetry that used to drive
these removals - Verilator refuses the class-based drivers, QuestaSim tolerates them -
is not a reason to keep feeding either tool sources nobody uses.

1. The IP's own testharness, which the enabled 'snitch_cluster_wrapper' target pulls
   in: it expects register headers only the IP's standalone flow generates, so it
   fails to compile with "Macro `SNITCH_CLUSTER_PERIPHERAL_REG_SCRATCH_1_REG_OFFSET
   is undefined". The SoC brings its own testbench.
2/3. The tcdm_interface and mem_interface verification clusters: a driver/monitor
   class package plus the testbenches that use it. Driver and consumers are removed
   TOGETHER - removing the package alone breaks QuestaSim, which still compiles the
   consumers (learned the hard way on 2026-08-06).
4. The snitch_ssr fixtures and testbenches, referenced by nothing.
5. The tcdm interconnect testbench, same.

The mechanics match the in-registry patch engine: replacements apply on freshly
ledger-restored sources, every touched file is recorded in the checkout's
.ollivander_patched, and a search string that no longer matches is reported as a
stale patch.
"""

import sys
from pathlib import Path

MANIFEST = "Bender.yml"

PATCHES = [
    # 1. The IP's own testharness.
    (MANIFEST,
     "  - target: all(snitch_cluster_wrapper, any(simulation, verilator))\n"
     "    include_dirs:\n      - hw/generated\n    files:\n"
     "      - target/sim/tb/vip_snitch_cluster.sv\n      - target/sim/tb/testharness.sv",
     "  - target: all(snitch_cluster_wrapper, any(simulation, verilator))\n"
     "    include_dirs:\n      - hw/generated\n    files: []"),
    # 2. tcdm_interface verification cluster (driver package + its two testbenches).
    (MANIFEST,
     "  - target: simulation\n    files:\n      - hw/tcdm_interface/src/tcdm_test.sv\n"
     "  - target: test\n    files:\n"
     "      - hw/tcdm_interface/test/reqrsp_to_tcdm_tb.sv\n"
     "      - hw/tcdm_interface/test/tcdm_mux_tb.sv",
     "  - target: simulation\n    files: []"),
    # 3. mem_interface verification cluster (same shape).
    (MANIFEST,
     "  - target: simulation\n    files:\n      - hw/mem_interface/src/mem_test.sv\n"
     "  - target: test\n    files:\n"
     "      - hw/mem_interface/test/mem_wide_narrow_mux_tb.sv",
     "  - target: simulation\n    files: []"),
    # 4. snitch_ssr fixtures and testbenches.
    (MANIFEST,
     "  - target: test\n    files:\n      # Level 0\n"
     "      - hw/snitch_ssr/test/fixture_ssr.sv\n"
     "      - hw/snitch_ssr/test/fixture_ssr_streamer.sv\n      # Level 1\n"
     "      - hw/snitch_ssr/test/tb_simple_ssr.sv\n"
     "      - hw/snitch_ssr/test/tb_simple_ssr_streamer.sv",
     "  - target: test\n    files: []"),
    # 5. tcdm interconnect testbench.
    (MANIFEST,
     "  - target: test\n    files:\n"
     "      - hw/snitch_cluster/test/snitch_tcdm_interconnect_tb.sv",
     "  - target: test\n    files: []"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_snitch_cluster.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "snitch_cluster"
    if not root.is_dir():
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for snitch_cluster: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace, 1), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for snitch_cluster: '{search.strip()[:60]}' no longer "
                  f"occurs in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_snitch_cluster: {len(PATCHES) - stale} replacements in {len(touched)} files"
          + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

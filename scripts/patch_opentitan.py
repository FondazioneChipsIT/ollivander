#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Apply the opentitan source and manifest repairs inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_opentitan.py {bender_work}"

Two repair families:

1. Two xbar_cfg_t literals predate this axi fork's multicast fields
   (NoMulticastRules/NoMulticastPorts): complete under the axi they were vendored
   against, incomplete assignment patterns under ours, which Verilator refuses at
   elaboration. default: '0 keeps them complete whatever fields the fork adds next.

2. A dead verification cluster in the 'test' target: the astral testbenches, their
   tb/util helpers, the vendored jtag_test (riscv-dbg carries its own copy, which is
   the one its testbenches use) and pad_alsaqr, which only those testbenches
   instantiate. Verified inert: nothing outside the cluster references
   any of them, and the only external consumer of tb/util/uart.sv is pulp_cluster's
   own tb cluster, removed in the same pass (patch_pulp_cluster.py). Removed for BOTH
   simulators - Verilator refuses part of it, QuestaSim merely tolerates all of it,
   and neither needs any of it. The three include files of the same target stay: they
   carry defines and interfaces the RTL does use, which is why this removes the dead
   files rather than the target.

The mechanics match the in-registry patch engine: replacements apply on freshly
ledger-restored sources, every touched file is recorded in the checkout's
.ollivander_patched, and a search string that no longer matches is reported as a
stale patch.
"""

import sys
from pathlib import Path

WRAP = "hw/top_earlgrey/top/secure_subsystem_asynch_synth_wrap_astral.sv"
IDMA = "hw/ip/crypto_sram_wrap/rtl/idma_wrap.sv"
MANIFEST = "Bender.yml"

PATCHES = [
    (WRAP,
     "    NoAddrRules:                   NumAxiRules\n  };",
     "    NoAddrRules:                   NumAxiRules,\n    default: '0\n  };"),
    (IDMA,
     "    NoAddrRules:                      NumRules\n  };",
     "    NoAddrRules:                      NumRules,\n    default: '0\n  };"),
    (MANIFEST,
     "           - hw/tb/util/uart.sv\n"
     "           - hw/tb/util/jtag_intf.sv\n"
     "           - hw/tb/util/axi2mem_tb.sv\n"
     "           - hw/vendor/pulp_riscv_dbg/src/jtag_test.sv\n"
     "           - hw/vendor/common_pads/src/pad_alsaqr.sv\n"
     "           - hw/tb/vip_security_island_soc.sv\n"
     "           - hw/tb/testbench_asynch_astral.sv\n"
     "\n"
     "      -  target: test_ot_vip",
     "\n      -  target: test_ot_vip"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_opentitan.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "opentitan"
    if not root.is_dir():
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for opentitan: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for opentitan: '{search.strip()[:60]}' no longer "
                  f"occurs in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_opentitan: {len(PATCHES) - stale} replacements in {len(touched)} files"
          + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

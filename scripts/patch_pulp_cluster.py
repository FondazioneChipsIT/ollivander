#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Apply the pulp_cluster source repairs inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_pulp_cluster.py {bender_work}"

Three repair families, each documented at its patch group below:

1. cluster_interconnect_wrap still passes hci_interconnect the seven geometry
   overrides of an older hci, which the pinned hci derives internally from the
   HCI_SIZE macros - four are localparams now and three are not declared at all.
   Dead under QuestaSim (discarded with the 2732 warning the test suite keeps
   visible), refused outright by Verilator. NOT an upstream defect: pulp-platform's
   master carries these lines consistently with the older hci *it* requires - the
   incongruence is our own hci forcing, and the fix belongs at most in the
   CHIPS-IT fork alongside it. idma_wrap's boffs/lrdy ties are the same thread:
   interface members the pinned hci dropped, in a generate branch dead under our
   configuration, which Verilator link-checks anyway.

2. Verilator's constant evaluator cannot read unpacked-struct constants (5.050,
   "SimulateVisitor: unknown node"): Cfg.NumCores as a generate-for bound and
   Cfg.HwpeCfg handed down to hwpe_subsystem never fold, which stops every
   crossbar elaboration. Both configuration structs are made packed: every member
   is packable, all their literals are named assignment patterns, and no code
   bit-slices the whole struct (verified across the repository 2026-08-06), so
   QuestaSim semantics are unchanged. This also unfreezes opentitan's
   OTClusterCfg, a literal of the same typedef. Upstream candidate, see
   docs/developer/wip/upstream_pr_candidates.md.

3. cluster_bus_wrap's xbar_cfg_t literal predates this axi fork's multicast
   fields (NoMulticastRules/NoMulticastPorts): once Verilator elaborates it the
   incomplete pattern is an error; default: '0 keeps it complete whatever fields
   the fork adds next.

These replacements lived as {file, search, replace} triples in the dependency
registry and moved here verbatim when their volume outgrew the YAML (2026-08-06).
The mechanics are unchanged: replacements apply on freshly ledger-restored
sources, every touched file is recorded in the checkout's .ollivander_patched,
and a search string that no longer matches is reported as a stale patch, exactly
like the in-registry engine does.
"""

import sys
from pathlib import Path

ICW = "rtl/cluster_interconnect_wrap.sv"
IDMA = "rtl/idma_wrap.sv"
PKG = "packages/pulp_cluster_package.sv"
CBW = "rtl/cluster_bus_wrap.sv"
MANIFEST = "Bender.yml"

PATCHES = [
    # 1. Dead geometry overrides of an older hci (deleted lines).
    # Deletions leave the (now empty) line in place - byte-identical to how the
    # inline registry engine applied them.
    (ICW, "        .AWC    ( ADDR_WIDTH             ),", ""),
    (ICW, "        .DW_LIC ( DATA_WIDTH             ),", ""),
    (ICW, "        .DW_SIC ( NB_HWPE_PORTS*32       ),", ""),
    (ICW, "        .AWH    ( 32                     ),", ""),
    (ICW, "        .DWH    ( 288                    ),", ""),
    (ICW, "        .OWH    ( 1                      ),", ""),
    (ICW, "        .AWM    ( ADDR_MEM_WIDTH+2       ),", ""),
    # 1b. Interface-member ties the pinned hci dropped (deleted lines).
    (IDMA, "        assign tcdm_master[NB_TCDM_PORTS_PER_STRM*s+4].boffs = '0;", ""),
    (IDMA, "        assign tcdm_master[NB_TCDM_PORTS_PER_STRM*s+4].lrdy  = '0;", ""),
    (IDMA, "        assign tcdm_master[NB_TCDM_PORTS_PER_STRM*s+5].boffs = '0;", ""),
    (IDMA, "        assign tcdm_master[NB_TCDM_PORTS_PER_STRM*s+5].lrdy  = '0;", ""),
    # 2. Packed-ification of pulp_cluster_cfg_t and hwpe_subsystem_cfg_t (the only
    #    two unpacked typedefs in the package; replacement covers both).
    (PKG, "  typedef struct {", "  typedef struct packed {"),
    # 4. The IP's own testbench cluster (a mock UART, its AXI wrapper and the cluster
    #    testbench): nothing in a generated SoC instantiates them, and they are the
    #    only consumers of opentitan's tb/util/uart.sv, dropped in the same pass.
    #    Removed for both simulators - Verilator refuses them, QuestaSim only tolerates
    #    them, neither needs them.
    (MANIFEST,
     "  - target: test\n    files:\n      - tb/mock_uart.sv\n"
     "      - tb/mock_uart_axi.sv\n      - tb/pulp_cluster_tb.sv",
     "  - target: test\n    files: []"),
    # 3. Complete the xbar_cfg_t literal against the fork's multicast fields.
    (CBW,
     "                                          NoAddrRules: N_RULES\n"
     "                                          };",
     "                                          NoAddrRules: N_RULES,\n"
     "                                          default: '0\n"
     "                                          };"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_pulp_cluster.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "pulp_cluster"
    if not root.is_dir():
        # A graph without pulp_cluster has nothing to repair.
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for pulp_cluster: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for pulp_cluster: '{search.strip()[:60]}' no longer "
                  f"occurs in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_pulp_cluster: {len(PATCHES) - stale} replacements in "
          f"{len(touched)} files" + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

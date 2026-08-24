#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Split hwpe_ctrl_slave's mixed-style flags_o drive for Verilator.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_hwpe_ctrl.py {bender_work}"

hwpe_ctrl_slave drives its packed flags_o struct output with mixed styles: four
fields non-blocking in always_ff processes, the rest through continuous assigns.
Legal SystemVerilog, but Verilator refuses mixed blocking/non-blocking drives to
a single packed struct as unsupported (BLKANDNBLK); QuestaSim never minded. The
sequential fields are renamed onto intermediate registers (flags_*_q) and exposed
through continuous assignments, so every field of flags_o is driven in one style.
Upstream candidate (Verilator-compatibility PR), see
docs/developer/wip/upstream_pr_candidates.md.

ORDER MATTERS below: the four renames run first and hit every occurrence of the
struct fields, the anchored insertion then introduces the register declarations
and the flags_o continuous assigns - written AFTER the renames precisely so the
rename pass cannot reach them (re-ordering this list recreates the
self-assignment defect it once caused).

These replacements lived as {file, search, replace} triples in the dependency
registry and moved here verbatim when their volume outgrew the YAML.
The mechanics are unchanged: replacements apply on freshly ledger-restored
sources, every touched file is recorded in the checkout's .ollivander_patched,
and a search string that no longer matches is reported as a stale patch, exactly
like the in-registry engine does.
"""

import sys
from pathlib import Path

SLAVE = "rtl/hwpe_ctrl_slave.sv"

PATCHES = [
    (SLAVE, "flags_o.start", "flags_start_q"),
    (SLAVE, "flags_o.evt", "flags_evt_q"),
    (SLAVE, "flags_o.is_working", "flags_is_working_q"),
    (SLAVE, "flags_o.sw_evt", "flags_sw_evt_q"),
    (SLAVE,
     "  assign flags_o.done = regfile_flags.true_done;",
     "  // Registered flags, driven in the sequential processes below and exposed through\n"
     "  // continuous assignments so that every field of flags_o is driven in one style:\n"
     "  // mixed blocking/non-blocking drives to a single packed struct are refused\n"
     "  // by Verilator (BLKANDNBLK); QuestaSim semantics are unchanged.\n"
     "  logic                                              flags_start_q;\n"
     "  logic [REGFILE_N_MAX_CORES-1:0][REGFILE_N_EVT-1:0] flags_evt_q;\n"
     "  logic                                              flags_is_working_q;\n"
     "  logic [7:0]                                        flags_sw_evt_q;\n"
     "  assign flags_o.start      = flags_start_q;\n"
     "  assign flags_o.evt        = flags_evt_q;\n"
     "  assign flags_o.is_working = flags_is_working_q;\n"
     "  assign flags_o.sw_evt     = flags_sw_evt_q;\n"
     "\n"
     "  assign flags_o.done = regfile_flags.true_done;"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_hwpe_ctrl.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "hwpe-ctrl"
    if not root.is_dir():
        # A graph without hwpe-ctrl has nothing to repair.
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for hwpe-ctrl: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for hwpe-ctrl: '{search.strip()[:60]}' no longer "
                  f"occurs in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_hwpe_ctrl: {len(PATCHES) - stale} replacements in "
          f"{len(touched)} files" + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

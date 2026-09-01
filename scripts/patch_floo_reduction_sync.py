#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Make floo_reduction_sync's filter order-safe against QuestaSim's optimizer.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_floo_reduction_sync.py {bender_work}"

WHAT THE UPSTREAM CODE DOES, AND WHY IT IS NOT WRONG. floo_reduction_sync filters
the incoming valids of a reduction so that only flits belonging to the SAME
collective stream (same destination, same member mask) as the arbiter's selected
lane reach the downstream stream_join_dynamic. It computes that with six parallel
continuous assignments - one scalar plus a genvar row - each of which re-reads the
DYNAMICALLY selected lane, `valid_i[sel_i]` and `data_i[sel_i]`. That is legal,
race-free SystemVerilog: the assignments are pure functions of the module's inputs
and the LRM prescribes one unambiguous steady state.

WHY IT IS PATCHED ANYWAY. QuestaSim's default vopt merges those assignments into a
single process with a fixed evaluation order, and the merged code can read the
dynamic select STALE with respect to sel_i. The filter then freezes at zero, the
join never fires, and the collective transport wedges - silently: no error, no
assertion, the simulation simply runs to its watchdog. Measured on this design
(2026-08-31/09-01), one variable at a time:

  * QuestaSim 2026.1_2, default vopt, upstream file    -> wedges at the first
    collective store (no [COLLECTIVE] line, watchdog $finish)
  * same build, `-voptargs=+acc=rn+floo_reduction_sync.` (that ONE module)
                                                        -> fully green
  * same build, this patch, default vopt, no +acc anywhere
                                                        -> fully green
  * Verilator 5.050 -O1 and -O3, upstream file AND patched file
                                                        -> green in all four cells

Two independent schedulers execute the upstream code correctly at every usable
optimization level; only Questa's default optimizer does not. FlooNoC's own
developers report the failure disappears on QuestaSim 2022, which makes it a tool
REGRESSION rather than a fact of life - and pinning the whole team to a 2022
simulator is a worse remedy than these two dozen lines.

WHAT THE PATCH CHANGES. Nothing functional. The six parallel assignments become a
single always_comb that samples the selected lane EXACTLY ONCE into local
variables and derives the mask and the filtered valids from those. Same logic,
same combinational depth, no registers added - but with the dynamic selects read
once, in a stated order, the optimizer has nothing left to reorder.

Filed for upstream in docs/developer/wip/upstream_pr_candidates.md, as hardening
for FlooNoC and as a defect report for Siemens (the bisection above is the
reproduction). Drop this script when FlooNoC ships an equivalent rewrite, or when
the simulator stops mis-scheduling the original.
"""

import sys
from pathlib import Path

SYNC = "hw/floo_reduction_sync.sv"

SEARCH = """  logic [NumRoutes-1:0]  filtered_valid_in;


  logic [NumRoutes-1:0] filtered_route_mask;
  // The incoming mask is combinatorial. The valid is used to make sure the mask used in the following logic
  // is actually from a valid flit.
  assign filtered_route_mask = in_route_mask_i & {NumRoutes{valid_i[sel_i]}};


  // Filter valids from the expected input sources.
  for (genvar in = 0; in < NumRoutes; in++) begin : gen_valid
    // Only valid from same reduction streams are propagated
    assign filtered_valid_in[in] =  valid_i[in] && valid_i[sel_i] &&
                          (data_i[in].hdr.dst_id == data_i[sel_i].hdr.dst_id) &&
                          (data_i[in].hdr.collective_mask == data_i[sel_i].hdr.collective_mask);

  end"""

REPLACE = """  logic [NumRoutes-1:0]  filtered_valid_in;
  logic [NumRoutes-1:0]  filtered_route_mask;

  // OLLIVANDER PATCH (2026-09-01, scripts/patch_floo_reduction_sync.py): the
  // upstream code computes this filter with six parallel continuous assigns,
  // each re-reading the dynamically selected lane (valid_i[sel_i],
  // data_i[sel_i]). That is correct SystemVerilog - Verilator executes it right
  // at -O1 and -O3 - but QuestaSim's default vopt merges those assigns into one
  // process that can read the dynamic select STALE with respect to sel_i: the
  // filter then freezes at zero, the join below never fires, and the collective
  // transport wedges with no error and no assertion. Bisected to THIS module by
  // scoped +acc. The rewrite is purely structural: sample the selected lane once
  // into locals, derive mask and filtered valids from those, in stated order.
  always_comb begin
    logic  sel_valid;
    flit_t sel_flit;
    sel_valid           = valid_i[sel_i];
    sel_flit            = data_i[sel_i];
    // The incoming mask is combinatorial. The valid is used to make sure the
    // mask used in the following logic is actually from a valid flit.
    filtered_route_mask = in_route_mask_i & {NumRoutes{sel_valid}};
    // Filter valids from the expected input sources: only valids belonging to
    // the same reduction stream are propagated.
    for (int unsigned in = 0; in < NumRoutes; in++) begin
      filtered_valid_in[in] = valid_i[in] && sel_valid &&
                            (data_i[in].hdr.dst_id == sel_flit.hdr.dst_id) &&
                            (data_i[in].hdr.collective_mask == sel_flit.hdr.collective_mask);
    end
  end"""


def main():
    if len(sys.argv) != 2:
        print("usage: patch_floo_reduction_sync.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "floo_noc"
    if not root.is_dir():
        # A crossbar-topology graph carries no floo_noc: nothing to repair.
        return

    f = root / SYNC
    if not f.is_file():
        print(f"  [WARNING] Stale patch for floo_noc: target file missing: {f}")
        return

    text = f.read_text(encoding="utf-8")
    if SEARCH not in text:
        # Either the rewrite is already in (a re-run on a patched checkout), or
        # upstream changed the filter - both need the reader's attention, but
        # only the second is a defect. Distinguish them by the marker.
        if "OLLIVANDER PATCH" in text:
            print("  -> patch_floo_reduction_sync: already applied, nothing to do")
        else:
            print("  [WARNING] Stale patch for floo_noc: the filter in "
                  f"{SYNC} no longer matches the expected upstream text. The "
                  "QuestaSim wedge it works around may be back - revise it.")
        return

    f.write_text(text.replace(SEARCH, REPLACE), encoding="utf-8")
    print(f"  -> patch_floo_reduction_sync: order-safe filter applied to {SYNC}")

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | {str(f)})) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

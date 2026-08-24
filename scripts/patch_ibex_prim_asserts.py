#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Align ibex's vendored lowRISC assertion macros with their modern call signature.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_ibex_prim_asserts.py {bender_work}"

ibex's vendored lowrisc_ip prim_assert.sv redefines the whole ASSERT macro family
(guard PRIM_ASSERT_SV) after common_cells' modern assertions.svh has parsed,
inside Verilator's single compilation unit; later callers then get the 4-argument
lowRISC signatures - FlooNoC's five-argument ASSERT calls and snitch's
six-argument ASSERT_IF stop parsing, and ASSERT_STABLE vanishes. These patches
give the lowRISC macros the same trailing optional __desc argument (swallowed,
bodies untouched) so both calling conventions parse regardless of include order;
the dummy variant is the one Verilator selects (it predefines VERILATOR), and
QuestaSim compiles per file and never sees the clash. Note for the super
examples: opentitan vendors the same lowRISC file under the same guard, so this
pattern must be replicated there when both families share a unit.

These replacements lived as {file, search, replace} triples in the dependency
registry and moved here verbatim when their volume outgrew the YAML.
The mechanics are unchanged: files are applied on freshly ledger-restored sources,
every touched file is recorded in the checkout's .ollivander_patched, and a search
string that no longer matches is reported as a stale patch, exactly like the
in-registry engine does.
"""

import sys
from pathlib import Path

DUMMY = "vendor/lowrisc_ip/ip/prim/rtl/prim_assert_dummy_macros.svh"
REAL = "vendor/lowrisc_ip/ip/prim/rtl/prim_assert.sv"

PATCHES = [
    (DUMMY,
     '`define ASSERT_I(__name, __prop)',
     '`define ASSERT_I(__name, __prop, __desc = "")'),
    (DUMMY,
     '`define ASSERT_INIT(__name, __prop)',
     '`define ASSERT_INIT(__name, __prop, __desc = "")'),
    (DUMMY,
     '`define ASSERT_FINAL(__name, __prop)',
     '`define ASSERT_FINAL(__name, __prop, __desc = "")'),
    (DUMMY,
     '`define ASSERT(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)',
     '`define ASSERT(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "")'),
    (DUMMY,
     '`define ASSERT_NEVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)',
     '`define ASSERT_NEVER(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "")'),
    (DUMMY,
     '`define ASSERT_KNOWN(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)',
     '`define ASSERT_KNOWN(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "")'),
    (DUMMY,
     '`define ASSUME(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST)',
     '`define ASSUME(__name, __prop, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "")'),
    # ASSUME_I also anchors the injection of ASSERT_STABLE, which this vendored
    # header predates entirely.
    (DUMMY,
     '`define ASSUME_I(__name, __prop)',
     '`define ASSUME_I(__name, __prop, __desc = "")\n'
     '`define ASSERT_STABLE(__name, __valid, __ready, __data, __mask = \'0, '
     '__clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "")'),
    (REAL,
     '`define ASSERT_PULSE(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST) \\',
     '`define ASSERT_PULSE(__name, __sig, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "") \\'),
    (REAL,
     '`define ASSERT_IF(__name, __prop, __enable, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST) \\',
     '`define ASSERT_IF(__name, __prop, __enable, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "") \\'),
    (REAL,
     '`define ASSERT_KNOWN_IF(__name, __sig, __enable, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST) \\',
     '`define ASSERT_KNOWN_IF(__name, __sig, __enable, __clk = `ASSERT_DEFAULT_CLK, __rst = `ASSERT_DEFAULT_RST, __desc = "") \\'),
]


def main():
    if len(sys.argv) != 2:
        print("usage: patch_ibex_prim_asserts.py <bender_work>")
        sys.exit(1)
    root = Path(sys.argv[1]).resolve() / "ibex"
    if not root.is_dir():
        # A graph without the standalone ibex has nothing to align.
        return

    touched, stale = set(), 0
    for rel, search, replace in PATCHES:
        f = root / rel
        if not f.is_file():
            print(f"  [WARNING] Stale patch for ibex: target file missing: {f}")
            stale += 1
            continue
        text = f.read_text(encoding="utf-8")
        if search in text:
            f.write_text(text.replace(search, replace), encoding="utf-8")
            touched.add(str(f))
        else:
            print(f"  [WARNING] Stale patch for ibex: '{search[:60]}' no longer occurs "
                  f"in {f.name}. It has no effect and should be revised.")
            stale += 1
    print(f"  -> patch_ibex_prim_asserts: {len(PATCHES) - stale} replacements in "
          f"{len(touched)} files" + (f", {stale} stale" if stale else ""))

    ledger = root / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | touched)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Rename opentitan's vendored ibex out of the standalone ibex's way inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_ibex_ot.py {bender_work}"

opentitan vendors a lowRISC ibex under hw/vendor/lowrisc_ibex for its security island, and the
safety island brings the standalone ibex repository into the same graph. Compiled into one
library the two trees collide on every ibex_* global name - package, modules - and the last one
compiled wins, so one of the two cores elaborates against the other's package. QuestaSim hides
this as a design-unit overwrite (message 13233, suppressed as routine Bender noise) and happens
to survive on version compatibility; Verilator's single compilation unit surfaces it as missing
package members ('lfsr_seed_t', 'RndCnstLfsrSeedDefault') and unknown ports. Third instance of
the same-name collision family, after cva6's aes and spatz/snitch.

The colliding set is DISCOVERED at every run by intersecting the declarations of the two ibex
trees - and only of the ibex trees: both repositories also vendor lowRISC prim_* cells, so an
intersection taken over the whole checkouts would drag every primitive into the rename and
corrupt the rest of opentitan. The opentitan side is the one renamed because its consumers all
live inside the same checkout (rv_core_ibex and the DV collateral), so the rename can be applied
tree-wide there; the standalone ibex's names are referenced by the safety island RTL, which is
not ours to rewrite. When either tree is absent the script does nothing.

Idempotency is delegated to the generator's ledger, exactly as in patch_spatz_snitch.py: every
edited file is recorded in the checkout's .ollivander_patched and restored to its fetched state
before the next run, so dropping this command from the registry undoes the rename.
"""

import re
import sys
from pathlib import Path

# Global-scope declarations that land in the compilation library by name.
DECL = re.compile(r"^\s*(?:package|module|interface)\s+(?:automatic\s+)?([a-zA-Z_][a-zA-Z_0-9]*)",
                  re.M)


def declared_names(tree: Path) -> set[str]:
    """Collect every package, module and interface name declared under a directory."""
    names = set()
    for f in list(tree.rglob("*.sv")) + list(tree.rglob("*.svh")):
        if ".git" in f.parts:
            continue
        try:
            names |= set(DECL.findall(f.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return names


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: patch_ibex_ot.py <bender_work>")
    bender_work = Path(sys.argv[1]).resolve()
    opentitan = bender_work / "opentitan"
    vendored = opentitan / "hw" / "vendor" / "lowrisc_ibex"
    rival = bender_work / "ibex" / "rtl"
    if not vendored.is_dir():
        return  # opentitan (or its vendored ibex) is not part of this SoC: nothing to repair.
    if not rival.is_dir():
        print("  -> patch_ibex_ot: standalone ibex is not in the checkout, rename skipped")
        return

    colliding = sorted(declared_names(vendored) & declared_names(rival))
    if not colliding:
        print("  [WARNING] patch_ibex_ot: the two ibex trees no longer declare any common name;"
              " this pre-build command has no effect and should be revised.")
        return
    print(f"  -> patch_ibex_ot: renaming to ot_* the {len(colliding)} declarations opentitan's"
          f" vendored ibex shares with the standalone ibex")

    # The declarations live under hw/vendor/lowrisc_ibex, but the references extend to the
    # rv_core_ibex wrapper and the DV collateral, so the substitution walks the whole opentitan
    # checkout. Safe by construction: opentitan has no ibex of its own besides the vendored one,
    # so every occurrence of a colliding name inside the checkout belongs to it.
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in colliding) + r")\b")
    touched = []
    for f in list(opentitan.rglob("*.sv")) + list(opentitan.rglob("*.svh")):
        if ".git" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        renamed = pattern.sub(lambda m: f"ot_{m.group(1)}", text)
        if renamed != text:
            f.write_text(renamed, encoding="utf-8")
            touched.append(str(f))
    print(f"  -> patch_ibex_ot: {len(touched)} files renamed")

    ledger = opentitan / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | set(touched))) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

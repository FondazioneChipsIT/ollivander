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
which is exactly how this was got wrong first (2026-08-06).

The mechanics match the in-registry patch engine: replacements apply on freshly
ledger-restored sources, every touched file is recorded in the checkout's
.ollivander_patched, and a search string that no longer matches is reported as a
stale patch.
"""

import sys
from pathlib import Path

MANIFEST = "Bender.yml"

PATCHES = [
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

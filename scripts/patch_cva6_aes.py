#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Repair cva6's scalar-cryptography (Zknd/Zkne) sources inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_cva6_aes.py {bender_work}"

There are two independent problems, established by removing the previous declarative patches and
observing how each topology fails:

  1. cva6's own Bender.yml does not compile core/include/aes_pkg.sv and core/aes.sv, although
     ex_stage.sv instantiates the unit inside `generate if (CVA6Cfg.ZKN)`, and the configurations
     Ollivander selects (cv64a6_imafdc_sv39 and its hpdcache_wb variant) set ZKN to 1. Without the
     sources the NoC example fails with "Module 'aes' is not defined". This affects every SoC and is
     therefore applied unconditionally.

  2. The package and the module are named aes_pkg and aes, which collide with OpenTitan's AES IP
     when both are compiled into one library. The crossbar example does not fail with a missing
     module but with the *wrong* one: "Port 'fu_data_i' not found in module 'aes'", because the
     instance binds OpenTitan's module. The rename to cva6_aes_* is therefore applied only when a
     competing declaration is actually present in the checkout - which is what the condition below
     expresses, and what a flat patch could not.

The script restores its own targets before editing them, as the declarative `patches` mechanism does,
so that repeated runs converge instead of layering: a replacement that contains its own search string
would otherwise accumulate on every generation.
"""

import re
import subprocess
import sys
from pathlib import Path

# Renames applied only when a competing 'aes' declaration exists elsewhere in the checkout.
RENAMES = [
    ("core/include/aes_pkg.sv", "package aes_pkg;", "package cva6_aes_pkg;"),
    ("core/aes.sv", "import aes_pkg::*;", "import cva6_aes_pkg::*;"),
    ("core/aes.sv", "module aes", "module cva6_aes"),
    ("core/ex_stage.sv", "      aes #(", "      cva6_aes #("),
]

# Source files cva6's manifest omits, each added next to a line guaranteed to be present. The name
# is carried explicitly rather than parsed back out of the replacement, since the new entry is not
# always the first line of it.
MANIFEST_ADDITIONS = [
    ("core/include/aes_pkg.sv",
     "      - core/include/wt_cache_pkg.sv",
     "      - core/include/aes_pkg.sv\n      - core/include/wt_cache_pkg.sv"),
    ("core/aes.sv",
     "      - core/alu.sv",
     "      - core/alu.sv\n      - core/aes.sv"),
]


def restore(repo: Path, rel: str) -> None:
    """Return one tracked file to its fetched state, so that editing is idempotent."""
    target = repo / rel
    if not target.parent.is_dir():
        return
    r = subprocess.run(["git", "-C", str(repo), "checkout", "--", rel],
                       capture_output=True, text=True)
    if r.returncode != 0 and target.is_file():
        sys.exit(f"[ERROR] patch_cva6_aes: cannot restore {rel}: {r.stderr.strip()}")


def substitute(path: Path, search: str, replace: str, what: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if search not in text:
        # The file was just restored, so a missing search string means the IP no longer contains
        # what this script was written against - not that the edit is already in place.
        print(f"  [WARNING] patch_cva6_aes: '{search.strip()[:48]}' no longer occurs in "
              f"{path.name}; {what} had no effect and should be revised.")
        return False
    path.write_text(text.replace(search, replace), encoding="utf-8")
    return True


def competing_aes(bender_work: Path, cva6: Path) -> Path | None:
    """Find another IP declaring 'aes_pkg' or a module named 'aes', which cva6 would collide with."""
    pattern = re.compile(r"^\s*(package\s+aes_pkg\s*;|module\s+aes\b)", re.M)
    for sv in bender_work.rglob("*.sv"):
        if cva6 in sv.parents:
            continue
        try:
            if pattern.search(sv.read_text(encoding="utf-8", errors="ignore")):
                return sv
        except OSError:
            continue
    return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: patch_cva6_aes.py <bender_work>")
    bender_work = Path(sys.argv[1]).resolve()
    cva6 = bender_work / "cva6"
    if not cva6.is_dir():
        return  # cva6 is a transitive dependency of cheshire: absent in a SoC without it.

    for rel, _, _ in RENAMES:
        restore(cva6, rel)
    restore(cva6, "Bender.yml")

    for added, search, replace in MANIFEST_ADDITIONS:
        if substitute(cva6 / "Bender.yml", search, replace, f"adding {added}"):
            print(f"  -> patch_cva6_aes: compiling {added}")

    rival = competing_aes(bender_work, cva6)
    if rival is None:
        print("  -> patch_cva6_aes: no competing 'aes' declaration in the checkout, rename skipped")
        return
    print(f"  -> patch_cva6_aes: renaming to cva6_aes_* ('aes' is also declared by "
          f"{rival.relative_to(bender_work)})")
    for rel, search, replace in RENAMES:
        f = cva6 / rel
        if f.is_file():
            substitute(f, search, replace, f"renaming in {rel}")


if __name__ == "__main__":
    main()

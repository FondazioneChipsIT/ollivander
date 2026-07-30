#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Rename spatz's vendored snitch-family IPs out of snitch_cluster's way inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_spatz_snitch.py {bender_work}"

spatz ships its own copies of the snitch core and of its companion interface IPs (hw/ip/snitch,
reqrsp_interface, tcdm_interface, mem_interface), unconditionally listed in its manifest, and
snitch_cluster ships the same IPs several revisions later. Compiled into one library the two
trees collide on dozens of global names - packages, modules and interfaces - and the last one
compiled wins, so half the design elaborates against the wrong revision: first observed as
"Failed to find the name 'amo_op_e' in scope 'snitch_pkg'" at elaboration, then again on
mem_wide_narrow_mux, whose older copy lacks two ports. The two IPs never met before the super
examples put both families in one SoC: no released revision of either side avoids the clash, so
the repair is a rename, exactly as for cva6's aes unit.

The set of names to rename is DISCOVERED at every run, by intersecting the package, module and
interface declarations of the two checkouts: a hardcoded list proved too narrow once (measuring
only hw/ip/snitch missed the interface IPs) and would silently rot when either side is updated.
The spatz side is the one renamed because it is self-contained: nothing outside the spatz
checkout references its vendored copies - spatz's own top ('spatz_cluster') is declared by spatz
alone, so it can never enter the intersection - while snitch_cluster's names are baked into the
already-generated RTL of the mesh macros. When snitch_cluster is not part of the SoC the script
does nothing, so the projects that instantiate spatz alone compile the sources exactly as
fetched.

Idempotency is delegated to the generator's ledger: every file this script edits is recorded in
the checkout's .ollivander_patched, and run_pre_build_steps restores every ledger entry to its
fetched state before any patch or command runs. A file therefore always goes from pristine to
renamed, never from renamed to doubly renamed - and dropping this command from the registry
undoes the rename on the next generation.
"""

import re
import sys
from pathlib import Path

# Global-scope declarations that land in the compilation library by name.
DECL = re.compile(r"^\s*(?:package|module|interface)\s+(?:automatic\s+)?([a-zA-Z_][a-zA-Z_0-9]*)",
                  re.M)


def declared_names(tree: Path) -> set[str]:
    """Collect every package, module and interface name declared under a checkout."""
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
        sys.exit("usage: patch_spatz_snitch.py <bender_work>")
    bender_work = Path(sys.argv[1]).resolve()
    spatz = bender_work / "spatz"
    rival = bender_work / "snitch_cluster"
    if not spatz.is_dir():
        return  # spatz is not part of this SoC: nothing to repair.
    if not rival.is_dir():
        print("  -> patch_spatz_snitch: snitch_cluster is not in the checkout, rename skipped")
        return

    colliding = sorted(declared_names(spatz) & declared_names(rival))
    if not colliding:
        # Both trees are present and freshly restored, so an empty intersection means one of the
        # two IPs no longer declares what this script exists for - the collision is gone upstream.
        print("  [WARNING] patch_spatz_snitch: spatz and snitch_cluster no longer declare any"
              " common name; this pre-build command has no effect and should be revised.")
        return
    print(f"  -> patch_spatz_snitch: renaming to spatz_* the {len(colliding)} declarations"
          f" spatz shares with snitch_cluster")

    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in colliding) + r")\b")
    touched = []
    for f in list(spatz.rglob("*.sv")) + list(spatz.rglob("*.svh")):
        if ".git" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        renamed = pattern.sub(lambda m: f"spatz_{m.group(1)}", text)
        if renamed != text:
            f.write_text(renamed, encoding="utf-8")
            touched.append(str(f))
    print(f"  -> patch_spatz_snitch: {len(touched)} files renamed")

    # Record every edited file in the checkout's ledger, append-only, exactly as the declarative
    # patches do: the generator restores all ledger entries before the next run, which is what
    # makes this rename idempotent and removable.
    ledger = spatz / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | set(touched))) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Move spatz's vendored snitch-family IPs out of snitch_cluster's way inside a Bender checkout.

Invoked from the dependency registry as a pre-build command:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/patch_spatz_snitch.py {bender_work}"

spatz ships its own copies of the snitch core and of its companion interface IPs (hw/ip/snitch,
reqrsp_interface, tcdm_interface, mem_interface), unconditionally listed in its manifest, and
snitch_cluster ships the same IPs several revisions later. The two IPs never met before the super
examples put both families in one SoC, and no released revision of either side avoids the clash,
so the repair is a rename, exactly as for cva6's aes unit. It has to happen in TWO namespaces,
because the trees collide in two independent ways:

1. GLOBAL DECLARATIONS - packages, modules, interfaces and `define macros all land in one shared
   space (the compilation library for the first three, the preprocessor's macro table for the
   last), so the last one compiled wins and half the design elaborates against the wrong
   revision: first observed as "Failed to find the name 'amo_op_e' in scope 'snitch_pkg'" at
   elaboration, then again on mem_wide_narrow_mux, whose older copy lacks two ports.

2. PUBLISHED HEADER PATHS - both manifests export an include directory that publishes the very
   same relative subpaths ('reqrsp_interface/typedef.svh', 'tcdm_interface/assign.svh', ...).
   Include resolution walks the +incdir list and takes the FIRST root that satisfies the path,
   and that list is global to the whole design: snitch_cluster sorts before spatz, so spatz's own
   sources have always been compiled against snitch_cluster's headers - silently, long before
   anything failed. Renaming the declarations alone therefore breaks the build outright ("Define
   or directive not defined: '`spatz_REQRSP_TYPEDEF_ALL'"): spatz's call sites are renamed while
   the file that would define the renamed macros is never the file that gets read.

   Two cheaper repairs were measured against Verilator 5.050 and both are dead ends: making the
   include relative to the including file does not resolve at all (Verilator searches only the
   +incdir roots), and reordering the roots merely hands snitch_cluster's sources spatz's headers.
   What is left is to give spatz's headers a subpath no other IP publishes, and to repoint spatz's
   own include directives at it. The include ROOT is left untouched (only the namespace directory
   inside it is renamed), so the manifest keeps working as fetched and no incdir has to be added.

Renaming the include guards matters as much as renaming the macros, and is not an accident of the
blanket rename: in a single compilation unit snitch_cluster's copy has already defined the shared
guard, so a correctly resolved spatz header would otherwise be read and then discarded as inert.

The set of names to rename is DISCOVERED at every run, by intersecting what the two checkouts
declare and what they publish: a hardcoded list proved too narrow once (measuring only
hw/ip/snitch missed the interface IPs) and would silently rot when either side is updated. The
spatz side is the one renamed because it is self-contained: nothing outside the spatz checkout
references its vendored copies - spatz's own top ('spatz_cluster') is declared by spatz alone, so
it can never enter the intersection - while snitch_cluster's names are baked into the already
generated RTL of the mesh macros, down to the `include in components/tiles/cluster_subtile.sv.
When snitch_cluster is not part of the SoC the script does nothing, so the projects that
instantiate spatz alone compile the sources exactly as fetched.

Idempotency is delegated to the generator's ledger for everything the script EDITS: every such
file is recorded in the checkout's .ollivander_patched, and run_pre_build_steps restores every
ledger entry to its fetched state before any patch or command runs. A file therefore always goes
from pristine to renamed, never from renamed to doubly renamed - and dropping this command from
the registry undoes the rename on the next generation. The disambiguated namespaces are instead
PUBLISHED, not edited: the ledger restores content by path and cannot model a new directory, so
this script owns them and removes them at the start of every run. They are recognised rather than
remembered (a directory is ours if its original sibling is still next to it), which keeps the
cleanup working even when the command is later reconfigured. Dropping the command from the
registry does leave the last published copies behind, harmless because the restored include
directives no longer name them, until the next `make clean` re-fetches the checkout.
"""

import re
import shutil
import sys
from pathlib import Path

import yaml

# Global-scope declarations that land in the compilation library by name, and preprocessor macros,
# which share one table across the whole compilation unit. Both are matched at the start of a line
# so that a mention inside an expression or a comment cannot be taken for a declaration.
#
# The keyword list is the set of library-level design elements plus 'class', which is not one but
# is declared at $unit scope by both trees' testbenches: 'class translation_request' appears in the
# copy of snitch_l0_tlb_tb.sv that each of them ships, and a simulator with a single compilation
# unit rejects the second one ("Duplicate declaration of CLASS"). The optional qualifier absorbs
# the 'virtual class' and 'interface class' forms; a bare 'interface foo' still matches, the
# alternation backtracking to read 'interface' as the keyword it is.
DECL = re.compile(r"^\s*(?:(?:virtual|interface)\s+)?"
                  r"(?:package|module|interface|class|program|checker|primitive)\s+"
                  r"(?:automatic\s+)?([a-zA-Z_][a-zA-Z_0-9]*)", re.M)
MACRO = re.compile(r"^\s*`define\s+([a-zA-Z_][a-zA-Z_0-9]*)", re.M)

# Prefix applied to every renamed name and to every republished namespace directory. It doubles as
# the marker that lets a later run recognise what an earlier one published.
PREFIX = "spatz_"


def sv_files(tree: Path):
    """Every SystemVerilog source and header of a checkout, excluding its git metadata."""
    for f in list(tree.rglob("*.sv")) + list(tree.rglob("*.svh")):
        if ".git" not in f.parts:
            yield f


def declared_names(tree: Path) -> set[str]:
    """Collect every package, module, interface and macro name declared under a checkout."""
    names = set()
    for f in sv_files(tree):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        names |= set(DECL.findall(text)) | set(MACRO.findall(text))
    return names


def include_roots(tree: Path) -> list[Path]:
    """The include directories a checkout publishes to the rest of the design.

    Read from the manifest rather than guessed from directory names: 'export_include_dirs' is
    exactly what Bender turns into the +incdir list, so it is the only definition of what the IP
    publishes - and what another IP can therefore collide with.
    """
    manifest = tree / "Bender.yml"
    if not manifest.is_file():
        return []
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    return [tree / d for d in (data.get("export_include_dirs") or []) if (tree / d).is_dir()]


def published_namespaces(tree: Path) -> dict[str, list[Path]]:
    """Map each published header namespace to the directories implementing it.

    The namespace is the first component of the path an include directive names, i.e. the
    directory sitting immediately inside an exported include root: it is that component, not the
    header's file name, that decides which of two identically shaped trees answers an include.
    """
    out: dict[str, list[Path]] = {}
    for root in include_roots(tree):
        for child in sorted(root.iterdir()):
            if child.is_dir():
                out.setdefault(child.name, []).append(child)
    return out


def derived_dirs(tree: Path) -> list[Path]:
    """The namespace directories a previous run of this script published.

    Recognised, not remembered: a directory is ours if it is named '<PREFIX><X>' and its original
    sibling '<X>' is still next to it. That keeps the cleanup independent of any state file, which
    matters because these directories are untracked and the generator's ledger cannot restore them.
    """
    out = []
    for root in include_roots(tree):
        for child in root.iterdir():
            if (child.is_dir() and child.name.startswith(PREFIX)
                    and (root / child.name[len(PREFIX):]).is_dir()):
                out.append(child)
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: patch_spatz_snitch.py <bender_work>")
    bender_work = Path(sys.argv[1]).resolve()
    spatz = bender_work / "spatz"
    rival = bender_work / "snitch_cluster"
    if not spatz.is_dir():
        return  # spatz is not part of this SoC: nothing to repair.

    # Removed before anything else and whatever happens next, exactly like the ledger restore this
    # mirrors: a copy left over from a previous configuration would keep answering includes that
    # the restored sources no longer issue.
    for d in derived_dirs(spatz):
        shutil.rmtree(d)

    if not rival.is_dir():
        print("  -> patch_spatz_snitch: snitch_cluster is not in the checkout, rename skipped")
        return

    colliding = sorted(declared_names(spatz) & declared_names(rival))
    spatz_ns = published_namespaces(spatz)
    ns_colliding = sorted(set(spatz_ns) & set(published_namespaces(rival)))
    if not colliding:
        # Both trees are present and freshly restored, so an empty intersection means one of the
        # two IPs no longer declares what this script exists for - the collision is gone upstream.
        print("  [WARNING] patch_spatz_snitch: spatz and snitch_cluster no longer declare any"
              " common name; this pre-build command has no effect and should be revised.")
        return
    print(f"  -> patch_spatz_snitch: renaming to spatz_* the {len(colliding)} declarations and the"
          f" {len(ns_colliding)} header namespaces spatz shares with snitch_cluster")

    name_pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in colliding) + r")\b")
    # Only the namespace component is rewritten, and only where it is the target of an include:
    # the same word elsewhere in the source is an ordinary identifier, covered - or deliberately
    # not covered - by the rename above.
    inc_pat = re.compile(r"(`include\s*\")(" + "|".join(re.escape(n) for n in ns_colliding)
                         + r")/") if ns_colliding else None

    touched = []
    for f in sv_files(spatz):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        renamed = text
        if inc_pat:
            renamed = inc_pat.sub(lambda m: f"{m.group(1)}{PREFIX}{m.group(2)}/", renamed)
        # Applied after the include rewrite, and harmless in either order: '\b' cannot match
        # inside the 'spatz_<name>' the rewrite has just produced, since '_' is a word character.
        renamed = name_pat.sub(lambda m: f"{PREFIX}{m.group(1)}", renamed)
        if renamed != text:
            f.write_text(renamed, encoding="utf-8")
            touched.append(str(f))
    print(f"  -> patch_spatz_snitch: {len(touched)} files renamed")

    # Published only now, so the copies carry the renamed declarations and the rewritten include
    # directives: they are what the design actually reads, the originals having become unreachable
    # (their subpath is answered by snitch_cluster's root, which comes first in the +incdir list).
    for ns in ns_colliding:
        for d in spatz_ns[ns]:
            shutil.copytree(d, d.parent / f"{PREFIX}{ns}")
    print(f"  -> patch_spatz_snitch: {len(ns_colliding)} header namespaces republished as"
          f" {PREFIX}*")

    # Record every edited file in the checkout's ledger, append-only, exactly as the declarative
    # patches do: the generator restores all ledger entries before the next run, which is what
    # makes this rename idempotent and removable. The republished directories are not listed -
    # they are untracked, and this script removes them itself at the start of every run.
    ledger = spatz / ".ollivander_patched"
    ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
        if ledger.is_file() else set()
    ledger.write_text("\n".join(sorted(ever | set(touched))) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

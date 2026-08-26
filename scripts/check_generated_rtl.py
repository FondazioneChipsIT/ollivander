#!/usr/bin/env python3
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
"""
Elaborate what Ollivander wrote and report only what Ollivander owns.

    scripts/check_generated_rtl.py <project_dir> [<project_dir> ...]

Ollivander already uses pyslang to READ the external IPs' headers; this closes
the loop by re-reading what it WRITES. The defect class it exists for is the one
no other flow can see: `vlog` does not check port existence across a module
boundary, and nothing in any flow elaborates the chip wrapper - so a wrapper
connecting fourteen ports that the padframe never declared compiled clean,
simulated clean, and was only found by an external tool.

Reported set: files under the project's generated output and under the component
directories, INCLUDING any a project adds through `paths.components` in its own
`*_env.yml`. Vendor sources are parsed - the packages are needed to elaborate
anything - but never reported, or the check drowns in third-party noise. Note the
components a user writes for their own project are the least reviewed
SystemVerilog in a tree: a hardcoded pair of paths would under-cover exactly
them.

Two traps, both paid for once:

  * `Driver.reportCompilation()` REPORTS NOTHING. Measured: on a file that
    getAllDiagnostics() rejects with four errors it prints nothing and returns
    None. A gate built on it is a no-op that reads as a pass, which is why this
    script self-tests against a known-invalid input before trusting itself
    (--self-test, run automatically unless --no-self-test is given).
  * Without `--timescale`, which `vlog` receives, roughly 130 spurious
    "design element does not have a time scale defined" errors bury the real ones.

Exit status: 0 when clean, 1 on elaboration errors in the reported set, 2 when
the check itself could not run (no flist, no pyslang, self-test failed).
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

try:
    import pyslang
    from pyslang.driver import Driver
except ImportError:
    print("[ERROR] pyslang is missing. It ships in requirements.txt: "
          "activate the project's .venv, or run 'make setup'.", file=sys.stderr)
    sys.exit(2)

# A module whose localparam is a nested assignment pattern under 'default:' -
# accepted by QuestaSim and Verilator, rejected by a strict front-end. Used to
# prove the checker actually reports.
SELF_TEST_INVALID = """
package olli_selftest_pkg;
  typedef struct {
    int unsigned Regs [2][3];
  } cfg_t;
endpackage
module olli_selftest #(parameter int N = 2) ();
  localparam olli_selftest_pkg::cfg_t C [N] = '{default: '{Regs: '{'{1,2,3},'{4,5,6}}}};
endmodule
"""


def elaborate(argv):
    """Elaborate a slang command line and return (diagnostics, sourceManager, engine)."""
    driver = Driver()
    driver.addStandardArgs()
    if not driver.parseCommandLine(" ".join(argv)):
        return None, None, None
    if not driver.processOptions():
        return None, None, None
    driver.parseAllSources()
    comp = driver.createCompilation()
    # NOT driver.reportCompilation(): see the module docstring.
    return list(comp.getAllDiagnostics()), comp.sourceManager, pyslang.DiagnosticEngine(comp.sourceManager)


def errors_only(diags, engine):
    return [d for d in diags
            if engine.getSeverity(d.code, d.location) == pyslang.DiagnosticSeverity.Error]


def self_test():
    """Refuse to run if the checker cannot flag a file that is known to be invalid."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "olli_selftest.sv"
        bad.write_text(SELF_TEST_INVALID)
        diags, _, engine = elaborate(["slang", "--single-unit", "--timescale=1ns/1ps", str(bad)])
        if diags is None or not errors_only(diags, engine):
            print("[ERROR] Self-test failed: the checker reported nothing on a file that is "
                  "known to be invalid, so a clean result from it would mean nothing.",
                  file=sys.stderr)
            return False
    return True


def flist_from_tcl(tcl_path):
    """Files, include paths and defines, taken from the flist the fast-check builds."""
    text = tcl_path.read_text(encoding="utf-8", errors="replace")
    root_match = re.search(r'set ROOT "([^"]+)"', text)
    root = root_match.group(1) if root_match else str(tcl_path.parents[3])
    files, incdirs, defines, seen = [], [], [], set()
    for line in text.splitlines():
        if "vlog " not in line:
            continue
        line = line.replace("$ROOT", root)
        for m in re.finditer(r"\+incdir\+([^\s\"]+)", line):
            if m.group(1) not in incdirs:
                incdirs.append(m.group(1))
        for m in re.finditer(r"\+define\+([^\s\"+]+)", line):
            if m.group(1) not in defines:
                defines.append(m.group(1))
        for m in re.finditer(r"\"([^\"]+\.s?v)\"", line):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                files.append(m.group(1))
    return files, incdirs, defines


def reported_roots(project_dir):
    """Directories whose diagnostics are ours: the output, plus every component path.

    Derived rather than hardcoded, so a project that declares extra component
    directories in its own environment YAML is covered the day it declares them.
    """
    roots = [(project_dir / "generated").resolve()]
    repo = Path(__file__).resolve().parents[1]
    roots.append((repo / "components").resolve())
    for env_yml in sorted(project_dir.glob("*_env.yml")):
        try:
            import yaml
            data = yaml.safe_load(env_yml.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        paths_cfg = (data.get("paths") or {})
        declared = paths_cfg.get("components", paths_cfg.get("components_dir")) or []
        if isinstance(declared, str):
            declared = [declared]
        for entry in declared:
            candidate = (env_yml.parent / entry).resolve()
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
    return roots


def check_project(project_dir):
    tcl = project_dir / "generated" / "sim" / "questa" / "compile_vsim_fast.tcl"
    if not tcl.is_file():
        print(f"[SKIP] {project_dir.name}: no flist yet. Run 'make fast-check' first "
              f"(it is what writes {tcl.relative_to(project_dir)}).")
        return 2

    files, incdirs, defines = flist_from_tcl(tcl)
    argv = (["slang", "--single-unit", "--ignore-unknown-modules", "--timescale=1ns/1ps"]
            + [f"-I{d}" for d in incdirs] + [f"-D{d}=1" for d in defines] + files)
    diags, sm, engine = elaborate(argv)
    if diags is None:
        print(f"[ERROR] {project_dir.name}: slang refused the command line built from "
              f"{tcl.name}.", file=sys.stderr)
        return 2

    roots = reported_roots(project_dir)
    ours = []
    for diag in errors_only(diags, engine):
        path = Path(sm.getFileName(diag.location)).resolve()
        if any(str(path).startswith(str(root)) for root in roots):
            ours.append((path, sm.getLineNumber(diag.location), engine.formatMessage(diag)))

    if not ours:
        print(f"[OK] {project_dir.name}: {len(files)} files elaborated, no errors in what we own.")
        return 0
    print(f"[FAIL] {project_dir.name}: {len(ours)} error(s) in files we own:")
    for path, line, message in ours:
        print(f"    {path}:{line}  {message}")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("projects", nargs="+", type=Path, help="project directories")
    parser.add_argument("--no-self-test", action="store_true",
                        help="skip the self-test (not advisable: see the module docstring)")
    args = parser.parse_args()

    if not args.no_self_test and not self_test():
        return 2

    worst = 0
    for project in args.projects:
        worst = max(worst, check_project(project.resolve()))
    return worst


if __name__ == "__main__":
    sys.exit(main())

# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
Elaborate what Ollivander wrote, and report only what Ollivander owns.

Ollivander already uses pyslang to READ the external IPs' headers; this closes
the loop by re-reading what it WRITES. The defect class it exists for is the one
no other flow can see: `vlog` does not check port existence across a module
boundary, and nothing in any flow elaborates the chip wrapper - so a wrapper that
connected fourteen ports the padframe never declared compiled clean, simulated
clean, and was found only by an external tool.

Used from two places, deliberately sharing one implementation so the two traps
below are paid for once:

*   at the END OF GENERATION (`ollivander.py`, phase 11), where the vendor
    modules are black-boxed because the stubs do not exist yet. This checks the
    self-consistency of everything we wrote, and it is the fastest feedback a
    user gets since `make generate` is their inner loop.
*   at FAST-CHECK, where the stubs carry exact IP signatures, so the same
    elaboration additionally verifies our wrappers AGAINST those signatures -
    the only place that boundary is checked - and the stubs themselves.

Two traps, both measured rather than guessed:

*   `Driver.reportCompilation()` REPORTS NOTHING: on a file that
    getAllDiagnostics() rejects with four errors it prints nothing and returns
    None. A gate built on it is a no-op that reads as a pass, which is why
    `self_test()` exists and why callers should run it.
*   Without `--timescale`, which `vlog` receives, roughly 130 spurious "design
    element does not have a time scale defined" errors bury the real ones.
"""

import re
import subprocess
from pathlib import Path

try:
    import pyslang
    from pyslang.driver import Driver
    HAS_PYSLANG = True
except ImportError:
    HAS_PYSLANG = False

# A localparam whose value is a nested assignment pattern under 'default:' -
# accepted by QuestaSim and Verilator, rejected by a strict front-end. Used to
# prove the checker actually reports before its clean verdict is believed.
_SELF_TEST_INVALID = """
package olli_selftest_pkg;
  typedef struct { int unsigned Regs [2][3]; } cfg_t;
endpackage
module olli_selftest #(parameter int N = 2) ();
  localparam olli_selftest_pkg::cfg_t C [N] = '{default: '{Regs: '{'{1,2,3},'{4,5,6}}}};
endmodule
"""

# THE ERROR LIMIT IS LIFTED DELIBERATELY, and this is the difference between a check that
# guards and one that reports success. slang stops after its default number of errors, and on
# a full flist that budget is spent entirely by VENDOR sources before our own files are even
# reached: measured on noc, 86 errors, every one of them in axi_demux, cv32e40p_tracer, the
# *_reg_top blocks and floo_nw_chimney. Those are filtered out of the report by ownership -
# correctly, they are not ours to fix - but filtering happens AFTER the limit has been
# consumed, so a genuine error in what we generate is never emitted at all: measured on a
# full flist, the default budget was spent entirely on vendor diagnostics (86 errors, none
# ours) while lifting it exposed a real declaration-order defect in a generated tile. An explicit large number rather than 0: slang documents 0 as
# "no limit", and a version reading it as "print none" would silently disable the check.
# --allow-genblk-reference: the generated testbench preloads interleaved memories through
# paths that cross an UNNAMED generate block inside the IP
# ('i_dyn_mem_bank_group.genblk1[0].i_ecc_sram_wrap.i_bank.sram'). 'genblk1' is the implicit
# name the LRM gives such a block; QuestaSim and Verilator both resolve it, and the whole
# fleet boots through those paths - so refusing it would reject a construct that demonstrably
# works, not find a defect. Surfaced on crossbar_isle the moment the error limit was lifted.
_BASE_ARGS = ["slang", "--single-unit", "--ignore-unknown-modules", "--timescale=1ns/1ps",
              "--error-limit=100000", "--allow-genblk-reference"]


def _elaborate(argv):
    """Returns (diagnostics, sourceManager, engine), or (None, None, None) on refusal."""
    driver = Driver()
    driver.addStandardArgs()
    if not driver.parseCommandLine(" ".join(argv)):
        return None, None, None
    if not driver.processOptions():
        return None, None, None
    driver.parseAllSources()
    comp = driver.createCompilation()
    # NOT driver.reportCompilation(): see the module docstring.
    return (list(comp.getAllDiagnostics()), comp.sourceManager,
            pyslang.DiagnosticEngine(comp.sourceManager))


def _errors(diags, engine):
    return [d for d in diags
            if engine.getSeverity(d.code, d.location) == pyslang.DiagnosticSeverity.Error]


def self_test():
    """False when the checker cannot flag an input that is known to be invalid."""
    if not HAS_PYSLANG:
        return False
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "olli_selftest.sv"
        bad.write_text(_SELF_TEST_INVALID)
        diags, _, engine = _elaborate(["slang", "--single-unit", "--timescale=1ns/1ps", str(bad)])
        return bool(diags) and bool(_errors(diags, engine))


def bender_flist(project_dir: Path, targets, bender_exe="bender"):
    """Source files and include paths from `bender script flist-plus`, or None.

    The flist is NOT available at the end of generation - `compile_vsim.tcl` is
    written by prep-sim - so the check builds its own. The targets come from the
    generated sim.mk, which is the single place that decides them.
    """
    try:
        result = subprocess.run([bender_exe, "script", "flist-plus"] + list(targets),
                                cwd=project_dir, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    if result.returncode != 0:
        return None, None, None

    files, incdirs, defines = [], [], []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("+incdir+"):
            incdirs.append(line[len("+incdir+"):])
        elif line.startswith("+define+"):
            defines.append(line[len("+define+"):].split("=")[0])
        elif not line.startswith("+"):
            # SystemVerilog only. flist-plus also lists the VHDL sources (the CAN
            # controller), and feeding those to a SystemVerilog parser does not
            # fail on them - it fails on the NEXT file, because --single-unit makes
            # one unterminated construct poison everything after it. The symptom
            # is nonsense like "member not allowed in interface declaration" on one
            # of our own packages, which is how this was found.
            if Path(line).suffix in (".sv", ".v", ".svh", ".vh"):
                files.append(line)
    return files, incdirs, defines


def targets_from_sim_mk(sim_mk: Path):
    """The -t flags the generated sim.mk declares for Bender, or []."""
    if not sim_mk.is_file():
        return []
    match = re.search(r"^BENDER_TARGETS\s*\?=\s*(.+)$", sim_mk.read_text(encoding="utf-8"),
                      re.MULTILINE)
    return match.group(1).split() if match else []


def flist_from_tcl(tcl_path: Path):
    """Files, include paths and defines out of a generated compile TCL."""
    text = tcl_path.read_text(encoding="utf-8", errors="replace")
    root = re.search(r'set ROOT "([^"]+)"', text)
    root = root.group(1) if root else str(tcl_path.parents[3])
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


def check(files, incdirs, defines, reported_roots, excluded_roots=()):
    """Elaborate, and return the errors that fall inside reported_roots.

    Vendor sources are PARSED - their packages are needed to elaborate anything -
    but never REPORTED, or the check drowns in third-party noise. Returns
    (ok, findings) where findings is [(path, line, message)]; ok is False only
    when the elaboration itself could not run.

    excluded_roots carves directories back out of the reported set. The stubbed
    pass needs it for the generated testbench: the bench reaches into the IPs with
    dotted paths to preload their memories, and a dotted path cannot cross a
    blackbox, so every one of those references is unresolvable against stubs. It
    is not a defect and never was - the same bench elaborates clean at generation,
    where the real IPs are present and the paths resolve.
    """
    diags, sm, engine = _elaborate(
        _BASE_ARGS + [f"-I{d}" for d in incdirs] + [f"-D{d}=1" for d in defines] + list(files))
    if diags is None:
        return False, []

    roots = [str(Path(r).resolve()) for r in reported_roots]
    excluded = [str(Path(r).resolve()) for r in excluded_roots]
    findings = []
    for diag in _errors(diags, engine):
        path = Path(sm.getFileName(diag.location)).resolve()
        if any(str(path).startswith(root) for root in excluded):
            continue
        if any(str(path).startswith(root) for root in roots):
            findings.append((path, sm.getLineNumber(diag.location), engine.formatMessage(diag)))
    return True, findings


def reported_roots(outdir_path: Path, component_paths):
    """What counts as ours: the generated output plus every component directory.

    DERIVED, not hardcoded: `paths.components` is a list a project extends in its
    own environment YAML, so a user-added component directory is covered the day
    it is declared. Those components are also the least-reviewed SystemVerilog in
    any tree - nobody reviewed them, they have no upstream, and no example
    exercises them - which is exactly where a hardcoded pair of paths would have
    under-covered.
    """
    return [outdir_path] + list(component_paths)

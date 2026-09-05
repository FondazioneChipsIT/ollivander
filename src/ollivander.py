#!/usr/bin/env python3
# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
Ollivander SoC Generator - Main Entry Point

This is the core orchestrator of the Ollivander generation flow. It parses
the SoC configuration, resolves dependencies, validates hardware constraints,
renders the SystemVerilog Top-Level and infrastructure via Mako, fetches 
external IPs via Bender, and invokes external tools (PeakRDL, FlooGen, Verible)
to complete the SoC generation.
"""

import argparse
import sys
import re
import shutil
import subprocess
import textwrap
import importlib.util
from pathlib import Path
import yaml
from pydantic import ValidationError
from mako.lookup import TemplateLookup

from core.soc_schema import OllivanderConfig, validate_soc_components, validate_cross_references, validate_untyped_blocks, normalize_address_ranges, Component
from core.stub_generator import generate_stubs
from core.env_manager import setup_environment, load_env_yaml
from core.arch_optimizer import optimize_clock_tree, autoconfigure_host, warn_boot_memory_gated, check_boot_memory_executable
from core.tool_runners import run_floogen, run_peakrdl, run_verible, run_pre_build_steps, run_padrick
from core import rtl_checker
from core.reporter import print_generation_report
from core.rtl_generator import RTLGenerator
from core.ipxact_generator import generate_ipxact
from core.noc_placement_checker import run_noc_placement_check, write_noc_placement_report

def run_generated_rtl_check(env, outdir_path, use_stubs=False):
    """Phase 11: elaborate the generated RTL and report only what we own.

    Policy from the environment (`generated_rtl_check`): 'strict' stops the
    generation, 'warn' reports and carries on, 'off' skips. Strict is the default
    because a check that does not stop is a check whose green result means
    nothing; 'warn' exists for a project whose OWN components carry a construct
    its simulator accepts and a strict front-end refuses - we are entitled to
    impose our tooling's severity on our output, not on someone else's code.

    Degrades loudly, never silently: a missing pyslang, a Bender that cannot
    produce a file list, or a checker that fails its own self-test all report why
    and leave the generation alone rather than passing quietly.
    """
    policy = getattr(env, "generated_rtl_check", "strict")
    if policy == "off":
        return

    print("=" * 70)
    print(f"[*] {'Self-Elaborating the stubbed design' if use_stubs else 'Starting Phase 11: Self-Elaborating the Generated RTL'}...\n")

    if not rtl_checker.HAS_PYSLANG:
        print("  [WARNING] pyslang is not available: skipping. It ships in "
              "requirements.txt - run 'make setup' to restore the venv.")
        print("=" * 70)
        return
    if not rtl_checker.self_test():
        print("  [WARNING] The checker did not flag a known-invalid input, so a clean "
              "result from it would mean nothing. Skipping rather than reassuring.")
        print("=" * 70)
        return

    if use_stubs:
        tcl = outdir_path / "sim" / "questa" / "compile_vsim_fast.tcl"
        if not tcl.is_file():
            print(f"  [WARNING] {tcl.name} was not written: skipping.")
            print("=" * 70)
            return
        files, incdirs, defines = rtl_checker.flist_from_tcl(tcl)
    else:
        targets = rtl_checker.targets_from_sim_mk(outdir_path / "sim" / "sim.mk")
        files, incdirs, defines = rtl_checker.bender_flist(env.bender_dir, targets)
    if not files:
        print("  [WARNING] Could not obtain a file list: skipping. The check needs "
              "one, and building it by hand would only guess.")
        print("=" * 70)
        return

    # In the stubbed pass the generated testbench is out of scope: it preloads the
    # IPs' memories through dotted paths, which cannot cross a blackbox, so every
    # such reference is unresolvable against stubs and none of them is a defect.
    # The same bench IS checked at generation, against the real IPs.
    excluded = [outdir_path / "tb"] if use_stubs else []
    ok, findings = rtl_checker.check(
        files, incdirs, defines,
        rtl_checker.reported_roots(outdir_path, env.component_paths), excluded)
    if not ok:
        print("  [WARNING] The elaboration could not run: skipping.")
        print("=" * 70)
        return

    if not findings:
        what = "in the stubs or what we generate" if use_stubs else "in what we generate"
        print(f"  [SUCCESS] {len(files)} files elaborated, no errors {what}.")
        print("=" * 70)
        return

    label = "ERROR" if policy == "strict" else "WARNING"
    print(f"  [{label}] {len(findings)} error(s) in RTL we generate:")
    for path, line, message in findings:
        print(f"    {path}:{line}")
        print(f"      {message}")
    if policy == "strict":
        print("\n  These are errors in what Ollivander just wrote. Set "
              "'generated_rtl_check: warn' in the environment YAML to report them "
              "without stopping.")
        print("=" * 70)
        sys.exit(1)
    print("=" * 70)


def check_floogen_matches_rtl(env, soc_config):
    """Warn when the resolved FlooNoC revision is not the one FlooGen was validated with.

    FlooGen EMITS code that instantiates FlooNoC's modules, so the two have to
    match; the registry records which generator a revision was validated against
    (`validated_with`), and the resolved revision is read from Bender.lock, which
    carries it in both regimes - a semver-resolved entry and one forced by
    `overrides`. Version STRINGS are unusable for this: a forced revision makes the
    lock record 'version: null', FlooNoC's own manifest declares no version, and the
    checkout carries a synthetic 'bender-tmp-<hash>' tag.

    Only for topologies where Ollivander actually runs FlooGen. NOT for every
    project that merely links floo_noc: on a nested macro the check would compare
    two things that are trivially equal - one venv, one catalogue - while the thing
    that could differ, the macro's package emitted in another run, is outside its
    reach. Coherence is a property of the generation event that emitted the package.

    A warning, not an error: our own pin makes a mismatch nearly impossible, so the
    case this exists for is a project overriding floo_noc in its own environment -
    a legitimate choice that deserves to be informed, not refused.
    """
    if soc_config.topology.type != "noc":
        return

    entry = (env.registry_dependencies or {}).get("floo_noc") or {}
    expected = ((entry.get("validated_with") or {}).get("floogen") or "").strip()
    pinned = (entry.get("rev") or "").strip()

    try:
        from importlib.metadata import version as pkg_version
        installed = pkg_version("floogen")
    except Exception:
        installed = None

    lock = env.bender_dir / "Bender.lock" if env.bender_dir else None
    resolved = None
    if lock and lock.is_file():
        # The lock is a flat YAML mapping; read the revision under floo_noc only.
        in_entry = False
        for line in lock.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\s{2}floo_noc:\s*$", line):
                in_entry = True
                continue
            if in_entry:
                m = re.match(r"^\s+revision:\s*([0-9a-f]{7,40})", line)
                if m:
                    resolved = m.group(1)
                    break
                if re.match(r"^\s{2}\S", line):     # next package
                    break

    # Two independent ways the pair can drift, and each names the file to fix.
    if resolved and pinned and resolved != pinned:
        print(f"\n  [WARNING] floo_noc resolved to {resolved[:12]}, not the {pinned[:12]} "
              f"this catalogue records as validated (with FlooGen {expected or '?'}).")
        print(f"            A project override can do this legitimately - but then pin a "
              f"FlooGen that matches it, or the emitted package and the instantiated "
              f"RTL can disagree.")

    if installed and expected and installed != expected:
        print(f"\n  [WARNING] FlooGen {installed} is installed while the catalogue records "
              f"floo_noc {pinned[:12] or '?'} as validated with FlooGen {expected}.")
        print(f"            Bumping one of the two without the other is how they drifted "
              f"apart before: update 'validated_with' in ollivander_config.yml, or "
              f"requirements.txt, so they move together.")


def main():
    # =========================================================================
    # 1. ARGUMENT PARSING
    # =========================================================================
    # Setup the command-line interface for the generator.
    parser = argparse.ArgumentParser(description="Ollivander SoC Generator")
    parser.add_argument(
        "-c", "--config", 
        type=str, 
        required=True, 
        help="Path to the SoC configuration file (.yaml, .yml, .py)."
    )
    parser.add_argument(
        "-o", "--outdir", 
        type=str, 
        default=None, 
        help="Output directory for generated files (default: './generated')."
    )
    parser.add_argument(
        "-e", "--env-config", 
        type=str, 
        default=None, 
        help="Path to a custom Ollivander environment config YAML to replace the default one."
    )
    parser.add_argument(
        "-b", "--bender", 
        type=str, 
        default=None, 
        help="Path for the generated Bender.yml manifest (overrides config)."
    )
    parser.add_argument(
        "-a", "--append-env", 
        type=str, 
        default=None, 
        help="Path to an additional environment config YAML to merge with the base configuration."
    )
    parser.add_argument(
        "--generate-stubs",
        action="store_true",
        help="Generate faithful RTL stubs for fast-check and exit."
    )
    parser.add_argument(
        "--check-rtl",
        choices=["design", "stubs"],
        default=None,
        help="Re-run phase 11 over an ALREADY generated tree and exit, without "
             "regenerating anything: 'design' elaborates the whole design (the real "
             "IPs), 'stubs' elaborates the fast-check list and so checks stub "
             "fidelity. Useful while working through a list of findings."
    )
    parser.add_argument(
        "--test-app",
        type=str,
        default=None,
        help="Override software_stack.test_app.name from the command line (e.g. run a plain "
             "'hello_world' on a project whose description selects the 'offload' test)."
    )
    parser.add_argument(
        "--offload-targets",
        type=str,
        default=None,
        help="Comma- or space-separated component names restricting the 'offload' test to a "
             "subset of the offload-capable components (default: all of them)."
    )

    args = parser.parse_args()
    config_path = Path(args.config)
    
    from core.utils import get_ollivander_version, get_generation_comment, yaml_load_strict
    print(f"Ollivander SoC Generator v{get_ollivander_version()}\n")
    
    # Ensure the provided SoC specification file exists.
    if not config_path.is_file():
        print(f"[ERROR] Configuration file not found: {config_path}")
        sys.exit(1)
        
    # The base directory of the Ollivander generator itself.
    base_dir = Path(__file__).parent.parent.resolve()
        
    # =========================================================================
    # 2. ENVIRONMENT SETUP & PATH RESOLUTION
    # =========================================================================
    # This section resolves where to find Mako templates, SystemVerilog component
    # sources, and where to place the generated output files. It follows a
    # clear precedence order for flexibility.
    
    env = setup_environment(args, base_dir)
    env.config_file_path = config_path.resolve()
    env.outdir_path.mkdir(parents=True, exist_ok=True)

    # Report-only entry point, and it has to come BEFORE the cleanup below: it
    # re-elaborates the tree as it stands, so wiping that tree first would leave
    # it with nothing to read - and destroy the very output the user asked about.
    if args.check_rtl:
        run_generated_rtl_check(env, env.outdir_path, use_stubs=(args.check_rtl == "stubs"))
        sys.exit(0)

    # Clean output directory to avoid stale generated files from previous runs
    if not args.generate_stubs:
        import shutil
        for child in env.outdir_path.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except Exception as e:
                print(f"[WARNING] Could not clean stale generated item '{child.name}': {e}")
    bender_work = env.bender_dir / "bender_work"
    bender_work.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # 3. CONFIGURATION PARSING & VALIDATION
    # =========================================================================
    try:
        if config_path.suffix == '.py':
            spec = importlib.util.spec_from_file_location("soc_config_module", config_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if not hasattr(module, 'config'):
                print(f"[ERROR] The file {config_path.name} must define a global variable named 'config'.")
                sys.exit(1)
                
            raw_config = module.config
            if isinstance(raw_config, OllivanderConfig):
                config_data = raw_config.model_dump(by_alias=True)
            elif isinstance(raw_config, dict):
                config_data = raw_config
            else:
                print("[ERROR] The 'config' variable must be a dictionary or an OllivanderConfig instance.")
                sys.exit(1)
        elif config_path.suffix in ['.yaml', '.yml']:
            with open(config_path, "r", encoding="utf-8") as f:
                # Strict loader: duplicate keys in a SoC description are refused
                # rather than silently collapsed to the last value (core/utils.py).
                config_data = yaml_load_strict(f)
        else:
            print(f"[ERROR] Unsupported configuration file extension: {config_path.suffix}. Use .yaml, .yml, or .py")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load configuration file:\n{e}")
        sys.exit(1)
        
    # Command-line overrides of the software stack, applied on the raw configuration
    # BEFORE the Pydantic validation so that every downstream consumer (validators,
    # generator, templates) sees a single source of truth. Same precedence philosophy
    # as -b / -o: the command line wins over the description file.
    if args.test_app or args.offload_targets:
        sw_stack = config_data.setdefault("software_stack", {})
        test_app = sw_stack.setdefault("test_app", {})
        if args.test_app:
            test_app["name"] = args.test_app
            print(f"[INFO] test_app.name overridden from the command line: '{args.test_app}'")
        if args.offload_targets:
            targets = [t for t in re.split(r"[,\s]+", args.offload_targets.strip()) if t]
            test_app["offload_targets"] = targets
            print(f"[INFO] test_app.offload_targets overridden from the command line: {targets}")

    print(f"[*] Validating SoC configuration: {config_path.name}...")
    try:
        soc_config = OllivanderConfig(**config_data)
    except ValidationError as e:
        print("\n[ERROR] SoC Configuration Validation Failed!")
        print("=" * 70)
        for err in e.errors():
            loc = " -> ".join([str(x) for x in err['loc']])
            msg = err['msg']
            print(f"Location : {loc}\nError    : {msg}\n" + "-" * 70)
        sys.exit(1)
        
    print("\n[SUCCESS] Basic Configuration validated successfully!")

    # =========================================================================
    # AUTO-INJECT PADFRAME REGBUS COMPONENT
    # =========================================================================
    if soc_config.padframe:
        if soc_config.components is None:
            soc_config.components = []
        # Inject only if the user hasn't already defined it manually
        if not any(c.name == "padframe_config" for c in soc_config.components):
            padframe_cfg_comp = Component(
                name="padframe_config",
                description="Auto-generated Padframe configuration registers",
                type="padframe_cfg",
                interfaces={
                    "regbus_slave": [{
                        "external": True,
                        "base_addr": soc_config.padframe.base_addr,
                        "size": soc_config.padframe.size,
                        "sync_domain": soc_config.padframe.sync_domain
                    }]
                }
            )
            soc_config.components.append(padframe_cfg_comp)

    if args.generate_stubs:
        print("\n[*] Starting Fast-Check Stub Generation...")
        generate_stubs(env.outdir_path, soc_config, env.registry_dependencies, base_dir, env.fast_check_tool)
        print("  [SUCCESS] Faithful stubs and fast-compile scripts generated.")
        # The same check as phase 11, over the list that has just been written -
        # so it sees the STUBS. That is all this second pass adds: whether a stub
        # faithfully represents the IP it replaces. The boundary against the real
        # IPs is already covered at generation, where bender_work is populated and
        # the true modules elaborate. Cheap (a tenth of the design), and it is how
        # the malformed tc_pad stub was caught.
        run_generated_rtl_check(env, env.outdir_path, use_stubs=True)
        sys.exit(0)

    registry_dependencies = env.registry_dependencies
    outdir_path = env.outdir_path
    hw_sub = env.hw_sub
    sw_sub = env.sw_sub
    doc_sub = env.doc_sub
    cfg_sub = env.cfg_sub
    reg_sub = env.reg_sub
    tb_sub = env.tb_sub
    bender_manifest_path = env.bender_manifest_path
    bender_dir = env.bender_dir
    template_paths = env.template_paths
    component_paths = env.component_paths
    search_paths = env.search_paths
    exclude_dir = env.exclude_dir

    # Mako template engine setup.
    template_lookup = TemplateLookup(directories=[str(p) for p in template_paths])

    # =========================================================================
    # 4. ARCHITECTURAL OPTIMIZATION (GARBAGE COLLECTION)
    # =========================================================================
    # This pass removes unused clock domains from the configuration to optimize
    # Power, Performance, and Area (PPA) of the final design.
    optimize_clock_tree(soc_config)

    # Create all necessary output directories.
    outdir_path.mkdir(parents=True, exist_ok=True)
    hw_dir = outdir_path / hw_sub
    sw_dir = outdir_path / sw_sub
    doc_dir = outdir_path / doc_sub
    cfg_dir = outdir_path / cfg_sub
    reg_dir = outdir_path / reg_sub
    tb_dir = outdir_path / tb_sub
    for d in [hw_dir, sw_dir, doc_dir, cfg_dir, reg_dir, tb_dir, bender_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    print(f"[*] Using templates from: {[p.name for p in template_paths]}")

    # =========================================================================
    # 5. HOST AUTO-CONFIGURATION
    # =========================================================================
    # This critical step auto-calculates the required widths for the Host's
    # interrupt vectors and AXI/RegBus interconnect arrays. This is done by
    # inspecting the entire SoC topology defined in the YAML. This makes the
    # Host component highly adaptable without requiring manual parameterization.
    # The host isle's default of NumIntrsIn is the width of the external interrupt vector it is
    # built for (component standardization, 5.1): the vector is sized to it, not to the routed
    # count. Once the host is configured, its resolved parameters - the isle's defaults under
    # the description's and the derived ones - are published to the pre-build phase, where a
    # registry command may read any of them as '{host.<Parameter>}' (the cheshire PLIC
    # regeneration does).
    from core.sv_parser import get_isle_info as _host_isle_info
    _hinfo = _host_isle_info(soc_config.host.type, env.search_paths, env.exclude_dir) or {}
    _cap = (_hinfo.get("supported_params") or {}).get("NumIntrsIn")
    try:
        _cap = int(str(_cap), 0) if _cap is not None else None
    except ValueError:
        _cap = None   # a default that is an expression, not a literal: no capacity rule
    autoconfigure_host(soc_config, ext_irq_capacity=_cap)
    env.host_params = dict(_hinfo.get("supported_params") or {})
    env.host_params.update({k: ("1" if v is True else "0" if v is False else v)
                            for k, v in (soc_config.host.parameters or {}).items()})

    print("=" * 70)
    print("[*] Starting Phase 1: Generating dynamic Isles...")
    
    # Store original isle types before they are overwritten for NoC topology.
    # This is needed by the Universal Tile wrapper to instantiate the correct underlying module.
    original_isle_types = {}
    if soc_config.topology.type == "noc":
        all_comps_for_type_tracking = [soc_config.host] + (soc_config.components if soc_config.components else [])
        for c in all_comps_for_type_tracking:
            if c.type.endswith('_isle') or c.type.endswith('_subtile'):
                original_isle_types[c.name] = c.type
                
    # Data structures to track generated files and dependencies.
    generated_module_files = []
    required_local_files = set()
    project_dependencies = {}
    # Regex for extracting Ollivander-specific pragmas from source files.
    req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
    dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')

    # Mako helper to inject a `require` pragma into the rendered output.
    def require_file_helper(filename):
        required_local_files.add(filename)
        return f'// OLLIVANDER: require="{filename}"'
        
    # Mako helper to inject a `BENDER` dependency pragma.
    def require_bender_helper(name, git=None, rev=None, version=None):
        project_dependencies.setdefault(name, {})
        if git:
            project_dependencies[name]['git'] = git
        if rev:
            project_dependencies[name]['rev'] = rev
        if version:
            project_dependencies[name]['version'] = version
        
        args = []
        if git:
            args.append(f'git="{git}"')
        if rev:
            args.append(f'rev="{rev}"')
        if version:
            args.append(f'version="{version}"')
        arg_str = " ".join(args)
        if arg_str:
            arg_str = " " + arg_str
        return f'// BENDER: name="{name}"{arg_str}'

    # =========================================================================
    # 6. PHASE 1: DYNAMIC ISLES GENERATION
    # =========================================================================
    # This phase generates intermediate SystemVerilog wrappers for composite
    # blocks (like the APB Subsystem) before validating the main top-level
    # interconnect. This allows for a two-pass generation flow where complex
    # sub-modules are created first, and their interfaces are then analyzed
    # for the final top-level wiring.

    generator = RTLGenerator(env, soc_config, template_lookup)
    generator.generate_dynamic_isles()
    
    print("\n[*] Starting Phase 2: Cross-validating Hardware constraints...")
    
    # =========================================================================
    # 7. PHASE 2: HARDWARE-FIRST VALIDATION
    # =========================================================================
    # This second validation pass ensures that the configuration defined in YAML
    # still matches the hardware constraints, even after Phase 1 has generated
    # new intermediate modules (like the APB subsystem). This is a crucial
    # "Hardware-First" correctness check.
    try:
        validate_cross_references(soc_config)
        validate_untyped_blocks(soc_config)
        # Per-instance lists become resolved windows here, before any generation step reads an
        # address: from this point on 'base_addr' is always an integer and '_windows' holds the
        # per-instance truth (soc_schema.normalize_address_ranges).
        normalize_address_ranges(soc_config)
        validate_soc_components(soc_config, search_paths, exclude_dir, generator.original_isle_types)
        warn_boot_memory_gated(soc_config, generator.original_isle_types)
        if soc_config.topology.type == "noc":
            print("[*] Running NoC Placement Checker (NPC)...")
            run_noc_placement_check(soc_config, env)
            print("  [SUCCESS] NoC placement validated (no coordinate collision).")
    except ValueError as e:
        print("\n[ERROR] SoC Hardware Validation Failed!")
        print("=" * 70)
        print(e)
        sys.exit(1)

    print("\n[SUCCESS] Hardware semantics validated successfully!")
    
    # =========================================================================
    # 8. GENERATION REPORTING
    # =========================================================================
    print_generation_report(soc_config)

    # =========================================================================
    # 9. PHASE 3: METADATA EXTRACTION & TOP-LEVEL RENDERING
    # =========================================================================
    # This phase prepares all the data needed for the final Mako rendering pass.
    comp_info, wiring_matrix, global_defines = generator.extract_wiring_metadata()
    # The boot image must be linked for a memory the host can FETCH from, and the
    # three declarations that decide it never mention each other (see
    # check_boot_memory_executable). Runs here because it needs the parsed host
    # contract from comp_info, and before rendering so a bad map never reaches RTL.
    check_boot_memory_executable(soc_config, comp_info)
    generator.render_top_level(comp_info, wiring_matrix, global_defines)
    # The placement report reads the generator's truth - the staged isle headers in
    # comp_info and the resolved offload targets - so it is written only now.
    if soc_config.topology.type == "noc":
        write_noc_placement_report(soc_config, env, comp_info, getattr(generator, "offload_targets", {}), generator.original_isle_types)
        print("  -> NoC placement report written (generated/doc/noc_placement_report.md).")
            
    # =========================================================================
    # INJECT BENDER OVERRIDES
    # =========================================================================
    # If the environment configurations specify dependency overrides, append them
    # to the generated Bender manifest to resolve version/path conflicts automatically.
    # The base environment is read first and the project one second, so that a project keeps the
    # last word key by key. The base config is included deliberately: a few forced resolutions
    # are Ollivander's own responsibility rather than the user's - a topology the generator
    # advertises must work out of the box, and Bender cannot reach some of those resolutions on
    # its own (a fork under a different URL, or an untagged commit, cannot satisfy a semantic
    # version requirement coming from another IP). Note that env_config_path is the resolved
    # default, which args.env_config does not carry when -e is not passed.
    env_yaml_paths = [env.env_config_path, args.append_env]
    loaded = []
    for p in env_yaml_paths:
        if p and Path(p).is_file():
            loaded.append((Path(p).name, load_env_yaml(p)))

    # A project may decline the forced resolutions of the base configuration as a whole, with
    # "inherit_default_overrides: false". That is what a project re-pinning many IPs wants: it
    # rewrites the set from scratch without inheriting forcings it did not ask for, which would
    # otherwise apply in silence, since Bender never reports an override it honours. The flag
    # governs only what the base configuration contributes, never the project's own block, and
    # defaults to true. There is no counterpart for the dependency registry, and the reason is worth
    # keeping should that ever change: a registry entry only reaches Bender when a component or a
    # template requires it by pragma, so an unused one is already inert. Forcings apply to the whole
    # graph unconditionally, which is what makes an escape hatch necessary for them alone.
    inherit_defaults = True
    for _, env_data in loaded:  # Base first, project last: the project has the last word.
        if 'inherit_default_overrides' in env_data:
            inherit_defaults = bool(env_data['inherit_default_overrides'])
    if not inherit_defaults and loaded:
        base_name, base_data = loaded[0]
        print(f"  [INFO] inherit_default_overrides is false: the "
              f"{len(base_data.get('overrides') or {})} forced resolutions declared by {base_name} "
              f"are ignored, and Bender resolves those packages on its own.")
        loaded = loaded[1:]

    # The file each surviving forcing came from, so that the report below can tell an inherited one
    # from one the project asked for. The last writer wins, exactly as the values do.
    base_src = Path(env.env_config_path).name if env.env_config_path else None
    overrides, disabled, origin = {}, [], {}
    for src_name, env_data in loaded:
        for name, spec in (env_data.get('overrides') or {}).items():
            if spec is None or spec is False:
                # A null (or false) value disables a forced resolution instead of replacing it.
                # Substituting is not always possible: a revision satisfying both the catalogue and
                # an IP the project adds may simply not exist. Dropping the entry hands the package
                # back to Bender's own resolution, conflict report included.
                if overrides.pop(name, None) is not None:
                    origin.pop(name, None)
                    disabled.append(name)
                elif inherit_defaults:
                    # A removal that removes nothing survives the update that made it pointless, so
                    # it is reported - unless inheritance is off, where it is redundant by
                    # construction rather than stale.
                    print(f"  [WARNING] {src_name} disables the forced resolution of '{name}', which"
                          f" no configuration declares: the entry has no effect.")
            elif isinstance(spec, dict):
                overrides[name] = spec
                origin[name] = src_name
            else:
                # Any other scalar would be written into Bender.local verbatim and fail inside a
                # generated file the user never wrote, so it is refused here, where the cause is
                # still visible.
                print(f"\n[ERROR] In {src_name}, the override of '{name}' is neither a mapping nor "
                      f"null: {spec!r}.\n        Declare 'git' plus 'rev' to force a revision, or "
                      f"null to drop a forced resolution.")
                sys.exit(1)
    if disabled:
        print(f"  [INFO] Forced resolutions dropped on request: {', '.join(sorted(disabled))}."
              f" Bender resolves those packages on its own.")

    # Report what is in effect, and not only what was skipped. Bender never mentions an override it
    # honours, so an inherited forcing is invisible from inside the project: seeing it would mean
    # opening the generator's own configuration, or reading the Bender.local this run is about to
    # write. Naming the packages here makes the set auditable where the project is built, which is
    # what turned a silent iDMA misresolution into a fixable one.
    if overrides:
        from_project = {n for n, src in origin.items() if src != base_src}
        if not from_project:
            print(f"  [INFO] Forced resolutions in effect: {len(overrides)}, all from {base_src}.")
        elif len(from_project) == len(overrides):
            print(f"  [INFO] Forced resolutions in effect: {len(overrides)}, all declared by the"
                  f" project.")
        else:
            print(f"  [INFO] Forced resolutions in effect: {len(overrides)}, of which "
                  f"{len(from_project)} declared by the project (*), the rest by {base_src}.")
        # The marker only earns its place when the set is mixed: where every entry has the same
        # origin, the heading already says so and a star on each name is noise.
        mark = from_project if len(from_project) != len(overrides) else set()
        listing = ", ".join(f"{n}*" if n in mark else n for n in sorted(overrides))
        # break_on_hyphens would split 'hwpe-ctrl' and 'riscv-dbg' across two lines, leaving a
        # package name that cannot be read nor grepped for.
        print(textwrap.fill(listing, width=100, initial_indent=" " * 9, subsequent_indent=" " * 9,
                            break_on_hyphens=False, break_long_words=False))

    # Write overrides to Bender.local to cleanly resolve conflicts without mangling Bender.yml
    bender_local_path = env.bender_dir / "Bender.local"
    if overrides:
        try:
            with open(bender_local_path, 'w', encoding='utf-8') as bf:
                bf.write(get_generation_comment("#", base_dir))
                bf.write("# Auto-generated by Ollivander to resolve dependency conflicts\n")
                yaml.dump({"overrides": overrides}, bf, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"[WARNING] Failed to write Bender.local: {e}")
    elif bender_local_path.is_file():
        # No overrides are declared any more, so a Bender.local left over from a previous run
        # must go: Bender applies its 'overrides' section to the whole dependency graph,
        # transitive dependencies included, so a stale file would keep forcing revisions that
        # nothing in the configuration asks for - silently, since Bender does not report an
        # override it honours.
        try:
            bender_local_path.unlink()
            print("  [INFO] No dependency overrides declared: removed the stale Bender.local.")
        except OSError as e:
            print(f"[WARNING] Failed to remove the stale Bender.local: {e}")

    # =========================================================================
    # 10. PHASE 4: FETCH EXTERNAL IPs & PRE-BUILD
    # =========================================================================
    print("=" * 70)
    print("[*] Starting Phase 4: Fetching External IPs via Bender...\n")
    bender_exe = shutil.which("bender") or (str(base_dir / "bender") if (base_dir / "bender").is_file() else "bender")
    lock_file = env.bender_dir / "Bender.lock"
    from core.utils import Spinner
    # 'bender checkout' materializes the existing lock and is therefore much faster, but it also
    # ignores declarations that changed after the lock was written: the new revisions would
    # silently not take effect, which is why editing a dependency used to require TEST_CLEAN=1.
    # Compare instead what the manifests pin against what the lock resolved, and re-resolve on
    # any mismatch. Timestamps are useless here: Bender.yml is regenerated on every run, so its
    # mtime is always newer than the lock's.
    def bender_lock_is_stale(lock_path):
        """Return (stale, refetch): whether the lock disagrees with the declared revisions, and
        {name: (checkout_path, reason)} for every package whose mismatch is pinned to a specific
        checkout. The caller DELETES those checkouts before 'bender update': Bender never
        overwrites a checkout carrying local modifications (warning W06), and a patched checkout
        is modified by construction - so on a revision bump the update would rewrite the lock
        while the OLD tree silently survived in bender_work, and the run would validate a state
        that no longer exists (seen live on the cheshire 55650af -> faa7d15 bump, 2026-08-29: the
        gate needed TEST_CLEAN=1 as a requirement, not a caution). Re-materializing only the
        mismatched checkout keeps the steady state free and bounds a bump's cost to the
        dependency being bumped (user-facing behaviour: env_configuration_guide.md, section 3.1).
        """
        refetch = {}
        work_root = env.bender_dir / "bender_work"
        try:
            locked = (yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}).get("packages", {}) or {}
        except Exception:
            return True, refetch  # An unreadable lock is not worth trusting.
        try:
            manifest_deps = (yaml.safe_load(env.bender_manifest_path.read_text(encoding="utf-8")) or {}).get("dependencies", {}) or {}
        except (OSError, yaml.YAMLError):
            # The manifest was written by this very run, so failing to read it back means something
            # is badly wrong. Carrying on with an empty declaration set would compare the lock
            # against nothing and pronounce it valid, which is the one answer that cannot be right.
            return True, refetch
        stale = False
        declared = dict(manifest_deps)
        declared.update(overrides)  # An override wins over the manifest, exactly as in Bender.
        for name, spec in declared.items():
            if not isinstance(spec, dict):
                continue
            entry = locked.get(name)
            if entry is None:
                # A forced resolution for a package that never enters this SoC's graph is inert by
                # design - the catalogue is deliberately a superset - so its absence from the lock
                # is the normal case, not a disagreement. A dependency the manifest actually
                # declares is another matter: if the lock does not carry it, the lock is behind.
                if name in manifest_deps:
                    stale = True
                continue
            source = entry.get("source", {}) or {}
            rev = str(spec.get("rev", ""))
            if "Path" in source:
                # Bender degraded this package to a path dependency because its checkout is not in
                # a clean state (warning W06) - which is the expected consequence of patching it,
                # since a patch modifies tracked files (untracked pre-build artifacts, like the
                # downloaded boot-device models, do NOT trigger the degradation - verified on the
                # 2026-08-29 replays). The lock entry then carries neither a Git
                # source nor a revision, so comparing the declaration against those nulls reports
                # the lock stale on *every* run and re-resolves the whole graph each time: minutes
                # per project, for a state we created on purpose. Ask git instead, which still
                # knows the revision the checkout was fetched at, so a genuine revision bump on a
                # patched IP is still detected.
                if re.fullmatch(r"[0-9a-f]{40}", rev):
                    checkout = env.bender_dir / source["Path"]
                    head = subprocess.run(["git", "-C", str(checkout),
                                           "rev-parse", "HEAD"], capture_output=True, text=True)
                    if head.returncode == 0 and head.stdout.strip() != rev:
                        stale = True
                        refetch[name] = (checkout, f"declared rev changed ({head.stdout.strip()[:10]} -> {rev[:10]})")
                continue
            if spec.get("git") and source.get("Git") != spec["git"]:
                stale = True
                refetch[name] = (work_root / name, f"git URL changed ({source.get('Git')} -> {spec['git']})")
                continue
            # Only an explicit commit can be compared: a branch or tag name is a moving target
            # by definition, and the lock legitimately freezes it to whatever it pointed at.
            # Semantic-version constraints resolve to a revision that cannot be predicted here.
            if re.fullmatch(r"[0-9a-f]{40}", rev) and entry.get("revision") != rev:
                stale = True
                refetch[name] = (work_root / name, f"declared rev changed ({str(entry.get('revision'))[:10]} -> {rev[:10]})")
        return stale, refetch

    lock_is_stale, stale_checkouts = bender_lock_is_stale(lock_file) if lock_file.is_file() else (False, {})
    # Re-materialize every checkout whose declaration moved: deleted here, BEFORE 'bender
    # update', so the update fetches it fresh at the new revision and the patches and pre-build
    # commands re-apply on a pristine tree (Phase 4b runs after this). The deletion is loud on
    # purpose: bender_work is a build product by contract, but a developer's parked experiment
    # must never vanish without a line naming what went and why.
    work_root = (env.bender_dir / "bender_work").resolve()
    for name, (checkout, reason) in stale_checkouts.items():
        checkout = checkout.resolve()
        if not checkout.is_dir() or work_root not in checkout.parents:
            continue  # Nothing on disk to refresh, or a path outside the workspace: never delete those.
        print(f"  [INFO] Re-materializing '{name}': {reason}; removing {checkout} so Bender fetches it fresh.")
        try:
            shutil.rmtree(checkout)
        except OSError as e:
            # Leave the rest to 'bender update': a half-removed checkout is not clean either, so
            # at worst the next run reports this same mismatch again, loudly.
            print(f"[WARNING] Could not remove '{checkout}': {e}")
    try:
        if lock_file.is_file() and not lock_is_stale:
            try:
                # Attempt to use the existing locked dependency versions first
                with Spinner("  -> Running 'bender checkout' to verify local cache..."):
                    subprocess.run([bender_exe, "checkout", "--force"], cwd=env.bender_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # If checkout fails (e.g. missing dependencies in lockfile), fall back to update
                print("  [WARNING] 'bender checkout' failed. Attempting 'bender update' to resolve dependencies...")
                with Spinner("  -> Running 'bender update' (this may take a minute)..."):
                    subprocess.run([bender_exe, "update"], cwd=env.bender_dir, check=True, capture_output=True)
        else:
            if lock_is_stale:
                print("  [INFO] Bender.lock disagrees with the declared revisions: re-resolving dependencies.")
            with Spinner("  -> Running 'bender update' (this may take a minute)..."):
                subprocess.run([bender_exe, "update"], cwd=env.bender_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Failed to fetch dependencies with Bender.\nStdout: {e.stdout.decode(errors='ignore')}\nStderr: {e.stderr.decode(errors='ignore')}")
        sys.exit(1)

    # A package the lock records as a path dependency is one Bender never re-fetches:
    # if the directory is gone, 'bender checkout' merely warns (W22) and exits 0, and
    # the failure surfaces phases later disguised as something else - a PeakRDL include
    # that cannot be found, an RTL file missing from the manifest. Patched checkouts are
    # exactly the packages that end up recorded this way (a dirty checkout is degraded
    # to a path dependency, as the registry documents), so the two ways to get here are
    # both realistic: a lost bender_work/ with a surviving lock, or Bender.* files
    # carried over from another machine, whose paths were valid only there.
    missing_paths = []
    if lock_file.is_file():
        try:
            lock_data = yaml.safe_load(lock_file.read_text()) or {}
            for pkg_name, entry in (lock_data.get("packages") or {}).items():
                source = entry.get("source") or {}
                if "Path" in source and not (env.bender_dir / source["Path"]).is_dir():
                    missing_paths.append(pkg_name)
        except yaml.YAMLError:
            pass  # An unreadable lock already fails loudly in bender_lock_is_stale.
    if missing_paths:
        print(f"\n[ERROR] These packages are recorded as path dependencies in Bender.lock but are "
              f"missing from the checkout:\n          {', '.join(sorted(missing_paths))}\n"
              f"        Bender never re-fetches a path dependency, so generation would fail phases "
              f"later with an unrelated-looking message.\n"
              f"        This happens when a patched checkout is lost, or when Bender.yml/Bender.lock/"
              f"Bender.local are carried over from another machine.\n"
              f"        Run 'make clean' in the project and regenerate.")
        sys.exit(1)
    print("  [SUCCESS] External IPs successfully fetched and resolved.")
        
    # The environment YAMLs were already merged, once, when the environment was
    # built (env_manager.build_environment). A second merge used to happen here
    # with .extend() on 'patches' and 'pre_build_cmds' - over lists the first pass
    # had ALREADY filled with the project's own entries, so a project declaring
    # either had them appended to themselves: patches applied twice, the second
    # application finding its search string already replaced and reported as a
    # stale patch, and pre-build commands run twice. Latent only because no
    # example project declares dependencies per project.

    # Execute Pre-Build commands and patches on fetched IPs
    run_pre_build_steps(env)

    # =========================================================================
    # 11. PHASE 5: NOC GENERATION (FLOOGEN)
    # =========================================================================
    # Automatically invokes FlooGen to generate the NoC configuration, router
    # instances, and the standard FlooNoC package.
    check_floogen_matches_rtl(env, soc_config)
    run_floogen(soc_config, cfg_dir, hw_dir)

    # =========================================================================
    # 12. PHASE 6: REGISTER RTL GENERATION (PEAKRDL)
    # =========================================================================
    # Automatically invokes PeakRDL to generate the physical SystemVerilog 
    # register block from the rendered SystemRDL specification.
    custom_rdl_paths = list(getattr(env, 'rdl_include_paths', getattr(env, 'rdl_includes', [])))
    for p in [args.env_config, args.append_env]:
        if p and Path(p).is_file():
            env_data = load_env_yaml(p)
            if 'rdl_includes' in env_data:
                custom_rdl_paths.extend(env_data['rdl_includes'])
            paths_cfg = env_data.get('paths')
            if isinstance(paths_cfg, dict) and 'rdl_includes' in paths_cfg:
                custom_rdl_paths.extend(paths_cfg['rdl_includes'])
    run_peakrdl(soc_config, reg_dir, hw_dir, sw_dir, registry_dependencies, bender_dir, custom_rdl_paths)
    
    # =========================================================================
    # 13. PHASE 7: PADFRAME GENERATION (PADRICK)
    # =========================================================================
    run_padrick(env, soc_config, config_path.parent.resolve())

    # Re-render top-level manifests (specifically Bender.yml) now that Padrick
    # has generated the padframe source files list (src_files.yml).
    if soc_config.padframe:
        generator.render_top_level(comp_info, wiring_matrix, global_defines)

    # =========================================================================
    # 14. PHASE 8: CHIP WRAPPER ENGINE
    # =========================================================================
    if soc_config.padframe:
        generator.generate_chip_wrapper(comp_info, wiring_matrix, global_defines)

    # =========================================================================
    # 15. PHASE 9: RTL FORMATTING (VERIBLE)
    # =========================================================================
    # Automatically formats all generated SystemVerilog files to ensure a clean,
    # professional and highly readable output.
    run_verible(hw_dir, tb_dir)

    # =========================================================================
    # 16. PHASE 10: IP-XACT COMPONENT EXPORT
    # =========================================================================
    # Generates a standard IEEE 1685 IP-XACT component XML description for
    # the digital top-level of the SoC.
    generate_ipxact(soc_config, env, generator, comp_info)

    # =========================================================================
    # 17. PHASE 11: SELF-ELABORATION OF THE GENERATED RTL
    # =========================================================================
    # Ollivander parses the external IPs with pyslang and, until now, never
    # re-read what it writes. This closes that loop, and it runs LAST so it
    # validates the bytes actually shipped, formatting included.
    #
    # It black-boxes nothing it does not have to: the dependencies are already
    # materialized (bender checkout ran in phase 4), so the whole design
    # elaborates. What it cannot see are the stubs, which do not exist yet -
    # that half belongs to fast-check, the only place our wrappers are checked
    # against exact IP signatures.
    run_generated_rtl_check(env, outdir_path)

    print(f"\n[SUCCESS] Generation complete! Files saved to '{outdir_path.resolve()}'")

if __name__ == "__main__":
    main()

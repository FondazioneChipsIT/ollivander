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
import importlib.util
from pathlib import Path
import yaml
from pydantic import ValidationError
from mako.lookup import TemplateLookup

from core.soc_schema import OllivanderConfig, validate_soc_components, Component
from core.stub_generator import generate_stubs
from core.env_manager import setup_environment
from core.arch_optimizer import optimize_clock_tree, autoconfigure_host
from core.tool_runners import run_floogen, run_peakrdl, run_verible, run_pre_build_steps, run_padrick
from core.reporter import print_generation_report
from core.rtl_generator import RTLGenerator
from core.ipxact_generator import generate_ipxact
from core.noc_placement_checker import run_noc_placement_check

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
    
    args = parser.parse_args()
    config_path = Path(args.config)
    
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
                config_data = yaml.safe_load(f)
        else:
            print(f"[ERROR] Unsupported configuration file extension: {config_path.suffix}. Use .yaml, .yml, or .py")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load configuration file:\n{e}")
        sys.exit(1)
        
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
    autoconfigure_host(soc_config)

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
        validate_soc_components(soc_config, search_paths, exclude_dir, generator.original_isle_types)
        if soc_config.topology.type == "noc":
            print("[*] Running NoC Placement Checker (NPC) and Latency Estimator...")
            run_noc_placement_check(soc_config, env)
            print("  [SUCCESS] NoC placement validated. Report generated successfully.")
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
    generator.render_top_level(comp_info, wiring_matrix, global_defines)
            
    # =========================================================================
    # INJECT BENDER OVERRIDES
    # =========================================================================
    # If the environment configurations specify dependency overrides, append them
    # to the generated Bender manifest to resolve version/path conflicts automatically.
    env_yaml_paths = [args.env_config, args.append_env]
    overrides = {}
    for p in env_yaml_paths:
        if p and Path(p).is_file():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    env_data = yaml.safe_load(f)
                if env_data and 'overrides' in env_data:
                    overrides.update(env_data['overrides'])
            except Exception:
                pass

    # Write overrides to Bender.local to cleanly resolve conflicts without mangling Bender.yml
    if overrides:
        bender_local_path = env.bender_dir / "Bender.local"
        try:
            with open(bender_local_path, 'w', encoding='utf-8') as bf:
                bf.write("# Auto-generated by Ollivander to resolve dependency conflicts\n")
                yaml.dump({"overrides": overrides}, bf, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"[WARNING] Failed to write Bender.local: {e}")

    # =========================================================================
    # 10. PHASE 4: FETCH EXTERNAL IPs & PRE-BUILD
    # =========================================================================
    print("=" * 70)
    print("[*] Starting Phase 4: Fetching External IPs via Bender...\n")
    bender_exe = shutil.which("bender") or (str(base_dir / "bender") if (base_dir / "bender").is_file() else "bender")
    lock_file = env.bender_dir / "Bender.lock"
    from core.utils import Spinner
    try:
        if lock_file.is_file():
            try:
                # Attempt to use the existing locked dependency versions first
                with Spinner("  -> Running 'bender checkout' to verify local cache..."):
                    subprocess.run([bender_exe, "checkout"], cwd=env.bender_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # If checkout fails (e.g. missing dependencies in lockfile), fall back to update
                print("  [WARNING] 'bender checkout' failed. Attempting 'bender update' to resolve dependencies...")
                with Spinner("  -> Running 'bender update' (this may take a minute)..."):
                    subprocess.run([bender_exe, "update"], cwd=env.bender_dir, check=True, capture_output=True)
        else:
            with Spinner("  -> Running 'bender update' (this may take a minute)..."):
                subprocess.run([bender_exe, "update"], cwd=env.bender_dir, check=True, capture_output=True)
        print("  [SUCCESS] External IPs successfully fetched and resolved.")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Failed to fetch dependencies with Bender.\nStdout: {e.stdout.decode(errors='ignore')}\nStderr: {e.stderr.decode(errors='ignore')}")
        sys.exit(1)
        
    # Merge custom patches and pre-build commands from Environment YAMLs
    for p in [args.env_config, args.append_env]:
        if p and Path(p).is_file():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    env_data = yaml.safe_load(f)
                if env_data and 'dependencies' in env_data:
                    for dep_name, dep_info in env_data['dependencies'].items():
                        if dep_name not in env.registry_dependencies:
                            env.registry_dependencies[dep_name] = {}
                        if 'patches' in dep_info:
                            env.registry_dependencies[dep_name].setdefault('patches', []).extend(dep_info['patches'])
                        if 'pre_build_cmds' in dep_info:
                            env.registry_dependencies[dep_name].setdefault('pre_build_cmds', []).extend(dep_info['pre_build_cmds'])
            except Exception:
                pass

    # Execute Pre-Build commands and patches on fetched IPs
    run_pre_build_steps(env)

    # =========================================================================
    # 11. PHASE 5: NOC GENERATION (FLOOGEN)
    # =========================================================================
    # Automatically invokes FlooGen to generate the NoC configuration, router
    # instances, and the standard FlooNoC package.
    run_floogen(soc_config, cfg_dir, hw_dir)

    # =========================================================================
    # 12. PHASE 6: REGISTER RTL GENERATION (PEAKRDL)
    # =========================================================================
    # Automatically invokes PeakRDL to generate the physical SystemVerilog 
    # register block from the rendered SystemRDL specification.
    custom_rdl_paths = list(getattr(env, 'rdl_include_paths', getattr(env, 'rdl_includes', [])))
    for p in [args.env_config, args.append_env]:
        if p and Path(p).is_file():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    env_data = yaml.safe_load(f)
                if env_data:
                    if 'rdl_includes' in env_data:
                        custom_rdl_paths.extend(env_data['rdl_includes'])
                    if 'paths' in env_data and isinstance(env_data['paths'], dict) and 'rdl_includes' in env_data['paths']:
                        custom_rdl_paths.extend(env_data['paths']['rdl_includes'])
            except Exception:
                pass
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

    print(f"\n[SUCCESS] Generation complete! Files saved to '{outdir_path.resolve()}'")

if __name__ == "__main__":
    main()
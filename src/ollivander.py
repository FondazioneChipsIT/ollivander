#!/usr/bin/env python3
# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
#
# Ollivander SoC Generator - Main Entry Point

import argparse
import sys
import re
from pathlib import Path
import yaml
from pydantic import ValidationError
from mako.lookup import TemplateLookup

from core.soc_schema import OllivanderConfig, validate_soc_components
from core.stub_generator import generate_stubs
from core.env_manager import setup_environment
from core.arch_optimizer import optimize_clock_tree, autoconfigure_host
from core.tool_runners import run_floogen, run_regtool, run_verible
from core.reporter import print_generation_report
from core.rtl_generator import RTLGenerator

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
        help="Path to the SoC configuration YAML file."
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
    regtool_paths = env.regtool_paths
    search_paths = env.search_paths
    exclude_dir = env.exclude_dir

    # Mako template engine setup.
    template_lookup = TemplateLookup(directories=[str(p) for p in template_paths])

    # =========================================================================
    # 3. YAML PARSING & VALIDATION
    # =========================================================================
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
    except Exception as e:
        print(f"[ERROR] Failed to parse YAML file:\n{e}")
        sys.exit(1)
        
    print(f"[*] Validating SoC configuration: {config_path.name}...")
    
    try:
        # Initialize the Pydantic model. This triggers the entire validation
        # engine defined in `soc_schema.py`, including the dynamic parsing of
        # SystemVerilog files for hardware components (Isles/Tiles).
        soc_config = OllivanderConfig(**yaml_data)
    except ValidationError as e:
        # If validation fails, print detailed, user-friendly error messages.
        print("\n[ERROR] SoC Configuration Validation Failed!")
        print("=" * 70)
        for err in e.errors():
            loc = " -> ".join([str(x) for x in err['loc']])
            msg = err['msg']
            print(f"Location : {loc}\nError    : {msg}\n" + "-" * 70)
        sys.exit(1)
        
    # If we get here, the basic configuration is valid.
    print("\n[SUCCESS] Basic Configuration validated successfully!")

    if args.generate_stubs:
        print("\n[*] Starting Fast-Check Stub Generation...")
        generate_stubs(outdir_path, soc_config, registry_dependencies, base_dir)
        print("  [SUCCESS] Faithful stubs and fast-compile scripts generated.")
        sys.exit(0)

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
    # 4.5. HOST AUTO-CONFIGURATION
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
    # 5. PHASE 1: DYNAMIC ISLES GENERATION
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
    # 6. PHASE 2: HARDWARE-FIRST VALIDATION
    # =========================================================================
    # This second validation pass ensures that the configuration defined in YAML
    # still matches the hardware constraints, even after Phase 1 has generated
    # new intermediate modules (like the APB subsystem). This is a crucial
    # "Hardware-First" correctness check.
    try:
        validate_soc_components(soc_config, search_paths, exclude_dir, generator.original_isle_types)
    except ValueError as e:
        print("\n[ERROR] SoC Hardware Validation Failed!")
        print("=" * 70)
        print(e)
        sys.exit(1)

    print("\n[SUCCESS] Hardware semantics validated successfully!")
    
    # =========================================================================
    # 7. GENERATION REPORTING
    # =========================================================================
    print_generation_report(soc_config)

    # =========================================================================
    # 8. PHASE 3: METADATA EXTRACTION & TOP-LEVEL RENDERING
    # =========================================================================
    # This phase prepares all the data needed for the final Mako rendering pass.
    comp_info, wiring_matrix, global_defines = generator.extract_wiring_metadata()
    generator.render_top_level(comp_info, wiring_matrix, global_defines)
            
    # =========================================================================
    # =========================================================================
    # Automatically invokes FlooGen to generate the NoC configuration, router
    # instances, and the standard FlooNoC package.
    run_floogen(soc_config, cfg_dir, hw_dir)

    # =========================================================================
    # 12. PHASE 5: REGISTER RTL GENERATION (REGTOOL)
    # =========================================================================
    # Automatically invokes the OpenTitan regtool to generate the physical 
    # SystemVerilog register block from the rendered HJSON specification.
    run_regtool(soc_config, reg_dir, hw_dir, sw_dir, regtool_paths, base_dir)

    # =========================================================================
    # 13. PHASE 6: RTL FORMATTING (VERIBLE)
    # =========================================================================
    # Automatically formats all generated SystemVerilog files to ensure a clean,
    # professional and highly readable output.
    run_verible(hw_dir, tb_dir)

    print(f"\n[SUCCESS] Generation complete! Files saved to '{outdir_path.resolve()}'")

if __name__ == "__main__":
    main()
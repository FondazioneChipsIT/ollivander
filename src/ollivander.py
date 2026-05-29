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
import os
import subprocess
import yaml
from pydantic import ValidationError
from mako.template import Template
from mako.lookup import TemplateLookup

from soc_schema import OllivanderConfig, get_isle_info, validate_soc_components
from wiring import build_connection_matrix, infer_interrupts

def fmt_dom(name): return name.replace('_clk', '').lower() if name else ""
def fmt_reg(name): return name.replace('_clk', '').lower() if name else ""
def fmt_rst(name): return name.replace('_rst', '').lower() if name else ""
def camel_case(name): return ''.join(word.title() for word in name.split('_'))

def is_external(comp):
    if not comp.interfaces:
        return False

    slaves = comp.interfaces.get('regbus_slave', [])
    if isinstance(slaves, dict):
        slaves = [slaves]

    return any(slv.get('external', False) for slv in slaves)

def auto_import_sv_packages(code: str) -> str:
    """Auto-detect SystemVerilog package dependencies and insert missing imports."""
    pkgs = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)::', code))
    existing_imports = set(re.findall(r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)::\*;', code))
    new_imports = pkgs - existing_imports
    if new_imports:
        import_statements = "".join([f"  import {p}::*;\n" for p in sorted(list(new_imports))])
        insert_pos = -1
        last_import_match = list(re.finditer(r'\bimport\s+[a-zA-Z_][a-zA-Z0-9_]*::\*;', code))
        if last_import_match:
            line_end = code.find('\n', last_import_match[-1].end())
            insert_pos = line_end + 1 if line_end != -1 else last_import_match[-1].end()
        else:
            module_match = re.search(r'\bmodule\s+[a-zA-Z_][a-zA-Z0-9_]*\s*(?:#\(|\(|;|\n)', code)
            if module_match:
                line_end = code.find('\n', module_match.start())
                insert_pos = line_end + 1 if line_end != -1 else module_match.end()
        if insert_pos != -1:
            return code[:insert_pos] + import_statements + code[insert_pos:]
    return code

def write_if_changed(file_path: Path, content: str):
    """Write content to file only if it differs from existing content to preserve timestamps."""
    if file_path.is_file():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if f.read() == content:
                    return
        except Exception:
            pass
    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

def main():
    # =========================================================================
    # 1. ARGUMENT PARSING
    # =========================================================================
    # Setup command line interface for the generator.
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
    
    args = parser.parse_args()
    config_path = Path(args.config)
    
    # Ensure the provided SoC specification file exists
    if not config_path.is_file():
        print(f"[ERROR] Configuration file not found: {config_path}")
        sys.exit(1)
        
    base_dir = Path(__file__).parent.parent.resolve()
        
    # =========================================================================
    # 2. ENVIRONMENT SETUP & PATH RESOLUTION
    # =========================================================================
    # Resolve where to find the Mako templates, SystemVerilog Isles, and output dir.
    env_config_path = Path(args.env_config) if args.env_config else base_dir / "ollivander_config.yaml"
    env_cfg = {}
    if env_config_path.is_file():
        try:
            with open(env_config_path, "r", encoding="utf-8") as f:
                env_cfg = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[WARNING] Failed to parse environment config '{env_config_path}': {e}")
    elif args.env_config:
        print(f"[ERROR] Specified environment config not found: {env_config_path}")
        sys.exit(1)
        
    env_base = env_config_path.parent
    paths_cfg = env_cfg.get('paths', {})
    
    append_env_cfg = {}
    append_env_base = None
    if args.append_env:
        append_env_path = Path(args.append_env)
        if append_env_path.is_file():
            try:
                with open(append_env_path, "r", encoding="utf-8") as f:
                    append_env_cfg = yaml.safe_load(f) or {}
                append_env_base = append_env_path.parent
            except Exception as e:
                print(f"[WARNING] Failed to parse appended environment config '{append_env_path}': {e}")
        else:
            print(f"[ERROR] Specified append environment config not found: {append_env_path}")
            sys.exit(1)
            
    app_paths_cfg = append_env_cfg.get('paths', {})

    registry_dependencies = env_cfg.get('dependencies', {})
    if append_env_cfg:
        for dep_name, dep_info in append_env_cfg.get('dependencies', {}).items():
            if dep_name in registry_dependencies:
                registry_dependencies[dep_name].update(dep_info)
            else:
                registry_dependencies[dep_name] = dep_info

    # Determine outdir: Command Line > Append Env > Env > Default
    if args.outdir is not None:
        outdir_path = Path(args.outdir).resolve()
    elif 'outdir' in app_paths_cfg:
        outdir_path = (append_env_base / app_paths_cfg['outdir']).resolve()
    elif 'outdir' in paths_cfg:
        outdir_path = (env_base / paths_cfg['outdir']).resolve()
    else:
        outdir_path = Path("generated").resolve()

    def get_path_cfg(key, default):
        if key in app_paths_cfg:
            return app_paths_cfg[key]
        if key in paths_cfg:
            return paths_cfg[key]
        return default

    hw_sub = get_path_cfg('sub_hw', 'hw')
    sw_sub = get_path_cfg('sub_sw', 'sw')
    doc_sub = get_path_cfg('sub_doc', 'doc')
    cfg_sub = get_path_cfg('sub_cfg', 'cfg')
    reg_sub = get_path_cfg('sub_reg', 'reg')
    tb_sub = get_path_cfg('sub_tb', 'tb')
    
    def resolve_manifest_path(raw_path, base_path):
        replaced = raw_path.replace('{outdir}', str(outdir_path))
        p = Path(replaced)
        return p.resolve() if p.is_absolute() else (base_path / p).resolve()

    if args.bender is not None:
        bender_manifest_path = resolve_manifest_path(args.bender, Path.cwd())
    elif 'bender_manifest' in app_paths_cfg:
        bender_manifest_path = resolve_manifest_path(app_paths_cfg['bender_manifest'], append_env_base)
    elif 'bender_manifest' in paths_cfg:
        bender_manifest_path = resolve_manifest_path(paths_cfg['bender_manifest'], env_base)
    else:
        bender_manifest_path = outdir_path / "Bender.yml"
        
    bender_dir = bender_manifest_path.parent

    def resolve_paths(cfg_val, base, default):
        if not cfg_val:
            cfg_val = default
        if isinstance(cfg_val, str):
            cfg_val = [cfg_val]
        return [(base / p).resolve() for p in cfg_val]
        
    # Handle legacy path keys for backwards compatibility
    tpl_cfg = paths_cfg.get('templates', paths_cfg.get('templates_dir', ['src/templates']))
    cmp_cfg = paths_cfg.get('components', paths_cfg.get('components_dir', ['components']))
    regtool_cfg = paths_cfg.get('regtool', ['tools/reggen/regtool.py'])
    
    template_paths = resolve_paths(tpl_cfg, env_base, ['src/templates'])
    component_paths = resolve_paths(cmp_cfg, env_base, ['components'])
    regtool_paths = resolve_paths(regtool_cfg, env_base, ['tools/reggen/regtool.py'])
    
    if append_env_base:
        template_paths.extend(resolve_paths(app_paths_cfg.get('templates', app_paths_cfg.get('templates_dir', [])), append_env_base, []))
        component_paths.extend(resolve_paths(app_paths_cfg.get('components', app_paths_cfg.get('components_dir', [])), append_env_base, []))
        app_regtool_cfg = app_paths_cfg.get('regtool', [])
        if app_regtool_cfg:
            # Sostituisce i percorsi di regtool se specificati nel file in append
            regtool_paths = resolve_paths(app_regtool_cfg, append_env_base, [])
    
    search_paths = [outdir_path] + component_paths + [base_dir]
    exclude_dir = outdir_path.name

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
        # Initialize the Pydantic model. This triggers the entire validation engine,
        # including the dynamic SystemVerilog file parsing for Isles/Tiles.
        soc_config = OllivanderConfig(**yaml_data)
    except ValidationError as e:
        print("\n[ERROR] SoC Configuration Validation Failed!")
        print("=" * 70)
        for err in e.errors():
            loc = " -> ".join([str(x) for x in err['loc']])
            msg = err['msg']
            print(f"Location : {loc}\nError    : {msg}\n" + "-" * 70)
        sys.exit(1)
        
    # If we get here, validation was successful
    print("\n[SUCCESS] Basic Configuration validated successfully!")

    # =========================================================================
    # 4. ARCHITECTURAL OPTIMIZATION (GARBAGE COLLECTION)
    # =========================================================================
    # Remove Unused Clock Domains to optimize PPA (Power, Performance, Area).
    used_clk_domains = set()
    if soc_config.host and soc_config.host.clock_domain:
        used_clk_domains.add(soc_config.host.clock_domain)
        
    if soc_config.components:
        for c in soc_config.components:
            if c.clock_domain:
                used_clk_domains.add(c.clock_domain)
            if c.components:
                for sub in c.components:
                    if sub.clock_domain:
                        used_clk_domains.add(sub.clock_domain)

    # Keep only domains that are either explicitly referenced or marked as real-time
    active_domains = []
    for dom in soc_config.clock_tree.domains:
        if dom.name in used_clk_domains or dom.is_real_time:
            active_domains.append(dom)
        else:
            print(f"[INFO] Clock domain '{dom.name}' is defined but not used by any component. Removing it from the generated project.")
            
    soc_config.clock_tree.domains = active_domains

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
    # Auto-calculate the required widths for Host interrupt vectors and AXI/Reg
    # arrays based on the physical topology mapped in the YAML, before Phase 1.
    def get_all_irqs(comps):
        irqs = []
        for c in comps:
            if c.interrupts:
                for irq_name, irq_cfg in c.interrupts.items():
                    irqs.append((c, irq_name, irq_cfg))
        return irqs

    comps_list = soc_config.components if soc_config.components else []
    all_irqs = get_all_irqs([soc_config.host] + comps_list)
    
    host_num_intrs_in = 0
    host_num_intrs_out = 0
    host_num_irq_harts = 0
    host_num_dbg_harts = 0

    if soc_config.host.interrupts:
        for irq_name, irq_cfg in soc_config.host.interrupts.items():
            if 'intr_ext' in irq_name:
                src = str(irq_cfg.get('source', ''))
                indices = re.findall(r'\[(\d+)(?::\d+)?\]\s*:', src)
                if indices:
                    host_num_intrs_in = max([int(i) for i in indices]) + 1

    for c, irq_name, irq_cfg in all_irqs:
        src = str(irq_cfg.get('source', ''))
        if c.name != soc_config.host.name:
            if f'{soc_config.host.name}.intr_ext_o' in src:
                indices = re.findall(rf'{soc_config.host.name}\.intr_ext_o\[(\d+)(?::\d+)?\]', src)
                if indices:
                    host_num_intrs_out = max(host_num_intrs_out, max([int(i) for i in indices]) + 1)
            
            if any(sig in src for sig in [f'{soc_config.host.name}.mtip_ext_o', f'{soc_config.host.name}.msip_ext_o', f'{soc_config.host.name}.xeip_ext_o']):
                host_num_irq_harts += int(irq_cfg.get('width', 1))
                
            if f'{soc_config.host.name}.dbg_ext_req_o' in src:
                host_num_dbg_harts += int(irq_cfg.get('width', 1))

    if soc_config.topology.type == "noc":
        # In a NoC, the Host is a single node. Its AXI counts are bounded to 1 (the Chimney connection)
        host_axi_mst_sync = 1 if ('axi_slave' in soc_config.host.interfaces or 'llc_port' in soc_config.host.interfaces) else 0
        host_axi_mst_async = 0
        host_axi_slv_sync = 1 if soc_config.host.interfaces.get('axi_master') else 0
        host_axi_slv_async = 0
        # For NoC, RegNumSlvSync must account for ALL slaves attached to the Host's RegBus.
        # This includes the external register blocks AND the internal System Controller.
        host_reg_slv_sync = (len(soc_config.system_controller.external_registers) if soc_config.system_controller and soc_config.system_controller.external_registers else 0) + (1 if soc_config.system_controller else 0)
        host_reg_slv_async = 0
    else:
        host_axi_mst = sum(1 for c in comps_list if c.interfaces and c.interfaces.get('axi_master'))
        host_axi_mst_sync = 0
        host_axi_mst_async = host_axi_mst
        
        host_axi_slv_sync = 0
        host_axi_slv_async = 0
        for c in comps_list:
            if c.interfaces and 'axi_slave' in c.interfaces:
                slvs = c.interfaces['axi_slave']
                if not isinstance(slvs, list):
                    slvs = [slvs]
                for slv in slvs:
                    if slv.get('sync_domain', False):
                        host_axi_slv_sync += slv.get('ports', 1)
                    else:
                        host_axi_slv_async += slv.get('ports', 1)
        host_reg_slv_sync = 1 if soc_config.system_controller else 0
        host_reg_slv_async = 0
        for c in comps_list:
            if c.interfaces and 'regbus_slave' in c.interfaces:
                slvs = c.interfaces['regbus_slave']
                if not isinstance(slvs, list):
                    slvs = [slvs]
                for slv in slvs:
                    if slv.get('sync_domain', True):
                        host_reg_slv_sync += 1
                    else:
                        host_reg_slv_async += 1

    if getattr(soc_config.host, 'parameters', None) is None:
        soc_config.host.parameters = {}
    
    soc_config.host.parameters.setdefault('NumIntrsIn', host_num_intrs_in)
    soc_config.host.parameters.setdefault('NumIntrsOut', host_num_intrs_out)
    soc_config.host.parameters.setdefault('NumIrqHarts', host_num_irq_harts)
    soc_config.host.parameters.setdefault('NumDbgHarts', host_num_dbg_harts)
    soc_config.host.parameters.setdefault('AxiNumMstSync', host_axi_mst_sync)
    soc_config.host.parameters.setdefault('AxiNumMstAsync', host_axi_mst_async)
    soc_config.host.parameters.setdefault('AxiNumSlvAsync', host_axi_slv_async)
    soc_config.host.parameters.setdefault('AxiNumSlvSync', host_axi_slv_sync)
    soc_config.host.parameters.setdefault('RegNumSlvAsync', host_reg_slv_async)
    soc_config.host.parameters.setdefault('RegNumSlvSync', host_reg_slv_sync)
    
    # Inject standard RegBus types to prevent SV from flattening parameterized structs into bits
    soc_config.host.parameters.setdefault('sync_reg_out_req_t', f'{soc_config.project.name}_soc_pkg::soc_reg_req_t')
    soc_config.host.parameters.setdefault('sync_reg_out_rsp_t', f'{soc_config.project.name}_soc_pkg::soc_reg_rsp_t')
    soc_config.host.parameters.setdefault('async_reg_out_req_t', f'{soc_config.project.name}_soc_pkg::soc_reg_req_t')
    soc_config.host.parameters.setdefault('async_reg_out_rsp_t', f'{soc_config.project.name}_soc_pkg::soc_reg_rsp_t')

    for comp in comps_list:
        if 'mailbox' in comp.type and comp.interrupts:
            if getattr(comp, 'parameters', None) is None:
                comp.parameters = {}
            if 'NumMailboxes' not in comp.parameters:
                comp.parameters['NumMailboxes'] = len([k for k, v in comp.interrupts.items() if not v.get('source')])

    # Helper function to recursively find a file within a list of base directories
    def find_file_in_paths(rel_path, paths_list):
        rel_path_obj = Path(rel_path)
        for p in paths_list:
            if p.is_file() and p.name == rel_path_obj.name:
                return p
            elif p.is_dir():
                candidate = p / rel_path
                if candidate.is_file():
                    return candidate
        return None

    print("=" * 70)
    print("[*] Starting Phase 1: Generating dynamic Isles...")
    
    # Store original isle types before they are overwritten for NoC topology
    original_isle_types = {}
    if soc_config.topology.type == "noc":
        all_comps_for_type_tracking = [soc_config.host] + (soc_config.components if soc_config.components else [])
        for c in all_comps_for_type_tracking:
            if c.type.endswith('_isle') or c.type.endswith('_subtile'):
                original_isle_types[c.name] = c.type
                
    generated_module_files = []
    required_local_files = set()
    project_dependencies = {}
    req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
    dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')

    def require_file_helper(filename):
        required_local_files.add(filename)
        return f'// OLLIVANDER: require="{filename}"'
        
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
    # Generate intermediate SystemVerilog wrappers for composite blocks 
    # (like the APB Subsystem) before validating the main top-level interconnect.
    def is_external_comp(comp):
        if not comp.interfaces:
            return False
        slaves = comp.interfaces.get('regbus_slave', [])
        if isinstance(slaves, dict):
            slaves = [slaves]
        return any(slv.get('external', False) for slv in slaves)

    if soc_config.topology.type == "crossbar":
        all_comps = [soc_config.host] + (soc_config.components if soc_config.components else [])
        for c in all_comps:
            if c.type == "apb_subsystem_isle":
                apb_peripherals = []
                if c.components:
                    for idx, p in enumerate(c.components):
                        # Auto-inject known interrupts for standard APB peripherals
                        # so the user doesn't have to define them in the YAML.
                        if not p.interrupts:
                            if p.type == 'apb_timer_unit':
                                p.interrupts = {'irq_hi': {}, 'irq_lo': {}}
                            elif p.type == 'apb_adv_timer':
                                p.interrupts = {'events': {'width': 4}, 'channels': {'width': 4}}
                            elif p.type == 'aon_timer':
                                p.interrupts = {
                                    'aon_timer_rst_req': {}, 'wkup_req': {}, 
                                    'nmi_wdog_timer_bark': {}, 'intr_wdog_timer_bark': {}, 
                                    'intr_wkup_timer_expired': {}
                                }
                            elif p.type == 'can_top_apb':
                                p.interrupts = {'event': {}}

                        p_dict = p.model_dump(exclude_none=True)
                        p_dict['idx'] = idx
                        if 'base_addr' in p_dict:
                            p_dict['base_addr'] = f"32'h{p_dict['base_addr']:X}" if isinstance(p_dict['base_addr'], int) else f"32'h{str(p_dict['base_addr']).replace('0x','')}"
                        if 'size' in p_dict:
                            p_dict['size'] = f"32'h{p_dict['size']:X}" if isinstance(p_dict['size'], int) else f"32'h{str(p_dict['size']).replace('0x','')}"
                        apb_peripherals.append(p_dict)
                
                tpl_path = find_file_in_paths("hw/isles/apb_subsystem_isle.sv.mako", template_paths)
                if not tpl_path:
                    print("\n[ERROR] APB subsystem template 'apb_subsystem_isle.sv.mako' not found.")
                    sys.exit(1)
                out_file = hw_dir / f"{soc_config.project.name}_{c.type}.sv"
                rel_name = os.path.relpath(out_file, bender_dir).replace('\\', '/')
                if rel_name not in generated_module_files:
                    generated_module_files.append(rel_name)
                print(f"  -> Rendering Isle {tpl_path.name} into {out_file.name}")
                try:
                    template = Template(filename=str(tpl_path), lookup=template_lookup)
                    rendered_code = template.render(apb_peripherals=apb_peripherals, c_type=c.type, p_name=soc_config.project.name, comp=c, config=soc_config, require_file=require_file_helper, require_bender=require_bender_helper)
                    required_local_files.update(req_pattern.findall(rendered_code))
                    rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{soc_config.project.name}_soc_pkg', rendered_code)
                    rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{soc_config.project.name}_noc_pkg', rendered_code)
                    if out_file.suffix == '.sv':
                        rendered_code = auto_import_sv_packages(rendered_code)
                    rendered_code = rendered_code.replace('\r\n', '\n')
                    write_if_changed(out_file, rendered_code)
                except Exception as e:
                    print(f"\n[ERROR] Failed to render {tpl_path.name}:\n{e}")
                    sys.exit(1)
            else:
                existing_isle = None
                for cp in component_paths:
                    if cp.is_dir():
                        try:
                            existing_isle = next(cp.rglob(f"{c.type}.sv"))
                            break
                        except StopIteration:
                            pass
                    elif cp.is_file() and cp.name == f"{c.type}.sv":
                        existing_isle = cp
                        break
                
                if existing_isle:
                    print(f"  -> Processing Component {existing_isle.name} (Staging to output)")
                    out_file = hw_dir / f"{soc_config.project.name}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, bender_dir).replace('\\', '/')
                    if rel_name not in generated_module_files:
                        generated_module_files.append(rel_name)
                    try:
                        content = existing_isle.read_text(encoding='utf-8')
                        required_local_files.update(req_pattern.findall(content))
                        content = re.sub(r'\bollivander_soc_pkg\b', f'{soc_config.project.name}_soc_pkg', content)
                        content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{soc_config.project.name}_noc_pkg', content)
                        content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {soc_config.project.name}_{c.type}', content)
                        content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {soc_config.project.name}_{c.type}', content)
                        write_if_changed(out_file, content)
                    except Exception as e:
                        print(f"\n[ERROR] Failed to stage {existing_isle.name}:\n{e}")
                        sys.exit(1)
    elif soc_config.topology.type == "noc":
        tpl_path = find_file_in_paths("hw/tiles/universal_tile.sv.mako", template_paths)
        if not tpl_path:
            print("\n[ERROR] Universal tile template 'universal_tile.sv.mako' not found.")
            sys.exit(1)
            
        all_comps = [soc_config.host] + (soc_config.components if soc_config.components else [])
        for c in all_comps:
            # Exclude external components (no RTL wrapper needed)
            if is_external_comp(c):
                continue
            
            if c.type.endswith('_tile'):
                existing_tile = None
                for cp in component_paths:
                    if cp.is_dir():
                        try:
                            existing_tile = next(cp.rglob(f"{c.type}.sv"))
                            break
                        except StopIteration:
                            pass
                    elif cp.is_file() and cp.name == f"{c.type}.sv":
                        existing_tile = cp
                        break
                
                if existing_tile:
                    print(f"  -> Processing custom Tile {existing_tile.name} (Staging to output)")
                    out_file = hw_dir / f"{soc_config.project.name}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, bender_dir).replace('\\', '/')
                    if rel_name not in generated_module_files:
                        generated_module_files.append(rel_name)
                    try:
                        content = existing_tile.read_text(encoding='utf-8')
                        required_local_files.update(req_pattern.findall(content))
                        content = re.sub(r'\bollivander_soc_pkg\b', f'{soc_config.project.name}_soc_pkg', content)
                        content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{soc_config.project.name}_noc_pkg', content)
                        content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {soc_config.project.name}_{c.type}', content)
                        content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {soc_config.project.name}_{c.type}', content)
                        write_if_changed(out_file, content)
                    except Exception as e:
                        print(f"\n[ERROR] Failed to stage {existing_tile.name}:\n{e}")
                        sys.exit(1)
                    continue
                else:
                    print(f"\n[ERROR] Component '{c.name}' requests '{c.type}', but no '{c.type}.sv' was found in component paths.")
                    sys.exit(1)
                    
            elif c.type.endswith('_isle') or c.type.endswith('_subtile'):
                existing_isle = None
                for cp in component_paths:
                    if cp.is_dir():
                        try:
                            existing_isle = next(cp.rglob(f"{c.type}.sv"))
                            break
                        except StopIteration:
                            pass
                    elif cp.is_file() and cp.name == f"{c.type}.sv":
                        existing_isle = cp
                        break
                
                if not existing_isle:
                    print(f"\n[ERROR] Component '{c.name}' requests '{c.type}', but no '{c.type}.sv' was found in component paths.")
                    sys.exit(1)
                
                isle_type = c.type
                tile_type = f"{c.name}_tile"
                print(f"  [INFO] Auto-converting Isle '{c.type}' -> Tile '{tile_type}'")
                
                # Stage the underlying Isle to the output directory with namespace substitution
                isle_out_file = hw_dir / f"{soc_config.project.name}_{existing_isle.name}"
                rel_isle_name = os.path.relpath(isle_out_file, bender_dir).replace('\\', '/')
                if rel_isle_name not in generated_module_files:
                    generated_module_files.append(rel_isle_name)
                try:
                    content = existing_isle.read_text(encoding='utf-8')
                    required_local_files.update(req_pattern.findall(content))
                    
                    for match in dep_pattern.finditer(content):
                        dep_name = match.group(1)
                        project_dependencies.setdefault(dep_name, {})
                        if match.group(2): 
                            project_dependencies[dep_name]['git'] = match.group(2)
                        if match.group(3): 
                            project_dependencies[dep_name]['rev'] = match.group(3)
                        if match.group(4): 
                            project_dependencies[dep_name]['version'] = match.group(4)
                    
                    content = re.sub(r'\bollivander_soc_pkg\b', f'{soc_config.project.name}_soc_pkg', content)
                    content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{soc_config.project.name}_noc_pkg', content)
                    content = re.sub(rf'\bmodule\s+{isle_type}\b', f'module {soc_config.project.name}_{isle_type}', content)
                    content = re.sub(rf'\bendmodule\s*:\s*{isle_type}\b', f'endmodule : {soc_config.project.name}_{isle_type}', content)
                    write_if_changed(isle_out_file, content)
                except Exception as e:
                    print(f"\n[WARNING] Failed to stage {existing_isle.name}:\n{e}")

                # Update component type to the generated tile type so subsequent phases use the wrapper
                c.type = tile_type
                
                out_file = hw_dir / f"{soc_config.project.name}_{c.type}.sv"
                rel_name = os.path.relpath(out_file, bender_dir).replace('\\', '/')
                if rel_name not in generated_module_files:
                    generated_module_files.append(rel_name)
                print(f"  -> Rendering Tile {tpl_path.name} into {out_file.name}")
                try:
                    template = Template(filename=str(tpl_path), lookup=template_lookup)
                    rendered_code = template.render(comp=c, config=soc_config, search_paths=search_paths, original_type=isle_type, require_file=require_file_helper, require_bender=require_bender_helper)
                    required_local_files.update(req_pattern.findall(rendered_code))
                    if out_file.suffix == '.sv':
                        rendered_code = auto_import_sv_packages(rendered_code)
                        
                    if "reg2hw_t" in rendered_code and f"import {soc_config.project.name}_reg_pkg::*;" not in rendered_code:
                        rendered_code = re.sub(rf'import {soc_config.project.name}_soc_pkg::\*;', 
                                               rf'import {soc_config.project.name}_soc_pkg::*;\n  import {soc_config.project.name}_reg_pkg::*;', 
                                               rendered_code)
                    rendered_code = re.sub(rf'(?<!::)\b{soc_config.project.name}_reg2hw_t\b', f'{soc_config.project.name}_reg_pkg::{soc_config.project.name}_reg2hw_t', rendered_code)
                    rendered_code = re.sub(rf'(?<!::)\b{soc_config.project.name}_hw2reg_t\b', f'{soc_config.project.name}_reg_pkg::{soc_config.project.name}_hw2reg_t', rendered_code)
                    rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_req_t\b', f'{soc_config.project.name}_soc_pkg::soc_axi_req_t', rendered_code)
                    rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_rsp_t\b', f'{soc_config.project.name}_soc_pkg::soc_axi_resp_t', rendered_code)
                    rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_([a-z]+)_chan_t\b', rf'{soc_config.project.name}_soc_pkg::soc_axi_\1_chan_t', rendered_code)
                                               
                    rendered_code = rendered_code.replace('\r\n', '\n')
                    write_if_changed(out_file, rendered_code)
                except Exception as e:
                    print(f"\n[ERROR] Failed to render {tpl_path.name}:\n{e}")
                    sys.exit(1)
                    
            else:
                print(f"\n[ERROR] Component '{c.name}' has invalid type '{c.type}'. In NoC topology, components must be either '*_tile' or '*_isle'.")
                sys.exit(1)

    print("\n[*] Starting Phase 2: Cross-validating Hardware constraints...")
    # =========================================================================
    # 6. PHASE 2: HARDWARE-FIRST VALIDATION
    # =========================================================================
    # Ensures that the configuration defined in YAML actually matches the 
    # parameters, ports, and limitations embedded inside the physical SystemVerilog files.
    try:
        validate_soc_components(soc_config, search_paths, exclude_dir, original_isle_types)
    except ValueError as e:
        print("\n[ERROR] SoC Hardware Validation Failed!")
        print("=" * 70)
        print(e)
        sys.exit(1)

    print("\n[SUCCESS] Hardware semantics validated successfully!")
    
    # =========================================================================
    # 7. GENERATION REPORTING
    # =========================================================================
    # Print a detailed summary of the SoC architecture to the terminal.

    components_list = soc_config.components if soc_config.components else []
    internal_comps = [c for c in components_list if not is_external_comp(c)]
    external_comps = [c for c in components_list if is_external_comp(c)]
    
    axi_slaves = []
    for c in components_list:
        if c.interfaces and 'axi_slave' in c.interfaces:
            slvs = c.interfaces['axi_slave']
            if isinstance(slvs, dict):
                slvs = [slvs]
            for slv in slvs:
                for _ in range(slv.get('ports', 1)):
                    axi_slaves.append(c.name)
                
    axi_masters = [c.name for c in components_list if c.interfaces and c.interfaces.get('axi_master')]
    
    reg_slaves = [soc_config.system_controller.name] if soc_config.system_controller else []
    reg_slaves_async = []
    for c in components_list:
        if c.interfaces and 'regbus_slave' in c.interfaces:
            slvs = c.interfaces['regbus_slave']
            if isinstance(slvs, dict):
                slvs = [slvs]
            for slv in slvs:
                if slv.get('sync_domain', True):
                    reg_slaves.append(c.name)
                else:
                    reg_slaves_async.append(c.name)
    all_reg_slaves = reg_slaves + reg_slaves_async

    def get_comp_report(comps):
        lines = []
        is_noc = soc_config.topology.type == "noc"
        for c in comps:
            intfs = []
            
            # --- NoC Specific Reporting ---
            if is_noc:
                if getattr(c, 'placement', None) and c.placement.get('logical'):
                    logical = c.placement.get('logical')
                    if isinstance(logical, list):
                        intfs.append("NoC Placement [Multiple Regions]")
                    elif 'box' in logical:
                        box = logical['box']
                        intfs.append(f"NoC Placement [Box X:{box.get('x_start')}-{box.get('x_end')} Y:{box.get('y_start')}-{box.get('y_end')}]")
                    else:
                        intfs.append(f"NoC Placement [X:{logical.get('x')} Y:{logical.get('y')}]")
                        
                if c.interfaces and 'noc_networks' in c.interfaces:
                    intfs.append(f"NoC Networks  [{', '.join(c.interfaces['noc_networks'])}]")
                    
            # --- General Interfaces ---
            if c.interfaces:
                if c.interfaces.get('axi_master'): 
                    if is_noc:
                        intfs.append("AXI Master    [Routed via NoC]")
                    else:
                        intfs.append(f"AXI Master    [MstIdx: {axi_masters.index(c.name)}]")
                    
                if 'axi_slave' in c.interfaces:
                    slvs = c.interfaces['axi_slave'] if isinstance(c.interfaces['axi_slave'], list) else [c.interfaces['axi_slave']]
                    for slv in slvs:
                        ports = slv.get('ports', 1)
                        if is_noc:
                            intfs.append(f"AXI Slave     ({ports} ports) [Routed via NoC]" if ports > 1 else "AXI Slave     [Routed via NoC]")
                        else:
                            if ports > 1:
                                idx_list = [i for i, name in enumerate(axi_slaves) if name == c.name]
                                intfs.append(f"AXI Slave     ({ports} ports) [SlvIdx: {idx_list}]")
                            else:
                                intfs.append(f"AXI Slave     [SlvIdx: {axi_slaves.index(c.name)}]")
                                
                if 'llc_port' in c.interfaces:
                    intfs.append("LLC Port      [Direct to Host]")
                if 'regbus_slave' in c.interfaces:
                    intfs.append(f"RegBus Slave  [RegIdx: {all_reg_slaves.index(c.name)}]")
                
            if getattr(c, 'components', None):
                intfs.append(f"APB Bridge    ({len(c.components)} peripherals)")
            if not intfs:
                intfs.append("No Interconnect Interfaces")
            lines.append(f"    - {c.name} ({c.type}):\n" + "\n".join([f"        > {i}" for i in intfs]))
        return "\n".join(lines)

    print("=" * 70)
    print(f"Project      : {soc_config.project.name} - {soc_config.project.description}")
    print(f"Topology     : {soc_config.topology.type.upper()}")
    print(f"Host         : {soc_config.host.name} ({soc_config.host.type})")
    print(f"Components   : {len(internal_comps)} Internal, {len(external_comps)} External")
    print("\n  [Internal Components - Instantiated in Top-Level]")
    print(get_comp_report(internal_comps) if internal_comps else "    (None)")
    print("\n  [External Components - Exported to I/O]")
    print(get_comp_report(external_comps) if external_comps else "    (None)")
    print("=" * 70)
    print("[*] Starting Phase 3: Top-Level Code Generation...\n")

    # =========================================================================
    # 8. PHASE 3: METADATA EXTRACTION & WIRING MATRIX
    # =========================================================================
    # Read SV headers one last time to extract dimensions for the wiring engine
    comp_info = {}
    for c in [soc_config.host] + (soc_config.components if soc_config.components else []):
        info = get_isle_info(f"{soc_config.project.name}_{c.type}", search_paths, None)
        if not info:
            info = get_isle_info(c.type, search_paths, exclude_dir)
        comp_info[c.name] = info if info else {}
        if info and "dependencies" in info:
            for dep_name, dep_dict in info["dependencies"].items():
                project_dependencies.setdefault(dep_name, {})
                project_dependencies[dep_name].update(dep_dict)

    # Infer implicit interrupts using extracted SV headers
    infer_interrupts(soc_config, comp_info)

    # Build the massive dictionary that maps every component port to a Top-Level wire
    wiring_matrix = build_connection_matrix(soc_config, comp_info)

    # Extract all compilation macros requested by the components
    global_defines = set()
    for c in [soc_config.host] + (soc_config.components if soc_config.components else []):
        if getattr(c, 'defines', None):
            global_defines.update(c.defines)

    # =========================================================================
    # 9. MAKO TEMPLATE RENDERING
    # =========================================================================
    # Prepare the dictionary of arguments to pass into the Mako templates
    template_kwargs = {
        "config": soc_config,
        "project_name": soc_config.project.name,
        "sys_ctrl": soc_config.system_controller.model_dump(exclude_none=True) if soc_config.system_controller else {},
        "wiring_matrix": wiring_matrix,
        "domains": [d.model_dump(exclude_none=True) for d in soc_config.clock_tree.domains],
        "components": [c.model_dump(exclude_none=True) for c in soc_config.components] if soc_config.components else [],
        "comp_info": comp_info,
        "global_defines": sorted(list(global_defines)),
        "original_isle_types": original_isle_types,
        "fmt_dom": fmt_dom,
        "fmt_reg": fmt_reg,
        "fmt_rst": fmt_rst,
        "camel_case": camel_case,
        "is_external": is_external,
        "generated_module_files": sorted(generated_module_files),
        "require_file": require_file_helper,
        "require_bender": require_bender_helper,
        "rel_hw_dir": os.path.relpath(hw_dir, bender_dir).replace('\\', '/'),
        "rel_manifest_path": os.path.relpath(bender_manifest_path, Path.cwd()).replace('\\', '/'),
        "rel_outdir_path": os.path.relpath(outdir_path, Path.cwd()).replace('\\', '/'),
        "rel_tb_dir": os.path.relpath(tb_dir, bender_dir).replace('\\', '/')
    }

    # Determine which templates to render based on the topology
    if soc_config.topology.type == "crossbar":
        templates_to_render = {
            "reg/soc_regs_regtool.hjson.mako": reg_dir / f"{soc_config.project.name}_regs.hjson",
            "hw/crossbar_soc_pkg.sv.mako": hw_dir / f"{soc_config.project.name}_soc_pkg.sv",
            "hw/crossbar_soc_top.sv.mako": hw_dir / f"{soc_config.project.name}.sv",
            "hw/infrastructure/soc_rstgen.sv.mako": hw_dir / f"{soc_config.project.name}_rstgen.sv",
            "sw/soc_map.h.mako": sw_dir / f"{soc_config.project.name}_map.h",
            "doc/crossbar_map.csv.mako": doc_dir / f"{soc_config.project.name}_map.csv",
            "Makefile.hw.mako": outdir_path / "Makefile.hw",
            "Makefile.vsim.mako": outdir_path / "Makefile.vsim",
            "tb/tb_soc.sv.mako": tb_dir / f"tb_{soc_config.project.name}.sv"
        }
    else:
        templates_to_render = {
            "hw/noc_soc_pkg.sv.mako": hw_dir / f"{soc_config.project.name}_soc_pkg.sv",
            "hw/noc_soc_top.sv.mako": hw_dir / f"{soc_config.project.name}.sv",
            "hw/tiles/dummy_tile.sv.mako": hw_dir / f"{soc_config.project.name}_dummy_tile.sv",
            "hw/infrastructure/soc_rstgen.sv.mako": hw_dir / f"{soc_config.project.name}_rstgen.sv",
            "reg/soc_regs_regtool.hjson.mako": reg_dir / f"{soc_config.project.name}_regs.hjson",
            "sw/soc_map.h.mako": sw_dir / f"{soc_config.project.name}_map.h",
            "cfg/floogen_cfg.yml.mako": cfg_dir / f"{soc_config.project.name}_floogen.yml",
            "doc/noc_map.csv.mako": doc_dir / f"{soc_config.project.name}_noc_map.csv",
            "Makefile.hw.mako": outdir_path / "Makefile.hw",
            "Makefile.vsim.mako": outdir_path / "Makefile.vsim",
            "tb/tb_soc.sv.mako": tb_dir / f"tb_{soc_config.project.name}.sv"
        }

    # 1. RENDER TOP-LEVEL TEMPLATES & EXTRACT PRAGMAS DYNAMICALLY
    for tpl_name, out_file in templates_to_render.items():
        tpl_path = find_file_in_paths(tpl_name, template_paths)
        
        if not tpl_path:
            print(f"[WARNING] Template '{tpl_name}' not found in provided template paths. Skipping.")
            continue
            
        print(f"  -> Rendering {tpl_name} into {out_file.name}")
        try:
            template = Template(filename=str(tpl_path), lookup=template_lookup)
            rendered_code = template.render(**template_kwargs)
            
            rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{soc_config.project.name}_soc_pkg', rendered_code)
            rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{soc_config.project.name}_noc_pkg', rendered_code)

            if out_file.name.endswith('.sv'):
                rendered_code = auto_import_sv_packages(rendered_code)
                
            if "reg2hw_t" in rendered_code and f"import {soc_config.project.name}_reg_pkg::*;" not in rendered_code:
                rendered_code = re.sub(rf'import {soc_config.project.name}_soc_pkg::\*;', 
                                       rf'import {soc_config.project.name}_soc_pkg::*;\n  import {soc_config.project.name}_reg_pkg::*;', 
                                       rendered_code)
            rendered_code = re.sub(rf'(?<!::)\b{soc_config.project.name}_reg2hw_t\b', f'{soc_config.project.name}_reg_pkg::{soc_config.project.name}_reg2hw_t', rendered_code)
            rendered_code = re.sub(rf'(?<!::)\b{soc_config.project.name}_hw2reg_t\b', f'{soc_config.project.name}_reg_pkg::{soc_config.project.name}_hw2reg_t', rendered_code)

            # EXTRACT DYNAMIC PRAGMAS FROM RENDERED CODE
            required_local_files.update(req_pattern.findall(rendered_code))
            for match in dep_pattern.finditer(rendered_code):
                dep_name = match.group(1)
                project_dependencies.setdefault(dep_name, {})
                if match.group(2):
                    project_dependencies[dep_name]['git'] = match.group(2)
                if match.group(3):
                    project_dependencies[dep_name]['rev'] = match.group(3)
                if match.group(4):
                    project_dependencies[dep_name]['version'] = match.group(4)

            rendered_code = rendered_code.replace('\r\n', '\n')
            write_if_changed(out_file, rendered_code)
        except Exception as e:
            print(f"\n[ERROR] Failed to render {tpl_name}:\n{e}")
            sys.exit(1)

    # Process secondary local files required by pragmas
    staged_local_files = set()
    external_local_files = []
    pending_files = sorted(list(required_local_files))
    while pending_files:
        req_file = pending_files.pop(0)
        if req_file in staged_local_files:
            continue
        
        src_path = None
        for cp in component_paths:
            if cp.is_dir():
                try:
                    src_path = next(cp.rglob(req_file))
                    break
                except StopIteration:
                    pass
            elif cp.is_file() and cp.name == req_file:
                src_path = cp
                break
        
        if src_path:
            print(f"  -> Linking dependency {src_path.name} from {src_path.parent}")
            content = src_path.read_text(encoding='utf-8')
            for new_req in req_pattern.findall(content):
                if new_req not in staged_local_files and new_req not in pending_files:
                    pending_files.append(new_req)
                    
            for match in dep_pattern.finditer(content):
                dep_name = match.group(1)
                project_dependencies.setdefault(dep_name, {})
                if match.group(2):
                    project_dependencies[dep_name]['git'] = match.group(2)
                if match.group(3):
                    project_dependencies[dep_name]['rev'] = match.group(3)
                if match.group(4):
                    project_dependencies[dep_name]['version'] = match.group(4)
            
            rel_path = os.path.relpath(src_path, bender_dir).replace('\\', '/')
            if rel_path not in external_local_files:
                external_local_files.append(rel_path)
                
            staged_local_files.add(src_path.name)
        else:
            print(f"[WARNING] Required file '{req_file}' not found in component paths.")
            staged_local_files.add(req_file)

    template_kwargs["external_local_files"] = sorted(external_local_files)

    resolved_dependencies = {}
    for dep_name in sorted(project_dependencies.keys()):
        dep_info = project_dependencies[dep_name]
        git = dep_info.get('git')
        rev = dep_info.get('rev')
        version = dep_info.get('version')
        if not git or (not rev and not version):
            if dep_name in registry_dependencies:
                git = git or registry_dependencies[dep_name].get('git')
                rev = rev or registry_dependencies[dep_name].get('rev')
                version = version or registry_dependencies[dep_name].get('version')
            else:
                print(f"[WARNING] Dependency '{dep_name}' is missing git/rev/version information and is not found in the environment registry.")
        resolved_dependencies[dep_name] = {'git': git, 'rev': rev, 'version': version}
            
    template_kwargs["project_dependencies"] = resolved_dependencies

    # Render Bender.yml.mako as the very last step
    bender_tpl = "Bender.yml.mako"
    bender_path = find_file_in_paths(bender_tpl, template_paths)
    if bender_path:
        print(f"  -> Rendering {bender_tpl} into Bender.yml")
        try:
            template = Template(filename=str(bender_path), lookup=template_lookup)
            rendered_code = template.render(**template_kwargs)
            rendered_code = rendered_code.replace('\r\n', '\n')
            rendered_code = re.sub(r',\s*rev:\s*"None"', '', rendered_code, flags=re.IGNORECASE)
            rendered_code = re.sub(r',\s*version:\s*"None"', '', rendered_code, flags=re.IGNORECASE)
            
            # Ensure floo_noc_pkg is compiled before soc_pkg
            soc_pkg_pattern = r'(\n\s*-\s*[^\n]*_soc_pkg\.sv)'
            noc_pkg_pattern = r'(\n\s*-\s*[^\n]*_noc_pkg\.sv)'
            noc_match = re.search(noc_pkg_pattern, rendered_code)
            if noc_match:
                noc_line = noc_match.group(1)
                rendered_code = rendered_code.replace(noc_line, '')
                rendered_code = re.sub(soc_pkg_pattern, lambda m: noc_line + m.group(1), rendered_code)
                
            out_file = bender_manifest_path
            write_if_changed(out_file, rendered_code)
        except Exception as e:
            print(f"\n[ERROR] Failed to render {bender_tpl}:\n{e}")
            sys.exit(1)
            
    # =========================================================================
    # 11. PHASE 4: NETWORK-ON-CHIP GENERATION (FLOOGEN)
    # =========================================================================
    # Automatically invokes FlooGen to generate the NoC configuration, router
    # instances, and the standard FlooNoC package.
    if soc_config.topology.type == "noc":
        floogen_file = cfg_dir / f"{soc_config.project.name}_floogen.yml"
        if floogen_file.is_file():
            print("=" * 70)
            print("[*] Starting Phase 4: Generating NoC RTL with FlooGen...\n")
            print(f"  -> Running FlooGen on {floogen_file.name}")
            
            import shutil
            floogen_exe = shutil.which("floogen")
            if not floogen_exe:
                venv_floogen = Path(sys.executable).parent / "floogen"
                if venv_floogen.is_file() and os.access(venv_floogen, os.X_OK):
                    floogen_exe = str(venv_floogen)
            
            if floogen_exe:
                cmd = [floogen_exe, "pkg", "-c", str(floogen_file), "--outdir", str(hw_dir)]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    print("  [SUCCESS] FlooNoC RTL and packages generated.")
                except subprocess.CalledProcessError as e:
                    print(f"\n[ERROR] FlooGen failed:\n{e.stderr}\n{e.stdout}")
                    sys.exit(1)
            else:
                print("\n[ERROR] FlooGen executable not found in PATH.")
                print("[HINT] Please install it using: pip install floogen")
                sys.exit(1)

    # =========================================================================
    # 12. PHASE 5: REGISTER RTL GENERATION (REGTOOL)
    # =========================================================================
    # Automatically invokes the OpenTitan regtool to generate the physical 
    # SystemVerilog register block from the rendered HJSON specification.
    if soc_config.system_controller:
        hjson_file = reg_dir / f"{soc_config.project.name}_regs.hjson"
        if hjson_file.is_file():
            print("=" * 70)
            print("[*] Starting Phase 5: Generating Register RTL with regtool...\n")
            
            regtool_path = None
            for p in regtool_paths:
                if p.is_file():
                    regtool_path = p
                    break
            if not regtool_path:
                regtool_path = base_dir / "tools" / "reggen" / "regtool.py"

            if regtool_path.is_file():
                cmd = [
                    sys.executable, 
                    str(regtool_path), 
                    "-r", 
                    "-t", str(hw_dir), 
                    str(hjson_file)
                ]
                print(f"  -> Running regtool on {hjson_file.name}")
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    print("  [SUCCESS] System Controller register RTL generated.")

                    # Generate the C Defines Header for software drivers
                    c_header_file = sw_dir / f"{soc_config.project.name}_regs.h"
                    cmd_c = [
                        sys.executable, 
                        str(regtool_path), 
                        "--cdefines", 
                        "-o", str(c_header_file), 
                        str(hjson_file)
                    ]
                    print("  -> Running regtool to generate C header...")
                    subprocess.run(cmd_c, check=True, capture_output=True, text=True)
                    print(f"  [SUCCESS] System Controller C header generated ({c_header_file.name}).")
                except subprocess.CalledProcessError as e:
                    print(f"\n[ERROR] regtool failed:\n{e.stderr}")
                    if "ModuleNotFoundError" in e.stderr:
                        print("[HINT] A dependency for regtool is missing in your environment.")
                        print("       Run: pip install tabulate hjson mistletoe mako \"setuptools<70.0.0\"")
                    sys.exit(1)
            else:
                print(f"[WARNING] regtool.py not found at {regtool_path}. Skipping register RTL generation.")

    print(f"\n[SUCCESS] Generation complete! Files saved to '{outdir_path.resolve()}'")

if __name__ == "__main__":
    main()
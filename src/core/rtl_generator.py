# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import os
import re
import sys
from pathlib import Path
from mako.template import Template

from core.soc_schema import get_isle_info
from core.wiring import build_connection_matrix
from core.utils import fmt_dom, fmt_reg, fmt_rst, camel_case, is_external, auto_import_sv_packages, write_if_changed

class RTLGenerator:
    """
    Orchestrates the generation of SystemVerilog modules and the final Top-Level architecture
    using the Mako templating engine. Tracks file dependencies, Bender configurations,
    and extracts PeakRDL specifications from the generated hardware.
    """
    def __init__(self, env, soc_config, template_lookup):
        self.env = env
        self.soc_config = soc_config
        self.template_lookup = template_lookup
        
        # Keeps track of the original Isle types before they are wrapped into NoC Tiles.
        # This allows subsequent phases to inspect the original parameters and ports.
        self.original_isle_types = {}
        # Tracks all generated module paths to inject them into the Bender manifest.
        self.generated_module_files = []
        self.required_local_files = set()
        self.project_dependencies = {}
        
        # Regex patterns to extract dependency pragmas directly from SV or Template files.
        # This allows templates to be fully modular and self-declare what they need.
        self.req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
        self.dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')

    def require_file_helper(self, filename):
        """Mako helper passed to templates to inject a local file dependency pragma."""
        self.required_local_files.add(filename)
        return f'// OLLIVANDER: require="{filename}"'
        
    def require_bender_helper(self, name, git=None, rev=None, version=None):
        """Mako helper passed to templates to inject an external Bender IP dependency pragma."""
        self.project_dependencies.setdefault(name, {})
        if git: self.project_dependencies[name]['git'] = git
        if rev: self.project_dependencies[name]['rev'] = rev
        if version: self.project_dependencies[name]['version'] = version
        
        args = []
        if git: args.append(f'git="{git}"')
        if rev: args.append(f'rev="{rev}"')
        if version: args.append(f'version="{version}"')
        arg_str = " ".join(args)
        if arg_str: arg_str = " " + arg_str
        return f'// BENDER: name="{name}"{arg_str}'

    def find_file_in_paths(self, rel_path, paths_list):
        """Recursively finds a file within a list of base directories."""
        rel_path_obj = Path(rel_path)
        for p in paths_list:
            if p.is_file() and p.name == rel_path_obj.name:
                return p
            elif p.is_dir():
                candidate = p / rel_path
                if candidate.is_file():
                    return candidate
        return None

    def generate_dynamic_isles(self):
        """
        Phase 1: Generates intermediate SystemVerilog wrappers for composite blocks 
        (like the APB Subsystem or NoC Universal Tiles).
        
        This is done BEFORE Top-Level generation (and before Phase 2 validation) so that 
        the newly generated SV files can be parsed to extract their exact port signatures 
        and parameters, enforcing the "Hardware-First" philosophy.
        """
        hw_dir = self.env.outdir_path / self.env.hw_sub
        
        if self.soc_config.topology.type == "noc":
            all_comps_for_type_tracking = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
            for c in all_comps_for_type_tracking:
                if c.type.endswith('_isle') or c.type.endswith('_subtile'):
                    self.original_isle_types[c.name] = c.type

        if self.soc_config.topology.type == "crossbar":
            all_comps = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
            for c in all_comps:
                if c.type == "apb_subsystem_isle":
                    apb_peripherals = []
                    if c.components:
                        for idx, p in enumerate(c.components):
                            # Auto-inject known interrupts for standard APB peripherals
                            # so the user doesn't have to explicitly define them in the YAML,
                            # drastically reducing boilerplate for well-known IP blocks.
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
                    
                    tpl_path = self.find_file_in_paths("hw/isles/apb_subsystem_isle.sv.mako", self.env.template_paths)
                    if not tpl_path:
                        print("\n[ERROR] APB subsystem template 'apb_subsystem_isle.sv.mako' not found.")
                        sys.exit(1)
                    out_file = hw_dir / f"{self.soc_config.project.name}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_name)
                    print(f"  -> Rendering Isle {tpl_path.name} into {out_file.name}")
                    try:
                        template = Template(filename=str(tpl_path), lookup=self.template_lookup)
                        rendered_code = template.render(apb_peripherals=apb_peripherals, c_type=c.type, p_name=self.soc_config.project.name, comp=c, config=self.soc_config, require_file=self.require_file_helper, require_bender=self.require_bender_helper)
                        self.required_local_files.update(self.req_pattern.findall(rendered_code))
                        
                        # Replace placeholder package names with the project-specific ones.
                        rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.name}_soc_pkg', rendered_code)
                        rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{self.soc_config.project.name}_noc_pkg', rendered_code)
                        if out_file.suffix == '.sv':
                            rendered_code = auto_import_sv_packages(rendered_code)
                        rendered_code = rendered_code.replace('\r\n', '\n')
                        write_if_changed(out_file, rendered_code)
                    except Exception as e:
                        print(f"\n[ERROR] Failed to render {tpl_path.name}:\n{e}")
                        sys.exit(1)
                else:
                    # For all other components in a Crossbar topology, simply find the source file
                    # and stage it to the output directory, renaming the module namespace.
                    existing_isle = None
                    for cp in self.env.component_paths:
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
                        out_file = hw_dir / f"{self.soc_config.project.name}_{c.type}.sv"
                        rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                        if rel_name not in self.generated_module_files:
                            self.generated_module_files.append(rel_name)
                        try:
                            content = existing_isle.read_text(encoding='utf-8')
                            self.required_local_files.update(self.req_pattern.findall(content))
                            content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.name}_soc_pkg', content)
                            content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{self.soc_config.project.name}_noc_pkg', content)
                            content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {self.soc_config.project.name}_{c.type}', content)
                            content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {self.soc_config.project.name}_{c.type}', content)
                            write_if_changed(out_file, content)
                        except Exception as e:
                            print(f"\n[ERROR] Failed to stage {existing_isle.name}:\n{e}")
                            sys.exit(1)
        elif self.soc_config.topology.type == "noc":
            tpl_path = self.find_file_in_paths("hw/tiles/universal_tile.sv.mako", self.env.template_paths)
            if not tpl_path:
                print("\n[ERROR] Universal tile template 'universal_tile.sv.mako' not found.")
                sys.exit(1)
                
            all_comps = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
            for c in all_comps:
                if is_external(c):
                    continue
                if c.type.endswith('_tile'):
                    # If the component is already a fully formed Tile, just stage it.
                    existing_tile = None
                    for cp in self.env.component_paths:
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
                        out_file = hw_dir / f"{self.soc_config.project.name}_{c.type}.sv"
                        rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                        if rel_name not in self.generated_module_files:
                            self.generated_module_files.append(rel_name)
                        try:
                            content = existing_tile.read_text(encoding='utf-8')
                            self.required_local_files.update(self.req_pattern.findall(content))
                            content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.name}_soc_pkg', content)
                            content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{self.soc_config.project.name}_noc_pkg', content)
                            content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {self.soc_config.project.name}_{c.type}', content)
                            content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {self.soc_config.project.name}_{c.type}', content)
                            write_if_changed(out_file, content)
                        except Exception as e:
                            print(f"\n[ERROR] Failed to stage {existing_tile.name}:\n{e}")
                            sys.exit(1)
                        continue
                    else:
                        print(f"\n[ERROR] Component '{c.name}' requests '{c.type}', but no '{c.type}.sv' was found in component paths.")
                        sys.exit(1)
                        
                elif c.type.endswith('_isle') or c.type.endswith('_subtile'):
                    # If the component is an Isle, it must be wrapped inside a Universal Tile
                    # to be able to connect to the NoC routers. This auto-conversion provides
                    # topology abstraction: the same Isle can be used in a Crossbar or a NoC 
                    # without any modifications to the IP wrapper itself.
                    existing_isle = None
                    for cp in self.env.component_paths:
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
                    
                    # 1. Stage the underlying Isle to the output directory.
                    isle_out_file = hw_dir / f"{self.soc_config.project.name}_{existing_isle.name}"
                    rel_isle_name = os.path.relpath(isle_out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_isle_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_isle_name)
                    try:
                        content = existing_isle.read_text(encoding='utf-8')
                        self.required_local_files.update(self.req_pattern.findall(content))
                        for match in self.dep_pattern.finditer(content):
                            dep_name = match.group(1)
                            self.project_dependencies.setdefault(dep_name, {})
                            if match.group(2): self.project_dependencies[dep_name]['git'] = match.group(2)
                            if match.group(3): self.project_dependencies[dep_name]['rev'] = match.group(3)
                            if match.group(4): self.project_dependencies[dep_name]['version'] = match.group(4)
                        
                        content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.name}_soc_pkg', content)
                        content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{self.soc_config.project.name}_noc_pkg', content)
                        content = re.sub(rf'\bmodule\s+{isle_type}\b', f'module {self.soc_config.project.name}_{isle_type}', content)
                        content = re.sub(rf'\bendmodule\s*:\s*{isle_type}\b', f'endmodule : {self.soc_config.project.name}_{isle_type}', content)
                        write_if_changed(isle_out_file, content)
                    except Exception as e:
                        print(f"\n[WARNING] Failed to stage {existing_isle.name}:\n{e}")

                    # Update component type to the generated tile type so subsequent phases use the wrapper.
                    c.type = tile_type
                    
                    # 2. Render the Universal Tile wrapper for this component.
                    out_file = hw_dir / f"{self.soc_config.project.name}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_name)
                    print(f"  -> Rendering Tile {tpl_path.name} into {out_file.name}")
                    try:
                        template = Template(filename=str(tpl_path), lookup=self.template_lookup)
                        rendered_code = template.render(comp=c, config=self.soc_config, search_paths=self.env.search_paths, original_type=isle_type, require_file=self.require_file_helper, require_bender=self.require_bender_helper)
                        self.required_local_files.update(self.req_pattern.findall(rendered_code))
                        if out_file.suffix == '.sv':
                            rendered_code = auto_import_sv_packages(rendered_code)
                            
                        # Post-processing to fix up package scopes for register and NoC AXI types.
                        if "reg2hw_t" in rendered_code and f"import {self.soc_config.project.name}_reg_pkg::*;" not in rendered_code:
                            rendered_code = re.sub(rf'import {self.soc_config.project.name}_soc_pkg::\*;', 
                                                   rf'import {self.soc_config.project.name}_soc_pkg::*;\n  import {self.soc_config.project.name}_reg_pkg::*;', 
                                                   rendered_code)
                        rendered_code = re.sub(rf'(?<!::)\b{self.soc_config.project.name}_reg2hw_t\b', f'{self.soc_config.project.name}_reg_pkg::{self.soc_config.project.name}_reg2hw_t', rendered_code)
                        rendered_code = re.sub(rf'(?<!::)\b{self.soc_config.project.name}_hw2reg_t\b', f'{self.soc_config.project.name}_reg_pkg::{self.soc_config.project.name}_hw2reg_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_req_t\b', f'{self.soc_config.project.name}_soc_pkg::soc_axi_req_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_rsp_t\b', f'{self.soc_config.project.name}_soc_pkg::soc_axi_resp_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_([a-z]+)_chan_t\b', rf'{self.soc_config.project.name}_soc_pkg::soc_axi_\1_chan_t', rendered_code)
                                                   
                        rendered_code = rendered_code.replace('\r\n', '\n')
                        write_if_changed(out_file, rendered_code)
                    except Exception as e:
                        print(f"\n[ERROR] Failed to render {tpl_path.name}:\n{e}")
                        sys.exit(1)
                else:
                    print(f"\n[ERROR] Component '{c.name}' has invalid type '{c.type}'. In NoC topology, components must be either '*_tile' or '*_isle'.")
                    sys.exit(1)

    def extract_wiring_metadata(self):
        """
        Phase 3: Prepares all the metadata needed for Top-Level wiring, including
        connection matrices (which implicitly resolve interrupts) and global 
        definitions. This reads the SV headers from the newly generated/staged 
        files in the output directory.
        """
        comp_info = {}
        for c in [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else []):
            info = get_isle_info(f"{self.soc_config.project.name}_{c.type}", self.env.search_paths, None)
            if not info:
                info = get_isle_info(c.type, self.env.search_paths, self.env.exclude_dir)
            if not info:
                info = {}
            comp_info[c.name] = info

            # Check for PEAKRDL pragma in the SystemVerilog source.
            # Example: // PEAKRDL: source="my_ip.rdl" map="my_map"
            # This encapsulates register definitions within the specific IP wrapper,
            # handling cases where a single Bender repository provides multiple distinct IPs.
            sv_name = f"{self.soc_config.project.name}_{c.type}.sv"
            sv_path = self.find_file_in_paths(sv_name, [self.env.outdir_path / self.env.hw_sub])
            if not sv_path:
                sv_path = self.find_file_in_paths(f"{c.type}.sv", self.env.component_paths)
                
            if sv_path:
                try:
                    content = sv_path.read_text(encoding='utf-8', errors='ignore')
                    peakrdl_match = re.search(r'(?://|##)\s*PEAKRDL:\s*source="([^"]+)"(?:.*?map="([^"]+)")?', content)
                    if peakrdl_match:
                        info["rdl_file"] = Path(peakrdl_match.group(1)).name
                        if peakrdl_match.group(2):
                            info["rdl_map"] = peakrdl_match.group(2)
                except Exception:
                    pass

            if "dependencies" in info:
                for dep_name, dep_dict in info["dependencies"].items():
                    self.project_dependencies.setdefault(dep_name, {})
                    self.project_dependencies[dep_name].update(dep_dict)

        wiring_matrix = build_connection_matrix(self.soc_config, comp_info)

        global_defines = set()
        for c in [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else []):
            if getattr(c, 'defines', None):
                global_defines.update(c.defines)

        return comp_info, wiring_matrix, global_defines

    def render_top_level(self, comp_info, wiring_matrix, global_defines):
        """
        Phase 3 (cont'd): The main generation loop where all Top-Level components,
        packages, memory maps, and the final Bender.yml manifest are rendered.
        """
        hw_dir = self.env.outdir_path / self.env.hw_sub
        sw_dir = self.env.outdir_path / self.env.sw_sub
        doc_dir = self.env.outdir_path / self.env.doc_sub
        cfg_dir = self.env.outdir_path / self.env.cfg_sub
        reg_dir = self.env.outdir_path / self.env.reg_sub
        tb_dir = self.env.outdir_path / self.env.tb_sub
        
        template_kwargs = {
            "config": self.soc_config,
            "project_name": self.soc_config.project.name,
            "sys_ctrl": self.soc_config.system_controller.model_dump(exclude_none=True) if self.soc_config.system_controller else {},
            "wiring_matrix": wiring_matrix,
            "domains": [d.model_dump(exclude_none=True) for d in self.soc_config.clock_tree.domains],
            "components": [c.model_dump(exclude_none=True) for c in self.soc_config.components] if self.soc_config.components else [],
            "comp_info": comp_info,
            "global_defines": sorted(list(global_defines)),
            "env_config": {"dependencies": self.env.registry_dependencies},
            "original_isle_types": self.original_isle_types,
            "fmt_dom": fmt_dom,
            "fmt_reg": fmt_reg,
            "fmt_rst": fmt_rst,
            "camel_case": camel_case,
            "is_external": is_external,
            "generated_module_files": sorted(self.generated_module_files),
            "require_file": self.require_file_helper,
            "require_bender": self.require_bender_helper,
            "rel_hw_dir": os.path.relpath(hw_dir, self.env.bender_dir).replace('\\', '/'),
            "rel_manifest_path": os.path.relpath(self.env.bender_manifest_path, Path.cwd()).replace('\\', '/'),
            "rel_outdir_path": os.path.relpath(self.env.outdir_path, Path.cwd()).replace('\\', '/'),
            "rel_tb_dir": os.path.relpath(tb_dir, self.env.bender_dir).replace('\\', '/'),
            "rel_hw_from_tb": os.path.relpath(hw_dir, tb_dir).replace('\\', '/'),
            "rel_ollivander_dir": os.path.relpath(self.env.base_dir, Path.cwd()).replace('\\', '/')
        }

        if self.soc_config.topology.type == "crossbar":
            templates_to_render = {
                "reg/soc_regs.rdl.mako": reg_dir / f"{self.soc_config.project.name}_regs.rdl",
                "reg/soc_memory_map.rdl.mako": reg_dir / f"{self.soc_config.project.name}_memory_map.rdl",
                "hw/crossbar_soc_pkg.sv.mako": hw_dir / f"{self.soc_config.project.name}_soc_pkg.sv",
                "hw/crossbar_soc_top.sv.mako": hw_dir / f"{self.soc_config.project.name}.sv",
                "hw/infrastructure/soc_rstgen.sv.mako": hw_dir / f"{self.soc_config.project.name}_rstgen.sv",
                "sw/soc_map.h.mako": sw_dir / f"{self.soc_config.project.name}_map.h",
                "doc/crossbar_map.csv.mako": doc_dir / f"{self.soc_config.project.name}_map.csv",
                "Makefile.vsim.mako": self.env.outdir_path / "Makefile.vsim",
                "tb/tb_soc.sv.mako": tb_dir / f"tb_{self.soc_config.project.name}.sv"
            }
        else:
            templates_to_render = {
                "hw/noc_soc_pkg.sv.mako": hw_dir / f"{self.soc_config.project.name}_soc_pkg.sv",
                "hw/noc_soc_top.sv.mako": hw_dir / f"{self.soc_config.project.name}.sv",
                "hw/tiles/dummy_tile.sv.mako": hw_dir / f"{self.soc_config.project.name}_dummy_tile.sv",
                "hw/infrastructure/soc_rstgen.sv.mako": hw_dir / f"{self.soc_config.project.name}_rstgen.sv",
                "reg/soc_regs.rdl.mako": reg_dir / f"{self.soc_config.project.name}_regs.rdl",
                "reg/soc_memory_map.rdl.mako": reg_dir / f"{self.soc_config.project.name}_memory_map.rdl",
                "sw/soc_map.h.mako": sw_dir / f"{self.soc_config.project.name}_map.h",
                "cfg/floogen_cfg.yml.mako": cfg_dir / f"{self.soc_config.project.name}_floogen.yml",
                "doc/noc_map.csv.mako": doc_dir / f"{self.soc_config.project.name}_noc_map.csv",
                "Makefile.vsim.mako": self.env.outdir_path / "Makefile.vsim",
                "tb/tb_soc.sv.mako": tb_dir / f"tb_{self.soc_config.project.name}.sv"
            }

        # Add Software templates dynamically if a software stack is configured
        if getattr(self.soc_config, "software_stack", None):
            templates_to_render["sw/linker.ld.mako"] = sw_dir / "linker.ld"
            templates_to_render["sw/Makefile.sw.mako"] = sw_dir / "Makefile"
            if self.soc_config.software_stack.get("test_app", {}).get("auto_generate_c", False):
                templates_to_render["sw/main.c.mako"] = sw_dir / "main.c"

        for tpl_name, out_file in templates_to_render.items():
            tpl_path = self.find_file_in_paths(tpl_name, self.env.template_paths)
            if not tpl_path:
                print(f"[WARNING] Template '{tpl_name}' not found in provided template paths. Skipping.")
                continue
                
            print(f"  -> Rendering {tpl_name} into {out_file.name}")
            try:
                template = Template(filename=str(tpl_path), lookup=self.template_lookup)
                rendered_code = template.render(**template_kwargs)
                
                # Final namespace substitution: replace placeholder package names with
                # project-specific ones to prevent collisions in multi-SoC environments.
                rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.name}_soc_pkg', rendered_code)
                rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'floo_{self.soc_config.project.name}_noc_pkg', rendered_code)

                if out_file.name.endswith('.sv'):
                    rendered_code = auto_import_sv_packages(rendered_code)
                    
                if "hwif_in" in rendered_code and f"import {self.soc_config.project.name}_sys_regs_pkg::*;" not in rendered_code:
                    rendered_code = re.sub(rf'import {self.soc_config.project.name}_soc_pkg::\*;', 
                                           rf'import {self.soc_config.project.name}_soc_pkg::*;\n  import {self.soc_config.project.name}_sys_regs_pkg::*;', 
                                           rendered_code)

                # Extract dynamic pragmas from the fully rendered code.
                self.required_local_files.update(self.req_pattern.findall(rendered_code))
                for match in self.dep_pattern.finditer(rendered_code):
                    dep_name = match.group(1)
                    self.project_dependencies.setdefault(dep_name, {})
                    if match.group(2): self.project_dependencies[dep_name]['git'] = match.group(2)
                    if match.group(3): self.project_dependencies[dep_name]['rev'] = match.group(3)
                    if match.group(4): self.project_dependencies[dep_name]['version'] = match.group(4)

                rendered_code = rendered_code.replace('\r\n', '\n')
                write_if_changed(out_file, rendered_code)
            except Exception as e:
                print(f"\n[ERROR] Failed to render {tpl_name}:\n{e}")
                sys.exit(1)

        # Iteratively resolve all local files (e.g., infrastructure primitives) that 
        # need to be copied into the output hierarchy based on 'OLLIVANDER: require' pragmas.
        # This recursively scans dependencies until the closure is complete.
        staged_local_files = set()
        external_local_files = []
        pending_files = sorted(list(self.required_local_files))
        while pending_files:
            req_file = pending_files.pop(0)
            if req_file in staged_local_files:
                continue
            
            src_path = None
            for cp in self.env.component_paths:
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
                # Recursively find more required files inside the staged dependency.
                for new_req in self.req_pattern.findall(content):
                    if new_req not in staged_local_files and new_req not in pending_files:
                        pending_files.append(new_req)
                        
                for match in self.dep_pattern.finditer(content):
                    dep_name = match.group(1)
                    self.project_dependencies.setdefault(dep_name, {})
                    if match.group(2): self.project_dependencies[dep_name]['git'] = match.group(2)
                    if match.group(3): self.project_dependencies[dep_name]['rev'] = match.group(3)
                    if match.group(4): self.project_dependencies[dep_name]['version'] = match.group(4)
                
                rel_path = os.path.relpath(src_path, self.env.bender_dir).replace('\\', '/')
                if rel_path not in external_local_files:
                    external_local_files.append(rel_path)
                    
                staged_local_files.add(src_path.name)
            else:
                print(f"[WARNING] Required file '{req_file}' not found in component paths.")
                staged_local_files.add(req_file)

        template_kwargs["external_local_files"] = sorted(external_local_files)

        # Resolve all collected Bender dependencies against the environment registry.
        # If a dependency was declared in a pragma without git/rev/version details,
        # we look it up in the central registry (e.g., ollivander_config.yaml).
        resolved_dependencies = {}
        for dep_name in sorted(self.project_dependencies.keys()):
            dep_info = self.project_dependencies[dep_name]
            git = dep_info.get('git')
            rev = dep_info.get('rev')
            version = dep_info.get('version')
            
            if not git or (not rev and not version):
                if dep_name in self.env.registry_dependencies:
                    git = git or self.env.registry_dependencies[dep_name].get('git')
                    rev = rev or self.env.registry_dependencies[dep_name].get('rev')
                    version = version or self.env.registry_dependencies[dep_name].get('version')
                else:
                    print(f"[WARNING] Dependency '{dep_name}' is missing git/rev/version information and is not found in the environment registry.")
            resolved_dependencies[dep_name] = {'git': git, 'rev': rev, 'version': version}
                
        template_kwargs["project_dependencies"] = resolved_dependencies

        # Render Bender.yml as the very last step, now that all dependencies are known
        # and the exact required files have been fully resolved.
        bender_tpl = "Bender.yml.mako"
        bender_path = self.find_file_in_paths(bender_tpl, self.env.template_paths)
        if bender_path:
            print(f"  -> Rendering {bender_tpl} into Bender.yml")
            try:
                template = Template(filename=str(bender_path), lookup=self.template_lookup)
                rendered_code = template.render(**template_kwargs)
                rendered_code = rendered_code.replace('\r\n', '\n')
                # Clean up None values from the YAML output.
                rendered_code = re.sub(r',\s*rev:\s*"None"', '', rendered_code, flags=re.IGNORECASE)
                rendered_code = re.sub(r',\s*version:\s*"None"', '', rendered_code, flags=re.IGNORECASE)
                
                # Ensure floo_noc_pkg is compiled before soc_pkg for NoC topologies.
                soc_pkg_pattern = r'(\n\s*-\s*[^\n]*_soc_pkg\.sv)'
                noc_pkg_pattern = r'(\n\s*-\s*[^\n]*_noc_pkg\.sv)'
                noc_match = re.search(noc_pkg_pattern, rendered_code)
                if noc_match:
                    noc_line = noc_match.group(1)
                    rendered_code = rendered_code.replace(noc_line, '')
                    rendered_code = re.sub(soc_pkg_pattern, lambda m: noc_line + m.group(1), rendered_code)
                    
                out_file = self.env.bender_manifest_path
                write_if_changed(out_file, rendered_code)
            except Exception as e:
                print(f"\n[ERROR] Failed to render {bender_tpl}:\n{e}")
                sys.exit(1)
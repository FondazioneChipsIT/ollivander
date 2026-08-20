# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import os
import re
import sys
import yaml
from pathlib import Path
from mako.template import Template

import core.interfaces
from core.interfaces import get_interface_ports
from core.sv_parser import get_isle_info
from core.wiring import build_connection_matrix
from core.utils import fmt_dom, fmt_reg, fmt_rst, camel_case, is_external, auto_import_sv_packages, write_if_changed, strip_comments, simplify_port_ranges, get_ollivander_version, get_ollivander_git_hash
from core.sv_ir import SVArchitectureIR, PortConnection
from core.rtl_helpers import get_base_name, extract_dims, get_suffixes, norm_type, sv_dependency_sort, PORT_PATTERN
from core.rtl_ir_builder import build_crossbar_ir, build_noc_ir, get_type_param_fill

# The de-typing pass of the isle staging (_detype_staged_isle) does its header
# surgery on pyslang's syntax tree; without pyslang the pass degrades to a no-op
# and the typed isles simply stay out of the hierarchical block set, mirroring
# sv_parser's own optional-import discipline.
try:
    import pyslang
    HAS_PYSLANG = True
except ImportError:
    HAS_PYSLANG = False
from core.macro_boundary import resolve_noc_id_widths, resolve_noc_user_widths


class RTLGenerator:
    """
    Orchestrates the generation of SystemVerilog modules and the final Top-Level architecture
    using the Mako templating engine. Tracks file dependencies, Bender configurations,
    and extracts PeakRDL specifications from the generated hardware.
    """
    def __init__(self, env, soc_config, template_lookup):
        self.gen_version = get_ollivander_version()
        self.git_hash = get_ollivander_git_hash(env.base_dir)
        self.env = env
        self.soc_config = soc_config
        self.template_lookup = template_lookup
        
        # Keeps track of the original Isle types before they are wrapped into NoC Tiles.
        # This allows subsequent phases to inspect the original parameters and ports.
        self.original_isle_types = {}
        # Tracks all generated module paths to inject them into the Bender manifest.
        self.generated_module_files = []
        # Per-isle types packages emitted by the de-typing pass of the isle staging
        # (see _detype_staged_isle): listed separately because they must compile
        # BEFORE the component wrappers, while generated_module_files is emitted
        # alphabetically - which would put '<isle>.sv' ahead of '<isle>_types_pkg.sv'.
        self.generated_types_pkg_files = []
        # Per staged module, the parameter names the de-typing removed. Consumed by
        # the IR builders through comp_info: an override for one of these names -
        # arch_optimizer injects four reg types into the HOST's custom parameters,
        # outside the supported_params loop - must be dropped, or it dangles on a
        # header that no longer declares the parameter.
        self._detyped_params = {}
        # The module names this project's own cfg/<top>.vlt declares as hierarchical
        # blocks, captured by generate_verilator_config. A macro export re-emits them
        # as '// OLLIVANDER: hier_block="..."' pragmas so a PARENT project knows,
        # by declaration rather than inference, which of the macro's internals are
        # block-eligible - the single source of truth being the child's own .vlt.
        self.hier_block_modules = []
        # And the parent-side view: per component, the hier_block declarations its
        # staged source carries (collected in both staging branches). A component
        # with a non-empty list is an Ollivander macro with block-eligible internals:
        # the uniform rule promotes the DECLARED modules into this project's .vlt and
        # never makes the macro's own wrapper (or its tile) a block itself - blocks
        # inside an enclosing block would nest, which is territory Verilator's
        # hierarchical mode has not been probed on.
        self.hier_pragma_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*hier_block="([^"]+)"')
        self.macro_hier_blocks = {}
        self.required_local_files = set()
        # Simulation-only requirements, kept apart from the RTL ones: they belong to
        # the manifest's 'simulation' target and never to a macro's export list.
        self.tb_required_local_files = set()
        self.project_dependencies = {}
        
        # Compute top_level_module_name once to be used across all generations
        self.top_level_module_name = self.soc_config.project.top_level_module_name

        # Regex patterns to extract dependency pragmas directly from SV or Template files.
        # This allows templates to be fully modular and self-declare what they need.
        self.req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
        self.dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')
        # Compilation macros imported from component sources via '// DEFINE: name="..."' pragmas.
        # A macro wrapper exports the defines its internals were generated with, and the consuming
        # project must compile with them: they are collected here wherever component sources are
        # scanned, and joined with the project's own 'defines' in extract_wiring_metadata.
        self.def_pattern = re.compile(r'(?://|##)\s*DEFINE:\s*name="([^"]+)"')
        self.imported_defines = set()
        # Components that declare, via '// OLLIVANDER: exclude_hier_block="reason"', that they
        # carry a construct Verilator refuses inside a '--lib-create' child library. Collected
        # exactly like the defines above - from the parsed component AND from the staged isle
        # source, because the tile wrapper rendered around an isle does not carry its pragmas -
        # and consumed by generate_verilator_config. Maps component name to the declared reason.
        self.hier_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*exclude_hier_block="([^"]*)"')
        self.hier_block_marks = {}

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
        
        return f'// BENDER: name="{name}"'

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

    def _detype_staged_isle(self, content, comp, module_name, hw_dir):
        """Replace a staged isle's `parameter type` header entries with a generated
        per-isle types package (the hier-block admission work, wip 5.1).

        A wrapper whose header carries `parameter type` cannot be a Verilator
        hierarchical block (the hier-parameters wrapper cannot serialize a type),
        and the parameters exist only because the shared component cannot name the
        project's SoC package. The STAGED copy is project-specific by construction,
        so it can: this pass emits `<module>_types_pkg.sv` with one typedef per
        former parameter - same names, resolved through the same role-based helper
        the instantiation site uses (get_type_param_fill) - deletes the parameters
        from the header and injects the package import. Ports and body keep the
        very same identifiers, now supplied by the import, and the instantiation
        site stops emitting the overrides automatically: extract_wiring_metadata
        parses the transformed copy, so the names simply leave supported_params.

        The header surgery is done on pyslang's syntax tree, not with regexes: the
        parameter list exposes declarations and separator commas interleaved, each
        carrying its exact source text (trivia included), so the survivors are
        reassembled verbatim and the spliced spans come from real token offsets.
        The first, regex-based version of this pass produced three distinct
        defects in one evening - a swallowed newline, catastrophic backtracking
        and a lazy capture stopping after one character - which is exactly the
        class of fragility a parser removes. Unresolved `include directives are
        harmless here: the surgery is purely syntactic and the components carry
        no preprocessor conditionals in their headers.

        On any structural surprise - pyslang unavailable, no module of the
        expected name, no type parameters - the content is returned untouched:
        the staged copy then behaves exactly as before this pass existed, and the
        isle merely stays out of the hierarchical block set as it always was.
        """
        if not HAS_PYSLANG:
            print("  [INFO] pyslang unavailable: staged isles keep their type parameters"
                  " (not hier-block eligible)")
            return content
        tree = pyslang.syntax.SyntaxTree.fromText(content)
        root = tree.root
        mod = None
        if str(root.kind) == "SyntaxKind.ModuleDeclaration":
            mod = root
        elif hasattr(root, "members"):
            for m in root.members:
                if (str(m.kind) == "SyntaxKind.ModuleDeclaration"
                        and m.header.name.valueText == module_name):
                    mod = m
                    break
        if (mod is None or mod.header.name.valueText != module_name
                or mod.header.parameters is None):
            return content

        plist = mod.header.parameters
        entries = []  # (former parameter name, its declared default)
        kept = []     # surviving declaration nodes, in order, commas dropped
        for it in plist.declarations:
            kind = str(getattr(it, "kind", ""))
            if kind == "SyntaxKind.TypeParameterDeclaration":
                # One declaration may carry several declarators
                # (`parameter type a = logic, b = logic`): each becomes a typedef.
                for a in it.declarators:
                    default = str(a.assignment.type).strip() if a.assignment else "logic"
                    entries.append((a.name.valueText, default))
            elif kind != "TokenKind.Comma":
                kept.append(it)
        if not entries:
            return content

        pkg = self.soc_config.project.soc_pkg_name
        pkg_name = f"{module_name}_types_pkg"
        lines = [
            "// Copyright 2026 Fondazione Chips-IT.",
            "// Solderpad Hardware License, Version 0.51, see LICENSE for details.",
            "// SPDX-License-Identifier: SHL-0.51",
            "//",
            f"// Generated by Ollivander v{self.gen_version} ({self.git_hash})",
            "//",
            f"// Types the staged '{module_name}' isle used to receive as `parameter type`",
            "// overrides, resolved here once through the same role-based mapping the",
            "// instantiation site used (rtl_ir_builder.get_type_param_fill). Keeping the",
            "// header free of type parameters is what admits the isle as a Verilator",
            "// hierarchical block; the typedef names are the former parameter names, so",
            "// the isle's ports and body compile unchanged.",
            f"package {pkg_name};",
        ]
        for name, default in entries:
            fill = get_type_param_fill(name, comp, self.soc_config, pkg) or default
            lines.append(f"  typedef {fill} {name};")
        lines.append(f"endpackage : {pkg_name}")
        pkg_file = hw_dir / f"{pkg_name}.sv"
        write_if_changed(pkg_file, "\n".join(lines) + "\n")
        rel_pkg = os.path.relpath(pkg_file, self.env.bender_dir).replace("\\", "/")
        if rel_pkg not in self.generated_types_pkg_files:
            self.generated_types_pkg_files.append(rel_pkg)
        self._detyped_params.setdefault(module_name, set()).update(n for n, _ in entries)

        # Reassemble the survivors verbatim - each node's text carries its own
        # leading trivia, so formatting and comments travel with their owner -
        # with a bare comma between consecutive entries, exactly as the original
        # separator tokens were. Splice by token offsets, params first, then the
        # import after the module name (an earlier offset, untouched by the splice).
        rebuilt = "".join(("," if i else "") + str(d) for i, d in enumerate(kept))
        p_start = plist.openParen.range.end.offset
        p_end = plist.closeParen.range.start.offset
        name_end = mod.header.name.range.end.offset
        content = content[:p_start] + rebuilt + content[p_end:]
        content = (content[:name_end] + f"\n  import {pkg_name}::*;"
                   + content[name_end:])
        print(f"  -> De-typing staged isle '{module_name}': {len(entries)} type parameters"
              f" moved to {pkg_name}")
        return content

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
            # De-typing precondition (see _detype_staged_isle): the type fills are
            # ROLE-based (host / behind the LLC port / plain slave) while the staged
            # copy is shared by every component of the same type, so the pass may
            # only fire when all of them agree on the role. Disagreement is legal
            # SoC description - it just keeps that isle out of the hier-block set,
            # and says so, rather than silently giving one component the other's types.
            roles_by_type = {}
            for c2 in all_comps:
                if is_external(c2):
                    continue
                role = (c2.name == self.soc_config.host.name,
                        'llc_port' in (c2.interfaces or {}))
                roles_by_type.setdefault(c2.type, set()).add(role)
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
                    out_file = hw_dir / f"{self.soc_config.project.module_prefix}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_name)
                    print(f"  -> Rendering Isle {tpl_path.name} into {out_file.name}")
                    try:
                        template = Template(filename=str(tpl_path), lookup=self.template_lookup)
                        rendered_code = template.render(apb_peripherals=apb_peripherals, c_type=c.type, p_name=self.soc_config.project.module_prefix, comp=c, config=self.soc_config, require_file=self.require_file_helper, require_bender=self.require_bender_helper, gen_version=self.gen_version, git_hash=self.git_hash)
                        self.required_local_files.update(self.req_pattern.findall(rendered_code))
                        
                        # Replace placeholder package names with the project-specific ones.
                        rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.soc_pkg_name}', rendered_code)
                        rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'{self.soc_config.project.noc_pkg_name}', rendered_code)
                        if out_file.suffix == '.sv':
                            rendered_code = auto_import_sv_packages(rendered_code)
                        rendered_code = rendered_code.replace('\r\n', '\n')
                        if len(roles_by_type.get(c.type, set())) == 1:
                            rendered_code = self._detype_staged_isle(
                                rendered_code, c,
                                f"{self.soc_config.project.module_prefix}_{c.type}", hw_dir)
                        else:
                            print(f"  [INFO] '{c.type}' instances disagree on role: type"
                                  f" parameters kept, isle not hier-block eligible")
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
                        out_file = hw_dir / f"{self.soc_config.project.module_prefix}_{c.type}.sv"
                        rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                        if rel_name not in self.generated_module_files:
                            self.generated_module_files.append(rel_name)
                        try:
                            content = existing_isle.read_text(encoding='utf-8')
                            self.required_local_files.update(self.req_pattern.findall(content))
                            # A macro wrapper declares its block-eligible internals;
                            # collected here for the .vlt promotion (uniform rule).
                            declared = self.hier_pragma_pattern.findall(content)
                            if declared:
                                # Idempotent: staging and re-render both pass here.
                                cur = self.macro_hier_blocks.setdefault(c.name, [])
                                cur.extend(m for m in declared if m not in cur)
                            content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.soc_pkg_name}', content)
                            content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'{self.soc_config.project.noc_pkg_name}', content)
                            content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {self.soc_config.project.module_prefix}_{c.type}', content)
                            content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {self.soc_config.project.module_prefix}_{c.type}', content)
                            if len(roles_by_type.get(c.type, set())) == 1:
                                content = self._detype_staged_isle(
                                    content, c,
                                    f"{self.soc_config.project.module_prefix}_{c.type}", hw_dir)
                            else:
                                print(f"  [INFO] '{c.type}' instances disagree on role: type"
                                      f" parameters kept, isle not hier-block eligible")
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
                        out_file = hw_dir / f"{self.soc_config.project.module_prefix}_{c.type}.sv"
                        rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                        if rel_name not in self.generated_module_files:
                            self.generated_module_files.append(rel_name)
                        try:
                            content = existing_tile.read_text(encoding='utf-8')
                            self.required_local_files.update(self.req_pattern.findall(content))
                            content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.soc_pkg_name}', content)
                            content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'{self.soc_config.project.noc_pkg_name}', content)
                            content = re.sub(rf'\bmodule\s+{c.type}\b', f'module {self.soc_config.project.module_prefix}_{c.type}', content)
                            content = re.sub(rf'\bendmodule\s*:\s*{c.type}\b', f'endmodule : {self.soc_config.project.module_prefix}_{c.type}', content)
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
                    isle_out_file = hw_dir / f"{self.soc_config.project.module_prefix}_{existing_isle.name}"
                    rel_isle_name = os.path.relpath(isle_out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_isle_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_isle_name)
                    try:
                        peakrdl_pragma = ""
                        content = existing_isle.read_text(encoding='utf-8')
                        self.required_local_files.update(self.req_pattern.findall(content))
                        for match in self.dep_pattern.finditer(content):
                            dep_name = match.group(1)
                            self.project_dependencies.setdefault(dep_name, {})
                            if match.group(2): self.project_dependencies[dep_name]['git'] = match.group(2)
                            if match.group(3): self.project_dependencies[dep_name]['rev'] = match.group(3)
                            if match.group(4): self.project_dependencies[dep_name]['version'] = match.group(4)
                        # The staged isle may be a macro exporting the compilation defines its
                        # internals need; the tile wrapper rendered around it does not carry the
                        # pragmas, so they are collected here, at the only point where the isle
                        # source itself is read.
                        self.imported_defines.update(self.def_pattern.findall(content))
                        # Same reasoning for the hierarchical-block restriction: an exported macro
                        # declares here that something inside it cannot be verilated as a child
                        # library, and the tile built around it inherits that restriction.
                        hier_mark = self.hier_pattern.search(content)
                        if hier_mark:
                            self.hier_block_marks[c.name] = re.sub(
                                r'\s*(?://|##)?\s+', " ", hier_mark.group(1)).strip() or "unspecified"
                        # And the positive declaration: the macro's own block-eligible
                        # internals, promoted into this project's .vlt (uniform rule).
                        declared = self.hier_pragma_pattern.findall(content)
                        if declared:
                            # Idempotent: staging and re-render both pass here.
                            cur = self.macro_hier_blocks.setdefault(c.name, [])
                            cur.extend(m for m in declared if m not in cur)

                        # Extract PEAKRDL pragma to pass to the wrapper
                        peakrdl_match = re.search(r'(?://|##)\s*PEAKRDL:\s*source="([^"]+)"(?:.*?map="([^"]+)")?', content)
                        if peakrdl_match:
                            source = peakrdl_match.group(1)
                            map_name = peakrdl_match.group(2)
                            if map_name:
                                peakrdl_pragma = f'// PEAKRDL: source="{source}" map="{map_name}"'
                            else:
                                peakrdl_pragma = f'// PEAKRDL: source="{source}"'
                        
                        content = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.soc_pkg_name}', content)
                        content = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'{self.soc_config.project.noc_pkg_name}', content)
                        content = re.sub(rf'\bmodule\s+{isle_type}\b', f'module {self.soc_config.project.module_prefix}_{isle_type}', content)
                        content = re.sub(rf'\bendmodule\s*:\s*{isle_type}\b', f'endmodule : {self.soc_config.project.module_prefix}_{isle_type}', content)
                        write_if_changed(isle_out_file, content)
                    except Exception as e:
                        print(f"\n[WARNING] Failed to stage {existing_isle.name}:\n{e}")
                        peakrdl_pragma = ""

                    # Update component type to the generated tile type so subsequent phases use the wrapper.
                    c.type = tile_type
                    
                    # 2. Render the Universal Tile wrapper for this component.
                    out_file = hw_dir / f"{self.soc_config.project.module_prefix}_{c.type}.sv"
                    rel_name = os.path.relpath(out_file, self.env.bender_dir).replace('\\', '/')
                    if rel_name not in self.generated_module_files:
                        self.generated_module_files.append(rel_name)
                    print(f"  -> Rendering Tile {tpl_path.name} into {out_file.name}")
                    try:
                        template = Template(filename=str(tpl_path), lookup=self.template_lookup)
                        rendered_code = template.render(comp=c, config=self.soc_config, search_paths=self.env.search_paths, original_type=isle_type, peakrdl_pragma=peakrdl_pragma, require_file=self.require_file_helper, require_bender=self.require_bender_helper, top_level_module_name=self.top_level_module_name, gen_version=self.gen_version, git_hash=self.git_hash)
                        self.required_local_files.update(self.req_pattern.findall(rendered_code))
                        if out_file.suffix == '.sv':
                            rendered_code = auto_import_sv_packages(rendered_code)
                            
                        # Post-processing to fix up package scopes for register and NoC AXI types.
                        if "reg2hw_t" in rendered_code and f"import {self.soc_config.project.name}_reg_pkg::*;" not in rendered_code:
                            rendered_code = re.sub(rf'import {self.soc_config.project.soc_pkg_name}::\*;', 
                                                   rf'import {self.soc_config.project.soc_pkg_name}::*;\n  import {self.soc_config.project.name}_reg_pkg::*;', 
                                                   rendered_code)
                        rendered_code = re.sub(rf'(?<!::)\b{self.soc_config.project.name}_reg2hw_t\b', f'{self.soc_config.project.name}_reg_pkg::{self.soc_config.project.name}_reg2hw_t', rendered_code)
                        rendered_code = re.sub(rf'(?<!::)\b{self.soc_config.project.name}_hw2reg_t\b', f'{self.soc_config.project.name}_reg_pkg::{self.soc_config.project.name}_hw2reg_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_req_t\b', f'{self.soc_config.project.soc_pkg_name}::soc_axi_req_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_rsp_t\b', f'{self.soc_config.project.soc_pkg_name}::soc_axi_resp_t', rendered_code)
                        rendered_code = re.sub(r'\bfloo_[a-zA-Z0-9_]+_noc_pkg::noc_axi_([a-z]+)_chan_t\b', rf'{self.soc_config.project.soc_pkg_name}::soc_axi_\1_chan_t', rendered_code)
                                                   
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
            info = get_isle_info(f"{self.soc_config.project.module_prefix}_{c.type}", self.env.search_paths, None)
            if not info:
                info = get_isle_info(c.type, self.env.search_paths, self.env.exclude_dir)
            if not info:
                info = {}
            # Names the de-typing pass removed from this module's header: the IR
            # builders drop any custom-parameter override carrying one of them.
            info["detyped_params"] = self._detyped_params.get(
                f"{self.soc_config.project.module_prefix}_{c.type}", set())
            comp_info[c.name] = info

            # Check for PEAKRDL pragma in the SystemVerilog source.
            # Example: // PEAKRDL: source="my_ip.rdl" map="my_map"
            # This encapsulates register definitions within the specific IP wrapper,
            # handling cases where a single Bender repository provides multiple distinct IPs.
            sv_name = f"{self.soc_config.project.module_prefix}_{c.type}.sv"
            sv_path = self.find_file_in_paths(sv_name, [self.env.outdir_path / self.env.hw_sub])
            if not sv_path:
                sv_path = self.find_file_in_paths(f"{c.type}.sv", self.env.component_paths)
                
            if sv_path:
                # A read that fails here used to be swallowed, and the consequence was invisible:
                # without the pragma the component's registers are simply not generated, so the
                # first sign would be a missing register block much later. Report the file instead.
                try:
                    content = sv_path.read_text(encoding='utf-8', errors='ignore')
                    peakrdl_match = re.search(r'(?://|##)\s*PEAKRDL:\s*source="([^"]+)"(?:.*?map="([^"]+)")?', content)
                    if peakrdl_match:
                        info["rdl_file"] = Path(peakrdl_match.group(1)).name
                        if peakrdl_match.group(2):
                            info["rdl_map"] = peakrdl_match.group(2)
                except OSError as e:
                    print(f"  [WARNING] Cannot read '{sv_path}' to look for its PEAKRDL pragma: {e}."
                          f" Any register block {c.name} declares there will not be generated.")

            if "dependencies" in info:
                for dep_name, dep_dict in info["dependencies"].items():
                    self.project_dependencies.setdefault(dep_name, {})
                    self.project_dependencies[dep_name].update(dep_dict)

        # Dynamically adjust sync_domain and host AXI parameters based on physical ports.
        if self.soc_config.topology.type == "crossbar":
            num_sync_slaves = 0
            num_async_slaves = 0
            for c in self.soc_config.components if self.soc_config.components else []:
                if c.interfaces and 'axi_slave' in c.interfaces:
                    slvs = c.interfaces['axi_slave']
                    if isinstance(slvs, dict):
                        slvs = [slvs]
                    for slv in slvs:
                        ports_cnt = slv.get('ports', 1)
                        is_sync = slv.get('sync_domain', False)
                        c_info = comp_info.get(c.name, {})
                        if not is_sync:
                            if c_info and "ports" in c_info:
                                if "async_axi_in_aw_data_i" not in c_info["ports"]:
                                    slv['sync_domain'] = True
                                    is_sync = True
                        if is_sync:
                            num_sync_slaves += ports_cnt
                        else:
                            num_async_slaves += ports_cnt

            if self.soc_config.project.build_mode == "macro" and self.soc_config.project.macro_settings:
                if self.soc_config.project.macro_settings.masters:
                    num_sync_slaves += len(self.soc_config.project.macro_settings.masters)

            if getattr(self.soc_config.host, 'parameters', None) is None:
                self.soc_config.host.parameters = {}
            self.soc_config.host.parameters['AxiNumSlvSync'] = num_sync_slaves
            self.soc_config.host.parameters['AxiNumSlvAsync'] = num_async_slaves

            num_sync_masters = 0
            num_async_masters = 0
            for c in self.soc_config.components if self.soc_config.components else []:
                if c.interfaces and c.interfaces.get('axi_master'):
                    is_sync_mst = True
                    c_info = comp_info.get(c.name, {})
                    if c_info and "ports" in c_info:
                        if "async_axi_out_aw_data_o" in c_info["ports"]:
                            is_sync_mst = False
                    if is_sync_mst:
                        num_sync_masters += 1
                    else:
                        num_async_masters += 1

            if self.soc_config.project.build_mode == "macro" and self.soc_config.project.macro_settings:
                if self.soc_config.project.macro_settings.slaves:
                    num_sync_masters += len(self.soc_config.project.macro_settings.slaves)

            self.soc_config.host.parameters['AxiNumMstSync'] = num_sync_masters
            self.soc_config.host.parameters['AxiNumMstAsync'] = num_async_masters

        core.interfaces.GLOBAL_COMP_INFO.clear()
        core.interfaces.GLOBAL_COMP_INFO.update(comp_info)

        wiring_matrix = build_connection_matrix(self.soc_config, comp_info)

        # Compilation macros are merged BY NAME, not as plain strings, with the project's own
        # 'defines' taking precedence over the ones imported from component pragmas. For a
        # valueless flag the two are equivalent, but a valued define (NAME=VAL) declared by both
        # sides would otherwise land twice on the vlog command line, where the winner is decided
        # by flag order - silently. Precedence makes the YAML the override, mirroring how every
        # other project-level setting relates to what a component or macro declares.
        merged = {}
        all_comps = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
        # 1. Defines exported by component sources via '// DEFINE:' pragmas, the way a macro
        #    carries the compilation macros its internals were generated with (sv_parser), plus
        #    the ones collected while staging isle sources (the NoC isle-to-tile path, where the
        #    tile wrapper parsed above does not carry the original isle's pragmas).
        for c in all_comps:
            for d in (comp_info.get(c.name) or {}).get("defines") or []:
                merged[d.split('=', 1)[0]] = d
        for d in self.imported_defines:
            merged[d.split('=', 1)[0]] = d
        # 2. The project's own declarations, last so they win by name.
        for c in all_comps:
            for d in (getattr(c, 'defines', None) or []):
                merged[d.split('=', 1)[0]] = d
        global_defines = set(merged.values())

        # Hierarchical-block restrictions declared by the components themselves (the crossbar
        # path, where the isle is parsed directly; the NoC isle-to-tile path fills the same map
        # while staging the isle source, above).
        for c in all_comps:
            reason = (comp_info.get(c.name) or {}).get("verilator_exclude_hier_block")
            if reason:
                self.hier_block_marks[c.name] = reason

        return comp_info, wiring_matrix, global_defines

    def _get_pad_domains(self):
        if not self.soc_config.padframe: return []
        domains_config = self.soc_config.padframe.domains or []
        
        pad_domains = []
        for dom in domains_config:
            config_dir = self.env.config_file_path.parent if (hasattr(self.env, 'config_file_path') and self.env.config_file_path) else Path.cwd()
            raw_list = self.soc_config.padframe.get_pad_list_data(dom.name, config_dir)

            expanded_list = []
            for pad in raw_list:
                if pad.get("multiple", 1) > 1:
                    for i in range(pad.get("multiple", 1)):
                        ep = dict(pad)
                        ep["name"] = ep["name"].replace("{i}", str(i))
                        if "default_port" in ep:
                            ep["default_port"] = ep["default_port"].replace("{i}", str(i))
                        if "connections" in ep:
                            ep["connections"] = {k.replace("{i}", str(i)) if isinstance(k, str) else k: v.replace("{i}", str(i)) if isinstance(v, str) else v for k, v in ep["connections"].items()}
                        expanded_list.append(ep)
                else:
                    expanded_list.append(pad)
            pad_domains.append({"name": dom.name, "pad_list": expanded_list})
        return pad_domains

    def get_signal_domain(self, sig_name, core_sig_to_domain, default_dom="domain_0"):
        if not sig_name:
            return default_dom
        # 1. Direct lookup
        if sig_name in core_sig_to_domain:
            return core_sig_to_domain[sig_name]
        # 2. Normalize signal name
        base = sig_name
        for suffix in ("_en_o", "_oe_o", "_oe", "_no", "_ni", "_o", "_i"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        if base in core_sig_to_domain:
            return core_sig_to_domain[base]
        # Handle index suffix, e.g., gpio_i_31 -> gpio_31 -> domain_3v3
        m = re.match(r"^([a-zA-Z0-9_]+)_([0-9]+)$", sig_name)
        if m:
            prefix, idx = m.group(1), m.group(2)
            for suffix in ("_en_o", "_oe_o", "_oe", "_no", "_ni", "_o", "_i"):
                if prefix.endswith(suffix):
                    prefix = prefix[: -len(suffix)]
                    break
            norm_with_idx = f"{prefix}_{idx}"
            if norm_with_idx in core_sig_to_domain:
                return core_sig_to_domain[norm_with_idx]
            if prefix in core_sig_to_domain:
                return core_sig_to_domain[prefix]
        # 3. Fallback to first dynamic domain if default_dom is "domain_0"
        if default_dom == "domain_0":
            dynamic_domains = [dom["name"] for dom in self._get_pad_domains() if any(not pad.get("is_static") for pad in dom["pad_list"])]
            if dynamic_domains:
                return dynamic_domains[0]
        return default_dom

    def generate_port_groups(self, comp_info):
        """
        Auto-generates the Padrick port_groups YAML configuration by inspecting
        the SoC configuration and the export_interfaces of each component.
        This acts as the 'Port-Group Provider', eliminating name mismatches
        between the Core and the Padframe.
        """
        if not self.soc_config.padframe:
            return {}, {}

        cfg_dir = self.env.outdir_path / self.env.cfg_sub
        port_groups_file = cfg_dir / f"{self.soc_config.project.name}_soc_port_groups.yml"
        
        oe_signal_name = "paden2chip"
        domains_config = self.soc_config.padframe.domains or []
        for dom in domains_config:
            tech_file = None
            search_dirs = self.env.component_paths + [self.env.base_dir / "components"]
            for d in search_dirs:
                candidate = d / "padframes" / dom.tech / f"{dom.tech}.yml"
                if candidate.is_file():
                    tech_file = candidate
                    break
                candidate = d / "padframes" / "tech" / f"{dom.tech}.yml"
                if candidate.is_file():
                    tech_file = candidate
                    break
            if tech_file:
                tech_data = yaml.safe_load(tech_file.read_text(encoding='utf-8')) or []
                for p_type in tech_data:
                    signals = p_type.get("pad_signals", [])
                    signal_names = {sig["name"] for sig in signals if isinstance(sig, dict) and "name" in sig}
                    if "output_en" in signal_names:
                        oe_signal_name = "output_en"
                        break
        
        lines = []
        lines.append("port_groups:")
        lines.append('  - name: "soc_exports"')
        lines.append('    output_defaults: "1\'b0"')
        lines.append('    ports:')
        
        all_comps = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
        

        pad_domains = self._get_pad_domains()
        port_multiples = {}
        
        domains_config = self.soc_config.padframe.domains or []
        
        for dom in domains_config:
            config_dir = self.env.config_file_path.parent if (hasattr(self.env, 'config_file_path') and self.env.config_file_path) else Path.cwd()
            raw_list = self.soc_config.padframe.get_pad_list_data(dom.name, config_dir)
            for pad in raw_list:
                dp = pad.get("default_port", "")
                if dp.startswith("soc_exports."):
                    p_name = dp.split(".")[-1]
                    p_base = p_name.replace('_{i}', '').replace('[{i}]', '')
                    port_multiples[p_base] = pad.get("multiple", 1)
                elif "connections" in pad:
                    for k, v in pad["connections"].items():
                        soc_sig = k if v in ["pad2chip", "paden2chip", "chip2pad"] else v
                        if "_{i}" in soc_sig or "[{i}]" in soc_sig:
                            p_name = soc_sig.replace('_{i}', '').replace('[{i}]', '')
                            p_base = get_base_name(p_name)
                            port_multiples[p_base] = pad.get("multiple", 1)

        grouped_ports = {}
        port_mapping = {}


        def add_port(name, direction, soc_port_name, p_type="logic"):
            dims = extract_dims(p_type)
            if not dims:
                base = get_base_name(name)
                if base not in grouped_ports:
                    grouped_ports[base] = {}
                soc_sig = soc_port_name
                if direction == "output":
                    if name.endswith("_en_o") or name.endswith("_oe_o") or name.endswith("_oe"):
                        grouped_ports[base][oe_signal_name] = soc_sig
                    else:
                        grouped_ports[base]["chip2pad"] = soc_sig
                elif direction == "input":
                    grouped_ports[base][soc_sig] = "pad2chip"
                elif direction == "inout":
                    grouped_ports[base][soc_sig] = "pad_inout"
            else:
                for suf in get_suffixes(dims):
                    base = get_base_name(name) + suf
                    if base not in grouped_ports:
                        grouped_ports[base] = {}
                    soc_sig = f"{soc_port_name}{suf}"
                    if direction == "output":
                        if name.endswith("_en_o") or name.endswith("_oe_o") or name.endswith("_oe"):
                            grouped_ports[base][oe_signal_name] = soc_sig
                        else:
                            grouped_ports[base]["chip2pad"] = soc_sig
                    elif direction == "input":
                        grouped_ports[base][soc_sig] = "pad2chip"
                    elif direction == "inout":
                        grouped_ports[base][soc_sig] = "pad_inout"
                
            if soc_port_name not in port_mapping:
                port_mapping[soc_port_name] = {
                    'pad_base': get_base_name(name),
                    'dir': direction
                }

        # Always export primary global signals
        if getattr(self.soc_config.clock_tree, 'generators', 0) > 0:
            add_port("pwr_on_rst_ni", "input", "pwr_on_rst_ni")
            add_port("ref_clk_i", "input", "ref_clk_i")
        else:
            add_port("clk_i", "input", "clk_i")
            add_port("rst_ni", "input", "rst_ni")
        add_port("test_mode_i", "input", "test_mode_i")
        bm_w = port_multiples.get("boot_mode", 2)
        add_port("boot_mode_i", "input", "boot_mode_i", f"logic [{bm_w-1}:0]" if bm_w > 1 else "logic")

        def process_interfaces(target_comp, info, is_host):
            c_ports = info.get("ports", {})
            if target_comp.export_interfaces:
                for ext_if in target_comp.export_interfaces:
                    # 1. DYNAMIC INTERFACE EXTRACTION (The Smart Way)
                    # Find all physical ports that start with the requested interface prefix
                    for comp_port, p_info in c_ports.items():
                        if comp_port.startswith(f"{ext_if}_") or comp_port == ext_if:
                            p_type = p_info.get("type_dim", "logic")
                            p_dir = p_info.get("dir", "inout")
                            
                            width = 1
                            w_match = re.search(r'\[\s*(\d+)\s*[-:]+\s*(\d+)\s*\]', p_type)
                            if w_match:
                                width = abs(int(w_match.group(1)) - int(w_match.group(2))) + 1
                                
                            if is_host:
                                p_top = comp_port
                            else:
                                if comp_port.startswith(f"{target_comp.name}_"):
                                    p_top = comp_port
                                else:
                                    p_top = f"{target_comp.name}_{comp_port}"
                                    
                            add_port(p_top, p_dir, p_top, p_type)

                    ports = get_interface_ports(ext_if, target_comp.name, is_host, info)
                    for p in ports:
                        comp_port = p.get("internal", p["top"])
                        p_type = c_ports.get(comp_port, {}).get("type_dim", "logic")
                        p_dir = p.get("dir", c_ports.get(comp_port, {}).get("dir", "inout"))
                        
                        p_top = p["top"]
                            
                        add_port(p_top, p_dir, p_top, p_type)

        for comp in all_comps:
            c_info = comp_info.get(comp.name, {})
            process_interfaces(comp, c_info, comp.name == self.soc_config.host.name)
            
            if comp.components:
                for sub_c in comp.components:
                    sub_info = comp_info.get(sub_c.name, {})
                    process_interfaces(sub_c, sub_info, False)
                
        for base, conns in grouped_ports.items():
            lines.append(f'      - name: "{base}"')
            lines.append(f'        connections:')
            for pad_sig, soc_sig in conns.items():
                lines.append(f'          {pad_sig}: {soc_sig}')

        write_if_changed(port_groups_file, "\n".join(lines) + "\n")
        return grouped_ports, port_mapping

    def render_top_level(self, comp_info, wiring_matrix, global_defines):
        """
        Phase 3 (cont'd): The main generation loop where all Top-Level components,
        packages, memory maps, and the final Bender.yml manifest are rendered.
        """
        grouped_ports, port_mapping = self.generate_port_groups(comp_info)
        
        pad_domains = self._get_pad_domains()

        top_level_module_name = self.top_level_module_name
        top_level_filename = f"{top_level_module_name}.sv"

        # ----------------------------------------------------------------------
        # Calculate comp_extra_conns and top_ports in Python
        # ----------------------------------------------------------------------
        comp_extra_conns = {}
        top_ports = []
        all_extra_ports = []
        noc_comp_extra_conns = {}
        
        all_comps = [self.soc_config.host] + (self.soc_config.components if self.soc_config.components else [])
        
        if self.soc_config.topology.type == "crossbar":
            for comp in all_comps:
                comp_extra_conns.setdefault(comp.name, [])
                exported_interfaces = comp.export_interfaces if comp.export_interfaces else []
                c_info = comp_info.get(comp.name, {})
                is_host = (comp.name == self.soc_config.host.name)
                
                for if_name in exported_interfaces:
                    ports_to_export = get_interface_ports(if_name, comp.name, is_host, c_info)
                    for p in ports_to_export:
                        internal_port = p['internal']
                        top_port = p['top']
                        p_dir = p['dir']
                        
                        p_info = c_info.get("ports", {}).get(internal_port)
                        if not p_info:
                            continue
                        
                        decl = p_info["decl"]
                        known_params = {}
                        known_params.update(c_info.get("supported_params", {}))
                        known_params.update(c_info.get("fixed_params", {}))
                        if comp.parameters:
                            for k, v in comp.parameters.items():
                                known_params[k] = "1" if v is True else "0" if v is False else str(v)
                                
                        for param_name, param_val in known_params.items():
                            decl = re.sub(rf'\b{param_name}\b', param_val, decl)
                            
                        name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
                        if name_match:
                            decl = decl[:name_match.start()] + top_port + name_match.group(2)
                            decl = simplify_port_ranges(decl)
                            if f"{p_dir} {decl}" not in top_ports:
                                top_ports.append(f"{p_dir} {decl}")
                            conn_str = f".{internal_port:<17} ( {top_port} )"
                            if conn_str not in comp_extra_conns[comp.name]:
                                comp_extra_conns[comp.name].append(conn_str)
        elif self.soc_config.topology.type == "noc":
            max_x, max_y = 0, 0
            grid = {}
            for c in all_comps:
                p = getattr(c, 'placement', None)
                if not p or 'logical' not in p: continue
                log = p['logical']
                items = log if isinstance(log, list) else [log]
                inst_idx = 0
                for item in items:
                    if 'box' in item:
                        b = item['box']
                        for x in range(b['x_start'], b['x_end']+1):
                            for y in range(b['y_start'], b['y_end']+1):
                                grid[(x,y)] = (c, inst_idx)
                                inst_idx += 1
                                max_x = max(max_x, x)
                                max_y = max(max_y, y)
                    else:
                        x, y = item['x'], item['y']
                        grid[(x,y)] = (c, inst_idx)
                        inst_idx += 1
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
            
            for c in all_comps:
                inst_coords = {}
                num_instances = 0
                for (gx, gy), (c_grid, idx) in grid.items():
                    if c_grid and c_grid.name == c.name:
                        num_instances = max(num_instances, idx + 1)
                        inst_coords[idx] = (gx, gy)
                if num_instances == 0:
                    num_instances = 1
                    
                c_info = comp_info.get(c.name, {})
                is_host = (c.name == self.soc_config.host.name)
                exported_interfaces = c.export_interfaces if c.export_interfaces else []
                
                for if_name in exported_interfaces:
                    ports_to_export = get_interface_ports(if_name, c.name, is_host, c_info)
                    for p in ports_to_export:
                        internal_port = p['internal']
                        p_dir = p['dir']
                        p_info = c_info.get("ports", {}).get(internal_port)
                        if not p_info: continue
                        decl = p_info["decl"]
                        
                        known_params = {}
                        known_params.update(c_info.get("supported_params", {}))
                        known_params.update(c_info.get("fixed_params", {}))
                        if c.parameters:
                            for k, v in c.parameters.items():
                                known_params[k] = "1" if v is True else "0" if v is False else str(v)
                        for param_name, param_val in known_params.items():
                            decl = re.sub(rf'\b{param_name}\b', param_val, decl)
                        decl = simplify_port_ranges(decl)
                        
                        name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
                        if name_match:
                            for inst_idx in range(num_instances):
                                if is_host:
                                    top_port_name = p['top']
                                else:
                                    if num_instances > 1:
                                        cx, cy = inst_coords.get(inst_idx, (0,0))
                                        top_port_name = f"{c.name}_{cx}_{cy}_{internal_port}"
                                    else:
                                        top_port_name = p['top']
                                        
                                inst_decl = decl[:name_match.start()] + top_port_name + name_match.group(2)
                                if f"{p_dir} {inst_decl}" not in all_extra_ports:
                                    all_extra_ports.append(f"{p_dir} {inst_decl}")
                                    
                                key = (c.name, inst_idx)
                                noc_comp_extra_conns.setdefault(key, [])
                                conn_str = f".{internal_port:<17} ( {top_port_name} )"
                                if conn_str not in noc_comp_extra_conns[key]:
                                    noc_comp_extra_conns[key].append(conn_str)

        # Build and verify the SystemVerilog Intermediate Representation (IR)
        ir = self.build_architecture_ir(comp_info, wiring_matrix, comp_extra_conns, noc_comp_extra_conns, port_mapping, top_ports, all_extra_ports)
        validation_messages = ir.verify(comp_info)
        if validation_messages:
            print("\n" + "="*70)
            print("[*] RTL Structural Verification Report:")
            has_error = False
            for msg in validation_messages:
                print(f"  {msg}")
                if msg.startswith("[ERROR]"):
                    has_error = True
            print("="*70 + "\n")
            if has_error:
                print("[FATAL ERROR] Structural verification failed. Halting generation.")
                sys.exit(1)

        macro_pragmas = []
        hw_dir = self.env.outdir_path / self.env.hw_sub
        sw_dir = self.env.outdir_path / self.env.sw_sub
        doc_dir = self.env.outdir_path / self.env.doc_sub
        cfg_dir = self.env.outdir_path / self.env.cfg_sub
        reg_dir = self.env.outdir_path / self.env.reg_sub
        tb_dir = self.env.outdir_path / self.env.tb_sub

        sys_regs_addr_width = 8
        try:
            sys_regs_info = get_isle_info(f"{top_level_module_name}_sys_regs", [reg_dir])
            if sys_regs_info and "ports" in sys_regs_info:
                p_info = sys_regs_info["ports"].get("s_apb_paddr")
                if p_info:
                    decl = p_info.get("decl", "")
                    m_range = re.search(r'\[\s*([0-9]+)\s*:\s*([0-9]+)\s*\]', decl)
                    if m_range:
                        sys_regs_addr_width = int(m_range.group(1)) - int(m_range.group(2)) + 1
        except Exception as e:
            print(f"[WARNING] Could not parse system registers address width: {e}. Falling back to 8.")
        
        # Resolved once here rather than inside each template, so that the SoC package
        # and the FlooGen configuration cannot end up with different ID widths for the
        # same network. Empty for a crossbar, which has no network to size.
        noc_id_widths, noc_user_widths = {}, {}
        if self.soc_config.topology.type == "noc":
            noc_user_widths = resolve_noc_user_widths(self.soc_config)
            noc_id_widths = resolve_noc_id_widths(self.soc_config, self.env.component_paths,
                                                  self.original_isle_types)

        # UART baud, resolved once for the two consumers that must agree on it: the
        # firmware, which programs the 16550 divisor, and the testbench monitor, which
        # samples the line. What they share is the DIVISOR, not the nominal baud: the
        # divisor is an integer, so the rate the hardware actually produces is
        # uart_freq/(16*divisor), and at high rates that differs from the nominal by
        # percents (a nominal 2 Mbaud lands on 2.083 with divisor 3). A monitor timed on
        # the nominal value would drift across a frame and mis-sample the stop bit.
        # Raising the baud is the largest lever on Verilator run time, where every idle
        # bit-cycle is evaluated (future_evolution_tasks.md, chapter 5).
        uart_freq = 100_000_000
        uart_baudrate = 115200
        if getattr(self.soc_config, "software_stack", None):
            uart_baudrate = int(self.soc_config.software_stack.get("test_app", {})
                                .get("baudrate", uart_baudrate))
        uart_divisor = max(1, round(uart_freq / (16 * uart_baudrate)))

        # Offload test resolution: which components the generated firmware will drive.
        # Resolved here once with report=True, so the generation log records the target
        # list the firmware was actually built for (schema validation already proved the
        # resolution sound). The payload region comes from 'test_app.payload_memory'
        # when declared, and is carved out of the boot memory otherwise - the two modes
        # and their reasons are commented at the resolution below.
        app_name = "hello_world"
        if getattr(self.soc_config, "software_stack", None):
            app_name = self.soc_config.software_stack.get("test_app", {}).get("name", "hello_world")

        # Preload entries may name the firmware through the '{test_app}' token instead of
        # hardcoding it: the token resolves here, to the app that is actually generated,
        # so a TEST_APP / --test-app override retargets the testbench preload with it.
        # A hardcoded file name keeps working (legacy examples), but silently decouples
        # from the override - the token is the recommended spelling.
        if getattr(self.soc_config, "testbench", None):
            for mem in (self.soc_config.testbench.get("preload_memories") or []):
                if isinstance(mem.get("file"), str):
                    mem["file"] = mem["file"].replace("{test_app}", app_name)

        offload_targets = {}
        offload_payload_base = 0
        offload_payload_size = 0
        offload_host_stack_top = 0
        offload_payload_ctrl_group = None
        if app_name == "offload":
            from core.soc_schema import resolve_offload_targets
            offload_targets = resolve_offload_targets(
                self.soc_config, self.env.search_paths, self.env.exclude_dir,
                self.original_isle_types, report=True)

            all_comps = [self.soc_config.host] + (self.soc_config.components or [])

            def _slave_window(comp_name, role):
                """First axi_slave window (component, base, size) of a named component,
                accepting 'size_per_instance' so multi-instance memories resolve to
                their instance-0 window. A miss is a hard error: the offload firmware
                cannot be linked without the region this window provides."""
                comp = next((c for c in all_comps if c.name == comp_name), None)
                slaves = (getattr(comp, "interfaces", None) or {}).get("axi_slave", []) if comp else []
                if isinstance(slaves, dict):
                    slaves = [slaves]
                if not slaves:
                    print(f"[ERROR] The 'offload' test derives its {role} from '{comp_name}', "
                          f"which does not resolve to a component with an axi_slave window.")
                    sys.exit(1)
                addr = slaves[0].get("base_addr", 0)
                addr = int(addr, 0) if isinstance(addr, str) else int(addr)
                size = slaves[0].get("size", slaves[0].get("size_per_instance", 0))
                size = int(size, 0) if isinstance(size, str) else int(size)
                return comp, addr, size

            boot_mem_name = self.soc_config.software_stack.get("boot_memory", "")
            _, b_addr, b_size = _slave_window(boot_mem_name, "payload region (via 'boot_memory')")

            payload_mem_name = self.soc_config.software_stack.get(
                "test_app", {}).get("payload_memory")
            if payload_mem_name:
                # An explicit 'test_app.payload_memory' places the payload at the base of
                # that component's (instance-0) window instead of carving the boot memory.
                # This exists because the carve is not universally FETCHABLE: on the mesh
                # family the boot SPM is a narrow-network endpoint, while the snitch
                # instruction cache refills through the cluster's WIDE master (the hive's
                # axi port, snitch_cluster.sv) - the payload must therefore live in a
                # memory both networks reach (L2), which only the SoC author can name.
                pm_comp, offload_payload_base, offload_payload_size = \
                    _slave_window(payload_mem_name, "payload region (via 'payload_memory')")
                # The host image and stack keep the WHOLE boot memory: nothing is carved.
                offload_host_stack_top = b_addr + b_size
                # When the payload memory is under an auto control group it powers on
                # gated: the firmware must ungate the group before loading the payload,
                # so the group's name travels to the templates alongside the region.
                pm_type = self.original_isle_types.get(pm_comp.name, pm_comp.type)
                sys_ctrl = self.soc_config.system_controller
                for g in (sys_ctrl.auto_control_groups if sys_ctrl else None) or []:
                    if g.type == "clk_rst_control" and pm_type in (g.target_component_type,
                                                                   g.target_tile_type):
                        offload_payload_ctrl_group = g.name.lower()
                        break
            else:
                # The payload region is the SECOND QUARTER of the boot memory window, not
                # its upper half. The upper half is not safe to write on every memory: the
                # dyn_mem-based L2 (l2_isle) maps it as the NON-interleaved VIEW of the same
                # physical banks the lower half exposes interleaved (dyn_mem_addr_map.sv
                # re-scrambles the same low address bits), so a payload written there lands
                # scattered across the physical words holding the host image - the fence.i
                # writeback then corrupts the code the host is running (found 2026-08-07:
                # Illegal Instruction right after the first fence.i on crux). The second
                # quarter stays inside the image's own view on such memories and is merely
                # conservative on a flat one; the host stack is capped at the payload base
                # (main_offload.c.mako), so image, stack and payload can never meet.
                offload_payload_size = b_size // 4
                offload_payload_base = b_addr + b_size // 4
                offload_host_stack_top = offload_payload_base

        template_kwargs = {
            "sys_regs_addr_width": sys_regs_addr_width,
            "config": self.soc_config,
            "uart_freq": uart_freq,
            "uart_divisor": uart_divisor,
            "offload_targets": offload_targets,
            "offload_payload_base": offload_payload_base,
            "offload_payload_size": offload_payload_size,
            # Top of the HOST's stack in the offload app: the payload base when the
            # payload is carved from the boot memory, the end of the boot memory when
            # an explicit 'payload_memory' hosts the payload elsewhere.
            "offload_host_stack_top": offload_host_stack_top,
            # Auto control group gating the payload memory (None when ungated): the
            # firmware ungates it before the first payload write.
            "offload_payload_ctrl_group": offload_payload_ctrl_group,
            # The toy workload of the offload payload, as (iterations, whitening) of a
            # sum of squares. Single source for BOTH sides of the check: the payload is
            # compiled with these as -D macros (Makefile.sw.mako) and the host firmware
            # bakes the expected result from the same two numbers (main_offload.c.mako).
            # The whitening constant must keep bit 31 CLEAR: the memory_mapped return
            # slots carry (value << 1) | 1 in 32 bits, so only 31 bits of value survive
            # the round-trip (found 2026-08-10: 0xCAFE0000 came back as 0x4AFE...).
            "offload_check_n": 16,
            "offload_check_xor": 0x4AFE0000,
            "noc_id_widths": noc_id_widths,
            "noc_user_widths": noc_user_widths,
            "ir": ir,
            "top_level_module_name": top_level_module_name,
            "project_name": self.soc_config.project.name,
            "sys_ctrl": self.soc_config.system_controller.model_dump(exclude_none=True) if self.soc_config.system_controller else {},
            "wiring_matrix": wiring_matrix,
            "domains": [d.model_dump(exclude_none=True) for d in self.soc_config.clock_tree.domains],
            "components": [c.model_dump(exclude_none=True) for c in self.soc_config.components] if self.soc_config.components else [],
            "comp_info": comp_info,
            "ecc_schemes_dir": str(self.env.ecc_schemes_dir) if self.env.ecc_schemes_dir else None,
            "global_defines": sorted(list(global_defines)),
            "env_config": {
                "dependencies": self.env.registry_dependencies,
                "fast_check_tool": self.env.fast_check_tool
            },
            "gen_version": self.gen_version,
            "git_hash": self.git_hash,
            "grouped_ports": grouped_ports,
            "port_mapping": port_mapping,
            "top_ports": top_ports,
            "all_extra_ports": all_extra_ports,
            "top_level_params": {},
            "pad_domains": pad_domains,
            "macro_pragmas": macro_pragmas,
            "original_isle_types": self.original_isle_types,
            "fmt_dom": fmt_dom,
            "fmt_reg": fmt_reg,
            "fmt_rst": fmt_rst,
            "camel_case": camel_case,
            "is_external": is_external,
            "generated_module_files": sorted(self.generated_module_files),
            "generated_types_pkg_files": sorted(self.generated_types_pkg_files),
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
                "reg/soc_regs.rdl.mako": reg_dir / f"{top_level_module_name}_regs.rdl",
                "reg/soc_memory_map.rdl.mako": reg_dir / f"{top_level_module_name}_memory_map.rdl",
                "hw/crossbar_soc_pkg.sv.mako": hw_dir / f"{self.soc_config.project.soc_pkg_name}.sv",
                "hw/crossbar_soc_top.sv.mako": hw_dir / top_level_filename,
                "sw/soc_map.h.mako": sw_dir / f"{self.soc_config.project.name}_map.h",
                "doc/crossbar_map.csv.mako": doc_dir / f"{self.soc_config.project.name}_map.csv",
                "sim.mk.mako": self.env.outdir_path / "sim" / "sim.mk",
                "tb/tb_soc.sv.mako": tb_dir / f"tb_{self.soc_config.project.name}.sv"
            }
        else:
            templates_to_render = {
                "hw/noc_soc_pkg.sv.mako": hw_dir / f"{self.soc_config.project.soc_pkg_name}.sv",
                "hw/noc_soc_top.sv.mako": hw_dir / top_level_filename,
                "hw/tiles/dummy_tile.sv.mako": hw_dir / f"{self.soc_config.project.module_prefix}_dummy_tile.sv",
                "reg/soc_regs.rdl.mako": reg_dir / f"{top_level_module_name}_regs.rdl",
                "reg/soc_memory_map.rdl.mako": reg_dir / f"{top_level_module_name}_memory_map.rdl",
                "sw/soc_map.h.mako": sw_dir / f"{self.soc_config.project.name}_map.h",
                "cfg/floogen_cfg.yml.mako": cfg_dir / f"{self.soc_config.project.name}_floogen.yml",
                "doc/noc_map.csv.mako": doc_dir / f"{self.soc_config.project.name}_noc_map.csv",
                "sim.mk.mako": self.env.outdir_path / "sim" / "sim.mk",
                "tb/tb_soc.sv.mako": tb_dir / f"tb_{self.soc_config.project.name}.sv"
            }

        # The global reset tree only exists when at least one clock domain is managed
        # (see OllivanderConfig.managed_clock_domains). Emitting `<name>_rstgen.sv`
        # unconditionally would add a module that is compiled but never instantiated.
        if self.soc_config.has_reset_tree:
            templates_to_render["hw/infrastructure/soc_rstgen.sv.mako"] = \
                hw_dir / f"{self.soc_config.project.module_prefix}_rstgen.sv"

        # Add Software templates dynamically if a software stack is configured
        if getattr(self.soc_config, "software_stack", None):
            templates_to_render["sw/linker.ld.mako"] = sw_dir / "linker.ld"
            templates_to_render["sw/Makefile.sw.mako"] = sw_dir / "Makefile"
            if self.soc_config.software_stack.get("test_app", {}).get("auto_generate_c", False):
                if app_name == "offload":
                    # The offload app swaps in its own host main and brings the payload
                    # build with it: generic payload source, linker script pinned to the
                    # payload region, per-target helpers, and the bin2header.py embedder
                    # copied alongside so the generated tree builds with no path back
                    # into the Ollivander installation.
                    templates_to_render["sw/main_offload.c.mako"] = sw_dir / "main.c"
                    templates_to_render["sw/offload.h.mako"] = sw_dir / f"{self.soc_config.project.name}_offload.h"
                    templates_to_render["sw/payload_main.c.mako"] = sw_dir / "payload_main.c"
                    templates_to_render["sw/payload.ld.mako"] = sw_dir / "payload.ld"
                    bin2header_src = (Path(__file__).parent / "bin2header.py").read_text(encoding="utf-8")
                    write_if_changed(sw_dir / "bin2header.py", bin2header_src)
                else:
                    templates_to_render["sw/main.c.mako"] = sw_dir / "main.c"

        for tpl_name, out_file in templates_to_render.items():
            if tpl_name == "tb/tb_soc.sv.mako":
                top_info = get_isle_info(top_level_module_name, [self.env.outdir_path / self.env.hw_sub])
                if top_info:
                    template_kwargs["top_level_ports"] = top_info.get("ports", {})
                    top_params = {}
                    top_params.update(top_info.get("supported_params", {}))
                    top_params.update(top_info.get("fixed_params", {}))
                    template_kwargs["top_level_params"] = top_params
                    # The testbench re-declares the top-level ports in its own scope, so it
                    # must locally typedef every type parameter those ports refer to.
                    template_kwargs["top_level_type_params"] = top_info.get("type_params", {})
                else:
                    template_kwargs["top_level_ports"] = {}
                    template_kwargs["top_level_params"] = {}
                    template_kwargs["top_level_type_params"] = {}

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
                rendered_code = re.sub(r'\bollivander_soc_pkg\b', f'{self.soc_config.project.soc_pkg_name}', rendered_code)
                rendered_code = re.sub(r'\bfloo_ollivander_noc_pkg\b', f'{self.soc_config.project.noc_pkg_name}', rendered_code)

                if out_file.name.endswith('.sv'):
                    rendered_code = auto_import_sv_packages(rendered_code)
                    
                if "hwif_in" in rendered_code and f"import {top_level_module_name}_sys_regs_pkg::*;" not in rendered_code:
                    rendered_code = re.sub(rf'import {self.soc_config.project.soc_pkg_name}::\*;', 
                                           rf'import {self.soc_config.project.soc_pkg_name}::*;\n  import {top_level_module_name}_sys_regs_pkg::*;', 
                                           rendered_code)

                # Extract dynamic pragmas from the fully rendered code. THE TESTBENCH'S
                # REQUIREMENTS ARE NOT THE PROJECT'S: the VIP is a simulation-only
                # bench (classes, timing), so pooling its 'require' with the RTL ones
                # put it among the manifest's RTL sources and - worse - into the list a
                # MACRO EXPORTS, making a parent compile another project's bench as if
                # it were hardware (found 2026-08-19 in crux_isle.sv's export header).
                # Same principle as the local/exported split in generate_verilator_config:
                # an artifact of MY bench is not a property of MY hardware.
                if tpl_name == "tb/tb_soc.sv.mako":
                    self.tb_required_local_files.update(self.req_pattern.findall(rendered_code))
                else:
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

        # Emit the Verilator hierarchical configuration next to the other cfg/ artifacts:
        # the sim.mk verilator targets reference it unconditionally.
        self.generate_verilator_config(cfg_dir, hw_dir, top_level_module_name, comp_info)

        # Explicitly require the Clock Generator for the Phase 8 Chip Wrapper
        if getattr(self.soc_config.clock_tree, 'generators', 0) > 0:
            self.required_local_files.add("olli_clk_gen.sv")

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

        template_kwargs["external_local_files"] = sv_dependency_sort(external_local_files)

        # THE SIMULATION-ONLY CLOSURE, resolved the same way but kept in its own list:
        # the manifest template puts it under the 'simulation' target next to the
        # testbench, and the macro export ignores it (see the collection site above).
        # A file already staged as RTL is not repeated here - if some component really
        # needs it, it is hardware by that fact alone.
        tb_external_local_files = []
        tb_pending = sorted(self.tb_required_local_files)
        while tb_pending:
            req_file = tb_pending.pop(0)
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
                print(f"  -> Linking simulation dependency {src_path.name} from {src_path.parent}")
                content = src_path.read_text(encoding='utf-8')
                for new_req in self.req_pattern.findall(content):
                    if new_req not in staged_local_files and new_req not in tb_pending:
                        tb_pending.append(new_req)
                for match in self.dep_pattern.finditer(content):
                    dep_name = match.group(1)
                    self.project_dependencies.setdefault(dep_name, {})
                    if match.group(2): self.project_dependencies[dep_name]['git'] = match.group(2)
                    if match.group(3): self.project_dependencies[dep_name]['rev'] = match.group(3)
                    if match.group(4): self.project_dependencies[dep_name]['version'] = match.group(4)
                rel_path = os.path.relpath(src_path, self.env.bender_dir).replace('\\', '/')
                if rel_path not in tb_external_local_files:
                    tb_external_local_files.append(rel_path)
                staged_local_files.add(src_path.name)
            else:
                print(f"[WARNING] Required simulation file '{req_file}' not found in component paths.")
                staged_local_files.add(req_file)

        template_kwargs["tb_external_local_files"] = sv_dependency_sort(tb_external_local_files)

        # Resolve all collected Bender dependencies against the environment registry.
        # If a dependency was declared in a pragma without git/rev/version details,
        # we look it up in the central registry (e.g., ollivander_config.yml).
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
                    # A pragma names a package no registry can source: the manifest this loop
                    # is building would carry an entry with no git and no revision, and Bender
                    # would fail on it later, far from the file that asked. Refusing here names
                    # the wrapper's pragma instead - and is what makes
                    # 'inherit_default_dependencies: false' an audit rather than a trap: with
                    # the base registry declined, every requirement the project forgot to
                    # declare stops the generation at this line. This used to be a warning,
                    # and generation continued into the Bender failure.
                    print(f"\n[ERROR] Dependency '{dep_name}' is required by a '// BENDER:' pragma "
                          f"but no 'dependencies' block provides its source (git and rev/version).\n"
                          f"        Declare it in the project's *_env.yml under 'dependencies' - or, "
                          f"if inherit_default_dependencies is false, reconsider that choice.")
                    sys.exit(1)

            resolved_dependencies[dep_name] = {'git': git, 'rev': rev, 'version': version}
                
        # Collect padframe files if padframe is enabled
        padframe_files = []
        if self.soc_config.padframe:
            seen_techs = set()
            domains_config = self.soc_config.padframe.domains or []
            for dom in domains_config:
                if dom.tech in seen_techs:
                    continue
                seen_techs.add(dom.tech)
                
                padframe_dir = self.env.base_dir / "components" / "padframes" / dom.tech
                if not padframe_dir.is_dir():
                    padframe_dir = self.env.base_dir / "components" / "padframe"
                
                if padframe_dir.is_dir():
                    for f_path in padframe_dir.glob("*.sv"):
                        rel_f = os.path.relpath(f_path, self.env.bender_dir).replace('\\', '/')
                        if rel_f not in padframe_files:
                            padframe_files.append(rel_f)
            
            pf_src_files_path = self.env.outdir_path / self.env.hw_sub / "padframe" / "src_files.yml"
            if pf_src_files_path.is_file():
                try:
                    pf_src_files = yaml.safe_load(pf_src_files_path.read_text(encoding='utf-8'))
                    pf_name = self.soc_config.padframe.name
                    if pf_name in pf_src_files and "files" in pf_src_files[pf_name]:
                        for f in pf_src_files[pf_name]["files"]:
                            abs_f = self.env.outdir_path / self.env.hw_sub / "padframe" / f
                            rel_f = os.path.relpath(abs_f, self.env.bender_dir).replace('\\', '/')
                            padframe_files.append(rel_f)
                except Exception as e:
                    print(f"[WARNING] Failed to parse padframe src_files.yml: {e}")

        template_kwargs["padframe_files"] = padframe_files
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
                    
                if self.soc_config.project.build_mode == "macro":
                    rendered_code = re.sub(rf'hw/{self.soc_config.project.name}\.sv', f'hw/{top_level_filename}', rendered_code)

                out_file = self.env.bender_manifest_path
                write_if_changed(out_file, rendered_code)
            except Exception as e:
                print(f"\n[ERROR] Failed to render {bender_tpl}:\n{e}")
                sys.exit(1)
                
        # ----------------------------------------------------------------------
        # Inject macro pragmas using the fully resolved Bender lists
        # ----------------------------------------------------------------------
        top_file_path = hw_dir / top_level_filename
        if top_file_path.is_file():
            content = top_file_path.read_text(encoding='utf-8')
            if self.soc_config.project.build_mode == "macro":
                macro_pragmas = []
                
                for dep_name, dep_info in sorted(resolved_dependencies.items()):
                    macro_pragmas.append(f'// BENDER: name="{dep_name}"')

                # A macro must also carry the compilation macros its internals were generated
                # with, the way it carries its Bender requirements: the consuming project has no
                # other way to know that, say, pulp_cluster inside this macro needs
                # FEATURE_ICACHE_STAT. global_defines already includes the defines this project
                # itself imported, so nesting a macro inside a macro forwards them transitively.
                for define in sorted(global_defines):
                    macro_pragmas.append(f'// DEFINE: name="{define}"')

                # A macro must equally carry forward the hierarchical-block restrictions of its
                # internals: the consuming project sees one isle, and has no other way to know
                # that something inside it cannot become a Verilator child library. The reasons
                # are merged into one declaration because the consumer's decision is binary - the
                # tile built around this macro is excluded - while the text has to stay readable.
                if self.hier_block_marks:
                    merged_reason = "; ".join(
                        f"{name}: {reason}" for name, reason in sorted(self.hier_block_marks.items()))
                    macro_pragmas.append(f'// OLLIVANDER: exclude_hier_block="{merged_reason}"')

                # The positive counterpart of the mark: the modules this macro's own
                # .vlt declares as hierarchical blocks, re-emitted so the parent can
                # promote them by declaration instead of inferring them from file
                # names. What the child excluded is simply absent from the list.
                for m in self.hier_block_modules:
                    macro_pragmas.append(f'// OLLIVANDER: hier_block="{m}"')

                if self.soc_config.topology.type == "noc":
                    macro_pragmas.append(f'// OLLIVANDER: require="{self.soc_config.project.noc_pkg_name}.sv"')
                macro_pragmas.append(f'// OLLIVANDER: require="{self.soc_config.project.soc_pkg_name}.sv"')
                if self.soc_config.system_controller:
                    macro_pragmas.append(f'// OLLIVANDER: require="{top_level_module_name}_sys_regs_pkg.sv"')
    
                for f in sv_dependency_sort(external_local_files):
                    fname = Path(f).name
                    if fname not in [f"{self.soc_config.project.noc_pkg_name}.sv", f"{self.soc_config.project.soc_pkg_name}.sv", f"{top_level_module_name}_sys_regs_pkg.sv"]:
                        macro_pragmas.append(f'// OLLIVANDER: require="{fname}"')
    
                # The per-isle types packages travel with the macro like every other
                # generated file; they precede the module list so a parent that keeps
                # the require order compiles each package before its importing isle.
                for f in sorted(self.generated_types_pkg_files):
                    macro_pragmas.append(f'// OLLIVANDER: require="{Path(f).name}"')

                for f in sorted(self.generated_module_files):
                    fname = Path(f).name
                    macro_pragmas.append(f'// OLLIVANDER: require="{fname}"')
    
                if self.soc_config.topology.type == "noc":
                    macro_pragmas.append(f'// OLLIVANDER: require="{self.soc_config.project.module_prefix}_dummy_tile.sv"')
                if getattr(self.soc_config.clock_tree, 'generators', 0) > 0:
                    macro_pragmas.append('// OLLIVANDER: require="olli_clk_gen.sv"')
                # Only require the reset tree when it is actually generated.
                if self.soc_config.has_reset_tree:
                    macro_pragmas.append(f'// OLLIVANDER: require="{self.soc_config.project.module_prefix}_rstgen.sv"')
                if self.soc_config.system_controller:
                    macro_pragmas.append(f'// OLLIVANDER: require="{top_level_module_name}_sys_regs.sv"')
    
                macro_pragmas.append(f'// PEAKRDL: source="{top_level_module_name}_memory_map.rdl" map="{top_level_module_name}_soc_map"')
    
                pragma_str = "\n".join(macro_pragmas)
                content = content.replace("// OLLIVANDER_MACRO_PRAGMAS_PLACEHOLDER", pragma_str)
            else:
                content = content.replace("// OLLIVANDER_MACRO_PRAGMAS_PLACEHOLDER\n", "").replace("// OLLIVANDER_MACRO_PRAGMAS_PLACEHOLDER", "")
                
            write_if_changed(top_file_path, content)

    def generate_verilator_config(self, cfg_dir, hw_dir, top_level_module_name, comp_info=None):
        """Emit cfg/<top>.vlt: the hier_block declarations for the Verilator flow.

        Hierarchical verilation is the only build mode the emitted verilator targets use:
        every module marked 'hier_block' is verilated once into a child library, so a tile
        repeated N times costs one build instead of N inlined copies (measured on the mesh:
        hours and tens of GB monolithic against minutes and ~3 GB per unit). The generator
        is the right author for this file because the selection rules are mechanical over
        information only it has:

        - every tile module is a candidate, single-instance ones included: each child
          verilates in its own bounded lane and is reused within the build, so the win
          is not only the N-instances-one-build sharing (every instance shares one
          parameterization by construction of the templates) but the lane itself;
        - a module is EXCLUDED when the generated testbench reaches into it hierarchically
          (Verilator cannot cross a hier-block boundary with a dotted path): the host tile
          carries the bring-up forces and the Cheshire boot scratch, and every tile named
          in testbench.preload_memories is a $readmemh target;
        - a module is EXCLUDED when its wrapper declares struct-typed or type parameters:
          Verilator 5.050's hier-parameters wrapper cannot rebuild those (internal error,
          reported upstream). Detected by scanning the generated wrapper header.

        On a crossbar the same architecture applies with isles in place of tiles: the
        host isle stays in the top unit (the testbench's bring-up forces and the boot
        scratch reach into it hierarchically, exactly like the manager tile on the
        mesh), preload targets stay for their $readmemh paths, and every other
        non-external component whose wrapper survives the parameter rules becomes its
        own child library — valuable even at one instance apiece, because each child
        verilates in its own bounded lane and is reused within the build (between-build reuse is deliberately disabled in sim.mk, 2026-08-18).

        A config with no hier_block entries remains valid input and simply degenerates
        to a flat build.
        """
        vlt_dir = self.env.outdir_path / "sim" / "verilator"
        vlt_dir.mkdir(parents=True, exist_ok=True)
        vlt_path = vlt_dir / f"{top_level_module_name}.vlt"
        lines = ["`verilator_config"]

        # THE HOST'S EXCLUSION IS A CONSEQUENCE OF THE BOOT MODE, NOT A PROPERTY
        # OF THE HOST. Under 'force' the generated testbench reaches into the host
        # with dotted paths (the boot scratch, the bring-up registers) and Verilator
        # cannot cross a hier-block boundary with one, so the host must stay in the
        # top unit. Under 'jtag' every one of those writes travels the debug module
        # instead: no dotted path survives, and the host - the heaviest single
        # component of every example - becomes eligible like any other. This is the
        # dividend the force-free bring-up exists for (wip 2.1).
        host_boot_mode = (self.soc_config.testbench or {}).get("boot_mode", "force")
        host_reachable_by_tb = (host_boot_mode != "jtag")

        # LOCAL EXCLUSIONS VS EXPORTED DECLARATIONS (wip 2.1 residual 2, second half).
        # Two kinds of exclusion end up in the same set below, and they do NOT have
        # the same scope:
        #   - TESTBENCH-driven (this host under force boot, this project's $readmemh
        #     targets): they hold only for a simulation of THIS project, because they
        #     describe what MY testbench reaches into with dotted paths.
        #   - STRUCTURAL (a declared hier_block restriction, the macro wrapper rule,
        #     the type-parameter rule): properties of the module itself, true for any
        #     consumer.
        # A macro build still generates its own testbench and simulates standalone
        # (build_mode only skips the chip wrapper), so the local .vlt must keep BOTH.
        # But the list this project EXPORTS - the pragmas a parent re-emits into its
        # own .vlt - is read by a different testbench, with its own boot mode and its
        # own preload list: propagating my testbench's exclusions there would let a
        # force-mode donor silently cost its parent a promoted block (super_noc
        # promotes mesh_subtile_manager_tile today only because the donor happens to
        # boot by jtag). So the export carries the structural exclusions alone, and
        # the PARENT decides what its own testbench forbids. Tested by construction
        # from 2026-08-19: mesh_subtile boots by force while super_noc boots by jtag,
        # so a regression here shows up as a drop in the parent's block count.
        tb_excluded = set()
        if host_reachable_by_tb:
            tb_excluded.add(self.soc_config.host.name)
        exported_modules = []

        def _wrapper_params_ok(module):
            """Parameter rule shared by both topologies: a wrapper carrying a TYPE in
            its parameterization cannot be a hier_block, because Verilator 5.050
            serializes it into __hierParameters.v as a typedef and then fails on its
            own output (V3LinkDot.cpp:496 internal error, reported upstream).

            Two forms trip it, both established by probe rather than assumed
            (2026-08-06): a real `parameter type` in the header — which the crossbar's
            sync isles carry, since the generator injects the SoC's AXI types there —
            and a body `localparam type`, which Verilator counts as parameterization
            too. The templates no longer emit the latter, so the check guards against
            its reappearance rather than any current wrapper.

            Deliberately nothing else. Two earlier criteria were dropped once probed:
            parameter defaults reading struct members (e.g. `= AxiCfgJoin.AddrWidth`)
            build perfectly well, and they had been excluding the heaviest memory tiles
            for nothing; package-qualified struct parameters never matched any wrapper
            in any example. The rule errs on the permissive side on purpose, because
            the two mistakes are not symmetric: admitting a module that cannot be built
            fails loudly at verilation, naming the module, while excluding one that
            could be built is silent forever - slower builds nobody attributes to a
            rule they cannot see. Add a criterion only with a probe behind it."""
            wrapper = hw_dir / f"{module}.sv"
            if not wrapper.is_file():
                return True
            text = wrapper.read_text(encoding="utf-8", errors="ignore")
            header = text.split(") (", 1)[0]
            reason = None
            if re.search(r"parameter\s+type\s", header):
                reason = "a 'parameter type' in its header"
            elif re.search(r"^\s*localparam\s+type\s", text, re.M):
                reason = "a body 'localparam type'"
            if reason:
                print(f"  -> vlt: skipping {module} ({reason}: Verilator cannot rebuild "
                      f"a type in a hier_block's parameterization)")
                return False
            return True

        if self.soc_config.topology.type == "noc":
            # Instance count per component, replicating the grid mapping of
            # noc_soc_top.sv.mako (box placements expand to their full area).
            comps = [self.soc_config.host] + (self.soc_config.components or [])
            counts = {}
            grid_owner = {}
            max_x = max_y = 0
            for c in comps:
                p = getattr(c, 'placement', None)
                if not p or 'logical' not in p:
                    continue
                log = p['logical']
                items = log if isinstance(log, list) else [log]
                for item in items:
                    if 'box' in item:
                        b = item['box']
                        for x in range(b['x_start'], b['x_end'] + 1):
                            for y in range(b['y_start'], b['y_end'] + 1):
                                counts[c.name] = counts.get(c.name, 0) + 1
                                grid_owner[(x, y)] = c.name
                                max_x, max_y = max(max_x, x), max(max_y, y)
                    else:
                        x, y = item['x'], item['y']
                        counts[c.name] = counts.get(c.name, 0) + 1
                        grid_owner[(x, y)] = c.name
                        max_x, max_y = max(max_x, x), max(max_y, y)
            dummy_count = sum(1 for x in range(max_x + 1) for y in range(max_y + 1)
                              if (x, y) not in grid_owner)

            # Exclusion 1: tiles the testbench references hierarchically. TB-driven,
            # so it stays out of the exported declarations (see the split above).
            excluded = set()
            tb_cfg = self.soc_config.testbench or {}

            for mem in tb_cfg.get("preload_memories", []):
                # 'instance' is the documented key; 'name' survives as its historical
                # alias. Until the single-instance rule was dropped this lookup never
                # decided anything on the shipped examples - their preload tiles were
                # all single-instance and skipped by count - so the wrong key here
                # was latent: with every tile now a hier_block candidate, missing the
                # exclusion would put the $readmemh target behind a hier boundary.
                name = mem.get("instance", mem.get("name", ""))
                for part in name.split('.'):
                    if part.startswith("i_tile_"):
                        coords = part.replace("i_tile_", "").split('_')
                        if len(coords) >= 2:
                            try:
                                owner = grid_owner.get((int(coords[0]), int(coords[1])))
                                if owner:
                                    # TB-driven as well: the $readmemh path is mine.
                                    tb_excluded.add(owner)
                            except ValueError:
                                pass

            # Exclusion 3: tiles carrying a component that declares it cannot be verilated as a
            # child library. The declaration travels with the component (and with a macro that
            # nests it), so a tile is excluded BECAUSE of what it contains - which is why this
            # rule survives a change of block granularity, where a rule phrased over the
            # structure ("a tile nesting a macro") would have to be rewritten. See section 5.3 of
            # docs/developer/wip/future_evolution_tasks.md for the measurement behind it.
            for comp_name, reason in sorted(self.hier_block_marks.items()):
                excluded.add(comp_name)
                print(f"  [INFO] hier_block: '{comp_name}' excluded - {reason}")
            # UNIFORM MACRO RULE (see the crossbar branch): the tile around a macro
            # that declares internal blocks is never a block itself - the declared
            # internals are promoted after the branches, wrapper and tile inlined.
            for comp_name in sorted(self.macro_hier_blocks):
                excluded.add(comp_name)

            prefix = self.soc_config.project.module_prefix
            for comp_name, count in sorted(counts.items()):
                if comp_name in excluded:
                    continue
                module = f"{prefix}_{comp_name}_tile"
                if not _wrapper_params_ok(module):
                    continue
                # Structurally eligible: exported to a parent in every case, declared
                # locally only if my own testbench keeps its hands off it.
                exported_modules.append(module)
                if comp_name not in tb_excluded:
                    lines.append(f'hier_block -module "{module}"')
            if dummy_count >= 1:
                exported_modules.append(f"{prefix}_dummy_tile")
                lines.append(f'hier_block -module "{prefix}_dummy_tile"')
        else:
            # Crossbar: the host isle stays in the top unit (the testbench's bring-up
            # forces and the Cheshire boot scratch reach into it hierarchically, the
            # same role the manager tile plays on the mesh), preload targets stay for
            # their $readmemh paths, and every other non-external component whose
            # wrapper survives the parameter rule becomes its own child library.
            excluded = set()
            tb_cfg = self.soc_config.testbench or {}
            for mem in tb_cfg.get("preload_memories", []):
                inst = mem.get("instance", mem.get("name", ""))
                for part in inst.split('.'):
                    if part.startswith("i_"):
                        # TB-driven: my $readmemh path, not a property of the memory.
                        tb_excluded.add(part[2:])
            # The declared restriction, exactly as on the mesh above. It matters here even though
            # the crossbar family builds today: hyperbus is out of the block set only because its
            # wrapper carries a `parameter type`, a workaround for a Verilator internal error that
            # section 5.1 plans to retire - and the day it is retired, the restriction has to be
            # the thing keeping the isle out, not a coincidence.
            for comp_name, reason in sorted(self.hier_block_marks.items()):
                excluded.add(comp_name)
                print(f"  [INFO] hier_block: '{comp_name}' excluded - {reason}")
            # UNIFORM MACRO RULE: a component whose staged source declares
            # '// OLLIVANDER: hier_block=' internals is an Ollivander macro. Its
            # declared modules are promoted below and its own wrapper never becomes
            # a block (blocks inside a block would nest, unprobed territory).
            for comp_name in sorted(self.macro_hier_blocks):
                excluded.add(comp_name)
            prefix = self.soc_config.project.module_prefix
            by_module = {}
            # The host is a candidate on the same terms as any other isle, unless
            # the testbench still reaches into it (force boot); it lives outside
            # 'components', which is why it used to be excluded by enumeration.
            candidates = list(self.soc_config.components or []) + [self.soc_config.host]
            for c in candidates:
                if is_external(c) or c.name in excluded:
                    continue
                by_module.setdefault(f"{prefix}_{c.type}", []).append(c.name)
            for module in sorted(by_module):
                if not _wrapper_params_ok(module):
                    continue
                exported_modules.append(module)
                # A module is declared locally only if NO component behind it is one
                # my testbench reaches into: several isles may share a wrapper type.
                if not any(n in tb_excluded for n in by_module[module]):
                    lines.append(f'hier_block -module "{module}"')

        # THE MACRO DESCENT (both topologies): promote the internals every macro
        # declared. Since the local/exported split (2026-08-19) those declarations are
        # everything STRUCTURALLY eligible in the child, including the modules the
        # child's own testbench keeps inlined - the child's boot mode and preload list
        # are its business, mine are mine. What the child still withholds are the
        # structural refusals (a marked isle, a wrapper carrying a type parameter):
        # those the parent must respect, and their absence from the declarations is
        # how it does. hier_block is a per-module declaration at any depth, so
        # Verilator carves these out of the enclosing macro content by name alone.
        # OPEN CASE: a parent whose OWN testbench reaches into a promoted macro
        # internal with a dotted path (a $readmemh into a nested memory - not done
        # today, and the nested-boot design deliberately loads through the window
        # instead) would need this loop to honour its own tb_excluded set. It fails
        # loudly at build time ("Cannot access non-port symbols inside hierarchical
        # block"), not silently, so the filter can wait for a case that needs it.
        promoted = set()
        for comp_name, modules in sorted(self.macro_hier_blocks.items()):
            for m in modules:
                if m not in promoted:
                    promoted.add(m)
                    exported_modules.append(m)
                    lines.append(f'hier_block -module "{m}"')
            if modules:
                print(f"  [INFO] hier_block: '{comp_name}' is a macro declaring"
                      f" {len(modules)} internal blocks - promoted, wrapper inlined")

        write_if_changed(vlt_path, "\n".join(lines) + "\n")
        # THE EXPORTED LIST IS NOT THE LOCAL ONE (see the split at the top of this
        # method): a macro re-emits as pragmas everything STRUCTURALLY eligible, so a
        # parent inherits the full set and applies its own testbench's restrictions.
        # Deduplicated while preserving order - a wrapper type shared by several
        # components is one declaration.
        self.hier_block_modules = list(dict.fromkeys(exported_modules))
        local_count = len(lines) - 1
        extra = len(self.hier_block_modules) - local_count
        print(f"  -> Rendering verilator hierarchical config into {vlt_path.name} "
              f"({local_count} hier blocks locally"
              + (f", {len(self.hier_block_modules)} exported to a parent)" if extra > 0 else ")"))

        # STUB OF rand_verif_pkg, VERILATOR FLOW ONLY. common_verification's
        # rand_verif_pkg::rand_wait contains an event control ('repeat (cycles)
        # @(posedge clk)'), and a hierarchical child whose subtree elaborates the
        # package fails with "Unsupported: --lib-create with --timing and delays"
        # (met 2026-08-17: cheshire_isle was the only isle affected, and the task
        # is never called by generated code - proven by rebuilding the subtree
        # with this very stub, which verilates clean even under --no-timing).
        # The stub lands next to the .vlt, outside every Bender-visible tree, and
        # enters compile_verilator_src.f alone while the flist filter drops the
        # real file (VERILATOR_FLIST_EXCLUDE): the QuestaSim flows keep compiling
        # the true package. Same pattern as the VHDL auto-stubs, and like them a
        # declared coverage loss of the license-free flow (docs/getting_started.md).
        stub_path = vlt_dir / "rand_verif_pkg_stub.sv"
        write_if_changed(stub_path, "\n".join([
            "// AUTO-GENERATED by Ollivander - Verilator flow only, do not edit.",
            "// Timing-free stand-in for common_verification's rand_verif_pkg: the",
            "// real task waits a random number of clock cycles, which Verilator",
            "// rejects inside a hierarchical block (--lib-create with --timing and",
            "// delays). No generated code calls it; the stub only keeps the symbol",
            "// resolvable. The QuestaSim flows compile the real package instead.",
            "package rand_verif_pkg;",
            "  task automatic rand_wait(input int unsigned min, max, ref logic clk);",
            "  endtask",
            "endpackage",
        ]) + "\n")

        # HIERARCHICAL PARAMETERS FILE, VERILATOR FLOW ONLY - deliberately empty.
        # Verilator substitutes a prebuilt hier_block library for its instances only
        # when --hierarchical-params-file is passed alongside --hierarchical-block;
        # otherwise the top-level verilation silently de-parameterizes the block and
        # inlines one clone per instance, while the child library is still built and
        # then never referenced. The engine emits a parameters file of its own only
        # for blocks carrying 'parameter type', so a design without those - ours -
        # never gets the option and never boxes anything that has parameters at all.
        # That is why the parameter-free dummy tile was the only block that ever
        # boxed here. The option merely needs to name a parseable file; parameter
        # declarations are not required, and Verilator would generate the same empty
        # content. Measured on the mesh example (2026-08-20): every declared block
        # boxes, against one before.
        params_path = vlt_dir / f"{top_level_module_name}_hier_params.v"
        write_if_changed(params_path, "\n".join([
            "// AUTO-GENERATED by Ollivander - Verilator flow only, do not edit.",
            "// Intentionally empty: only the presence of --hierarchical-params-file",
            "// enables substitution of prebuilt hierarchical libraries for blocks",
            "// that declare parameters. Add declarations here only if a hierarchical",
            "// block ever gains a 'parameter type', keeping them in sync with what",
            "// the tool itself would emit. NOTE: no comment line here may start with",
            "// the word 'verilator' - that spelling is read as a pragma (BADVLTPRAGMA).",
            "//",
            "// SAFETY CONDITION, measured 2026-08-20: this file may stay empty only",
            "// while no hierarchical block declares a 'parameter type' overridden per",
            "// instance. In that one case the engine writes a real parameters file per",
            "// specialization (each carrying its typedef) and this one, forwarded from",
            "// the command line, comes last in the child's arguments: every instance",
            "// then binds to a single specialization - silently wrong, not merely slow.",
            "// Value parameters are unaffected, measured: two instances differing by a",
            "// value get two libraries and the top references both.",
            "// The condition holds BY CONSTRUCTION here, and that is the thing to",
            "// preserve: what gets boxed is always the generated tile/isle wrapper,",
            "// and the standardization contracts keep that boundary type-free - the",
            "// underlying isles declare up to fourteen type parameters each, injected",
            "// one level inside the wrapper, with the types themselves reaching it",
            "// through per-isle packages. Putting a 'parameter type' on a WRAPPER",
            "// boundary is what would reintroduce the risk.",
        ]) + "\n")

    def generate_chip_wrapper(self, comp_info, wiring_matrix, global_defines):
        """
        Phase 8: The Chip Wrapper Engine.
        Reads the generated Top-Level Core RTL and the Padframe package generated 
        by Padrick, extracts their exact port/struct signatures, validates 
        type constraints, and securely renders the final Chip wrapper.
        """
        print("=" * 70)
        print("[*] Starting Phase 8: Cross-Validating and Generating Chip Wrapper...\n")

        if self.soc_config.project.build_mode == "macro":
            print("  [INFO] Build mode is 'macro'. Skipping Chip Wrapper generation.")
            print("=" * 70)
            return
        
        hw_dir = self.env.outdir_path / self.env.hw_sub
        core_file = hw_dir / f"{self.soc_config.project.name}.sv"
        
        padframe_dir = hw_dir / "padframe"
        pkg_filename = f"pkg_{self.soc_config.padframe.name}.sv"
        pkg_file = next(padframe_dir.rglob(pkg_filename), None)
        
        if not core_file.is_file():
            print("\n[ERROR] Core RTL missing. Cannot validate wrapper.")
            print(f"  -> Looked for Core RTL at: {core_file}")
            sys.exit(1)
            
        # 1. Parse Core RTL Ports
        core_clean = strip_comments(core_file.read_text(encoding='utf-8'))

        
        core_ports = {}
        module_match = re.search(r'\bmodule\s+'+self.soc_config.project.name+r'\b[\s\S]*?\)\s*;', core_clean)
        if module_match:
            for m in PORT_PATTERN.finditer(module_match.group(0)):
                p_type = re.sub(r'\s+', ' ', m.group(2).strip())
                core_ports[m.group(3).strip()] = {'dir': m.group(1).strip(), 'type': p_type}
                
        # 2. Parse Padrick Package Structs
        pkg_clean = ""
        if not pkg_file or not pkg_file.is_file():
            print(f"\n[WARNING] Padframe package '{pkg_filename}' missing in: {padframe_dir}")
            print("  -> Treating all core ports as unmapped to generate missing pads stub.")
        else:
            pkg_clean = strip_comments(pkg_file.read_text(encoding='utf-8'))

        
        field_pattern = re.compile(r'^\s*(logic(?:[\s\[\]0-9a-zA-Z_\-\+\*:]+)?)\s+([a-zA-Z0-9_]+)\s*;', re.MULTILINE)
        padframe_fields = {}
        for m in field_pattern.finditer(pkg_clean):
            f_type = re.sub(r'\s+', ' ', m.group(1).strip())
            padframe_fields[m.group(2).strip()] = {'type': f_type}
            
        grouped_ports, port_mapping = self.generate_port_groups(comp_info)
        
        pad_domains = self._get_pad_domains()
        
        statically_routed_wires = set()
        core_sig_to_domain = {}
        for dom in pad_domains:
            for pad in dom["pad_list"]:
                if "connections" in pad:
                    for k, v in pad["connections"].items():
                        soc_sig = k if v in ["pad2chip", "paden2chip", "chip2pad"] else v
                        core_sig_to_domain[soc_sig] = dom["name"]
                if "default_port" in pad:
                    dp = pad["default_port"].split(".")[-1]
                    core_sig_to_domain[dp] = dom["name"]
                
                if pad.get('is_static') and 'connections' in pad:
                    for _, pad_sig in pad['connections'].items():
                        statically_routed_wires.add(pad_sig)
                    
        # 3. Cross-Validation
        fatal_errors = []
        missing_pads = []
        validated_connections = []
        
        for core_sig, mapping in port_mapping.items():
            if core_sig not in core_ports:
                continue
                
            is_input_to_soc = core_ports[core_sig]['dir'] == 'input'
            core_type = core_ports[core_sig]['type']
            pad_base = mapping['pad_base']
            
            if core_sig in statically_routed_wires:
                pad_sig = core_sig
                p_dir = core_ports[core_sig]['dir']
                if p_dir == 'inout':
                    validated_connections.append({
                        'sig_name': core_sig,
                        'sv_type': core_type,
                        'is_input_to_soc': False,
                        'is_inout': True,
                        'struct_path': core_sig
                    })
                elif pad_sig not in padframe_fields:
                    missing_pads.append((pad_sig, core_sig, core_type, p_dir))
                else:
                    pad_type = padframe_fields[pad_sig]['type']
                    if norm_type(core_type) != norm_type(pad_type):
                        fatal_errors.append(f"Width/Type mismatch on '{core_sig}': Core expects '{core_type}', Padframe provides '{pad_type}'")
                    else:
                        dom_name = self.get_signal_domain(core_sig, core_sig_to_domain)
                        struct_path = f"static_pad2soc.{dom_name}.{pad_sig}" if is_input_to_soc else f"static_soc2pad.{dom_name}.{pad_sig}"
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': is_input_to_soc,
                            'struct_path': struct_path
                        })
            else:
                p_dir = core_ports[core_sig]['dir']
                dims = []
                for m in re.finditer(r'\[\s*([^\]:]+)\s*:\s*([^\]]+)\s*\]', core_type):
                    try:
                        dims.append((int(eval(m.group(1), {"__builtins__": {}})), int(eval(m.group(2), {"__builtins__": {}}))))
                    except Exception: pass
                    
                if not dims:
                    pad_sig = core_sig
                    if p_dir == 'inout':
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': False,
                            'is_inout': True,
                            'struct_path': core_sig
                        })
                    elif pad_sig not in padframe_fields:
                        missing_pads.append((pad_sig, core_sig, core_type, p_dir))
                    else:
                        dom_name = self.get_signal_domain(pad_sig, core_sig_to_domain)
                        struct_path = f"port_pad2soc.{dom_name}.soc_exports.{pad_sig}" if is_input_to_soc else f"port_soc2pad.{dom_name}.soc_exports.{pad_sig}"
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': is_input_to_soc,
                            'is_inout': False,
                            'assignments': [{"lhs": core_sig, "rhs": struct_path} if is_input_to_soc else {"lhs": struct_path, "rhs": core_sig}]
                        })
                elif len(dims) == 1:
                    msb, lsb = dims[0]
                    step = -1 if msb >= lsb else 1
                    
                    found_all = True
                    scalar_struct_paths = []
                    for idx in range(msb, lsb + step, step):
                        pad_sig_i = f"{core_sig}_{idx}"
                        if p_dir == 'inout':
                            continue
                        elif pad_sig_i not in padframe_fields:
                            missing_pads.append((pad_sig_i, f"{core_sig}[{idx}]", "logic", p_dir))
                            found_all = False
                        else:
                            dom_name = self.get_signal_domain(pad_sig_i, core_sig_to_domain)
                            if pad_sig_i in statically_routed_wires:
                                struct_path = f"static_pad2soc.{dom_name}.{pad_sig_i}" if is_input_to_soc else f"static_soc2pad.{dom_name}.{pad_sig_i}"
                            else:
                                struct_path = f"port_pad2soc.{dom_name}.soc_exports.{pad_sig_i}" if is_input_to_soc else f"port_soc2pad.{dom_name}.soc_exports.{pad_sig_i}"
                            scalar_struct_paths.append(struct_path)
                    
                    if found_all and p_dir != 'inout':
                        concat_str = "{" + ", ".join(scalar_struct_paths) + "}"
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': is_input_to_soc,
                            'is_inout': False,
                            'assignments': [{"lhs": core_sig, "rhs": concat_str} if is_input_to_soc else {"lhs": concat_str, "rhs": core_sig}]
                        })
                    elif p_dir == 'inout':
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': False,
                            'is_inout': True,
                            'struct_path': core_sig
                        })
                else:
                    outer_msb, outer_lsb = dims[0]
                    outer_step = -1 if outer_msb >= outer_lsb else 1

                    assignments = []
                    found_all = True
                    for out_idx in range(outer_msb, outer_lsb + outer_step, outer_step):
                        inner_dims = dims[1:]
                        
                        inner_suffixes = get_suffixes(inner_dims)
                        chunk_paths = []
                        for suf in inner_suffixes:
                            pad_sig_i = f"{core_sig}_{out_idx}{suf}"
                            if p_dir == 'inout':
                                continue
                            elif pad_sig_i not in padframe_fields:
                                display_suf = suf.replace('_', '][') + ']'
                                missing_pads.append((pad_sig_i, f"{core_sig}[{out_idx}{display_suf}", "logic", p_dir))
                                found_all = False
                            else:
                                dom_name = self.get_signal_domain(pad_sig_i, core_sig_to_domain)
                                if pad_sig_i in statically_routed_wires:
                                    struct_path = f"static_pad2soc.{dom_name}.{pad_sig_i}" if is_input_to_soc else f"static_soc2pad.{dom_name}.{pad_sig_i}"
                                else:
                                    struct_path = f"port_pad2soc.{dom_name}.soc_exports.{pad_sig_i}" if is_input_to_soc else f"port_soc2pad.{dom_name}.soc_exports.{pad_sig_i}"
                                chunk_paths.append(struct_path)
                                
                        if found_all and p_dir != 'inout':
                            concat_str = "{" + ", ".join(chunk_paths) + "}"
                            inner_dim_str = "".join(f"[{m[0]}:{m[1]}]" for m in inner_dims)
                            lhs_str = f"{core_sig}[{out_idx}]{inner_dim_str}"
                            if is_input_to_soc:
                                assignments.append({"lhs": lhs_str, "rhs": concat_str})
                            else:
                                assignments.append({"lhs": concat_str, "rhs": lhs_str})

                    if found_all and p_dir != 'inout':
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': is_input_to_soc,
                            'is_inout': False,
                            'assignments': assignments
                        })
                    elif p_dir == 'inout':
                        validated_connections.append({
                            'sig_name': core_sig,
                            'sv_type': core_type,
                            'is_input_to_soc': False,
                            'is_inout': True,
                            'struct_path': core_sig
                        })
                    
        # 4. Catch-all for unmapped core ports
        for core_sig, p_info in core_ports.items():
            if core_sig not in port_mapping:
                if core_sig.startswith("ext_reg_async_slv_") or core_sig.startswith("domain_clk_i") or core_sig.startswith("clk_gen_lock_i"):
                    continue
                
                p_type = p_info['type']
                p_dir = p_info['dir']
                width = 1
                for w_match in re.finditer(r'\[\s*(\d+)\s*[-:]+\s*(\d+)\s*\]', p_type):
                    width *= abs(int(w_match.group(1)) - int(w_match.group(2))) + 1

                if width > 1:
                    for i in range(width):
                        missing_pads.append((f"{core_sig}_{i}", f"{core_sig}[{i}]", "logic", p_dir))
                else:
                    missing_pads.append((core_sig, core_sig, p_type, p_dir))
                    
        if missing_pads:
            print("\n  [ERROR] The following Core ports are missing from the Padframe:")
            yml_lines = []
            for ps, ss, ct, p_dir in missing_pads:
                print(f"    - {ss} ({ct})")
                
                if p_dir == 'input':
                    pad_type = 'PAD_INPUT'
                    conn_str = f"    pad2chip: {ps}"
                elif p_dir == 'output':
                    pad_type = 'PAD_OUTPUT'
                    conn_str = f"    chip2pad: {ps}"
                else:
                    pad_type = 'PAD_ANALOG'
                    conn_str = f"    pad_inout: {ps}"
                    
                yml_lines.append(f"- name: PAD_{ps.upper()}")
                yml_lines.append(f"  description: \"Auto-generated missing pad for {ss}\"")
                yml_lines.append(f"  pad_type: {pad_type}")
                yml_lines.append(f"  is_static: true")
                yml_lines.append(f"  connections:")
                yml_lines.append(conn_str)
                yml_lines.append("")
                
            cfg_dir = self.env.outdir_path / self.env.cfg_sub
            missing_file = cfg_dir / f"{self.soc_config.project.name}_missing_pads.yml"
            missing_file.write_text("\n".join(yml_lines))
            print(f"  [HINT] A stub YAML has been generated at {missing_file.name}. You can copy-paste it into your pad list!\n")
            
        if fatal_errors:
            print("\n[FATAL ERROR] Cross-Validation between Core RTL and Padframe failed!")
            for err in fatal_errors:
                print(f"  -> {err}")
            sys.exit(1)
        elif not missing_pads:
            print("  [SUCCESS] Core and Padframe types match perfectly!")
        
        template_kwargs = {
            "config": self.soc_config,
            "project_name": self.soc_config.project.name,
            "pad_domains": pad_domains,
            "core_sig_to_domain": core_sig_to_domain,
            "validated_connections": validated_connections,
            "gen_version": self.gen_version,
            "git_hash": self.git_hash,
        }
        
        out_file = hw_dir / f"{self.soc_config.project.module_prefix}_chip.sv"
        print(f"  -> Rendering chip wrapper into {out_file.name}")
        try:
            template = self.template_lookup.get_template("hw/chip_top.sv.mako")
            rendered_code = template.render(**template_kwargs)
            rendered_code = auto_import_sv_packages(rendered_code)
            rendered_code = rendered_code.replace('\r\n', '\n')
            write_if_changed(out_file, rendered_code)
        except Exception as e:
            print(f"\n[ERROR] Failed to render chip_top.sv.mako:\n{e}")
            sys.exit(1)

    def build_architecture_ir(self, comp_info, wiring_matrix, comp_extra_conns, noc_comp_extra_conns, port_mapping, top_ports=None, all_extra_ports=None):
        ir = SVArchitectureIR()
        
        # Register top-level system signals
        ir.add_signal("clk_i", "logic")
        ir.add_signal("rst_ni", "logic")
        ir.add_signal("host_clk", "logic")
        ir.add_signal("host_rst_n", "logic")
        ir.add_signal("host_pwr_on_rst_n", "logic")
        ir.add_signal("rt_clk", "logic")
        ir.add_signal("test_mode_i", "logic")
        ir.add_signal("boot_mode_i", "logic", "[1:0]")
        
        # Register clock and reset domain arrays
        num_domains = len(self.soc_config.clock_tree.domains)
        ir.add_signal("clks", "logic", f"[{num_domains-1}:0]")
        ir.add_signal("clks_n", "logic", f"[{num_domains-1}:0]")
        ir.add_signal("rsts_n", "logic", f"[{num_domains-1}:0]")
        ir.add_signal("pwr_on_rsts_n", "logic", f"[{num_domains-1}:0]")
        ir.add_signal("sw_rsts_n", "logic", f"[{num_domains-1}:0]")

        # Register exported interface signals (skip if already registered)
        for pm_name, pm_info in port_mapping.items():
            if pm_name not in ir.signals:
                ir.add_signal(pm_name, "logic")
            
        ir.add_signal("sys_regs_hwif_out", f"{self.top_level_module_name}_sys_regs_pkg::{self.top_level_module_name}_sys_regs__out_t")
        ir.add_signal("sys_regs_hwif_in", f"{self.top_level_module_name}_sys_regs_pkg::{self.top_level_module_name}_sys_regs__in_t")

        # Parse top_ports and all_extra_ports to register the correct type and dimensions
        for port_decl in ((top_ports or []) + (all_extra_ports or [])):
            port_decl_clean = port_decl.strip()
            if not port_decl_clean:
                continue
            m_dir = re.match(r"^\s*(input|output|inout)\b\s*(.*)$", port_decl_clean)
            if m_dir:
                remaining = m_dir.group(2).strip()
                # Port name, then any trailing UNPACKED dimensions ('foo [2:0]'). The
                # bracket escapes were doubled from birth (8342ebe), which demanded
                # literal backslashes: the dims group degenerated to the empty match
                # and a port with unpacked dims was silently never registered as an
                # IR signal (fixed 2026-08-11; no shipped example exposes such a
                # port, so no generated output changes).
                m_name = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$", remaining)
                if m_name:
                    sig_name = m_name.group(1)
                    trailing_dims = m_name.group(2).strip()
                    type_and_leading_dims = remaining[:m_name.start()].strip()
                    
                    m_dim = re.search(r"(\[.*\])$", type_and_leading_dims)
                    if m_dim:
                        dimensions = m_dim.group(1) + trailing_dims
                        sig_type = type_and_leading_dims[:m_dim.start()].strip()
                    else:
                        dimensions = trailing_dims
                        sig_type = type_and_leading_dims
                    
                    ir.add_signal(sig_name, sig_type, dimensions)

        if self.soc_config.topology.type == "crossbar":
            build_crossbar_ir(ir, self.soc_config, comp_info, wiring_matrix, comp_extra_conns)
        elif self.soc_config.topology.type == "noc":
            build_noc_ir(ir, self.soc_config, comp_info, noc_comp_extra_conns, self.original_isle_types)

        return ir

# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
SystemVerilog AST parsing and wrapper metadata extraction.
Utilizes pyslang compiler front-end to extract port signatures and parameter settings.
"""

import re
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional
from core.utils import strip_comments

try:
    import pyslang
    HAS_PYSLANG = True
except ImportError:
    HAS_PYSLANG = False

def _token_text(node: Any) -> str:
    """Source text of a token or syntax node, without its leading trivia.

    pyslang's str() reproduces the original text including whatever preceded the
    node - indentation and comments - so a port declared under a '// Landing
    Pads' banner would report that banner as part of its direction.
    """
    if node is None:
        return ""
    value = getattr(node, "valueText", None)
    if value is not None:              # a single token
        return str(value).strip()
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", " ", str(node))).strip()


def get_module_ports(filepath: Path, module_name: str) -> Optional[dict[str, dict[str, str]]]:
    """Read the ANSI port list of one module from a file: {name: {dir, type}}.

    SYNTAX ONLY, deliberately: no Compilation is built, so no packages, include
    paths or defines are needed. That matters because the caller is the chip
    wrapper generator, which runs before anything has been elaborated and only
    needs to know which ports exist, with what direction and width.

    Why this exists at all: the chip wrapper used to PREDICT the padframe's
    interface from the pad list, assuming every pad yields one port named
    '<pad>_pad'. Padrick emits one port per pad signal DECLARED BY THE PAD TYPE
    instead, so the assumption broke twice over - a config pad became four
    differently-named ports, and a pad type declaring no pad signals (corner
    cells, supplies) became none at all - and the wrapper connected fourteen
    ports that did not exist. Nothing caught it: `vlog` does not check port
    existence across a module boundary, and no flow elaborates the chip wrapper.
    Reading the generated file replaces the model of Padrick's behaviour with
    Padrick's actual output, which is also what makes this robust to a real PDK
    whose pad types we have never seen.

    Returns None when the file cannot be parsed or the module is not in it, so
    the caller can stop rather than fall back to guessing.
    """
    if not HAS_PYSLANG or not filepath or not Path(filepath).is_file():
        return None
    try:
        tree = pyslang.syntax.SyntaxTree.fromFile(str(filepath))
    except Exception:
        return None

    ports: dict[str, dict[str, str]] = {}
    for member in getattr(tree.root, "members", []):
        if "ModuleDeclaration" not in str(member.kind):
            continue
        header = member.header
        if str(header.name.valueText) != module_name:
            continue
        port_list = header.ports
        if port_list is None:
            return {}
        for port in getattr(port_list, "ports", []):
            if "ImplicitAnsiPort" not in str(port.kind):
                continue  # commas and non-ANSI forms
            p_hdr = port.header
            # str() on a token or node includes its leading trivia, comments and
            # all, so read the tokens' values instead of the raw source text.
            direction = _token_text(getattr(p_hdr, "direction", None))
            data_type = _token_text(getattr(p_hdr, "dataType", None))
            ports[str(port.declarator.name.valueText)] = {
                "dir": direction,
                "type": data_type,
            }
        return ports
    return None


def _clean_param_val(val: Any) -> str:
    """
    Converts a parameter value from the YAML configuration or the SystemVerilog
    source into a canonical string form (preferably a base-10 integer).
    This is crucial for comparing values like `32'hFF` (SV) with `255` (YAML)
    to ensure they represent the same hardware configuration, avoiding false
    positive validation errors due to syntax differences.
    """
    if isinstance(val, bool):
        return "1" if val else "0"
    
    val_str = str(val).strip()
    # A QUOTED value is a string literal, never a number: normalizing would chew
    # any SV-literal-looking text inside it ("32'h00000000" used to come out as
    # plain 0, which surfaced as `localparam string X = 0` once the declared
    # parameter types started travelling to the generated tile).
    if val_str.startswith('"'):
        return val_str
    # Handle Verilog-style literals like 1'b1, 32'hFF, 8'd10
    m = re.search(r'\'([dDbBhH]?)([0-9a-fA-F_]+)', val_str)
    if m:
        base_char = m.group(1).lower()
        num_str = m.group(2).replace('_', '')
        base = 16 if base_char == 'h' else (2 if base_char == 'b' else 10)
        try:
            return str(int(num_str, base))
        except ValueError:
            return val_str # return original on failure
    
    # Handle plain integers or hex/octal/binary like 0x..., 0o..., 0b...
    try:
        # int(x, 0) auto-detects the base
        return str(int(val_str, 0))
    except (ValueError, TypeError):
        # If it's not a number (e.g., a string parameter), return as is
        return val_str

def get_isle_info(component_type: str, search_paths: list[Path] = None, exclude_dir: str = None) -> Optional[dict[str, Any]]:
    """
    Scans the Ollivander project for the SystemVerilog wrapper associated 
    with the component_type to extract its capabilities and fixed constraints.
    
    This function acts as a bridge between the YAML configuration and the actual
    hardware implementation. It parses the SV header to guarantee that the 
    generator respects the Hardware Single Source of Truth (SSoT) paradigm.
    
    Returns a dictionary containing:
    - 'supported_params': A list of parameters the user can configure in YAML.
    - 'fixed_params': A dictionary of localparams with hardcoded values (constraints).
    - 'dependencies': External IP dependencies (BENDER pragmas).
    - 'required_files': Local file dependencies (OLLIVANDER pragmas).
    - 'ports': A dictionary detailing every physical port of the module.
    - 'imports': A list of SystemVerilog packages imported by the module.
    - 'rdl_file' / 'rdl_map': PeakRDL configurations extracted from pragmas.
    - Boolean flags indicating supported interfaces (e.g., 'has_sync_axi_slave', 'has_test_mode').
    """
    if not search_paths:
        search_paths = [Path(__file__).parent.parent.parent]
    
    filepath = None
    for sp in search_paths:
        # Check if the search path is directly a file.
        if sp.is_file() and sp.name == f"{component_type}.sv":
            filepath = sp
            break
        elif sp.is_dir():
            # Recursively search directories for the target SV wrapper.
            for p in sp.rglob(f"{component_type}.sv"):
                if exclude_dir and sp.name != exclude_dir and exclude_dir in p.parts:
                    continue
                filepath = p
                break
        if filepath:
            break
            
    if not filepath:
        return None
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    info = {
        "supported_params": {},
        "fixed_params": {},
        # Declared type of each VALUE parameter (canonical pyslang form, e.g.
        # 'longint unsigned', 'logic[63:0]'). The tile wrapper re-declares the
        # supported parameters and needs the real type: inferring it from the
        # (normalized) default value cannot tell a 64-bit parameter from a
        # 32-bit one, which silently capped instance-identity values at 4 GiB.
        # Empty under the regex fallback, whose consumers keep the inference.
        "param_types": {},
        # Subset of the parameters above that are SystemVerilog *type* parameters,
        # mapping each name to the type it defaults to. Consumers that re-declare a
        # module's ports outside the module itself (the generated testbench) need this:
        # the port declarations refer to the parameter names, which do not exist in any
        # package, so an equivalent typedef must be emitted in the consumer's scope.
        "type_params": {},
        "dependencies": {},
        "required_files": [],
        # Compilation macros (+define+) the component's sources are meant to be compiled with,
        # declared via '// DEFINE: name="..."' pragmas. Macro wrappers carry them so that a
        # consuming project inherits the defines the macro's internals were generated with.
        "defines": [],
        # Reason, if any, why this component cannot be verilated as a hierarchical block,
        # declared via '// OLLIVANDER: exclude_hier_block="..."'. Empty string means no
        # restriction. See generate_verilator_config for what the generator does with it.
        "verilator_exclude_hier_block": ""
    }
    
    # Unify header extraction: isolate the module declaration to prevent
    # matching parameters or ports defined inside the module body.
    module_decl_match = re.search(r'module\s+\w+\s*(?:import\s+[^;]+;\s*)*(?:#\s*\(([\s\S]*?)\))?\s*(\([\s\S]*?\))\s*;', content, re.MULTILINE)
    if module_decl_match:
        param_content = module_decl_match.group(1) or ""
        header_content = module_decl_match.group(2) or ""
    else:
        module_header_match = re.search(r'\bmodule\s+\w+[\s\S]*?\)\s*;', content)
        if module_header_match:
            param_content = module_header_match.group(0)
            header_content = module_header_match.group(0)
        else:
            param_content = content
            header_content = content

    # Use pyslang to extract parameters and ports
    pyslang_success = False
    port_names = set()
    info["ports"] = {}

    if HAS_PYSLANG:
        try:
            tree = pyslang.syntax.SyntaxTree.fromFile(str(filepath))
            comp = pyslang.ast.Compilation()
            comp.addSyntaxTree(tree)
            root = comp.getRoot()
            top_instances = list(root.topInstances)
            
            # Find the instance matching the component_type
            inst = None
            for top_inst in top_instances:
                if top_inst.name == component_type:
                    inst = top_inst
                    break
            if not inst and top_instances:
                inst = top_instances[0]
                
            if inst:
                body = inst.body
                # 1. Parameter extraction
                for p in body.parameters:
                    # Detect if parameter is a type parameter
                    is_type = type(p).__name__ == "TypeParameterSymbol" or not hasattr(p, 'value')
                    val = ""
                    if is_type:
                        if hasattr(p, 'targetType') and p.targetType and hasattr(p.targetType, 'type') and p.targetType.type and not str(p.targetType.type).startswith('<error>'):
                            val = str(p.targetType.type)
                        if not val and hasattr(p, 'syntax') and p.syntax and hasattr(p.syntax, 'assignment') and p.syntax.assignment:
                            val = str(p.syntax.assignment).strip()
                            if val.startswith('='):
                                val = val[1:].strip()
                        info["type_params"][p.name] = val
                        if p.isLocalParam:
                            info["fixed_params"][p.name] = val
                        else:
                            info["supported_params"][p.name] = val
                    else:
                        if hasattr(p, 'value') and not p.value.empty:
                            val = str(p.value.value)
                        if not val and hasattr(p, 'syntax') and p.syntax and hasattr(p.syntax, 'initializer') and p.syntax.initializer and hasattr(p.syntax.initializer, 'expr') and p.syntax.initializer.expr:
                            val = str(p.syntax.initializer.expr).strip()
                        clean_val = _clean_param_val(val)
                        try:
                            info["param_types"][p.name] = str(p.type)
                        except Exception:
                            pass
                        if p.isLocalParam:
                            info["fixed_params"][p.name] = clean_val
                        else:
                            info["supported_params"][p.name] = clean_val

                # 2. Port extraction
                for port in body.portList:
                    p_name = port.name
                    port_names.add(p_name)
                    
                    direction_str = str(port.direction).split('.')[-1].lower()
                    if direction_str == 'in':
                        p_dir = 'input'
                    elif direction_str == 'out':
                        p_dir = 'output'
                    elif direction_str == 'inout':
                        p_dir = 'inout'
                    else:
                        p_dir = direction_str
                        
                    decl = ""
                    type_dim = ""
                    unpacked = ""
                    if hasattr(port, 'syntax') and port.syntax and hasattr(port.syntax, 'parent') and port.syntax.parent:
                        decl = strip_comments(str(port.syntax.parent)).strip()
                        # Strip direction prefix from declaration
                        for prefix in ['input', 'output', 'inout']:
                            if decl.startswith(prefix):
                                decl = decl[len(prefix):].strip()
                                break
                        header = strip_comments(str(port.syntax.parent.header)).strip()
                        type_dim = header
                        for prefix in ['input', 'output', 'inout']:
                            if header.startswith(prefix):
                                type_dim = header[len(prefix):].strip()
                                break
                        if hasattr(port.syntax, 'dimensions') and port.syntax.dimensions:
                            unpacked = "".join(strip_comments(str(d)).strip() for d in port.syntax.dimensions)
                    else:
                        decl = f"logic {p_name}"
                        type_dim = "logic"
                        
                    info["ports"][p_name] = {
                        "dir": p_dir,
                        "decl": decl,
                        "type_dim": type_dim,
                        "unpacked": unpacked
                    }
                pyslang_success = True
        except Exception as e:
            print(f"[WARNING] pyslang parsing failed for {component_type}: {e}. Falling back to regex.")

    if not pyslang_success:
        # Fallback Parameter Extraction (Legacy Regex)
        pattern = re.compile(r'\b(parameter|localparam)\b\s+(?:type\s+|[A-Za-z0-9_\[\]\$:]+\s+)*([A-Za-z0-9_]+)\s*=\s*([^,;\n]+)[,;]?')
        for match in pattern.finditer(param_content):
            param_kind = match.group(1).strip()
            param_name = match.group(2).strip()
            clean_val = _clean_param_val(match.group(3).strip())
            if param_kind == "parameter":
                info["supported_params"][param_name] = clean_val
            elif param_kind == "localparam":
                info["fixed_params"][param_name] = clean_val

    # Extract Bender dependencies from comments (e.g. // BENDER: name="axi")
    dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')
    for match in dep_pattern.finditer(content):
        dep_name = match.group(1)
        info["dependencies"].setdefault(dep_name, {})
        if match.group(2): info["dependencies"][dep_name]["git"] = match.group(2)
        if match.group(3): info["dependencies"][dep_name]["rev"] = match.group(3)
        if match.group(4): info["dependencies"][dep_name]["version"] = match.group(4)
    
    # Extract local file dependencies (e.g. // OLLIVANDER: require="file.sv")
    req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
    for match in req_pattern.finditer(content):
        info["required_files"].append(match.group(1))

    # Extract compilation macros (e.g. // DEFINE: name="FEATURE_ICACHE_STAT"). The companion of
    # the BENDER pragma: it tells the consuming project which +define+ the component's sources
    # need, exactly as BENDER tells it which repositories they need.
    def_pattern = re.compile(r'(?://|##)\s*DEFINE:\s*name="([^"]+)"')
    for match in def_pattern.finditer(content):
        if match.group(1) not in info["defines"]:
            info["defines"].append(match.group(1))

    # Extract the hierarchical-block restriction (e.g.
    # // OLLIVANDER: exclude_hier_block="behavioural timing: ..."). A component declares here that
    # it carries a construct Verilator refuses inside a '--lib-create' child library - a delay, an
    # intra-assignment delay, a fork/join_none in a package class - so that the generator can keep
    # it, and every candidate containing it, out of sim/verilator/<top>.vlt. The reason is part of the
    # pragma on purpose: the message Verilator emits carries no source location, so without a
    # written reason the exclusion looks arbitrary to whoever reads the config later.
    # The value may span continuation comment lines, hence the DOTALL-free multi-line pattern.
    hier_match = re.search(r'(?://|##)\s*OLLIVANDER:\s*exclude_hier_block="([^"]*)"', content)
    if hier_match:
        # Collapse the continuation lines' comment markers and whitespace into single spaces,
        # so the reason reads as one sentence wherever it is printed.
        info["verilator_exclude_hier_block"] = re.sub(
            r'\s*(?://|##)?\s+', " ", hier_match.group(1)).strip() or "unspecified"

    # Extract PeakRDL mapping information (e.g. // PEAKRDL: source="my_ip.rdl" map="my_map")
    peakrdl_match = re.search(r'(?://|##)\s*PEAKRDL:\s*source="([^"]+)"(?:.*?map="([^"]+)")?', content)
    if peakrdl_match:
        info["rdl_file"] = Path(peakrdl_match.group(1)).name
        if peakrdl_match.group(2):
            info["rdl_map"] = peakrdl_match.group(2)

    # Clean comments from header_content for safe regex matching
    header_clean = strip_comments(header_content)

    # Fallback/Merge Port Names Extraction
    port_matches = re.finditer(r'\b(input|output|inout)\b([\s\S]*?)(?=\b(?:input|output|inout)\b|\)\s*(?:;|$))', header_clean)
    for m in port_matches:
        p_dir = m.group(1)
        decl = m.group(2).strip().split('=')[0].strip()
        decl = re.sub(r'[,;]\s*$', '', decl).strip()
        name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
        if name_match:
            p_name = name_match.group(1)
            if p_name not in info["ports"]:
                port_names.add(p_name)
                info["ports"][p_name] = {
                    "dir": p_dir,
                    "decl": decl,
                    "type_dim": decl[:name_match.start()].strip(),
                    "unpacked": name_match.group(2).strip()
                }
            
    # Extract package imports (Regex fallback that matches all imports in the file)
    imports = set()
    content_clean = strip_comments(content)
    for m in re.finditer(r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)::', content_clean):
        imports.add(m.group(1))
    info["imports"] = list(imports)

    # Detect interfaces based on standardized port naming conventions
    info["has_sync_axi_slave"] = 'axi_req_i' in port_names or re.search(r'\baxi_req_i\b', header_clean) is not None
    info["has_sync_axi_master"] = 'axi_req_o' in port_names or re.search(r'\baxi_req_o\b', header_clean) is not None
    info["has_async_axi_slave"] = 'async_axi_in_aw_data_i' in port_names or re.search(r'\basync_axi_in_aw_data_i\b', header_clean) is not None
    info["has_async_axi_master"] = 'async_axi_out_aw_data_o' in port_names or re.search(r'\basync_axi_out_aw_data_o\b', header_clean) is not None
    
    # Dual network variants
    info["has_sync_axi_narrow_slave"] = 'axi_narrow_req_i' in port_names or re.search(r'\baxi_narrow_req_i\b', header_clean) is not None
    info["has_sync_axi_wide_slave"] = 'axi_wide_req_i' in port_names or re.search(r'\baxi_wide_req_i\b', header_clean) is not None
    info["has_sync_axi_narrow_master"] = 'axi_narrow_req_o' in port_names or re.search(r'\baxi_narrow_req_o\b', header_clean) is not None
    info["has_sync_axi_wide_master"] = 'axi_wide_req_o' in port_names or re.search(r'\baxi_wide_req_o\b', header_clean) is not None
    info["has_async_axi_narrow_slave"] = 'async_axi_narrow_in_aw_data_i' in port_names or re.search(r'\basync_axi_narrow_in_aw_data_i\b', header_clean) is not None
    info["has_async_axi_wide_slave"] = 'async_axi_wide_in_aw_data_i' in port_names or re.search(r'\basync_axi_wide_in_aw_data_i\b', header_clean) is not None
    info["has_async_axi_narrow_master"] = 'async_axi_narrow_out_aw_data_o' in port_names or re.search(r'\basync_axi_narrow_out_aw_data_o\b', header_clean) is not None
    info["has_async_axi_wide_master"] = 'async_axi_wide_out_aw_data_o' in port_names or re.search(r'\basync_axi_wide_out_aw_data_o\b', header_clean) is not None

    info["has_test_mode"] = 'test_mode_i' in port_names or re.search(r'\btest_mode_i\b', header_clean) is not None
    info["has_pwr_on_rst"] = 'pwr_on_rst_ni' in port_names or re.search(r'\bpwr_on_rst_ni\b', header_clean) is not None
    info["has_ref_clk"] = 'ref_clk_i' in port_names or re.search(r'\bref_clk_i\b', header_clean) is not None
    info["has_rt_clk"] = 'rt_clk_i' in port_names or re.search(r'\brt_clk_i\b', header_clean) is not None
    info["has_sys_clk"] = 'sys_clk_i' in port_names or re.search(r'\bsys_clk_i\b', header_clean) is not None
    info["has_sys_rst"] = 'sys_rst_ni' in port_names or re.search(r'\bsys_rst_ni\b', header_clean) is not None
    info["has_rtc"] = 'rtc_i' in port_names or re.search(r'\brtc_i\b', header_clean) is not None
    info["has_boot_mode"] = 'boot_mode_i' in port_names or re.search(r'\bboot_mode_i\b', header_clean) is not None
    info["has_bootmode"] = 'bootmode_i' in port_names or re.search(r'\bbootmode_i\b', header_clean) is not None
    info["has_boot_addr"] = 'boot_addr_i' in port_names or re.search(r'\bboot_addr_i\b', header_clean) is not None
    info["has_jtag_oe"] = 'jtag_tdo_oe_o' in port_names or re.search(r'\bjtag_tdo_oe_o\b', header_clean) is not None
    
    info["header_content"] = header_content
            
    return info

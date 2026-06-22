# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
SystemVerilog AST parsing and wrapper metadata extraction.
Utilizes Verible parser to extract port signatures and parameter settings.
"""

import re
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.utils import strip_comments

def get_verible_ast(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    Invokes Google's Verible parser to extract the Abstract Syntax Tree (AST)
    from a SystemVerilog file. This allows Ollivander to reliably parse complex
    module headers, parameters, and ports without relying solely on Regex.
    The AST is exported as JSON, providing a structured, hierarchical view of
    the RTL which is immune to formatting variations or multi-line declarations.
    """
    # Try to find the Verible executable in the system PATH.
    verible_exe = shutil.which("verible-verilog-syntax")
    if not verible_exe:
        # Fallback: check if it's installed locally in the current Python
        # virtual environment (e.g., via `pip install verible`).
        venv_verible = Path(sys.executable).parent / "verible-verilog-syntax"
        if venv_verible.is_file() and os.access(venv_verible, os.X_OK):
            verible_exe = str(venv_verible)
            
    if not verible_exe:
        return None
        
    try:
        result = subprocess.run([verible_exe, "--export_json", str(filepath)], capture_output=True, text=True, check=True)
        json_data = json.loads(result.stdout)
        # Verible outputs a dictionary mapping the absolute file path to its AST.
        # Example: {"/absolute/path.sv": {"tag": "kCompilationUnit", ...}}
        return json_data.get(str(filepath))
    except Exception:
        return None

def walk_ast(node, tags):
    """
    Recursively yields nodes that match any of the given tags.
    Used to navigate the heavily nested JSON representation of the Verible AST.
    """
    if isinstance(node, dict):
        if node.get("tag") in tags:
            yield node
        for child in node.get("children", []):
            if child:
                yield from walk_ast(child, tags)
    elif isinstance(node, list):
        for item in node:
            if item:
                yield from walk_ast(item, tags)

def extract_tokens(node, tag=None):
    """
    Extracts tokens (leaves) from an AST node.
    Optionally filters tokens by a specific Verible syntax tag.
    """
    if isinstance(node, dict):
        if "children" not in node:
            if not tag or node.get("tag") == tag:
                yield node
        else:
            for child in node.get("children", []):
                if child:
                    yield from extract_tokens(child, tag)
    elif isinstance(node, list):
        for item in node:
            if item:
                yield from extract_tokens(item, tag)

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

def get_isle_info(component_type: str, search_paths: List[Path] = None, exclude_dir: str = None) -> Optional[Dict[str, Any]]:
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
        
    ast = get_verible_ast(filepath)

    info = {
        "supported_params": {},
        "fixed_params": {},
        "dependencies": {},
        "required_files": []
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

    ast_found_params = False
    if ast:
        # =====================================================================
        # AST-BASED PARAMETER EXTRACTION
        # =====================================================================
        decl_tags = {"kParamDeclaration", "kLocalParamDeclaration", "kParameterPortDeclaration"}
        assign_tags = {"kVariableDeclarationAssignment", "kTypeAssignment", "kParamAssignment", "kParameterAssignment", "kAssignment"}
        for decl in walk_ast(ast, decl_tags):
            is_local = (decl.get("tag") == "kLocalParamDeclaration")
            for assign in walk_ast(decl, assign_tags):
                tokens = list(extract_tokens(assign))
                eq_index = -1
                for i, t in enumerate(tokens):
                    if t.get("text") == "=":
                        eq_index = i
                        break
                        
                if eq_index > 0:
                    param_name = ""
                    for i in range(eq_index - 1, -1, -1):
                        text = tokens[i].get("text", "")
                        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', text):
                            param_name = text
                            break
                            
                    if param_name:
                        # Reconstruct the value from the remaining tokens.
                        val_tokens = [t.get("text", "") for t in tokens[eq_index + 1:]]
                        if val_tokens:
                            param_val = "".join(val_tokens).strip(";")
                            clean_val = _clean_param_val(param_val)
                            if is_local:
                                info["fixed_params"][param_name] = clean_val
                            else:
                                info["supported_params"][param_name] = clean_val
                            ast_found_params = True

    if not ast or not ast_found_params:
        # =====================================================================
        # LEGACY REGEX-BASED PARAMETER EXTRACTION (Fallback)
        # =====================================================================
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

    # Extract PeakRDL mapping information (e.g. // PEAKRDL: source="my_ip.rdl" map="my_map")
    peakrdl_match = re.search(r'(?://|##)\s*PEAKRDL:\s*source="([^"]+)"(?:.*?map="([^"]+)")?', content)
    if peakrdl_match:
        info["rdl_file"] = Path(peakrdl_match.group(1)).name
        if peakrdl_match.group(2):
            info["rdl_map"] = peakrdl_match.group(2)

    # Clean comments from header_content for safe regex matching
    header_clean = strip_comments(header_content)

    # =====================================================================
    # PORT NAMES EXTRACTION (AST + Regex Fallback)
    # =====================================================================
    port_names = set()
    info["ports"] = {}
    if ast:
        for port_decl in walk_ast(ast, {"kPortDeclaration", "kPort"}):
            tokens = list(extract_tokens(port_decl))
            
            # Split tokens using commas to properly handle multiple declarations
            # on the same line
            sub_decls_tokens = []
            current_decl = []
            bracket_level = 0
            for t in tokens:
                text = t.get("text", "")
                if text == ',' and bracket_level == 0:
                    if current_decl:
                        sub_decls_tokens.append(current_decl)
                    current_decl = []
                else:
                    current_decl.append(t)
                    if text in ['[', '(', '{']: bracket_level += 1
                    elif text in [']', ')', '}']: bracket_level -= 1
            if current_decl:
                sub_decls_tokens.append(current_decl)

            for decl_tokens in sub_decls_tokens:
                unpacked_level = 0
                port_name = ""
                for t in reversed(decl_tokens):
                    text = t.get("text", "")
                    if text == ']': unpacked_level += 1
                    elif text == '[': unpacked_level -= 1
                    elif unpacked_level == 0 and t.get("tag") == "SymbolIdentifier":
                        port_name = text
                        break
                if port_name:
                    port_names.add(port_name)

    # Fallback Regex: Useful for retrieving ports hidden inside Macro calls
    port_matches = re.finditer(r'\b(input|output|inout)\b([\s\S]*?)(?=\b(?:input|output|inout)\b|\)\s*(?:;|$))', header_clean)
    for m in port_matches:
        p_dir = m.group(1)
        decl = m.group(2).strip().split('=')[0].strip()
        decl = re.sub(r'[,;]\s*$', '', decl).strip()
        name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
        if name_match:
            p_name = name_match.group(1)
            port_names.add(p_name)
            info["ports"][p_name] = {
                "dir": p_dir,
                "decl": decl,
                "type_dim": decl[:name_match.start()].strip(),
                "unpacked": name_match.group(2).strip()
            }
            
    # Add any ports detected exclusively by the AST
    for p_name in port_names:
        if p_name not in info["ports"]:
            info["ports"][p_name] = {
                "dir": "inout",
                "decl": f"logic {p_name}",
                "type_dim": "logic",
                "unpacked": ""
            }
            
    # =====================================================================
    # IMPORTS EXTRACTION (AST + Regex Fallback)
    # =====================================================================
    imports = set()
    if ast:
        for imp_decl in walk_ast(ast, {"kPackageImportItem"}):
            ids = list(extract_tokens(imp_decl, "SymbolIdentifier"))
            if ids:
                imports.add(ids[0].get("text", ""))
                
    # Always run the regex fallback on the full content to catch imports before the module declaration
    content_clean = strip_comments(content)
    for m in re.finditer(r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)::\*;', content_clean):
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

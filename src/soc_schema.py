# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
#
# Pydantic Schema Definitions for the Ollivander SoC Generator

import re
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

def get_verible_ast(filepath: Path) -> Optional[Dict[str, Any]]:
    verible_exe = shutil.which("verible-verilog-syntax")
    if not verible_exe:
        venv_verible = Path(sys.executable).parent / "verible-verilog-syntax"
        if venv_verible.is_file() and os.access(venv_verible, os.X_OK):
            verible_exe = str(venv_verible)
            
    if not verible_exe:
        return None
        
    try:
        result = subprocess.run([verible_exe, "--export_json", str(filepath)], capture_output=True, text=True, check=True)
        json_data = json.loads(result.stdout)
        # Verible outputs {"/absolute/path": {AST} or null}
        return json_data.get(str(filepath))
    except Exception as e:
        return None

def walk_ast(node, tags):
    """Recursively yields nodes that match any of the given tags."""
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
    """Extracts tokens (leaves) from an AST node."""
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
    """Converts a parameter value from YAML or SV into a canonical string form (base-10 integer if possible)."""
    if isinstance(val, bool):
        return "1" if val else "0"
    
    val_str = str(val).strip()
    # Handle Verilog-style literals like 1'b1, 32'hFF
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
    - Boolean flags indicating supported interfaces (e.g., 'has_sync_axi_slave', 'has_test_mode').
    """
    if not search_paths:
        search_paths = [Path(__file__).parent.parent]
    
    filepath = None
    for sp in search_paths:
        if sp.is_file() and sp.name == f"{component_type}.sv":
            filepath = sp
            break
        elif sp.is_dir():
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
    
    # Unify header extraction since both methods need it (AST needs it for ports)
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
                        # The first token before '=' that is a valid C identifier
                        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', text):
                            param_name = text
                            break
                            
                    if param_name:
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

    # Extract Bender dependencies from comments
    dep_pattern = re.compile(r'(?://|##)\s*BENDER:\s*name="([^"]+)"(?:.*?git="([^"]+)")?(?:.*?rev="([^"]+)")?(?:.*?version="([^"]+)")?')
    for match in dep_pattern.finditer(content):
        dep_name = match.group(1)
        info["dependencies"].setdefault(dep_name, {})
        if match.group(2): info["dependencies"][dep_name]["git"] = match.group(2)
        if match.group(3): info["dependencies"][dep_name]["rev"] = match.group(3)
        if match.group(4): info["dependencies"][dep_name]["version"] = match.group(4)
    
    # Extract local file dependencies
    req_pattern = re.compile(r'(?://|##)\s*OLLIVANDER:\s*require="([^"]+)"')
    for match in req_pattern.finditer(content):
        info["required_files"].append(match.group(1))

    # Clean comments from header_content for safe regex matching
    header_clean = re.sub(r'//.*', '', header_content)
    header_clean = re.sub(r'/\*.*?\*/', '', header_clean, flags=re.DOTALL)

    # =====================================================================
    # PORT NAMES EXTRACTION (AST + Regex Fallback)
    # =====================================================================
    port_names = set()
    info["ports"] = {}
    if ast:
        for port_decl in walk_ast(ast, {"kPortDeclaration", "kPort"}):
            tokens = list(extract_tokens(port_decl))
            
            # Dividiamo i token usando le virgole per gestire dichiarazioni multiple (es: input a, b;)
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
                # Il nome della porta è l'ultimo SymbolIdentifier prima degli array di dimensione (Unpacked)
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

    # Fallback Regex per recuperare le porte nascoste all'interno di chiamate a Macro (kMacroCall)
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
            
    # Aggiungiamo eventuali porte rilevate solo dall'AST (es. multi-porte o macro opache)
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
    else:
        for m in re.finditer(r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)::\*;', header_clean):
            imports.add(m.group(1))
    info["imports"] = list(imports)

    # Detect interfaces based on standardized port naming conventions defined 
    # in the Ollivander "Isle Standardization" guidelines.
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

# ==============================================================================
# 1. PROJECT & TOPOLOGY
# ==============================================================================

class Project(BaseModel):
    """Basic project metadata."""
    name: str
    description: str
    author: str

class GlobalBus(BaseModel):
    """
    Defines the properties of the central interconnect in a Crossbar topology.
    These widths are used to size the global AXI typedefs (macros) in the SV top-level.
    """
    protocol: str
    data_width: int
    addr_width: int
    user_width: int
    mst_id_width: int

class NoCNetwork(BaseModel):
    """Defines the dimensions for a specific NoC physical sub-network."""
    data_width: int
    addr_width: int

class NoCSettings(BaseModel):
    """
    Configuration for Network-on-Chip (NoC) topologies (e.g., FlooNoC).
    Manages multiple parallel networks (e.g., narrow and wide).
    """
    type: str
    routing_algorithm: str
    networks: Dict[str, NoCNetwork]
    default_tile: str

class Topology(BaseModel):
    """Defines the main architectural interconnect style of the SoC."""
    type: Literal["crossbar", "noc"]
    global_bus: Optional[GlobalBus] = None
    noc_settings: Optional[NoCSettings] = None

    @model_validator(mode='after')
    def check_topology_config(self) -> 'Topology':
        if self.type == "crossbar" and not self.global_bus:
            raise ValueError("Topology type 'crossbar' requires a 'global_bus' definition.")
        if self.type == "noc" and not self.noc_settings:
            raise ValueError("Topology type 'noc' requires a 'noc_settings' definition.")
        return self

# ==============================================================================
# 2. SYSTEM MICROARCHITECTURE SETTINGS
# ==============================================================================

class UserMapping(BaseModel):
    """
    Maps the bits of the AXI 'user' sideband signal to specific hardware features
    like Atomics (AMO) and Error Correction (ECC), ensuring system-wide coherence.
    """
    amo_msb: int
    amo_lsb: int
    ecc_err_bit: int

class LlcMicroarch(BaseModel):
    """
    Microarchitectural properties of the Last Level Cache (LLC) to size
    tracking FIFOs and ATOP adapters correctly.
    """
    max_read_txns: int
    max_write_txns: int
    amo_num_cuts: int
    amo_post_cut: Optional[bool] = None

class RegBusMicroarch(BaseModel):
    """
    Microarchitectural properties of the internal Register Bus (RegBus) 
    peripheral interconnect tree.
    """
    max_read_txns: int
    max_write_txns: int
    amo_num_cuts: int
    amo_post_cut: bool

class SystemSettings(BaseModel):
    """Container for all low-level system configuration tuning."""
    user_mapping: UserMapping
    llc: LlcMicroarch
    reg_bus: RegBusMicroarch

# ==============================================================================
# 3. CLOCK TREE
# ==============================================================================

class ClockDomain(BaseModel):
    """
    Defines a single clock routing domain within the SoC.
    It orchestrates the generation of Glitch-Free Muxes and Fractional Dividers.
    """
    name: str
    description: Optional[str] = None
    is_real_time: Optional[bool] = False       # Bypasses SW config registers (always-on, fixed freq)
    source_fll: Optional[int] = None           # Hardwired FLL source index (avoids deadlocks)
    static_div: Optional[int] = None           # Hardwired clock division factor (for static clocks)
    has_mux: bool                              # True = generates a glitch-free mux + selection register
    has_divider: bool                          # True = generates a SW-programmable clock divider
    has_debug_divider: Optional[bool] = False  # Generates a parallel synchronized clock for JTAG/Debug
    default_div: Optional[int] = 1             # Boot division factor
    
    @model_validator(mode='after')
    def normalize_name(self) -> 'ClockDomain':
        if self.name and not self.name.endswith('_clk'):
            self.name = f"{self.name}_clk"
        return self

class ClockTree(BaseModel):
    """Root definition for the SoC clock generation and distribution tree."""
    flls: int                                  # Total number of Frequency Locked Loops available
    domains: List[ClockDomain]

# ==============================================================================
# 4. REGISTERS (Crossbar & NoC variations)
# ==============================================================================

class ExternalRegister(BaseModel):
    """
    A register block physically located outside the generated top-level (e.g., in a padframe).
    Ollivander handles exporting the RegBus ports to reach it.
    """
    name: str
    base_addr: Union[str, int]
    size: Optional[Union[str, int]] = None

class AutoControlGroup(BaseModel):
    """Rules for auto-generating distributed control registers (used mainly in NoC topologies)."""
    name: str
    type: str
    target_component_type: Optional[str] = None
    target_tile_type: Optional[str] = None

class SystemController(BaseModel):
    """
    Unified System Controller definition. Used to generate the main control 
    register file (PCRs) managing resets, AXI isolation, clock gating, and boot addresses.
    It feeds into `carfield_regs.hjson` to generate the SystemRDL block.
    """
    model_config = {"populate_by_name": True}

    name: str
    description: Optional[str] = None
    base_addr: Union[str, int]
    size: Optional[Union[str, int]] = None
    scratch_registers: Optional[int] = 0
    version_registers: Optional[int] = 0
    jedec_id: Optional[Union[str, int]] = 0
    fll_status_regs: Optional[bool] = False
    external_registers: Optional[List[ExternalRegister]] = None
    auto_control_groups: Optional[List[AutoControlGroup]] = Field(None, alias='groups')

# ==============================================================================
# 5. HOST & COMPONENTS
# ==============================================================================

class Component(BaseModel):
    """
    A generic hardware block (Isle/Tile) instantiated in the SoC.
    This is the core building block of Ollivander. It captures functional properties, 
    clock/reset assignments, memory mappings, and interrupt routing.
    """
    name: str                                      # Unique instance name in the SoC
    type: str                                      # Must match the *_isle.sv or *_tile.sv wrapper filename
    base_addr: Optional[Union[str, int]] = None    # Used mainly for APB sub-components
    size: Optional[Union[str, int]] = None         # Used mainly for APB sub-components
    description: Optional[str] = None
    clock_domain: Optional[str] = None             # Automatically wired to the generated clock tree
    reset_domain: Optional[str] = None             # Automatically wired to the generated reset tree
    interfaces: Optional[Dict[str, Any]] = None    # AXI, APB, RegBus, JTAG, etc.
    export_interfaces: Optional[List[str]] = None  # List of raw interfaces to export to top-level I/O
    parameters: Optional[Dict[str, Any]] = None    # Hardware parameters mapped to SystemVerilog
    system_config: Optional[Dict[str, Any]] = None # Isolation, Boot Address, etc.
    features: Optional[Dict[str, Any]] = None      # Custom boolean flags
    defines: Optional[List[str]] = None            # Compilation macros (+define+) required by the IP
    interrupts: Optional[Dict[str, Any]] = None    # IRQ routing mapping
    dedicated_clock_div: Optional[Dict[str, Any]] = None # Specific clock divider (e.g., Ethernet)
    components: Optional[List['Component']] = None # For APB Subsystems
    placement: Optional[Dict[str, Any]] = None     # For NoC Tiles
    logical_placement: Optional[Any] = None        # For NoC Tiles
    noc_connections: Optional[List[str]] = None    # For NoC Tiles
    memory_map: Optional[List[Dict[str, Any]]] = None # For NoC Tiles
    
    @model_validator(mode='after')
    def normalize_domains(self) -> 'Component':
        if self.clock_domain and not self.clock_domain.endswith('_clk'):
            self.clock_domain = f"{self.clock_domain}_clk"
        if self.reset_domain and not self.reset_domain.endswith('_rst'):
            self.reset_domain = f"{self.reset_domain}_rst"
        if self.dedicated_clock_div and 'name' in self.dedicated_clock_div:
            if not self.dedicated_clock_div['name'].endswith('_clk'):
                self.dedicated_clock_div['name'] = f"{self.dedicated_clock_div['name']}_clk"
        return self

# ==============================================================================
# OLLIVANDER ROOT CONFIGURATION
# ==============================================================================

class OllivanderConfig(BaseModel):
    """
    Root Pydantic Model mapping the entire YAML configuration.
    Contains the top-level sections defining the SoC.
    """
    model_config = {"populate_by_name": True}

    project: Project
    topology: Topology
    system_settings: SystemSettings
    clock_tree: ClockTree
    system_controller: Optional[SystemController] = None
    host: Component
    components: Optional[List[Component]] = Field(default_factory=list, alias='tiles')


def validate_soc_components(config: OllivanderConfig, search_paths: List[Path] = None, exclude_dir: str = None, original_types: Dict[str, str] = None):
    """
    Validates the user-defined components against their actual SystemVerilog
    implementations, enforcing strict Hardware-First correctness.
    
    This prevents generating structurally flawed RTL by verifying parameter existence,
    matching fixed localparams against global settings, and validating sync/async ports.
    """
    all_comps = [config.host]
    if config.components:
        all_comps.extend(config.components)
        
    global_bus = config.topology.global_bus
    
    for comp in all_comps:
        c_type = original_types.get(comp.name, comp.type) if original_types else comp.type
        
        # TOPOLOGY ENFORCEMENT: Crossbar cannot use NoC-specific components
        if config.topology.type == "crossbar":
            if c_type.endswith('_subtile') or c_type.endswith('_tile'):
                raise ValueError(
                    f"\n[ARCHITECTURAL ERROR] Component '{comp.name}' is declared as '{c_type}'.\n"
                    f"Components ending in '_subtile' or '_tile' are exclusively for NoC topologies.\n"
                    f"For Crossbar topologies, please use universal components ending in '_isle'."
                )
        
        info = get_isle_info(c_type, search_paths, exclude_dir)
        if not info:
            continue # Skip if file not found
            
        # 1. PARAMETER SUPPORT CHECK: Prevent users from setting parameters in YAML 
        #    that do not physically exist as 'parameter' in the module's SV header.
        if comp.parameters is not None:
            for param, user_val in comp.parameters.items():
                # First, check if the user is trying to override a fixed 'localparam'.
                if param in info["fixed_params"]:
                    fixed_val_clean = info["fixed_params"][param]
                    user_val_clean = _clean_param_val(user_val)

                    if user_val_clean != fixed_val_clean:
                        raise ValueError(
                            f"\n[ARCHITECTURAL ERROR] in component '{comp.name}' ({comp.type}):\n"
                            f"Parameter '{param}' is a fixed 'localparam' in the hardware with value '{info['fixed_params'][param]}'.\n"
                            f"You cannot override it with the value '{user_val}' in the YAML."
                        )
                    
                    # If the values match, it's redundant but not an error.
                    print(f"[INFO] [{comp.name}] Parameter '{param}' is a fixed 'localparam'. The value provided in YAML matches the hardware and is redundant.")
                    continue

                if param not in info["supported_params"]:
                    if not info["supported_params"]:
                        raise ValueError(
                            f"\n[{comp.name}] Component '{comp.type}' is a statically configured block.\n"
                            f"It does not expose any configurable parameters, therefore the 'parameters' key in the YAML is not supported."
                        )
                    else:
                        raise ValueError(
                            f"\n[{comp.name}] Parameter '{param}' is not supported by component '{comp.type}'.\n"
                            f"Valid parameters declared as 'parameter' in the SystemVerilog file: {list(info['supported_params'].keys())}"
                        )
        
        # 2. HARDWARE CONSTRAINTS CHECK: Ensure that component 'localparam's (fixed 
        #    architectural constraints) do not conflict with the global bus geometry.
        if global_bus:
            global_checks = {
                "AxiDataWidth": global_bus.data_width,
                "AxiAddrWidth": global_bus.addr_width,
                "AxiUserWidth": global_bus.user_width
            }
            
            for param_name, global_val in global_checks.items():
                if param_name in info["fixed_params"]:
                    fixed_val_str = info["fixed_params"][param_name]
                    try:
                        fixed_val = int(fixed_val_str)
                    except ValueError:
                        continue # Skip validation if parameter is a macro string
                        
                    if global_val != fixed_val:
                        raise ValueError(
                            f"\n[ARCHITECTURAL ERROR]\n"
                            f"Component '{comp.name}' ({comp.type}) only accepts the fixed value {fixed_val} for '{param_name}'.\n"
                            f"The value {global_val}, configured by the user in the global_bus, is not compatible!"
                        )
                        
        # 3. SYNCHRONICITY & NOC MODE CHECK: Verify that the physical ports defined in the wrapper
        #    support the sync/async connection style and NoC mode requested in the YAML. (Skip Host)
        if comp.name != config.host.name and comp.interfaces:
            host_clk = config.host.clock_domain
            c_clk = comp.clock_domain or host_clk
            
            noc_nets = comp.interfaces.get('noc_networks', {})
            noc_mode = noc_nets.get('noc_mode', 'joined') if isinstance(noc_nets, dict) else 'joined'
            
            has_slave = 'axi_slave' in comp.interfaces
            has_master = 'axi_master' in comp.interfaces
            
            if noc_mode == "dual":
                # Dual Mode Checks
                if has_slave:
                    slvs = comp.interfaces['axi_slave']
                    if isinstance(slvs, dict): slvs = [slvs]
                    for slv in slvs:
                        is_sync = slv.get('sync_domain', True)
                        if is_sync:
                            if not (info.get("has_sync_axi_narrow_slave") or info.get("has_sync_axi_wide_slave")):
                                raise ValueError(f"\n[{comp.name}] Component '{comp.type}' uses noc_mode: 'dual' but lacks synchronous dual AXI slave ports (axi_narrow_req_i / axi_wide_req_i).")
                        else:
                            if not (info.get("has_async_axi_narrow_slave") or info.get("has_async_axi_wide_slave")):
                                raise ValueError(f"\n[{comp.name}] Component '{comp.type}' uses noc_mode: 'dual' but lacks asynchronous dual AXI slave ports.")
                                
                if has_master:
                    if not (info.get("has_sync_axi_narrow_master") or info.get("has_sync_axi_wide_master") or 
                            info.get("has_async_axi_narrow_master") or info.get("has_async_axi_wide_master")):
                        raise ValueError(f"\n[{comp.name}] Component '{comp.type}' uses noc_mode: 'dual' but lacks dual AXI master ports.")
                        
            else:
                # Standard/Joined Mode Checks
                if has_slave:
                    slvs = comp.interfaces['axi_slave']
                    if isinstance(slvs, dict): slvs = [slvs]
                    for slv in slvs:
                        is_sync = slv.get('sync_domain', True)
                        if is_sync:
                            if not info.get("has_sync_axi_slave"):
                                raise ValueError(f"\n[{comp.name}] Component '{comp.type}' does not expose synchronous AXI ports (axi_req_i/axi_resp_o), but YAML defines it as sync_domain: true.")
                            if c_clk != host_clk:
                                raise ValueError(f"\n[{comp.name}] Component '{comp.type}' is sync_domain: true, but its clock domain ('{c_clk}') differs from host ('{host_clk}').")
                        else:
                            if not info.get("has_async_axi_slave"):
                                raise ValueError(f"\n[{comp.name}] Component '{comp.type}' does not expose asynchronous AXI ports (async_axi_in_*), but YAML defines it as sync_domain: false.")
                            
                            if c_clk == host_clk:
                                print(f"[WARNING] [{comp.name}] Uses asynchronous AXI interfaces (CDC), but its clock domain ('{c_clk}') matches the host. This adds unnecessary latency/area unless intended as an elastic buffer for floorplanning.")

            # Dual Mode Parameter Enforcement
            if noc_mode == "dual":
                all_params = list(info.get('supported_params', {}).keys()) + list(info.get('fixed_params', {}).keys())
                has_dual_params = any(p.startswith('AxiNarrow') or p.startswith('AxiWide') for p in all_params)
                if not has_dual_params:
                    raise ValueError(f"\n[{comp.name}] Component '{comp.type}' uses noc_mode: 'dual' but does not expose any 'AxiNarrow...' or 'AxiWide...' parameters in its SV header.")
                            
        # 4. INTERRUPT PIN CHECK: Verify that any referenced interrupt port physically exists 
        #    on the SystemVerilog module's header.
        if comp.interrupts:
            for irq_name, irq_cfg in comp.interrupts.items():
                source = irq_cfg.get('source')
                if source and str(source).strip().lower() != "none":
                    source_str = str(source).strip()
                    matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', source_str)
                    
                    for src_comp_name, src_port_name in matches:
                        src_comp = next((c for c in all_comps if c.name == src_comp_name), None)
                        if not src_comp:
                            for c in all_comps:
                                if c.components:
                                    src_comp = next((sub for sub in c.components if sub.name == src_comp_name), None)
                                    if src_comp: break
                        
                        if src_comp:
                            src_info = get_isle_info(src_comp.type, search_paths, exclude_dir)
                            if src_info:
                                src_header = src_info.get("header_content", "")
                                if not re.search(r'\b' + re.escape(src_port_name) + r'\b', src_header):
                                    raise ValueError(
                                        f"\n[INTERRUPT VALIDATION ERROR]\n"
                                        f"Component '{comp.name}' maps interrupt '{irq_name}' to '{src_comp_name}.{src_port_name}'.\n"
                                        f"However, the port '{src_port_name}' does not exist in the SystemVerilog header of '{src_comp.type}'!"
                                    )
                elif not source:
                    port_name = irq_cfg.get('port', irq_name)
                    if not re.search(r'\b' + re.escape(port_name) + r'\b', info.get("header_content", "")):
                        raise ValueError(
                            f"\n[INTERRUPT VALIDATION ERROR]\n"
                            f"Component '{comp.name}' declares an output interrupt on port '{port_name}'.\n"
                            f"However, the port '{port_name}' does not exist in its SystemVerilog header!"
                        )
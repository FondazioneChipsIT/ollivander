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
from core.sv_parser import get_isle_info


# ==============================================================================
# 1. PROJECT & TOPOLOGY
# ==============================================================================

class MacroExport(BaseModel):
    """Defines an exported AXI interface and its internal connection target."""
    bus_type: Literal["standard", "narrow", "wide"]
    target: str

class MacroSettings(BaseModel):
    """
    Defines how the SoC should be wrapped when exported as a macro IP.
    """
    export_type: Literal["isle", "subtile"] = "isle"
    masters: Optional[List[MacroExport]] = Field(default_factory=list)
    slaves: Optional[List[MacroExport]] = Field(default_factory=list)
    
    @model_validator(mode='after')
    def check_macro(self) -> 'MacroSettings':
        if not self.masters and not self.slaves:
            raise ValueError("A macro must export at least one AXI master or slave interface.")
        return self

class Project(BaseModel):
    """
    Basic project metadata.
    Used for naming the top-level module and global SV packages.
    """
    name: str
    description: str
    author: str
    build_mode: Literal["standalone", "macro"] = "standalone"
    macro_settings: Optional[MacroSettings] = None
    vendor: str = "Ollivander"
    library: str = "SoC"
    version: str = "1.0"

    @property
    def top_level_module_name(self) -> str:
        """
        Dynamically computes the top-level module name based on build_mode and export_type.
        """
        if self.build_mode == "macro" and self.macro_settings:
            return f"{self.name}_{self.macro_settings.export_type}"
        return self.name


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
    """
    Container for all low-level system configuration tuning.
    These parameters affect the generation of hardware adapters and 
    ensure compliance with the requested AXI/RegBus protocols.
    """
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
    source_gen: Optional[int] = None           # Hardwired Clock Generator source index (useful to avoid boot deadlocks)
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
    generators: int                            # Total number of analog Clock Generators (PLLs/FLLs) available
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
    """
    Rules for auto-generating distributed control registers (used mainly in NoC topologies).
    Aggregates control signals of multiple identical tiles into a single packed CSR.
    """
    name: str
    type: str
    target_component_type: Optional[str] = None
    target_tile_type: Optional[str] = None

class SystemController(BaseModel):
    """
    Unified System Controller definition. Used to generate the main control 
    register file (PCRs) managing resets, AXI isolation, clock gating, and boot addresses.
    It is used to automatically generate the SystemRDL specification, which is then
    compiled by PeakRDL into SystemVerilog RTL and C headers.
    """
    model_config = {"populate_by_name": True}

    name: str
    description: Optional[str] = None
    base_addr: Union[str, int]
    size: Optional[Union[str, int]] = None
    scratch_registers: Optional[int] = 0
    version_registers: Optional[int] = 0
    jedec_id: Optional[Union[str, int]] = 0
    clk_gen_status_regs: Optional[bool] = False
    external_registers: Optional[List[ExternalRegister]] = None
    auto_control_groups: Optional[List[AutoControlGroup]] = Field(None, alias='groups')

# ==============================================================================
# 5. PADFRAME & PINMUX (Padrick Integration)
# ==============================================================================

def parse_pad_csv(csv_path: Path, domains_list: list) -> dict:
    import csv
    if not csv_path.is_file():
        print(f"\n[ERROR] Pad CSV file not found: {csv_path}")
        sys.exit(1)
        
    domain_names = {dom.name for dom in domains_list}
    result = {name: [] for name in domain_names}
    
    core_columns = {"domain", "pad name", "type", "multiple", "is static", "default port", "description"}
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print(f"\n[ERROR] Pad CSV file '{csv_path.name}' is empty or invalid.")
            sys.exit(1)
            
        header_map = {h.strip().lower(): h for h in reader.fieldnames}
        
        required = ["domain", "pad name", "type", "is static"]
        for req in required:
            if req not in header_map:
                print(f"\n[ERROR] Pad CSV file is missing required column: '{req}'. Available: {reader.fieldnames}")
                sys.exit(1)
                
        connection_cols = []
        for h in reader.fieldnames:
            h_strip = h.strip()
            if h_strip.lower() not in core_columns:
                connection_cols.append(h_strip)
                
        for row_idx, row in enumerate(reader, start=2):
            domain_key = header_map.get("domain")
            domain_val = row[domain_key].strip() if row.get(domain_key) else ""
            if not domain_val:
                continue
                
            if domain_val not in domain_names:
                print(f"\n[ERROR] [CSV Error] Row {row_idx}: Domain '{domain_val}' is not defined in the SoC configuration domains: {list(domain_names)}")
                sys.exit(1)
                
            name_key = header_map.get("pad name")
            pad_name = row[name_key].strip() if row.get(name_key) else ""
            if not pad_name:
                print(f"\n[ERROR] [CSV Error] Row {row_idx}: Missing 'Pad Name'.")
                sys.exit(1)
                
            type_key = header_map.get("type")
            pad_type = row[type_key].strip() if row.get(type_key) else ""
            if not pad_type:
                print(f"\n[ERROR] [CSV Error] Row {row_idx}: Missing 'Type' for pad '{pad_name}'.")
                sys.exit(1)
                
            is_static_key = header_map.get("is static")
            is_static_str = row[is_static_key].strip().lower() if row.get(is_static_key) else "false"
            is_static = is_static_str in ("true", "1", "yes")
            
            multiple_key = header_map.get("multiple")
            multiple_val = 1
            if multiple_key and row.get(multiple_key):
                m_str = row[multiple_key].strip()
                if m_str:
                    try:
                        multiple_val = int(m_str)
                    except ValueError:
                        print(f"\n[ERROR] [CSV Error] Row {row_idx}: Invalid 'Multiple' value '{m_str}'. Must be an integer.")
                        sys.exit(1)
                        
            default_port_key = header_map.get("default port")
            default_port_val = row[default_port_key].strip() if (default_port_key and row.get(default_port_key)) else ""
            
            description_key = header_map.get("description")
            desc_val = row[description_key].strip() if (description_key and row.get(description_key)) else ""
            
            connections = {}
            for col in connection_cols:
                val = row[col].strip() if row.get(col) else ""
                if val:
                    connections[col] = val
                    
            if not is_static and connections:
                print(f"\n[ERROR] [CSV Error] Row {row_idx}: Pad '{pad_name}' is marked multiplexed (Is Static = False) but has static connections: {connections}. Multiplexed pads must have empty connection columns.")
                sys.exit(1)
                
            if is_static and default_port_val:
                print(f"\n[ERROR] [CSV Error] Row {row_idx}: Pad '{pad_name}' is marked static (Is Static = True) but has a 'Default Port' specified: '{default_port_val}'. Default ports are only for multiplexed pads.")
                sys.exit(1)
                
            pad_dict = {
                "name": pad_name,
                "pad_type": pad_type,
                "is_static": is_static,
            }
            if multiple_val > 1:
                pad_dict["multiple"] = multiple_val
            if desc_val:
                pad_dict["description"] = desc_val
            if default_port_val:
                pad_dict["default_port"] = default_port_val
            if connections:
                pad_dict["connections"] = connections
                
            result[domain_val].append(pad_dict)
            
    return result

def parse_pad_py(py_path: Path) -> dict:
    import importlib.util
    import sys
    
    if not py_path.is_file():
        print(f"\n[ERROR] Pad Python file not found: {py_path}")
        sys.exit(1)
        
    try:
        spec = importlib.util.spec_from_file_location("dynamic_pad_config", py_path)
        if spec is None or spec.loader is None:
            print(f"\n[ERROR] [Python Error] Failed to load spec for script '{py_path.name}'.")
            sys.exit(1)
        module = importlib.util.module_from_spec(spec)
        sys.modules["dynamic_pad_config"] = module
        spec.loader.exec_module(module)
    except Exception as e:
        import traceback
        print(f"\n[ERROR] [Python Error] Execution of user padlist script '{py_path.name}' failed:")
        traceback.print_exc()
        sys.exit(1)
        
    if not hasattr(module, "pad_domains"):
        print(f"\n[ERROR] [Python Error] Script '{py_path.name}' must define a global variable 'pad_domains' containing the padlist mapping.")
        sys.exit(1)
        
    pad_domains = getattr(module, "pad_domains")
    if not isinstance(pad_domains, dict):
        print(f"\n[ERROR] [Python Error] 'pad_domains' in script '{py_path.name}' must be a dictionary.")
        sys.exit(1)
        
    for dom_name, pads in pad_domains.items():
        if not isinstance(pads, list):
            print(f"\n[ERROR] [Python Error] 'pad_domains[\"{dom_name}\"]' must be a list of dictionaries.")
            sys.exit(1)
        for idx, pad in enumerate(pads):
            if not isinstance(pad, dict):
                print(f"\n[ERROR] [Python Error] Pad at index {idx} in domain '{dom_name}' must be a dictionary. Found type: {type(pad)}")
                sys.exit(1)
            if "name" not in pad or "pad_type" not in pad:
                print(f"\n[ERROR] [Python Error] Pad at index {idx} in domain '{dom_name}' is missing required fields 'name' or 'pad_type': {pad}")
                sys.exit(1)
            is_static = pad.get("is_static", False)
            connections = pad.get("connections", {})
            default_port = pad.get("default_port", "")
            if not is_static and connections:
                print(f"\n[ERROR] [Python Error] Pad '{pad['name']}' in domain '{dom_name}' is marked multiplexed but has static connections: {connections}.")
                sys.exit(1)
            if is_static and default_port:
                print(f"\n[ERROR] [Python Error] Pad '{pad['name']}' in domain '{dom_name}' is marked static but has default_port: '{default_port}'.")
                sys.exit(1)
                
    return pad_domains

class PadDomainConfig(BaseModel):
    """
    Configuration for a single Padframe domain (power/voltage domain).
    """
    name: str
    tech: str
    pad_list: Optional[str] = None

class PadframeConfig(BaseModel):
    """
    Configuration for the Padrick Padframe and Pinmux generator.
    Delegates the physical pad definitions (technology macros, orientation, etc.) 
    to a native Padrick YAML configuration file, maintaining the SoC YAML technology-agnostic.
    """
    name: str
    description: Optional[str] = None
    base_addr: Union[str, int]                 # RegBus base address for pinmux CSRs
    size: Optional[Union[str, int]] = 0x1000
    sync_domain: Optional[bool] = False        # True = Host Clock, False = Uses async CDC adapter
    domains: Optional[List[PadDomainConfig]] = None
    padrick_cfg: Optional[str] = None          # Path to a custom Padrick config_top.yml (overrides domains)
    pad_csv: Optional[str] = None              # Path to a CSV file defining the padlist dynamically
    pad_py: Optional[str] = None               # Path to a Python file defining the padlist dynamically
    header_file: Optional[str] = None          # Path to a text file for the RTL header (auto-generates standard license if None)

    @model_validator(mode='after')
    def check_padrick_config(self) -> 'PadframeConfig':
        if not self.padrick_cfg:
            if not self.domains:
                raise ValueError("Padframe requires either 'padrick_cfg' or a 'domains' list.")
            for dom in self.domains:
                if not self.pad_csv and not self.pad_py and not dom.pad_list:
                    raise ValueError(f"Domain '{dom.name}' requires 'pad_list' since neither 'pad_csv' nor 'pad_py' is specified.")
        return self

    def get_pad_list_data(self, domain_name: str, config_dir: Path) -> list:
        if self.pad_csv:
            csv_path = config_dir / self.pad_csv
            csv_pads = parse_pad_csv(csv_path, self.domains or [])
            return csv_pads.get(domain_name, [])
        elif self.pad_py:
            py_path = config_dir / self.pad_py
            py_pads = parse_pad_py(py_path)
            return py_pads.get(domain_name, [])
        else:
            dom = next((d for d in (self.domains or []) if d.name == domain_name), None)
            if not dom or not dom.pad_list:
                return []
            import yaml
            pl_file = config_dir / dom.pad_list
            if not pl_file.is_file():
                return []
            return yaml.safe_load(pl_file.read_text(encoding='utf-8')) or []

# ==============================================================================
# 5. HOST & COMPONENTS
# ==============================================================================

class Component(BaseModel):
    """
    A generic hardware block (Isle/Tile) instantiated in the SoC.
    This is the core building block of Ollivander. It captures functional properties, 
    clock/reset assignments, memory mappings, and interrupt routing.
    The 'type' field must strictly match the name of the underlying SystemVerilog module.
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
    components: Optional[List['Component']] = None # Nested sub-components (e.g., for APB Subsystems)
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
    Contains the top-level sections defining the SoC and acts as the 
    in-memory database for the entire generation process.
    """
    model_config = {"populate_by_name": True}

    project: Project
    topology: Topology
    system_settings: SystemSettings
    clock_tree: ClockTree
    system_controller: Optional[SystemController] = None
    padframe: Optional[PadframeConfig] = None
    host: Component
    components: Optional[List[Component]] = Field(default_factory=list, alias='tiles')
    testbench: Optional[Dict[str, Any]] = None
    software_stack: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def enforce_macro_rules(self) -> 'OllivanderConfig':
        if self.project.build_mode == "macro":
            if self.padframe is not None:
                print("[INFO] Build mode is 'macro'. Forcing padframe to None (Phase 7 and 8 will be skipped).")
                self.padframe = None
        return self

    # Allows Mako templates to safely use config.get("key", default) as if it were a dictionary
    def get(self, key, default=None):
        return getattr(self, key, default)


def validate_soc_components(config: OllivanderConfig, search_paths: List[Path] = None, exclude_dir: str = None, original_types: Dict[str, str] = None):
    """
    Validates the user-defined components against their actual SystemVerilog
    implementations, enforcing strict Hardware-First correctness.
    
    This prevents generating structurally flawed RTL by verifying parameter existence,
    matching fixed localparams against global settings, and validating sync/async ports
    before any templating occurs.
    """
    all_comps = [config.host]
    if config.components:
        all_comps.extend(config.components)
        
    global_bus = config.topology.global_bus
    
    for comp in all_comps:
        # If the component was wrapped in a NoC Tile during Phase 1, we must validate
        # the underlying original user IP (the Isle), not the auto-generated Tile wrapper.
        c_type = original_types.get(comp.name, comp.type) if original_types else comp.type

        if config.project.build_mode == "macro" and config.project.macro_settings:
            if config.topology.type == "crossbar" and config.project.macro_settings.export_type != "isle":
                raise ValueError("Projects with 'crossbar' topology can only be exported as 'isle' macros.")
        
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
                # Localparams represent hard architectural limits of the IP (e.g. FIFO depth)
                # or structural choices that cannot be altered from the top-level instantiation.
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
        #    support the sync/async connection style and NoC mode requested in the YAML.
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
        #    on the SystemVerilog module's header to avoid top-level wiring errors.
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
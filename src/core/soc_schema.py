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
# 0. VALIDATION POLICY
# ==============================================================================

class StrictModel(BaseModel):
    """Base class for every block of the SoC description.

    Pydantic ignores unknown keys by default, which turns a mistyped field into a silently
    missing one: 'data_widht: 128' used to be accepted and dropped, leaving the bus at its
    default width with nothing reported. Forbidding extras makes the generator name the
    offending key and its path instead, at the only moment when the user can still act on it.

    This does not reach the blocks declared 'Dict[str, Any]' (interfaces, system_config, features,
    placement, dedicated_clock_div, testbench, software_stack): there is no field list to check
    them against, so those are validated separately by validate_untyped_blocks below.
    """
    model_config = {"extra": "forbid"}


# ==============================================================================
# 1. PROJECT & TOPOLOGY
# ==============================================================================

class MacroExport(StrictModel):
    """Defines an exported AXI interface and its internal connection target."""
    bus_type: Literal["standard", "narrow", "wide"]
    target: str

class MacroSettings(StrictModel):
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

class Project(StrictModel):
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

    @property
    def soc_pkg_name(self) -> str:
        """
        Name of the global SoC SystemVerilog package.

        It follows the same suffixing rule as `top_level_module_name`, so that a
        "macro" build never collides with the "standalone" build of the same
        project: `crux` yields `crux_soc_pkg`, while the same project built as a
        macro with export_type "isle" yields `crux_isle_soc_pkg`. Both the emitted
        file name and every reference to the package are derived from this single
        property, so the two builds can coexist in one simulation library.
        """
        return f"{self.top_level_module_name}_soc_pkg"

    @property
    def module_prefix(self) -> str:
        """
        Prefix applied to every SystemVerilog module Ollivander generates for this SoC
        (tile wrappers, isle wrappers, the dummy tile, the reset tree).

        Follows the same suffixing rule as `top_level_module_name`, and for the same
        reason as `soc_pkg_name`: a parent SoC may instantiate two macros exported from
        the same project, and every module of one must be distinguishable from its
        counterpart in the other. Using the bare project name would emit, for instance,
        two different `mesh_manager_tile` modules whose system-register ports carry
        incompatible struct types.
        """
        return self.top_level_module_name

    @property
    def noc_pkg_name(self) -> str:
        """
        Name of the FlooNoC package generated for this SoC.

        Follows the same suffixing rule as `soc_pkg_name` and for the same reason: a
        parent SoC may instantiate two macros exported from the same project (an "isle"
        and a "subtile" variant, say) and must compile both into one library. Deriving
        the name from the bare project name would give them identical package names with
        different contents, and only one would survive.

        FlooGen builds the package name from the `name` field of its own configuration,
        so that field must be fed this value rather than the project name.
        """
        return f"floo_{self.top_level_module_name}_noc_pkg"

    @property
    def bender_pkg_name(self) -> str:
        """
        Name of the Bender package declared in the generated manifest. Suffixed like the
        top-level module so that two macros exported from the same project do not declare
        two different Bender packages under one name.
        """
        return f"{self.top_level_module_name}_soc"


class GlobalBus(StrictModel):
    """
    Defines the properties of the central interconnect in a Crossbar topology.
    These widths are used to size the global AXI typedefs (macros) in the SV top-level.
    """
    protocol: str
    data_width: int
    addr_width: int
    user_width: int
    mst_id_width: int

class NoCNetwork(StrictModel):
    """Defines the dimensions for a specific NoC physical sub-network."""
    data_width: int
    addr_width: int
    # None means "derive it": the width the attached macros impose, with FlooNoC's own
    # default as the floor (src/core/macro_boundary.py). The default used to be 4, which
    # made "not declared" indistinguishable from "declared 4" and left the derivation
    # unreachable - and silently gave the wide network 4 where FlooNoC uses 3.
    id_width: Optional[int] = None

class NoCSettings(StrictModel):
    """
    Configuration for Network-on-Chip (NoC) topologies (e.g., FlooNoC).
    Manages multiple parallel networks (e.g., narrow and wide).
    """
    type: str
    routing_algorithm: str
    networks: Dict[str, NoCNetwork]
    default_tile: str

class Topology(StrictModel):
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
        if self.type == "noc" and self.noc_settings:
            # Ollivander emits a FlooNoC of type "narrow-wide", with the four protocols
            # narrow_in/narrow_out/wide_in/wide_out, so both networks are structurally required by
            # what is generated rather than merely conventional. Leaving one out used to be
            # accepted: the templates fell back to inventing its widths, and the result was a
            # network the description never asked for, sized by numbers nobody chose.
            missing = {"narrow", "wide"} - set(self.noc_settings.networks or {})
            if missing:
                raise ValueError(
                    f"Topology type 'noc' requires both a 'narrow' and a 'wide' network in "
                    f"'noc_settings.networks'; missing: {', '.join(sorted(missing))}.")
        return self

# ==============================================================================
# 2. SYSTEM MICROARCHITECTURE SETTINGS
# ==============================================================================

class UserMapping(StrictModel):
    """
    Maps the bits of the AXI 'user' sideband signal to specific hardware features
    like Atomics (AMO) and Error Correction (ECC), ensuring system-wide coherence.
    """
    amo_msb: int
    amo_lsb: int
    ecc_err_bit: int

class LlcMicroarch(StrictModel):
    """
    Microarchitectural properties of the Last Level Cache (LLC) to size
    tracking FIFOs and ATOP adapters correctly.
    """
    max_read_txns: int
    max_write_txns: int
    amo_num_cuts: int
    amo_post_cut: Optional[bool] = None

class RegBusMicroarch(StrictModel):
    """
    Microarchitectural properties of the internal Register Bus (RegBus) 
    peripheral interconnect tree.
    """
    max_read_txns: int
    max_write_txns: int
    amo_num_cuts: int
    amo_post_cut: bool

class SystemSettings(StrictModel):
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

class ClockDomain(StrictModel):
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

class ClockTree(StrictModel):
    """Root definition for the SoC clock generation and distribution tree."""
    generators: int                            # Total number of analog Clock Generators (PLLs/FLLs) available
    generator_periods_ns: Optional[List[float]] = None
    rt_clk_period_ns: Optional[float] = 1000.0  # Real-Time Clock simulation period in ns (testbench only)
    domains: List[ClockDomain]

# ==============================================================================
# 4. REGISTERS (Crossbar & NoC variations)
# ==============================================================================

class ExternalRegister(StrictModel):
    """
    A register block physically located outside the generated top-level (e.g., in a padframe).
    Ollivander handles exporting the RegBus ports to reach it.
    """
    name: str
    base_addr: Union[str, int]
    size: Optional[Union[str, int]] = None

class AutoControlGroup(StrictModel):
    """
    Rules for auto-generating distributed control registers (used mainly in NoC topologies).
    Aggregates control signals of multiple identical tiles into a single packed CSR.
    """
    name: str
    type: str
    target_component_type: Optional[str] = None
    target_tile_type: Optional[str] = None

class SystemController(StrictModel):
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

    # Power-on state of every clock-enable / software-reset register generated by the
    # System Controller, applied identically to managed clock domains and to auto
    # control groups so the two mechanisms can never drift apart.
    #
    #   "gated"   : clocks off and resets asserted at power-on. Safe hardware default
    #               and the behaviour of the gwaihir reference SoC; software (or an
    #               external agent such as JTAG, or the `clk_rst_bypass_i` pin) must
    #               bring the controlled blocks up before using them.
    #   "enabled" : clocks running and resets released at power-on, so the SoC comes
    #               up without any CSR write. Convenient for bring-up, but leaves
    #               every controlled block powered from reset.
    power_on_state: Literal["gated", "enabled"] = "gated"

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

class PadDomainConfig(StrictModel):
    """
    Configuration for a single Padframe domain (power/voltage domain).
    """
    name: str
    tech: str
    pad_list: Optional[str] = None

class PadframeConfig(StrictModel):
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

class Component(StrictModel):
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
    isa: Optional[str] = None                      # Compiler ISA override (e.g. rv64imafdc)
    abi: Optional[str] = None                      # Compiler ABI override (e.g. lp64d)
    cmodel: Optional[str] = None                   # Compiler code model override (e.g. medany)
    
    @property
    def num_instances(self) -> int:
        """
        Number of physical instances this component expands into.

        A NoC component may declare its placement either as a single coordinate or
        as one or more rectangular boxes, each box expanding into one instance per
        grid cell. Components without a logical placement (the crossbar case) are a
        single instance. Mirrors the expansion performed by the NoC IR builder, and
        is what sizes the packed control registers of an auto control group.
        """
        placement = self.placement or {}
        logical = placement.get('logical')
        if not logical:
            return 1
        items = logical if isinstance(logical, list) else [logical]
        count = 0
        for item in items:
            if 'box' in item:
                b = item['box']
                count += (b['x_end'] - b['x_start'] + 1) * (b['y_end'] - b['y_start'] + 1)
            else:
                count += 1
        return count

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

class OllivanderConfig(StrictModel):
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

    @property
    def managed_clock_domains(self) -> List[ClockDomain]:
        """
        Clock domains served by the global reset tree.

        Real-time domains are excluded because they are free-running and must never
        be gated or software-reset. The host's own domain is excluded because it has
        a dedicated root reset generator (`i_host_rstgen`): the host must come up
        before any software can drive the control CSRs.

        A SoC whose only non-real-time domain is the host's therefore has NO managed
        domain, and consequently no reset tree at all. That is a legitimate
        configuration (the gwaihir reference NoC SoC is built exactly this way), not
        a degenerate one, so every consumer must handle the empty list.
        """
        host_clk = self.host.clock_domain or "system_clk"
        return [d for d in self.clock_tree.domains if not d.is_real_time and d.name != host_clk]

    @property
    def has_reset_tree(self) -> bool:
        """
        True when the SoC instantiates the `<name>_rstgen` global reset tree.

        Single source of truth shared by the generator and the Mako templates, so
        that the RTL, the Bender manifest and the testbench never disagree on
        whether the tree (and the `rsts_n` / `pwr_on_rsts_n` vectors it drives)
        exists.
        """
        return len(self.managed_clock_domains) > 0

    def control_group_width(self, group, original_isle_types: Optional[Dict[str, str]] = None) -> int:
        """
        Number of tiles controlled by an auto control group, i.e. the width of its
        packed `<group>_clk_en` / `<group>_rst` registers.

        A group targets a component *type*, and by the time the registers are
        emitted the NoC components have already been wrapped in Tile wrappers, so
        the original (pre-wrap) type is matched as well. This is the same matching
        rule used by the NoC IR builder when it assigns each instance its bit index,
        which is what guarantees the register is exactly wide enough to hold them.
        """
        original_isle_types = original_isle_types or {}
        width = 0
        for comp in (self.components or []):
            orig_type = original_isle_types.get(comp.name, comp.type)
            candidates = [comp.type, orig_type,
                          orig_type.replace('_isle', '_tile').replace('_subtile', '_tile')]
            if group.target_component_type in candidates:
                width += comp.num_instances
        # Never emit a zero-width field: a group that currently matches nothing still
        # needs a legal (single-bit) register.
        return max(width, 1)

    @property
    def gated_at_power_on(self) -> bool:
        """
        True when clocks are gated and resets asserted at power-on, i.e. software
        must explicitly bring up the controlled domains and tiles.

        Defaults to the safe hardware behaviour; see SystemController.power_on_state.
        """
        if not self.system_controller:
            return False
        return self.system_controller.power_on_state == "gated"

    # Allows Mako templates to safely use config.get("key", default) as if it were a dictionary
    def get(self, key, default=None):
        return getattr(self, key, default)


def _suggest(name: str, candidates) -> str:
    """Propose the closest declared name, so a typo reads as one rather than as a mystery."""
    import difflib
    match = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.5)
    return f" Did you mean '{match[0]}'?" if match else \
           (f" Declared: {', '.join(sorted(candidates))}." if candidates else "")


def validate_cross_references(config: OllivanderConfig):
    """Check the references the description makes by name against what it declares.

    Forbidding unknown keys catches a misspelled *field*; it cannot catch a misspelled *value*
    that names something else in the same file. Those are the more dangerous of the two, because
    several of them are used directly as identifiers in the generated RTL: a component whose
    'clock_domain' names a domain that does not exist is wired to a signal nobody declares, and
    since the generated sources do not set `default_nettype none`, that signal becomes an
    implicit wire - a peripheral silently left with a floating clock, with no message at any
    stage. Every check below therefore reports at generation time, where the user can act on it.

    Note that the '_clk' suffix is appended by the model validators of both ClockDomain and
    Component, so the comparison happens between normalized names; messages strip it again, to
    quote the user their own spelling.
    """
    errors = []

    declared_domains = {d.name for d in (config.clock_tree.domains or [])} if config.clock_tree else set()
    all_comps = [config.host] + (config.components or [])

    for comp in all_comps:
        # An unset clock_domain is legitimate and inherits the host's (see managed_clock_domains),
        # and a 'dedicated_clock_div' *declares* a derived clock rather than referencing one, so
        # neither takes part in this check.
        if comp.clock_domain and comp.clock_domain not in declared_domains:
            bare = comp.clock_domain[:-4] if comp.clock_domain.endswith('_clk') else comp.clock_domain
            bare_declared = {d[:-4] if d.endswith('_clk') else d for d in declared_domains}
            errors.append(f"[{comp.name}] clock_domain '{bare}' is not declared in clock_tree.domains."
                          f"{_suggest(bare, bare_declared)}")

    # In a NoC, an AXI port and the network it rides on are two halves of one statement: the
    # component says it has a master port, and 'noc_networks' says which network that port injects
    # into. Declaring one without the other used to be accepted, and the generator then wired the
    # port to whichever network came first - in super_mesh that connected the Crux macro's 64-bit
    # master to the 512-bit wide injection, a 280-bit struct on a 751-bit port, reported by nothing
    # because no traffic exercised it. Neither half is optional, and neither implies the other.
    if config.topology.type == "noc":
        for comp in all_comps:
            ifaces = comp.interfaces or {}
            networks = ifaces.get('noc_networks') or {}
            if not isinstance(networks, dict):
                continue
            for port, key in (('axi_master', 'master'), ('axi_slave', 'slave')):
                declares_port = bool(ifaces.get(port))
                declares_net = bool(networks.get(key))
                if declares_port and not declares_net:
                    errors.append(f"[{comp.name}] declares '{port}' but noc_networks names no"
                                  f" '{key}' network for it to use.")
                elif declares_net and not declares_port:
                    errors.append(f"[{comp.name}] noc_networks lists a '{key}' network"
                                  f" ({networks[key]}) but the component declares no '{port}'.")

    boot_memory = (config.software_stack or {}).get('boot_memory')
    if boot_memory:
        comp_names = {c.name for c in all_comps}
        if boot_memory not in comp_names:
            errors.append(f"[software_stack] boot_memory '{boot_memory}' is not a component of this SoC."
                          f"{_suggest(boot_memory, comp_names)}")

    if errors:
        raise ValueError("\n".join(f"\n{e}" for e in errors))


# The entries each untyped block accepts. Forbidding unknown *fields* cannot reach these: they are
# keys of 'Dict[str, Any]' members, so 'axi_slaves' is not a misspelled field but an unknown
# dictionary entry, and Pydantic has no list to check it against. Every set below is exactly what
# the generator and the templates read, which is the point: an entry outside it is inert by
# construction, meaning the user asked for something nothing implements. Extending a set is
# therefore part of implementing the feature that reads it, never a step taken on its own.
#
# 'parameters' and 'interrupts' are deliberately absent. Their keys are SystemVerilog names, and
# both are already validated against the module itself - an unsupported parameter and a
# non-existent interrupt port are each fatal today - so checking them against a hardcoded list
# would be strictly worse than checking them against the hardware.
# The shape language used below is deliberately tiny: a Python type means "a value of this type",
# a one-element list means "a list of that shape" (a single entry may also be written bare, which
# the generator accepts), and a dict means "a mapping whose keys are exactly these". That is
# enough to describe every one of these blocks, and it keeps them as plain dictionaries at
# run time - the alternative, real Pydantic models, would have to be threaded through 123
# dictionary-style accesses of 'interfaces' alone, across Python and Mako, for no additional
# validation. That refactor is now internal cleanup rather than a correctness matter.
_ADDR_RANGE = {"name": str, "base_addr": int, "size": int, "size_per_instance": int,
               "ports": int, "sync_domain": bool}
_PLACEMENT_NODE = {"x": int, "y": int,
                   "box": {"x_start": int, "x_end": int, "y_start": int, "y_end": int}}

_COMPONENT_BLOCK_SPEC = {
    "interfaces": {
        "axi_master": bool,
        "axi_slave": [_ADDR_RANGE],
        "llc_port": [_ADDR_RANGE],
        # 'external' marks a register block whose bus is exported at the chip boundary instead of
        # being driven internally, and only a register-bus slave can be one.
        "regbus_slave": [dict(_ADDR_RANGE, external=bool)],
        "noc_networks": {"master": [str], "slave": [str], "noc_mode": str},
    },
    "system_config": {"boot_addr": int, "boot_enable": bool, "debug_req": bool,
                      "fetch_enable": bool, "has_busy_status": bool, "has_eoc_status": bool,
                      "is_l2_mem": bool, "isolate": bool},
    "features": {"error_slaves": [str], "multicast_target": bool, "terminate_ports": [str]},
    "placement": {"logical": [_PLACEMENT_NODE]},
    "dedicated_clock_div": {"name": str, "default_div": int, "port": str},
}

_ROOT_BLOCK_SPEC = {
    "testbench": {"boot_force_delay_ns": int, "boot_force_fast_delay_ns": int,
                  "boot_timeout_ns": int, "boot_timeout_fast_ns": int, "sim_timeout_ns": int,
                  "preload_memories": [{"instance": str, "file": str}]},
    "software_stack": {"toolchain": str, "boot_memory": str,
                       "test_app": {"name": str, "auto_generate_c": bool}},
}


def _check_shape(spec, value, where, errors):
    """Match one value against the shape language described above, collecting every mismatch."""
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            errors.append(f"{where} should be a mapping, not {type(value).__name__}.")
            return
        for key, item in value.items():
            if key not in spec:
                errors.append(f"{where} does not accept the entry '{key}'.{_suggest(key, spec)}")
            else:
                _check_shape(spec[key], item, f"{where}.{key}", errors)
    elif isinstance(spec, list):
        # A lone entry written without its surrounding list is accepted by the generator, so it is
        # accepted here too rather than reported as a shape error.
        for i, item in enumerate(value if isinstance(value, list) else [value]):
            _check_shape(spec[0], item, f"{where}[{i}]", errors)
    elif spec is bool:
        if not isinstance(value, bool):
            errors.append(f"{where} should be true or false, not {type(value).__name__}.")
    elif spec is int:
        # bool is a subclass of int in Python, so it has to be excluded explicitly: 'size: true'
        # is a mistake, not a zero-or-one size.
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{where} should be an integer, not {type(value).__name__}.")
    elif spec is str and not isinstance(value, str):
        errors.append(f"{where} should be a string, not {type(value).__name__}.")


def validate_untyped_blocks(config: OllivanderConfig):
    """Validate the blocks the schema types only as 'Dict[str, Any]', names and values alike.

    Those blocks carry the densest part of the description - which ports a component exposes,
    whether it boots, how the testbench preloads it - and used to accept anything. Writing
    'axi_slaves' instead of 'axi_slave' silently meant "this component has no slave port", and
    'siez' inside an address range silently meant a range of no size; in both cases the
    consequence surfaced much later, as a component wired to nothing or mapped nowhere.
    """
    errors = []
    for comp in [config.host] + (config.components or []):
        for block, spec in _COMPONENT_BLOCK_SPEC.items():
            value = getattr(comp, block, None)
            if isinstance(value, dict):
                _check_shape(spec, value, f"[{comp.name}] '{block}'", errors)
    for block, spec in _ROOT_BLOCK_SPEC.items():
        value = getattr(config, block, None)
        if isinstance(value, dict):
            _check_shape(spec, value, f"'{block}'", errors)
    if errors:
        raise ValueError("\n".join(f"\n{e}" for e in errors))


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

    # The per-network ID widths a NoC resolves (input side) and fixes (output side),
    # needed by the capacity check below. Resolved once, quietly: the provenance report
    # belongs to the generation step, which resolves the same values again.
    noc_in_id_widths = {}
    if config.topology.type == "noc" and search_paths:
        from core.macro_boundary import resolve_noc_id_widths, NOC_OUTPUT_ID_WIDTH
        noc_in_id_widths = resolve_noc_id_widths(config, search_paths, original_types, report=False)
    
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
        
        # 2. HARDWARE CONSTRAINTS CHECK: a component's fixed 'localparam's state a geometry
        #    it cannot depart from, so where the bus it is attached to disagrees, the
        #    connection is malformed and nothing downstream can repair it.
        #
        #    Only the address and data widths are checked, and the choice is the point of
        #    this block rather than a simplification: they are the two widths for which no
        #    adaptation exists. An ID width that differs is zero-extended or truncated at
        #    the tile boundary (universal_tile.sv.mako), and a user field wider than the
        #    network loses only the bits above the meaningful span, refused separately in
        #    macro_boundary.py when that span would not survive. Gating those here would
        #    reject working components - 'cluster_subtile' declares a narrow ID width of 5
        #    while snitch_cluster gives it 4, which is precisely why the adaptation exists.
        #
        #    It used to run only when 'global_bus' existed, i.e. never for a NoC, which is
        #    where the geometry comes from the networks rather than one declared bus - so
        #    the topology that most needs the check was the one skipping it.
        geometry_checks = {}
        if global_bus:
            geometry_checks["AxiAddrWidth"] = (global_bus.addr_width, "the global bus")
            geometry_checks["AxiDataWidth"] = (global_bus.data_width, "the global bus")
        elif config.topology.noc_settings and config.topology.noc_settings.networks:
            nets = config.topology.noc_settings.networks
            comp_nets = (comp.interfaces or {}).get("noc_networks") or {}
            attached = set((comp_nets.get("master") or []) + (comp_nets.get("slave") or []))
            # Both networks share the address space, so the plain name is unambiguous.
            if "narrow" in nets:
                geometry_checks["AxiAddrWidth"] = (nets["narrow"].addr_width, "the NoC network geometry")
            # A component on both networks names its data widths per network, per the
            # subtile standardization; one on a single network uses the plain name.
            for net_name, prefix in (("narrow", "Narrow"), ("wide", "Wide")):
                if net_name in nets and net_name in attached:
                    geometry_checks[f"Axi{prefix}DataWidth"] = (nets[net_name].data_width,
                                                                f"the '{net_name}' network")
                    if len(attached) == 1:
                        geometry_checks["AxiDataWidth"] = (nets[net_name].data_width,
                                                           f"the '{net_name}' network")

        for param_name, (bus_val, source) in geometry_checks.items():
            if param_name in info["fixed_params"]:
                fixed_val_str = info["fixed_params"][param_name]
                try:
                    fixed_val = int(fixed_val_str)
                except ValueError:
                    # Reported rather than skipped in silence. The parser keeps the value
                    # as written, so anything that is not a literal - a package reference,
                    # an expression - cannot be compared here, and a check that quietly
                    # stops running is worse than no check: whoever replaces a literal
                    # with a reference has to know the verification goes with it.
                    print(f"  [WARNING] [{comp.name}] '{param_name}' is fixed to the expression "
                          f"'{fixed_val_str}', which cannot be compared against {source}: this "
                          f"geometry is left unverified. Declare it as a literal to have it checked, "
                          f"or check it inside the component with an elaboration-time $fatal.")
                    continue

                if bus_val != fixed_val:
                    raise ValueError(
                        f"\n[ARCHITECTURAL ERROR]\n"
                        f"Component '{comp.name}' ({comp.type}) fixes '{param_name}' to {fixed_val} as a "
                        f"'localparam', but {source} carries {bus_val}.\n"
                        f"Address and data widths cannot be adapted between a component and its bus: "
                        f"connecting them would silently truncate or pad every transfer."
                    )

        # 2b. ID CAPACITY CHECK (NoC): a fixed ID width states what the component's own
        #     hardware emits and accepts, so it is verified along the direction of travel
        #     rather than for equality. What the component *emits* (OutIdWidth) may be
        #     narrower than the network - the tile zero-extends it - but never wider,
        #     since the network would truncate and distinct transactions would alias.
        #     What it *accepts* (InIdWidth) must cover the network's compressed output
        #     side, or responses would be misrouted inside the component. Only fixed
        #     'localparam's are checked: a 'parameter' is driven by the generator to the
        #     network's own width and cannot disagree with it.
        if noc_in_id_widths and comp.interfaces:
            comp_nets = comp.interfaces.get("noc_networks") or {}
            id_prefixes = {"narrow": "AxiNarrow", "wide": "AxiWide"}

            def _fixed_int(names):
                for n in names:
                    if n in info["fixed_params"]:
                        try:
                            return n, int(info["fixed_params"][n])
                        except ValueError:
                            continue
                return None, None

            for net in (comp_nets.get("master") or []):
                pname, declared = _fixed_int([f"{id_prefixes.get(net, 'Axi')}OutIdWidth", "AxiOutIdWidth"])
                if declared is not None and declared > noc_in_id_widths.get(net, declared):
                    raise ValueError(
                        f"\n[ARCHITECTURAL ERROR]\n"
                        f"Component '{comp.name}' ({comp.type}) emits {declared}-bit AXI IDs "
                        f"('{pname}') on the '{net}' network, which accepts {noc_in_id_widths[net]}.\n"
                        f"The network would truncate the top bits and distinct transactions would alias. "
                        f"Raise the network's 'id_width' or use a component matching its geometry."
                    )
            for net in (comp_nets.get("slave") or []):
                pname, declared = _fixed_int([f"{id_prefixes.get(net, 'Axi')}InIdWidth", "AxiInIdWidth"])
                if declared is not None and declared < NOC_OUTPUT_ID_WIDTH.get(net, declared):
                    raise ValueError(
                        f"\n[ARCHITECTURAL ERROR]\n"
                        f"Component '{comp.name}' ({comp.type}) accepts {declared}-bit AXI IDs "
                        f"('{pname}'), but the '{net}' network delivers "
                        f"{NOC_OUTPUT_ID_WIDTH[net]} to its subordinates.\n"
                        f"The component would truncate the ID and misroute its responses."
                    )
                        
        # 3. SYNCHRONICITY & NOC MODE CHECK: Verify that the physical ports defined in the wrapper
        #    support the sync/async connection style and NoC mode requested in the YAML.
        if comp.name != config.host.name and comp.interfaces:
            host_clk = config.host.clock_domain
            c_clk = comp.clock_domain or host_clk
            
            noc_nets = comp.interfaces.get('noc_networks', {})
            noc_mode = noc_nets.get('noc_mode', 'joined') if isinstance(noc_nets, dict) else 'joined'
            
            if noc_mode not in ["joined", "joined_narrow", "joined_wide", "dual"]:
                raise ValueError(f"\n[{comp.name}] Invalid noc_mode '{noc_mode}'. Must be one of: 'joined', 'joined_narrow', 'joined_wide', 'dual'.")

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

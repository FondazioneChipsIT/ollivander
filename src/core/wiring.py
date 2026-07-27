# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
Connection Matrix Generator for the Ollivander SoC Generator.

This module is responsible for analyzing the parsed SoC configuration and building
a comprehensive "Connection Matrix". It translates the high-level YAML topology
descriptions into explicit, low-level SystemVerilog port connection strings.

It also resolves "implicit" connections, such as dynamically inferring the existence
and width of an interrupt output on a source component simply because a target 
component declared it as an input source.
"""
import re

from core.interfaces import get_interface_ports
from core.utils import camel_case, is_external

def _is_array_port(comp_name, port_name, comp_info, is_input=True):
    """
    Checks if a given port on a component is an array (packed or unpacked).
    This is used to determine if SystemVerilog replication syntax `'{default: ...}` 
    is needed when connecting a scalar signal to a vector input port.
    """
    ports = comp_info.get(comp_name, {}).get("ports", {})
    p_info = ports.get(port_name)
    if not p_info:
        # Fallback: Some SV modules explicitly use '_i' or '_o' suffixes, but the YAML 
        # topology references might omit them. Try to find the base name.
        base_port = port_name[:-2] if (is_input and port_name.endswith('_i')) or (not is_input and port_name.endswith('_o')) else port_name
        p_info = ports.get(base_port)
        
    if p_info:
        # A port is an array if its type or unpacked dimension contains brackets.
        return '[' in p_info["type_dim"] or '[' in p_info["unpacked"]
    return False

def _infer_interrupts(soc_config, comp_info):
    """
    Scans all components looking for input interrupts that reference an output 
    from another component (e.g., 'source: safety_island.debug_req_o'). 
    If the target output ('debug_req_o') is not explicitly defined in the YAML 
    for the source component ('safety_island'), this function automatically infers 
    its existence and sizes it dynamically by parsing the target's SystemVerilog header.
    
    This allows the user to define connections "one-way" in the YAML, keeping 
    the configuration concise and reducing boilerplate.
    """
    # Create a flattened, unified lookup table of all components (Host + Peripherals)
    all_comps = {c.name: c for c in [soc_config.host] + (soc_config.components if soc_config.components else [])}
    
    # Also include APB sub-components in the lookup dictionary to allow direct
    # cross-references like 'apb_subsystem.timer.irq_o'.
    for c in list(all_comps.values()):
        if c.components:
            for sub_c in c.components:
                all_comps[sub_c.name] = sub_c
                
    for comp in all_comps.values():
        if comp.interrupts:
            for irq_name, irq_cfg in comp.interrupts.items():
                source = irq_cfg.get('source')
                sources_to_check = list(source.values()) if isinstance(source, dict) else [str(source)]
                for s in sources_to_check:
                    # Find all 'component.port' references in the source string.
                    matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', str(s))
                    for src_comp, src_port in matches:
                        if src_comp in all_comps:
                            src_c = all_comps[src_comp]
                            if src_c.interrupts is None: 
                                src_c.interrupts = {}
                                
                            # If the source component didn't explicitly declare this output, infer it.
                            if src_port not in src_c.interrupts:
                                dim_str = ""
                                # Parse the SV header of the source component to extract the exact port dimensions.
                                # This ensures the generated wire will have the correct bit-width.
                                src_ports = comp_info.get(src_comp, {}).get("ports", {})
                                p_info = src_ports.get(src_port) or src_ports.get(f"{src_port}_o")
                                
                                if p_info:
                                    dims = re.findall(r'\[.*?\]', p_info["type_dim"])
                                    if dims:
                                        dim_str = "".join(dims)
                                
                                # Inject the newly discovered output interrupt into the source component's metadata.
                                irq_data = {"type": "level"}
                                if dim_str:
                                    irq_data["sv_dimensions"] = dim_str
                                    
                                src_c.interrupts[src_port] = irq_data

def _evaluate_sv_expr(expr, comp_info, comp_name):
    c_info = comp_info.get(comp_name, {})
    params = {}
    params.update(c_info.get("fixed_params", {}))
    params.update(c_info.get("supported_params", {}))
    defaults = {
        "AxiAddrWidth": 48,
        "AxiDataWidth": 64,
        "AxiUserWidth": 10,
        "AxiInIdWidth": 5,
        "AxiOutIdWidth": 2,
        "LogDepth": 3,
        "NumCores": 8
    }
    for k, v in defaults.items():
        if k not in params:
            params[k] = str(v)
            
    clean_expr = expr.strip()
    
    def aw_width(addr_width, id_width, user_width):
        return id_width + addr_width + user_width + 35
        
    def w_width(data_width, user_width):
        return data_width + data_width // 8 + 1 + user_width
        
    def b_width(id_width, user_width):
        return id_width + 2 + user_width
        
    def ar_width(addr_width, id_width, user_width):
        return id_width + addr_width + user_width + 29
        
    def r_width(data_width, id_width, user_width):
        return id_width + data_width + user_width + 3

    sorted_keys = sorted(params.keys(), key=len, reverse=True)
    for _ in range(5):
        changed = False
        for k in sorted_keys:
            val = params[k]
            new_expr, count = re.subn(rf'\b{k}\b', str(val), clean_expr)
            if count > 0:
                clean_expr = new_expr
                changed = True
        if not changed:
            break
            
    clean_expr = clean_expr.replace("axi_pkg::", "")
    eval_env = {
        "aw_width": aw_width,
        "w_width": w_width,
        "b_width": b_width,
        "ar_width": ar_width,
        "r_width": r_width
    }
    try:
        return int(eval(clean_expr, {"__builtins__": None}, eval_env))
    except Exception as e:
        return None

def _get_resolved_port_width(comp_name, port_name, comp_info):
    c_info = comp_info.get(comp_name, {})
    p_info = c_info.get("ports", {}).get(port_name)
    if not p_info:
        return None
    type_dim = p_info.get("type_dim", "")
    decl = p_info.get("decl", "")
    m = re.search(r'\[\s*([a-zA-Z0-9_]+)\s*-\s*1\s*:\s*0\s*\]', type_dim or decl)
    if m:
        param_name = m.group(1)
        val = c_info.get("fixed_params", {}).get(param_name) or c_info.get("supported_params", {}).get(param_name)
        if val:
            return _evaluate_sv_expr(val, comp_info, comp_name)
    m_num = re.search(r'\[\s*([0-9]+)\s*:\s*0\s*\]', type_dim or decl)
    if m_num:
        return int(m_num.group(1)) + 1
    return None

def build_connection_matrix(soc_config, comp_info):
    """
    The Core Wiring Engine.
    Parses the SoC configuration and generates the physical SystemVerilog 
    connection strings for every instantiated component.
    
    It internally orchestrates the resolution of implicit interrupts before
    computing the actual physical wire mappings.
    
    Returns a dictionary mapping component names to lists of port bindings:
    {
      "l2_shared_memory": [ ".clk_i ( l2_clk )", ".axi_req_i ( ... )", ... ],
      "pulp_cluster": [ ... ]
    }
    """
    # 0. INFER IMPLICIT CONNECTIONS
    # Pre-process the metadata to resolve "one-way" interrupt declarations.
    _infer_interrupts(soc_config, comp_info)

    matrix = {}
    
    # Dictionary mapping standard AXI4 channels to their physical direction on a SLAVE port.
    # 'i' means input to the component, 'o' means output from the component.
    slv_ports = {
        'aw_data': 'i', 'aw_wptr': 'i', 'aw_rptr': 'o',
        'w_data':  'i', 'w_wptr':  'i', 'w_rptr':  'o',
        'b_data':  'o', 'b_wptr':  'o', 'b_rptr':  'i',
        'ar_data': 'i', 'ar_wptr': 'i', 'ar_rptr': 'o',
        'r_data':  'o', 'r_wptr':  'o', 'r_rptr':  'i'
    }
    
    # Dictionary mapping standard AXI4 channels to their physical direction on a MASTER port.
    # Used to automatically generate the hundreds of connections required for the interconnect.
    mst_ports = {
        'aw_data': 'o', 'aw_wptr': 'o', 'aw_rptr': 'i',
        'w_data':  'o', 'w_wptr':  'o', 'w_rptr':  'i',
        'b_data':  'i', 'b_wptr':  'i', 'b_rptr':  'o',
        'ar_data': 'o', 'ar_wptr': 'o', 'ar_rptr': 'i',
        'r_data':  'i', 'r_wptr':  'i', 'r_rptr':  'o'
    }
    
    all_comps = [soc_config.host] + (soc_config.components if soc_config.components else [])
    
    for comp in all_comps:
        c_info = comp_info.get(comp.name, {})
        ports = []
        if not comp.interfaces:
            matrix[comp.name] = ports
            continue
            
        # ----------------------------------------------------------------------
        # 1. AXI & REGBUS CROSSBAR CONNECTIONS
        # ----------------------------------------------------------------------
        if comp.name == soc_config.host.name:
            # HOST COMPONENT (Crossbar acts as Host):
            # The host exposes massive packed arrays covering all slaves and masters in the system.
            # We invert the directions because the Host master connects to the peripheral's slave, and vice versa.
            for sig, d in slv_ports.items():
                p_dir = 'o' if d == 'i' else 'i'
                ports.append(f".async_axi_out_{sig}_{p_dir} ( xbar_slv_{sig} )")
            if soc_config.host.parameters.get('AxiNumMstAsync', 0) > 0:
                for sig, d in mst_ports.items():
                    p_dir = 'o' if d == 'i' else 'i'
                    ports.append(f".async_axi_in_{sig}_{p_dir} ( xbar_mst_{sig} )")
            if soc_config.host.parameters.get('AxiNumMstSync', 0) > 0:
                ports.append(".axi_req_i ( xbar_sync_mst_req )")
                ports.append(".axi_resp_o ( xbar_sync_mst_rsp )")
            
            # Host synchronous AXI connection (bypass CDC for high-performance peripherals)
            ports.append(".axi_req_o ( xbar_sync_slv_req )")
            ports.append(".axi_resp_i ( xbar_sync_slv_rsp )")

            # Host LLC Connection (Dedicated Point-to-Point, separate from main Crossbar).
            has_llc = any('llc_port' in c.interfaces for c in all_comps if c.interfaces)
            if has_llc:
                for sig, d in mst_ports.items():
                    ports.append(f".async_axi_llc_{sig}_{d} ( async_axi_llc_{sig} )")
                ports.append(".async_axi_llc_isolate_i ( 1'b0 )")
                ports.append(".async_axi_llc_isolated_o ( )")
            else:
                # If no LLC is present, tie off the LLC ports on the Host.
                for sig, d in mst_ports.items():
                    if d == 'i': # Master input
                        ports.append(f".async_axi_llc_{sig}_i ( '0 )")
                ports.append(".async_axi_llc_isolate_i ( 1'b0 )")

            # Host RegBus Connection: Aggregates both synchronous and asynchronous register buses.
            pkg = f"{soc_config.project.soc_pkg_name}"
            ports.append(f".reg_req_o ( sys_reg_req[{pkg}::NumSyncRegSlaves-1:0] )")
            ports.append(f".reg_rsp_i ( sys_reg_rsp[{pkg}::NumSyncRegSlaves-1:0] )")
            ports.append(".reg_async_mst_req_o ( async_reg_req_out )")
            ports.append(".reg_async_mst_ack_i ( async_reg_ack_in )")
            ports.append(".reg_async_mst_data_o ( async_reg_data_out )")
            ports.append(".reg_async_mst_req_i ( async_reg_req_in )")
            ports.append(".reg_async_mst_ack_o ( async_reg_ack_out )")
            ports.append(".reg_async_mst_data_i ( async_reg_data_in )")
        else:
            # STANDARD COMPONENT: 
            # Each peripheral connects to a specific slice (defined by its autogenerated index) 
            # of the Host's multidimensional AXI/RegBus arrays.
            if 'llc_port' in comp.interfaces:
                for sig, d in slv_ports.items():
                    p_dir = 'o' if d == 'i' else 'i'
                    ports.append(f".async_axi_in_{sig}_{d} ( async_axi_llc_{sig} )")

            if 'axi_slave' in comp.interfaces:
                # In a NoC topology, AXI slave ports are internal to the Tile and connected
                # to the Chimney. They are not wired up at the top-level.
                if soc_config.topology.type != "noc":
                    slvs = comp.interfaces['axi_slave']
                    if isinstance(slvs, dict): 
                        slvs = [slvs]
                    num_ports = slvs[0].get('ports', 1) if isinstance(slvs, list) and len(slvs)>0 else 1
                    base_idx = f"ollivander_soc_pkg::AxiSlvIdx_{camel_case(comp.name)}"
                    
                    is_sync = slvs[0].get('sync_domain', False)
                    c_info = comp_info.get(comp.name, {})
                    if c_info and "ports" in c_info:
                        if not is_sync and "async_axi_in_aw_data_i" not in c_info["ports"]:
                            is_sync = True
                    
                    # Handle AXI Slaves: if a component exposes multiple AXI ports (e.g., a multi-bank L2 memory),
                    # we construct a concatenation '{...}' of the corresponding slices from the Host array.
                    if is_sync:
                        if num_ports > 1:
                            concat_req = ", ".join([f"xbar_sync_slv_req[({base_idx}{p} - ollivander_soc_pkg::NumAxiSlavesAsync)]" for p in reversed(range(num_ports))])
                            concat_rsp = ", ".join([f"xbar_sync_slv_rsp[({base_idx}{p} - ollivander_soc_pkg::NumAxiSlavesAsync)]" for p in reversed(range(num_ports))])
                            ports.append(f".axi_req_i ( {{ {concat_req} }} )")
                            ports.append(f".axi_resp_o ( {{ {concat_rsp} }} )")
                        else:
                            ports.append(f".axi_req_i ( xbar_sync_slv_req[({base_idx} - ollivander_soc_pkg::NumAxiSlavesAsync)] )")
                            ports.append(f".axi_resp_o ( xbar_sync_slv_rsp[({base_idx} - ollivander_soc_pkg::NumAxiSlavesAsync)] )")
                    else:
                        for sig, d in slv_ports.items():
                            if num_ports > 1:
                                # Map multiple asynchronous ports by slicing the crossbar array.
                                concat = ", ".join([f"xbar_slv_{sig}[{base_idx}{p}]" for p in reversed(range(num_ports))])
                                ports.append(f".async_axi_in_{sig}_{d} ( {{ {concat} }} )")
                            else:
                                port_name = f"async_axi_in_{sig}_{d}"
                                width = _get_resolved_port_width(comp.name, port_name, comp_info)
                                if width is not None:
                                    ports.append(f".{port_name} ( xbar_slv_{sig}[{base_idx}][{width-1}:0] )")
                                else:
                                    ports.append(f".{port_name} ( xbar_slv_{sig}[{base_idx}] )")
                    
            if 'axi_master' in comp.interfaces:
                # In a NoC topology, AXI master ports are internal to the Tile and connected
                # to the Chimney. They are not wired up at the top-level.
                if soc_config.topology.type != "noc":
                    idx = f"ollivander_soc_pkg::AxiMstIdx_{camel_case(comp.name)}"
                    is_sync_mst = True
                    c_info = comp_info.get(comp.name, {})
                    if c_info and "ports" in c_info:
                        if "async_axi_out_aw_data_o" in c_info["ports"]:
                            is_sync_mst = False
                            
                    if is_sync_mst:
                        ports.append(f".axi_req_o ( xbar_sync_mst_req[({idx} - ollivander_soc_pkg::NumAxiMastersAsync)] )")
                        ports.append(f".axi_resp_i ( xbar_sync_mst_rsp[({idx} - ollivander_soc_pkg::NumAxiMastersAsync)] )")
                    else:
                        for sig, d in mst_ports.items():
                            port_name = f"async_axi_out_{sig}_{d}"
                            width = _get_resolved_port_width(comp.name, port_name, comp_info)
                            if width is not None:
                                ports.append(f".{port_name} ( xbar_mst_{sig}[{idx}][{width-1}:0] )")
                            else:
                                ports.append(f".{port_name} ( xbar_mst_{sig}[{idx}] )")

        # ----------------------------------------------------------------------
        # 2. PERIPHERAL REGBUS CONNECTIONS
        # ----------------------------------------------------------------------
        if comp.interfaces and 'regbus_slave' in comp.interfaces:
            slvs = comp.interfaces['regbus_slave']
            if isinstance(slvs, dict): 
                slvs = [slvs]
            is_sync = slvs[0].get('sync_domain', True)
            idx = f"ollivander_soc_pkg::RegBusSlvIdx_{camel_case(comp.name)}"
            
            if is_sync:
                # Synchronous RegBus directly accesses the Host's sys_reg_req/rsp arrays.
                ports.append(f".reg_req_i ( sys_reg_req[{idx}] )")
                ports.append(f".reg_rsp_o ( sys_reg_rsp[{idx}] )")
            else:
                # Asynchronous RegBus needs an index offset (NumSyncRegSlaves) since the array is split.
                async_idx = f"({idx} - ollivander_soc_pkg::NumSyncRegSlaves)"
                if not is_external(comp):
                    ports.append(f".reg_async_slv_req_i ( async_reg_req_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_ack_o ( async_reg_ack_in[{async_idx}] )")
                    ports.append(f".reg_async_slv_data_i ( async_reg_data_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_req_o ( async_reg_req_in[{async_idx}] )")
                    ports.append(f".reg_async_slv_ack_i ( async_reg_ack_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_data_o ( async_reg_data_in[{async_idx}] )")
            
        # Connect the APB interface of the System Controller to the APB Subsystem
        if soc_config.system_controller and comp.name == soc_config.system_controller.name:
            idx = f"ollivander_soc_pkg::RegBusSlvIdx_{camel_case(comp.name)}"
            ports.append(f".paddr_i   ( apb_slv_reqs[{idx}].paddr )")
            ports.append(f".psel_i    ( apb_slv_reqs[{idx}].psel )")
            ports.append(f".penable_i ( apb_slv_reqs[{idx}].penable )")
            ports.append(f".pwrite_i  ( apb_slv_reqs[{idx}].pwrite )")
            ports.append(f".pwdata_i  ( apb_slv_reqs[{idx}].pwdata )")
            ports.append(f".pstrb_i   ( apb_slv_reqs[{idx}].pstrb )")
            ports.append(f".prdata_o  ( apb_slv_rsps[{idx}].prdata )")
            ports.append(f".pready_o  ( apb_slv_rsps[{idx}].pready )")
            ports.append(f".pslverr_o ( apb_slv_rsps[{idx}].pslverr )")

        # ----------------------------------------------------------------------
        # 3. PHYSICAL PERIPHERAL PORTS EXPORT
        # ----------------------------------------------------------------------
        # Resolves standard physical interfaces (JTAG, UART, I2C, SPI, etc.)
        # and automatically wires them directly to the Top-Level I/O boundaries.
        interfaces_to_wire = set()
        if comp.export_interfaces:
            interfaces_to_wire.update(comp.export_interfaces)
            
        for if_name in interfaces_to_wire:
            port_mappings = get_interface_ports(if_name, comp.name, comp.name == soc_config.host.name, c_info)
            for pm in port_mappings:
                ports.append(f".{pm['internal']} ( {pm['top']} )")
            
        # ----------------------------------------------------------------------
        # 4. INTERRUPT ROUTING & CDC
        # ----------------------------------------------------------------------
        output_ports_wired = set()
        if comp.interrupts:
            for irq_name, irq_cfg in comp.interrupts.items():
                if irq_cfg.get('source'):
                    port_name = irq_name if irq_name.endswith('_i') else f"{irq_name}_i"
                    # --- INPUT INTERRUPT ---
                    # This pin acts as a sink. It must be driven by another component's output wire.
                    source = irq_cfg.get('source')
                    if source == "none":
                        # Tie off unconnected interrupts to ground.
                        ports.append(f".{port_name} ( '0 )")
                    else:
                        # Parse the source string to detect the target component and 
                        # determine if a Clock Domain Crossing (CDC) is required.
                        source_str = str(source).strip()
                        is_mapped_block = source_str.startswith('{') and source_str.endswith('}')
                        sources_to_check = [m[1] for m in re.findall(r'(\[[^\]]+\])\s*:\s*([^,\n]+)', source_str[1:-1])] if is_mapped_block else [source_str]
                        
                        needs_sync = False
                        missing_comp = None
                        dst_clk = comp.clock_domain or soc_config.host.clock_domain
                        for s in sources_to_check:
                            src_comp_names = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', s))
                            for src_comp_name in src_comp_names:
                                src_comp = next((c for c in all_comps if c.name == src_comp_name), None)
                                if not src_comp:
                                    # Check inside sub-components (e.g., APB subsystem)
                                    for c in all_comps:
                                        if c.components:
                                            src_comp = next((sub for sub in c.components if sub.name == src_comp_name), None)
                                            if src_comp: 
                                                break
                                if not src_comp:
                                    missing_comp = src_comp_name
                                    break
                                
                                if src_comp:
                                    src_clk = src_comp.clock_domain or soc_config.host.clock_domain
                                    if src_clk != dst_clk:
                                        needs_sync = True
                                        break
                            if missing_comp or needs_sync: 
                                break
                                
                        if missing_comp:
                            print(f"[WARNING] [{comp.name}] Interrupt '{irq_name}' references missing component '{missing_comp}'. Tying off to '0'.")
                            if is_mapped_block:
                                ports.append(f".{port_name} ( intr_{comp.name}_{irq_name} )")
                            else:
                                ports.append(f".{port_name} ( '0 /* missing {missing_comp} */ )")
                            continue
                                
                        # Respect explicit user overrides to disable CDC.
                        if irq_cfg.get('cdc') is False:
                            needs_sync = False
                                    
                        if is_mapped_block or isinstance(source, dict):
                            # For complex mapped interrupts, a dedicated wire is always generated.
                            if needs_sync:
                                ports.append(f".{port_name} ( intr_{comp.name}_{irq_name}_sync )")
                            else:
                                ports.append(f".{port_name} ( intr_{comp.name}_{irq_name} )")
                        else:
                            # For simple 1-to-1 connections, generate the wire name directly.
                            processed_str = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', source_str)
                            
                            # Evaluate if the destination port is a vector (array) and the source is a scalar.
                            is_arr = _is_array_port(comp.name, port_name, comp_info)
                            src_is_arr = False
                            src_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$', source_str.strip())
                            if src_match:
                                src_is_arr = _is_array_port(src_match.group(1), src_match.group(2), comp_info, False)
                                
                            # Use SystemVerilog replication syntax '{default: ...} to safely broadcast the scalar to the whole vector.
                            out_str = f"'{{default: {processed_str}}}" if (is_arr and not src_is_arr) else processed_str
                            out_str_sync = f"'{{default: intr_{comp.name}_{irq_name}_sync}}" if (is_arr and not src_is_arr) else f"intr_{comp.name}_{irq_name}_sync"
                            
                            if needs_sync:
                                ports.append(f".{port_name} ( {out_str_sync} )")
                            else:
                                ports.append(f".{port_name} ( {out_str} )")
                else:
                    # --- OUTPUT INTERRUPT ---
                    # This pin acts as a source. It drives a global wire that other components can listen to.
                    port_name = irq_cfg.get('port', irq_name)
                    p_name = port_name if not port_name.endswith('_o') else port_name[:-2]
                    if port_name not in output_ports_wired:
                        output_ports_wired.add(port_name)
                        ports.append(f".{p_name}_o ( intr_{comp.name}_{port_name} )")

        if comp.components:
            for sub_c in comp.components:
                sub_interfaces = set()
                if sub_c.export_interfaces:
                    sub_interfaces.update(sub_c.export_interfaces)
                if sub_c.type == 'can_top_apb':
                    sub_interfaces.add('can_bus')
                
                for if_name in sub_interfaces:
                    sub_c_info = comp_info.get(sub_c.name, {})
                    port_mappings = get_interface_ports(if_name, sub_c.name, False, sub_c_info)
                    for pm in port_mappings:
                        ports.append(f".{pm['internal']} ( {pm['top']} )")

        # ----------------------------------------------------------------------
        # 5. SUB-COMPONENT INTERRUPT ROUTING (e.g., inside APB Subsystems)
        # ----------------------------------------------------------------------
        # APB subsystems hide multiple peripherals inside a single Isle wrapper.
        # We need to explicitly route their interrupts out to the Top-Level.
        if comp.components:
            for sub_c in comp.components:
                if sub_c.interrupts:
                    for irq_name, irq_cfg in sub_c.interrupts.items():
                        if irq_cfg.get('source'):
                            ports.append(f".{sub_c.name}_{irq_name}_i ( intr_{irq_cfg['source']}_{irq_name} )")
                        else:
                            p_name = f"{sub_c.name}_{irq_name}"
                            p_name = p_name if not p_name.endswith('_o') else p_name[:-2]
                            port_str = f"{p_name}_o"
                            if port_str not in output_ports_wired:
                                output_ports_wired.add(port_str)
                                ports.append(f".{port_str} ( /* unconnected */ )")

        matrix[comp.name] = ports
        
    return matrix
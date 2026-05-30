# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
#
# ==============================================================================
# CONNECTION MATRIX GENERATOR FOR OLLIVANDER SoC
# ==============================================================================
# This module is responsible for analyzing the SoC configuration and building a 
# comprehensive "Connection Matrix". It translates the high-level YAML topology 
# into low-level SystemVerilog port connections.
#
# It also handles "implicit" connections, like inferring the existence of an 
# interrupt output on a source component just because a target component 
# declared it as its input.
# ==============================================================================
import re

def camel_case(name):
    """Converts a snake_case string to CamelCase (e.g., 'pulp_cluster' -> 'PulpCluster')."""
    return ''.join(word.title() for word in name.split('_'))

def is_external(comp):
    """
    Determines if a component is 'external' by checking if any of its RegBus 
    interfaces are explicitly marked with `external: true` in the YAML.
    External components are not instantiated in the top-level; instead, their 
    RegBus ports are exported to the SoC top-level boundaries.
    """
    if not comp.interfaces: 
        return False
    slaves = comp.interfaces.get('regbus_slave', [])
    if isinstance(slaves, dict): 
        slaves = [slaves]
    return any(slv.get('external', False) for slv in slaves)

def is_array_port(comp_name, port_name, comp_info, is_input=True):
    ports = comp_info.get(comp_name, {}).get("ports", {})
    p_info = ports.get(port_name)
    if not p_info:
        base_port = port_name[:-2] if (is_input and port_name.endswith('_i')) or (not is_input and port_name.endswith('_o')) else port_name
        p_info = ports.get(base_port)
        
    if p_info:
        return '[' in p_info["type_dim"] or '[' in p_info["unpacked"]
    return False

def infer_interrupts(soc_config, comp_info):
    """
    Scans all components looking for input interrupts that reference an output 
    from another component (e.g., 'source: safety_island.debug_req_o'). 
    If the target output ('debug_req_o') is not explicitly defined in the YAML 
    for 'safety_island', this function automatically infers its existence and 
    sizes it dynamically by parsing the target's SystemVerilog header.
    
    This allows the user to define connections "one-way" in the YAML, keeping 
    the configuration concise.
    """
    all_comps = {c.name: c for c in [soc_config.host] + (soc_config.components if soc_config.components else [])}
    
    # Include APB sub-components in the lookup dictionary
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
                    matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', str(s))
                    for src_comp, src_port in matches:
                        if src_comp in all_comps:
                            src_c = all_comps[src_comp]
                            if src_c.interrupts is None: 
                                src_c.interrupts = {}
                            if src_port not in src_c.interrupts:
                                dim_str = ""
                                src_ports = comp_info.get(src_comp, {}).get("ports", {})
                                p_info = src_ports.get(src_port) or src_ports.get(f"{src_port}_o")
                                
                                if p_info:
                                    dims = re.findall(r'\[.*?\]', p_info["type_dim"])
                                    if dims:
                                        dim_str = "".join(dims)
                                
                                irq_data = {"type": "level"}
                                if dim_str:
                                    irq_data["sv_dimensions"] = dim_str
                                    
                                src_c.interrupts[src_port] = irq_data

def build_connection_matrix(soc_config, comp_info):
    """
    The Core Wiring Engine.
    Parses the SoC configuration and generates the physical SystemVerilog 
    connection strings for every instantiated component.
    
    Returns a dictionary mapping component names to lists of port bindings:
    {
      "l2_shared_memory": [ ".clk_i ( l2_clk )", ".axi_req_i ( ... )", ... ],
      "pulp_cluster": [ ... ]
    }
    """
    matrix = {}
    
    # Standard AXI channel directions for a SLAVE port (from the component's perspective)
    slv_ports = {
        'aw_data': 'i', 'aw_wptr': 'i', 'aw_rptr': 'o',
        'w_data':  'i', 'w_wptr':  'i', 'w_rptr':  'o',
        'b_data':  'o', 'b_wptr':  'o', 'b_rptr':  'i',
        'ar_data': 'i', 'ar_wptr': 'i', 'ar_rptr': 'o',
        'r_data':  'o', 'r_wptr':  'o', 'r_rptr':  'i'
    }
    
    # Standard AXI channel directions for a MASTER port (from the component's perspective)
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
            # HOST COMPONENT: Acts as the central switch. It exposes massive 
            # multidimensional arrays covering all slaves and masters in the system.
            for sig, d in slv_ports.items():
                p_dir = 'o' if d == 'i' else 'i'
                ports.append(f".async_axi_out_{sig}_{p_dir} ( xbar_slv_{sig} )")
            for sig, d in mst_ports.items():
                p_dir = 'o' if d == 'i' else 'i'
                ports.append(f".async_axi_in_{sig}_{p_dir} ( xbar_mst_{sig} )")
            
            # Host Sync AXI Connection
            ports.append(".axi_req_o ( xbar_sync_slv_req )")
            ports.append(".axi_resp_i ( xbar_sync_slv_rsp )")

            # Host LLC Connection (Dedicated Point-to-Point)
            has_llc = any('llc_port' in c.interfaces for c in all_comps if c.interfaces)
            if has_llc:
                for sig, d in mst_ports.items():
                    ports.append(f".async_axi_llc_{sig}_{d} ( async_axi_llc_{sig} )")
                ports.append(".async_axi_llc_isolate_i ( 1'b0 )")
                ports.append(".async_axi_llc_isolated_o ( )")
            else:
                for sig, d in mst_ports.items():
                    if d == 'i': # Master input
                        ports.append(f".async_axi_llc_{sig}_i ( '0 )")
                ports.append(".async_axi_llc_isolate_i ( 1'b0 )")

            # Host RegBus Connection
            pkg = f"{soc_config.project.name}_soc_pkg"
            ports.append(f".reg_req_o ( sys_reg_req[{pkg}::NumSyncRegSlaves-1:0] )")
            ports.append(f".reg_rsp_i ( sys_reg_rsp[{pkg}::NumSyncRegSlaves-1:0] )")
            ports.append(".reg_async_mst_req_o ( async_reg_req_out )")
            ports.append(".reg_async_mst_ack_i ( async_reg_ack_in )")
            ports.append(".reg_async_mst_data_o ( async_reg_data_out )")
            ports.append(".reg_async_mst_req_i ( async_reg_req_in )")
            ports.append(".reg_async_mst_ack_o ( async_reg_ack_out )")
            ports.append(".reg_async_mst_data_i ( async_reg_data_in )")
        else:
            # STANDARD COMPONENT: Connects to a specific slice (index) of the 
            # Host's multidimensional AXI/RegBus arrays.
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
                    base_idx = f"AxiSlvIdx_{camel_case(comp.name)}"
                    
                    is_sync = slvs[0].get('sync_domain', False)
                    
                    # If a component exposes multiple AXI ports (e.g., Dual-Port L2),
                    # we concatenate the corresponding slices from the Host array.
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
                                # Map multiple ports slicing the array (e.g. L2 Dual Port Memory)
                                concat = ", ".join([f"xbar_slv_{sig}[{base_idx}{p}]" for p in reversed(range(num_ports))])
                                ports.append(f".async_axi_in_{sig}_{d} ( {{ {concat} }} )")
                            else:
                                ports.append(f".async_axi_in_{sig}_{d} ( xbar_slv_{sig}[{base_idx}] )")
                    
            if 'axi_master' in comp.interfaces:
                # In a NoC topology, AXI master ports are internal to the Tile and connected
                # to the Chimney. They are not wired up at the top-level.
                if soc_config.topology.type != "noc":
                    idx = f"AxiMstIdx_{camel_case(comp.name)}"
                    for sig, d in mst_ports.items():
                        ports.append(f".async_axi_out_{sig}_{d} ( xbar_mst_{sig}[{idx}] )")

        # ----------------------------------------------------------------------
        # 2. PERIPHERAL REGBUS CONNECTIONS
        # ----------------------------------------------------------------------
        if comp.interfaces and 'regbus_slave' in comp.interfaces:
            slvs = comp.interfaces['regbus_slave']
            if isinstance(slvs, dict): 
                slvs = [slvs]
            is_sync = slvs[0].get('sync_domain', True)
            idx = f"RegBusSlvIdx_{camel_case(comp.name)}"
            
            if is_sync:
                ports.append(f".reg_req_i ( sys_reg_req[{idx}] )")
                ports.append(f".reg_rsp_o ( sys_reg_rsp[{idx}] )")
            else:
                async_idx = f"({idx} - ollivander_soc_pkg::NumSyncRegSlaves)"
                if not is_external(comp):
                    ports.append(f".reg_async_slv_req_i ( async_reg_req_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_ack_o ( async_reg_ack_in[{async_idx}] )")
                    ports.append(f".reg_async_slv_data_i ( async_reg_data_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_req_o ( async_reg_req_in[{async_idx}] )")
                    ports.append(f".reg_async_slv_ack_i ( async_reg_ack_out[{async_idx}] )")
                    ports.append(f".reg_async_slv_data_o ( async_reg_data_in[{async_idx}] )")
            
        # ----------------------------------------------------------------------
        # 3. SYSTEM CONTROLLER CONNECTIONS (PCRs)
        # ----------------------------------------------------------------------
        if comp.system_config:
            reg_prefix = f"sys_regs_reg2hw.{comp.name.lower()}"
            hw2reg_prefix = f"sys_regs_hw2reg.{comp.name.lower()}"
            
            if comp.system_config.get('isolate'):
                ports.append(f".axi_isolate_i ( {reg_prefix}_isolate.q )")
                ports.append(f".axi_isolated_o ( {hw2reg_prefix}_isolate_status.d )")
                
            if comp.system_config.get('fetch_enable'):
                ports.append(f".fetch_en_i ( {reg_prefix}_fetch_enable.q )")
                
            if comp.system_config.get('boot_enable'):
                ports.append(f".en_sa_boot_i ( {reg_prefix}_boot_enable.q )")
                
            if comp.system_config.get('debug_req'):
                if is_array_port(comp.name, 'debug_req_i', comp_info):
                    ports.append(f".debug_req_i ( '{{default: {reg_prefix}_debug_req.q}} )")
                else:
                    ports.append(f".debug_req_i ( {reg_prefix}_debug_req.q )")
                
            if 'boot_addr' in comp.system_config and c_info.get("has_boot_addr"):
                ports.append(f".boot_addr_i ( {reg_prefix}_boot_addr.q )")
                
            if comp.system_config.get('has_busy_status'):
                ports.append(f".busy_o ( {hw2reg_prefix}_busy.d )")
                
            if comp.system_config.get('has_eoc_status') and 'eoc' not in (comp.interrupts or {}) and 'eoc_o' not in (comp.interrupts or {}):
                ports.append(f".eoc_o ( {hw2reg_prefix}_eoc.d )")

        # ----------------------------------------------------------------------
        # 4. JTAG CONNECTIONS
        # ----------------------------------------------------------------------
        if comp.interfaces and comp.interfaces.get('jtag'):
            jtag_pfx = "jtag_" if comp.name == soc_config.host.name else f"jtag_{comp.name}_"
            ports.append(f".jtag_tck_i ( {jtag_pfx}tck_i )")
            ports.append(f".jtag_trst_ni ( {jtag_pfx}trst_ni )")
            ports.append(f".jtag_tms_i ( {jtag_pfx}tms_i )")
            ports.append(f".jtag_tdi_i ( {jtag_pfx}tdi_i )")
            ports.append(f".jtag_tdo_o ( {jtag_pfx}tdo_o )")
            if c_info.get("has_jtag_oe"):
                ports.append(f".jtag_tdo_oe_o ( {jtag_pfx}tdo_oe_o )")
            
        # ----------------------------------------------------------------------
        # 5. INTERRUPT ROUTING & CDC
        # ----------------------------------------------------------------------
        output_ports_wired = set()
        if comp.interrupts:
            for irq_name, irq_cfg in comp.interrupts.items():
                if irq_cfg.get('source'):
                    port_name = irq_name if irq_name.endswith('_i') else f"{irq_name}_i"
                    # --- INPUT INTERRUPT ---
                    # This pin must be driven by another component's output.
                    source = irq_cfg.get('source')
                    if source == "none":
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
                                
                        # Respect explicit user overrides to disable CDC
                        if irq_cfg.get('cdc') is False:
                            needs_sync = False
                                    
                        if is_mapped_block or isinstance(source, dict):
                            if needs_sync:
                                ports.append(f".{port_name} ( intr_{comp.name}_{irq_name}_sync )")
                            else:
                                ports.append(f".{port_name} ( intr_{comp.name}_{irq_name} )")
                        else:
                            processed_str = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', source_str)
                            
                            is_arr = is_array_port(comp.name, port_name, comp_info)
                            src_is_arr = False
                            src_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$', source_str.strip())
                            if src_match:
                                src_is_arr = is_array_port(src_match.group(1), src_match.group(2), comp_info, False)
                                
                            out_str = f"'{{default: {processed_str}}}" if (is_arr and not src_is_arr) else processed_str
                            out_str_sync = f"'{{default: intr_{comp.name}_{irq_name}_sync}}" if (is_arr and not src_is_arr) else f"intr_{comp.name}_{irq_name}_sync"
                            
                            if needs_sync:
                                ports.append(f".{port_name} ( {out_str_sync} )")
                            else:
                                ports.append(f".{port_name} ( {out_str} )")
                else:
                    # --- OUTPUT INTERRUPT ---
                    # This pin drives a wire that other components can listen to.
                    port_name = irq_cfg.get('port', irq_name)
                    p_name = port_name if not port_name.endswith('_o') else port_name[:-2]
                    if port_name not in output_ports_wired:
                        output_ports_wired.add(port_name)
                        ports.append(f".{p_name}_o ( intr_{comp.name}_{port_name} )")
                    
        # ----------------------------------------------------------------------
        # 6. PHYSICAL PERIPHERAL PORTS EXPORT
        # ----------------------------------------------------------------------
        # Routes native I/O interfaces directly to the Top-Level boundaries.
        pfx = "" if comp.name == soc_config.host.name else f"{comp.name}_"
        
        if (comp.interfaces and comp.interfaces.get('uart')) or (comp.parameters and comp.parameters.get('Uart')):
            uart_pfx = "uart_" if comp.name == soc_config.host.name else f"uart_{comp.name}_"
            ports.append(f".uart_tx_o ( {uart_pfx}tx_o )")
            ports.append(f".uart_rx_i ( {uart_pfx}rx_i )")
            
        if (comp.interfaces and comp.interfaces.get('i2c')) or (comp.parameters and comp.parameters.get('I2c')):
            i2c_pfx = "i2c_" if comp.name == soc_config.host.name else f"i2c_{comp.name}_"
            ports.append(f".i2c_sda_o ( {i2c_pfx}sda_o )")
            ports.append(f".i2c_sda_i ( {i2c_pfx}sda_i )")
            ports.append(f".i2c_sda_en_o ( {i2c_pfx}sda_en_o )")
            ports.append(f".i2c_scl_o ( {i2c_pfx}scl_o )")
            ports.append(f".i2c_scl_i ( {i2c_pfx}scl_i )")
            ports.append(f".i2c_scl_en_o ( {i2c_pfx}scl_en_o )")
            
        if (comp.interfaces and comp.interfaces.get('spi_host')) or (comp.parameters and comp.parameters.get('SpiHost')):
            spi_pfx = "spi_" if comp.name == soc_config.host.name else f"spi_{comp.name}_"
            ports.append(f".spih_sck_o ( {spi_pfx}sck_o )")
            ports.append(f".spih_sck_en_o ( {spi_pfx}sck_en_o )")
            ports.append(f".spih_csb_o ( {spi_pfx}csb_o )")
            ports.append(f".spih_csb_en_o ( {spi_pfx}csb_en_o )")
            ports.append(f".spih_sd_o ( {spi_pfx}sd_o )")
            ports.append(f".spih_sd_en_o ( {spi_pfx}sd_en_o )")
            ports.append(f".spih_sd_i ( {spi_pfx}sd_i )")

        if comp.interfaces and comp.interfaces.get('hyperbus_phy'):
            for p in ['cs_no', 'ck_o', 'ck_no', 'rwds_o', 'rwds_i', 'rwds_oe_o', 'dq_i', 'dq_o', 'dq_oe_o', 'reset_no']:
                p_dir = 'o' if p.endswith('_i') else 'i' # From component's perspective
                ports.append(f".{p} ( {pfx}{p} )")
                
        if comp.interfaces and comp.interfaces.get('rgmii_phy'):
            for p in ['phy_rx_clk_i', 'phy_rxd_i', 'phy_rx_ctl_i', 'phy_tx_clk_o', 'phy_txd_o', 'phy_tx_ctl_o', 'phy_resetn_o', 'phy_mdio_i', 'phy_mdio_o', 'phy_mdio_oe', 'phy_mdc_o']:
                ports.append(f".{p} ( {pfx}{p} )")
                
        if comp.components:
            for sub_c in comp.components:
                if sub_c.type == 'can_top_apb':
                    ports.append(f".{sub_c.name}_rx_i ( {sub_c.name}_rx_i )")
                    ports.append(f".{sub_c.name}_tx_o ( {sub_c.name}_tx_o )")

        # ----------------------------------------------------------------------
        # 7. SUB-COMPONENT INTERRUPT ROUTING (e.g., inside APB Subsystems)
        # ----------------------------------------------------------------------
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
# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

"""
Topology-specific IR builder functions for the RTL generator.

These functions are extracted from RTLGenerator.build_architecture_ir to
keep the main generator class focused on orchestration rather than low-level
instantiation details. Each function populates a pre-existing SVArchitectureIR
object (passed by reference) with the instances and connections specific to its
topology.
"""

import re

from core.sv_ir import PortConnection
from core.utils import fmt_rst, is_external


def build_crossbar_ir(ir, soc_config, comp_info, wiring_matrix, comp_extra_conns):
    """
    Populate *ir* with instances and connections for a Crossbar topology.

    Each component receives a single named instance with full AXI parameter
    substitution, clock/reset connections, system-controller hooks,
    wiring-matrix connections, exported-interface connections, and auto
    tie-offs for any remaining unconnected ports.
    """
    pkg = f"{soc_config.project.name}_soc_pkg"
    all_comps = [soc_config.host] + (soc_config.components if soc_config.components else [])

    for comp in all_comps:
        if is_external(comp):
            continue
        inst_name = f"i_{comp.name}"
        module_name = f"{soc_config.project.name}_{comp.type}"
        inst = ir.add_instance(inst_name, module_name)

        c_info = comp_info.get(comp.name, {})

        # Parameters
        supported = c_info.get("supported_params", [])
        for p in supported:
            if p in ['AxiAddrWidth', 'AxiDataWidth', 'AxiUserWidth', 'LogDepth']:
                inst.parameters[p] = p
            elif p == 'AxiMaxReadTxns': inst.parameters[p] = f"{pkg}::LlcMaxReadTxns" if 'l2' in comp.name else f"{pkg}::RegMaxReadTxns"
            elif p == 'AxiMaxWriteTxns': inst.parameters[p] = f"{pkg}::LlcMaxWriteTxns" if 'l2' in comp.name else f"{pkg}::RegMaxWriteTxns"
            elif p == 'AxiUserAmoMsb': inst.parameters[p] = f"{pkg}::AxiUserAmoMsb"
            elif p == 'AxiUserAmoLsb': inst.parameters[p] = f"{pkg}::AxiUserAmoLsb"
            elif p == 'AxiUserEccErrBit': inst.parameters[p] = f"{pkg}::AxiUserEccErrBit"
            elif p == 'AxiAmoNumCuts': inst.parameters[p] = f"{pkg}::LlcAmoNumCuts" if 'l2' in comp.name else f"{pkg}::RegAmoNumCuts"
            elif p == 'AxiInIdWidth':
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcIdWidth'
                else: inst.parameters[p] = 'AxiSlvIdWidth'
            elif p == 'AxiOutIdWidth': inst.parameters[p] = 'AxiIdWidth'
            elif p == 'AxiIdWidth':
                interfaces = comp.interfaces or {}
                has_slave = 'axi_slave' in interfaces or 'llc_port' in interfaces
                has_master = 'axi_master' in interfaces
                if has_slave and not has_master:
                    inst.parameters[p] = 'AxiSlvIdWidth'
                else:
                    inst.parameters[p] = 'AxiIdWidth'
            elif p in ['axi_req_t', 'axi_in_req_t', 'sync_axi_in_req_t', 'axi_slave_req_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_req_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_req_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_req_t"
            elif p in ['axi_resp_t', 'axi_in_resp_t', 'sync_axi_in_rsp_t', 'axi_slave_resp_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_resp_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_resp_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_resp_t"
            elif p in ['axi_aw_chan_t', 'axi_in_aw_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_aw_chan_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_aw_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_aw_chan_t"
            elif p in ['axi_w_chan_t', 'axi_in_w_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_w_chan_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_w_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_w_chan_t"
            elif p in ['axi_b_chan_t', 'axi_in_b_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_b_chan_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_b_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_b_chan_t"
            elif p in ['axi_ar_chan_t', 'axi_in_ar_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_ar_chan_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_ar_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_ar_chan_t"
            elif p in ['axi_r_chan_t', 'axi_in_r_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_r_chan_t"
                elif 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f"{pkg}::soc_axi_llc_r_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_slv_r_chan_t"
            elif p in ['axi_out_req_t', 'sync_axi_out_req_t', 'axi_master_req_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_req_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_req_t"
            elif p in ['axi_out_resp_t', 'sync_axi_out_rsp_t', 'axi_master_resp_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_resp_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_resp_t"
            elif p in ['axi_out_aw_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_aw_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_aw_chan_t"
            elif p in ['axi_out_w_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_w_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_w_chan_t"
            elif p in ['axi_out_b_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_b_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_b_chan_t"
            elif p in ['axi_out_ar_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_ar_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_ar_chan_t"
            elif p in ['axi_out_r_chan_t']:
                if comp.name == soc_config.host.name: inst.parameters[p] = f"{pkg}::soc_axi_slv_r_chan_t"
                else: inst.parameters[p] = f"{pkg}::soc_axi_r_chan_t"
            elif p in ['reg_req_t', 'sync_reg_in_req_t', 'sync_reg_out_req_t', 'async_reg_out_req_t']:
                inst.parameters[p] = f"{pkg}::soc_reg_req_t"
            elif p in ['reg_rsp_t', 'sync_reg_in_rsp_t', 'sync_reg_out_rsp_t', 'async_reg_out_rsp_t']:
                inst.parameters[p] = f"{pkg}::soc_reg_rsp_t"
            elif p == 'MACRO_BASE_ADDR':
                b_addr = 0
                if comp.interfaces and 'axi_slave' in comp.interfaces:
                    slvs = comp.interfaces['axi_slave']
                    if isinstance(slvs, list) and len(slvs) > 0:
                        b_addr = slvs[0].get('base_addr', 0)
                elif getattr(comp, 'base_addr', None) is not None:
                    b_addr = comp.base_addr
                b_val = int(b_addr, 16) if isinstance(b_addr, str) else b_addr
                inst.parameters[p] = f"64'h{b_val:X}"
            elif p.startswith('AsyncAxiLlc'):
                if p == 'AsyncAxiLlcAwWidth': inst.parameters[p] = f'{pkg}::LlcAwWidth'
                elif p == 'AsyncAxiLlcWWidth': inst.parameters[p] = f'{pkg}::LlcWWidth'
                elif p == 'AsyncAxiLlcBWidth': inst.parameters[p] = f'{pkg}::LlcBWidth'
                elif p == 'AsyncAxiLlcArWidth': inst.parameters[p] = f'{pkg}::LlcArWidth'
                elif p == 'AsyncAxiLlcRWidth': inst.parameters[p] = f'{pkg}::LlcRWidth'
            elif p in ['AsyncAxiInAwWidth', 'AxiSlvAwWidth']:
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcAwWidth'
                else: inst.parameters[p] = 'XbarMstAwWidth' if comp.name == soc_config.host.name else 'XbarSlvAwWidth'
            elif p in ['AsyncAxiInWWidth', 'AxiSlvWWidth']:
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcWWidth'
                else: inst.parameters[p] = 'XbarMstWWidth' if comp.name == soc_config.host.name else 'XbarSlvWWidth'
            elif p in ['AsyncAxiInBWidth', 'AxiSlvBWidth']:
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcBWidth'
                else: inst.parameters[p] = 'XbarMstBWidth' if comp.name == soc_config.host.name else 'XbarSlvBWidth'
            elif p in ['AsyncAxiInArWidth', 'AxiSlvArWidth']:
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcArWidth'
                else: inst.parameters[p] = 'XbarMstArWidth' if comp.name == soc_config.host.name else 'XbarSlvArWidth'
            elif p in ['AsyncAxiInRWidth', 'AxiSlvRWidth']:
                if 'llc_port' in (comp.interfaces or {}): inst.parameters[p] = f'{pkg}::LlcRWidth'
                else: inst.parameters[p] = 'XbarMstRWidth' if comp.name == soc_config.host.name else 'XbarSlvRWidth'
            elif p in ['AsyncAxiOutAwWidth', 'AxiMstAwWidth']:
                inst.parameters[p] = 'XbarSlvAwWidth' if comp.name == soc_config.host.name else 'XbarMstAwWidth'
            elif p in ['AsyncAxiOutWWidth', 'AxiMstWWidth']:
                inst.parameters[p] = 'XbarSlvWWidth' if comp.name == soc_config.host.name else 'XbarMstWWidth'
            elif p in ['AsyncAxiOutBWidth', 'AxiMstBWidth']:
                inst.parameters[p] = 'XbarSlvBWidth' if comp.name == soc_config.host.name else 'XbarMstBWidth'
            elif p in ['AsyncAxiOutArWidth', 'AxiMstArWidth']:
                inst.parameters[p] = 'XbarSlvArWidth' if comp.name == soc_config.host.name else 'XbarMstArWidth'
            elif p in ['AsyncAxiOutRWidth', 'AxiMstRWidth']:
                inst.parameters[p] = 'XbarSlvRWidth' if comp.name == soc_config.host.name else 'XbarMstRWidth'

        # Custom parameters from YAML
        if comp.parameters:
            for p_k, p_v in comp.parameters.items():
                if isinstance(p_v, bool):
                    inst.parameters[p_k] = "1'b1" if p_v else "1'b0"
                else:
                    inst.parameters[p_k] = str(p_v)

        # Clock/reset connections
        c_clk = comp.clock_domain or "host_clk"
        c_rst = comp.reset_domain or c_clk.replace('_clk', '_rst')
        rst_wire = 'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'

        inst.connections.append(PortConnection("clk_i", c_clk))
        inst.connections.append(PortConnection("rst_ni", rst_wire))

        if c_info.get('has_pwr_on_rst'):
            por_wire = 'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'
            inst.connections.append(PortConnection("pwr_on_rst_ni", por_wire))

        if c_info.get('has_ref_clk'): inst.connections.append(PortConnection("ref_clk_i", "rt_clk"))
        elif c_info.get('has_rt_clk'): inst.connections.append(PortConnection("rt_clk_i", "rt_clk"))

        if c_info.get('has_sys_clk'): inst.connections.append(PortConnection("sys_clk_i", "host_clk"))
        if c_info.get('has_sys_rst'): inst.connections.append(PortConnection("sys_rst_ni", "host_pwr_on_rst_n"))

        if c_info.get('has_rtc'): inst.connections.append(PortConnection("rtc_i", "rt_clk"))
        if c_info.get('has_test_mode'): inst.connections.append(PortConnection("test_mode_i", "test_mode_i"))

        if c_info.get('has_boot_mode'): inst.connections.append(PortConnection("boot_mode_i", "boot_mode_i"))
        elif c_info.get('has_bootmode'): inst.connections.append(PortConnection("bootmode_i", "boot_mode_i"))

        if comp.dedicated_clock_div:
            div_clk = comp.dedicated_clock_div['name']
            div_port = comp.dedicated_clock_div.get('port', f"{div_clk}_i")
            inst.connections.append(PortConnection(div_port, div_clk))

        # System Controller PeakRDL connections
        if comp.system_config:
            c_name = comp.name
            reg_out = "sys_regs_hwif_out"
            reg_in = "sys_regs_hwif_in"
            if comp.system_config.get('isolate'):
                inst.connections.append(PortConnection("axi_isolate_i", f"{reg_out}.isolate_ctrl.{c_name}_isolate.value"))
                inst.connections.append(PortConnection("axi_isolated_o", f"{reg_in}.isolate_status.{c_name}_isolated.next"))
            if comp.system_config.get('fetch_enable'):
                inst.connections.append(PortConnection("fetch_en_i", f"{reg_out}.fetch_enable.{c_name}_fetch_enable.value"))
            if comp.system_config.get('boot_enable'):
                inst.connections.append(PortConnection("en_sa_boot_i", f"{reg_out}.boot_enable.{c_name}_boot_enable.value"))
            if comp.system_config.get('debug_req'):
                dim = ""
                p_info_dbg = c_info.get("ports", {}).get("debug_req_i")
                if p_info_dbg:
                    dim = re.findall(r'\[.*?\]', p_info_dbg["type_dim"])
                if dim:
                    inst.connections.append(PortConnection("debug_req_i", f"'{{default: {reg_out}.debug_req.{c_name}_debug_req.value}}"))
                else:
                    inst.connections.append(PortConnection("debug_req_i", f"{reg_out}.debug_req.{c_name}_debug_req.value"))
            if 'boot_addr' in comp.system_config and c_info.get("has_boot_addr"):
                inst.connections.append(PortConnection("boot_addr_i", f"{reg_out}.{c_name}_boot_addr.{c_name}_boot_addr.value"))
            if comp.system_config.get('has_busy_status'):
                inst.connections.append(PortConnection("busy_o", f"{reg_in}.busy_status.{c_name}_busy.next"))
            if comp.system_config.get('has_eoc_status') and 'eoc' not in (comp.interrupts or {}) and 'eoc_o' not in (comp.interrupts or {}):
                inst.connections.append(PortConnection("eoc_o", f"{reg_in}.eoc_status.{c_name}_eoc.next"))

        # Wiring matrix connections
        for wc in wiring_matrix.get(comp.name, []):
            m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(\s*(.*)\s*\)\s*$', wc.strip())
            if m:
                p_name = m.group(1).strip()
                expr = m.group(2).strip()
                if comp.name in comp_extra_conns:
                    exported_ports = [c.split('(')[0].strip().strip('.') for c in comp_extra_conns[comp.name]]
                    if p_name in exported_ports:
                        continue
                inst.connections.append(PortConnection(p_name, expr))

        # Exported interfaces
        if comp.name in comp_extra_conns:
            for ec in comp_extra_conns[comp.name]:
                m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(\s*(.*)\s*\)\s*$', ec.strip())
                if m:
                    inst.connections.append(PortConnection(m.group(1).strip(), m.group(2).strip()))

        # Auto-tie-off remaining ports
        connected_ports = {c.port_name for c in inst.connections}
        for port_name, p_info in c_info.get("ports", {}).items():
            if port_name not in connected_ports:
                val = "'0" if p_info["dir"] == "input" else ""
                inst.connections.append(PortConnection(port_name, val))


def build_noc_ir(ir, soc_config, comp_info, noc_comp_extra_conns, original_isle_types):
    """
    Populate *ir* with instances and connections for a NoC (FlooNoC) topology.

    Builds the physical 2-D mesh grid from component placement metadata, fills
    unoccupied coordinates with dummy-tile instances, and wires every real tile
    to its clock, reset, NoC router ports, and system-controller hooks.
    """
    max_x, max_y = 0, 0
    grid = {}
    comps = [soc_config.host] + (soc_config.components if soc_config.components else [])
    for c in comps:
        p = getattr(c, 'placement', None)
        if not p or 'logical' not in p:
            continue
        log = p['logical']
        items = log if isinstance(log, list) else [log]
        inst_idx = 0
        for item in items:
            if 'box' in item:
                b = item['box']
                for x in range(b['x_start'], b['x_end'] + 1):
                    for y in range(b['y_start'], b['y_end'] + 1):
                        grid[(x, y)] = (c, inst_idx)
                        inst_idx += 1
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
            else:
                x, y = item['x'], item['y']
                grid[(x, y)] = (c, inst_idx)
                inst_idx += 1
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    # Fill unassigned physical coordinates with None to indicate where a Dummy
    # Tile (a pure FlooNoC router with no attached IP) should be instantiated.
    for x in range(max_x + 1):
        for y in range(max_y + 1):
            if (x, y) not in grid:
                grid[(x, y)] = (None, 0)

    host_clk = soc_config.host.clock_domain or "system_clk"

    for y in range(max_y + 1):
        for x in range(max_x + 1):
            c, inst_idx = grid[(x, y)]
            t_name = f"i_tile_{x}_{y}"
            if c is None:
                inst = ir.add_instance(t_name, f"{soc_config.project.name}_dummy_tile")
                inst.connections.append(PortConnection("clk_i", host_clk))
                inst.connections.append(PortConnection("rst_ni", "host_pwr_on_rst_n"))
                inst.connections.append(PortConnection("test_mode_i", "test_mode_i"))
                inst.connections.append(PortConnection("id_i", f"{{ x: {x}, y: {y}, port_id: 0 }}"))
                inst.connections.append(PortConnection("floo_req_o", f"tile_req_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_i", f"tile_rsp_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_o", f"tile_wide_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_req_i", f"tile_req_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_o", f"tile_rsp_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_i", f"tile_wide_i[{x}][{y}]"))
            else:
                is_host = (c.name == soc_config.host.name)
                module_type = f"{soc_config.project.name}_{c.type}"
                inst = ir.add_instance(t_name, module_type)

                # Note: tile coordinates are passed via id_i port (below), not as
                # module parameters. Tiles do not declare x/y parameters.
                c_clk = c.clock_domain or host_clk
                c_rst = c.reset_domain or c_clk.replace('_clk', '_rst')
                c_rst_wire = 'host_pwr_on_rst_n' if c_rst == host_clk.replace('_clk', '_rst') else f'rsts_n[DomainIdx_{fmt_rst(c_rst)}]'

                inst.connections.append(PortConnection("clk_i", c_clk))
                inst.connections.append(PortConnection("rst_ni", c_rst_wire))
                inst.connections.append(PortConnection("test_mode_i", "test_mode_i"))
                inst.connections.append(PortConnection("id_i", f"'{{ x: {x}, y: {y}, port_id: 0 }}"))
                inst.connections.append(PortConnection("floo_req_o", f"tile_req_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_i", f"tile_rsp_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_o", f"tile_wide_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_req_i", f"tile_req_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_o", f"tile_rsp_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_i", f"tile_wide_i[{x}][{y}]"))

                if is_host:
                    inst.connections.append(PortConnection("sys_regs_hwif_out_o", "sys_regs_hwif_out"))
                    inst.connections.append(PortConnection("sys_regs_hwif_in_i", "sys_regs_hwif_in"))
                    inst.connections.append(PortConnection("boot_mode_i", "boot_mode_i"))
                    inst.connections.append(PortConnection("rtc_i", "rtc_i"))
                    has_ext_regs = any(is_external(comp) for comp in comps)
                    inst.connections.append(PortConnection("reg_req_o", "host_reg_req" if has_ext_regs else "/* unused */"))
                    inst.connections.append(PortConnection("reg_rsp_i", "host_reg_rsp" if has_ext_regs else "'0"))

                ctrl_group = None
                if soc_config.system_controller and soc_config.system_controller.auto_control_groups:
                    for g in soc_config.system_controller.auto_control_groups:
                        orig_type = original_isle_types.get(c.name, c.type)
                        if g.target_component_type in [c.type, orig_type, orig_type.replace('_isle', '_tile').replace('_subtile', '_tile')]:
                            ctrl_group = g
                            break
                if ctrl_group:
                    inst.connections.append(PortConnection("tile_clk_en_i", f"sys_regs_hwif_out.{ctrl_group.name.lower()}_clk_en.{ctrl_group.name.lower()}_clk_en.value[{inst_idx}]"))
                    inst.connections.append(PortConnection("tile_rst_ni", f"~sys_regs_hwif_out.{ctrl_group.name.lower()}_rst.{ctrl_group.name.lower()}_rst.value[{inst_idx}]"))
                    inst.connections.append(PortConnection("clk_rst_bypass_i", "clk_rst_bypass_i"))

                key = (c.name, inst_idx)
                if key in noc_comp_extra_conns:
                    for ec in noc_comp_extra_conns[key]:
                        m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(\s*(.*)\s*\)\s*$', ec.strip())
                        if m:
                            inst.connections.append(PortConnection(m.group(1).strip(), m.group(2).strip()))

                c_info = comp_info.get(c.name, {})
                tile_ports = c_info.get("ports", {})
                connected_ports = {conn.port_name for conn in inst.connections}
                for port_name, p_info in tile_ports.items():
                    if port_name not in connected_ports:
                        val = "'0" if p_info["dir"] == "input" else ""
                        inst.connections.append(PortConnection(port_name, val))

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


def get_instance_window(comp, inst_idx=0):
    """
    Calculate one instance's slave window (base address, size) for a component that
    decodes its own window internally - the values behind the InstanceBaseAddr /
    InstanceWindowSize identity parameters (docs/hw/subtile_standardization.md 2.6).
    """
    base_addr = 0
    size_val = 0
    if comp.interfaces and 'axi_slave' in comp.interfaces:
        slvs = comp.interfaces['axi_slave']
        if isinstance(slvs, list) and len(slvs) > 0:
            b_addr = slvs[0].get('base_addr', 0)
            b_val = int(b_addr, 16) if isinstance(b_addr, str) else b_addr
            raw_size = slvs[0].get('size_per_instance', slvs[0].get('size', 0))
            size_val = int(raw_size, 16) if isinstance(raw_size, str) and raw_size.startswith('0x') else int(raw_size)
            base_addr = b_val + inst_idx * size_val
    return f"64'h{base_addr:X}", str(size_val)


def get_type_param_fill(p, comp, soc_config, pkg):
    """Package-qualified type a component's TYPE parameter is filled with, or None.

    Extracted verbatim from build_crossbar_ir's dispatch (2026-08-14) so that the
    isle-staging pass can ask the same question the instantiation site answers: the
    hier-block work (wip 5.1) replaces `parameter type` in the staged isle copies
    with a generated per-isle types package, and its typedefs must be exactly these
    fills. The answer is ROLE-based - host, behind the LLC port, or plain slave -
    which is a per-component property: the staging transform may therefore only
    fire when every component of an isle type agrees on the role.
    """
    is_host = comp.name == soc_config.host.name
    is_llc = 'llc_port' in (comp.interfaces or {})

    def in_side(base):
        if is_host:
            return f"{pkg}::soc_axi_{base}"
        if is_llc:
            return f"{pkg}::soc_axi_llc_{base}"
        return f"{pkg}::soc_axi_slv_{base}"

    def out_side(base):
        return f"{pkg}::soc_axi_slv_{base}" if is_host else f"{pkg}::soc_axi_{base}"

    if p in ['axi_req_t', 'axi_in_req_t', 'sync_axi_in_req_t', 'axi_slave_req_t']:
        return in_side("req_t")
    if p in ['axi_resp_t', 'axi_in_resp_t', 'sync_axi_in_rsp_t', 'axi_slave_resp_t']:
        return in_side("resp_t")
    if p in ['axi_out_req_t', 'sync_axi_out_req_t', 'axi_master_req_t']:
        return out_side("req_t")
    if p in ['axi_out_resp_t', 'sync_axi_out_rsp_t', 'axi_master_resp_t']:
        return out_side("resp_t")
    for ch in ['aw', 'w', 'b', 'ar', 'r']:
        if p in [f'axi_{ch}_chan_t', f'axi_in_{ch}_chan_t']:
            return in_side(f"{ch}_chan_t")
        if p == f'axi_out_{ch}_chan_t':
            return out_side(f"{ch}_chan_t")
    if p in ['reg_req_t', 'sync_reg_in_req_t', 'sync_reg_out_req_t', 'async_reg_out_req_t']:
        return f"{pkg}::soc_reg_req_t"
    if p in ['reg_rsp_t', 'sync_reg_in_rsp_t', 'sync_reg_out_rsp_t', 'async_reg_out_rsp_t']:
        return f"{pkg}::soc_reg_rsp_t"
    return None


def build_crossbar_ir(ir, soc_config, comp_info, wiring_matrix, comp_extra_conns):
    """
    Populate *ir* with instances and connections for a Crossbar topology.

    Each component receives a single named instance with full AXI parameter
    substitution, clock/reset connections, system-controller hooks,
    wiring-matrix connections, exported-interface connections, and auto
    tie-offs for any remaining unconnected ports.
    """
    pkg = f"{soc_config.project.soc_pkg_name}"
    all_comps = [soc_config.host] + (soc_config.components if soc_config.components else [])

    for comp in all_comps:
        if is_external(comp):
            continue
        inst_name = f"i_{comp.name}"
        module_name = f"{soc_config.project.module_prefix}_{comp.type}"
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
            # TYPE parameters: filled by the shared role-based helper above, so the
            # isle-staging pass (wip 5.1 hier-block work) computes the same answer.
            elif (type_fill := get_type_param_fill(p, comp, soc_config, pkg)) is not None:
                inst.parameters[p] = type_fill
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
            elif p == 'InstanceBaseAddr':
                # INSTANCE IDENTITY (docs/hw/subtile_standardization.md section 2.6): a
                # component that decodes its own slave window internally (the pulp
                # cluster's cluster_bus_wrap, the memory isles' mapping rules) declares
                # this parameter and receives the axi_slave 'base_addr' the description
                # maps it at. Crossbar macros keep GLOBAL addresses inside - no border
                # rebase exists on this family, unlike the NoC one (build_noc_ir) - so
                # a macro build offsets the base by the macro's placement.
                b_val, _ = get_instance_window(comp)
                if soc_config.project.build_mode == "macro":
                    inst.parameters[p] = f"MACRO_BASE_ADDR + {b_val}"
                else:
                    inst.parameters[p] = b_val
            elif p == 'InstanceWindowSize':
                _, size_val = get_instance_window(comp)
                inst.parameters[p] = size_val
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
            detyped = c_info.get("detyped_params", ())
            for p_k, p_v in comp.parameters.items():
                # A name the de-typing pass moved into the isle's types package no
                # longer exists as a header parameter: overriding it would dangle
                # (vopt-2732). These entries are generator-injected (arch_optimizer's
                # reg types on the host), never user YAML, so dropping is silent.
                if p_k in detyped:
                    continue
                if isinstance(p_v, bool):
                    inst.parameters[p_k] = "1'b1" if p_v else "1'b0"
                elif isinstance(p_v, int) and p_v > 0x7FFFFFFF:
                    # An unsized decimal literal is SIGNED 32-bit in SV: past 2^31-1 it
                    # sign-extends when overriding a wider parameter (see the identical
                    # guard in build_noc_ir and the 2026-08-11 LlcOutRegionStart case).
                    inst.parameters[p_k] = f"64'h{p_v:X}"
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

        # INSTANCE IDENTITY ON A PORT (2026-08-20). The twin of the InstanceBaseAddr
        # parameter above, for isles that take the base at run time instead: it MUST
        # be connected explicitly, because the tie-off below would otherwise drive it
        # to '0 and the isle would decode its window at address zero - a valid design
        # that never boots. Same value and same macro rebase as the parameter path.
        if "instance_base_addr_i" in (c_info.get("ports") or {}):
            b_val, _ = get_instance_window(comp)
            expr = (f"MACRO_BASE_ADDR + {b_val}"
                    if soc_config.project.build_mode == "macro" else b_val)
            inst.connections.append(PortConnection("instance_base_addr_i", expr))

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
                inst = ir.add_instance(t_name, f"{soc_config.project.module_prefix}_dummy_tile")
                inst.connections.append(PortConnection("clk_i", host_clk))
                inst.connections.append(PortConnection("rst_ni", "host_pwr_on_rst_n"))
                inst.connections.append(PortConnection("test_mode_i", "test_mode_i"))
                inst.connections.append(PortConnection("id_i", f"'{{ x: {x}, y: {y}, port_id: 0 }}"))
                inst.connections.append(PortConnection("floo_req_o", f"tile_req_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_i", f"tile_rsp_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_o", f"tile_wide_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_req_i", f"tile_req_i[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_rsp_o", f"tile_rsp_o[{x}][{y}]"))
                inst.connections.append(PortConnection("floo_wide_i", f"tile_wide_i[{x}][{y}]"))
            else:
                is_host = (c.name == soc_config.host.name)
                module_type = f"{soc_config.project.module_prefix}_{c.type}"
                inst = ir.add_instance(t_name, module_type)

                # Populate instance parameters from user-defined YAML configuration (host and components)
                if c.parameters:
                    for p_name, p_val in c.parameters.items():
                        if p_name.startswith("AxiNum"):
                            continue
                        if isinstance(p_val, bool):
                            formatted_val = "1'b1" if p_val else "1'b0"
                        elif isinstance(p_val, int):
                            # An unsized decimal literal is a SIGNED 32-bit value in SV:
                            # anything past 2^31-1 would sign-extend when it overrides a
                            # wider parameter (LlcOutRegionStart=0xD000_0000 became
                            # 0xFFFF_FFFF_D000_0000 and broke CVA6's execute region,
                            # found 2026-08-11). Size everything past the boundary.
                            formatted_val = f"64'h{p_val:X}" if p_val > 0x7FFFFFFF else str(p_val)
                        else:
                            formatted_val = str(p_val)
                        inst.parameters[p_name] = formatted_val

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
                    inst.connections.append(PortConnection("rt_clk_i", "rt_clk_i"))
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
                    gn = ctrl_group.name.lower()
                    # The packed control registers hold exactly one bit per controlled tile.
                    # PeakRDL emits a single-bit SystemRDL field as a scalar `logic`, which
                    # cannot be bit-selected, so a one-tile group is referenced without index.
                    group_width = soc_config.control_group_width(ctrl_group, original_isle_types)
                    bit_sel = f"[{inst_idx}]" if group_width > 1 else ""
                    inst.connections.append(PortConnection("tile_clk_en_i", f"sys_regs_hwif_out.{gn}_clk_en.{gn}_clk_en.value{bit_sel}"))
                    inst.connections.append(PortConnection("tile_rst_ni", f"~sys_regs_hwif_out.{gn}_rst.{gn}_rst.value{bit_sel}"))
                    inst.connections.append(PortConnection("clk_rst_bypass_i", "clk_rst_bypass_i"))

                key = (c.name, inst_idx)
                if key in noc_comp_extra_conns:
                    for ec in noc_comp_extra_conns[key]:
                        m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(\s*(.*)\s*\)\s*$', ec.strip())
                        if m:
                            inst.connections.append(PortConnection(m.group(1).strip(), m.group(2).strip()))

                c_info = comp_info.get(c.name, {})
                tile_ports = c_info.get("ports", {})

                # INSTANCE IDENTITY parameters (docs/hw/subtile_standardization.md,
                # section 2.6): a component that decodes its own slave window declares
                # InstanceBaseAddr / InstanceWindowSize in its header, and every
                # instance receives ITS OWN window here - base + inst_idx * stride,
                # the same x-major enumeration FlooGen's address map and the control
                # group bit-selects use. The header opts in; no component- or
                # port-name matching is involved. One route for every self-mapping
                # component: the snitch cluster arrays and the memory isles alike
                # (the former per-component L2 override with its name heuristic was
                # absorbed here, 2026-08-11). Values stay PROJECT-LOCAL in macro
                # builds too: the NoC border adapters rebase incoming traffic (they
                # subtract MACRO_BASE_ADDR before any tile sees it, noc_soc_top
                # .sv.mako) - the crossbar family keeps global addresses instead,
                # see the same parameter in build_crossbar_ir. Left at the '0
                # default, every window access missed the internal decode and hung
                # the host (found 2026-08-10).
                supported = c_info.get("supported_params", {})
                # THE BASE MAY ARRIVE AS A PORT INSTEAD OF A PARAMETER (2026-08-20).
                # A subtile that needs the window base only at run time declares
                # 'instance_base_addr_i' and the constant is DRIVEN, not elaborated:
                # every instance then shares one module, where a per-instance
                # parameter made Verilator specialize the tile once per instance
                # (sixteen cluster tiles, sixteen elaborations - wip 5.2.-1). The
                # parameter path stays for the isles that build elaboration-time
                # structures from the value, l2_isle's mapping rules being the case.
                base_is_port = "instance_base_addr_i" in tile_ports
                if base_is_port or "InstanceBaseAddr" in supported:
                    slaves = (c.interfaces or {}).get("axi_slave", [])
                    if isinstance(slaves, dict):
                        slaves = [slaves]
                    if slaves:
                        s_base = slaves[0].get("base_addr", 0)
                        s_base = int(s_base, 0) if isinstance(s_base, str) else int(s_base)
                        s_size = slaves[0].get("size_per_instance", slaves[0].get("size", 0))
                        s_size = int(s_size, 0) if isinstance(s_size, str) else int(s_size)
                        base_lit = f"64'h{s_base + inst_idx * s_size:X}"
                        if base_is_port:
                            inst.connections.append(PortConnection(
                                "instance_base_addr_i", base_lit))
                        else:
                            inst.parameters["InstanceBaseAddr"] = base_lit
                        if "InstanceWindowSize" in supported:
                            inst.parameters["InstanceWindowSize"] = f"64'h{s_size:X}"

                connected_ports = {conn.port_name for conn in inst.connections}
                for port_name, p_info in tile_ports.items():
                    if port_name not in connected_ports:
                        val = "'0" if p_info["dir"] == "input" else ""
                        inst.connections.append(PortConnection(port_name, val))

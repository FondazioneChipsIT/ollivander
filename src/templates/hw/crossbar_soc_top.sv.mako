<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE SOC TOP-LEVEL (CROSSBAR TOPOLOGY)
  # ============================================================================
  # This template generates the absolute Top-Level SystemVerilog module for a 
  # traditional, Crossbar-based SoC architecture. It is responsible for 
  # orchestrating the entire system:
  # 1. Instantiating the Clock and Reset distribution trees.
  # 2. Generating the massive multidimensional arrays for AXI and RegBus routing.
  # 3. Automatically injecting Clock Domain Crossing (CDC) synchronizers for interrupts.
  # 4. Instantiating all the hardware components (Isles) and wiring them together.

  p_name = config.project.name
  pkg    = config.project.soc_pkg_name
  rpkg   = f"{top_level_module_name}_sys_regs_pkg"
  host_clk = config.host.clock_domain or "system_clk"
      
  import re
  from core.utils import simplify_port_ranges

  # Resolves SystemVerilog dimensions by substituting 'parameter' names with their
  # actual integer values defined in the component's YAML configuration or the 
  # module's default 'fixed_params', evaluating simple math expressions if needed.
  def resolve_dim(c, c_info, dim_str):
      params = {}
      if c_info:
          params.update(c_info.get('fixed_params', {}))
          supported = c_info.get('supported_params', {})
          if isinstance(supported, dict):
              params.update(supported)
      if getattr(c, 'parameters', None):
          params.update(c.parameters)
          
      for pk, pv in params.items():
          dim_str = re.sub(r'\b' + re.escape(pk) + r'\b', str(pv), dim_str)
          
      def eval_math(m):
          parts = m.group(1).split(':')
          eval_parts = []
          for p in parts:
              try:
                  val = eval(p, {"__builtins__": {}})
                  eval_parts.append(str(val))
              except Exception:
                  eval_parts.append(p.strip())
          return '[' + ':'.join(eval_parts) + ']'
          
      return re.sub(r'\[(.*?)\]', eval_math, dim_str)

  # Extracts the array dimension (e.g. '[31:0]') of a specific port by parsing 
  # the SystemVerilog header extracted during Phase 2.
  def get_port_dim(c_name, port_name, is_input):
      c_info = comp_info.get(c_name, {})
      ports = c_info.get("ports", {})
      p_info = ports.get(port_name)
      if not p_info:
          base_port = port_name[:-2] if (is_input and port_name.endswith('_i')) or (not is_input and port_name.endswith('_o')) else port_name
          p_info = ports.get(base_port)
          
      if p_info:
          dims = re.findall(r'\[.*?\]', p_info["type_dim"])
          if dims:
              c_obj = next((x for x in [config.host] + config.components if x.name == c_name), None)
              return resolve_dim(c_obj, c_info, "".join(dims))
      return ""

  def get_rep_factor(dim_str):
      if not dim_str: return ""
      m = re.match(r'\[(.*?):(.*?)\s*\]', dim_str)
      if m:
          try:
              val = int(m.group(1)) - int(m.group(2)) + 1
              return str(val) if val > 1 else ""
          except Exception:
              u = m.group(1).strip()
              l = m.group(2).strip()
              if l == '0':
                  if u.endswith('-1'): return u[:-2].strip()
                  if u.endswith('- 1'): return u[:-3].strip()
              return f"({u})-({l})+1"
      return ""

  # Validates that a source component referenced in an interrupt mapping 
  # actually exists in the topology. Missing components are safely ignored 
  # to allow partial SoC generation without causing syntax errors.
  def check_src_valid(src_expr):
      src_comp_names = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', src_expr))
      for sc in src_comp_names:
          found = False
          if sc == config.host.name:
              found = True
          else:
              for c in config.components:
                  if c.name == sc: found = True; break
                  if c.components:
                      for sub in c.components:
                          if sub.name == sc: found = True; break
          if not found:
              return False, sc
      return True, None

  # Pre-compute interrupt wires and required packages strictly used in Top-Level logic
  def get_all_irqs(comps, parent_clk=None, parent_rst=None):
      irqs = []
      for c in comps:
          c_clk = c.clock_domain or parent_clk or "host_clk"
          c_rst = c.reset_domain or parent_rst or "host_rst"
          if c.interrupts:
              for irq_name, irq_cfg in c.interrupts.items():
                  irqs.append((c, irq_name, irq_cfg, c_clk, c_rst))
      return irqs
  
  all_irqs = get_all_irqs([config.host] + config.components)

  # Extract all physical output interrupt ports that need a wire declaration
  out_ports = {}
  
  for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
      if not irq_cfg.get('source'):
          port_name = irq_cfg.get('port', irq_name)
          if (c.name, port_name) not in out_ports:
              fallback = irq_cfg.get('width', 1)
              c_info = comp_info.get(c.name, {})
              header = c_info.get("header_content", "")
              parse_dim = irq_cfg.get('parse_sv_dim', True)
              dim = ""
              if parse_dim:
                  ports = c_info.get("ports", {})
                  base_port = port_name[:-2] if port_name.endswith('_o') else port_name
                  p_info = ports.get(port_name) or ports.get(base_port)
                  if p_info:
                      dims = re.findall(r'\[.*?\]', p_info["type_dim"])
                      if dims:
                          dim = resolve_dim(c, c_info, "".join(dims))
              if not dim and fallback > 1:
                  dim = f"[{fallback-1}:0]"
              out_ports[(c.name, port_name)] = dim
      else:
          dim = get_port_dim(c.name, irq_name, is_input=True)
          
%><%namespace file="/license_header.mako" import="license"/>\
${license()}\
//
// AUTOMATICALLY GENERATED BY OLLIVANDER - DO NOT EDIT DIRECTLY
//
// Top-Level SystemVerilog Module for ${p_name.upper()}
// Topology: Centralized Crossbar (AXI4)
//
// This module serves as the physical wrapper for the entire System-on-Chip.
// It exposes external memory interfaces (LLC/DRAM), standardized physical 
// peripherals (UART, SPI, I2C), and debug interfaces (JTAG), while hiding
// the internal routing matrices and synchronization logic.
//
// OLLIVANDER_MACRO_PRAGMAS_PLACEHOLDER

`include "axi/typedef.svh"
`include "axi/assign.svh"
`include "register_interface/typedef.svh"
`include "apb/typedef.svh"

module ${top_level_module_name}
  import ${pkg}::*;
  import ${rpkg}::*;
  import axi_pkg::*;
<%
  # Auto-inject imports from component headers to resolve exported constants and types
  all_imports = set()
  for c in [config.host] + config.components:
      imports = comp_info.get(c.name, {}).get("imports", [])
      for imp in imports:
          if imp not in [pkg, rpkg, "axi_pkg"]:
              all_imports.add(imp)
%>\
% for imp in sorted(all_imports):
  import ${imp}::*;
% endfor
<%
  ## Kept in variables so that each separator can be emitted at the end of the line it
  ## belongs to: a comma produced from inside the conditional block below lands on a
  ## line of its own instead.
  is_macro = config.project.build_mode == "macro"
  has_macro_masters = is_macro and config.project.macro_settings and config.project.macro_settings.masters
%>
#(
  // Standard geometry, referenced from the SoC package rather than re-emitted here: two
  // copies of the same width are what let this header contradict the package it imports.
  // Nothing inside the module reads them - they are the contract a parent and the
  // documentation see.
  localparam int unsigned AxiAddrWidth = ${pkg}::AxiAddrWidth,
  localparam int unsigned AxiDataWidth = ${pkg}::AxiDataWidth,
  localparam int unsigned AxiUserWidth = ${pkg}::AxiUserWidth,
  localparam int unsigned AxiIdWidth   = ${pkg}::AxiIdWidth${"," if is_macro else ""}
% if is_macro:
  // Incoming requests carry the interconnect's own ID; outgoing ones leave through the
  // exported master port, whose width the crossbar widens to address its slaves and
  // which is published as MacroMstIdWidth. Emitting AxiIdWidth for both, as this header
  // used to, understated the master port by four bits.
  localparam int unsigned AxiInIdWidth  = ${pkg}::AxiIdWidth,
  localparam int unsigned AxiOutIdWidth = ${pkg}::MacroMstIdWidth,
  // Macro Base Address for hardware address translation
  parameter logic [63:0] MACRO_BASE_ADDR = 64'h0,
  // Macro Types
  parameter type axi_req_t  = ${pkg}::soc_axi_req_t,
  parameter type axi_resp_t = ${pkg}::soc_axi_resp_t${"," if has_macro_masters else ""}
%   if has_macro_masters:
  parameter type axi_master_req_t  = ${pkg}::soc_axi_slv_req_t,
  parameter type axi_master_resp_t = ${pkg}::soc_axi_slv_resp_t
%   endif
% endif
) (
  // ---------------------------------------------------------
  // Global Clocks, Resets and Control
  // ---------------------------------------------------------
% if config.clock_tree.generators > 0:
  input  logic [${config.clock_tree.generators - 1}:0] domain_clk_i,
  input  logic [${config.clock_tree.generators - 1}:0] clk_gen_lock_i,
% else:
  input  logic clk_i,
  input  logic rst_ni,
% endif
  input  logic pwr_on_rst_ni,
  input  logic test_mode_i,
  // Simulation/bring-up bypass of the clocking infrastructure (RT dividers),
  // name-uniform with the NoC top. Tie low in silicon use.
  input  logic clk_rst_bypass_i,
<%
  has_rt_clk = any(dom.is_real_time and (dom.source_gen is None or config.clock_tree.generators == 0) for dom in config.clock_tree.domains)
%>\
% if has_rt_clk:
  input  logic rt_clk_i,
% endif
  input  logic [1:0] boot_mode_i\
<%
    top_ports_list = list(top_ports)
    
    ext_async_slaves = []
    ext_sync_slaves = []
    for comp in config.components:
        if is_external(comp):
            slvs = comp.interfaces.get('regbus_slave', [])
            if isinstance(slvs, dict): slvs = [slvs]
            if slvs[0].get('sync_domain', True):
                ext_sync_slaves.append(comp)
            else:
                ext_async_slaves.append(comp)
    num_ext_async_slaves = len(ext_async_slaves)

    if num_ext_async_slaves > 0:
        width_str = f"[{num_ext_async_slaves-1}:0]" if num_ext_async_slaves > 1 else ""
        top_ports_list.append(f"output logic     {width_str} ext_reg_async_slv_req_o")
        top_ports_list.append(f"input  logic     {width_str} ext_reg_async_slv_ack_i")
        top_ports_list.append(f"output {pkg}::soc_reg_req_t {width_str} ext_reg_async_slv_data_o")
        top_ports_list.append(f"input  logic     {width_str} ext_reg_async_slv_req_i")
        top_ports_list.append(f"output logic     {width_str} ext_reg_async_slv_ack_o")
        top_ports_list.append(f"input  {pkg}::soc_reg_rsp_t {width_str} ext_reg_async_slv_data_i")

    for comp in ext_sync_slaves:
        top_ports_list.append(f"output {pkg}::soc_reg_req_t {comp.name}_reg_req_o")
        top_ports_list.append(f"input  {pkg}::soc_reg_rsp_t {comp.name}_reg_rsp_i")

    if config.project.build_mode == "macro" and config.project.macro_settings:
        if config.project.macro_settings.slaves:
            top_ports_list.append("input  axi_req_t  axi_req_i")
            top_ports_list.append("output axi_resp_t axi_resp_o")
        if config.project.macro_settings.masters:
            top_ports_list.append("output axi_master_req_t  axi_req_o")
            top_ports_list.append("input  axi_master_resp_t axi_resp_i")
%>${"," if top_ports_list else ""}
% if top_ports_list:

  // ---------------------------------------------------------
  // External Component Ports
  // ---------------------------------------------------------
  ${",\n  ".join(top_ports_list)}
% endif
);

  // SoC Registers interfaces
  ${top_level_module_name}_sys_regs_pkg::${top_level_module_name}_sys_regs__out_t sys_regs_hwif_out;
  ${top_level_module_name}_sys_regs_pkg::${top_level_module_name}_sys_regs__in_t  sys_regs_hwif_in;

  // Root host reset, always present (driven by clock_and_reset_tree).
  // The per-domain vectors `pwr_on_rsts_n` / `rsts_n` are declared by that same
  // macro, but only when the SoC actually has a global reset tree to drive them.
  logic host_pwr_on_rst_n;

% if not has_rt_clk:
  logic rt_clk_i;
  assign rt_clk_i = 1'b0;
% endif

  // Physical Interconnect Wires
% for (c_name, prt_name), dim in out_ports.items():
  logic ${dim + " " if dim else ""}intr_${c_name}_${prt_name};
% endfor

  // =========================================================================
  // 1. CLOCK AND RESET TREE
  // =========================================================================
<%namespace file="/hw/infrastructure/clock_reset.mako" import="clock_and_reset_tree"/>\
${clock_and_reset_tree(config, p_name)}

  // =========================================================================
  // 2. SYSTEM CONTROLLER REGISTERS (PCRs)
  // =========================================================================
  // The System Controller houses the Power, Clock, and Reset (PCR) registers.
  // It controls the dynamic clock gating and reset state of every peripheral.
  
  ${pkg}::soc_reg_req_t pcrs_req;
  ${pkg}::soc_reg_rsp_t pcrs_rsp;
  ${pkg}::soc_reg_req_t pcrs_req_cut;
  ${pkg}::soc_reg_rsp_t pcrs_rsp_cut;
  
  // Pipeline cut for timing closure on the central system registers.
  // Because the PCRs fan out to the entire chip, this bus is heavily loaded.
  // Adding a register slice here drastically improves physical synthesis timing.
  reg_cut #(
    .req_t ( ${pkg}::soc_reg_req_t ),
    .rsp_t ( ${pkg}::soc_reg_rsp_t )
  ) i_sys_ctrl_reg_cut (
    .clk_i     ( host_clk ),
    .rst_ni    ( host_pwr_on_rst_n ),
    .src_req_i ( pcrs_req ),
    .src_rsp_o ( pcrs_rsp ),
    .dst_req_o ( pcrs_req_cut ),
    .dst_rsp_i ( pcrs_rsp_cut )
  );
  
  // RegBus to APB Adapter for the PeakRDL System Controller.
  // Converts the internal high-performance RegBus into standard APB4.
  typedef logic [31:0] sys_apb_addr_t;
  typedef logic [31:0] sys_apb_data_t;
  typedef logic [3:0]  sys_apb_strb_t;
  `APB_TYPEDEF_ALL(sys_apb, sys_apb_addr_t, sys_apb_data_t, sys_apb_strb_t)

  sys_apb_req_t pcrs_apb_req;
  sys_apb_resp_t pcrs_apb_rsp;

  reg_to_apb #(
    .reg_req_t ( ${pkg}::soc_reg_req_t ),
    .reg_rsp_t ( ${pkg}::soc_reg_rsp_t ),
    .apb_req_t ( sys_apb_req_t ),
    .apb_rsp_t ( sys_apb_resp_t )
  ) i_sys_ctrl_reg_to_apb (
    .clk_i     ( host_clk ),
    .rst_ni    ( host_pwr_on_rst_n ),
    .reg_req_i ( pcrs_req_cut ),
    .reg_rsp_o ( pcrs_rsp_cut ),
    .apb_req_o ( pcrs_apb_req ),
    .apb_rsp_i ( pcrs_apb_rsp )
  );

  ${top_level_module_name}_sys_regs i_sys_ctrl_regs (
    .clk            ( host_clk ),
    .arst_n         ( host_pwr_on_rst_n ), // Async active-low reset
    .s_apb_paddr    ( pcrs_apb_req.paddr[${sys_regs_addr_width-1}:0] ),
    .s_apb_pprot    ( pcrs_apb_req.pprot ),
    .s_apb_psel     ( pcrs_apb_req.psel ),
    .s_apb_penable  ( pcrs_apb_req.penable ),
    .s_apb_pwrite   ( pcrs_apb_req.pwrite ),
    .s_apb_pwdata   ( pcrs_apb_req.pwdata ),
    .s_apb_pstrb    ( pcrs_apb_req.pstrb ),
    .s_apb_pready   ( pcrs_apb_rsp.pready ),
    .s_apb_prdata   ( pcrs_apb_rsp.prdata ),
    .s_apb_pslverr  ( pcrs_apb_rsp.pslverr ),
    .hwif_in        ( sys_regs_hwif_in ),
    .hwif_out       ( sys_regs_hwif_out )
  );
  
% if config.system_controller and config.system_controller.clk_gen_status_regs:
  assign sys_regs_hwif_in.clk_gen_lock.clk_gen_lock.next  = clk_gen_lock_i;
% endif

% for c in config.components:
 % if c.system_config and c.system_config.get('has_eoc_status'):
  % if c.interrupts and 'eoc_o' in c.interrupts and not c.interrupts['eoc_o'].get('source'):
  assign sys_regs_hwif_in.eoc_status.${c.name}_eoc.next = intr_${c.name}_eoc_o;
  % endif
 % endif
% endfor

  // =========================================================================
  // 3. CONNECTION MATRIX (AXI, REGBUS, IRQ)
  // =========================================================================
  // Ollivander implements Crossbars using massive multidimensional packed arrays.
  // The Host module contains the physical router and exposes these global arrays,
  // while the individual components connect to specific slices (indices) of them.
  localparam int unsigned LogDepth = 3;
  localparam int unsigned AxiSlvIdWidth = ${pkg}::ExtSlvIdWidth;
  
  localparam int unsigned XbarSlvAwWidth = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, AxiSlvIdWidth, AxiUserWidth);
  localparam int unsigned XbarSlvWWidth  = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth);
  localparam int unsigned XbarSlvBWidth  = (2**LogDepth)*axi_pkg::b_width(AxiSlvIdWidth, AxiUserWidth);
  localparam int unsigned XbarSlvArWidth = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, AxiSlvIdWidth, AxiUserWidth);
  localparam int unsigned XbarSlvRWidth  = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, AxiSlvIdWidth, AxiUserWidth);

  localparam int unsigned XbarMstAwWidth = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, AxiIdWidth, AxiUserWidth);
  localparam int unsigned XbarMstWWidth  = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth);
  localparam int unsigned XbarMstBWidth  = (2**LogDepth)*axi_pkg::b_width(AxiIdWidth, AxiUserWidth);
  localparam int unsigned XbarMstArWidth = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, AxiIdWidth, AxiUserWidth);
  localparam int unsigned XbarMstRWidth  = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, AxiIdWidth, AxiUserWidth);

<% 
  channels = [
    ('aw_data', 'XbarSlvAwWidth', 'XbarMstAwWidth'), ('aw_wptr', 'LogDepth+1', 'LogDepth+1'), ('aw_rptr', 'LogDepth+1', 'LogDepth+1'),
    ('w_data',  'XbarSlvWWidth', 'XbarMstWWidth'),   ('w_wptr',  'LogDepth+1', 'LogDepth+1'), ('w_rptr',  'LogDepth+1', 'LogDepth+1'),
    ('b_data',  'XbarSlvBWidth', 'XbarMstBWidth'),   ('b_wptr',  'LogDepth+1', 'LogDepth+1'), ('b_rptr',  'LogDepth+1', 'LogDepth+1'),
    ('ar_data', 'XbarSlvArWidth', 'XbarMstArWidth'), ('ar_wptr', 'LogDepth+1', 'LogDepth+1'), ('ar_rptr', 'LogDepth+1', 'LogDepth+1'),
    ('r_data',  'XbarSlvRWidth', 'XbarMstRWidth'),   ('r_wptr',  'LogDepth+1', 'LogDepth+1'), ('r_rptr',  'LogDepth+1', 'LogDepth+1')
  ]
%>
  `define IOMSB(x) ((x) > 0 ? (x) - 1 : 0)

  // Slaves (Host -> Components)
% for sig, slv_w, mst_w in channels:
  logic [`IOMSB(${pkg}::NumAxiSlavesAsync):0][${slv_w}-1:0] xbar_slv_${sig};
% endfor

  // Synchronous Slaves (Host -> Components)
  ${pkg}::soc_axi_slv_req_t  [`IOMSB(${pkg}::NumAxiSlavesSync):0] xbar_sync_slv_req;
  ${pkg}::soc_axi_slv_resp_t [`IOMSB(${pkg}::NumAxiSlavesSync):0] xbar_sync_slv_rsp;

  // Masters (Components -> Host)
% for sig, slv_w, mst_w in channels:
  logic [`IOMSB(${pkg}::NumAxiMastersAsync):0][${mst_w}-1:0] xbar_mst_${sig};
% endfor

  // Synchronous Masters (Components -> Host)
  ${pkg}::soc_axi_req_t  [`IOMSB(${pkg}::NumAxiMastersSync):0] xbar_sync_mst_req;
  ${pkg}::soc_axi_resp_t [`IOMSB(${pkg}::NumAxiMastersSync):0] xbar_sync_mst_rsp;

`ifndef SYNTHESIS
  // PROGRESS MONITOR COUNTERS (simulation only, read by the testbench under
  // +progress): one free-running count of AW, AR and W handshakes per crossbar
  // port, in the package's enumeration order (axi_slv_idx_e / axi_mst_idx_e:
  // asynchronous ports first, then synchronous). The crossbar twin of the mesh
  // top's per-tile link counters: with them a port polling at full rate while the
  // others sit at zero reads as a wait that will not end, a whole list at zero as
  // a stall. Sync ports count valid & ready; async ports count the steps of the
  // CDC write pointers, one per item pushed, which is the same thing seen from the
  // top. Every increment of a cycle is summed in ONE assignment: separate
  // non-blocking increments would keep only the last one.
  int unsigned mon_slv_cnt [`IOMSB(${pkg}::NumAxiSlaves):0];
  int unsigned mon_mst_cnt [`IOMSB(${pkg}::NumAxiMasters):0];
  for (genvar i = 0; i < ${pkg}::NumAxiSlavesAsync; i++) begin : gen_mon_slv_async
    logic [LogDepth:0] aw_q, ar_q, w_q;
    always_ff @(posedge host_clk) begin
      aw_q <= xbar_slv_aw_wptr[i];
      ar_q <= xbar_slv_ar_wptr[i];
      w_q  <= xbar_slv_w_wptr[i];
      mon_slv_cnt[i] <= mon_slv_cnt[i] + 32'(xbar_slv_aw_wptr[i] != aw_q)
                                       + 32'(xbar_slv_ar_wptr[i] != ar_q)
                                       + 32'(xbar_slv_w_wptr[i]  != w_q);
    end
  end
  for (genvar i = 0; i < ${pkg}::NumAxiSlavesSync; i++) begin : gen_mon_slv_sync
    always_ff @(posedge host_clk) begin
      mon_slv_cnt[${pkg}::NumAxiSlavesAsync + i] <= mon_slv_cnt[${pkg}::NumAxiSlavesAsync + i]
          + 32'(xbar_sync_slv_req[i].aw_valid && xbar_sync_slv_rsp[i].aw_ready)
          + 32'(xbar_sync_slv_req[i].ar_valid && xbar_sync_slv_rsp[i].ar_ready)
          + 32'(xbar_sync_slv_req[i].w_valid  && xbar_sync_slv_rsp[i].w_ready);
    end
  end
  for (genvar i = 0; i < ${pkg}::NumAxiMastersAsync; i++) begin : gen_mon_mst_async
    logic [LogDepth:0] aw_q, ar_q, w_q;
    always_ff @(posedge host_clk) begin
      aw_q <= xbar_mst_aw_wptr[i];
      ar_q <= xbar_mst_ar_wptr[i];
      w_q  <= xbar_mst_w_wptr[i];
      mon_mst_cnt[i] <= mon_mst_cnt[i] + 32'(xbar_mst_aw_wptr[i] != aw_q)
                                       + 32'(xbar_mst_ar_wptr[i] != ar_q)
                                       + 32'(xbar_mst_w_wptr[i]  != w_q);
    end
  end
  for (genvar i = 0; i < ${pkg}::NumAxiMastersSync; i++) begin : gen_mon_mst_sync
    always_ff @(posedge host_clk) begin
      mon_mst_cnt[${pkg}::NumAxiMastersAsync + i] <= mon_mst_cnt[${pkg}::NumAxiMastersAsync + i]
          + 32'(xbar_sync_mst_req[i].aw_valid && xbar_sync_mst_rsp[i].aw_ready)
          + 32'(xbar_sync_mst_req[i].ar_valid && xbar_sync_mst_rsp[i].ar_ready)
          + 32'(xbar_sync_mst_req[i].w_valid  && xbar_sync_mst_rsp[i].w_ready);
    end
  end
`endif

  // Dedicated LLC Wires (Host <-> LLC Peripheral)
% for sig, slv_w, mst_w in channels:
<%
  llc_w = "Llc" + sig.split('_')[0].capitalize() + "Width" if sig.endswith('_data') else mst_w
%>
  logic [${pkg}::${llc_w}-1:0] async_axi_llc_${sig};
% endfor

  ${pkg}::soc_reg_req_t [${pkg}::NumTotalRegSlaves-1:0] sys_reg_req;
  ${pkg}::soc_reg_rsp_t [${pkg}::NumTotalRegSlaves-1:0] sys_reg_rsp;
  
  // Asynchronous RegBus Slaves
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_req_out;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_ack_in;
  ${pkg}::soc_reg_req_t [${pkg}::NumAsyncRegSlaves-1:0] async_reg_data_out;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_req_in;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_ack_out;
  ${pkg}::soc_reg_rsp_t [${pkg}::NumAsyncRegSlaves-1:0] async_reg_data_in;

  assign pcrs_req = sys_reg_req[${pkg}::RegBusSlvIdx_SysCtrl];
  assign sys_reg_rsp[${pkg}::RegBusSlvIdx_SysCtrl] = pcrs_rsp;

  // --- External RegBus Slaves (Export to Top-Level) ---
  // Exports RegBus ports to the top-level boundary to control external 
  // components physically located outside this module (e.g., analog padframes).
% if ext_sync_slaves:
  // Synchronous External Slaves
  % for comp in ext_sync_slaves:
  <% idx = f"{pkg}::RegBusSlvIdx_{camel_case(comp.name)}" %>
  assign ${comp.name}_reg_req_o = sys_reg_req[${idx}];
  assign sys_reg_rsp[${idx}] = ${comp.name}_reg_rsp_i;
  % endfor
% endif

% if num_ext_async_slaves > 0:
  // Asynchronous External Slaves
  <% ext_async_idx = 0 %>
  % for comp in ext_async_slaves:
    <% 
      idx = f"{pkg}::RegBusSlvIdx_{camel_case(comp.name)}"
      async_idx = f"({idx} - {pkg}::NumSyncRegSlaves)"
      ext_slice = f"[{ext_async_idx}]" if num_ext_async_slaves > 1 else ""
    %>
  assign ext_reg_async_slv_req_o${ext_slice}  = async_reg_req_out[${async_idx}];
  assign async_reg_ack_in[${async_idx}]  = ext_reg_async_slv_ack_i${ext_slice};
  assign ext_reg_async_slv_data_o${ext_slice} = async_reg_data_out[${async_idx}];
  assign async_reg_req_in[${async_idx}]  = ext_reg_async_slv_req_i${ext_slice};
  assign ext_reg_async_slv_ack_o${ext_slice}  = async_reg_ack_out[${async_idx}];
  assign async_reg_data_in[${async_idx}] = ext_reg_async_slv_data_i${ext_slice};
    <% ext_async_idx += 1 %>
  % endfor
% endif

% if config.project.build_mode == "macro" and config.project.macro_settings:
 % if config.project.macro_settings.slaves:
  // Macro slave interface -> Host's sync master slot
  always_comb begin
    xbar_sync_mst_req[${pkg}::NumAxiMastersSync - 1] = axi_req_i;
    xbar_sync_mst_req[${pkg}::NumAxiMastersSync - 1].aw.addr = axi_req_i.aw.addr - MACRO_BASE_ADDR;
    xbar_sync_mst_req[${pkg}::NumAxiMastersSync - 1].ar.addr = axi_req_i.ar.addr - MACRO_BASE_ADDR;
  end
  assign axi_resp_o = xbar_sync_mst_rsp[${pkg}::NumAxiMastersSync - 1];
 % endif
 % if config.project.macro_settings.masters:
  // Macro master interface <- Host's sync slave slot
  //
  // Field-wise, because the exported port is typed by the parent from the network it
  // plugs into and this crossbar's user field is wider: only the bits above the span
  // that carries semantics (MacroMstUserSpan, see the boundary block of the SoC
  // package) are dropped, and they carry nothing. A whole-struct assignment would
  // instead misalign every field, 'id' being the first member and therefore the most
  // significant bits.
  `AXI_ASSIGN_REQ_STRUCT(axi_req_o, xbar_sync_slv_req[${pkg}::NumAxiSlavesSync - 1])
  `AXI_ASSIGN_RESP_STRUCT(xbar_sync_slv_rsp[${pkg}::NumAxiSlavesSync - 1], axi_resp_i)
 % endif
% endif

  // Logical Aliases for sparse interrupt mapping.
  // If an interrupt destination is just a single bit of a larger bus, we create an alias wire.
% for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
 % if not irq_cfg.get('source'):
  % if irq_cfg.get('port') and irq_cfg.get('port') != irq_name:
  <% 
    bit_idx = irq_cfg.get('bit', 0)
    dim = get_port_dim(c.name, irq_name, is_input=False)
  %>
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name};
  assign intr_${c.name}_${irq_name} = intr_${c.name}_${irq_cfg['port']}[${bit_idx}];
  % endif
 % endif
% endfor

  // =========================================================================
  // 4. INTERRUPT ROUTING (MAPPED SOURCES)
  // =========================================================================
  // Generates continuous assignments for interrupts defined using the 
  // '{ [bit] : component.port }' dictionary syntax in the YAML.
<%
  complex_irqs = []
  for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
      source_str = str(irq_cfg.get('source', '')).strip()
      if source_str.startswith('{') and source_str.endswith('}'):
          complex_irqs.append((c, irq_name, irq_cfg, source_str))
%>
% for c, irq_name, irq_cfg, source_str in complex_irqs:
  <% 
     dim = get_port_dim(c.name, irq_name, is_input=True)
     mappings = re.findall(r'(\[[^\]]+\])\s*:\s*([^,\n]+)', source_str[1:-1])
  %>\
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name};
  always_comb begin
    intr_${c.name}_${irq_name} = '0; // Unmapped bits default to zero
  % for idx, src in mappings:
    <% 
       is_valid, missing = check_src_valid(src)
       if is_valid:
           val_processed = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', src.strip())
       else:
           val_processed = f"'0 /* Missing component: {missing} */"
    %>\
    intr_${c.name}_${irq_name}${idx} = ${val_processed};
  % endfor
  end
% endfor

  // =========================================================================
  // 5. INTER-DOMAIN SYNCHRONIZERS (CDC)
  // =========================================================================
  // Automatically generates multi-stage synchronizers whenever an interrupt 
  // connection spans across two different clock domains, guaranteeing a safe 
  // transition without metastability.
<%
  def get_clk_by_comp_name(name):
      if name == config.host.name: return config.host.clock_domain or 'host_clk'
      c = next((c for c in config.components if c.name == name), None)
      if c: return c.clock_domain or 'host_clk'
      for c in config.components:
          if c.components:
              sub = next((s for s in c.components if s.name == name), None)
              if sub: return sub.clock_domain or c.clock_domain or 'host_clk'
      return 'host_clk'

  sync_irqs = []
  for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
      if irq_cfg.get('source') and str(irq_cfg.get('source')) != 'none':
          source_str = str(irq_cfg.get('source')).strip()
          is_valid, missing = check_src_valid(source_str)
          if not is_valid:
              continue
              
          src_comp_names = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', source_str))
          needs_sync = False
          for src_comp_name in src_comp_names:
              src_clk = get_clk_by_comp_name(src_comp_name)
              if src_clk != c_clk:
                  needs_sync = True
                  break
          if irq_cfg.get('cdc') is False:
              needs_sync = False
          if needs_sync:
              sync_irqs.append((c, irq_name, irq_cfg, c_clk, c_rst, source_str))
%>
% for c, irq_name, irq_cfg, c_clk, c_rst, source_str in sync_irqs:
  // Synchronizer for ${c.name} ${irq_name} (CDC to ${c_clk})
  <%
    dim = get_port_dim(c.name, irq_name, is_input=True)
  %>\
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name}_async;
  % if source_str.startswith('{'):
  assign intr_${c.name}_${irq_name}_async = intr_${c.name}_${irq_name};
  % else:
  <% 
     processed_str = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', source_str)
     rep = ""
     src_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$', source_str.strip())
     if src_match and not get_port_dim(src_match.group(1), src_match.group(2), False):
         rep = get_rep_factor(dim)
  %>\
  assign intr_${c.name}_${irq_name}_async = ${f"'{{default: {processed_str}}}" if rep else processed_str};
  % endif
  
  ${require_file("olli_sync.sv")}
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name}_sync;
  
  % if dim:
  for (genvar i = 0; i < $bits(intr_${c.name}_${irq_name}_async); i++) begin : gen_sync_${c.name}_${irq_name}
  olli_sync #(
    .STAGES    (3),
    .ResetValue(1'b0)
  ) i_sync_${c.name}_${irq_name} (
    .clk_i    ( ${c_clk} ),
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'} ),
    .serial_i ( intr_${c.name}_${irq_name}_async[i] ),
    .serial_o ( intr_${c.name}_${irq_name}_sync[i] )
  );
  end
  % else:
  olli_sync #(
    .STAGES    (3),
    .ResetValue(1'b0)
  ) i_sync_${c.name}_${irq_name} (
    .clk_i    ( ${c_clk} ),
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'} ),
    .serial_i ( intr_${c.name}_${irq_name}_async ),
    .serial_o ( intr_${c.name}_${irq_name}_sync )
  );
  % endif

% endfor

  // =========================================================================
  // 6. COMPONENT INSTANTIATIONS (ISLES)
  // =========================================================================
  // Here we loop over the components defined in the YAML, mapping their generic
  // clock/reset domains to the physical networks defined above.
  // Parameters and ports are injected automatically based on the component's 
  // SV header analysis (Phase 2) and the Wiring Matrix.
  
% if ir.assignments:
  // IR-level continuous assignments. Today these carry the dual-role interrupt exports:
  // a port claimed both by an exported interface and by an interrupt route drives its
  // 'intr_*' wire, and the exported top-level signal is fed from that wire here.
% for lhs, rhs in ir.assignments:
  assign ${lhs} = ${rhs};
% endfor
% endif

% for inst_name, inst in ir.instances.items():
  // --- Component: ${inst.inst_name} (${inst.module_name}) ---
  ${inst.module_name} \
  % if inst.parameters:
  #(
    % for idx, (k, v) in enumerate(inst.parameters.items()):
    .${k.ljust(17)} ( ${v} )${"," if idx < len(inst.parameters) - 1 else ""}
    % endfor
  ) \
  % endif
  ${inst.inst_name} (
    % for idx, conn in enumerate(inst.connections):
    .${conn.port_name.ljust(17)} ( ${conn.expression} )${"," if idx < len(inst.connections) - 1 else ""}
    % endfor
  );

% endfor

endmodule : ${top_level_module_name}

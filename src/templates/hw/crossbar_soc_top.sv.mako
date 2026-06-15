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
  pkg    = f"{p_name}_soc_pkg"
  rpkg   = f"{p_name}_sys_regs_pkg"
  host_clk = config.host.clock_domain or "system_clk"
      
  import re
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
// BENDER: name="axi"
// BENDER: name="register_interface"

`include "axi/typedef.svh"
`include "axi/assign.svh"
`include "register_interface/typedef.svh"
`include "apb/typedef.svh"

module ${p_name}
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
#(
  // Standard System Parameters extracted from Configuration
  parameter int unsigned AxiAddrWidth = ${config.topology.global_bus.addr_width},
  parameter int unsigned AxiDataWidth = ${config.topology.global_bus.data_width},
  parameter int unsigned AxiUserWidth = ${config.topology.global_bus.user_width},
  parameter int unsigned AxiIdWidth   = ${config.topology.global_bus.mst_id_width}
) (
  // ---------------------------------------------------------
  // Global Clocks, Resets and Control
  // ---------------------------------------------------------
  input  logic [${config.clock_tree.generators - 1}:0] domain_clk_i,
  input  logic [${config.clock_tree.generators - 1}:0] clk_gen_lock_i,
  input  logic pwr_on_rst_ni,
  input  logic test_mode_i,
  input  logic [1:0] boot_mode_i\
<%
    top_ports = []
    comp_extra_conns = {}
    
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
        top_ports.append(f"output logic     {width_str} ext_reg_async_slv_req_o")
        top_ports.append(f"input  logic     {width_str} ext_reg_async_slv_ack_i")
        top_ports.append(f"output soc_reg_req_t {width_str} ext_reg_async_slv_data_o")
        top_ports.append(f"input  logic     {width_str} ext_reg_async_slv_req_i")
        top_ports.append(f"output logic     {width_str} ext_reg_async_slv_ack_o")
        top_ports.append(f"input  soc_reg_rsp_t {width_str} ext_reg_async_slv_data_i")

    for comp in ext_sync_slaves:
        top_ports.append(f"output soc_reg_req_t {comp.name}_reg_req_o")
        top_ports.append(f"input  soc_reg_rsp_t {comp.name}_reg_rsp_i")

    from core.interfaces import get_interface_ports

    for comp in [config.host] + config.components:
        comp_extra_conns.setdefault(comp.name, [])
        exported_interfaces = comp.export_interfaces if comp.export_interfaces else []
        c_info = comp_info.get(comp.name, {})
        is_host = (comp.name == config.host.name)

        for if_name in exported_interfaces:
            # The get_interface_ports function now contains all the "smart" logic
            ports_to_export = get_interface_ports(if_name, comp.name, is_host, c_info)

            for p in ports_to_export:
                internal_port = p['internal']
                top_port = p['top']
                p_dir = p['dir']

                # Get the full declaration from the parsed component info
                p_info = c_info.get("ports", {}).get(internal_port)
                if not p_info: continue

                decl = p_info["decl"]

                # Evaluate parameters in the port declaration
                known_params = {}
                known_params.update(c_info.get("supported_params", {}))
                known_params.update(c_info.get("fixed_params", {}))
                if comp.parameters:
                    for k, v in comp.parameters.items():
                        known_params[k] = "1" if v is True else "0" if v is False else str(v)

                for param_name, param_val in known_params.items():
                    decl = re.sub(rf'\b{param_name}\b', param_val, decl)

                # Reconstruct the declaration with the correct top-level name
                name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
                if name_match:
                    decl = decl[:name_match.start()] + top_port + name_match.group(2)
                    if f"{p_dir} {decl}" not in top_ports:
                        top_ports.append(f"{p_dir} {decl}")
                    conn_str = f".{internal_port:<17} ( {top_port} )"
                    if conn_str not in comp_extra_conns[comp.name]:
                        comp_extra_conns[comp.name].append(conn_str)
%>\
% if top_ports:
,

  // ---------------------------------------------------------
  // External Component Ports
  // ---------------------------------------------------------
  ${",\n  ".join(top_ports)}
% endif
);

  // SoC Registers interfaces
  ${p_name}_sys_regs_pkg::${p_name}_sys_regs__out_t sys_regs_hwif_out;
  ${p_name}_sys_regs_pkg::${p_name}_sys_regs__in_t  sys_regs_hwif_in;

  // Global reset lines (driven by clock_and_reset_tree)
  logic host_pwr_on_rst_n;
  logic [${pkg}::NumDomains-1:0] pwr_on_rsts_n;
  logic [${pkg}::NumDomains-1:0] rsts_n;

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
  
  soc_reg_req_t pcrs_req;
  soc_reg_rsp_t pcrs_rsp;
  soc_reg_req_t pcrs_req_cut;
  soc_reg_rsp_t pcrs_rsp_cut;
  
  // Pipeline cut for timing closure on the central system registers.
  // Because the PCRs fan out to the entire chip, this bus is heavily loaded.
  // Adding a register slice here drastically improves physical synthesis timing.
  reg_cut #(
    .req_t ( soc_reg_req_t ),
    .rsp_t ( soc_reg_rsp_t )
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
    .reg_req_t ( soc_reg_req_t ),
    .reg_rsp_t ( soc_reg_rsp_t ),
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

  ${p_name}_sys_regs i_sys_ctrl_regs (
    .clk            ( host_clk ),
    .arst_n         ( host_pwr_on_rst_n ), // Async active-low reset
    .s_apb_paddr    ( pcrs_apb_req.paddr ),
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
  soc_axi_slv_req_t  [`IOMSB(${pkg}::NumAxiSlavesSync):0] xbar_sync_slv_req;
  soc_axi_slv_resp_t [`IOMSB(${pkg}::NumAxiSlavesSync):0] xbar_sync_slv_rsp;

  // Masters (Components -> Host)
% for sig, slv_w, mst_w in channels:
  logic [`IOMSB(${pkg}::NumAxiMasters):0][${mst_w}-1:0] xbar_mst_${sig};
% endfor

  // Dedicated LLC Wires (Host <-> LLC Peripheral)
% for sig, slv_w, mst_w in channels:
<%
  llc_w = "Llc" + sig.split('_')[0].capitalize() + "Width" if sig.endswith('_data') else mst_w
%>
  logic [${pkg}::${llc_w}-1:0] async_axi_llc_${sig};
% endfor

  soc_reg_req_t [${pkg}::NumTotalRegSlaves-1:0] sys_reg_req;
  soc_reg_rsp_t [${pkg}::NumTotalRegSlaves-1:0] sys_reg_rsp;
  
  // Asynchronous RegBus Slaves
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_req_out;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_ack_in;
  soc_reg_req_t [${pkg}::NumAsyncRegSlaves-1:0] async_reg_data_out;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_req_in;
  logic [${pkg}::NumAsyncRegSlaves-1:0] async_reg_ack_out;
  soc_reg_rsp_t [${pkg}::NumAsyncRegSlaves-1:0] async_reg_data_in;

  assign pcrs_req = sys_reg_req[RegBusSlvIdx_SysCtrl];
  assign sys_reg_rsp[RegBusSlvIdx_SysCtrl] = pcrs_rsp;

  // --- External RegBus Slaves (Export to Top-Level) ---
  // Exports RegBus ports to the top-level boundary to control external 
  // components physically located outside this module (e.g., analog padframes).
% if ext_sync_slaves:
  // Synchronous External Slaves
  % for comp in ext_sync_slaves:
  <% idx = f"RegBusSlvIdx_{camel_case(comp.name)}" %>
  assign ${comp.name}_reg_req_o = sys_reg_req[${idx}];
  assign sys_reg_rsp[${idx}] = ${comp.name}_reg_rsp_i;
  % endfor
% endif

% if num_ext_async_slaves > 0:
  // Asynchronous External Slaves
  <% ext_async_idx = 0 %>
  % for comp in ext_async_slaves:
    <% 
      idx = f"RegBusSlvIdx_{camel_case(comp.name)}"
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
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[DomainIdx_{fmt_rst(c_rst)}]'} ),
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
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[DomainIdx_{fmt_rst(c_rst)}]'} ),
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
  
% for comp in [config.host] + config.components:
 % if not is_external(comp):
  <% 
    c_clk = comp.clock_domain or "host_clk"
    c_rst = comp.reset_domain or c_clk.replace('_clk', '_rst')
  %>
  // --- Component: ${comp.name} (${comp.type}) ---
<%
  param_dict = {}
  c_info = comp_info.get(comp.name, {})
  
  # 1. Standard AXI/System parameters
  supported = c_info.get("supported_params", [])
  for p in supported:
      if p in ['AxiAddrWidth', 'AxiDataWidth', 'AxiUserWidth', 'LogDepth']:
          param_dict[p] = p
      elif p == 'AxiMaxReadTxns': param_dict[p] = f"{pkg}::LlcMaxReadTxns" if 'l2' in comp.name else f"{pkg}::RegMaxReadTxns"
      elif p == 'AxiMaxWriteTxns': param_dict[p] = f"{pkg}::LlcMaxWriteTxns" if 'l2' in comp.name else f"{pkg}::RegMaxWriteTxns"
      elif p == 'AxiUserAmoMsb': param_dict[p] = f"{pkg}::AxiUserAmoMsb"
      elif p == 'AxiUserAmoLsb': param_dict[p] = f"{pkg}::AxiUserAmoLsb"
      elif p == 'AxiUserEccErrBit': param_dict[p] = f"{pkg}::AxiUserEccErrBit"
      elif p == 'AxiAmoNumCuts': param_dict[p] = f"{pkg}::LlcAmoNumCuts" if 'l2' in comp.name else f"{pkg}::RegAmoNumCuts"
      elif p == 'AxiInIdWidth':
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcIdWidth'
          else: param_dict[p] = 'AxiSlvIdWidth'
      elif p == 'AxiOutIdWidth': param_dict[p] = 'AxiIdWidth'
      elif p == 'AxiIdWidth':
          # If it only has an axi_slave (or llc_port) and no axi_master, it's AxiSlvIdWidth
          interfaces = comp.interfaces or {}
          has_slave = 'axi_slave' in interfaces or 'llc_port' in interfaces
          has_master = 'axi_master' in interfaces
          if has_slave and not has_master: 
              param_dict[p] = 'AxiSlvIdWidth'
          else: 
              param_dict[p] = 'AxiIdWidth'
              
      # --- Type Mappings ---
      elif p in ['axi_req_t', 'axi_in_req_t', 'sync_axi_in_req_t', 'axi_slave_req_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_req_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_req_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_req_t"
      elif p in ['axi_resp_t', 'axi_in_resp_t', 'sync_axi_in_rsp_t', 'axi_slave_resp_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_resp_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_resp_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_resp_t"
      elif p in ['axi_aw_chan_t', 'axi_in_aw_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_aw_chan_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_aw_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_aw_chan_t"
      elif p in ['axi_w_chan_t', 'axi_in_w_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_w_chan_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_w_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_w_chan_t"
      elif p in ['axi_b_chan_t', 'axi_in_b_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_b_chan_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_b_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_b_chan_t"
      elif p in ['axi_ar_chan_t', 'axi_in_ar_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_ar_chan_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_ar_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_ar_chan_t"
      elif p in ['axi_r_chan_t', 'axi_in_r_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_r_chan_t"
          elif 'llc_port' in (comp.interfaces or {}):
              param_dict[p] = f"{pkg}::soc_axi_llc_r_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_slv_r_chan_t"

      elif p in ['axi_out_req_t', 'sync_axi_out_req_t', 'axi_master_req_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_req_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_req_t"
      elif p in ['axi_out_resp_t', 'sync_axi_out_rsp_t', 'axi_master_resp_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_resp_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_resp_t"
      elif p in ['axi_out_aw_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_aw_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_aw_chan_t"
      elif p in ['axi_out_w_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_w_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_w_chan_t"
      elif p in ['axi_out_b_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_b_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_b_chan_t"
      elif p in ['axi_out_ar_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_ar_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_ar_chan_t"
      elif p in ['axi_out_r_chan_t']: 
          if comp.name == config.host.name:
              param_dict[p] = f"{pkg}::soc_axi_slv_r_chan_t"
          else:
              param_dict[p] = f"{pkg}::soc_axi_r_chan_t"

      elif p in ['reg_req_t', 'sync_reg_in_req_t', 'sync_reg_out_req_t', 'async_reg_out_req_t']: 
          param_dict[p] = f"{pkg}::soc_reg_req_t"
      elif p in ['reg_rsp_t', 'sync_reg_in_rsp_t', 'sync_reg_out_rsp_t', 'async_reg_out_rsp_t']: 
          param_dict[p] = f"{pkg}::soc_reg_rsp_t"

      # --- CDC Width Mappings ---
      elif p.startswith('AsyncAxiLlc'):
          if p == 'AsyncAxiLlcAwWidth': 
              param_dict[p] = f'{pkg}::LlcAwWidth'
          elif p == 'AsyncAxiLlcWWidth': 
              param_dict[p] = f'{pkg}::LlcWWidth'
          elif p == 'AsyncAxiLlcBWidth': 
              param_dict[p] = f'{pkg}::LlcBWidth'
          elif p == 'AsyncAxiLlcArWidth': 
              param_dict[p] = f'{pkg}::LlcArWidth'
          elif p == 'AsyncAxiLlcRWidth': 
              param_dict[p] = f'{pkg}::LlcRWidth'
      elif p in ['AsyncAxiInAwWidth', 'AxiSlvAwWidth']:
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcAwWidth'
          else: param_dict[p] = 'XbarMstAwWidth' if comp.name == config.host.name else 'XbarSlvAwWidth'
      elif p in ['AsyncAxiInWWidth', 'AxiSlvWWidth']:
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcWWidth'
          else: param_dict[p] = 'XbarMstWWidth' if comp.name == config.host.name else 'XbarSlvWWidth'
      elif p in ['AsyncAxiInBWidth', 'AxiSlvBWidth']:
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcBWidth'
          else: param_dict[p] = 'XbarMstBWidth' if comp.name == config.host.name else 'XbarSlvBWidth'
      elif p in ['AsyncAxiInArWidth', 'AxiSlvArWidth']:
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcArWidth'
          else: param_dict[p] = 'XbarMstArWidth' if comp.name == config.host.name else 'XbarSlvArWidth'
      elif p in ['AsyncAxiInRWidth', 'AxiSlvRWidth']:
          if 'llc_port' in (comp.interfaces or {}): param_dict[p] = f'{pkg}::LlcRWidth'
          else: param_dict[p] = 'XbarMstRWidth' if comp.name == config.host.name else 'XbarSlvRWidth'
          
      elif p in ['AsyncAxiOutAwWidth', 'AxiMstAwWidth']:
          param_dict[p] = 'XbarSlvAwWidth' if comp.name == config.host.name else 'XbarMstAwWidth'
      elif p in ['AsyncAxiOutWWidth', 'AxiMstWWidth']:
          param_dict[p] = 'XbarSlvWWidth' if comp.name == config.host.name else 'XbarMstWWidth'
      elif p in ['AsyncAxiOutBWidth', 'AxiMstBWidth']:
          param_dict[p] = 'XbarSlvBWidth' if comp.name == config.host.name else 'XbarMstBWidth'
      elif p in ['AsyncAxiOutArWidth', 'AxiMstArWidth']:
          param_dict[p] = 'XbarSlvArWidth' if comp.name == config.host.name else 'XbarMstArWidth'
      elif p in ['AsyncAxiOutRWidth', 'AxiMstRWidth']:
          param_dict[p] = 'XbarSlvRWidth' if comp.name == config.host.name else 'XbarMstRWidth'
          
  # 2. Custom parameters from YAML (override standard ones if specified)
  if comp.parameters:
      for p_k, p_v in comp.parameters.items():
          if isinstance(p_v, bool):
              param_dict[p_k] = "1'b1" if p_v else "1'b0"
          else:
              param_dict[p_k] = p_v
      
  param_list = [f".{k} ( {v} )" for k, v in param_dict.items()]
  
  # 3. Dynamic Port List Generation
  port_list = []
  port_list.append(f".clk_i         ( {c_clk} )")
  
  rst_wire = 'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'rsts_n[DomainIdx_{fmt_rst(c_rst)}]'
  port_list.append(f".rst_ni        ( {rst_wire} )")
  
  if c_info.get('has_pwr_on_rst'):
      por_wire = 'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[DomainIdx_{fmt_rst(c_rst)}]'
      port_list.append(f".pwr_on_rst_ni ( {por_wire} )")
      
  if c_info.get('has_ref_clk'): port_list.append(".ref_clk_i     ( rt_clk )")
  elif c_info.get('has_rt_clk'): port_list.append(".rt_clk_i      ( rt_clk )")
      
  if c_info.get('has_sys_clk'): port_list.append(".sys_clk_i     ( host_clk )")
  if c_info.get('has_sys_rst'): port_list.append(".sys_rst_ni    ( host_pwr_on_rst_n )")
      
  if c_info.get('has_rtc'): port_list.append(".rtc_i         ( rt_clk )")
  if c_info.get('has_test_mode'): port_list.append(".test_mode_i   ( test_mode_i )")
      
  if c_info.get('has_boot_mode'): port_list.append(".boot_mode_i   ( boot_mode_i )")
  elif c_info.get('has_bootmode'): port_list.append(".bootmode_i    ( boot_mode_i )")
      
  # Connect dedicated clock divider if present
  if comp.dedicated_clock_div:
      div_clk = comp.dedicated_clock_div['name']
      div_port = comp.dedicated_clock_div.get('port', f"{div_clk}_i")
      port_list.append(f".{div_port:<17} ( {div_clk} )")
      
  # --- SYSTEM CONTROLLER (PeakRDL) WIRING ---
  if comp.system_config:
      c_name = comp.name
      reg_out = "sys_regs_hwif_out"
      reg_in = "sys_regs_hwif_in"
      if comp.system_config.get('isolate'):
          port_list.append(f".axi_isolate_i   ( {reg_out}.isolate_ctrl.{c_name}_isolate.value )")
          port_list.append(f".axi_isolated_o  ( {reg_in}.isolate_status.{c_name}_isolated.next )")
      if comp.system_config.get('fetch_enable'):
          port_list.append(f".fetch_en_i      ( {reg_out}.fetch_enable.{c_name}_fetch_enable.value )")
      if comp.system_config.get('boot_enable'):
          port_list.append(f".en_sa_boot_i    ( {reg_out}.boot_enable.{c_name}_boot_enable.value )")
      if comp.system_config.get('debug_req'):
          if get_port_dim(c_name, 'debug_req_i', True):
              port_list.append(f".debug_req_i     ( '{{default: {reg_out}.debug_req.{c_name}_debug_req.value}} )")
          else:
              port_list.append(f".debug_req_i     ( {reg_out}.debug_req.{c_name}_debug_req.value )")
      if 'boot_addr' in comp.system_config and c_info.get("has_boot_addr"):
          port_list.append(f".boot_addr_i     ( {reg_out}.{c_name}_boot_addr.{c_name}_boot_addr.value )")
      if comp.system_config.get('has_busy_status'):
          port_list.append(f".busy_o          ( {reg_in}.busy_status.{c_name}_busy.next )")
      if comp.system_config.get('has_eoc_status') and 'eoc' not in (comp.interrupts or {}) and 'eoc_o' not in (comp.interrupts or {}):
          port_list.append(f".eoc_o           ( {reg_in}.eoc_status.{c_name}_eoc.next )")

  # Append the wiring matrix connections
  exported_ports = [c.split('(')[0].strip().strip('.') for c in comp_extra_conns.get(comp.name, [])]
  for wc in wiring_matrix.get(comp.name, []):
      port_name = wc.split('(')[0].strip().strip('.')
      if port_name not in exported_ports:
          port_list.append(wc)
          
  # Inject exported interfaces
  if comp.name in comp_extra_conns:
      port_list.extend(comp_extra_conns[comp.name])
      
  # Auto-tie-off remaining unconnected ports to prevent TFMPC warnings
  connected_ports = []
  for p in port_list:
      m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(', p)
      if m: connected_ports.append(m.group(1))
      
  for port_name, p_info in c_info.get("ports", {}).items():
      if port_name not in connected_ports:
          val = "'0" if p_info["dir"] == "input" else ""
          port_list.append(f".{port_name:<17} ( {val} )")
%>
  ${p_name}_${comp.type} ${"#(" if param_list else ""}
% for i, p_str in enumerate(param_list):
    ${p_str}${"," if i < len(param_list)-1 else ""}
% endfor
  ${")" if param_list else ""} i_${comp.name} (
% for i, port_conn in enumerate(port_list):
    ${port_conn}${"," if i < len(port_list) - 1 else ""}
% endfor
  );

 % endif
% endfor

endmodule : ${p_name}
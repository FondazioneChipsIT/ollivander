<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE UNIVERSAL WRAPPER (ISLE / TILE)
  # ============================================================================
  # This template takes a generic 'Isle' (a standard, topology-agnostic SoC 
  # component) and wraps it with the appropriate NoC interconnect logic 
  # (FlooNoC Router + Chimney) to generate a fully compliant 'Tile'. 
  # This abstraction completely isolates the IP from the physical 2D Mesh 
  # routing complexities.

  import re
  from core.sv_parser import get_isle_info
  from core.interfaces import get_interface_ports

  c_name = comp.name
  c_type = comp.type
  # Prefix of every generated module: follows the top-level name so that two macros
  # exported from the same project do not emit identically named modules.
  p_name = config.project.module_prefix
  # FlooNoC package name. Derived from the top-level module so that macros exported
  # from the same project do not collide when compiled into one library.
  noc_pkg = config.project.noc_pkg_name
  # Global SoC package name. Derived from the project so that a "macro" build gets
  # the same suffix as its top-level module and never collides with a "standalone"
  # build of the same project.
  soc_pkg = config.project.soc_pkg_name
  is_host = (comp.name == config.host.name)
  
  # ============================================================================
  # 1. NOC NETWORK RESOLUTION
  # ============================================================================
  # Inspect the configuration to extract the specific NoC networks (e.g., narrow, 
  # wide) this tile connects to, and determine its role (AXI Master, Slave, or both).
  # This dictates the instantiation of the Chimney channels and Routers.
  noc_nets_raw = comp.interfaces.get('noc_networks', {}) if comp.interfaces else {}
  mst_nets = noc_nets_raw.get('master', []) if isinstance(noc_nets_raw, dict) else noc_nets_raw
  slv_nets = noc_nets_raw.get('slave', []) if isinstance(noc_nets_raw, dict) else noc_nets_raw
  noc_mode = noc_nets_raw.get('noc_mode', 'joined') if isinstance(noc_nets_raw, dict) else 'joined'
  
  has_master = comp.interfaces.get('axi_master', False) if comp.interfaces else False
  has_slave = ('axi_slave' in comp.interfaces or 'llc_port' in comp.interfaces) if comp.interfaces else False
  
  has_master_narrow = has_master and ("narrow" in mst_nets)
  has_master_wide   = has_master and ("wide" in mst_nets or not has_master_narrow)
  has_slave_narrow  = has_slave and ("narrow" in slv_nets)
  has_slave_wide    = has_slave and ("wide" in slv_nets or not has_slave_narrow)
  has_narrow = has_master_narrow or has_slave_narrow
  has_wide   = has_master_wide or has_slave_wide
  
  has_clk_ctrl = False
  if not is_host and config.system_controller and config.system_controller.auto_control_groups:
      for g in config.system_controller.auto_control_groups:
          if g.target_component_type in [c_type, context.get('original_type', '')]:
              has_clk_ctrl = True
              break

  use_join = has_slave and has_slave_narrow and has_slave_wide and noc_mode.startswith("joined")
  
  # Determine RouteCfg based on multicast feature, using explicit scopes
  use_mcast = comp.features and comp.features.get('multicast_target')
  route_cfg = "RouteCfg" if use_mcast else "RouteCfgNoMcast"
  
  # Determine the underlying IP to instantiate (restoring the original _subtile or _isle suffix)
  _orig_type = context.get('original_type', c_type.replace('_tile', '_isle'))
  isle_name = f"{p_name}_{_orig_type}"

  # ============================================================================
  # 2. ISLE AUTO-INSPECTION (SSoT)
  # ============================================================================
  # Auto-inspect the underlying Isle using the Verible AST parser to extract its 
  # native parameters and physical I/O ports. This ensures the wrapper perfectly 
  # matches the underlying hardware (Single Source of Truth).
  isle_info = get_isle_info(isle_name, search_paths)
  terminated_ports = []
  error_slave_ports = []
  isle_params = {}
  axi_req_o_dim = ""
  axi_req_i_dim = ""
  terminate_prefixes = comp.features.get('terminate_ports', []) if comp.features else []
  error_slave_prefixes = comp.features.get('error_slaves', []) if comp.features else []
  isle_ports = []
  known_ports = set(isle_info.get("ports", {}).keys()) if isle_info else set()
  
  if isle_info:
      isle_params.update(isle_info.get('supported_params', {}))
      
      # Get the set of ports that should be exported based on the "stupid" logic
      exported_interfaces = comp.export_interfaces if comp.export_interfaces else []
      ports_to_export_list = []
      for if_name in exported_interfaces:
          ports_to_export_list.extend(get_interface_ports(if_name, c_name, is_host, isle_info))
      exported_internal_ports = {p['internal'] for p in ports_to_export_list}

      for p_port_name, p_data in isle_info.get("ports", {}).items():
          p_dir = p_data["dir"]
          p_type_dim = p_data["type_dim"]
          p_unpacked_dim = p_data["unpacked"]
              
          if p_port_name == 'axi_req_o':
              axi_req_o_dim = p_type_dim
          elif p_port_name == 'axi_req_i':
              axi_req_i_dim = p_type_dim
          
          # Check if the port is part of an exported interface
          if p_port_name in exported_internal_ports:
              isle_ports.append({'dir': p_dir, 'type': p_type_dim, 'name': p_port_name, 'unpacked': p_unpacked_dim})
              continue # Port handled, move to next one

          # Passthrough ports for architecture wiring
          passthrough_ports = {
              'sys_clk_i', 'sys_rst_ni', 'pwr_on_rst_ni', 'rt_clk_i', 'boot_mode_i', 'bootmode_i',
              'hart_base_id_i', 'cluster_base_addr_i', 'cluster_base_offset_i',
              'axi_isolate_i', 'axi_isolated_o', 'fetch_en_i', 'en_sa_boot_i', 'boot_addr_i',
              'busy_o', 'eoc_o', 'debug_req_i'
          }
          
          if comp.interrupts:
              for irq_name, irq_cfg in comp.interrupts.items():
                  passthrough_ports.add(irq_name)
                  if isinstance(irq_cfg, dict) and 'port' in irq_cfg:
                      passthrough_ports.add(irq_cfg['port'])

          if p_port_name in passthrough_ports:
              isle_ports.append({'dir': p_dir, 'type': p_type_dim, 'name': p_port_name, 'unpacked': p_unpacked_dim})
              continue

          # The port is NOT exported. Now check for other special handling.
          if any(p_port_name.startswith(pfx) for pfx in error_slave_prefixes):
              error_slave_ports.append({'dir': p_dir, 'type': p_type_dim, 'name': p_port_name, 'unpacked': p_unpacked_dim})
              continue

          if any(p_port_name.startswith(pfx) for pfx in terminate_prefixes):
              terminated_ports.append({'dir': p_dir, 'name': p_port_name})
              continue
  
  valid_user_params = {k: v for k, v in (comp.parameters or {}).items() if k in isle_params}
  all_params = {**isle_params, **valid_user_params}
          
  # ============================================================================
  # 3. AXI TYPE OVERRIDES
  # ============================================================================
  # Dynamically overrides the Isle's generic AXI types (e.g., axi_req_t) with the 
  # specific, auto-generated NoC AXI types (e.g., axi_narrow_in_req_t). 
  # These are separated so they don't appear in the Tile's public parameter list,
  # as they are internal structs generated by FlooGen inside the module body.
  isle_type_overrides = {}
  if has_master and noc_mode != "dual":
      cfg_mst_pfx = "AxiCfgN" if has_master_narrow else "AxiCfgW"
      req_mst_type = 'axi_narrow_in_req_t' if has_master_narrow else 'axi_wide_in_req_t'
      rsp_mst_type = 'axi_narrow_in_rsp_t' if has_master_narrow else 'axi_wide_in_rsp_t'
      if not has_slave:
          if 'axi_req_t' in all_params: isle_type_overrides['axi_req_t'] = req_mst_type
          if 'axi_resp_t' in all_params: isle_type_overrides['axi_resp_t'] = rsp_mst_type
          if 'axi_rsp_t' in all_params: isle_type_overrides['axi_rsp_t'] = rsp_mst_type
      if 'sync_axi_out_req_t' in all_params: isle_type_overrides['sync_axi_out_req_t'] = req_mst_type
      if 'sync_axi_out_rsp_t' in all_params: isle_type_overrides['sync_axi_out_rsp_t'] = rsp_mst_type
      
      # Auto-inject physical NoC parameters for Master ports
      if 'AxiOutIdWidth' in all_params: all_params['AxiOutIdWidth'] = f"{cfg_mst_pfx}.InIdWidth"
      if not has_slave:
          if 'AxiDataWidth' in all_params: all_params['AxiDataWidth'] = f"{cfg_mst_pfx}.DataWidth"
          if 'AxiAddrWidth' in all_params: all_params['AxiAddrWidth'] = f"{cfg_mst_pfx}.AddrWidth"
          if 'AxiIdWidth' in all_params: all_params['AxiIdWidth'] = f"{cfg_mst_pfx}.InIdWidth"
          if 'AxiUserWidth' in all_params: all_params['AxiUserWidth'] = f"{cfg_mst_pfx}.UserWidth"
      
  if has_slave and noc_mode != "dual":
      cfg_slv_pfx = "AxiCfgJoin" if use_join else ("AxiCfgW" if has_slave_wide else "AxiCfgN")
      req_slv_type = "axi_nw_join_req_t" if use_join else ("axi_wide_out_req_t" if has_slave_wide else "axi_narrow_out_req_t")
      rsp_slv_type = "axi_nw_join_rsp_t" if use_join else ("axi_wide_out_rsp_t" if has_slave_wide else "axi_narrow_out_rsp_t")
      if not has_master or use_join:
          if 'axi_req_t' in all_params: isle_type_overrides['axi_req_t'] = req_slv_type
          if 'axi_resp_t' in all_params: isle_type_overrides['axi_resp_t'] = rsp_slv_type
          if 'axi_rsp_t' in all_params: isle_type_overrides['axi_rsp_t'] = rsp_slv_type
      if 'sync_axi_in_req_t' in all_params: isle_type_overrides['sync_axi_in_req_t'] = req_slv_type
      if 'sync_axi_in_rsp_t' in all_params: isle_type_overrides['sync_axi_in_rsp_t'] = rsp_slv_type
      
      # Auto-inject physical NoC parameters for Slave ports
      if 'AxiInIdWidth' in all_params: all_params['AxiInIdWidth'] = f"{cfg_slv_pfx}.OutIdWidth"
      if 'AxiIdWidth' in all_params: all_params['AxiIdWidth'] = f"{cfg_slv_pfx}.OutIdWidth"
      if 'AxiUserWidth' in all_params: all_params['AxiUserWidth'] = f"{cfg_slv_pfx}.UserWidth"
      if not has_master or use_join:
          if 'AxiDataWidth' in all_params: all_params['AxiDataWidth'] = f"{cfg_slv_pfx}.DataWidth"
          if 'AxiAddrWidth' in all_params: all_params['AxiAddrWidth'] = f"{cfg_slv_pfx}.AddrWidth"
          
  for k in isle_type_overrides.keys():
      if k.endswith('_t') and k in all_params: del all_params[k]

  def fmt_param_type(p_val):
      if isinstance(p_val, bool) or str(p_val) in ["True", "False"]: return "bit"
      if str(p_val).isdigit(): return "int unsigned"
      if str(p_val) == "logic" or str(p_val).endswith("_t"): return "type"
      if str(p_val).startswith('"') or str(p_val).startswith("'"): return "string"
      return "int unsigned"
      
  def fmt_param_val(p_val):
      if isinstance(p_val, bool): return "1'b1" if p_val else "1'b0"
      if str(p_val) == "True": return "1'b1"
      if str(p_val) == "False": return "1'b0"
      return str(p_val)
      
  has_offload = 'offload_wide_req_i' in known_ports
          
%><%namespace file="/license_header.mako" import="license"/>\
${license()}\
//
// AUTOMATICALLY GENERATED BY OLLIVANDER - DO NOT EDIT DIRECTLY
//
// Universal Tile Wrapper for ${c_type}
// Topology: Network-on-Chip (FlooNoC)
//
% if context.get('peakrdl_pragma'):
${context.get('peakrdl_pragma')}
//
% endif
// BENDER: name="axi"
// BENDER: name="floo_noc"
% if is_host and config.system_controller:
${require_bender("register_interface")}
% endif
% if has_clk_ctrl:
${require_bender("common_cells")}
% endif

`include "axi/typedef.svh"
`include "floo_noc/typedef.svh"
`include "axi/assign.svh"
`include "apb/typedef.svh"

module ${p_name}_${c_type}
  import floo_pkg::*;
  import ${noc_pkg}::*; // Autogenerated NoC package (Widths, IDs)
  import ${soc_pkg}::*;      // Global SoC parameters and routes
  import ${top_level_module_name}_sys_regs_pkg::*;
<%
  # Auto-inject imports from the underlying IP header
  isle_imports = set(imp for imp in isle_info.get("imports", []) if imp not in ["floo_pkg", f"{noc_pkg}"])
%>\
% for imp in sorted(isle_imports):
  import ${imp}::*;
% endfor

<%
  fixed_params_to_expose = []
  if isle_info and "fixed_params" in isle_info:
      for param_name, p_val in isle_info["fixed_params"].items():
          if param_name.startswith("Preload") or param_name.startswith("ForceBoot") or param_name in ["HasEcc", "EccType", "HasForceBoot"]:
              if param_name in ["PreloadTemplate", "ForceBootPath"]:
                  clean_val = p_val.strip("\"'")
                  p_val = f'"i_isle.{clean_val}"'
              fixed_params_to_expose.append((param_name, p_val))
%>
% if all_params or fixed_params_to_expose:
#(
 % for i, (param_name, p_val) in enumerate(all_params.items()):
  parameter ${fmt_param_type(p_val)} ${param_name} = ${fmt_param_val(p_val)}${"," if (i < len(all_params)-1 or fixed_params_to_expose) else ""}
 % endfor
 % for i, (param_name, p_val) in enumerate(fixed_params_to_expose):
  localparam ${fmt_param_type(p_val)} ${param_name} = ${fmt_param_val(p_val)}${"," if i < len(fixed_params_to_expose)-1 else ""}
 % endfor
)
% endif
(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic test_mode_i,

  // Chimney Logical Coordinates (X, Y mapped to a flat ID)
  input wire ${noc_pkg}::id_t  id_i,

  // =======================================================================
  // ROUTER PORTS (Always 4 Cardinal Directions)
  // =======================================================================
  // These ports connect this tile to its 4 adjacent neighbors in the 2D mesh.
  output ${noc_pkg}::floo_req_t  [West:North] floo_req_o,
  input wire ${noc_pkg}::floo_rsp_t  [West:North] floo_rsp_i,
  output ${noc_pkg}::floo_wide_t [West:North] floo_wide_o,
  input wire ${noc_pkg}::floo_req_t  [West:North] floo_req_i,
  output ${noc_pkg}::floo_rsp_t  [West:North] floo_rsp_o,
  input wire ${noc_pkg}::floo_wide_t [West:North] floo_wide_i

  // =======================================================================
  // COMPONENT-SPECIFIC I/Os and INTERRUPTS (Extracted from ${isle_name})
  // =======================================================================

% if isle_ports:
  ,
 % for i, p in enumerate(isle_ports):
  ${p['dir']} ${p['type']} ${p['name']}${p.get('unpacked', '')}${"," if i < len(isle_ports)-1 else ""}
 % endfor
% endif

% if has_clk_ctrl:
  ,
  // =======================================================================
  // CLOCK GATING & RESET CONTROL
  // =======================================================================
  // Dynamic clock gating and reset bypass logic for this specific Tile.
  // This is managed centrally by the System Controller via the Auto Control 
  // Groups mechanism, allowing fine-grained power management of the NoC array.
  input  logic tile_clk_en_i,
  input  logic tile_rst_ni,
  input  logic clk_rst_bypass_i
% endif

% if is_host and config.system_controller:
<%
  reg_rsp_type = isle_info.get("ports", {}).get("reg_rsp_i", {}).get("type_dim", "soc_reg_rsp_t").strip()
  reg_req_type = isle_info.get("ports", {}).get("reg_req_o", {}).get("type_dim", "soc_reg_req_t").strip()
  if "::" not in reg_rsp_type: reg_rsp_type = f"{soc_pkg}::{reg_rsp_type}"
  if "::" not in reg_req_type: reg_req_type = f"{soc_pkg}::{reg_req_type}"
%>
  ,
  // System Controller Hardware Interfaces (Exported to Top-Level)
  output ${top_level_module_name}_sys_regs_pkg::${top_level_module_name}_sys_regs__out_t sys_regs_hwif_out_o,
  input  ${top_level_module_name}_sys_regs_pkg::${top_level_module_name}_sys_regs__in_t  sys_regs_hwif_in_i,
  output ${reg_req_type} reg_req_o,
  input  ${reg_rsp_type} reg_rsp_i
% endif
);
  logic tile_clk;
  logic tile_rst_n;

% if has_clk_ctrl:
  tc_clk_gating i_tc_clk_gating (
    .clk_i,
    .en_i     ( tile_clk_en_i ),
    .test_en_i( clk_rst_bypass_i ),
    .clk_o    ( tile_clk )
  );

`ifdef TARGET_XILINX
  assign tile_rst_n = (clk_rst_bypass_i) ? rst_ni : (rst_ni && tile_rst_ni);
`else
  logic tile_rst_n_gated;
  assign tile_rst_n_gated = rst_ni && tile_rst_ni;
  tc_clk_mux2 i_tc_reset_mux (
    .clk0_i   ( tile_rst_n_gated ),
    .clk1_i   ( rst_ni ),
    .clk_sel_i( clk_rst_bypass_i ),
    .clk_o    ( tile_rst_n )
  );
`endif
% else:
  assign tile_clk   = clk_i;
  assign tile_rst_n = rst_ni;
% endif

  // =======================================================================
  // 0. NOC CLOCK DOMAIN ASSIGNMENT
  // =======================================================================
  // Determines which clock domain drives the NoC routing infrastructure 
  // (Router and Chimney). Typically, this is the synchronous global system 
  // clock, but it gracefully falls back to the local clock if isolated.
  logic noc_clk;
  logic noc_rst_n;
% if 'sys_clk_i' in known_ports:
  assign noc_clk   = sys_clk_i;
  assign noc_rst_n = sys_rst_ni;
% else:
  assign noc_clk   = clk_i;
  assign noc_rst_n = rst_ni;
% endif

  // =======================================================================
  // 1. FLOONOC ROUTER
  // =======================================================================
  // The Router is the physical 2D crossbar switch node. It forwards incoming 
  // packets to adjacent tiles via the 4 Cardinal ports (North, South, East, West),
  // and delivers local packets to the Isle via the 'Eject' port (Chimney).
  ${noc_pkg}::floo_req_t  [Eject:North] router_floo_req_out, router_floo_req_in;
  ${noc_pkg}::floo_rsp_t  [Eject:North] router_floo_rsp_out, router_floo_rsp_in;
  ${noc_pkg}::floo_wide_t [Eject:North] router_floo_wide_in, router_floo_wide_out;

% if has_offload:
  ${noc_pkg}::red_wide_req_t offload_wide_req_out;
  ${noc_pkg}::red_wide_rsp_t offload_wide_rsp_in;
% endif

  floo_nw_router #(
    .AxiCfgN       ( ${noc_pkg}::AxiCfgN ),
    .AxiCfgW       ( ${noc_pkg}::AxiCfgW ),
% if use_mcast:
    .RouteAlgo     ( ${noc_pkg}::RouteCfg.RouteAlgo ),
% else:
    .RouteAlgo     ( ${soc_pkg}::RouteCfgNoMcast.RouteAlgo ),
% endif
    .NumRoutes     ( 5 ), // 4 Cardinals + 1 Eject
    .InFifoDepth   ( 2 ),
    .OutFifoDepth  ( 2 ),
    .id_t          ( ${noc_pkg}::id_t ),
    .hdr_t         ( ${noc_pkg}::hdr_t ),
    .floo_req_t    ( ${noc_pkg}::floo_req_t ),
    .floo_rsp_t    ( ${noc_pkg}::floo_rsp_t ),
    .floo_wide_t   ( ${noc_pkg}::floo_wide_t ),
% if use_mcast:
    .red_wide_req_t( ${noc_pkg}::red_wide_req_t ),
    .red_wide_rsp_t( ${noc_pkg}::red_wide_rsp_t ),
% endif
    .WideRwDecouple( ${noc_pkg}::WideRwDecouple ),
    .VcImpl        ( ${noc_pkg}::VcImpl )
% if use_mcast:
    , .CollectiveCfg ( ${noc_pkg}::${route_cfg}.CollectiveCfg )
    // Collective traffic needs the loopback path: a multicast flit replicated onto
    // several outputs may legitimately include the port it arrived on. FlooNoC
    // defaults NoLoopback to 1'b1 and asserts !(EnCollective && NoLoopback), so the
    // value is derived here from the very configuration passed above, instead of
    // patching the default inside the fetched IP.
    , .NoLoopback    ( !floo_pkg::en_collective(${noc_pkg}::${route_cfg}.CollectiveCfg.OpCfg) )
% endif
  ) i_router (
    .clk_i          ( noc_clk ),
    .rst_ni         ( noc_rst_n ),
    .id_i,
    .test_enable_i  ( test_mode_i ),
    .id_route_map_i ( '0 ),
    .floo_req_i     ( router_floo_req_in ),
    .floo_rsp_o     ( router_floo_rsp_out ),
    .floo_req_o     ( router_floo_req_out ),
    .floo_rsp_i     ( router_floo_rsp_in )
    , .floo_wide_i  ( router_floo_wide_in )
    , .floo_wide_o  ( router_floo_wide_out )
   % if has_offload:
    , .offload_wide_req_o  ( offload_wide_req_out )
    , .offload_wide_rsp_i  ( offload_wide_rsp_in )
   % else:
    , .offload_wide_req_o  ()
    , .offload_wide_rsp_i  ('0)
   % endif
    , .offload_narrow_req_o()
    , .offload_narrow_rsp_i('0)
  );

  // Route the internal router arrays to the physical Tile pins
  assign floo_req_o                      = router_floo_req_out[West:North];
  assign router_floo_req_in[West:North]  = floo_req_i;
  assign floo_rsp_o                      = router_floo_rsp_out[West:North];
  assign router_floo_rsp_in[West:North]  = floo_rsp_i;
  assign floo_wide_o[West:North]         = router_floo_wide_out[West:North];
  assign router_floo_wide_in[West:North] = floo_wide_i;

  // =======================================================================
  // 2. FLOONOC CHIMNEY & AXI WIRING
  // =======================================================================
  // The Chimney acts as the network adapter. It translates the standard, memory-
  // mapped AXI4 protocol used by the internal IP (Isle) into the flit-based, 
  // packet-switched protocol used by the FlooNoC Router, and vice-versa.
  
  ${noc_pkg}::axi_narrow_in_req_t  narrow_in_req;
  ${noc_pkg}::axi_narrow_in_rsp_t  narrow_in_rsp;
  ${noc_pkg}::axi_narrow_out_req_t narrow_out_req;
  ${noc_pkg}::axi_narrow_out_rsp_t narrow_out_rsp;
  ${noc_pkg}::axi_wide_in_req_t    wide_in_req;
  ${noc_pkg}::axi_wide_in_rsp_t    wide_in_rsp;
  ${noc_pkg}::axi_wide_out_req_t   wide_out_req;
  ${noc_pkg}::axi_wide_out_rsp_t   wide_out_rsp;

  floo_nw_chimney #(
    .AxiCfgN             ( ${noc_pkg}::AxiCfgN ),
    .AxiCfgW             ( ${noc_pkg}::AxiCfgW ),
    .ChimneyCfgN         ( floo_pkg::set_ports(floo_pkg::ChimneyDefaultCfg, ${"1'b1" if has_slave_narrow else "1'b0"}, ${"1'b1" if has_master_narrow else "1'b0"}) ),
    .ChimneyCfgW         ( floo_pkg::set_ports(floo_pkg::ChimneyDefaultCfg, ${"1'b1" if has_slave_wide else "1'b0"}, ${"1'b1" if has_master_wide else "1'b0"}) ),
% if use_mcast:
    .RouteCfg            ( ${noc_pkg}::RouteCfg ),
% else:
    .RouteCfg            ( ${soc_pkg}::RouteCfgNoMcast ),
% endif
    .AtopSupport         ( 1'b1 ),
    .WideRwDecouple      ( ${noc_pkg}::WideRwDecouple ),
    .VcImpl              ( ${noc_pkg}::VcImpl ),
    .MaxAtomicTxns       ( ${"3" if has_master else "1"} ),
% if use_mcast:
    .Sam                 ( ${noc_pkg}::CollectiveSam ),
    .sam_rule_t          ( ${noc_pkg}::collective_sam_rule_t ),
    .sam_idx_t           ( ${noc_pkg}::collective_idx_t ),
    .mask_sel_t          ( ${noc_pkg}::collective_mask_sel_t ),
    .user_narrow_struct_t( ${noc_pkg}::collective_axi_narrow_in_user_t ),
    .user_wide_struct_t  ( ${noc_pkg}::collective_axi_wide_in_user_t ),
% else:
    .Sam                 ( ${noc_pkg}::Sam ),
    .sam_rule_t          ( ${noc_pkg}::sam_rule_t ),
% endif
    .id_t                ( ${noc_pkg}::id_t ),
    .rob_idx_t           ( ${noc_pkg}::rob_idx_t ),
    .hdr_t               ( ${noc_pkg}::hdr_t ),
    .axi_narrow_in_req_t ( ${noc_pkg}::axi_narrow_in_req_t ),
    .axi_narrow_in_rsp_t ( ${noc_pkg}::axi_narrow_in_rsp_t ),
    .axi_narrow_out_req_t( ${noc_pkg}::axi_narrow_out_req_t ),
    .axi_narrow_out_rsp_t( ${noc_pkg}::axi_narrow_out_rsp_t ),
    .axi_wide_in_req_t   ( ${noc_pkg}::axi_wide_in_req_t ),
    .axi_wide_in_rsp_t   ( ${noc_pkg}::axi_wide_in_rsp_t ),
    .axi_wide_out_req_t  ( ${noc_pkg}::axi_wide_out_req_t ),
    .axi_wide_out_rsp_t  ( ${noc_pkg}::axi_wide_out_rsp_t ),
    .floo_req_t          ( ${noc_pkg}::floo_req_t ),
    .floo_rsp_t          ( ${noc_pkg}::floo_rsp_t ),
    .floo_wide_t         ( ${noc_pkg}::floo_wide_t )
  ) i_chimney (
    .clk_i               ( noc_clk ),
    .rst_ni              ( noc_rst_n ),
    .id_i,
    .test_enable_i       ( test_mode_i ),
    .route_table_i       ( '0 ),
    .sram_cfg_i          ( '0 ),
    .axi_narrow_in_req_i ( narrow_in_req ),
    .axi_narrow_in_rsp_o ( narrow_in_rsp ),
    .axi_narrow_out_req_o( narrow_out_req ),
    .axi_narrow_out_rsp_i( narrow_out_rsp ),
    .axi_wide_in_req_i   ( wide_in_req ),
    .axi_wide_in_rsp_o   ( wide_in_rsp ),
    .axi_wide_out_req_o  ( wide_out_req ),
    .axi_wide_out_rsp_i  ( wide_out_rsp ),
    // Connects to the Router's Eject port
    .floo_req_o  ( router_floo_req_in[Eject] ),
    .floo_rsp_o  ( router_floo_rsp_in[Eject] ),
    .floo_wide_o ( router_floo_wide_in[Eject] ),
    .floo_req_i  ( router_floo_req_out[Eject] ),
    .floo_rsp_i  ( router_floo_rsp_out[Eject] ),
    .floo_wide_i ( router_floo_wide_out[Eject] )
  );

  // Tie off unused chimney master inputs
% if not has_master_narrow:
  assign narrow_in_req = '0;
% endif
% if not has_master_wide:
  assign wide_in_req = '0;
% endif

% if error_slave_ports:
  // =======================================================================
  // AXI ERROR SLAVES FOR TERMINATED PORTS
  // =======================================================================
  // Instantiates dummy AXI slaves that respond with DECERR (Decode Error) for 
  // ports explicitly marked as 'terminated' in the YAML configuration. 
  // This prevents the interconnect from hanging on unconnected interfaces.
 % for p in error_slave_ports:
  <% p_type_actual = isle_type_overrides.get(p['type'], p['type']) %>
  ${p_type_actual} ${p['name']}${p.get('unpacked', '')};
  % if p['name'].endswith('_isolate_i'):
  assign ${p['name']} = 1'b0;
  % endif
 % endfor

  typedef logic [AxiAddrWidth-1:0]   err_slv_addr_t;
  typedef logic [AxiOutIdWidth-1:0]  err_slv_id_t;
  typedef logic [AxiDataWidth-1:0]   err_slv_data_t;
  typedef logic [AxiDataWidth/8-1:0] err_slv_strb_t;
  typedef logic [AxiUserWidth-1:0]   err_slv_user_t;

  `AXI_TYPEDEF_ALL(err_slv, err_slv_addr_t, err_slv_id_t, err_slv_data_t, err_slv_strb_t, err_slv_user_t)

 % for pfx in error_slave_prefixes:
  err_slv_req_t  ${pfx}_err_req;
  err_slv_resp_t ${pfx}_err_rsp;

  % if pfx.startswith("async_"):
  // The asynchronous ports of `axi_cdc_dst` are declared as arrays of `2**LogDepth` channel
  // structs (one entry per gray-coded FIFO slot), not as a single flat channel. The glue
  // signals must therefore carry the same array dimension, otherwise only 1/2**LogDepth of
  // each async bus is connected and the remaining FIFO entries are left undriven.
  logic [2**LogDepth-1:0][$bits(err_slv_aw_chan_t)-1:0] ${pfx}_err_aw_data_i;
  logic [2**LogDepth-1:0][$bits(err_slv_w_chan_t)-1:0]  ${pfx}_err_w_data_i;
  logic [2**LogDepth-1:0][$bits(err_slv_ar_chan_t)-1:0] ${pfx}_err_ar_data_i;
  logic [2**LogDepth-1:0][$bits(err_slv_b_chan_t)-1:0]  ${pfx}_err_b_data_o;
  logic [2**LogDepth-1:0][$bits(err_slv_r_chan_t)-1:0]  ${pfx}_err_r_data_o;

  // Resize against the full array width so that the flat async buses exported by the isle are
  // reinterpreted (zero-extended or truncated) consistently in both directions.
  assign ${pfx}_err_aw_data_i = $bits(${pfx}_err_aw_data_i)'(${pfx}_aw_data_o);
  assign ${pfx}_err_w_data_i  = $bits(${pfx}_err_w_data_i)'(${pfx}_w_data_o);
  assign ${pfx}_err_ar_data_i = $bits(${pfx}_err_ar_data_i)'(${pfx}_ar_data_o);
  assign ${pfx}_b_data_i      = $bits(${pfx}_b_data_i)'(${pfx}_err_b_data_o);
  assign ${pfx}_r_data_i      = $bits(${pfx}_r_data_i)'(${pfx}_err_r_data_o);

  axi_cdc_dst #(
    .LogDepth   ( LogDepth ),
    .SyncStages ( CdcSyncStages ),
    .aw_chan_t  ( err_slv_aw_chan_t ),
    .w_chan_t   ( err_slv_w_chan_t ),
    .b_chan_t   ( err_slv_b_chan_t ),
    .ar_chan_t  ( err_slv_ar_chan_t ),
    .r_chan_t   ( err_slv_r_chan_t ),
    .axi_req_t  ( err_slv_req_t ),
    .axi_resp_t ( err_slv_resp_t )
  ) i_err_cdc_dst_${pfx} (
    .async_data_slave_aw_data_i ( ${pfx}_err_aw_data_i ),
    .async_data_slave_aw_wptr_i ( ${pfx}_aw_wptr_o ),
    .async_data_slave_aw_rptr_o ( ${pfx}_aw_rptr_i ),
    .async_data_slave_w_data_i  ( ${pfx}_err_w_data_i ),
    .async_data_slave_w_wptr_i  ( ${pfx}_w_wptr_o ),
    .async_data_slave_w_rptr_o  ( ${pfx}_w_rptr_i ),
    .async_data_slave_b_data_o  ( ${pfx}_err_b_data_o ),
    .async_data_slave_b_wptr_o  ( ${pfx}_b_wptr_i ),
    .async_data_slave_b_rptr_i  ( ${pfx}_b_rptr_o ),
    .async_data_slave_ar_data_i ( ${pfx}_err_ar_data_i ),
    .async_data_slave_ar_wptr_i ( ${pfx}_ar_wptr_o ),
    .async_data_slave_ar_rptr_o ( ${pfx}_ar_rptr_i ),
    .async_data_slave_r_data_o  ( ${pfx}_err_r_data_o ),
    .async_data_slave_r_wptr_o  ( ${pfx}_r_wptr_i ),
    .async_data_slave_r_rptr_i  ( ${pfx}_r_rptr_o ),
    .dst_clk_i                  ( noc_clk ),
    .dst_rst_ni                 ( noc_rst_n ),
    .dst_req_o                  ( ${pfx}_err_req ),
    .dst_resp_i                 ( ${pfx}_err_rsp )
  );
  % else:
  assign ${pfx}_err_req  = $bits(err_slv_req_t)'(${pfx}_req_o);
  assign ${pfx}_resp_i   = $bits(${pfx}_resp_i)'(${pfx}_err_rsp);
  % endif

  axi_err_slv #(
    .AxiIdWidth ( AxiOutIdWidth ),
    .axi_req_t  ( err_slv_req_t ),
    .axi_resp_t ( err_slv_resp_t ),
    .Resp       ( axi_pkg::RESP_DECERR ),
    .RespWidth  ( AxiDataWidth ),
    .RespData   ( 64'hCA11AB1EBADCAB1E ),
    .ATOPs      ( 1'b1 ),
    .MaxTrans   ( 4 )
  ) i_err_slv_${pfx} (
    .clk_i      ( noc_clk ),
    .rst_ni     ( noc_rst_n ),
    .test_i     ( test_mode_i ),
    .slv_req_i  ( ${pfx}_err_req ),
    .slv_resp_o ( ${pfx}_err_rsp )
  );
 % endfor
% endif

  // =======================================================================
  // 2b. FLOONOC JOIN (OPTIONAL)
  // =======================================================================
  // Instantiates a FlooNoC Join adapter if the underlying IP acts as an AXI 
  // Slave listening to both the Narrow and Wide networks simultaneously. 
  // It arbitrates and merges the two disparate traffic streams into a single, 
  // unified AXI interface for the IP.
% if use_join:
  <%
    c_data_width = None
    if noc_mode == "joined_narrow":
        c_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"
    elif noc_mode == "joined_wide":
        c_data_width = f"{noc_pkg}::AxiCfgW.DataWidth"
    elif 'AxiDataWidth' in valid_user_params:
        c_data_width = valid_user_params['AxiDataWidth']
    elif 'SramDataWidth' in valid_user_params:
        c_data_width = valid_user_params['SramDataWidth']
    if c_data_width is None:
        if is_host and original_type == 'cheshire_isle':
            c_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"
        elif config.topology.type == "noc":
            c_data_width = f"{noc_pkg}::AxiCfgW.DataWidth"
        else:
            c_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"
  %>
  % if c_data_width is not None:
  localparam floo_pkg::axi_cfg_t AxiCfgJoin = '{
    AddrWidth:  ${noc_pkg}::AxiCfgN.AddrWidth,
    DataWidth:  ${c_data_width},
    UserWidth:  floo_pkg::max(${noc_pkg}::AxiCfgN.UserWidth, ${noc_pkg}::AxiCfgW.UserWidth),
    InIdWidth:  floo_pkg::max(${noc_pkg}::AxiCfgN.OutIdWidth, ${noc_pkg}::AxiCfgW.OutIdWidth),
    OutIdWidth: floo_pkg::max(${noc_pkg}::AxiCfgN.OutIdWidth, ${noc_pkg}::AxiCfgW.OutIdWidth) + 1
  };
  % else:
  localparam floo_pkg::axi_cfg_t AxiCfgJoin = floo_pkg::axi_join_cfg(${noc_pkg}::AxiCfgN, ${noc_pkg}::AxiCfgW);
  % endif

  typedef logic [AxiCfgJoin.OutIdWidth-1:0] nw_join_id_t;
  typedef logic [AxiCfgJoin.UserWidth-1:0]  nw_join_user_t;
  typedef logic [AxiCfgJoin.DataWidth-1:0]  nw_join_data_t;
  typedef logic [AxiCfgJoin.DataWidth/8-1:0] nw_join_strb_t;

  `AXI_TYPEDEF_ALL_CT(axi_nw_join, axi_nw_join_req_t, axi_nw_join_rsp_t, ${noc_pkg}::axi_wide_out_addr_t,
                      nw_join_id_t, nw_join_data_t, nw_join_strb_t, nw_join_user_t)

  axi_nw_join_req_t join_req;
  axi_nw_join_rsp_t join_rsp;
  
  floo_nw_join #(
    .AxiCfgN         ( floo_pkg::axi_cfg_swap_iw(${noc_pkg}::AxiCfgN) ),
    .AxiCfgW         ( floo_pkg::axi_cfg_swap_iw(${noc_pkg}::AxiCfgW) ),
    .AxiCfgJoin      ( floo_pkg::axi_cfg_swap_iw(AxiCfgJoin) ),
    .EnAtopAdapter   ( 1'b0 ), // Assuming ATOP is handled by the Isle
    .AtopUserAsId    ( 1'b1 ), // Enforces ID preservation for ATOPs
    .axi_narrow_req_t( ${noc_pkg}::axi_narrow_out_req_t ),
    .axi_narrow_rsp_t( ${noc_pkg}::axi_narrow_out_rsp_t ),
    .axi_wide_req_t  ( ${noc_pkg}::axi_wide_out_req_t ),
    .axi_wide_rsp_t  ( ${noc_pkg}::axi_wide_out_rsp_t ),
    .axi_req_t       ( axi_nw_join_req_t ),
    .axi_rsp_t       ( axi_nw_join_rsp_t )
  ) i_join (
    .clk_i           ( noc_clk ),
    .rst_ni          ( noc_rst_n ),
    .test_enable_i   ( test_mode_i ),
    .axi_narrow_req_i( narrow_out_req ),
    .axi_narrow_rsp_o( narrow_out_rsp ),
    .axi_wide_req_i  ( wide_out_req ),
    .axi_wide_rsp_o  ( wide_out_rsp ),
    .axi_req_o       ( join_req ),
    .axi_rsp_i       ( join_rsp )
  );
% endif

% if is_host and config.system_controller:
  // =======================================================================
  // 2c. HOST REGBUS FLATTENING & SYSTEM CONTROLLER
  // =======================================================================
  // Only generated for the Host Tile. It intercepts the local slice of the 
  // Host's multi-dimensional RegBus array and converts it to APB to drive 
  // the PeakRDL System Controller. This allows the Host to access its 
  // core CSRs locally without a full NoC roundtrip.
  <%
    reg_rsp_type = isle_info.get("ports", {}).get("reg_rsp_i", {}).get("type_dim", "soc_reg_rsp_t").strip()
    reg_req_type = isle_info.get("ports", {}).get("reg_req_o", {}).get("type_dim", "soc_reg_req_t").strip()
    if "::" not in reg_rsp_type: reg_rsp_type = f"{soc_pkg}::{reg_rsp_type}"
    if "::" not in reg_req_type: reg_req_type = f"{soc_pkg}::{reg_req_type}"
    base_rsp_type = reg_rsp_type.split('[')[0].strip()
    base_req_type = reg_req_type.split('[')[0].strip()
  %>
  ${reg_req_type} tile_reg_req;
  ${reg_rsp_type} tile_reg_rsp;
  ${base_rsp_type} pcrs_rsp;

  assign reg_req_o = tile_reg_req;

  always_comb begin
    tile_reg_rsp = reg_rsp_i;
    tile_reg_rsp[$low(tile_reg_rsp)] = pcrs_rsp;
  end

  // RegBus to APB Adapter for PeakRDL System Controller
  ${require_bender("apb")}
  typedef logic [31:0] sys_apb_addr_t;
  typedef logic [31:0] sys_apb_data_t;
  typedef logic [3:0]  sys_apb_strb_t;
  `APB_TYPEDEF_ALL(sys_apb, sys_apb_addr_t, sys_apb_data_t, sys_apb_strb_t)

  sys_apb_req_t pcrs_apb_req;
  sys_apb_resp_t pcrs_apb_rsp;

  reg_to_apb #(
    .reg_req_t ( ${base_req_type} ),
    .reg_rsp_t ( ${base_rsp_type} ),
    .apb_req_t ( sys_apb_req_t ),
    .apb_rsp_t ( sys_apb_resp_t )
  ) i_sys_ctrl_reg_to_apb (
    .clk_i     ( clk_i ),
    .rst_ni    ( rst_ni ),
    .reg_req_i ( tile_reg_req[$low(tile_reg_req)] ),
    .reg_rsp_o ( pcrs_rsp ),
    .apb_req_o ( pcrs_apb_req ),
    .apb_rsp_i ( pcrs_apb_rsp )
  );

  ${top_level_module_name}_sys_regs i_sys_ctrl_regs (
    .clk            ( clk_i ),
    .arst_n         ( rst_ni ), // Async active-low reset
    .s_apb_paddr    ( pcrs_apb_req.paddr[4:0] ),
    .s_apb_pprot    ( pcrs_apb_req.pprot ),
    .s_apb_psel     ( pcrs_apb_req.psel ),
    .s_apb_penable  ( pcrs_apb_req.penable ),
    .s_apb_pwrite   ( pcrs_apb_req.pwrite ),
    .s_apb_pwdata   ( pcrs_apb_req.pwdata ),
    .s_apb_pstrb    ( pcrs_apb_req.pstrb ),
    .s_apb_pready   ( pcrs_apb_rsp.pready ),
    .s_apb_prdata   ( pcrs_apb_rsp.prdata ),
    .s_apb_pslverr  ( pcrs_apb_rsp.pslverr ),
    .hwif_in        ( sys_regs_hwif_in_i ),
    .hwif_out       ( sys_regs_hwif_out_o )
  );
% endif

<%
  isle_connections = [
    ".clk_i  ( tile_clk )",
    ".rst_ni ( tile_rst_n )"
  ]
  if 'test_mode_i' in known_ports: isle_connections.append(".test_mode_i ( test_mode_i )")
  if 'id_i' in known_ports: isle_connections.append(".id_i ( id_i )")
  
  if has_offload:
      isle_connections.append(".offload_wide_req_i ( offload_wide_req_out )")
      isle_connections.append(".offload_wide_rsp_o ( offload_wide_rsp_in )")

  if isle_ports:
      for p in isle_ports:
          if is_host and config.system_controller and p['name'] in ['reg_req_o', 'reg_rsp_i']:
              continue # Handled explicitly below
          isle_connections.append(f".{p['name']} ( {p['name']} )")
          
  if is_host and config.system_controller:
      if 'reg_req_o' in known_ports: isle_connections.append(".reg_req_o ( tile_reg_req )")
      if 'reg_rsp_i' in known_ports: isle_connections.append(".reg_rsp_i ( tile_reg_rsp )")

  if terminated_ports:
      for p in terminated_ports:
          if p['dir'] == 'input':
              isle_connections.append(f".{p['name']} ( '0 )")
          else:
              isle_connections.append(f".{p['name']} ( )")
              
  if error_slave_ports:
      for p in error_slave_ports:
          isle_connections.append(f".{p['name']} ( {p['name']} )")
  
  if has_master:
      if noc_mode == "dual":
          if has_master_narrow:
              isle_connections.append(".axi_narrow_req_o  ( narrow_in_req )")
              isle_connections.append(".axi_narrow_resp_i ( narrow_in_rsp )")
          if has_master_wide:
              isle_connections.append(".axi_wide_req_o  ( wide_in_req )")
              isle_connections.append(".axi_wide_resp_i ( wide_in_rsp )")
      else:
          mst_req_sig = "narrow_in_req" if has_master_narrow else "wide_in_req"
          mst_rsp_sig = "narrow_in_rsp" if has_master_narrow else "wide_in_rsp"
          if '[' in axi_req_o_dim:
              isle_connections.append(f".axi_req_o  ( {{{mst_req_sig}}} )")
              isle_connections.append(f".axi_resp_i ( {{{mst_rsp_sig}}} )")
          else:
              isle_connections.append(f".axi_req_o  ( {mst_req_sig} )")
              isle_connections.append(f".axi_resp_i ( {mst_rsp_sig} )")
      
  if has_slave:
      if noc_mode == "dual":
          if has_slave_narrow:
              isle_connections.append(".axi_narrow_req_i  ( narrow_out_req )")
              isle_connections.append(".axi_narrow_resp_o ( narrow_out_rsp )")
          if has_slave_wide:
              isle_connections.append(".axi_wide_req_i  ( wide_out_req )")
              isle_connections.append(".axi_wide_resp_o ( wide_out_rsp )")
      else:
          req_sig = "join_req" if use_join else ("wide_out_req" if has_slave_wide else "narrow_out_req")
          rsp_sig = "join_rsp" if use_join else ("wide_out_rsp" if has_slave_wide else "narrow_out_rsp")
          
          if '[' in axi_req_i_dim:
              isle_connections.append(f".axi_req_i  ( {{{req_sig}}} )")
              isle_connections.append(f".axi_resp_o ( {{{rsp_sig}}} )")
          else:
              isle_connections.append(f".axi_req_i  ( {req_sig} )")
              isle_connections.append(f".axi_resp_o ( {rsp_sig} )")

  # Auto-tie-off remaining unconnected ports to prevent TFMPC / Linter warnings.
  connected_ports = []
  for p in isle_connections:
      m = re.match(r'^\s*\.\s*([a-zA-Z0-9_]+)\s*\(', p)
      if m: connected_ports.append(m.group(1))
      
  for port_name, p_info in isle_info.get("ports", {}).items():
      if port_name not in connected_ports:
          val = "'0" if p_info["dir"] == "input" else ""
          isle_connections.append(f".{port_name:<17} ( {val} )")
%>
% if isle_type_overrides:
  // Internal type overrides for the Isle (defined at the bottom to ensure they can use the local typedefs)
  % for k, v in sorted(isle_type_overrides.items()):
    % if k.endswith('_t'):
  localparam type ${k} = ${v};
    % endif
  % endfor

% endif

  // =======================================================================
  // 3. ISLE INSTANTIATION (${isle_name})
  // =======================================================================
  // Instantiates the actual core hardware IP (the Isle). 
  // Its standard AXI ports are wired to the Chimney/Join adapters, while any 
  // exported native physical I/O or interrupts are passed through to the Top-Level.
  
% if not has_slave_narrow:
  assign narrow_out_rsp = '0;
% endif
% if not has_slave_wide:
  assign wide_out_rsp   = '0;
% endif
  ${isle_name} \
% if all_params or isle_type_overrides:
  #(\
<%
  combined_params = []
  for k in all_params.keys(): combined_params.append(f".{k} ( {k} )")
  for k, v in isle_type_overrides.items(): combined_params.append(f".{k} ( {v} )")
%>
% for i, p_str in enumerate(combined_params):
    ${p_str}${"," if i < len(combined_params)-1 else ""}
% endfor
  )\
% endif
   i_isle (
% for i, conn in enumerate(isle_connections):
    ${conn}${"," if i < len(isle_connections)-1 else ""}
% endfor
  );

endmodule : ${p_name}_${c_type}

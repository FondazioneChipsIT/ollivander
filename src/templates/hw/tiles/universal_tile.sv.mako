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
  
  # Membership from config.control_group_members, the single authority the RTL bit indices,
  # the register width and the firmware contract all use. This was a FOURTH inline copy of the
  # rule: the other three were unified on 2026-08-27, and one left behind would have been
  # enough to let them drift again. Only this component's original type is needed, so a
  # one-entry map is passed rather than the whole table the generator holds.
  has_clk_ctrl = False
  if not is_host and config.system_controller and config.system_controller.auto_control_groups:
      _orig = {comp.name: context.get('original_type', c_type)}
      for g in config.system_controller.auto_control_groups:
          if any(m.name == comp.name for m, _ in config.control_group_members(g, _orig)):
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

  # AXI ISOLATION OWNED BY THE TILE.
  #
  # Isolation fences the OUTBOUND path - it stops a block injecting into the network while it is
  # being reset or powered down - so it needs a master port to sit on; a slave-only component has
  # nothing to fence. Every cell that exists in the tree today lives inside an isle
  # (spatz_cluster_isle, ethernet_isle), which is why the tile only forwards the pair when the
  # isle declares it: an isle that owns its cell keeps it, and the tile adds nothing.
  #
  # For an isle that declares no cell - sram_isle, cluster_subtile - the tile instantiates one
  # per master network here. It is the only place that can: the isle is hand-written and would
  # need editing per component, while the tile is generated and the wires on both sides of the
  # insertion point are already its own.
  isle_owns_isolate = 'axi_isolate_i' in known_ports
  tile_owns_isolate = (bool(comp.system_config and comp.system_config.get('isolate'))
                       and not isle_owns_isolate and has_master)
  iso_nets = []
  if tile_owns_isolate:
      if has_master_narrow: iso_nets.append("narrow")
      if has_master_wide:   iso_nets.append("wide")
  
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
          # NOTE ON INSTANCE IDENTITY. It used to travel only as
          # the InstanceBaseAddr / InstanceWindowSize header parameters. The WINDOW
          # SIZE still does - it is identical across the instances of a component, so
          # it costs nothing - but the BASE may differ per instance, and a differing
          # parameter value is a DISTINCT MODULE for Verilator: sixteen identical
          # cluster tiles became sixteen hierarchical specializations, each elaborated
          # and compiled separately, with elaboration accounting for half of a cold
          # build (docs/developer/wip, section 5.2.-1). A subtile that needs the base
          # only at run time therefore takes it as the port below, and the generator
          # drives the constant from the top. The parameter path stays for everything
          # not converted yet: l2_isle, for one, is convertible on inspection (its
          # base feeds mapping rules that dyn_mem takes on a PORT, so the localparams
          # could be wires) but is instantiated once per project, and one instance
          # cannot be specialized twice - there is nothing to collapse and no reason
          # to touch the boot memory's decoding. The day an array of it appears, the
          # conversion is the same three lines as here.
          passthrough_ports = {
              'sys_clk_i', 'sys_rst_ni', 'pwr_on_rst_ni', 'rt_clk_i', 'boot_mode_i', 'bootmode_i',
              'axi_isolate_i', 'axi_isolated_o', 'fetch_en_i', 'en_sa_boot_i', 'boot_addr_i',
              'busy_o', 'eoc_o', 'debug_req_i', 'instance_base_addr_i'
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
  # 2b. THE JOINED AXI CONFIGURATION, AS EXPRESSIONS
  # ============================================================================
  # The joined configuration is also declared as a localparam in the module BODY
  # (section 2b below) for the typedefs, but a parameter port list cannot see the
  # body: SystemVerilog elaborates it first, so 'AxiCfgJoin.AddrWidth' as a
  # parameter default is a use-before-declaration. Questa and Verilator tolerated
  # it; a strict front-end does not. Both places are therefore fed from the same
  # dictionary of PACKAGE-level expressions, which the parameter list can see, and
  # the body localparam is assembled from the very same strings so the two cannot
  # drift apart.
  join_cfg_data_width = None
  if noc_mode == "joined_narrow":
      join_cfg_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"
  elif noc_mode == "joined_wide":
      join_cfg_data_width = f"{noc_pkg}::AxiCfgW.DataWidth"
  elif 'AxiDataWidth' in valid_user_params:
      join_cfg_data_width = valid_user_params['AxiDataWidth']
  elif 'SramDataWidth' in valid_user_params:
      join_cfg_data_width = valid_user_params['SramDataWidth']
  if join_cfg_data_width is None:
      if is_host and original_type == 'cheshire_isle':
          join_cfg_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"
      elif config.topology.type == "noc":
          join_cfg_data_width = f"{noc_pkg}::AxiCfgW.DataWidth"
      else:
          join_cfg_data_width = f"{noc_pkg}::AxiCfgN.DataWidth"

  _join_max_out_id = f"floo_pkg::max({noc_pkg}::AxiCfgN.OutIdWidth, {noc_pkg}::AxiCfgW.OutIdWidth)"
  join_cfg = {
      'AddrWidth':  f"{noc_pkg}::AxiCfgN.AddrWidth",
      'DataWidth':  join_cfg_data_width,
      'UserWidth':  f"floo_pkg::max({noc_pkg}::AxiCfgN.UserWidth, {noc_pkg}::AxiCfgW.UserWidth)",
      'InIdWidth':  _join_max_out_id,
      'OutIdWidth': f"{_join_max_out_id} + 1",
  }

  def cfg_field(prefix, field):
      """'<cfg>.<field>' for a parameter default, join expanded to package terms."""
      return join_cfg[field] if prefix == "AxiCfgJoin" else f"{prefix}.{field}"

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

      # An isle exporting both a slave and a master keeps 'axi_req_t' for the slave
      # side, so the master pair carries its own names - and was therefore never
      # overridden by the branch above, which only fires when there is no slave. The
      # macro's own SoC types reached the network untouched: a nested crossbar macro
      # presented a 6-bit ID and a 10-bit user field to a network carrying 4 and 5.
      # Package-qualified, so that a NoC macro nested in a NoC parent - which imports
      # two FlooNoC packages declaring the same names - cannot resolve it to the wrong
      # one (vlog-2542).
      if 'axi_master_req_t' in all_params:
          isle_type_overrides['axi_master_req_t'] = f"{noc_pkg}::{req_mst_type}"
      if 'axi_master_resp_t' in all_params:
          isle_type_overrides['axi_master_resp_t'] = f"{noc_pkg}::{rsp_mst_type}"
      
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
      if 'AxiInIdWidth' in all_params: all_params['AxiInIdWidth'] = cfg_field(cfg_slv_pfx, 'OutIdWidth')
      if 'AxiIdWidth' in all_params: all_params['AxiIdWidth'] = cfg_field(cfg_slv_pfx, 'OutIdWidth')
      if 'AxiUserWidth' in all_params: all_params['AxiUserWidth'] = cfg_field(cfg_slv_pfx, 'UserWidth')
      if not has_master or use_join:
          if 'AxiDataWidth' in all_params: all_params['AxiDataWidth'] = cfg_field(cfg_slv_pfx, 'DataWidth')
          if 'AxiAddrWidth' in all_params: all_params['AxiAddrWidth'] = cfg_field(cfg_slv_pfx, 'AddrWidth')
          
  # A subtile macro exports one AXI pair per network, both typed with the input
  # type of the network (see the boundary comment in noc_soc_top.sv.mako). Hand it
  # this parent's own per-direction types, so the boundary follows the network the
  # macro is plugged into rather than the one it was generated against: left alone,
  # the macro keeps its own SoC types, a single ID and user width for both networks
  # and both directions, which matches neither of them.
  #
  # Only a generated macro exposes these as type parameters, and the condition is
  # load-bearing: a hand-written dual isle types its ports from its own IP package,
  # and the snitch cluster subtile takes OutIdWidth on its subordinate side, which
  # is exactly what the chimney output already carries. Hence macro_boundary_*
  # below, which keeps the two decisions together - an isle gets the input-typed
  # signals if and only if its port types were overridden to match.
  #
  # The types are package-qualified because a NoC macro inside a NoC parent imports
  # both FlooNoC packages, which declare the very same names: a bare name is
  # ambiguous (vlog-2542) and resolves to whichever package came first.
  if noc_mode == "dual":
      dual_boundary_types = {
          'axi_narrow_req_t':  f"{noc_pkg}::axi_narrow_in_req_t",
          'axi_narrow_resp_t': f"{noc_pkg}::axi_narrow_in_rsp_t",
          'axi_wide_req_t':    f"{noc_pkg}::axi_wide_in_req_t",
          'axi_wide_resp_t':   f"{noc_pkg}::axi_wide_in_rsp_t",
      }
      for boundary_param, boundary_type in dual_boundary_types.items():
          if boundary_param in all_params:
              isle_type_overrides[boundary_param] = boundary_type

  macro_boundary_narrow = 'axi_narrow_req_t' in isle_type_overrides and noc_mode == "dual"
  macro_boundary_wide   = 'axi_wide_req_t'   in isle_type_overrides and noc_mode == "dual"

  # A dual isle whose master ports we could not retype - a hand-written wrapper takes
  # them from its own IP package, as the snitch cluster subtile does - produces the ID
  # width that IP was built with, which may be narrower than the network's input width.
  # The zero-extension is done field-wise here: a wire when the widths already agree,
  # and the correct adaptation when they do not, where before it was a silent aliasing
  # of the most significant ID bits. The types are read from the isle's own ports, since
  # only the isle knows them.
  def isle_port_type(p_name):
      return (isle_info or {}).get("ports", {}).get(p_name, {}).get("type_dim", "").strip()

  mst_adapt = []
  if noc_mode == "dual" and has_master:
      for net, present, is_macro in (("narrow", has_master_narrow, macro_boundary_narrow),
                                     ("wide", has_master_wide, macro_boundary_wide)):
          if not present or is_macro:
              continue
          req_t, rsp_t = isle_port_type(f"axi_{net}_req_o"), isle_port_type(f"axi_{net}_resp_i")
          if req_t and rsp_t:
              mst_adapt.append((net, req_t, rsp_t))
  adapted_mst_nets = {net for net, _, _ in mst_adapt}

  # THE REG / LLC TYPES ARE PACKAGE TYPES, NOT TILE PARAMETERS. They used to stay
  # in the tile's public parameter list, where the top then overrode each of them
  # with... the very package type they already defaulted to. The round trip cost
  # more than redundancy: a wrapper carrying a 'parameter type' cannot be a
  # Verilator hier_block (5.050 fails rebuilding a type in __hierParameters), so
  # six pass-through types were keeping the whole host tile inlined in the top
  # unit - the single heaviest component of the design. Resolved here instead, at
  # the isle instantiation, exactly like the AXI types above: same values, no
  # public parameter, and the top's overrides disappear on their own because they
  # are derived from the wrapper's declared parameters.
  for _p, _fill in (
      ('sync_reg_out_req_t',  f"{soc_pkg}::soc_reg_req_t"),
      ('sync_reg_out_rsp_t',  f"{soc_pkg}::soc_reg_rsp_t"),
      ('async_reg_out_req_t', f"{soc_pkg}::soc_reg_req_t"),
      ('async_reg_out_rsp_t', f"{soc_pkg}::soc_reg_rsp_t"),
      ('sync_reg_in_req_t',   f"{soc_pkg}::soc_reg_req_t"),
      ('sync_reg_in_rsp_t',   f"{soc_pkg}::soc_reg_rsp_t"),
      ('reg_req_t',           f"{soc_pkg}::soc_reg_req_t"),
      ('reg_rsp_t',           f"{soc_pkg}::soc_reg_rsp_t"),
      ('axi_llc_req_t',       f"{soc_pkg}::soc_axi_llc_req_t"),
      ('axi_llc_resp_t',      f"{soc_pkg}::soc_axi_llc_resp_t"),
  ):
      if _p in all_params and _p not in isle_type_overrides:
          isle_type_overrides[_p] = _fill

  for k in isle_type_overrides.keys():
      if k.endswith('_t') and k in all_params: del all_params[k]

  param_decl_types = isle_info.get('param_types', {}) if isle_info else {}

  def fmt_param_type(p_name, p_val):
      # The type the isle header DECLARES wins whenever it is a plain built-in
      # (bit / int unsigned / longint unsigned / logic[N:M] / string): the value
      # heuristics below cannot tell a 64-bit parameter from a 32-bit one once
      # the parser has normalized the default, which capped instance-identity
      # values at 4 GiB. Scoped or exotic types fall back to the heuristics.
      decl = (param_decl_types.get(p_name) or "").strip()
      if re.fullmatch(r"[a-z][a-z0-9_ ]*(\[[0-9]+:[0-9]+\])?", decl):
          return decl
      if isinstance(p_val, bool) or str(p_val) in ["True", "False"]: return "bit"
      # A default written as a sized 64-bit literal declares its intent: keep the
      # 64-bit parameter type across the tile boundary (InstanceBaseAddr et al.),
      # or a wider override would silently truncate against an 'int unsigned'.
      if str(p_val).startswith("64'"): return "longint unsigned"
      if str(p_val).isdigit():
          # A bare decimal literal is 32-bit in SV, and 'int unsigned' cannot hold
          # more: a wider default (first hit: cheshire_isle's LlcOutRegionEnd,
          # 0x1_0000_0000) needs the 64-bit parameter type, paired with the sized
          # literal fmt_param_val emits for the same values.
          return "longint unsigned" if int(str(p_val)) > 0x7FFFFFFF else "int unsigned"
      if str(p_val) == "logic" or str(p_val).endswith("_t"): return "type"
      if str(p_val).startswith('"') or str(p_val).startswith("'"): return "string"
      return "int unsigned"

  def fmt_param_val(p_val):
      if isinstance(p_val, bool): return "1'b1" if p_val else "1'b0"
      if str(p_val) == "True": return "1'b1"
      if str(p_val) == "False": return "1'b0"
      # Size any literal beyond 32 bits: unsized decimals cap at 32 bits (vlog-13008).
      # The signed-32 boundary, not the unsigned one: an unsized decimal literal
      # is SIGNED, so anything past 2^31-1 sign-extends into a wider parameter.
      if str(p_val).isdigit() and int(str(p_val)) > 0x7FFFFFFF: return f"64'd{p_val}"
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
          # The Jtag* family joins the pass-through (wip 2.1): the testbench reads the
          # host's boot capabilities from the TILE wrapper on the NoC family, so the
          # isle-declared JTAG boot contract must survive the isle-to-tile conversion
          # exactly as the ForceBoot* one does. The Slink* preload contract
          # follows for the same reason; its values are EXPRESSIONS over isle params
          # the tile header re-declares, so they keep resolving in tile scope.
          # The Boot* family joins them: it locates the host's internal scratchpad
          # (BootSpmOffset/Size) and names the autonomous boots' device models and
          # straps. Absent from this list, both the internal-scratchpad boot memory
          # and the autonomous boot modes were silently unavailable on the NoC
          # family - the generator would look for a contract the tile had dropped.
          if param_name.startswith("Preload") or param_name.startswith("ForceBoot") or param_name.startswith("Jtag") or param_name.startswith("SlinkAxi") or param_name.startswith("Boot") or param_name in ["HasEcc", "EccType", "HasForceBoot", "HasJtagBoot", "HasSlinkPreload", "HasAutonomousBoot"]:
              if param_name in ["PreloadTemplate", "ForceBootPath"]:
                  clean_val = p_val.strip("\"'")
                  p_val = f'"i_isle.{clean_val}"'
              fixed_params_to_expose.append((param_name, p_val))
%>
% if all_params or fixed_params_to_expose:
#(
 % for i, (param_name, p_val) in enumerate(all_params.items()):
  parameter ${fmt_param_type(param_name, p_val)} ${param_name} = ${fmt_param_val(p_val)}${"," if (i < len(all_params)-1 or fixed_params_to_expose) else ""}
 % endfor
 % for i, (param_name, p_val) in enumerate(fixed_params_to_expose):
  localparam ${fmt_param_type(param_name, p_val)} ${param_name} = ${fmt_param_val(p_val)}${"," if i < len(fixed_params_to_expose)-1 else ""}
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
<%
  ## Three optional blocks follow, each needing a separator from whatever precedes it.
  ## The flags let every comma be emitted at the end of the line it belongs to; produced
  ## from inside the blocks instead, they landed on lines of their own.
  has_isle_ports = bool(isle_ports)
  has_sysctrl_ports = bool(is_host and config.system_controller)
  has_iso_ports = bool(iso_nets)
  has_tail_ports = has_isle_ports or has_clk_ctrl or has_iso_ports or has_sysctrl_ports
%>\
  input wire ${noc_pkg}::floo_wide_t [West:North] floo_wide_i${"," if has_tail_ports else ""}

  // =======================================================================
  // COMPONENT-SPECIFIC I/Os and INTERRUPTS (Extracted from ${isle_name})
  // =======================================================================

% if isle_ports:
 % for i, p in enumerate(isle_ports):
  ${p['dir']} ${p['type']} ${p['name']}${p.get('unpacked', '')}${"," if i < len(isle_ports)-1 or has_clk_ctrl or has_iso_ports or has_sysctrl_ports else ""}
 % endfor
% endif

% if has_clk_ctrl:
  // =======================================================================
  // CLOCK GATING & RESET CONTROL
  // =======================================================================
  // Dynamic clock gating and reset bypass logic for this specific Tile.
  // This is managed centrally by the System Controller via the Auto Control 
  // Groups mechanism, allowing fine-grained power management of the NoC array.
  input  logic tile_clk_en_i,
  input  logic tile_rst_ni,
  input  logic clk_rst_bypass_i${"," if has_iso_ports or has_sysctrl_ports else ""}
% endif

% if has_iso_ports:
  // =======================================================================
  // AXI ISOLATION (owned by this tile: the isle declares no cell of its own)
  // =======================================================================
  // Driven from the System Controller's isolation CSRs, exactly as the crossbar drives an
  // isle that owns its cell. 'axi_isolated_o' is asserted only when EVERY master network of
  // this tile has drained, so one bit means "quiet in every direction this block can speak".
  input  logic axi_isolate_i,
  output logic axi_isolated_o${"," if has_sysctrl_ports else ""}
% endif

% if has_sysctrl_ports:
<%
  def resolve_port_type(decl):
      """Map an isle port type onto what the TILE declares.

      The isle names its own type PARAMETER (e.g. 'sync_reg_out_req_t'); the tile
      resolves those parameters at the isle instantiation (isle_type_overrides)
      and does not re-declare them, so a port that kept the parameter name would
      reference an identifier that no longer exists in this scope. Substituting
      the resolved value keeps the port and the instantiation on one type.
      """
      out = decl
      for _k, _v in isle_type_overrides.items():
          out = re.sub(rf"\b{re.escape(_k)}\b", _v, out)
      return out

  reg_rsp_type = resolve_port_type(isle_info.get("ports", {}).get("reg_rsp_i", {}).get("type_dim", "soc_reg_rsp_t").strip())
  reg_req_type = resolve_port_type(isle_info.get("ports", {}).get("reg_req_o", {}).get("type_dim", "soc_reg_req_t").strip())
  if "::" not in reg_rsp_type: reg_rsp_type = f"{soc_pkg}::{reg_rsp_type}"
  if "::" not in reg_req_type: reg_req_type = f"{soc_pkg}::{reg_req_type}"
%>
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

  // THE GROUP REGISTER BIT IS THIS TILE'S ONLY RESET SOURCE, and it is a flop output: no
  // combinational logic sits on this net, so no glitch can reach part of the payload and the
  // POR synchronizer's synchronous release is not undone downstream. The power-on reset
  // arrives through that register's RESET VALUE, which soc_regs.rdl.mako pins to 'held in
  // reset' under both power-on policies - the route the gwaihir reference uses. ANDing
  // 'rst_ni' in here, as this did until 2026-08-27, added exactly that combinational
  // combination of two asynchronous sources for a path the POR already covers.
  //
  // Only the bypass is muxed, and its select is static; the mux is a clock cell so the
  // implementation flow treats this net as the tree it is.
`ifdef TARGET_XILINX
  assign tile_rst_n = (clk_rst_bypass_i) ? rst_ni : tile_rst_ni;
`else
  tc_clk_mux2 i_tc_reset_mux (
    .clk0_i   ( tile_rst_ni ),
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
% if has_slave and (macro_boundary_narrow or macro_boundary_wide):

  // A subtile macro presents the network's input type on both of its AXI ports,
  // while the chimney output carries OutIdWidth: the ID is widened back here, next
  // to the chimney that narrowed it. Field-wise, so that the extension applies to
  // 'id' alone; a whole-struct assignment would misalign every field, 'id' being
  // the first member and therefore the most significant bits.
 % if has_slave_narrow and macro_boundary_narrow:
  ${noc_pkg}::axi_narrow_in_req_t border_narrow_req;
  ${noc_pkg}::axi_narrow_in_rsp_t border_narrow_rsp;
  `AXI_ASSIGN_REQ_STRUCT(border_narrow_req, narrow_out_req)
  `AXI_ASSIGN_RESP_STRUCT(narrow_out_rsp, border_narrow_rsp)
 % endif
 % if has_slave_wide and macro_boundary_wide:
  ${noc_pkg}::axi_wide_in_req_t   border_wide_req;
  ${noc_pkg}::axi_wide_in_rsp_t   border_wide_rsp;
  `AXI_ASSIGN_REQ_STRUCT(border_wide_req, wide_out_req)
  `AXI_ASSIGN_RESP_STRUCT(wide_out_rsp, border_wide_rsp)
 % endif
% endif
% if iso_nets:

  // ISOLATION NETS, DECLARED HERE AND NOT WITH THEIR CELLS FURTHER DOWN. The conversion
  // block below drives 'iso_<net>_req' through an `AXI_ASSIGN macro, and a declaration
  // that came after that use compiled under vlog but was rejected by the slang pass over
  // the stubbed flist ("identifier used before its declaration"). Keeping the declarations
  // ahead of every consumer is the fix; the cells themselves stay next to their comment.
 % for net in iso_nets:
  ${noc_pkg}::axi_${net}_in_req_t iso_${net}_req;
  ${noc_pkg}::axi_${net}_in_rsp_t iso_${net}_rsp;
  logic iso_${net}_isolated;
 % endfor
% endif
% if mst_adapt:

  // The master side of an isle that keeps the AXI types of its own IP: its ID is
  // zero-extended to the network's input width on the way in, and truncated back on the
  // response, which recovers the original value exactly.
 % for net, req_t, rsp_t in mst_adapt:
  ${req_t} isle_${net}_req;
  ${rsp_t} isle_${net}_rsp;
  `AXI_ASSIGN_REQ_STRUCT(${"iso_" + net + "_req" if net in iso_nets else net + "_in_req"}, isle_${net}_req)
  `AXI_ASSIGN_RESP_STRUCT(isle_${net}_rsp, ${"iso_" + net + "_rsp" if net in iso_nets else net + "_in_rsp"})
 % endfor
% endif
% if iso_nets:

  // =======================================================================
  // AXI ISOLATION CELLS (outbound: this block towards the network)
  // =======================================================================
  // Inserted between whatever drives the chimney's input and the chimney itself, which is the
  // isle-to-network direction: 'axi_isolate' drains the transactions this block still has in
  // flight, then silences its master port. TerminateTransaction answers anything the block
  // issues afterwards with an error instead of blocking it, so a late access cannot deadlock
  // the isle against its own closed fence.
  //
  // CLOCKED BY 'noc_clk', THE UNGATED CLOCK, DELIBERATELY. The isle runs on the gated
  // 'tile_clk'; the two share a source, so during the drain both see the same edges and no
  // domain is crossed. Afterwards the cell must keep silencing its output while the isle is
  // gated, and must keep 'axi_isolated_o' readable - on the gated clock it would freeze
  // isolated, which is functionally safe (the state and the silencing are held) but would make
  // the status unreadable exactly when software wants to check it.
  //
  // NumPending comes from the chimney's own configuration for that network: the counter must
  // track what this path can have in flight, and 'ChimneyDefaultCfg' is the value the chimney
  // below is built with. Deriving it there rather than picking a constant is what keeps the two
  // in step if the network configuration ever changes.
  logic axi_isolate_sync;
  ${require_file("olli_sync.sv")}
  // The control crosses from the System Controller's clock domain. On today's mesh that is the
  // same 'system' clock the tile runs on, so the synchronizer is redundant - it is here because
  // 'dedicated_clock_div' makes a tile on a divided clock expressible, and the day someone
  // declares one this is the difference between a clean bring-up and an intermittent one.
  // RESET WITH THE NETWORK SIDE, not with the block being fenced: 'noc_rst_n' is the tile's
  // ungated domain reset, the very reset the chimney below uses, and never 'tile_rst_n' (the
  // gated software reset of the component). Two reasons, and the second is the load-bearing one:
  // the fence must survive the reset of the block it is isolating, and both ends of this AXI
  // path must reset together - a cell resetting independently of the chimney it feeds would
  // restart one end while the other still held mid-transaction state.
  olli_sync #(
    .STAGES ( 2 )
  ) i_axi_isolate_sync (
    .clk_i    ( noc_clk ),
    .rst_ni   ( ${"pwr_on_rst_ni" if "pwr_on_rst_ni" in known_ports else "noc_rst_n"} ),
    .serial_i ( axi_isolate_i ),
    .serial_o ( axi_isolate_sync )
  );

 % for net in iso_nets:

  axi_isolate #(
    .NumPending           ( floo_pkg::ChimneyDefaultCfg.MaxTxns ),
    .TerminateTransaction ( 1'b1 ),
    .AtopSupport          ( 1'b1 ),
    .AxiAddrWidth         ( ${noc_pkg}::AxiCfg${"N" if net == "narrow" else "W"}.AddrWidth ),
    .AxiDataWidth         ( ${noc_pkg}::AxiCfg${"N" if net == "narrow" else "W"}.DataWidth ),
    .AxiIdWidth           ( ${noc_pkg}::AxiCfg${"N" if net == "narrow" else "W"}.InIdWidth ),
    .AxiUserWidth         ( ${noc_pkg}::AxiCfg${"N" if net == "narrow" else "W"}.UserWidth ),
    .axi_req_t            ( ${noc_pkg}::axi_${net}_in_req_t ),
    .axi_resp_t           ( ${noc_pkg}::axi_${net}_in_rsp_t )
  ) i_axi_${net}_out_isolate (
    .clk_i      ( noc_clk ),
    .rst_ni     ( noc_rst_n ),
    .slv_req_i  ( iso_${net}_req ),
    .slv_resp_o ( iso_${net}_rsp ),
    .mst_req_o  ( ${net}_in_req ),
    .mst_resp_i ( ${net}_in_rsp ),
    .isolate_i  ( axi_isolate_sync ),
    .isolated_o ( iso_${net}_isolated )
  );
 % endfor

  // One status bit for the whole tile: asserted only when every master network has drained, so
  // the firmware waits on a single fact and cannot gate a clock while one direction is still
  // in flight.
  assign axi_isolated_o = ${" && ".join("iso_" + n + "_isolated" for n in iso_nets)};
% endif

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
    ## Same expressions the parameter port list was fed (section 2b above), so
    ## the two views of the joined configuration cannot drift apart.
    c_data_width = join_cfg['DataWidth']
  %>
  % if c_data_width is not None:
  localparam floo_pkg::axi_cfg_t AxiCfgJoin = '{
    AddrWidth:  ${join_cfg['AddrWidth']},
    DataWidth:  ${c_data_width},
    UserWidth:  ${join_cfg['UserWidth']},
    InIdWidth:  ${join_cfg['InIdWidth']},
    OutIdWidth: ${join_cfg['OutIdWidth']}
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
    reg_rsp_type = resolve_port_type(isle_info.get("ports", {}).get("reg_rsp_i", {}).get("type_dim", "soc_reg_rsp_t").strip())
    reg_req_type = resolve_port_type(isle_info.get("ports", {}).get("reg_req_o", {}).get("type_dim", "soc_reg_req_t").strip())
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
          # The adapted signals where the isle keeps its own AXI types, the chimney's own
          # where it took the network types: see the widening above.
          # Three possible destinations, in precedence order: the ID-adapting wire when this
          # net is adapted (the adapter then feeds the isolation cell, if any), the isolation
          # cell's slave side when the tile owns a cell on this net, or the chimney's input
          # directly. The cell must sit BETWEEN the isle and the chimney, so it can never be
          # bypassed by a connection made here.
          if has_master_narrow:
              nsig = ("isle_narrow" if "narrow" in adapted_mst_nets
                      else "iso_narrow" if "narrow" in iso_nets else "narrow_in")
              isle_connections.append(f".axi_narrow_req_o  ( {nsig}_req )")
              isle_connections.append(f".axi_narrow_resp_i ( {nsig}_rsp )")
          if has_master_wide:
              wsig = ("isle_wide" if "wide" in adapted_mst_nets
                      else "iso_wide" if "wide" in iso_nets else "wide_in")
              isle_connections.append(f".axi_wide_req_o  ( {wsig}_req )")
              isle_connections.append(f".axi_wide_resp_i ( {wsig}_rsp )")
      else:
          # Single-network master: the isolation cell, when the tile owns one, replaces the
          # chimney's input as the isle's destination for the same reason as above.
          _mnet = "narrow" if has_master_narrow else "wide"
          _mpfx = f"iso_{_mnet}" if _mnet in iso_nets else f"{_mnet}_in"
          mst_req_sig = f"{_mpfx}_req"
          mst_rsp_sig = f"{_mpfx}_rsp"
          if '[' in axi_req_o_dim:
              isle_connections.append(f".axi_req_o  ( {{{mst_req_sig}}} )")
              isle_connections.append(f".axi_resp_i ( {{{mst_rsp_sig}}} )")
          else:
              isle_connections.append(f".axi_req_o  ( {mst_req_sig} )")
              isle_connections.append(f".axi_resp_i ( {mst_rsp_sig} )")
      
  if has_slave:
      if noc_mode == "dual":
          # A macro boundary takes the input-typed signals, see the widening next to
          # the chimney declarations; any other dual isle takes the chimney output
          # directly, which already carries the width its subordinate side expects.
          if has_slave_narrow:
              nsig = "border_narrow" if macro_boundary_narrow else "narrow_out"
              isle_connections.append(f".axi_narrow_req_i  ( {nsig}_req )")
              isle_connections.append(f".axi_narrow_resp_o ( {nsig}_rsp )")
          if has_slave_wide:
              wsig = "border_wide" if macro_boundary_wide else "wide_out"
              isle_connections.append(f".axi_wide_req_i  ( {wsig}_req )")
              isle_connections.append(f".axi_wide_resp_o ( {wsig}_rsp )")
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
## The type overrides used to be mirrored here as 'localparam type' declarations. They
## were dead: the Isle instantiation below already receives each override directly
## (.axi_req_t ( axi_nw_join_req_t )), and no generated tile of any example ever
## referenced the localparam names — verified across every example project.
## Dead was not harmless: Verilator counts a body 'localparam type' as part of a
## hier_block's parameterization, serializes it into __hierParameters.v as a typedef,
## and then fails on its own output with an internal error (V3LinkDot.cpp:496). That is
## what kept the L2 and wide-SPM tiles out of the hierarchical build, wrongly blamed on
## their struct-member parameter defaults until a probe separated the two.

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

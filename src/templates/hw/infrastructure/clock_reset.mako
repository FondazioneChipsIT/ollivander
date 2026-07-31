<%def name="clock_and_reset_tree(config, p_name)">
<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE CLOCK AND RESET TREE
  # ============================================================================
  # This template generates the entire clock and reset infrastructure for the SoC,
  # dynamically adapting to the `clock_tree` defined in the YAML configuration.
  # It instantiates Glitch-Free Muxes, Integer Dividers, Reset Synchronizers,
  # and the necessary Clock Domain Crossing (CDC) logic to safely control the 
  # clock distribution network at runtime via the System Controller's CSRs.

  host_clk = config.host.clock_domain or "system_clk"
  # Single source of truth shared with the generator and the testbench template.
  # Empty when the only non-real-time domain is the host's, in which case the SoC
  # has no global reset tree at all (see OllivanderConfig.managed_clock_domains).
  managed_domains = config.managed_clock_domains
  num_managed_domains = len(managed_domains)
%>
  // BENDER: name="common_cells"

  localparam int unsigned DomainClkDivValueWidth = 24;
  localparam int unsigned NumDomains = ${num_managed_domains if num_managed_domains > 0 else 1};

  // =========================================================================
  // 0. DOMAIN INDICES
  // =========================================================================
  // Enumeration of the managed clock domains, used to index the global reset arrays.
% for i, dom in enumerate(managed_domains):
  localparam int unsigned DomainIdx_${fmt_dom(dom.name)} = ${i};
% endfor

% if num_managed_domains > 0:
  // Per-domain reset vectors driven by the global reset tree instantiated further
  // below. They are declared here, ahead of the clock generation section, because
  // component instantiations later in the top-level consume them and SystemVerilog
  // requires the declaration to precede every use.
  //
  // They live under the same guard as the tree that drives them: a SoC with no
  // managed domain has no driver for these vectors, and declaring them
  // unconditionally would leave dangling signals stuck at X.
  logic [NumDomains-1:0] pwr_on_rsts_n;
  logic [NumDomains-1:0] rsts_n;
% endif

  // =========================================================================
  // 1. CLOCK GENERATION (MUXES & DIVIDERS)
  // =========================================================================
% for dom in config.clock_tree.domains:
  // --- Domain: ${dom.name} ---
 % if dom.is_real_time:
  // Real-Time domains bypass SW control (always-on, fixed source).
  // Typically used for RTCs or Always-On Timers.
  % if dom.static_div is not None and dom.static_div > 1:
  logic ${dom.name}_source;
  assign ${dom.name}_source = ${f"domain_clk_i[{dom.source_gen}]" if config.clock_tree.generators > 0 and dom.source_gen is not None else "rt_clk_i"};
  
  // Real-Time hardwired static divider (always enabled)
  ${require_file("olli_clk_int_div.sv")}
  olli_clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(${dom.static_div}),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_static_div (
    .clk_i          ( ${dom.name}_source ),
    .rst_ni         ( host_pwr_on_rst_n ),
    .en_i           ( 1'b1 ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( 24'd${dom.static_div} ),
    .div_valid_i    ( 1'b0 ),
    .div_ready_o    ( ),
    .clk_o          ( ${dom.name} ),
    .cycl_count_o   ( )
  );
  % else:
  logic ${dom.name};
  assign ${dom.name} = ${f"domain_clk_i[{dom.source_gen}]" if config.clock_tree.generators > 0 and dom.source_gen is not None else "rt_clk_i"};
  % endif
 % else:
  logic ${dom.name}_muxed;
  logic ${dom.name}; // Final gated/divided clock
  
  // 1a. Glitch-Free Multiplexer
  // Safely switches between multiple asynchronous FLL clock sources at runtime
  // without introducing clock glitches or short pulses.
  % if dom.has_mux:
  ${require_file("olli_clk_mux_glitch_free.sv")}
  olli_clk_mux_glitch_free #(
    .NUM_INPUTS(${config.clock_tree.generators if config.clock_tree.generators > 0 else 1})
  ) i_${dom.name}_mux (
    .clks_i       ( ${"domain_clk_i" if config.clock_tree.generators > 0 else "clk_i"} ),
    .test_clk_i   ( 1'b0 ),
    .test_en_i    ( 1'b0 ),
    .async_rstn_i ( host_pwr_on_rst_n ),
    <%
      num_gen = config.clock_tree.generators if config.clock_tree.generators > 0 else 1
      import math
      sel_width = max(1, math.ceil(math.log2(num_gen)))
    %>
    .async_sel_i  ( ${sel_width}'(sys_regs_hwif_out.${fmt_reg(dom.name)}_clk_sel.${fmt_reg(dom.name)}_clk_sel.value) ),
    .clk_o        ( ${dom.name}_muxed )
  );
  % else:
  // No mux required; hardwired to FLL ${dom.source_gen if dom.source_gen is not None else "default"}.
  assign ${dom.name}_muxed = ${f"domain_clk_i[{dom.source_gen}]" if config.clock_tree.generators > 0 and dom.source_gen is not None else "clk_i"};
  % endif

  // 1b. Configurable/Static Integer Divider & Clock Gating
  % if dom.has_divider:
  logic [DomainClkDivValueWidth-1:0] ${dom.name}_div_value, ${dom.name}_div_synced;
  logic ${dom.name}_div_valid, ${dom.name}_div_ready, ${dom.name}_div_valid_synced, ${dom.name}_div_ready_synced;
  
  // Decouples the static CSR register output into a valid/ready handshake stream.
  // This ensures that division ratio updates are cleanly propagated to the CDC.
  ${require_file("olli_lossy_valid_to_stream.sv")}
  olli_lossy_valid_to_stream #(
    .DATA_WIDTH(DomainClkDivValueWidth),
    .T(logic [DomainClkDivValueWidth-1:0])
  ) i_${dom.name}_decouple (
    .clk_i   ( ${host_clk} ),
    .rst_ni  ( host_pwr_on_rst_n ),
    .valid_i ( sys_regs_hwif_out.${fmt_reg(dom.name)}_clk_div_value.${fmt_reg(dom.name)}_clk_div_value.swmod ),
    .data_i  ( DomainClkDivValueWidth'(sys_regs_hwif_out.${fmt_reg(dom.name)}_clk_div_value.${fmt_reg(dom.name)}_clk_div_value.value) ),
    .valid_o ( ${dom.name}_div_valid ),
    .ready_i ( ${dom.name}_div_ready ),
    .data_o  ( ${dom.name}_div_value ),
    .busy_o  ( )
  );

  // Safely crosses the division ratio configuration from the host clock domain 
  // (where the CSRs live) to the target clock domain to avoid metastable states.
  ${require_file("olli_cdc_4phase.sv")}
  olli_cdc_4phase #(
    .T(logic [DomainClkDivValueWidth-1:0])
  ) i_${dom.name}_cdc (
    .src_rst_ni  ( host_pwr_on_rst_n ),
    .src_clk_i   ( ${host_clk} ),
    .src_data_i  ( ${dom.name}_div_value ),
    .src_valid_i ( ${dom.name}_div_valid ),
    .src_ready_o ( ${dom.name}_div_ready ),
    .dst_rst_ni  ( pwr_on_rsts_n[DomainIdx_${fmt_dom(dom.name)}] ),
    .dst_clk_i   ( ${dom.name}_muxed ),
    .dst_data_o  ( ${dom.name}_div_synced ),
    .dst_valid_o ( ${dom.name}_div_valid_synced ),
    .dst_ready_i ( ${dom.name}_div_ready_synced )
  );

  // The actual integer divider and clock gating block.
  ${require_file("olli_clk_int_div.sv")}
  olli_clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(${dom.default_div}),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_div (
    .clk_i          ( ${dom.name}_muxed ),
    .rst_ni         ( pwr_on_rsts_n[DomainIdx_${fmt_dom(dom.name)}] ),
    .en_i           ( sys_regs_hwif_out.${fmt_reg(dom.name)}_clk_en.${fmt_reg(dom.name)}_clk_en.value ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( ${dom.name}_div_synced ),
    .div_valid_i    ( ${dom.name}_div_valid_synced ),
    .div_ready_o    ( ${dom.name}_div_ready_synced ),
    .clk_o          ( ${dom.name} ),
    .cycl_count_o   ( )
  );
  % elif dom.static_div is not None and dom.static_div > 1:
  // Hardwired static divider (always enabled)
  ${require_file("olli_clk_int_div.sv")}
  olli_clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(${dom.static_div}),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_static_div (
    .clk_i          ( ${dom.name}_muxed ),
    .rst_ni         ( pwr_on_rsts_n[DomainIdx_${fmt_dom(dom.name)}] ),
    .en_i           ( 1'b1 ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( 24'd${dom.static_div} ),
    .div_valid_i    ( 1'b0 ),
    .div_ready_o    ( ),
    .clk_o          ( ${dom.name} ),
    .cycl_count_o   ( )
  );
  % else:
  // No divider required
  assign ${dom.name} = ${dom.name}_muxed;
  % endif
 % endif
 
  // 1c. Debug Divider
  // Generates a parallel, slower clock typically used for JTAG and Debug Module 
  // Interfaces. It is derived directly from the domain clock to remain synchronous.
 % if dom.has_debug_divider:
  logic ${dom.name}_debug;
  ${require_file("olli_clk_int_div.sv")}
  olli_clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(10),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_debug_div (
    .clk_i          ( ${dom.name} ),
    .rst_ni         ( host_pwr_on_rst_n ),
    .en_i           ( sys_regs_hwif_out.${fmt_reg(dom.name)}_debug_clk_en.${fmt_reg(dom.name)}_debug_clk_en.value ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( DomainClkDivValueWidth'(sys_regs_hwif_out.${fmt_reg(dom.name)}_debug_clk_div_value.${fmt_reg(dom.name)}_debug_clk_div_value.value) ),
    .div_valid_i    ( sys_regs_hwif_out.${fmt_reg(dom.name)}_debug_clk_div_value.${fmt_reg(dom.name)}_debug_clk_div_value.swmod ),
    .div_ready_o    ( ),
    .clk_o          ( ${dom.name}_debug ),
    .cycl_count_o   ( )
  );
 % endif

% endfor

  // =========================================================================
  // 2. SYSTEM RESETS
  // =========================================================================
  
  // Root Host Reset Generator
  // Synchronizes the external asynchronous Power-On Reset (POR) to the main host clock.
  // This acts as the root reset for the entire System Controller and host domain.
  ${require_file("olli_rstgen.sv")}
  olli_rstgen i_host_rstgen (
    .clk_i  ( ${host_clk} ),
    .rst_ni ( ${"pwr_on_rst_ni" if config.clock_tree.generators > 0 else "rst_ni"} ),
    .test_mode_i ( test_mode_i ),
    .rst_no ( host_pwr_on_rst_n ),
    .init_no ()
  );

% if num_managed_domains > 0:
  // Global Reset Tree
  // Generates safely synchronized resets for all other clock domains. It combines the
  // root Power-On Reset with the software-triggered resets driven by the CSRs,
  // ensuring a glitch-free, synchronous de-assertion for each specific clock domain.
  logic [NumDomains-1:0] sw_rsts_vector;

  // `<dom>_rst` is an active-high, single-bit software reset (1 = hold in reset), so
  // the bit is selected explicitly and inverted once to obtain the active-low input
  // expected by the reset generator.
 % for i, dom in enumerate(managed_domains):
  assign sw_rsts_vector[DomainIdx_${fmt_dom(dom.name)}] = sys_regs_hwif_out.${fmt_reg(dom.name)}_rst.${fmt_reg(dom.name)}_rst.value;
 % endfor

  ${p_name}_rstgen #(
    .NumRstDomains(NumDomains)
  ) i_sys_rstgen (
    .clks_i         ( { ${", ".join([f"{d.name}_muxed" if d.has_mux else f"{d.name}" for d in managed_domains])} } ),
    .pwr_on_rst_ni  ( ${"pwr_on_rst_ni" if config.clock_tree.generators > 0 else "rst_ni"} ),
    .sw_rsts_ni     ( ~sw_rsts_vector ),
    .test_mode_i    ( test_mode_i ),
    .rsts_no        ( rsts_n ),
    .pwr_on_rsts_no ( pwr_on_rsts_n ),
    .inits_no       ( )
  );
% endif

  // =========================================================================
  // 3. DEDICATED CLOCK DIVIDERS
  // =========================================================================
  // Independent clock dividers dedicated to specific IP interfaces that require 
  // highly constrained or non-standard frequencies (e.g., RGMII for Ethernet, 
  // or HyperBus PHYs). These bypass the standard global clock domains.
<%
  dedicated_divs = []
  for c in [config.host] + (config.components if config.components else []):
      if c.dedicated_clock_div:
          dedicated_divs.append((c, c.dedicated_clock_div))
%>
% for comp, div_cfg in dedicated_divs:
  <%
    div_clk = div_cfg['name']
    src_clk = comp.clock_domain or host_clk
    c_rst = comp.reset_domain or src_clk.replace('_clk', '_rst')
    src_rst = 'host_pwr_on_rst_n' if c_rst == host_clk.replace('_clk', '_rst') else f"pwr_on_rsts_n[DomainIdx_{fmt_rst(c_rst)}]"
  %>
  // --- Dedicated Divider: ${div_clk} for ${comp.name} ---
  logic ${div_clk};
  logic [DomainClkDivValueWidth-1:0] ${div_clk}_div_value, ${div_clk}_div_synced;
  logic ${div_clk}_div_valid, ${div_clk}_div_ready, ${div_clk}_div_valid_synced, ${div_clk}_div_ready_synced;
  
  // Decouples the static CSR register output into a valid/ready handshake stream.
  ${require_file("olli_lossy_valid_to_stream.sv")}
  olli_lossy_valid_to_stream #(
    .DATA_WIDTH(DomainClkDivValueWidth),
    .T(logic [DomainClkDivValueWidth-1:0])
  ) i_${div_clk}_decouple (
    .clk_i   ( ${host_clk} ),
    .rst_ni  ( host_pwr_on_rst_n ),
    .valid_i ( sys_regs_hwif_out.${fmt_reg(div_clk)}_clk_div_value.${fmt_reg(div_clk)}_clk_div_value.swmod ),
    .data_i  ( DomainClkDivValueWidth'(sys_regs_hwif_out.${fmt_reg(div_clk)}_clk_div_value.${fmt_reg(div_clk)}_clk_div_value.value) ),
    .valid_o ( ${div_clk}_div_valid ),
    .ready_i ( ${div_clk}_div_ready ),
    .data_o  ( ${div_clk}_div_value ),
    .busy_o  ( )
  );

  // Safely crosses the configuration from the host domain to the local clock domain.
  ${require_file("olli_cdc_4phase.sv")}
  olli_cdc_4phase #(
    .T(logic [DomainClkDivValueWidth-1:0])
  ) i_${div_clk}_cdc (
    .src_rst_ni  ( host_pwr_on_rst_n ),
    .src_clk_i   ( ${host_clk} ),
    .src_data_i  ( ${div_clk}_div_value ),
    .src_valid_i ( ${div_clk}_div_valid ),
    .src_ready_o ( ${div_clk}_div_ready ),
    .dst_rst_ni  ( ${src_rst} ),
    .dst_clk_i   ( ${src_clk} ),
    .dst_data_o  ( ${div_clk}_div_synced ),
    .dst_valid_o ( ${div_clk}_div_valid_synced ),
    .dst_ready_i ( ${div_clk}_div_ready_synced )
  );

  // Dedicated integer divider and clock gating instance.
  ${require_file("olli_clk_int_div.sv")}
  olli_clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(${div_cfg.get('default_div', 1)}),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${div_clk}_div (
    .clk_i          ( ${src_clk} ),
    .rst_ni         ( ${src_rst} ),
    .en_i           ( sys_regs_hwif_out.${fmt_reg(div_clk)}_clk_en.${fmt_reg(div_clk)}_clk_en.value ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( ${div_clk}_div_synced ),
    .div_valid_i    ( ${div_clk}_div_valid_synced ),
    .div_ready_o    ( ${div_clk}_div_ready_synced ),
    .clk_o          ( ${div_clk} ),
    .cycl_count_o   ( )
  );
% endfor
</%def>

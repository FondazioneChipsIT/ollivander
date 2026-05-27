<%def name="clock_and_reset_tree(config, p_name)">
<%
  host_clk = config.host.clock_domain or "system_clk"
  managed_domains = [d for d in config.clock_tree.domains if not d.is_real_time and d.name != host_clk]
  num_managed_domains = len(managed_domains)
%>
  // BENDER: name="common_cells"

  localparam int unsigned DomainClkDivValueWidth = 24;
  localparam int unsigned NumDomains = ${num_managed_domains if num_managed_domains > 0 else 1};

% for i, dom in enumerate(managed_domains):
  localparam int unsigned DomainIdx_${fmt_dom(dom.name)} = ${i};
% endfor

% for dom in config.clock_tree.domains:
  // --- Domain: ${dom.name} ---
 % if dom.is_real_time:
  logic ${dom.name};
  assign ${dom.name} = ${f"domain_clk_i[{dom.source_fll}]" if config.clock_tree.flls > 0 and dom.source_fll is not None else "rtc_i"};
 % else:
  logic ${dom.name}_muxed;
  logic ${dom.name}; // Final gated/divided clock
  
  // Multiplexer
  % if dom.has_mux:
  ${require_file("clk_mux_glitch_free.sv")}
  clk_mux_glitch_free #(
    .NUM_INPUTS(${config.clock_tree.flls if config.clock_tree.flls > 0 else 1})
  ) i_${dom.name}_mux (
    .clks_i       ( ${"domain_clk_i" if config.clock_tree.flls > 0 else "clk_i"} ),
    .test_clk_i   ( 1'b0 ),
    .test_en_i    ( 1'b0 ),
    .async_rstn_i ( host_pwr_on_rst_n ),
    .async_sel_i  ( sys_regs_reg2hw.${fmt_reg(dom.name)}_clk_sel.q ),
    .clk_o        ( ${dom.name}_muxed )
  );
  % else:
  assign ${dom.name}_muxed = ${f"domain_clk_i[{dom.source_fll}]" if config.clock_tree.flls > 0 and dom.source_fll is not None else "clk_i"};
  % endif

  // Divider
  % if dom.has_divider:
  logic [DomainClkDivValueWidth-1:0] ${dom.name}_div_value, ${dom.name}_div_synced;
  logic ${dom.name}_div_valid, ${dom.name}_div_ready, ${dom.name}_div_valid_synced, ${dom.name}_div_ready_synced;
  
  ${require_file("lossy_valid_to_stream.sv")}
  lossy_valid_to_stream #(
    .T(logic [DomainClkDivValueWidth-1:0])
  ) i_${dom.name}_decouple (
    .clk_i   ( ${host_clk} ),
    .rst_ni  ( host_pwr_on_rst_n ),
    .valid_i ( sys_regs_reg2hw.${fmt_reg(dom.name)}_clk_div_value.qe ),
    .data_i  ( sys_regs_reg2hw.${fmt_reg(dom.name)}_clk_div_value.q ),
    .valid_o ( ${dom.name}_div_valid ),
    .ready_i ( ${dom.name}_div_ready ),
    .data_o  ( ${dom.name}_div_value ),
    .busy_o  ( )
  );

  ${require_file("cdc_4phase.sv")}
  cdc_4phase #(
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

  ${require_file("clk_int_div.sv")}
  clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(${dom.default_div}),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_div (
    .clk_i          ( ${dom.name}_muxed ),
    .rst_ni         ( pwr_on_rsts_n[DomainIdx_${fmt_dom(dom.name)}] ),
    .en_i           ( sys_regs_reg2hw.${fmt_reg(dom.name)}_clk_en.q ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( ${dom.name}_div_synced ),
    .div_valid_i    ( ${dom.name}_div_valid_synced ),
    .div_ready_o    ( ${dom.name}_div_ready_synced ),
    .clk_o          ( ${dom.name} ),
    .cycl_count_o   ( )
  );
  % else:
  assign ${dom.name} = ${dom.name}_muxed;
  % endif
 % endif
 
  // Debug Divider
 % if dom.has_debug_divider:
  logic ${dom.name}_debug;
  ${require_file("clk_int_div.sv")}
  clk_int_div #(
    .DIV_VALUE_WIDTH(DomainClkDivValueWidth),
    .DEFAULT_DIV_VALUE(10),
    .ENABLE_CLOCK_IN_RESET(1)
  ) i_${dom.name}_debug_div (
    .clk_i          ( ${dom.name} ),
    .rst_ni         ( host_pwr_on_rst_n ),
    .en_i           ( sys_regs_reg2hw.${fmt_reg(dom.name)}_debug_clk_en.q ),
    .test_mode_en_i ( test_mode_i ),
    .div_i          ( sys_regs_reg2hw.${fmt_reg(dom.name)}_debug_clk_div_value.q ),
    .div_valid_i    ( sys_regs_reg2hw.${fmt_reg(dom.name)}_debug_clk_div_value.qe ),
    .div_ready_o    ( ),
    .clk_o          ( ${dom.name}_debug ),
    .cycl_count_o   ( )
  );
 % endif

% endfor

  // =========================================================================
  // SYSTEM RESETS
  // =========================================================================
  rstgen i_host_rstgen (
    .clk_i  ( ${host_clk} ),
    .rst_ni ( ${"pwr_on_rst_ni" if config.clock_tree.flls > 0 else "rst_ni"} ),
    .test_mode_i ( test_mode_i ),
    .rst_no ( host_pwr_on_rst_n ),
    .init_no ()
  );

% if num_managed_domains > 0:
  logic [NumDomains-1:0] sw_rsts_vector;
  
 % for i, dom in enumerate(managed_domains):
  assign sw_rsts_vector[DomainIdx_${fmt_dom(dom.name)}] = sys_regs_reg2hw.${fmt_reg(dom.name)}_rst.q;
 % endfor

  ${p_name}_rstgen #(
    .NumRstDomains(NumDomains)
  ) i_sys_rstgen (
    .clks_i         ( { ${", ".join([f"{d.name}_muxed" if d.has_mux else f"{d.name}" for d in managed_domains])} } ),
    .pwr_on_rst_ni  ( ${"pwr_on_rst_ni" if config.clock_tree.flls > 0 else "rst_ni"} ),
    .sw_rsts_ni     ( ~sw_rsts_vector ),
    .test_mode_i    ( test_mode_i ),
    .rsts_no        ( rsts_n ),
    .pwr_on_rsts_no ( pwr_on_rsts_n ),
    .inits_no       ( )
  );
% endif
</%def>
// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Glitch-Free Clock Multiplexer.
// The user is required to implement the logic to safely switch between
// multiple asynchronous clock sources without producing runt pulses.
//
// BENDER: name="common_cells"

module olli_clk_mux_glitch_free #(
  parameter int unsigned NUM_INPUTS = 2,
  parameter int unsigned NUM_SYNC_STAGES = 2,
  parameter bit          CLOCK_DURING_RESET = 1'b1
) (
  input  logic [NUM_INPUTS-1:0]           clks_i,
  input  logic                            test_clk_i,
  input  logic                            test_en_i,
  input  logic                            async_rstn_i,
  input  logic [$clog2(NUM_INPUTS)-1:0]   async_sel_i,
  output logic                            clk_o
);

`ifndef TARGET_SYNTHESIS
  if (NUM_INPUTS >= 2) begin : gen_sim_mux
    // Simulation: use common_cells behavioral model
    clk_mux_glitch_free #(
      .NUM_INPUTS         ( NUM_INPUTS ),
      .NUM_SYNC_STAGES    ( NUM_SYNC_STAGES ),
      .CLOCK_DURING_RESET ( CLOCK_DURING_RESET )
    ) i_sim_mux (
      .clks_i       ( clks_i ),
      .test_clk_i   ( test_clk_i ),
      .test_en_i    ( test_en_i ),
      .async_rstn_i ( async_rstn_i ),
      .async_sel_i  ( async_sel_i ),
      .clk_o        ( clk_o )
    );
  end else begin : gen_bypass
    assign clk_o = clks_i[0];
  end
`else
  // Synthesis: instantiate foundry-specific standard cell here
  // (e.g., tsmc_clk_mux2)
`endif

endmodule

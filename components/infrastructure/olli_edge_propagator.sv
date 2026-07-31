// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Edge-to-Level CDC Propagator.
// The user is required to implement the logic to capture a short pulse (edge) 
// in the source clock domain, safely cross it to the destination clock domain, 
// and output it as a stable level-sensitive signal.
//
// BENDER: name="common_cells"

module olli_edge_propagator (
  input  logic clk_tx_i,
  input  logic rstn_tx_i,
  input  logic edge_i,
  
  input  logic clk_rx_i,
  input  logic rstn_rx_i,
  output logic edge_o
);

`ifndef TARGET_SYNTHESIS
  // Simulation: use common_cells behavioral model
  edge_propagator i_sim_edge_prop (
    .clk_tx_i  ( clk_tx_i ),
    .rstn_tx_i ( rstn_tx_i ),
    .edge_i    ( edge_i ),
    .clk_rx_i  ( clk_rx_i ),
    .rstn_rx_i ( rstn_rx_i ),
    .edge_o    ( edge_o )
  );
`else
  // Synthesis: instantiate foundry-specific CDC macro here
`endif

endmodule

// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Lossy Valid-to-Stream Adapter.
// The user is required to implement the logic to convert a static valid signal
// into a valid/ready stream, dropping intermediate values if the downstream
// logic is not ready.
//
// BENDER: name="common_cells"

module olli_lossy_valid_to_stream #(
  parameter int unsigned DATA_WIDTH = 32,
  parameter type T = logic [DATA_WIDTH-1:0]
) (
  input  logic    clk_i,
  input  logic    rst_ni,
  input  logic    valid_i,
  input  T        data_i,
  output logic    valid_o,
  input  logic    ready_i,
  output T        data_o,
  output logic    busy_o
);

`ifndef TARGET_SYNTHESIS
  // Simulation: use common_cells behavioral model
  lossy_valid_to_stream #(
    .DATA_WIDTH ( DATA_WIDTH ),
    .T          ( T )
  ) i_sim_lossy_valid_to_stream (
    .clk_i   ( clk_i ),
    .rst_ni  ( rst_ni ),
    .valid_i ( valid_i ),
    .data_i  ( data_i ),
    .valid_o ( valid_o ),
    .ready_i ( ready_i ),
    .data_o  ( data_o ),
    .busy_o  ( busy_o )
  );
`else
  // For synthesis, instantiate custom IP or foundry macro here
`endif

endmodule

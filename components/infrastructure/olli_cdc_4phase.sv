// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the 4-Phase Handshake CDC.
// The user is required to implement the logic to safely transfer multi-bit
// data between two asynchronous clock domains.
//
// BENDER: name="common_cells"

module olli_cdc_4phase #(
  parameter type T = logic,
  parameter bit DECOUPLED = 1'b1,
  parameter bit SEND_RESET_MSG = 1'b0,
  parameter T RESET_MSG = T'('0)
) (
  input  logic    src_rst_ni,
  input  logic    src_clk_i,
  input  T        src_data_i,
  input  logic    src_valid_i,
  output logic    src_ready_o,
  input  logic    dst_rst_ni,
  input  logic    dst_clk_i,
  output T        dst_data_o,
  output logic    dst_valid_o,
  input  logic    dst_ready_i
);

`ifndef TARGET_SYNTHESIS
  // Simulation: use common_cells behavioral model
  cdc_4phase #(
    .T              ( T ),
    .DECOUPLED      ( DECOUPLED ),
    .SEND_RESET_MSG ( SEND_RESET_MSG ),
    .RESET_MSG      ( RESET_MSG )
  ) i_sim_cdc_4phase (
    .src_rst_ni  ( src_rst_ni ),
    .src_clk_i   ( src_clk_i ),
    .src_data_i  ( src_data_i ),
    .src_valid_i ( src_valid_i ),
    .src_ready_o ( src_ready_o ),
    .dst_rst_ni  ( dst_rst_ni ),
    .dst_clk_i   ( dst_clk_i ),
    .dst_data_o  ( dst_data_o ),
    .dst_valid_o ( dst_valid_o ),
    .dst_ready_i ( dst_ready_i )
  );
`else
  // Synthesis: instantiate foundry-specific standard cell here
`endif

endmodule
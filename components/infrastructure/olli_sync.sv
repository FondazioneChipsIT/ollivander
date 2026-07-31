// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Multi-Stage Bit Synchronizer.
// The user is required to implement a chain of flip-flops to safely
// transfer a 1-bit signal between asynchronous clock domains.
//
// BENDER: name="common_cells"

module olli_sync #(
  parameter int unsigned STAGES = 2,
  parameter bit ResetValue = 1'b0
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic serial_i,
  output logic serial_o
);

`ifndef TARGET_SYNTHESIS
  // Simulation: use common_cells behavioral model
  sync #(
    .STAGES     ( STAGES ),
    .ResetValue ( ResetValue )
  ) i_sim_sync (
    .clk_i    ( clk_i ),
    .rst_ni   ( rst_ni ),
    .serial_i ( serial_i ),
    .serial_o ( serial_o )
  );
`else
  // Synthesis: instantiate foundry-specific standard cell here
`endif

endmodule

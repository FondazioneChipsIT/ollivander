// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Multi-Stage Bit Synchronizer.
// The user is required to implement a chain of flip-flops to safely
// transfer a 1-bit signal between asynchronous clock domains.

module sync #(
  parameter int STAGES = 3,
  parameter logic ResetValue = 1'b0
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic serial_i,
  output logic serial_o
);

  // TODO: Implement multi-stage synchronizer logic.

endmodule
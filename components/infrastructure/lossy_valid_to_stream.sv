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

module lossy_valid_to_stream #(
  parameter type T = logic
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

  // TODO: Implement lossy valid-to-stream adapter logic.

endmodule
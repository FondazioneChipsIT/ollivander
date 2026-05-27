// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Standard Reset Generator.
// The user is required to implement the logic to synchronize an asynchronous
// reset into a specific clock domain, ensuring a synchronous de-assertion.

module rstgen (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic test_mode_i,
  output logic rst_no,
  output logic init_no
);

  // TODO: Implement reset synchronizer logic.

endmodule
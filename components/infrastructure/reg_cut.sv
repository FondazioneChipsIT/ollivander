// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Register Bus Pipeline Cut.
// The user is required to implement the logic to insert a pipeline stage
// (flip-flops) on the request and response channels of the RegBus to break
// long combinatorial paths.

module reg_cut #(
  parameter type req_t = logic,
  parameter type rsp_t = logic
) (
  input  logic  clk_i,
  input  logic  rst_ni,
  input  req_t  src_req_i,
  output rsp_t  src_rsp_o,
  output req_t  dst_req_o,
  input  rsp_t  dst_rsp_i
);

  // TODO: Implement RegBus pipeline cut logic.

endmodule
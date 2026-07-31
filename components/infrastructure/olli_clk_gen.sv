// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This module encapsulates the physical PLLs/FLLs/DLLs.
// By default, it provides a behavioral bypass for RTL simulation.
// Replace the behavioral section with your foundry-specific hard macros for synthesis.

module olli_clk_gen #(
  parameter int unsigned NUM_CLOCKS = 1,
  parameter type reg_req_t = logic,
  parameter type reg_rsp_t = logic
) (
  input  logic                    ref_clk_i,
  output logic [NUM_CLOCKS-1:0]   clk_o,
  output logic [NUM_CLOCKS-1:0]   lock_o,

  // Configuration interface (RegBus Async Slave)
  input  logic                    cfg_req_i,
  output logic                    cfg_ack_o,
  input  reg_req_t                cfg_data_i,
  output logic                    cfg_req_o,
  input  logic                    cfg_ack_i,
  output reg_rsp_t                cfg_data_o
);

`ifndef TARGET_SYNTHESIS
  // =====================================================================
  // BEHAVIORAL SIMULATION MODEL
  // =====================================================================
  // Simple bypass of the reference clock to all domains.
  // Assumes instantaneous lock.
  
  assign clk_o  = {NUM_CLOCKS{ref_clk_i}};
  assign lock_o = '1;

  // Dummy RegBus response to avoid stalling the system if accessed
  assign cfg_ack_o = cfg_req_i;
  assign cfg_req_o = cfg_req_i;
  assign cfg_data_o.ready = 1'b1;
  assign cfg_data_o.error = 1'b0;
  assign cfg_data_o.rdata = '0;
`else
  // TODO: Instantiate your foundry-specific PLL/FLL macros here!
`endif

endmodule

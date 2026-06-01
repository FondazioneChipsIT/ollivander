// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// RegBus to TL-UL Adapter for OpenTitan register blocks
//
// This module bridges the standard RegBus protocol (widely used in PULP and 
// Ollivander-generated architectures) to the TileLink Uncached Lightweight (TL-UL) 
// protocol natively required by OpenTitan peripherals.
// It translates RegBus reads/writes into TL-UL Get/PutFullData operations 
// using a straightforward 2-state Finite State Machine (FSM).
//
// BENDER: name="opentitan"

module reg_to_tlul #(
  // Type definitions for the standard RegBus payload
  parameter type reg_req_t = logic,
  parameter type reg_rsp_t = logic,
  // Type definitions for the TileLink Uncached Lightweight (TL-UL) payload
  parameter type tl_h2d_t  = logic,
  parameter type tl_d2h_t  = logic
) (
  input  logic     clk_i,
  input  logic     rst_ni,
  input  reg_req_t reg_req_i,
  output reg_rsp_t reg_rsp_o,
  output tl_h2d_t  tl_o,
  input  tl_d2h_t  tl_i
);

  import tlul_pkg::*;

  // ---------------------------------------------------------------------------
  // FSM State Definition
  // ---------------------------------------------------------------------------
  typedef enum logic { TL_IDLE, TL_WAIT_RSP } tl_state_e;
  tl_state_e tl_state_q, tl_state_d;

  // ---------------------------------------------------------------------------
  // Combinational Logic: FSM and Protocol Translation
  // ---------------------------------------------------------------------------
  always_comb begin
    tl_state_d = tl_state_q;
    
    // Default assignments for TileLink Host-to-Device (H2D) channel
    tl_o       = '0;
    tl_o.a_valid = 1'b0;
    tl_o.d_ready = 1'b1; // We are always ready to accept the response
    
    // Default assignments for RegBus Response channel
    reg_rsp_o  = '0;

    case (tl_state_q)
      TL_IDLE: begin
        // Wait for a valid RegBus request to arrive
        if (reg_req_i.valid) begin
          tl_o.a_valid   = 1'b1;
          tl_o.a_opcode  = reg_req_i.write ? PutFullData : Get; // Map command type
          tl_o.a_address = reg_req_i.addr[31:0];
          tl_o.a_mask    = reg_req_i.wstrb;
          tl_o.a_data    = reg_req_i.wdata;
          tl_o.a_size    = 2'h2; // Fixed to 4-byte (32-bit) operations for standard CSRs

          // If the TL-UL device acknowledges the request, move to the wait state
          if (tl_i.a_ready) begin
            tl_state_d = TL_WAIT_RSP;
          end
        end
      end
      TL_WAIT_RSP: begin
        // Wait for the TL-UL device to return the response on the Device-to-Host channel
        if (tl_i.d_valid) begin
          reg_rsp_o.ready = 1'b1;
          reg_rsp_o.rdata = tl_i.d_data;
          reg_rsp_o.error = tl_i.d_error; // Forward any TileLink errors back to RegBus
          tl_state_d = TL_IDLE;
        end
      end
      default: tl_state_d = TL_IDLE;
    endcase
  end

  // ---------------------------------------------------------------------------
  // Sequential Logic: FSM state update
  // ---------------------------------------------------------------------------
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) tl_state_q <= TL_IDLE;
    else         tl_state_q <= tl_state_d;
  end

endmodule
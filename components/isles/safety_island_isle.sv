// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the Safety Island
//
// BENDER: name="safety_island"
// BENDER: name="axi"

`include "axi/typedef.svh"

module safety_island_isle
  import axi_pkg::*;
#(
  // Geometry of the SoC this isle is attached to, driven by the generator at
  // instantiation (rtl_ir_builder.py): AxiInIdWidth receives the crossbar's slave-side
  // ID width (ExtSlvIdWidth), AxiOutIdWidth its manager-side AxiIdWidth. These were
  // localparams frozen at the values astral's carfield computes for itself, and the
  // SoC around them had moved: this crossbar presents a 6-bit slave-side ID where the
  // frozen value said 5, and the generated connection was sliced to fit - which
  // misaligns every CDC packet after the first, not just the ID. The wrapped
  // safety_island_synth_wrapper takes all of these as parameters (astral drives them
  // the same way, carfield.sv), so nothing here is fixed.
  parameter int unsigned AxiAddrWidth       = 48,
  parameter int unsigned AxiDataWidth       = 64,
  parameter int unsigned AxiUserWidth       = 10,
  parameter int unsigned AxiInIdWidth       = 5,
  parameter int unsigned AxiOutIdWidth      = 2,
  parameter int unsigned LogDepth           = 3,
  // AXI user-field mapping, driven from the SoC package. The island marks its atomics
  // over these bits; its synth default (msb 3) is one bit wider than this SoC's
  // mapping (msb 2), so leaving it undriven would raise a user bit nothing else reads.
  parameter int unsigned AxiUserAmoMsb      = 2,
  parameter int unsigned AxiUserAmoLsb      = 0,
  parameter int unsigned AxiUserEccErrBit   = 4,
  localparam int unsigned NumInterrupts      = 128,
  localparam int unsigned NumDebug           = 96,
  // Async AXI IN (Slave Port)
  localparam int unsigned AsyncAxiInAwWidth  = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, AxiInIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiInWWidth   = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiInBWidth   = (2**LogDepth)*axi_pkg::b_width(AxiInIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiInArWidth  = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, AxiInIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiInRWidth   = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, AxiInIdWidth, AxiUserWidth),
  // Async AXI OUT (Master Port)
  localparam int unsigned AsyncAxiOutAwWidth = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutWWidth  = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutBWidth  = (2**LogDepth)*axi_pkg::b_width(AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutArWidth = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutRWidth  = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, AxiOutIdWidth, AxiUserWidth)
) (
  input  logic clk_i,
  input  logic rt_clk_i,
  input  logic rst_ni,
  input  logic pwr_on_rst_ni,
  input  logic test_mode_i,
  
  // Control and Status
  input  logic [1:0]  boot_mode_i,
  input  logic        fetch_en_i,
  input  logic        axi_isolate_i,
  output logic        axi_isolated_o,
  
  // Interrupts and Debug
  input  logic [NumInterrupts-1:0] irqs_i,
  output logic [NumDebug-1:0]      debug_req_o,
  
  // JTAG
  input  logic jtag_tck_i,
  input  logic jtag_trst_ni,
  input  logic jtag_tms_i,
  input  logic jtag_tdi_i,
  output logic jtag_tdo_o,
  
  // Standard AXI IN (Slave)
  input  logic [AsyncAxiInAwWidth-1:0] async_axi_in_aw_data_i,
  input  logic            [LogDepth:0] async_axi_in_aw_wptr_i,
  output logic            [LogDepth:0] async_axi_in_aw_rptr_o,
  input  logic [ AsyncAxiInWWidth-1:0] async_axi_in_w_data_i,
  input  logic            [LogDepth:0] async_axi_in_w_wptr_i,
  output logic            [LogDepth:0] async_axi_in_w_rptr_o,
  output logic [ AsyncAxiInBWidth-1:0] async_axi_in_b_data_o,
  output logic            [LogDepth:0] async_axi_in_b_wptr_o,
  input  logic            [LogDepth:0] async_axi_in_b_rptr_i,
  input  logic [AsyncAxiInArWidth-1:0] async_axi_in_ar_data_i,
  input  logic            [LogDepth:0] async_axi_in_ar_wptr_i,
  output logic            [LogDepth:0] async_axi_in_ar_rptr_o,
  output logic [ AsyncAxiInRWidth-1:0] async_axi_in_r_data_o,
  output logic            [LogDepth:0] async_axi_in_r_wptr_o,
  input  logic            [LogDepth:0] async_axi_in_r_rptr_i,

  // Standard AXI OUT (Master)
  output logic [AsyncAxiOutAwWidth-1:0] async_axi_out_aw_data_o,
  output logic             [LogDepth:0] async_axi_out_aw_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_aw_rptr_i,
  output logic [ AsyncAxiOutWWidth-1:0] async_axi_out_w_data_o,
  output logic             [LogDepth:0] async_axi_out_w_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_w_rptr_i,
  input  logic [ AsyncAxiOutBWidth-1:0] async_axi_out_b_data_i,
  input  logic             [LogDepth:0] async_axi_out_b_wptr_i,
  output logic             [LogDepth:0] async_axi_out_b_rptr_o,
  output logic [AsyncAxiOutArWidth-1:0] async_axi_out_ar_data_o,
  output logic             [LogDepth:0] async_axi_out_ar_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_ar_rptr_i,
  input  logic [ AsyncAxiOutRWidth-1:0] async_axi_out_r_data_i,
  input  logic             [LogDepth:0] async_axi_out_r_wptr_i,
  output logic             [LogDepth:0] async_axi_out_r_rptr_o
);

  // AXI channel types built from the isle's own parameters. The wrapper's type
  // parameters default to its synth-package types, which are frozen at the synth
  // geometry: without these, widening AxiInIdWidth would resize the flattened CDC
  // ports but not the structs travelling inside them.
  typedef logic [AxiAddrWidth-1:0]   isle_addr_t;
  typedef logic [AxiDataWidth-1:0]   isle_data_t;
  typedef logic [AxiDataWidth/8-1:0] isle_strb_t;
  typedef logic [AxiUserWidth-1:0]   isle_user_t;
  typedef logic [AxiInIdWidth-1:0]   isle_in_id_t;
  typedef logic [AxiOutIdWidth-1:0]  isle_out_id_t;
  `AXI_TYPEDEF_ALL(isle_axi_in, isle_addr_t, isle_in_id_t, isle_data_t, isle_strb_t, isle_user_t)
  `AXI_TYPEDEF_ALL(isle_axi_out, isle_addr_t, isle_out_id_t, isle_data_t, isle_strb_t, isle_user_t)

  // The geometry, the user mapping and the channel types are all propagated: the
  // wrapper is fully parametric, and every default it would fall back to describes the
  // synth context it ships with, not this SoC. The base address and range keep their
  // defaults on purpose - they match this SoC's memory map, and the map is owned by
  // the SoC description, not by this shell.
  safety_island_synth_wrapper #(
    .AxiAddrWidth       ( AxiAddrWidth     ),
    .AxiDataWidth       ( AxiDataWidth     ),
    .AxiUserWidth       ( AxiUserWidth     ),
    .AxiInIdWidth       ( AxiInIdWidth     ),
    .AxiOutIdWidth      ( AxiOutIdWidth    ),
    .AxiUserAtopMsb     ( AxiUserAmoMsb    ),
    .AxiUserAtopLsb     ( AxiUserAmoLsb    ),
    .AxiUserEccErrBit   ( AxiUserEccErrBit ),
    .LogDepth           ( LogDepth         ),
    .axi_in_aw_chan_t   ( isle_axi_in_aw_chan_t  ),
    .axi_in_w_chan_t    ( isle_axi_in_w_chan_t   ),
    .axi_in_b_chan_t    ( isle_axi_in_b_chan_t   ),
    .axi_in_ar_chan_t   ( isle_axi_in_ar_chan_t  ),
    .axi_in_r_chan_t    ( isle_axi_in_r_chan_t   ),
    .axi_in_req_t       ( isle_axi_in_req_t      ),
    .axi_in_resp_t      ( isle_axi_in_resp_t     ),
    .axi_out_aw_chan_t  ( isle_axi_out_aw_chan_t ),
    .axi_out_w_chan_t   ( isle_axi_out_w_chan_t  ),
    .axi_out_b_chan_t   ( isle_axi_out_b_chan_t  ),
    .axi_out_ar_chan_t  ( isle_axi_out_ar_chan_t ),
    .axi_out_r_chan_t   ( isle_axi_out_r_chan_t  ),
    .axi_out_req_t      ( isle_axi_out_req_t     ),
    .axi_out_resp_t     ( isle_axi_out_resp_t    ),
    .AsyncAxiInAwWidth  ( AsyncAxiInAwWidth  ),
    .AsyncAxiInWWidth   ( AsyncAxiInWWidth   ),
    .AsyncAxiInBWidth   ( AsyncAxiInBWidth   ),
    .AsyncAxiInArWidth  ( AsyncAxiInArWidth  ),
    .AsyncAxiInRWidth   ( AsyncAxiInRWidth   ),
    .AsyncAxiOutAwWidth ( AsyncAxiOutAwWidth ),
    .AsyncAxiOutWWidth  ( AsyncAxiOutWWidth  ),
    .AsyncAxiOutBWidth  ( AsyncAxiOutBWidth  ),
    .AsyncAxiOutArWidth ( AsyncAxiOutArWidth ),
    .AsyncAxiOutRWidth  ( AsyncAxiOutRWidth  )
  ) i_safety_island_synth_wrapper (
    .clk_i                       ( clk_i           ),
    .ref_clk_i                   ( rt_clk_i        ),
    .rst_ni                      ( rst_ni          ),
    .pwr_on_rst_ni               ( pwr_on_rst_ni   ),
    .test_enable_i               ( test_mode_i     ),
    .bootmode_i                  ( boot_mode_i     ),
    .fetch_en_i                  ( fetch_en_i      ),
    .axi_isolate_i               ( axi_isolate_i   ),
    .axi_isolated_o              ( axi_isolated_o  ),
    
    .jtag_tck_i                  ( jtag_tck_i      ),
    .jtag_trst_ni                ( jtag_trst_ni    ),
    .jtag_tms_i                  ( jtag_tms_i      ),
    .jtag_tdi_i                  ( jtag_tdi_i      ),
    .jtag_tdo_o                  ( jtag_tdo_o      ),

    .irqs_i                      ( irqs_i[safety_island_pkg::SafetyIslandDefaultConfig.NumInterrupts-1:0] ),
    .debug_req_o                 ( debug_req_o     ),
    
    // Map to Ollivander standard AXI IN
    .async_axi_in_aw_wptr_i      ( async_axi_in_aw_wptr_i ),
    .async_axi_in_aw_data_i      ( async_axi_in_aw_data_i ),
    .async_axi_in_aw_rptr_o      ( async_axi_in_aw_rptr_o ),
    .async_axi_in_w_wptr_i       ( async_axi_in_w_wptr_i  ),
    .async_axi_in_w_data_i       ( async_axi_in_w_data_i  ),
    .async_axi_in_w_rptr_o       ( async_axi_in_w_rptr_o  ),
    .async_axi_in_b_wptr_o       ( async_axi_in_b_wptr_o  ),
    .async_axi_in_b_data_o       ( async_axi_in_b_data_o  ),
    .async_axi_in_b_rptr_i       ( async_axi_in_b_rptr_i  ),
    .async_axi_in_ar_wptr_i      ( async_axi_in_ar_wptr_i ),
    .async_axi_in_ar_data_i      ( async_axi_in_ar_data_i ),
    .async_axi_in_ar_rptr_o      ( async_axi_in_ar_rptr_o ),
    .async_axi_in_r_wptr_o       ( async_axi_in_r_wptr_o  ),
    .async_axi_in_r_data_o       ( async_axi_in_r_data_o  ),
    .async_axi_in_r_rptr_i       ( async_axi_in_r_rptr_i  ),

    // Map to Ollivander standard AXI OUT
    .async_axi_out_aw_wptr_o     ( async_axi_out_aw_wptr_o ),
    .async_axi_out_aw_data_o     ( async_axi_out_aw_data_o ),
    .async_axi_out_aw_rptr_i     ( async_axi_out_aw_rptr_i ),
    .async_axi_out_w_wptr_o      ( async_axi_out_w_wptr_o  ),
    .async_axi_out_w_data_o      ( async_axi_out_w_data_o  ),
    .async_axi_out_w_rptr_i      ( async_axi_out_w_rptr_i  ),
    .async_axi_out_b_wptr_i      ( async_axi_out_b_wptr_i  ),
    .async_axi_out_b_data_i      ( async_axi_out_b_data_i  ),
    .async_axi_out_b_rptr_o      ( async_axi_out_b_rptr_o  ),
    .async_axi_out_ar_wptr_o     ( async_axi_out_ar_wptr_o ),
    .async_axi_out_ar_data_o     ( async_axi_out_ar_data_o ),
    .async_axi_out_ar_rptr_i     ( async_axi_out_ar_rptr_i ),
    .async_axi_out_r_wptr_i      ( async_axi_out_r_wptr_i  ),
    .async_axi_out_r_data_i      ( async_axi_out_r_data_i  ),
    .async_axi_out_r_rptr_o      ( async_axi_out_r_rptr_o  )
  );

endmodule : safety_island_isle

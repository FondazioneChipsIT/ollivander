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
  localparam int unsigned AxiAddrWidth       = 48,
  localparam int unsigned AxiDataWidth       = 64,
  localparam int unsigned AxiUserWidth       = 10,
  localparam int unsigned AxiInIdWidth       = 5,
  localparam int unsigned AxiOutIdWidth      = 2,
  localparam int unsigned LogDepth           = 3,
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

  // =================================================================================
  // NOTE ON PARAMETERIZATION
  // =================================================================================
  // This 'isle' wrapper exposes a set of standard parameters (AxiAddrWidth,
  // AxiDataWidth, etc.) to provide a uniform interface for the Ollivander generator.
  // However, the instantiated 'safety_island_synth_wrapper' module is an external and 
  // immutable IP whose configuration is handled internally through its SystemVerilog packages.
  // Consequently, the parameters of this shell are NOT propagated to the instance.
  // They exist solely to satisfy the generator's interface contract.
  // =================================================================================

  // Instantiate the immutable external wrapper
  safety_island_synth_wrapper i_safety_island_synth_wrapper (
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
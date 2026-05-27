// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the PULP Integer Cluster
//
// BENDER: name="pulp_cluster"
// BENDER: name="axi"

`include "axi/typedef.svh"

module pulp_cluster_isle
  import axi_pkg::*;
#(
  localparam int unsigned AxiAddrWidth       = 48,
  localparam int unsigned AxiDataWidth       = 64,
  localparam int unsigned AxiUserWidth       = 10,
  localparam int unsigned AxiInIdWidth       = 5,
  localparam int unsigned AxiOutIdWidth      = 2,
  localparam int unsigned LogDepth           = 3,
  localparam int unsigned NumCores           = 8,
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
  input  logic rst_ni,
  input  logic ref_clk_i,
  input  logic pwr_on_rst_ni,
  input  logic test_mode_i,
  
  // Control and Status
  input  logic        en_sa_boot_i,
  input  logic [5:0]  cluster_id_i,
  input  logic        fetch_en_i,
  output logic        eoc_o,
  output logic        busy_o,
  input  logic        axi_isolate_i,
  output logic        axi_isolated_o,
  
  // Interrupts
  input  logic                mbox_irq_i,
  input  logic [NumCores-1:0] dbg_irq_valid_i,
  
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
  // However, the instantiated 'pulp_cluster_wrap' module is an external and immutable IP
  // whose configuration is handled internally through its SystemVerilog packages.
  // Consequently, the parameters of this shell are NOT propagated to the instance.
  // They exist solely to satisfy the generator's interface contract.
  // =================================================================================

  // Instantiate the immutable external wrapper
  pulp_cluster_wrap i_pulp_cluster_wrap (
    .clk_i                       ( clk_i           ),
    .rst_ni                      ( rst_ni          ),
    .ref_clk_i                   ( ref_clk_i       ),
    .pwr_on_rst_ni               ( pwr_on_rst_ni   ),
    .pmu_mem_pwdn_i              ( 1'b0            ), // Tie-off default
    .test_mode_i                 ( test_mode_i     ),
    .en_sa_boot_i                ( en_sa_boot_i    ),
    .cluster_id_i                ( cluster_id_i    ),
    .fetch_en_i                  ( fetch_en_i      ),
    .eoc_o                       ( eoc_o           ),
    .busy_o                      ( busy_o          ),
    .axi_isolate_i               ( axi_isolate_i   ),
    .axi_isolated_o              ( axi_isolated_o  ),
    .dma_pe_evt_ack_i            ( 1'b1            ),
    .dma_pe_evt_valid_o          (                 ), // Unused at SoC level
    .dma_pe_irq_ack_i            ( 1'b1            ),
    .dma_pe_irq_valid_o          (                 ), // Unused at SoC level
    .pf_evt_ack_i                ( 1'b1            ),
    .pf_evt_valid_o              (                 ), // Unused at SoC level
    .dbg_irq_valid_i             ( dbg_irq_valid_i ),
    .mbox_irq_i                  ( mbox_irq_i      ),
    .async_cluster_events_wptr_i ( '0              ),
    .async_cluster_events_rptr_o (                 ), // Unused at SoC level
    .async_cluster_events_data_i ( '0              ),
    
    // Map to Ollivander standard AXI IN
    .async_data_slave_aw_wptr_i  ( async_axi_in_aw_wptr_i ),
    .async_data_slave_aw_data_i  ( async_axi_in_aw_data_i ),
    .async_data_slave_aw_rptr_o  ( async_axi_in_aw_rptr_o ),
    .async_data_slave_ar_wptr_i  ( async_axi_in_ar_wptr_i ),
    .async_data_slave_ar_data_i  ( async_axi_in_ar_data_i ),
    .async_data_slave_ar_rptr_o  ( async_axi_in_ar_rptr_o ),
    .async_data_slave_w_wptr_i   ( async_axi_in_w_wptr_i  ),
    .async_data_slave_w_data_i   ( async_axi_in_w_data_i  ),
    .async_data_slave_w_rptr_o   ( async_axi_in_w_rptr_o  ),
    .async_data_slave_r_wptr_o   ( async_axi_in_r_wptr_o  ),
    .async_data_slave_r_data_o   ( async_axi_in_r_data_o  ),
    .async_data_slave_r_rptr_i   ( async_axi_in_r_rptr_i  ),
    .async_data_slave_b_wptr_o   ( async_axi_in_b_wptr_o  ),
    .async_data_slave_b_data_o   ( async_axi_in_b_data_o  ),
    .async_data_slave_b_rptr_i   ( async_axi_in_b_rptr_i  ),

    // Map to Ollivander standard AXI OUT
    .async_data_master_aw_wptr_o ( async_axi_out_aw_wptr_o ),
    .async_data_master_aw_data_o ( async_axi_out_aw_data_o ),
    .async_data_master_aw_rptr_i ( async_axi_out_aw_rptr_i ),
    .async_data_master_ar_wptr_o ( async_axi_out_ar_wptr_o ),
    .async_data_master_ar_data_o ( async_axi_out_ar_data_o ),
    .async_data_master_ar_rptr_i ( async_axi_out_ar_rptr_i ),
    .async_data_master_w_wptr_o  ( async_axi_out_w_wptr_o  ),
    .async_data_master_w_data_o  ( async_axi_out_w_data_o  ),
    .async_data_master_w_rptr_i  ( async_axi_out_w_rptr_i  ),
    .async_data_master_r_wptr_i  ( async_axi_out_r_wptr_i  ),
    .async_data_master_r_data_i  ( async_axi_out_r_data_i  ),
    .async_data_master_r_rptr_o  ( async_axi_out_r_rptr_o  ),
    .async_data_master_b_wptr_i  ( async_axi_out_b_wptr_i  ),
    .async_data_master_b_data_i  ( async_axi_out_b_data_i  ),
    .async_data_master_b_rptr_o  ( async_axi_out_b_rptr_o  )
  );

endmodule : pulp_cluster_isle
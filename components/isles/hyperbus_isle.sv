// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Formatted for Ollivander SoC generator
//
// BENDER: name="hyperbus"
// BENDER: name="axi"
// BENDER: name="common_cells"
// BENDER: name="register_interface"

`include "register_interface/typedef.svh"

module hyperbus_isle
#(
  parameter int unsigned NumChips          = 1,
  parameter int unsigned NumPhys           = 2,
  parameter bit          UsePhyClkDivider  = 1,
  parameter int unsigned AxiAddrWidth      = 48,
  parameter int unsigned AxiDataWidth      = 64,
  parameter int unsigned AxiInIdWidth      = 4,
  parameter int unsigned AxiUserWidth      = 10,
  parameter int unsigned AxiMaxTrans       = 0 ,
  parameter type         axi_in_req_t      = logic,
  parameter type         axi_in_resp_t     = logic,
  parameter type         axi_in_w_chan_t   = logic,
  parameter type         axi_in_b_chan_t   = logic,
  parameter type         axi_in_ar_chan_t  = logic,
  parameter type         axi_in_r_chan_t   = logic,
  parameter type         axi_in_aw_chan_t  = logic,
  parameter int unsigned RegAddrWidth      = 32,
  parameter int unsigned RegDataWidth      = 32,
  parameter int unsigned MinFreqMHz        = 100,
  parameter type         reg_req_t         = logic,
  parameter type         reg_rsp_t         = logic,
  // The below have sensible defaults, but should be set on integration!
  parameter int unsigned RxFifoLogDepth    = 2,
  parameter int unsigned TxFifoLogDepth    = 2,
  parameter logic [RegDataWidth-1:0] RstChipBase  = 'h0,      // Base address for all chips
  parameter logic [RegDataWidth-1:0] RstChipSpace = 'h1_0000, // 64 KiB: Current maximum
                                                              // HyperBus device size
  parameter int unsigned PhyStartupCycles  = 300 * 200, /* us*MHz */
                                                        // Conservative maximum
                                                        // frequency estimate
  parameter int unsigned LogDepth          = 3,
  parameter int unsigned AsyncAxiInArWidth = 0,
  parameter int unsigned AsyncAxiInAwWidth = 0,
  parameter int unsigned AsyncAxiInBWidth  = 0,
  parameter int unsigned AsyncAxiInRWidth  = 0,
  parameter int unsigned AsyncAxiInWWidth  = 0,
  parameter int unsigned CdcSyncStages     = 0
)(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic test_mode_i,
  
  // Async AXI bus (Slave Port)
  input  logic [AsyncAxiInArWidth-1:0] async_axi_in_ar_data_i,
  input  logic [         LogDepth:0] async_axi_in_ar_wptr_i,
  output logic [         LogDepth:0] async_axi_in_ar_rptr_o,
  input  logic [AsyncAxiInAwWidth-1:0] async_axi_in_aw_data_i,
  input  logic [         LogDepth:0] async_axi_in_aw_wptr_i,
  output logic [         LogDepth:0] async_axi_in_aw_rptr_o,
  output logic [ AsyncAxiInBWidth-1:0] async_axi_in_b_data_o,
  output logic [         LogDepth:0] async_axi_in_b_wptr_o,
  input  logic [         LogDepth:0] async_axi_in_b_rptr_i,
  output logic [ AsyncAxiInRWidth-1:0] async_axi_in_r_data_o,
  output logic [         LogDepth:0] async_axi_in_r_wptr_o,
  input  logic [         LogDepth:0] async_axi_in_r_rptr_i,
  input  logic [ AsyncAxiInWWidth-1:0] async_axi_in_w_data_i,
  input  logic [         LogDepth:0] async_axi_in_w_wptr_i,
  output logic [         LogDepth:0] async_axi_in_w_rptr_o,
  
  // Reg bus (Async Slave Port)
  input  logic     reg_async_slv_req_i,
  output logic     reg_async_slv_ack_o,
  input  reg_req_t reg_async_slv_data_i,
  output logic     reg_async_slv_req_o,
  input  logic     reg_async_slv_ack_i,
  output reg_rsp_t reg_async_slv_data_o,

  // Physical interace: HyperBus PADs
  inout wire logic pad_config_tc_pad_internal_signals_0,
  inout wire logic pad_config_tc_pad_internal_signals_1,
  inout wire logic pad_config_tc_pad_internal_signals_2,
  inout wire logic pad_config_tc_pad_internal_signals_3,
  inout wire logic pad_hyper_phy0_cs_n_0_pad,
  inout wire logic pad_hyper_phy0_cs_n_1_pad,
  inout wire logic pad_hyper_phy0_ck_pad,
  inout wire logic pad_hyper_phy0_ck_n_pad,
  inout wire logic pad_hyper_phy0_rwds_pad,
  inout wire logic pad_hyper_phy0_dq_b0_pad,
  inout wire logic pad_hyper_phy0_dq_b1_pad,
  inout wire logic pad_hyper_phy0_dq_b2_pad,
  inout wire logic pad_hyper_phy0_dq_b3_pad,
  inout wire logic pad_hyper_phy0_dq_b4_pad,
  inout wire logic pad_hyper_phy0_dq_b5_pad,
  inout wire logic pad_hyper_phy0_dq_b6_pad,
  inout wire logic pad_hyper_phy0_dq_b7_pad,
  inout wire logic pad_hyper_phy0_reset_n_pad,
  inout wire logic pad_hyper_phy1_cs_n_0_pad,
  inout wire logic pad_hyper_phy1_cs_n_1_pad,
  inout wire logic pad_hyper_phy1_ck_pad,
  inout wire logic pad_hyper_phy1_ck_n_pad,
  inout wire logic pad_hyper_phy1_rwds_pad,
  inout wire logic pad_hyper_phy1_dq_b0_pad,
  inout wire logic pad_hyper_phy1_dq_b1_pad,
  inout wire logic pad_hyper_phy1_dq_b2_pad,
  inout wire logic pad_hyper_phy1_dq_b3_pad,
  inout wire logic pad_hyper_phy1_dq_b4_pad,
  inout wire logic pad_hyper_phy1_dq_b5_pad,
  inout wire logic pad_hyper_phy1_dq_b6_pad,
  inout wire logic pad_hyper_phy1_dq_b7_pad,
  inout wire logic pad_hyper_phy1_reset_n_pad
);

logic rst_n;

reg_req_t   reg_req;
reg_rsp_t   reg_rsp;

typedef struct packed {
  logic [31:0]             idx;
  logic [AxiAddrWidth-1:0] start_addr;
  logic [AxiAddrWidth-1:0] end_addr;
} addr_rule_t;

axi_in_req_t  hyper_req;
axi_in_resp_t hyper_rsp;

axi_cdc_dst #(
  .LogDepth       ( LogDepth         ),
  .SyncStages     ( CdcSyncStages    ),
  .aw_chan_t      ( axi_in_aw_chan_t ),
  .w_chan_t       ( axi_in_w_chan_t  ),
  .b_chan_t       ( axi_in_b_chan_t  ),
  .ar_chan_t      ( axi_in_ar_chan_t ),
  .r_chan_t       ( axi_in_r_chan_t  ),
  .axi_req_t      ( axi_in_req_t     ),
  .axi_resp_t     ( axi_in_resp_t    )
) i_hyper_axi_cdc_dst (
  // asynchronous slave port
  .async_data_slave_aw_data_i ( async_axi_in_aw_data_i ),
  .async_data_slave_aw_wptr_i ( async_axi_in_aw_wptr_i ),
  .async_data_slave_aw_rptr_o ( async_axi_in_aw_rptr_o ),
  .async_data_slave_w_data_i  ( async_axi_in_w_data_i  ),
  .async_data_slave_w_wptr_i  ( async_axi_in_w_wptr_i  ),
  .async_data_slave_w_rptr_o  ( async_axi_in_w_rptr_o  ),
  .async_data_slave_b_data_o  ( async_axi_in_b_data_o  ),
  .async_data_slave_b_wptr_o  ( async_axi_in_b_wptr_o  ),
  .async_data_slave_b_rptr_i  ( async_axi_in_b_rptr_i  ),
  .async_data_slave_ar_data_i ( async_axi_in_ar_data_i ),
  .async_data_slave_ar_wptr_i ( async_axi_in_ar_wptr_i ),
  .async_data_slave_ar_rptr_o ( async_axi_in_ar_rptr_o ),
  .async_data_slave_r_data_o  ( async_axi_in_r_data_o  ),
  .async_data_slave_r_wptr_o  ( async_axi_in_r_wptr_o  ),
  .async_data_slave_r_rptr_i  ( async_axi_in_r_rptr_i  ),
  // synchronous master port
  .dst_clk_i                  ( clk_i     ),
  .dst_rst_ni                 ( rst_n     ),
  .dst_req_o                  ( hyper_req ),
  .dst_resp_i                 ( hyper_rsp )
);

reg_cdc_dst #(
  .CDC_KIND ( "cdc_4phase" ),
  .req_t    ( reg_req_t ),
  .rsp_t    ( reg_rsp_t )
) i_hyper_reg_cdc_dst (
  .dst_clk_i   ( clk_i ),
  .dst_rst_ni  ( rst_n ),
  .dst_req_o   ( reg_req ),
  .dst_rsp_i   ( reg_rsp ),

  .async_req_i (reg_async_slv_req_i),
  .async_ack_o (reg_async_slv_ack_o),
  .async_data_i(reg_async_slv_data_i),

  .async_req_o (reg_async_slv_req_o),
  .async_ack_i (reg_async_slv_ack_i),
  .async_data_o(reg_async_slv_data_o)
);

rstgen i_hyper_rstgen (
  .clk_i   ( clk_i ),
  .rst_ni,
  .test_mode_i,
  .rst_no  ( rst_n ),
  .init_no ( )
);

logic [NumPhys-1:0][NumChips-1:0] hyper_cs_no;
logic [NumPhys-1:0] hyper_ck_o;
logic [NumPhys-1:0] hyper_ck_no;
logic [NumPhys-1:0] hyper_rwds_o;
logic [NumPhys-1:0] hyper_rwds_i;
logic [NumPhys-1:0] hyper_rwds_oe_o;
logic [NumPhys-1:0][7:0] hyper_dq_i;
logic [NumPhys-1:0][7:0] hyper_dq_o;
logic [NumPhys-1:0] hyper_dq_oe_o;
logic [NumPhys-1:0] hyper_reset_no;

hyperbus           #(
  .NumChips         ( NumChips         ),
  .NumPhys          ( NumPhys          ),
  // .IsClockODelayed  ( UsePhyClkDivider ),
  .AxiAddrWidth     ( AxiAddrWidth     ),
  .AxiDataWidth     ( AxiDataWidth     ),
  .AxiIdWidth       ( AxiInIdWidth     ),
  .AxiUserWidth     ( AxiUserWidth     ),
  .axi_req_t        ( axi_in_req_t     ),
  .axi_rsp_t        ( axi_in_resp_t    ),
  .RegAddrWidth     ( RegAddrWidth     ),
  .RegDataWidth     ( RegDataWidth     ),
  .reg_req_t        ( reg_req_t        ),
  .reg_rsp_t        ( reg_rsp_t        ),
  .axi_rule_t       ( addr_rule_t      ),

  .MinFreqMHz       ( MinFreqMHz ),
  .RxFifoLogDepth   ( RxFifoLogDepth   ),
  .TxFifoLogDepth   ( TxFifoLogDepth   ),
  .RstChipBase      ( RstChipBase      ),
  .RstChipSpace     ( RstChipSpace     ),
  .PhyStartupCycles ( PhyStartupCycles ),
  .SyncStages       ( CdcSyncStages    )
) i_hyperbus        (
  .clk_phy_i        ( clk_i              ),
  .rst_phy_ni       ( rst_n              ),
  .clk_sys_i        ( clk_i              ),
  .rst_sys_ni       ( rst_n              ),
  .test_mode_i      ( test_mode_i        ),
  .axi_req_i        ( hyper_req          ),
  .axi_rsp_o        ( hyper_rsp          ),
  .reg_req_i        ( reg_req            ),
  .reg_rsp_o        ( reg_rsp            ),
  .hyper_cs_no,
  .hyper_ck_o,
  .hyper_ck_no,
  .hyper_rwds_o,
  .hyper_rwds_i,
  .hyper_rwds_oe_o,
  .hyper_dq_i,
  .hyper_dq_o,
  .hyper_dq_oe_o,
  .hyper_reset_no
);

/*
  // Missing Padrick dependencies
  pad_domain_topr_static_connection_signals_pad2soc_t pad2soc; //output
  pad_domain_topr_static_connection_signals_soc2pad_t soc2pad; //input

hyperbus_padframe_topr_pads i_hyperbus_padframe_topr_pads(
  .static_connection_signals_pad2soc(pad2soc),
  .static_connection_signals_soc2pad(soc2pad),
  .pad_config_tc_pad_internal_signals_0,
  .pad_config_tc_pad_internal_signals_1,
  .pad_config_tc_pad_internal_signals_2,
  .pad_config_tc_pad_internal_signals_3,
  .pad_hyper_phy0_cs_n_0_pad,
  .pad_hyper_phy0_cs_n_1_pad,
  .pad_hyper_phy0_ck_pad,
  .pad_hyper_phy0_ck_n_pad,
  .pad_hyper_phy0_rwds_pad,
  .pad_hyper_phy0_dq_b0_pad,
  .pad_hyper_phy0_dq_b1_pad,
  .pad_hyper_phy0_dq_b2_pad,
  .pad_hyper_phy0_dq_b3_pad,
  .pad_hyper_phy0_dq_b4_pad,
  .pad_hyper_phy0_dq_b5_pad,
  .pad_hyper_phy0_dq_b6_pad,
  .pad_hyper_phy0_dq_b7_pad,
  .pad_hyper_phy0_reset_n_pad,
  .pad_hyper_phy1_cs_n_0_pad,
  .pad_hyper_phy1_cs_n_1_pad,
  .pad_hyper_phy1_ck_pad,
  .pad_hyper_phy1_ck_n_pad,
  .pad_hyper_phy1_rwds_pad,
  .pad_hyper_phy1_dq_b0_pad,
  .pad_hyper_phy1_dq_b1_pad,
  .pad_hyper_phy1_dq_b2_pad,
  .pad_hyper_phy1_dq_b3_pad,
  .pad_hyper_phy1_dq_b4_pad,
  .pad_hyper_phy1_dq_b5_pad,
  .pad_hyper_phy1_dq_b6_pad,
  .pad_hyper_phy1_dq_b7_pad,
  .pad_hyper_phy1_reset_n_pad
);

// PAD input and output signals assignment

assign soc2pad.hyper_phy0_cs_no_0 = hyper_cs_no[0][0];
assign soc2pad.hyper_phy0_cs_no_1 = hyper_cs_no[0][1];
assign soc2pad.hyper_phy0_ck_o = hyper_ck_o[0];
assign soc2pad.hyper_phy0_ck_no = hyper_ck_no[0];
assign soc2pad.hyper_phy0_rwds_o = hyper_rwds_o[0];
assign hyper_rwds_i[0] = pad2soc.hyper_phy0_rwds_i;
assign soc2pad.hyper_phy0_rwds_oe_o = hyper_rwds_oe_o[0];
assign hyper_dq_i[0][0] = pad2soc.hyper_phy0_dq_i_b0;
assign hyper_dq_i[0][1] = pad2soc.hyper_phy0_dq_i_b1;
assign hyper_dq_i[0][2] = pad2soc.hyper_phy0_dq_i_b2;
assign hyper_dq_i[0][3] = pad2soc.hyper_phy0_dq_i_b3;
assign hyper_dq_i[0][4] = pad2soc.hyper_phy0_dq_i_b4;
assign hyper_dq_i[0][5] = pad2soc.hyper_phy0_dq_i_b5;
assign hyper_dq_i[0][6] = pad2soc.hyper_phy0_dq_i_b6;
assign hyper_dq_i[0][7] = pad2soc.hyper_phy0_dq_i_b7;
assign soc2pad.hyper_phy0_dq_o_b0 = hyper_dq_o[0][0];
assign soc2pad.hyper_phy0_dq_o_b1 = hyper_dq_o[0][1];
assign soc2pad.hyper_phy0_dq_o_b2 = hyper_dq_o[0][2];
assign soc2pad.hyper_phy0_dq_o_b3 = hyper_dq_o[0][3];
assign soc2pad.hyper_phy0_dq_o_b4 = hyper_dq_o[0][4];
assign soc2pad.hyper_phy0_dq_o_b5 = hyper_dq_o[0][5];
assign soc2pad.hyper_phy0_dq_o_b6 = hyper_dq_o[0][6];
assign soc2pad.hyper_phy0_dq_o_b7 = hyper_dq_o[0][7];
assign soc2pad.hyper_phy0_dq_oe_o = hyper_dq_oe_o[0];
assign soc2pad.hyper_phy0_reset_no = hyper_reset_no[0];
assign soc2pad.hyper_phy1_cs_no_0 = hyper_cs_no[1][0];
assign soc2pad.hyper_phy1_cs_no_1 = hyper_cs_no[1][1];
assign soc2pad.hyper_phy1_ck_o = hyper_ck_o[1];
assign soc2pad.hyper_phy1_ck_no = hyper_ck_no[1];
assign soc2pad.hyper_phy1_rwds_o = hyper_rwds_o[1];
assign hyper_rwds_i[1] = pad2soc.hyper_phy1_rwds_i;
assign soc2pad.hyper_phy1_rwds_oe_o = hyper_rwds_oe_o[1];
assign hyper_dq_i[1][0] = pad2soc.hyper_phy1_dq_i_b0;
assign hyper_dq_i[1][1] = pad2soc.hyper_phy1_dq_i_b1;
assign hyper_dq_i[1][2] = pad2soc.hyper_phy1_dq_i_b2;
assign hyper_dq_i[1][3] = pad2soc.hyper_phy1_dq_i_b3;
assign hyper_dq_i[1][4] = pad2soc.hyper_phy1_dq_i_b4;
assign hyper_dq_i[1][5] = pad2soc.hyper_phy1_dq_i_b5;
assign hyper_dq_i[1][6] = pad2soc.hyper_phy1_dq_i_b6;
assign hyper_dq_i[1][7] = pad2soc.hyper_phy1_dq_i_b7;
assign soc2pad.hyper_phy1_dq_o_b0 = hyper_dq_o[1][0];
assign soc2pad.hyper_phy1_dq_o_b1 = hyper_dq_o[1][1];
assign soc2pad.hyper_phy1_dq_o_b2 = hyper_dq_o[1][2];
assign soc2pad.hyper_phy1_dq_o_b3 = hyper_dq_o[1][3];
assign soc2pad.hyper_phy1_dq_o_b4 = hyper_dq_o[1][4];
assign soc2pad.hyper_phy1_dq_o_b5 = hyper_dq_o[1][5];
assign soc2pad.hyper_phy1_dq_o_b6 = hyper_dq_o[1][6];
assign soc2pad.hyper_phy1_dq_o_b7 = hyper_dq_o[1][7];
assign soc2pad.hyper_phy1_dq_oe_o = hyper_dq_oe_o[1];
assign soc2pad.hyper_phy1_reset_no = hyper_reset_no[1];

assign soc2pad.hyper_phy0_schmitt_en_o = hyper_pad_cfg_o[0][7];
assign soc2pad.hyper_phy0_pu_en_o = hyper_pad_cfg_o[0][6];
assign soc2pad.hyper_phy0_pd_en_o = hyper_pad_cfg_o[0][5];
assign soc2pad.hyper_phy0_slew_en_o = hyper_pad_cfg_o[0][3];
assign soc2pad.hyper_phy0_drive_strength_o = hyper_pad_cfg_o[0][1:0];
assign soc2pad.hyper_phy1_schmitt_en_o = hyper_pad_cfg_o[1][7];
assign soc2pad.hyper_phy1_pu_en_o = hyper_pad_cfg_o[1][6];
assign soc2pad.hyper_phy1_pd_en_o = hyper_pad_cfg_o[1][5];
assign soc2pad.hyper_phy1_slew_en_o = hyper_pad_cfg_o[1][3];
assign soc2pad.hyper_phy1_drive_strength_o = hyper_pad_cfg_o[1][1:0];
*/

endmodule: hyperbus_isle
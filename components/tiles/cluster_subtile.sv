// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Cluster Subtile (NoC-Specific)
// Extracted and generalized from Gwaihir's cluster_tile.sv

// BENDER: name="floo_noc"
// BENDER: name="snitch_cluster"
// BENDER: name="axi"
//
// OLLIVANDER: require="snitch_hwpe_subsystem.sv"
// OLLIVANDER: require="snitch_tcdm_aligner.sv"

`include "axi/assign.svh"
`include "axi/typedef.svh"
`include "tcdm_interface/typedef.svh"

module cluster_subtile
  import floo_pkg::*;
  import floo_ollivander_noc_pkg::*;
  import snitch_cluster_pkg::*;
#(
  parameter bit UseHWPE = 1'b0,
  // Fixed architectural constraints from Snitch (Required by Ollivander Validation)
  localparam int unsigned AxiAddrWidth        = 48,  // snitch_cluster_pkg::AddrWidth
  localparam int unsigned AxiNarrowDataWidth  = 64,  // snitch_cluster_pkg::NarrowDataWidth
  localparam int unsigned AxiWideDataWidth    = 512, // snitch_cluster_pkg::WideDataWidth
  localparam int unsigned AxiNarrowOutIdWidth = 2,   // snitch_cluster_pkg::NarrowIdWidthOut
  localparam int unsigned AxiNarrowInIdWidth  = 5,   // snitch_cluster_pkg::NarrowIdWidthIn
  localparam int unsigned AxiWideOutIdWidth   = 1,   // snitch_cluster_pkg::WideIdWidthOut
  localparam int unsigned AxiWideInIdWidth    = 3    // snitch_cluster_pkg::WideIdWidthIn
) (
  input  logic                                    clk_i,
  input  logic                                    rst_ni,
  input  logic                                    test_mode_i,
  
  // Cluster ports
  input  logic                      [NrCores-1:0] debug_req_i,
  input  logic                      [NrCores-1:0] meip_i,
  input  logic                      [NrCores-1:0] mtip_i,
  input  logic                      [NrCores-1:0] msip_i,
  input  logic                      [        9:0] hart_base_id_i,
  input  snitch_cluster_pkg::addr_t               cluster_base_addr_i,
  input  snitch_cluster_pkg::addr_t               cluster_base_offset_i,
  
  // Dual-Network AXI Master Ports
  output snitch_cluster_pkg::narrow_out_req_t     axi_narrow_req_o,
  input  snitch_cluster_pkg::narrow_out_resp_t    axi_narrow_resp_i,
  output snitch_cluster_pkg::wide_out_req_t       axi_wide_req_o,
  input  snitch_cluster_pkg::wide_out_resp_t      axi_wide_resp_i,

  // Dual-Network AXI Slave Ports
  input  snitch_cluster_pkg::narrow_in_req_t      axi_narrow_req_i,
  output snitch_cluster_pkg::narrow_in_resp_t     axi_narrow_resp_o,
  input  snitch_cluster_pkg::wide_in_req_t        axi_wide_req_i,
  output snitch_cluster_pkg::wide_in_resp_t       axi_wide_resp_o,

  // Offload interface
  input  floo_ollivander_noc_pkg::red_wide_req_t  offload_wide_req_i,
  output floo_ollivander_noc_pkg::red_wide_rsp_t  offload_wide_rsp_o
);

  snitch_cluster_pkg::narrow_out_req_t  cluster_narrow_ext_req;
  snitch_cluster_pkg::narrow_out_resp_t cluster_narrow_ext_rsp;
  snitch_cluster_pkg::tcdm_dma_req_t    cluster_tcdm_ext_req_aligned;
  snitch_cluster_pkg::tcdm_dma_req_t    cluster_tcdm_ext_req_misaligned;
  snitch_cluster_pkg::tcdm_dma_rsp_t    cluster_tcdm_ext_rsp_aligned;
  snitch_cluster_pkg::tcdm_dma_rsp_t    cluster_tcdm_ext_rsp_misaligned;

  localparam int unsigned HWPECtrlAddrWidth = 32;
  localparam int unsigned HWPECtrlDataWidth = 32;
  typedef logic [HWPECtrlAddrWidth-1:0] addr_hwpe_ctrl_t;
  typedef logic [HWPECtrlDataWidth-1:0] data_hwpe_ctrl_t;
  typedef logic [3:0] strb_hwpe_ctrl_t;

  `AXI_TYPEDEF_ALL(cluster_narrow_out_dw_conv, snitch_cluster_pkg::addr_t,
                   snitch_cluster_pkg::narrow_out_id_t, data_hwpe_ctrl_t, strb_hwpe_ctrl_t,
                   snitch_cluster_pkg::user_narrow_t)

  cluster_narrow_out_dw_conv_req_t cluster_narrow_out_dw_conv_req, cluster_narrow_out_cut_req;
  cluster_narrow_out_dw_conv_resp_t cluster_narrow_out_dw_conv_rsp, cluster_narrow_out_cut_rsp;

  `TCDM_TYPEDEF_ALL(hwpectrl, HWPECtrlAddrWidth, HWPECtrlDataWidth, 1)

  hwpectrl_req_t               hwpectrl_req;
  hwpectrl_rsp_t               hwpectrl_rsp;

  logic          [NrCores-1:0] mxip;

  ////////////////////////
  // Wide FPU Reduction //
  ////////////////////////

  // Snitch cluster DCA interface
  snitch_cluster_pkg::dca_req_t offload_dca_req, offload_dca_req_cut;
  snitch_cluster_pkg::dca_rsp_t offload_dca_rsp, offload_dca_rsp_cut;

  if (floo_pkg::en_wide_reduction(RouteCfg.CollectiveCfg.OpCfg)) begin : gen_wide_offload_reduction
    // Connect the DCA Request
    assign offload_dca_req.q_valid = offload_wide_req_i.valid;
    assign offload_wide_rsp_o.ready  = offload_dca_rsp.q_ready;

    // Parse the FPU Request
    always_comb begin
      // Init default values
      offload_dca_req.q.operands     = '0;

      // Set default Values
      offload_dca_req.q.src_fmt      = fpnew_pkg::FP64;
      offload_dca_req.q.dst_fmt      = fpnew_pkg::FP64;
      offload_dca_req.q.int_fmt      = fpnew_pkg::INT64;
      offload_dca_req.q.vectorial_op = 1'b0;
      offload_dca_req.q.op_mod       = 1'b0;
      offload_dca_req.q.rnd_mode     = fpnew_pkg::RNE;
      offload_dca_req.q.op           = fpnew_pkg::ADD;

      // Define the operation we want to execute on the FPU
      unique casez (offload_wide_req_i.req.op)
        (floo_pkg::FpAdd): begin
          offload_dca_req.q.op          = fpnew_pkg::ADD;
          offload_dca_req.q.operands[0] = '0;
          offload_dca_req.q.operands[1] = offload_wide_req_i.req.operand1;
          offload_dca_req.q.operands[2] = offload_wide_req_i.req.operand2;
        end
        (floo_pkg::FpMul): begin
          offload_dca_req.q.op          = fpnew_pkg::MUL;
          offload_dca_req.q.operands[0] = offload_wide_req_i.req.operand1;
          offload_dca_req.q.operands[1] = offload_wide_req_i.req.operand2;
          offload_dca_req.q.operands[2] = '0;
        end
        (floo_pkg::FpMax): begin
          offload_dca_req.q.op          = fpnew_pkg::MINMAX;
          offload_dca_req.q.rnd_mode    = fpnew_pkg::RNE;
          offload_dca_req.q.operands[0] = offload_wide_req_i.req.operand1;
          offload_dca_req.q.operands[1] = offload_wide_req_i.req.operand2;
          offload_dca_req.q.operands[2] = '0;
        end
        (floo_pkg::FpMin): begin
          offload_dca_req.q.op          = fpnew_pkg::MINMAX;
          offload_dca_req.q.rnd_mode    = fpnew_pkg::RTZ;
          offload_dca_req.q.operands[0] = offload_wide_req_i.req.operand1;
          offload_dca_req.q.operands[1] = offload_wide_req_i.req.operand2;
          offload_dca_req.q.operands[2] = '0;
        end
        default: begin
          offload_dca_req.q.op          = fpnew_pkg::ADD;
          offload_dca_req.q.operands[0] = '0;
          offload_dca_req.q.operands[1] = '0;
          offload_dca_req.q.operands[2] = '0;
        end
      endcase
    end

    generic_reqrsp_cut #(
      .req_chan_t(snitch_cluster_pkg::dca_req_chan_t),
      .rsp_chan_t(snitch_cluster_pkg::dca_rsp_chan_t),
      .BypassReq (RouteCfg.CollectiveCfg.WideRedCfg.CutOffloadIntf),
      .BypassRsp (RouteCfg.CollectiveCfg.WideRedCfg.CutOffloadIntf)
    ) i_dca_router_cut (
      .clk_i    (clk_i),
      .rst_ni   (rst_ni),
      .slv_req_i(offload_dca_req),
      .slv_rsp_o(offload_dca_rsp),
      .mst_req_o(offload_dca_req_cut),
      .mst_rsp_i(offload_dca_rsp_cut)
    );
    
    assign offload_wide_rsp_o.valid      = offload_dca_rsp.p_valid;
    assign offload_dca_req.p_ready       = offload_wide_req_i.ready;
    assign offload_wide_rsp_o.rsp.result = offload_dca_rsp.p.result;

  end else begin : gen_no_wide_reduction
    assign offload_dca_req_cut           = '0;
    assign offload_dca_rsp               = '0;
    assign offload_wide_rsp_o.ready      = '0;
    assign offload_wide_rsp_o.rsp.result = '0;
    assign offload_wide_rsp_o.valid      = '0;
  end

  snitch_cluster_wrapper i_cluster (
    .clk_i             (clk_i),
    .rst_ni            (rst_ni),
    .debug_req_i,
    .meip_i,
    .mtip_i,
    .msip_i,
    .hart_base_id_i,
    .cluster_base_addr_i,
    .cluster_base_offset_i,
    .mxip_i            (mxip),
    .clk_d2_bypass_i   ('0),
    .sram_cfg_tcdm_i        ('0),
    .sram_cfg_icache_tag_i  ('0),
    .sram_cfg_icache_data_i ('0),
    .narrow_in_req_i   (axi_narrow_req_i),
    .narrow_in_resp_o  (axi_narrow_resp_o),
    .narrow_out_req_o  (axi_narrow_req_o),
    .narrow_out_resp_i (axi_narrow_resp_i),
    .wide_out_req_o    (axi_wide_req_o),
    .wide_out_resp_i   (axi_wide_resp_i),
    .wide_in_req_i     (axi_wide_req_i),
    .wide_in_resp_o    (axi_wide_resp_o),
    .narrow_ext_req_o  (cluster_narrow_ext_req),
    .narrow_ext_resp_i (cluster_narrow_ext_rsp),
    .tcdm_ext_req_i    (cluster_tcdm_ext_req_aligned),
    .tcdm_ext_resp_o   (cluster_tcdm_ext_rsp_aligned),
    .dca_req_i         (offload_dca_req_cut),
    .dca_rsp_o         (offload_dca_rsp_cut),
    .x_issue_req_o     (),
    .x_issue_resp_i    ('0),
    .x_issue_valid_o   (),
    .x_issue_ready_i   ('0),
    .x_register_o      (),
    .x_register_valid_o(),
    .x_register_ready_i('0),
    .x_commit_o        (),
    .x_commit_valid_o  (),
    .x_result_i        ('0),
    .x_result_valid_i  ('0),
    .x_result_ready_o  ()
  );

  if (UseHWPE) begin : gen_hwpe

    // Convert narrow AXI's 64 bit DW down to 32
    axi_dw_converter #(
      .AxiMaxReads        (1),
      .AxiSlvPortDataWidth(snitch_cluster_pkg::NarrowDataWidth),
      .AxiMstPortDataWidth(HWPECtrlDataWidth),
      .AxiAddrWidth       (snitch_cluster_pkg::AddrWidth),
      .AxiIdWidth         (snitch_cluster_pkg::NarrowIdWidthOut),
      .aw_chan_t          (snitch_cluster_pkg::narrow_out_aw_chan_t),
      .mst_w_chan_t       (cluster_narrow_out_dw_conv_w_chan_t),
      .slv_w_chan_t       (snitch_cluster_pkg::narrow_out_w_chan_t),
      .b_chan_t           (snitch_cluster_pkg::narrow_out_b_chan_t),
      .ar_chan_t          (snitch_cluster_pkg::narrow_out_ar_chan_t),
      .mst_r_chan_t       (cluster_narrow_out_dw_conv_r_chan_t),
      .slv_r_chan_t       (snitch_cluster_pkg::narrow_out_r_chan_t),
      .axi_mst_req_t      (cluster_narrow_out_dw_conv_req_t),
      .axi_mst_resp_t     (cluster_narrow_out_dw_conv_resp_t),
      .axi_slv_req_t      (snitch_cluster_pkg::narrow_out_req_t),
      .axi_slv_resp_t     (snitch_cluster_pkg::narrow_out_resp_t)
    ) i_axi_dw_hwpe (
      .clk_i     (clk_i),
      .rst_ni    (rst_ni),
      .slv_req_i (cluster_narrow_ext_req),
      .slv_resp_o(cluster_narrow_ext_rsp),
      .mst_req_o (cluster_narrow_out_dw_conv_req),
      .mst_resp_i(cluster_narrow_out_dw_conv_rsp)
    );

    axi_cut #(
      .Bypass    (0),
      .aw_chan_t (snitch_cluster_pkg::narrow_out_aw_chan_t),
      .w_chan_t  (cluster_narrow_out_dw_conv_w_chan_t),
      .b_chan_t  (snitch_cluster_pkg::narrow_out_b_chan_t),
      .ar_chan_t (snitch_cluster_pkg::narrow_out_ar_chan_t),
      .r_chan_t  (cluster_narrow_out_dw_conv_r_chan_t),
      .axi_req_t (cluster_narrow_out_dw_conv_req_t),
      .axi_resp_t(cluster_narrow_out_dw_conv_resp_t)
    ) i_cut_ext_narrow_slv (
      .clk_i     (clk_i),
      .rst_ni    (rst_ni),
      .slv_req_i (cluster_narrow_out_dw_conv_req),
      .slv_resp_o(cluster_narrow_out_dw_conv_rsp),
      .mst_req_o (cluster_narrow_out_cut_req),
      .mst_resp_i(cluster_narrow_out_cut_rsp)
    );

    axi_to_tcdm #(
      .axi_req_t (cluster_narrow_out_dw_conv_req_t),
      .axi_rsp_t (cluster_narrow_out_dw_conv_resp_t),
      .tcdm_req_t(hwpectrl_req_t),
      .tcdm_rsp_t(hwpectrl_rsp_t),
      .IdWidth   (snitch_cluster_pkg::NarrowIdWidthOut),
      .AddrWidth (HWPECtrlAddrWidth),
      .DataWidth (HWPECtrlDataWidth)
    ) i_axi_to_hwpe_ctrl (
      .clk_i     (clk_i),
      .rst_ni    (rst_ni),
      .axi_req_i (cluster_narrow_out_cut_req),
      .axi_rsp_o (cluster_narrow_out_cut_rsp),
      .tcdm_req_o(hwpectrl_req),
      .tcdm_rsp_i(hwpectrl_rsp)
    );

    snitch_tcdm_aligner #(
      .tcdm_req_t   (snitch_cluster_pkg::tcdm_dma_req_t),
      .tcdm_rsp_t   (snitch_cluster_pkg::tcdm_dma_rsp_t),
      .DataWidth    (snitch_cluster_pkg::WideDataWidth),
      .TCDMDataWidth(snitch_cluster_pkg::NarrowDataWidth),
      .AddrWidth    (snitch_cluster_pkg::TcdmAddrWidth)
    ) i_snitch_tcdm_aligner (
      .clk_i                (clk_i),
      .rst_ni               (rst_ni),
      .tcdm_req_misaligned_i(cluster_tcdm_ext_req_misaligned),
      .tcdm_req_aligned_o   (cluster_tcdm_ext_req_aligned),
      .tcdm_rsp_aligned_i   (cluster_tcdm_ext_rsp_aligned),
      .tcdm_rsp_misaligned_o(cluster_tcdm_ext_rsp_misaligned)
    );

    snitch_hwpe_subsystem #(
      .tcdm_req_t   (snitch_cluster_pkg::tcdm_dma_req_t),
      .tcdm_rsp_t   (snitch_cluster_pkg::tcdm_dma_rsp_t),
      .periph_req_t (hwpectrl_req_t),
      .periph_rsp_t (hwpectrl_rsp_t),
      .HwpeDataWidth(snitch_cluster_pkg::WideDataWidth),
      .IdWidth      (snitch_cluster_pkg::NarrowIdWidthOut),
      .NrCores      (NrCores),
      .TCDMDataWidth(snitch_cluster_pkg::NarrowDataWidth)
    ) i_snitch_hwpe_subsystem (
      .clk_i          (clk_i),
      .rst_ni         (rst_ni),
      .test_mode_i    (1'b0),
      .tcdm_req_o     (cluster_tcdm_ext_req_misaligned),
      .tcdm_rsp_i     (cluster_tcdm_ext_rsp_misaligned),
      .hwpe_ctrl_req_i(hwpectrl_req),
      .hwpe_ctrl_rsp_o(hwpectrl_rsp),
      .hwpe_evt_o     (mxip)
    );
  end else begin : gen_no_redmul_e
    assign mxip                         = '0;
    assign cluster_tcdm_ext_req_aligned = '0;
    assign cluster_narrow_ext_rsp       = '0;
  end

endmodule
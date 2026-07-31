// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// SRAM Memory Wrapper (Topology-Agnostic)
// Extracted and generalized from Gwaihir's mem_tile.sv
//
// BENDER: name="axi"
// BENDER: name="axi_obi"
// BENDER: name="common_cells"
// BENDER: name="obi"

`include "common_cells/registers.svh"
`include "axi/typedef.svh"
`include "obi/typedef.svh"

module sram_isle
  import obi_pkg::*;
#(
  parameter int unsigned AxiAddrWidth   = 48,
  parameter int unsigned AxiDataWidth   = 64,
  parameter int unsigned AxiInIdWidth   = 5,
  parameter int unsigned AxiUserWidth   = 2,
  parameter bit          AxiUserAtop    = 1'b1,
  parameter int unsigned AxiUserAtopMsb = 1,
  parameter int unsigned AxiUserAtopLsb = 0,
  parameter int unsigned L2MemSize      = 32'h00100000,
  parameter int unsigned MemSize        = L2MemSize,
  parameter logic [63:0] L2BaseAddr     = 64'h00000000,
  parameter int unsigned SramDataWidth  = 128,
  parameter int unsigned SramNumWords   = 1024,
  parameter type         axi_req_t      = logic,
  parameter type         axi_resp_t     = logic,
  // Memory preloading standardization parameters
  // PreloadType: Tells the generator that this memory uses interleaved multi-bank preloading.
  localparam string PreloadType = "interleaved",
  // PreloadTemplate: Hierarchical path from module top to individual tc_sram array instances.
  localparam string PreloadTemplate = "gen_sram_banks[{group}].gen_sram_macros[{bank}].i_sram.sram",
  // PreloadNumGroups: Number of bank groups (columns) inside the interleaved memory.
  localparam int unsigned PreloadNumGroups = AxiDataWidth / SramDataWidth,
  // PreloadBankWidth: Data width of a single physical SRAM bank in bits.
  localparam int unsigned PreloadBankWidth = SramDataWidth,
  // PreloadBanksPerGroup: Number of physical SRAM banks in each group (rows).
  localparam int unsigned PreloadBanksPerGroup = (MemSize / (AxiDataWidth / 8)) / SramNumWords,
  // PreloadInterleave: Physical interleaving scheme seen by the hex splitter.
  // "lane-group" means {group} is the data lane of the AXI word (gen_sram_banks, always all
  // written together) while {bank} is the depth row selected by the high address bits
  // (gen_sram_macros). This is the opposite of the "word-group" scheme used by l2_isle.
  localparam string PreloadInterleave = "lane-group",
  // HasEcc: 0 indicates this memory does not implement Error Correction Codes (ECC)
  localparam bit HasEcc = 0,
  // EccType: Set to 'none' since ECC is disabled
  localparam string EccType = "none"
) (
  input  logic      clk_i,
  input  logic      rst_ni,
  input  logic      test_mode_i,
  input  axi_req_t  axi_req_i,
  output axi_resp_t axi_resp_o
);

  localparam int unsigned NumBanksPerWord = AxiDataWidth / SramDataWidth;
  localparam int unsigned NumBankRows     = (MemSize / (AxiDataWidth / 8)) / SramNumWords;

  localparam int unsigned SramByteOffsetWidth = $clog2(AxiDataWidth / 8);
  localparam int unsigned SramAddrWidth       = $clog2(SramNumWords);
  localparam int unsigned SramRowSelWidth     = (NumBankRows > 1) ? $clog2(NumBankRows) : 32'd0;

  localparam int unsigned SramAddrWidthOffset = SramByteOffsetWidth;
  localparam int unsigned SramRowSelOffset    = SramAddrWidthOffset + SramAddrWidth;

  // Number of outstanding transactions should be larger than round-trip latency
  localparam int unsigned ObiLatency = 4;

  ///////////////////////
  // axi2obi converter //
  ///////////////////////

  // typedef obi for atomic config
  localparam obi_pkg::obi_optional_cfg_t MgrObiOptionalCfg = '{
      UseAtop: 1'b1,
      UseMemtype: 1'b0,
      UseProt: 1'b0,
      UseDbg: 1'b0,
      AUserWidth: 0,
      WUserWidth: 0,
      RUserWidth: 0,
      MidWidth: 0,
      AChkWidth: 0,
      RChkWidth: 0
  };
  localparam obi_pkg::obi_cfg_t MgrObiCfg = obi_pkg::obi_default_cfg(
      AxiAddrWidth,
      AxiDataWidth,
      (AxiUserAtop ? AxiUserAtopMsb + 1 - AxiUserAtopLsb : AxiInIdWidth),
      MgrObiOptionalCfg
  );
  `OBI_TYPEDEF_ATOP_A_OPTIONAL(mgr_obi_a_optional_t)
  `OBI_TYPEDEF_A_CHAN_T(mgr_obi_a_chan_t, MgrObiCfg.AddrWidth, MgrObiCfg.DataWidth, MgrObiCfg.IdWidth, mgr_obi_a_optional_t)
  `OBI_TYPEDEF_DEFAULT_REQ_T(mgr_obi_req_t, mgr_obi_a_chan_t)
  typedef struct packed {logic exokay;} mgr_obi_r_optional_t;
  `OBI_TYPEDEF_R_CHAN_T(mgr_obi_r_chan_t, MgrObiCfg.DataWidth, MgrObiCfg.IdWidth, mgr_obi_r_optional_t)
  `OBI_TYPEDEF_RSP_T(mgr_obi_rsp_t, mgr_obi_r_chan_t)

  // typedef obi for default config
  localparam obi_pkg::obi_optional_cfg_t SbrObiOptionalCfg = '{
      UseAtop: 1'b0,
      UseMemtype: 1'b0,
      UseProt: 1'b0,
      UseDbg: 1'b0,
      AUserWidth: 0,
      WUserWidth: 0,
      RUserWidth: 0,
      MidWidth: 0,
      AChkWidth: 0,
      RChkWidth: 0
  };
  localparam obi_pkg::obi_cfg_t SbrObiCfg = obi_pkg::obi_default_cfg(
      AxiAddrWidth,
      AxiDataWidth,
      (AxiUserAtop ? AxiUserAtopMsb + 1 - AxiUserAtopLsb : AxiInIdWidth),
      SbrObiOptionalCfg
  );
  `OBI_TYPEDEF_MINIMAL_A_OPTIONAL(sbr_obi_a_optional_t)
  `OBI_TYPEDEF_A_CHAN_T(sbr_obi_a_chan_t, SbrObiCfg.AddrWidth, SbrObiCfg.DataWidth, SbrObiCfg.IdWidth, sbr_obi_a_optional_t)
  `OBI_TYPEDEF_DEFAULT_REQ_T(sbr_obi_req_t, sbr_obi_a_chan_t)
  `OBI_TYPEDEF_MINIMAL_R_OPTIONAL(sbr_obi_r_optional_t)
  `OBI_TYPEDEF_R_CHAN_T(sbr_obi_r_chan_t, SbrObiCfg.DataWidth, SbrObiCfg.IdWidth, sbr_obi_r_optional_t)
  `OBI_TYPEDEF_RSP_T(sbr_obi_rsp_t, sbr_obi_r_chan_t)

  logic [AxiInIdWidth-1:0] axi_in_aw_id, axi_in_ar_id;
  logic [AxiUserWidth-1:0] axi_in_aw_user, axi_in_ar_user;
  logic [MgrObiCfg.IdWidth-1:0] obi_in_write_aid, obi_in_read_aid;

  logic [AxiUserWidth-1:0] axi_in_r_user, axi_in_b_user;
  logic axi_in_rsp_write_bank_strobe, axi_in_rsp_read_size_enable;

  logic [MgrObiCfg.IdWidth-1:0] obi_in_rsp_write_rid, obi_in_rsp_read_rid;

  mgr_obi_req_t obi_req;
  mgr_obi_rsp_t obi_rsp;
  sbr_obi_req_t mem_obi_req, mem_obi_req_cut;
  sbr_obi_rsp_t mem_obi_rsp, mem_obi_rsp_cut;

  if (AxiUserAtop) begin : gen_user_atop
    assign obi_in_write_aid = axi_in_aw_user[AxiUserAtopMsb:AxiUserAtopLsb];
    assign obi_in_read_aid  = axi_in_ar_user[AxiUserAtopMsb:AxiUserAtopLsb];
  end else begin : gen_plain_atop
    assign obi_in_write_aid = axi_in_aw_id;
    assign obi_in_read_aid  = axi_in_ar_id;
  end

  always_comb begin : proc_obi_user
    axi_in_r_user = '0;
    axi_in_b_user = '0;
    if (AxiUserAtop) begin
      axi_in_r_user[AxiUserAtopMsb:AxiUserAtopLsb] |= axi_in_rsp_read_size_enable ? obi_in_rsp_read_rid : '0;
      axi_in_b_user[AxiUserAtopMsb:AxiUserAtopLsb] |= axi_in_rsp_write_bank_strobe ? obi_in_rsp_write_rid : '0;
    end
  end

  axi_to_obi #(
    .ObiCfg      (MgrObiCfg),
    .obi_req_t   (mgr_obi_req_t),
    .obi_rsp_t   (mgr_obi_rsp_t),
    .obi_a_chan_t(mgr_obi_a_chan_t),
    .obi_r_chan_t(mgr_obi_r_chan_t),
    .AxiAddrWidth(AxiAddrWidth),
    .AxiDataWidth(AxiDataWidth),
    .AxiIdWidth  (AxiInIdWidth),
    .AxiUserWidth(AxiUserWidth),
    .MaxTrans    (ObiLatency),
    .axi_req_t   (axi_req_t),
    .axi_rsp_t   (axi_resp_t)
  ) i_axi_to_obi (
    .clk_i                (clk_i),
    .rst_ni               (rst_ni),
    .testmode_i           (test_mode_i),
    .axi_req_i            (axi_req_i),
    .axi_rsp_o            (axi_resp_o),
    .obi_req_o            (obi_req),
    .obi_rsp_i            (obi_rsp),
    .req_aw_id_o          (axi_in_aw_id),
    .req_aw_user_o        (axi_in_aw_user),
    .req_w_user_o         (),
    .req_write_aid_i      (obi_in_write_aid),
    .req_write_auser_i    ('0),
    .req_write_wuser_i    ('0),
    .req_ar_id_o          (axi_in_ar_id),
    .req_ar_user_o        (axi_in_ar_user),
    .req_read_aid_i       (obi_in_read_aid),
    .req_read_auser_i     ('0),
    .rsp_write_aw_user_o  (),
    .rsp_write_w_user_o   (),
    .rsp_write_bank_strb_o(axi_in_rsp_write_bank_strobe),
    .rsp_write_rid_o      (obi_in_rsp_write_rid),
    .rsp_write_ruser_o    (),
    .rsp_write_last_o     (),
    .rsp_write_hs_o       (),
    .rsp_b_user_i         (axi_in_b_user),
    .rsp_read_ar_user_o   (),
    .rsp_read_size_enable_o(axi_in_rsp_read_size_enable),
    .rsp_read_rid_o       (obi_in_rsp_read_rid),
    .rsp_read_ruser_o     (),
    .rsp_r_user_i         (axi_in_r_user)
  );

  /////////////////
  // SRAM macros //
  /////////////////

  logic                      mem_req;
  logic                      mem_we;
  logic [AxiAddrWidth-1:0]   mem_addr;
  logic [AxiDataWidth-1:0]   mem_wdata;
  logic [AxiDataWidth/8-1:0] mem_be;
  logic [AxiDataWidth-1:0]   mem_rdata;

  obi_atop_resolver #(
    .SbrPortObiCfg            (MgrObiCfg),
    .MgrPortObiCfg            (SbrObiCfg),
    .sbr_port_obi_req_t       (mgr_obi_req_t),
    .sbr_port_obi_rsp_t       (mgr_obi_rsp_t),
    .mgr_port_obi_req_t       (sbr_obi_req_t),
    .mgr_port_obi_rsp_t       (sbr_obi_rsp_t),
    .mgr_port_obi_a_optional_t(sbr_obi_a_optional_t),
    .mgr_port_obi_r_optional_t(sbr_obi_r_optional_t),
    .LrScEnable               (1'b1),
    .RiscvWordWidth           (32),
    .NumTxns                  (ObiLatency)
  ) i_obi_atop_resolver (
    .clk_i         (clk_i),
    .rst_ni        (rst_ni),
    .testmode_i    (test_mode_i),
    .sbr_port_req_i(obi_req),
    .sbr_port_rsp_o(obi_rsp),
    .mgr_port_req_o(mem_obi_req),
    .mgr_port_rsp_i(mem_obi_rsp)
  );

  obi_cut #(
    .ObiCfg      (SbrObiCfg),
    .obi_a_chan_t(sbr_obi_a_chan_t),
    .obi_r_chan_t(sbr_obi_r_chan_t),
    .obi_req_t   (sbr_obi_req_t),
    .obi_rsp_t   (sbr_obi_rsp_t)
  ) i_obi_cut (
    .clk_i         (clk_i),
    .rst_ni        (rst_ni),
    .sbr_port_req_i(mem_obi_req),
    .sbr_port_rsp_o(mem_obi_rsp),
    .mgr_port_req_o(mem_obi_req_cut),
    .mgr_port_rsp_i(mem_obi_rsp_cut)
  );

  obi_sram_shim #(
    .ObiCfg   (SbrObiCfg),
    .obi_req_t(sbr_obi_req_t),
    .obi_rsp_t(sbr_obi_rsp_t)
  ) i_sram_shim_bank (
    .clk_i    (clk_i),
    .rst_ni   (rst_ni),
    .obi_req_i(mem_obi_req_cut),
    .obi_rsp_o(mem_obi_rsp_cut),
    .req_o    (mem_req),
    .we_o     (mem_we),
    .addr_o   (mem_addr),
    .wdata_o  (mem_wdata),
    .be_o     (mem_be),
    .gnt_i    (1'b1),
    .rdata_i  (mem_rdata)
  );

  logic [NumBanksPerWord-1:0][(SramRowSelWidth > 0) ? SramRowSelWidth-1 : 0:0] sram_macro_sel, sram_macro_sel_q;
  logic [NumBanksPerWord-1:0][  SramAddrWidth-1:0]                    sram_addr;
  logic [    NumBankRows-1:0][NumBanksPerWord-1:0][SramDataWidth-1:0] sram_rdata_split;

  logic [NumBanksPerWord-1:0][  SramDataWidth-1:0]                    sram_wdata;
  logic [NumBanksPerWord-1:0][SramDataWidth/8-1:0]                    sram_be;

  for (genvar i = 0; i < NumBanksPerWord; i++) begin : gen_addresses
    assign sram_addr[i] = mem_addr[SramAddrWidthOffset+:SramAddrWidth];
    
    if (SramRowSelWidth > 0) begin : gen_sram_row_sel
      assign sram_macro_sel[i] = mem_addr[SramRowSelOffset+:SramRowSelWidth];
    end else begin : gen_no_sram_row_sel
      assign sram_macro_sel[i] = '0;
    end
    
    `FFL(sram_macro_sel_q[i], sram_macro_sel[i], mem_req & ~mem_we, '0);
    
    assign sram_wdata[i] = mem_wdata[i*SramDataWidth+:SramDataWidth];
    assign sram_be[i]    = mem_be[i*SramDataWidth/8+:SramDataWidth/8];
    assign mem_rdata[i*SramDataWidth+:SramDataWidth] = sram_rdata_split[sram_macro_sel_q[i]][i];
  end

  for (genvar c = 0; c < NumBanksPerWord; c++) begin : gen_sram_banks
    for (genvar r = 0; r < NumBankRows; r++) begin : gen_sram_macros
      tc_sram #(
        .NumWords (SramNumWords),
        .DataWidth(SramDataWidth),
        .NumPorts (1),
        .Latency  (1)
      ) i_sram (
        .clk_i  (clk_i),
        .rst_ni (rst_ni),
        .req_i  (mem_req && (sram_macro_sel[c] == r)),
        .we_i   (mem_we && (sram_macro_sel[c] == r)),
        .addr_i (sram_addr[c]),
        .wdata_i(sram_wdata[c]),
        .be_i   (sram_be[c]),
        .rdata_o(sram_rdata_split[r][c])
      );
    end
  end

endmodule
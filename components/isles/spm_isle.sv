// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// SPM Memory Wrapper (Topology-Agnostic)
// Extracted and generalized from Gwaihir's spm_tile.sv

// BENDER: name="axi"
// BENDER: name="common_cells"

`include "axi/assign.svh"
`include "axi/typedef.svh"
`include "common_cells/registers.svh"

module spm_isle #(
  parameter int unsigned AxiAddrWidth    = 48,
  parameter int unsigned AxiDataWidth    = 64,
  parameter int unsigned AxiInIdWidth    = 5,
  parameter int unsigned AxiUserWidth    = 2,
  parameter int unsigned AxiMaxWriteTxns = 1,
  parameter int unsigned InstanceWindowSize      = 32'h00040000,
  parameter int unsigned SpmTileSize     = InstanceWindowSize,
  // NO 'InstanceBaseAddr' HERE, DELIBERATELY. The instance identity convention
  // (docs/hw/subtile_standardization.md 2.6) is opt-in from the header, and this
  // isle decodes nothing against a base address: it answers on the low address
  // bits of whatever transaction the tile hands it. Declaring the parameter used
  // to make the generator fill it PER INSTANCE, and a differing parameter value
  // is a distinct module for Verilator: eight identical memory tiles became eight
  // hierarchical specializations, verilated and compiled eight times over
  // (measured on noc, 2026-08-20). An unused parameter is not free.
  parameter int unsigned SpmWordsPerBank = 1024,
  parameter int unsigned SpmDataWidth    = 64,
  parameter type         axi_req_t       = logic,
  parameter type         axi_resp_t      = logic,
  // Memory preloading standardization parameters
  // PreloadType: Tells the generator that this memory uses interleaved multi-bank preloading.
  localparam string PreloadType = "interleaved",
  // PreloadTemplate: Hierarchical path from module top to individual tc_sram array instances.
  localparam string PreloadTemplate = "gen_spm_bank_col[{group}].gen_spm_bank_row[{bank}].i_spm.sram",
  // PreloadNumGroups: Number of bank groups (columns) inside the interleaved memory.
  localparam int unsigned PreloadNumGroups = AxiDataWidth / SpmDataWidth,
  // PreloadBankWidth: Data width of a single physical SRAM bank in bits.
  localparam int unsigned PreloadBankWidth = SpmDataWidth,
  // PreloadBanksPerGroup: Number of physical SRAM banks in each group (rows).
  localparam int unsigned PreloadBanksPerGroup = (SpmTileSize / (AxiDataWidth / 8)) / SpmWordsPerBank,
  // PreloadInterleave: Physical interleaving scheme seen by the hex splitter.
  // "lane-group" means {group} is the data lane of the AXI word (gen_spm_bank_col, always all
  // written together) while {bank} is the depth row selected by the high address bits
  // (gen_spm_bank_row). This is the opposite of the "word-group" scheme used by l2_isle.
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

  // -----------------------------------------------------------------------
  // Dynamic Array Calculation
  // -----------------------------------------------------------------------
  localparam int unsigned SpmNumBanksPerWord = AxiDataWidth / SpmDataWidth;
  localparam int unsigned SpmNumBankRows     = (SpmTileSize / (AxiDataWidth / 8)) / SpmWordsPerBank;

  localparam int unsigned SpmByteOffsetWidth = $clog2(SpmDataWidth / 8);
  localparam int unsigned SpmBankSelWidth    = (SpmNumBanksPerWord > 1) ? $clog2(SpmNumBanksPerWord) : 32'd0;
  localparam int unsigned SpmAddrWidth       = $clog2(SpmWordsPerBank);
  localparam int unsigned SpmRowSelWidth     = (SpmNumBankRows > 1) ? $clog2(SpmNumBankRows) : 32'd0;

  localparam int unsigned SpmBankSelOffset   = SpmByteOffsetWidth;
  localparam int unsigned SpmAddrWidthOffset = SpmBankSelOffset + SpmBankSelWidth;
  localparam int unsigned SpmRowSelOffset    = SpmAddrWidthOffset + SpmAddrWidth;

  // -----------------------------------------------------------------------
  // AXI Internal Types
  // -----------------------------------------------------------------------
  typedef logic [AxiAddrWidth-1:0]   addr_t;
  typedef logic [AxiDataWidth-1:0]   data_t;
  typedef logic [AxiDataWidth/8-1:0] strb_t;
  typedef logic [AxiInIdWidth-1:0]   id_t;
  typedef logic [AxiUserWidth-1:0]   user_t;

  `AXI_TYPEDEF_ALL(spm, addr_t, id_t, data_t, strb_t, user_t)

  spm_req_t  axi_req, axi_filtered_req, axi_cut_req;
  spm_resp_t axi_rsp, axi_filtered_rsp, axi_cut_rsp;

  // SystemVerilog transparently casts structurally identical structs
  assign axi_req = axi_req_i;
  assign axi_resp_o = axi_rsp;

  // -----------------------------------------------------------------------
  // ATOP Filter (SPM does not support HW atomics, blocks them)
  // -----------------------------------------------------------------------
  axi_atop_filter #(
    .AxiIdWidth      ( AxiInIdWidth    ),
    .AxiMaxWriteTxns ( AxiMaxWriteTxns ),
    .axi_req_t       ( spm_req_t       ),
    .axi_resp_t      ( spm_resp_t      )
  ) i_axi_atop_filter (
    .clk_i      ( clk_i            ),
    .rst_ni     ( rst_ni           ),
    .slv_req_i  ( axi_req          ),
    .slv_resp_o ( axi_rsp          ),
    .mst_req_o  ( axi_filtered_req ),
    .mst_resp_i ( axi_filtered_rsp )
  );

  // -----------------------------------------------------------------------
  // AXI Pipeline Cut
  // -----------------------------------------------------------------------
  axi_cut #(
    .aw_chan_t  ( spm_aw_chan_t ),
    .w_chan_t   ( spm_w_chan_t  ),
    .b_chan_t   ( spm_b_chan_t  ),
    .ar_chan_t  ( spm_ar_chan_t ),
    .r_chan_t   ( spm_r_chan_t  ),
    .axi_req_t  ( spm_req_t     ),
    .axi_resp_t ( spm_resp_t    )
  ) i_axi_cut (
    .clk_i      ( clk_i            ),
    .rst_ni     ( rst_ni           ),
    .slv_req_i  ( axi_filtered_req ),
    .slv_resp_o ( axi_filtered_rsp ),
    .mst_req_o  ( axi_cut_req      ),
    .mst_resp_i ( axi_cut_rsp      )
  );

  // -----------------------------------------------------------------------
  // AXI to Memory Converter
  // -----------------------------------------------------------------------
  typedef logic [$clog2(SpmTileSize)-1:0] mem_addr_t;
  typedef logic [SpmDataWidth-1:0]        mem_data_t;
  typedef logic [SpmDataWidth/8-1:0]      mem_strb_t;

  logic      [SpmNumBanksPerWord-1:0] mem_req_d, mem_req_q;
  logic      [SpmNumBanksPerWord-1:0] mem_we;
  mem_addr_t [SpmNumBanksPerWord-1:0] mem_addr;
  mem_data_t [SpmNumBanksPerWord-1:0] mem_wdata, mem_rdata;
  mem_strb_t [SpmNumBanksPerWord-1:0] mem_strb;

  axi_to_mem #(
    .axi_req_t    ( spm_req_t           ),
    .axi_resp_t   ( spm_resp_t          ),
    .AddrWidth    ( $clog2(SpmTileSize) ),
    .DataWidth    ( AxiDataWidth        ),
    .IdWidth      ( AxiInIdWidth        ),
    .NumBanks     ( SpmNumBanksPerWord  ),
    .BufDepth     ( 1                   ),
    .HideStrb     ( 1'b0                ),
    .OutFifoDepth ( 1                   )
  ) i_axi_to_mem (
    .clk_i,
    .rst_ni,
    .busy_o      ( /* unused */ ),
    .axi_req_i   ( axi_cut_req  ),
    .axi_resp_o  ( axi_cut_rsp  ),
    .mem_req_o   ( mem_req_d    ),
    .mem_gnt_i   ( '1           ),
    .mem_addr_o  ( mem_addr     ),
    .mem_wdata_o ( mem_wdata    ),
    .mem_strb_o  ( mem_strb     ),
    .mem_atop_o  ( /* unused */ ),
    .mem_we_o    ( mem_we       ),
    .mem_rvalid_i( mem_req_q    ),
    .mem_rdata_i ( mem_rdata    )
  );

  `FF(mem_req_q, mem_req_d, '0)

  // -----------------------------------------------------------------------
  // SPM SRAM Macros & Address Multiplexing
  // -----------------------------------------------------------------------
  typedef logic [((SpmRowSelWidth > 0) ? SpmRowSelWidth-1 : 0) : 0] row_sel_t;

  logic      [SpmNumBanksPerWord-1:0]                         spm_req;
  logic      [SpmNumBanksPerWord-1:0]                         spm_we;
  mem_data_t [SpmNumBanksPerWord-1:0]                         spm_wdata;
  mem_strb_t [SpmNumBanksPerWord-1:0]                         spm_strb;
  mem_data_t [    SpmNumBankRows-1:0][SpmNumBanksPerWord-1:0] spm_rdata;
  logic      [SpmNumBanksPerWord-1:0][      SpmAddrWidth-1:0] spm_addr;

  row_sel_t [SpmNumBanksPerWord-1:0] spm_bank_row_sel_q, spm_bank_row_sel_d;

  for (genvar b = 0; b < SpmNumBanksPerWord; b++) begin : gen_spm_addressing
    assign spm_addr[b] = mem_addr[b][SpmAddrWidthOffset+:SpmAddrWidth];

    if (SpmRowSelWidth > 0) begin : gen_spm_row_sel
      assign spm_bank_row_sel_d[b] = mem_addr[b][SpmRowSelOffset+:SpmRowSelWidth];
    end else begin : gen_no_spm_row_sel
      assign spm_bank_row_sel_d[b] = '0;
    end

    assign mem_rdata[b] = spm_rdata[spm_bank_row_sel_q[b]][b];
    assign spm_wdata[b] = mem_wdata[b];
    assign spm_strb[b]  = mem_strb[b];
    assign spm_we[b]    = mem_we[b];
    assign spm_req[b]   = mem_req_d[b];
  end
  
  `FF(spm_bank_row_sel_q, spm_bank_row_sel_d, '0)

  for (genvar c = 0; c < SpmNumBanksPerWord; c++) begin : gen_spm_bank_col
    for (genvar r = 0; r < SpmNumBankRows; r++) begin : gen_spm_bank_row
      tc_sram #(
        .NumWords ( SpmWordsPerBank ),
        .DataWidth( SpmDataWidth    ),
        .NumPorts ( 1               ),
        .Latency  ( 1               )
      ) i_spm (
        .clk_i,
        .rst_ni,
        .req_i  ( spm_req[c] && (spm_bank_row_sel_d[c] == r) ),
        .we_i   ( spm_we[c] ),
        .addr_i ( spm_addr[c] ),
        .wdata_i( spm_wdata[c] ),
        .be_i   ( spm_strb[c] ),
        .rdata_o( spm_rdata[r][c] )
      );
    end
  end

endmodule

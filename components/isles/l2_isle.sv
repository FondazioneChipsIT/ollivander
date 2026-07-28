// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// L2 Memory Wrapper
// Formatted for Ollivander SoC generator
//
// BENDER: name="axi"
// BENDER: name="register_interface"
// BENDER: name="dyn_mem"

`include "axi/typedef.svh"
module l2_isle
  import ollivander_soc_pkg::*;
  import axi_pkg::*;
  import dyn_mem_pkg::*;
#(
  /// AXI Ports settings
  parameter int unsigned NumPort      = 2,
  parameter int unsigned AxiAddrWidth = 48,
  parameter int unsigned AxiDataWidth = 64,
  parameter int unsigned AxiInIdWidth = 5,
  parameter int unsigned AxiUserWidth = 1,
  parameter int unsigned AxiMaxTrans  = 8,
  parameter int unsigned LogDepth     = 3,
  parameter int unsigned CdcSyncStages  = 2,
  parameter int unsigned AxiMaxReadTxns   = ollivander_soc_pkg::LlcMaxReadTxns,
  parameter int unsigned AxiMaxWriteTxns  = ollivander_soc_pkg::LlcMaxWriteTxns,
  parameter int unsigned AxiUserAmoMsb    = ollivander_soc_pkg::AxiUserAmoMsb,
  parameter int unsigned AxiUserAmoLsb    = ollivander_soc_pkg::AxiUserAmoLsb,
  parameter int unsigned L2AmoNumCuts     = ollivander_soc_pkg::LlcAmoNumCuts,
  parameter int unsigned AxiUserEccErrBit = ollivander_soc_pkg::AxiUserEccErrBit,
  /// ECC Reg Bus
  parameter type         reg_req_t = logic,
  parameter type         reg_rsp_t = logic,
  /// Mapping rules
  parameter int unsigned NumRules   = dyn_mem_pkg::NUM_MAP_TYPES * NumPort,
  /// L2 Memory settings
  parameter logic [63:0] L2BaseAddr = 64'h88000000,
  parameter int unsigned L2MemSize  = 32'h00200000,
  /// Non-changable parameters
  localparam int unsigned AxiStrbWidth    = AxiDataWidth / 8,
  // Memory preloading standardization parameters
  // PreloadType: Tells the generator that this memory uses interleaved multi-bank preloading.
  localparam string PreloadType = "interleaved",
  // PreloadTemplate: The hierarchical path from the module top to the individual tc_sram array instances.
  // This path traverses four levels of third-party hierarchy (l2_top -> dyn_mem_bank_group ->
  // ecc_sram_wrap -> tc_sram), and ecc_sram_wrap is declared deprecated by redundancy_cells in
  // favour of ecc_sram. When dyn_mem migrates, the string below stops resolving and the generated
  // testbench fails to elaborate: the error surfaces in tb_<project>.sv, but the knowledge that
  // causes it lives here, and here is where it must be updated.
  localparam string PreloadTemplate = "i_l2_top.gen_bank_group[{group}].i_dyn_mem_bank_group.genblk1[{bank}].i_ecc_sram_wrap.i_bank.sram",
  // PreloadNumGroups: Number of bank groups inside the interleaved memory.
  localparam int unsigned PreloadNumGroups = 2,
  // PreloadBankWidth: Data width of a single physical SRAM bank in bits.
  localparam int unsigned PreloadBankWidth = 32,
  // PreloadBanksPerGroup: Number of physical SRAM banks in each group (rows).
  localparam int unsigned PreloadBanksPerGroup = AxiDataWidth / PreloadBankWidth,
  // PreloadInterleave: Physical interleaving scheme seen by the hex splitter.
  // "word-group" means consecutive AXI words rotate across the two {group} bank groups of
  // l2_top, and each AXI word is then sliced lane-by-lane across the {bank} macros of the
  // selected group. This is the opposite of the "lane-group" scheme used by sram_isle/spm_isle.
  localparam string PreloadInterleave = "word-group",
  // Memory ECC configuration parameters
  // HasEcc: 1 indicates this memory implements Error Correction Codes (ECC)
  localparam bit HasEcc = 1,
  // EccType: Specifies the ECC scheme (matching a loaded scheme configuration file)
  localparam string EccType = "secded_39_32",
  // CDC Parameters
  parameter int unsigned AsyncAxiInAwWidth =
                         (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth,
                                                         AxiInIdWidth,
                                                         AxiUserWidth),
  parameter int unsigned AsyncAxiInWWidth  =
                          (2**LogDepth)*axi_pkg::w_width(AxiDataWidth,
                                                         AxiUserWidth),
  parameter int unsigned AsyncAxiInRWidth  =
                          (2**LogDepth)*axi_pkg::r_width(AxiDataWidth,
                                                         AxiInIdWidth,
                                                         AxiUserWidth),
  parameter int unsigned AsyncAxiInBWidth  =
                          (2**LogDepth)*axi_pkg::b_width(AxiInIdWidth,
                                                         AxiUserWidth),
  parameter int unsigned AsyncAxiInArWidth =
                          (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth,
                                                          AxiInIdWidth,
                                                          AxiUserWidth)
)(
  input  logic                            clk_i            ,
  input  logic                            rst_ni           ,
  input  logic                            pwr_on_rst_ni    ,
  input  logic [NumPort-1:0][AsyncAxiInArWidth-1:0] async_axi_in_ar_data_i,
  input  logic [NumPort-1:0][       LogDepth:0] async_axi_in_ar_wptr_i,
  output logic [NumPort-1:0][       LogDepth:0] async_axi_in_ar_rptr_o,
  input  logic [NumPort-1:0][AsyncAxiInAwWidth-1:0] async_axi_in_aw_data_i,
  input  logic [NumPort-1:0][       LogDepth:0] async_axi_in_aw_wptr_i,
  output logic [NumPort-1:0][       LogDepth:0] async_axi_in_aw_rptr_o,
  output logic [NumPort-1:0][ AsyncAxiInBWidth-1:0] async_axi_in_b_data_o ,
  output logic [NumPort-1:0][       LogDepth:0] async_axi_in_b_wptr_o ,
  input  logic [NumPort-1:0][       LogDepth:0] async_axi_in_b_rptr_i ,
  output logic [NumPort-1:0][ AsyncAxiInRWidth-1:0] async_axi_in_r_data_o ,
  output logic [NumPort-1:0][       LogDepth:0] async_axi_in_r_wptr_o ,
  input  logic [NumPort-1:0][       LogDepth:0] async_axi_in_r_rptr_i ,
  input  logic [NumPort-1:0][ AsyncAxiInWWidth-1:0] async_axi_in_w_data_i ,
  input  logic [NumPort-1:0][       LogDepth:0] async_axi_in_w_wptr_i ,
  output logic [NumPort-1:0][       LogDepth:0] async_axi_in_w_rptr_o ,
  input  logic                                  reg_async_slv_req_i,
  output logic                                  reg_async_slv_ack_o,
  input  reg_req_t                              reg_async_slv_data_i,
  output logic                                  reg_async_slv_req_o,
  input  logic                                  reg_async_slv_ack_i,
  output reg_rsp_t                              reg_async_slv_data_o,
  output logic                            ecc_error_o
);

// verilog_lint: waive-start line-length
`AXI_TYPEDEF_ALL_CT(axi_async, axi_async_req_t, axi_async_rsp_t, logic [AxiAddrWidth-1:0], logic [AxiInIdWidth-1:0], logic [AxiDataWidth-1:0], logic [AxiStrbWidth-1:0], logic [AxiUserWidth-1:0])
// verilog_lint: waive-stop line-length

axi_async_req_t [NumPort-1:0] axi_async_req;
axi_async_rsp_t [NumPort-1:0] axi_async_rsp;

for (genvar i = 0; i < NumPort; i++) begin: gen_cdc_fifos
  axi_cdc_dst #(
    .LogDepth   ( LogDepth            ),
    .SyncStages ( CdcSyncStages       ),
    .aw_chan_t  ( axi_async_aw_chan_t ),
    .w_chan_t   ( axi_async_w_chan_t  ),
    .b_chan_t   ( axi_async_b_chan_t  ),
    .ar_chan_t  ( axi_async_ar_chan_t ),
    .r_chan_t   ( axi_async_r_chan_t  ),
    .axi_req_t  ( axi_async_req_t     ),
    .axi_resp_t ( axi_async_rsp_t     )
  ) i_dst_cdc   (
    // asynchronous slave port
    .async_data_slave_aw_data_i ( async_axi_in_aw_data_i [i] ),
    .async_data_slave_aw_wptr_i ( async_axi_in_aw_wptr_i [i] ),
    .async_data_slave_aw_rptr_o ( async_axi_in_aw_rptr_o [i] ),
    .async_data_slave_w_data_i  ( async_axi_in_w_data_i  [i] ),
    .async_data_slave_w_wptr_i  ( async_axi_in_w_wptr_i  [i] ),
    .async_data_slave_w_rptr_o  ( async_axi_in_w_rptr_o  [i] ),
    .async_data_slave_b_data_o  ( async_axi_in_b_data_o  [i] ),
    .async_data_slave_b_wptr_o  ( async_axi_in_b_wptr_o  [i] ),
    .async_data_slave_b_rptr_i  ( async_axi_in_b_rptr_i  [i] ),
    .async_data_slave_ar_data_i ( async_axi_in_ar_data_i [i] ),
    .async_data_slave_ar_wptr_i ( async_axi_in_ar_wptr_i [i] ),
    .async_data_slave_ar_rptr_o ( async_axi_in_ar_rptr_o [i] ),
    .async_data_slave_r_data_o  ( async_axi_in_r_data_o  [i] ),
    .async_data_slave_r_wptr_o  ( async_axi_in_r_wptr_o  [i] ),
    .async_data_slave_r_rptr_i  ( async_axi_in_r_rptr_i  [i] ),
    // synchronous master port
    .dst_clk_i  ( clk_i             ),
    .dst_rst_ni ( pwr_on_rst_ni     ),
    .dst_req_o  ( axi_async_req [i] ),
    .dst_resp_i ( axi_async_rsp [i] )
  );
end

reg_req_t reg_bus_req;
reg_rsp_t reg_bus_rsp;

reg_cdc_dst #(
    .CDC_KIND ( "cdc_4phase" ),
    .req_t     ( reg_req_t ),
    .rsp_t     ( reg_rsp_t )
 ) i_reg_cdc_dst (
     .dst_clk_i   ( clk_i                       ),
     .dst_rst_ni  ( pwr_on_rst_ni               ),
     .dst_req_o   ( reg_bus_req                 ),
     .dst_rsp_i   ( reg_bus_rsp                 ),

     .async_req_i ( reg_async_slv_req_i         ),
     .async_ack_o ( reg_async_slv_ack_o         ),
     .async_data_i( reg_async_slv_data_i        ),

     .async_req_o ( reg_async_slv_req_o         ),
     .async_ack_i ( reg_async_slv_ack_i         ),
     .async_data_o( reg_async_slv_data_o        )
 );

typedef struct packed {
  int unsigned             idx;
  logic [AxiAddrWidth-1:0] start_addr;
  logic [AxiAddrWidth-1:0] end_addr;
} map_rule_t;

localparam logic [63:0] L2Port0InterlBase    = L2BaseAddr;
localparam logic [63:0] L2Port0NonInterlBase = L2BaseAddr + L2MemSize / 2;
localparam logic [63:0] L2Port1InterlBase    = L2BaseAddr + L2MemSize;
localparam logic [63:0] L2Port1NonInterlBase = L2BaseAddr + L2MemSize + L2MemSize / 2;

localparam map_rule_t [NumRules-1:0] MappingRules = '{
  '{idx       : dyn_mem_pkg::INTERLEAVE,
    start_addr: L2Port0InterlBase,
    end_addr  : L2Port0InterlBase + L2MemSize/2},
  '{idx       : dyn_mem_pkg::NONE_INTER,
    start_addr: L2Port0NonInterlBase,
    end_addr  : L2Port0NonInterlBase + L2MemSize/2},
  '{idx       : dyn_mem_pkg::INTERLEAVE,
    start_addr: L2Port1InterlBase,
    end_addr  : L2Port1InterlBase + L2MemSize/2},
  '{idx       : dyn_mem_pkg::NONE_INTER,
    start_addr: L2Port1NonInterlBase,
    end_addr  : L2Port1NonInterlBase + L2MemSize/2}
};

dyn_mem_top #(
  .NUM_PORT            ( NumPort         ),
  .AXI_ADDR_WIDTH      ( AxiAddrWidth    ),
  .AXI_DATA_WIDTH      ( AxiDataWidth    ),
  .AXI_ID_WIDTH        ( AxiInIdWidth    ),
  .AXI_USER_WIDTH      ( AxiUserWidth    ),
  .NUM_MAP_RULES       ( NumRules        ),
  .L2_MEM_SIZE_IN_BYTE ( L2MemSize       ),
  .map_rule_t          ( map_rule_t      ),
  .ATM_MAX_READ_TXN    ( AxiMaxReadTxns  ),
  .ATM_MAX_WRIT_TXN    ( AxiMaxWriteTxns ),
  .ATM_USER_AS_ID      ( 1               ),
  .ATM_USER_ID_MSB     ( AxiUserAmoMsb   ),
  .ATM_USER_ID_LSB     ( AxiUserAmoLsb   ),
  .ATM_RISCV_WORD      ( 64              ),
  .ATM_NUM_CUTS        ( L2AmoNumCuts    ),
  .AXI_USER_ECC_ERR    ( 1'b1            ),
  .AXI_USER_ECC_ERR_BIT( AxiUserEccErrBit),
  .l2_ecc_reg_req_t    ( reg_req_t       ),
  .l2_ecc_reg_rsp_t    ( reg_rsp_t       ),
  .axi_req_t           ( axi_async_req_t ),
  .axi_resp_t          ( axi_async_rsp_t )
) i_l2_top             (
  .clk_i               ( clk_i           ),
  .rst_ni              ( rst_ni          ),
  .mapping_rules_i     ( MappingRules    ),
  .axi_req_i           ( axi_async_req   ),
  .axi_resp_o          ( axi_async_rsp   ),
  .l2_ecc_reg_req_i    ( reg_bus_req     ),
  .l2_ecc_reg_rsp_o    ( reg_bus_rsp     )
);

// Signal tied to avoid changing the interface
assign ecc_error_o = '0;

endmodule: l2_isle

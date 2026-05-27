// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the Mailbox Unit
// Encapsulates AMO support (riscv_atomics), AXI cuts, AXI-to-Reg conversion, 
// and the mailbox core itself. Synchronous to the Host clock domain.
//
// BENDER: name="mailbox_unit"
// BENDER: name="axi"
// BENDER: name="register_interface"

`include "axi/typedef.svh"

module mailbox_isle
  import ollivander_soc_pkg::*;
#(
  parameter int unsigned AxiAddrWidth    = 48,
  parameter int unsigned AxiDataWidth    = 64,
  parameter int unsigned AxiInIdWidth    = 4,
  parameter int unsigned AxiUserWidth    = 10,
  parameter int unsigned RegDataWidth    = 32,
  parameter int unsigned NumMailboxes    = 1,
  parameter int unsigned AxiMaxReadTxns  = ollivander_soc_pkg::RegMaxReadTxns,
  parameter int unsigned AxiMaxWriteTxns = ollivander_soc_pkg::RegMaxWriteTxns,
  parameter int unsigned AxiUserAmoMsb   = ollivander_soc_pkg::AxiUserAmoMsb,
  parameter int unsigned AxiUserAmoLsb   = ollivander_soc_pkg::AxiUserAmoLsb,
  parameter int unsigned AxiAmoNumCuts   = ollivander_soc_pkg::RegAmoNumCuts,
  parameter bit          RegAmoPostCut   = ollivander_soc_pkg::RegAmoPostCut,
  
  // AXI types
  parameter type axi_req_t      = logic,
  parameter type axi_resp_t     = logic,
  parameter type axi_aw_chan_t  = logic,
  parameter type axi_w_chan_t   = logic,
  parameter type axi_b_chan_t   = logic,
  parameter type axi_ar_chan_t  = logic,
  parameter type axi_r_chan_t   = logic,
  
  // REG types
  parameter type reg_req_t      = logic,
  parameter type reg_rsp_t      = logic
) (
  input  logic clk_i,
  input  logic rst_ni,

  // Synchronous AXI IN (Slave)
  input  axi_req_t  axi_req_i,
  output axi_resp_t axi_resp_o,

  // Interrupts OUT
  output logic [NumMailboxes-1:0] snd_irq_o
);

  // Intermediate AXI structs
  axi_req_t  axi_pre_amo_cut_req;
  axi_resp_t axi_pre_amo_cut_rsp;
  
  axi_req_t  axi_amo_req;
  axi_resp_t axi_amo_rsp;
  
  axi_req_t  axi_post_amo_cut_req;
  axi_resp_t axi_post_amo_cut_rsp;
  
  // Intermediate REG structs
  reg_req_t reg_mbox_req;
  reg_rsp_t reg_mbox_rsp;

  // 1. AXI Cut (Pre-AMO)
  axi_cut #(
    .Bypass     ( 1'b0 ),
    .aw_chan_t  ( axi_aw_chan_t ),
    .w_chan_t   ( axi_w_chan_t  ),
    .b_chan_t   ( axi_b_chan_t  ),
    .ar_chan_t  ( axi_ar_chan_t ),
    .r_chan_t   ( axi_r_chan_t  ),
    .axi_req_t  ( axi_req_t     ),
    .axi_resp_t ( axi_resp_t    )
  ) i_cut_pre_amo_mbox (
    .clk_i      ( clk_i               ),
    .rst_ni     ( rst_ni              ),
    .slv_req_i  ( axi_req_i           ),
    .slv_resp_o ( axi_resp_o          ),
    .mst_req_o  ( axi_pre_amo_cut_req ),
    .mst_resp_i ( axi_pre_amo_cut_rsp )
  );

  // 2. Shim atomics (not natively supported by Regbus)
  axi_riscv_atomics_structs #(
    .AxiAddrWidth     ( AxiAddrWidth    ),
    .AxiDataWidth     ( AxiDataWidth    ),
    .AxiIdWidth       ( AxiInIdWidth    ),
    .AxiUserWidth     ( AxiUserWidth    ),
    .AxiMaxReadTxns   ( AxiMaxReadTxns  ),
    .AxiMaxWriteTxns  ( AxiMaxWriteTxns ),
    .AxiUserAsId      ( 1               ),
    .AxiUserIdMsb     ( AxiUserAmoMsb   ),
    .AxiUserIdLsb     ( AxiUserAmoLsb   ),
    .RiscvWordWidth   ( 64              ),
    .NAxiCuts         ( AxiAmoNumCuts   ),
    .CutOupPopInpGnt  ( 1               ),
    .axi_req_t        ( axi_req_t       ),
    .axi_rsp_t        ( axi_resp_t      )
  ) i_atomics_mbox (
    .clk_i         ( clk_i               ),
    .rst_ni        ( rst_ni              ),
    .axi_slv_req_i ( axi_pre_amo_cut_req ),
    .axi_slv_rsp_o ( axi_pre_amo_cut_rsp ),
    .axi_mst_req_o ( axi_amo_req         ),
    .axi_mst_rsp_i ( axi_amo_rsp         )
  );

  // 3. AXI Cut (Post-AMO)
  axi_cut #(
    .Bypass     ( ~RegAmoPostCut ),
    .aw_chan_t  ( axi_aw_chan_t ),
    .w_chan_t   ( axi_w_chan_t  ),
    .b_chan_t   ( axi_b_chan_t  ),
    .ar_chan_t  ( axi_ar_chan_t ),
    .r_chan_t   ( axi_r_chan_t  ),
    .axi_req_t  ( axi_req_t     ),
    .axi_resp_t ( axi_resp_t    )
  ) i_cut_post_amo_mbox (
    .clk_i      ( clk_i                ),
    .rst_ni     ( rst_ni               ),
    .slv_req_i  ( axi_amo_req          ),
    .slv_resp_o ( axi_amo_rsp          ),
    .mst_req_o  ( axi_post_amo_cut_req ),
    .mst_resp_i ( axi_post_amo_cut_rsp )
  );

  // 4. AXI to Regbus conversion
  axi_to_reg_v2 #(
    .AxiAddrWidth ( AxiAddrWidth  ),
    .AxiDataWidth ( AxiDataWidth  ),
    .AxiIdWidth   ( AxiInIdWidth  ),
    .AxiUserWidth ( AxiUserWidth  ),
    .RegDataWidth ( RegDataWidth  ),
    .axi_req_t    ( axi_req_t     ),
    .axi_rsp_t    ( axi_resp_t    ),
    .reg_req_t    ( reg_req_t     ),
    .reg_rsp_t    ( reg_rsp_t     )
  ) i_axi_to_reg_v2_mbox (
    .clk_i     ( clk_i                ),
    .rst_ni    ( rst_ni               ),
    .axi_req_i ( axi_post_amo_cut_req ),
    .axi_rsp_o ( axi_post_amo_cut_rsp ),
    .reg_req_o ( reg_mbox_req         ),
    .reg_rsp_i ( reg_mbox_rsp         ),
    .reg_id_o  ( /* unused */         ),
    .busy_o    ( /* unused */         )
  );

  // 5. The Mailbox Unit
  mailbox_unit #(
    .reg_req_t( reg_req_t    ),
    .reg_rsp_t( reg_rsp_t    ),
    .NumMbox  ( NumMailboxes )
  ) i_mailbox_unit (
    .clk_i     ( clk_i        ),
    .rst_ni    ( rst_ni       ),
    .reg_req_i ( reg_mbox_req ),
    .reg_rsp_o ( reg_mbox_rsp ),
    .snd_irq_o ( snd_irq_o    ),
    .rcv_irq_o ( /* unused */ )
  );

endmodule : mailbox_isle
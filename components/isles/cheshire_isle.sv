// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the Cheshire Host, implementing the SoC, AXI isolation,
// and CDC (Clock Domain Crossing) blocks, exposing uniform Ollivander interfaces.
//
// BENDER: name="cheshire"
// BENDER: name="axi"
// BENDER: name="register_interface"
// BENDER: name="apb"
// PEAKRDL: source="cheshire.rdl" map="cheshire"

`include "cheshire/typedef.svh"
`include "axi/typedef.svh"
`include "axi/assign.svh"

module cheshire_isle
  import axi_pkg::*;
  import ollivander_soc_pkg::*;
  import cheshire_pkg::*;
#(
  // =================================================================================
  // OLLIVANDER STANDARD PARAMETERS
  // =================================================================================
  parameter int unsigned AxiAddrWidth       = 48,
  parameter int unsigned AxiDataWidth       = 64,
  parameter int unsigned AxiUserWidth       = 10,
  parameter int unsigned AxiInIdWidth       = 4,
  parameter int unsigned AxiOutIdWidth      = 4,
  parameter int unsigned LogDepth           = 3,

  parameter int unsigned AsyncAxiInAwWidth  = 0,
  parameter int unsigned AsyncAxiInWWidth   = 0,
  parameter int unsigned AsyncAxiInBWidth   = 0,
  parameter int unsigned AsyncAxiInArWidth  = 0,
  parameter int unsigned AsyncAxiInRWidth   = 0,

  parameter int unsigned AsyncAxiOutAwWidth = 0,
  parameter int unsigned AsyncAxiOutWWidth  = 0,
  parameter int unsigned AsyncAxiOutBWidth  = 0,
  parameter int unsigned AsyncAxiOutArWidth = 0,
  parameter int unsigned AsyncAxiOutRWidth  = 0,

  parameter int unsigned AsyncAxiLlcAwWidth = 0,
  parameter int unsigned AsyncAxiLlcWWidth  = 0,
  parameter int unsigned AsyncAxiLlcBWidth  = 0,
  parameter int unsigned AsyncAxiLlcArWidth = 0,
  parameter int unsigned AsyncAxiLlcRWidth  = 0,

  // =================================================================================
  // CHESHIRE SPECIFIC PARAMETERS
  // =================================================================================
  parameter int unsigned CdcSyncStages = 2,
  parameter int unsigned LlcCdcSyncStages = CdcSyncStages,

  // =================================================================================
  // OLLIVANDER HOST STANDARD PARAMETERS
  // =================================================================================
  parameter int unsigned AxiNumMstAsync     = 0,
  parameter int unsigned AxiNumMstSync      = 0,
  parameter int unsigned AxiNumSlvAsync     = 0,
  parameter int unsigned AxiNumSlvSync      = 0,
  parameter int unsigned RegNumSlvAsync     = 0,
  parameter int unsigned RegNumSlvSync      = 0,
  parameter int unsigned NumIntrsIn         = 32,
  parameter int unsigned NumIntrsOut        = 32,
  parameter int unsigned NumIrqHarts        = 1,
  parameter int unsigned NumDbgHarts        = 1,
  localparam int unsigned NumIrqCtxts       = 2, // Number of interrupt contexts (M, S modes)
  // Ollivander Host Force-Boot configuration parameters
  // HasForceBoot: 1 indicates this host supports software force-booting in simulation
  localparam bit HasForceBoot = 1,
  // JTAG boot support (wip 2.1): this host carries a riscv-dbg debug module whose
  // system-bus master reaches the boot scratch registers at the HOST-INTERNAL
  // offset below (Cheshire's own register block; scratch[i] at +4*i). The offset
  // is host-owned knowledge, declared here exactly as ForceBootPath is, so the
  // generated testbench composes bus addresses without knowing any host internals.
  localparam bit HasJtagBoot = 1,
  localparam longint unsigned JtagScratchOffset = 64'h0300_0000,
  // Expected TAP IDCODE, checked by the VIP's jtag_init liveness handshake:
  // Cheshire's own '{version: 4'h1, part_num: 16'hc5e5, manufacturer: 11'h6d9, _one: 1}.
  localparam longint unsigned JtagIdCode = 64'h1c5e_5db3,
  // ForceBootPath: Hierarchical path from host wrapper top to the entry point scratch register
  localparam string ForceBootPath = "i_cheshire_soc.i_regs.field_storage.scratch[0].scratch.value",
  // ForceBootVal: Force value template (32-bit hex)
  localparam string ForceBootVal = "32'h00000000",
  parameter int unsigned NumCores           = 1,
  parameter int unsigned RtcFreq            = 32768,
  parameter bit          Bootrom            = 1,
  parameter bit          Uart               = 1,
  parameter bit          I2c                = 1,
  parameter bit          SpiHost            = 1,
  parameter bit          Dma                = 1,
  parameter bit          SerialLink         = 0,
  parameter bit          Vga                = 0,
  parameter bit          Snooper            = 1,
  parameter bit          IrqRouter          = 1,
  parameter int unsigned SpihNumCs          = 1,
  parameter int unsigned SlinkNumChan       = 1,
  parameter int unsigned SlinkNumLanes      = 8,
  // Serial-link preload contract (wip 2.1, wave two): the VIP instantiates an
  // off-chip twin of this host's serial link, and the twin's AXI geometry must
  // mirror the DUT side's EXACTLY or the wire framing disagrees. Declared as
  // host-owned knowledge, the same pattern as the Jtag* block; the id
  // width repeats the expression the Cfg assembly below uses for AxiMstIdWidth.
  // Tied to the SerialLink feature switch above: exporting the pins of a link
  // Cheshire was built without would hand the testbench dead wires - found
  // the hard way on 2026-08-22, when the first slink pilot's driver waited
  // forever for credits from a stubbed-out receiver.
  localparam bit HasSlinkPreload = SerialLink,
  localparam int unsigned SlinkAxiAddrWidth = AxiAddrWidth,
  localparam int unsigned SlinkAxiDataWidth = AxiDataWidth,
  localparam int unsigned SlinkAxiUserWidth = AxiUserWidth,
  localparam int unsigned SlinkAxiIdWidth   = (AxiOutIdWidth > 0 && AxiOutIdWidth <= 3) ? AxiOutIdWidth : 3,
  // External-master id-width contract (wip 2.1 wave two, latent-truncation
  // fix): the internal crossbar prepends the ORIGINATING MASTER's index to
  // every outgoing id, so the external id width is the effective master id
  // width plus clog2 of the master count - and the count GROWS with feature
  // switches. SerialLink added the fifth master and exposed a bit the fabric
  // had been silently truncating for the DMA and USB masters (which never
  // issued fabric-bound transactions in any shipped test). The sum mirrors
  // cheshire_pkg::gen_axi_in field by field, Usb pinned at DefaultCfg's 1,
  // INCLUDING its AxiExtNumMst term: the external masters this instance
  // receives (the NoC ingress, the parent's exported masters) join the same
  // crossbar and widen the same ids - counting only the internal ones left a
  // one-bit undercount on the mesh, silent because the masters above the
  // clog2 plateau never spoke (the same latency pattern, one week older).
  // The generator resolves it numerically (the AxiNumMst* values are driven
  // into host.parameters before resolution) and sizes the interconnect id
  // width so the fabric FOLLOWS the host - astral's and gwaihir's practice.
  // The elaboration check beside cheshire's own AxiSlvIdWidth below keeps
  // this expression honest against cheshire_pkg::gen_axi_in forever.
  // NOTE: single line on purpose - the generator's header parser captures a
  // fixed_param's value up to the end of ITS line, so a wrapped expression
  // reaches the resolver truncated (found the hard way, mesh pilot 2026-08-22).
  localparam int unsigned NumAxiInMasters  = NumCores + 1 + Dma + SerialLink + Vga + 1 + AxiNumMstAsync + AxiNumMstSync,
  localparam int unsigned AxiExtOutIdWidth = ((AxiOutIdWidth > 0 && AxiOutIdWidth <= 3) ? AxiOutIdWidth : 3) + $clog2(NumAxiInMasters),
  parameter int unsigned VgaRedWidth        = 5,
  parameter int unsigned VgaGreenWidth      = 6,
  parameter int unsigned VgaBlueWidth       = 5,
  parameter bit          LlcNotBypass       = 1,
  parameter int unsigned LlcSetAssoc        = 8,
  parameter int unsigned LlcNumLines        = 256,
  parameter int unsigned LlcNumBlocks       = 8,
  parameter bit          Cva6ExtCieOnTop    = 0,
  parameter int unsigned Cva6ExtCieLength   = 'h2000_0000,
  // The LLC-out window doubles as CVA6's cached+executable region ABOVE the CIE
  // ceiling (the CIE is anchored below 0x8000_0000 by construction, see
  // gen_cva6_cfg in cheshire_pkg.sv). A SoC that boots from a memory mapped
  // high must cover exactly that memory here and nothing more: anything else in
  // the window becomes CACHED for the host, and polling device memory (e.g. the
  // offload return slots in a cluster TCDM) through a cache spins on a stale
  // line forever. Defaults are the upstream DefaultCfg values.
  parameter longint unsigned LlcOutRegionStart = 64'h8000_0000,
  parameter longint unsigned LlcOutRegionEnd   = 64'h1_0000_0000,
  // Outstanding transaction limits for AXI isolators
  parameter int unsigned AxiMaxSlvTrans     = 32,
  parameter int unsigned AxiMaxMstTrans     = 32,
  // Standard interface types for synchronous links
  parameter type sync_axi_out_req_t  = ollivander_soc_pkg::soc_axi_slv_req_t,
  parameter type sync_axi_out_rsp_t  = ollivander_soc_pkg::soc_axi_slv_resp_t,
  parameter type sync_axi_in_req_t   = ollivander_soc_pkg::soc_axi_req_t,
  parameter type sync_axi_in_rsp_t   = ollivander_soc_pkg::soc_axi_resp_t,
  parameter type sync_reg_out_req_t  = ollivander_soc_pkg::soc_reg_req_t,
  parameter type sync_reg_out_rsp_t  = ollivander_soc_pkg::soc_reg_rsp_t,
  parameter type async_reg_out_req_t = ollivander_soc_pkg::soc_reg_req_t,
  parameter type async_reg_out_rsp_t = ollivander_soc_pkg::soc_reg_rsp_t,
  parameter type axi_llc_req_t       = ollivander_soc_pkg::soc_axi_llc_req_t,
  parameter type axi_llc_resp_t      = ollivander_soc_pkg::soc_axi_llc_resp_t
)(
  input  logic        clk_i      ,
  input  logic        rst_ni     ,
  input  logic        test_mode_i,
  input  logic [1:0]  boot_mode_i,
  input  logic        rt_clk_i   ,
  
  // Standard AXI LLC (DRAM) port
  input  logic                            async_axi_llc_isolate_i,
  output logic                            async_axi_llc_isolated_o,
  output logic [AsyncAxiLlcArWidth-1:0]   async_axi_llc_ar_data_o,
  output logic [            LogDepth:0]   async_axi_llc_ar_wptr_o,
  input  logic [            LogDepth:0]   async_axi_llc_ar_rptr_i,
  output logic [AsyncAxiLlcAwWidth-1:0]   async_axi_llc_aw_data_o,
  output logic [            LogDepth:0]   async_axi_llc_aw_wptr_o,
  input  logic [            LogDepth:0]   async_axi_llc_aw_rptr_i,
  input  logic [ AsyncAxiLlcBWidth-1:0]   async_axi_llc_b_data_i ,
  input  logic [            LogDepth:0]   async_axi_llc_b_wptr_i ,
  output logic [            LogDepth:0]   async_axi_llc_b_rptr_o ,
  input  logic [ AsyncAxiLlcRWidth-1:0]   async_axi_llc_r_data_i ,
  input  logic [            LogDepth:0]   async_axi_llc_r_wptr_i ,
  output logic [            LogDepth:0]   async_axi_llc_r_rptr_o ,
  output logic [ AsyncAxiLlcWWidth-1:0]   async_axi_llc_w_data_o ,
  output logic [            LogDepth:0]   async_axi_llc_w_wptr_o ,
  input  logic [            LogDepth:0]   async_axi_llc_w_rptr_i ,
  
  // Synchronous AXI LLC (DRAM) port
  output axi_llc_req_t                    axi_llc_req_o,
  input  axi_llc_resp_t                   axi_llc_resp_i,

  // Standard AXI OUT (Master to external slaves) ports
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0]                        async_axi_out_isolate_i,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0]                        async_axi_out_isolated_o,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][AsyncAxiOutArWidth-1:0] async_axi_out_ar_data_o,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_ar_wptr_o,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_ar_rptr_i,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][AsyncAxiOutAwWidth-1:0] async_axi_out_aw_data_o,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_aw_wptr_o,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_aw_rptr_i,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][ AsyncAxiOutBWidth-1:0] async_axi_out_b_data_i ,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_b_wptr_i ,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_b_rptr_o ,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][ AsyncAxiOutRWidth-1:0] async_axi_out_r_data_i ,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_r_wptr_i ,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_r_rptr_o ,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][ AsyncAxiOutWWidth-1:0] async_axi_out_w_data_o ,
  output logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_w_wptr_o ,
  input  logic [cheshire_pkg::iomsb(AxiNumSlvAsync):0][            LogDepth:0] async_axi_out_w_rptr_i ,
  
  // Asynchronous AXI IN (Slave from external masters) ports
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][AsyncAxiInArWidth-1:0] async_axi_in_ar_data_i,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_ar_wptr_i,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_ar_rptr_o,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][AsyncAxiInAwWidth-1:0] async_axi_in_aw_data_i,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_aw_wptr_i,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_aw_rptr_o,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][ AsyncAxiInBWidth-1:0] async_axi_in_b_data_o ,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_b_wptr_o ,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_b_rptr_i ,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][ AsyncAxiInRWidth-1:0] async_axi_in_r_data_o ,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_r_wptr_o ,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_r_rptr_i ,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][ AsyncAxiInWWidth-1:0] async_axi_in_w_data_i ,
  input  logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_w_wptr_i ,
  output logic [cheshire_pkg::iomsb(AxiNumMstAsync):0][           LogDepth:0] async_axi_in_w_rptr_o ,

  // Synchronous AXI IN (Slave from external masters like NoC)
  input  sync_axi_in_req_t  [cheshire_pkg::iomsb(AxiNumMstSync):0] axi_req_i,
  output sync_axi_in_rsp_t  [cheshire_pkg::iomsb(AxiNumMstSync):0] axi_resp_o,
  
  // Synchronous AXI OUT (Master to synchronous slaves like Mailboxes)
  output sync_axi_out_req_t [cheshire_pkg::iomsb(AxiNumSlvSync):0] axi_req_o,
  input  sync_axi_out_rsp_t [cheshire_pkg::iomsb(AxiNumSlvSync):0] axi_resp_i,
  
  // Standard Sync Reg Ports (Cheshire's clock domain)
  output sync_reg_out_req_t [cheshire_pkg::iomsb(RegNumSlvSync):0] reg_req_o,
  input  sync_reg_out_rsp_t [cheshire_pkg::iomsb(RegNumSlvSync):0] reg_rsp_i,
  
  // Standard Async Reg Ports (Other clock domains)
  output logic               [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_req_o,
  input  logic               [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_ack_i,
  output async_reg_out_req_t [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_data_o,
  input  logic               [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_req_i,
  output logic               [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_ack_o,
  input  async_reg_out_rsp_t [cheshire_pkg::iomsb(RegNumSlvAsync):0] reg_async_mst_data_i,
  
  // Interrupts
  input  logic [cheshire_pkg::iomsb(NumIntrsIn):0]              intr_ext_i,
  output logic [cheshire_pkg::iomsb(NumIntrsOut):0]             intr_ext_o,
  output logic [cheshire_pkg::iomsb(NumIrqCtxts*NumIrqHarts):0] xeip_ext_o,
  output logic [cheshire_pkg::iomsb(NumIrqHarts):0]             mtip_ext_o,
  output logic [cheshire_pkg::iomsb(NumIrqHarts):0]             msip_ext_o,
  // Debug & JTAG
  output logic                               dbg_active_o,
  output logic [cheshire_pkg::iomsb(NumDbgHarts):0] dbg_ext_req_o,
  input  logic [cheshire_pkg::iomsb(NumDbgHarts):0] dbg_ext_unavail_i,
  input  logic jtag_tck_i,
  input  logic jtag_trst_ni,
  input  logic jtag_tms_i,
  input  logic jtag_tdi_i,
  output logic jtag_tdo_o,
  output logic jtag_tdo_oe_o,
  // Interfaces
  output logic uart_tx_o,
  input  logic uart_rx_i,
  output logic uart_rts_no,
  output logic uart_dtr_no,
  input  logic uart_cts_ni,
  input  logic uart_dsr_ni,
  input  logic uart_dcd_ni,
  input  logic uart_rin_ni,
  output logic i2c_sda_o,
  input  logic i2c_sda_i,
  output logic i2c_sda_en_o,
  output logic i2c_scl_o,
  input  logic i2c_scl_i,
  output logic i2c_scl_en_o,
  output logic                 spi_sck_o,
  output logic                 spi_sck_en_o,
  output logic [SpihNumCs-1:0] spi_csb_o,
  output logic [SpihNumCs-1:0] spi_csb_en_o,
  output logic [ 3:0]          spi_sd_o,
  output logic [ 3:0]          spi_sd_en_o,
  input  logic [ 3:0]          spi_sd_i,
  input  logic [31:0] gpio_i,
  output logic [31:0] gpio_o,
  output logic [31:0] gpio_en_o,
  input  logic [SlinkNumChan-1:0]                    slink_rcv_clk_i,
  output logic [SlinkNumChan-1:0]                    slink_rcv_clk_o,
  input  logic [SlinkNumChan-1:0][SlinkNumLanes-1:0] slink_i,
  output logic [SlinkNumChan-1:0][SlinkNumLanes-1:0] slink_o,
  output logic                         vga_hsync_o,
  output logic                         vga_vsync_o,
  output logic [4:0]                   vga_red_o,
  output logic [5:0]                   vga_green_o,
  output logic [4:0]                   vga_blue_o ,
  // USB interface
  input  logic                         usb_clk_i  ,
  input  logic                         usb_rst_ni ,
  input  logic [UsbNumPorts-1:0]       usb_dm_i   ,
  output logic [UsbNumPorts-1:0]       usb_dm_o   ,
  output logic [UsbNumPorts-1:0]       usb_dm_oe_o,
  input  logic [UsbNumPorts-1:0]       usb_dp_i   ,
  output logic [UsbNumPorts-1:0]       usb_dp_o   ,
  output logic [UsbNumPorts-1:0]       usb_dp_oe_o
);

  // =================================================================================
  // CHESHIRE DYNAMIC CONFIGURATION BUILDER
  // =================================================================================
  // We build the complex Cfg struct internally taking advantage of SystemVerilog functions.
  // This allows Ollivander (Python) to only write simple flat parameters into ollivander_soc_pkg
  // while maintaining a completely standard interface for cheshire_isle.

  function automatic cheshire_cfg_t build_cheshire_cfg();
    cheshire_cfg_t cfg;
    // 1. Initialize with default configuration
    cfg = cheshire_pkg::DefaultCfg;
    
    // 2. Override with parameters dynamically generated by Ollivander
    
    // Global Bus Architecture (from parameter list)
    cfg.AddrWidth         = AxiAddrWidth;
    cfg.AxiDataWidth      = AxiDataWidth;
    cfg.AxiUserWidth      = AxiUserWidth;
    cfg.AxiMstIdWidth     = (AxiOutIdWidth > 0 && AxiOutIdWidth <= 3) ? AxiOutIdWidth : 3;

    // Host Parameters (from YAML 'host.parameters')
    cfg.NumCores          = NumCores;
    cfg.RtcFreq           = RtcFreq;

    // Hardware Features (from YAML 'host.parameters.features')
    cfg.Bootrom           = Bootrom;
    cfg.Uart              = Uart;
    cfg.I2c               = I2c;
    cfg.SpiHost           = SpiHost;
    cfg.Dma               = Dma;
    cfg.SerialLink        = SerialLink;

    // Outstanding transaction limits
    cfg.AxiMaxSlvTrans    = AxiMaxSlvTrans;
    cfg.AxiMaxMstTrans    = AxiMaxMstTrans;

    // Auto-calculated Topology Parameters & Arrays (Derived from YAML 'components')
    cfg.AxiExtNumSlv      = AxiNumSlvAsync + AxiNumSlvSync;
    cfg.AxiExtNumMst      = AxiNumMstAsync + AxiNumMstSync;
    cfg.AxiExtNumRules    = ollivander_soc_pkg::AxiExtNumRules;
    cfg.AxiExtRegionIdx   = ollivander_soc_pkg::AxiExtRegionIdx;
    cfg.AxiExtRegionStart = ollivander_soc_pkg::AxiExtRegionStart;
    cfg.AxiExtRegionEnd   = ollivander_soc_pkg::AxiExtRegionEnd;
    
    cfg.RegExtNumSlv      = RegNumSlvSync + RegNumSlvAsync;
    cfg.RegExtNumRules    = ollivander_soc_pkg::RegExtNumRules;
    cfg.RegExtRegionIdx   = ollivander_soc_pkg::RegExtRegionIdx;
    cfg.RegExtRegionStart = ollivander_soc_pkg::RegExtRegionStart;
    cfg.RegExtRegionEnd   = ollivander_soc_pkg::RegExtRegionEnd;

    cfg.NumExtInIntrs     = NumIntrsIn;
    cfg.NumExtOutIntrs    = NumIntrsOut;
    cfg.NumExtOutIntrTgts = 0; // This is now a fixed assumption of the wrapper
    cfg.NumExtIrqHarts    = NumIrqHarts;
    cfg.NumExtDbgHarts    = NumDbgHarts;
    
    // Caches, Atomics and Memory map parameters (from YAML 'system_settings' and 'host.parameters')
    cfg.LlcNotBypass      = LlcNotBypass;
    cfg.LlcSetAssoc       = LlcSetAssoc;
    cfg.LlcNumLines       = LlcNumLines;
    cfg.LlcNumBlocks      = LlcNumBlocks;
    cfg.Cva6ExtCieOnTop   = Cva6ExtCieOnTop;
    cfg.Cva6ExtCieLength  = Cva6ExtCieLength;
    cfg.LlcOutRegionStart = LlcOutRegionStart;
    cfg.LlcOutRegionEnd   = LlcOutRegionEnd;
    cfg.LlcMaxReadTxns    = ollivander_soc_pkg::LlcMaxReadTxns;
    cfg.LlcMaxWriteTxns   = ollivander_soc_pkg::LlcMaxWriteTxns;
    cfg.LlcAmoNumCuts     = ollivander_soc_pkg::LlcAmoNumCuts;
    cfg.LlcAmoPostCut     = ollivander_soc_pkg::LlcAmoPostCut;
    
    cfg.AxiUserAmoMsb     = ollivander_soc_pkg::AxiUserAmoMsb;
    cfg.AxiUserAmoLsb     = ollivander_soc_pkg::AxiUserAmoLsb;
    // The serial link raises one bit of the AMO field to tell its own atomics apart from a core's
    // ('user |= 1 << SlinkUserAmoBit' in cheshire_soc.sv), while each core writes its index into
    // the same field ('user[AmoMsb:AmoLsb] = CoreUserAmoOffs + i'). The bit must therefore be one
    // no core index can set, which is what cheshire's convention means by reserving the field's
    // MSB for the link - so it follows AxiUserAmoMsb rather than cheshire's own default of 1.
    // With the default and our three-bit field the two collide from the third core onwards, since
    // index 2 raises bit 1: two atomics that the LLC could no longer distinguish, silently.
    cfg.SlinkUserAmoBit   = ollivander_soc_pkg::AxiUserAmoMsb;

    // RegBus Atomics
    cfg.RegMaxReadTxns    = ollivander_soc_pkg::RegMaxReadTxns;
    cfg.RegMaxWriteTxns   = ollivander_soc_pkg::RegMaxWriteTxns;
    cfg.RegAmoNumCuts     = ollivander_soc_pkg::RegAmoNumCuts;
    cfg.RegAmoPostCut     = ollivander_soc_pkg::RegAmoPostCut;

    // Bus Error mapping
    cfg.AxiUserErrBits    = 1;
    cfg.AxiUserErrLsb     = ollivander_soc_pkg::AxiUserEccErrBit;

    return cfg;
  endfunction

  localparam cheshire_cfg_t Cfg = build_cheshire_cfg();

  // =================================================================================
  // INTERNAL TYPE DEFINITIONS
  // =================================================================================
  typedef logic [AxiDataWidth-1:0]   axi_data_t;
  typedef logic [AxiDataWidth/8-1:0] axi_strb_t;
  typedef logic [AxiAddrWidth-1:0]   axi_addr_t;
  typedef logic [AxiUserWidth-1:0]   axi_user_t;

  localparam cheshire_pkg::axi_in_t AxiIn = cheshire_pkg::gen_axi_in(Cfg);
  localparam int unsigned AxiSlvIdWidth = Cfg.AxiMstIdWidth + $clog2(AxiIn.num_in);

  // The id-width contract of the header CANNOT be allowed to drift from the
  // truth cheshire computes right above: NumAxiInMasters is a hand-written
  // mirror of gen_axi_in, and a future cheshire bump that adds a master (or a
  // Cfg switch this wrapper forgets to count) would silently reopen the
  // latent-truncation hole the contract exists to close. Elaboration-time,
  // zero cost, both simulators stop dead on a mismatch.
  initial begin : gen_id_contract_check
    if (AxiExtOutIdWidth != AxiSlvIdWidth)
      $fatal(1, "cheshire_isle: id-width contract drift - AxiExtOutIdWidth=%0d (from NumAxiInMasters=%0d) but cheshire's real external width is %0d (AxiMstIdWidth=%0d + clog2(num_in=%0d)). Realign NumAxiInMasters with cheshire_pkg::gen_axi_in.",
             AxiExtOutIdWidth, NumAxiInMasters, AxiSlvIdWidth, Cfg.AxiMstIdWidth, AxiIn.num_in);
  end
  typedef logic [AxiSlvIdWidth:0]     llc_id_t;
  `AXI_TYPEDEF_ALL(cheshire_llc, axi_addr_t, llc_id_t, axi_data_t, axi_strb_t, axi_user_t)

  typedef logic [AxiSlvIdWidth-1:0]  ext_slv_id_t;
  `AXI_TYPEDEF_ALL(cheshire_ext_slv, axi_addr_t, ext_slv_id_t, axi_data_t, axi_strb_t, axi_user_t)

  typedef logic [Cfg.AxiMstIdWidth-1:0]  ext_mst_id_t;
  `AXI_TYPEDEF_ALL(cheshire_ext_mst, axi_addr_t, ext_mst_id_t, axi_data_t, axi_strb_t, axi_user_t)

  typedef struct packed {
    logic [AxiAddrWidth-1:0] addr;
    logic                    write;
    logic [31:0]             wdata;
    logic [3:0]              wstrb;
    logic                    valid;
  } cheshire_reg_req_t;

  typedef struct packed {
    logic [31:0] rdata;
    logic        error;
    logic        ready;
  } cheshire_reg_rsp_t;

  // All internal AXI slave buses (out to external masters)
  cheshire_ext_slv_req_t [cheshire_pkg::iomsb(Cfg.AxiExtNumSlv):0] axi_ext_slv_req;
  cheshire_ext_slv_resp_t [cheshire_pkg::iomsb(Cfg.AxiExtNumSlv):0] axi_ext_slv_rsp;

  cheshire_ext_slv_req_t [cheshire_pkg::iomsb(AxiNumSlvAsync):0] axi_ext_slv_isolated_req;
  cheshire_ext_slv_resp_t [cheshire_pkg::iomsb(AxiNumSlvAsync):0] axi_ext_slv_isolated_rsp;

  // All internal AXI master buses (in from external masters)
  cheshire_ext_mst_req_t [cheshire_pkg::iomsb(Cfg.AxiExtNumMst):0] axi_ext_mst_req;
  cheshire_ext_mst_resp_t [cheshire_pkg::iomsb(Cfg.AxiExtNumMst):0] axi_ext_mst_rsp;

  // Internal 2D wire for Cheshire's interrupt output
  logic [cheshire_pkg::iomsb(1):0][cheshire_pkg::iomsb(NumIntrsOut):0] chs_intr_ext_o;

  // Internal External LLC (DRAM) bus
  cheshire_llc_req_t  axi_llc_mst_req, axi_llc_mst_isolated_req;
  cheshire_llc_resp_t axi_llc_mst_rsp, axi_llc_mst_isolated_rsp;

  logic [cheshire_pkg::SpihNumCs-1:0] spih_csb_tmp;
  logic [cheshire_pkg::SpihNumCs-1:0] spih_csb_en_tmp;
  assign spi_csb_o    = spih_csb_tmp[SpihNumCs-1:0];
  assign spi_csb_en_o = spih_csb_en_tmp[SpihNumCs-1:0];

  cheshire_reg_req_t [cheshire_pkg::iomsb(Cfg.RegExtNumSlv):0] ext_reg_req;
  cheshire_reg_rsp_t [cheshire_pkg::iomsb(Cfg.RegExtNumSlv):0] ext_reg_rsp;

  // Generate synchronous external register interfaces from Cheshire
  for (genvar i = 0; i < RegNumSlvSync; i++) begin: gen_ext_reg_sync
    assign reg_req_o[i]   = ext_reg_req[i];
    assign ext_reg_rsp[i] = reg_rsp_i[i];
  end

  cheshire_soc #(
    .Cfg               ( Cfg                        ),
    .ExtHartinfo       ( '0                         ),
    .axi_ext_llc_req_t ( cheshire_llc_req_t         ),
    .axi_ext_llc_rsp_t ( cheshire_llc_resp_t        ),
    .axi_ext_mst_req_t ( cheshire_ext_mst_req_t     ),
    .axi_ext_mst_rsp_t ( cheshire_ext_mst_resp_t    ),
    .axi_ext_slv_req_t ( cheshire_ext_slv_req_t     ),
    .axi_ext_slv_rsp_t ( cheshire_ext_slv_resp_t    ),
    .reg_ext_req_t     ( cheshire_reg_req_t         ),
    .reg_ext_rsp_t     ( cheshire_reg_rsp_t         )
  ) i_cheshire_soc     (
    .clk_i      ,
    .rst_ni     ,
    .test_mode_i,
    .boot_mode_i,
    .rtc_i             ( rt_clk_i ),
    // External AXI LLC (DRAM) port
    .axi_llc_mst_req_o ( axi_llc_mst_req ),
    .axi_llc_mst_rsp_i ( axi_llc_mst_rsp ),
    // External AXI crossbar ports
    .axi_ext_mst_req_i ( axi_ext_mst_req ),
    .axi_ext_mst_rsp_o ( axi_ext_mst_rsp ),
    .axi_ext_slv_req_o ( axi_ext_slv_req ),
    .axi_ext_slv_rsp_i ( axi_ext_slv_rsp ),
    // External reg demux slaves
    .reg_ext_slv_req_o ( ext_reg_req     ),
    .reg_ext_slv_rsp_i ( ext_reg_rsp     ),
    // Interrupts from external devices
    .intr_ext_i,
    .intr_ext_o        ( chs_intr_ext_o ),
    // Interrupts to external harts
    .xeip_ext_o,
    .mtip_ext_o,
    .msip_ext_o,
    // Debug interface to external harts
    .dbg_active_o     ,
    .dbg_ext_req_o    ,
    .dbg_ext_unavail_i,
    // JTAG interface
    .jtag_tck_i   ,
    .jtag_trst_ni ,
    .jtag_tms_i   ,
    .jtag_tdi_i   ,
    .jtag_tdo_o   ,
    .jtag_tdo_oe_o,
    // UART interface
    .uart_tx_o,
    .uart_rx_i,
    // UART Modem flow control
    .uart_rts_no,
    .uart_dtr_no,
    .uart_cts_ni,
    .uart_dsr_ni,
    .uart_dcd_ni,
    .uart_rin_ni,
    // I2C interface
    .i2c_sda_o   ,
    .i2c_sda_i   ,
    .i2c_sda_en_o,
    .i2c_scl_o   ,
    .i2c_scl_i   ,
    .i2c_scl_en_o,
    // SPI host interface
    .spih_sck_o        ( spi_sck_o    ),
    .spih_sck_en_o     ( spi_sck_en_o ),
    .spih_csb_o        ( spih_csb_tmp    ),
    .spih_csb_en_o     ( spih_csb_en_tmp ),
    .spih_sd_o         ( spi_sd_o     ),
    .spih_sd_en_o      ( spi_sd_en_o  ),
    .spih_sd_i         ( spi_sd_i     ),
    // GPIO interface
    .gpio_i   ,
    .gpio_o   ,
    .gpio_en_o,
    // Serial link interface
    .slink_rcv_clk_i,
    .slink_rcv_clk_o,
    .slink_i        ,
    .slink_o        ,
    // VGA interface
    .vga_hsync_o,
    .vga_vsync_o,
    .vga_red_o  ,
    .vga_green_o,
    .vga_blue_o ,
    // USB interface
    .usb_clk_i  ,
    .usb_rst_ni ,
    .usb_dm_i   ,
    .usb_dm_o   ,
    .usb_dm_oe_o,
    .usb_dp_i   ,
    .usb_dp_o   ,
    .usb_dp_oe_o
  );

  assign intr_ext_o = chs_intr_ext_o[0];

  // Map the synchronous AXI outputs directly.
  // Convention: Async ports are mapped first, Sync ports are mapped sequentially after.
  for (genvar i = 0; i < AxiNumSlvSync; i++) begin : gen_ext_slv_sync
    `AXI_ASSIGN_REQ_STRUCT(axi_req_o[i], axi_ext_slv_req[AxiNumSlvAsync + i])
    `AXI_ASSIGN_RESP_STRUCT(axi_ext_slv_rsp[AxiNumSlvAsync + i], axi_resp_i[i])
  end

  // Cheshire's AXI master CDC generation for asynchronous slaves
  for (genvar i = 0; i < AxiNumSlvAsync; i++) begin: gen_ext_slv_src_cdc
    axi_isolate              #(
      .NumPending             ( Cfg.AxiMaxSlvTrans           ),
      .TerminateTransaction   ( 1                            ),
      .AtopSupport            ( 1                            ),
      .AxiAddrWidth           ( Cfg.AddrWidth                ),
      .AxiDataWidth           ( Cfg.AxiDataWidth             ),
      .AxiIdWidth             ( AxiInIdWidth                 ),
      .AxiUserWidth           ( Cfg.AxiUserWidth             ),
      .axi_req_t              ( cheshire_ext_slv_req_t       ),
      .axi_resp_t             ( cheshire_ext_slv_resp_t      )
    ) i_axi_ext_slave_isolate (
      .clk_i                  ( clk_i                        ),
      .rst_ni                 ( rst_ni                       ),
      .slv_req_i              ( axi_ext_slv_req          [i] ),
      .slv_resp_o             ( axi_ext_slv_rsp          [i] ),
      .mst_req_o              ( axi_ext_slv_isolated_req [i] ),
      .mst_resp_i             ( axi_ext_slv_isolated_rsp [i] ),
      .isolate_i              ( async_axi_out_isolate_i  [i] ),
      .isolated_o             ( async_axi_out_isolated_o [i] )
    );

    axi_cdc_src #(
      .LogDepth   ( LogDepth                       ),
      .SyncStages ( CdcSyncStages                  ),
      .aw_chan_t  ( cheshire_ext_slv_aw_chan_t     ),
      .w_chan_t   ( cheshire_ext_slv_w_chan_t      ),
      .b_chan_t   ( cheshire_ext_slv_b_chan_t      ),
      .ar_chan_t  ( cheshire_ext_slv_ar_chan_t     ),
      .r_chan_t   ( cheshire_ext_slv_r_chan_t      ),
      .axi_req_t  ( cheshire_ext_slv_req_t         ),
      .axi_resp_t ( cheshire_ext_slv_resp_t        )
    ) i_cheshire_ext_slv_cdc_src   (
      // synchronous slave port
      .src_clk_i                   ( clk_i               ),
      .src_rst_ni                  ( rst_ni              ),
      .src_req_i                   ( axi_ext_slv_isolated_req [i] ),
      .src_resp_o                  ( axi_ext_slv_isolated_rsp [i] ),
      // asynchronous master port
      .async_data_master_aw_data_o ( async_axi_out_aw_data_o [i] ),
      .async_data_master_aw_wptr_o ( async_axi_out_aw_wptr_o [i] ),
      .async_data_master_aw_rptr_i ( async_axi_out_aw_rptr_i [i] ),
      .async_data_master_w_data_o  ( async_axi_out_w_data_o  [i] ),
      .async_data_master_w_wptr_o  ( async_axi_out_w_wptr_o  [i] ),
      .async_data_master_w_rptr_i  ( async_axi_out_w_rptr_i  [i] ),
      .async_data_master_b_data_i  ( async_axi_out_b_data_i  [i] ),
      .async_data_master_b_wptr_i  ( async_axi_out_b_wptr_i  [i] ),
      .async_data_master_b_rptr_o  ( async_axi_out_b_rptr_o  [i] ),
      .async_data_master_ar_data_o ( async_axi_out_ar_data_o [i] ),
      .async_data_master_ar_wptr_o ( async_axi_out_ar_wptr_o [i] ),
      .async_data_master_ar_rptr_i ( async_axi_out_ar_rptr_i [i] ),
      .async_data_master_r_data_i  ( async_axi_out_r_data_i  [i] ),
      .async_data_master_r_wptr_i  ( async_axi_out_r_wptr_i  [i] ),
      .async_data_master_r_rptr_o  ( async_axi_out_r_rptr_o  [i] )
    );
  end

  // Cheshire's AXI slave cdc and isolate generation
  for (genvar i = 0; i < AxiNumMstAsync; i++) begin: gen_ext_mst_dst_cdc
    axi_cdc_dst #(
      .LogDepth   ( LogDepth                   ),
      .SyncStages ( CdcSyncStages              ),
      .aw_chan_t  ( cheshire_ext_mst_aw_chan_t     ),
      .w_chan_t   ( cheshire_ext_mst_w_chan_t      ),
      .b_chan_t   ( cheshire_ext_mst_b_chan_t      ),
      .ar_chan_t  ( cheshire_ext_mst_ar_chan_t     ),
      .r_chan_t   ( cheshire_ext_mst_r_chan_t      ),
      .axi_req_t  ( cheshire_ext_mst_req_t         ),
      .axi_resp_t ( cheshire_ext_mst_resp_t        )
    ) i_cheshire_ext_mst_cdc_dst  (
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
      .dst_clk_i                  ( clk_i               ),
      .dst_rst_ni                 ( rst_ni              ),
      .dst_req_o                  ( axi_ext_mst_req [i] ),
      .dst_resp_i                 ( axi_ext_mst_rsp [i] )
    );
  end
  
  // Map the synchronous AXI inputs directly.
  for (genvar i = 0; i < AxiNumMstSync; i++) begin : gen_ext_mst_sync
    `AXI_ASSIGN_REQ_STRUCT(axi_ext_mst_req[AxiNumMstAsync + i], axi_req_i[i])
    `AXI_ASSIGN_RESP_STRUCT(axi_resp_o[i], axi_ext_mst_rsp[AxiNumMstAsync + i])
  end

  // AXI isolate and CDC for external LLC connection
  axi_isolate              #(
    .NumPending             ( Cfg.AxiMaxSlvTrans         ),
    .TerminateTransaction   ( 1                          ),
    .AtopSupport            ( 1                          ),
    .AxiAddrWidth           ( Cfg.AddrWidth              ),
    .AxiDataWidth           ( Cfg.AxiDataWidth           ),
    .AxiIdWidth             ( $bits(llc_id_t)            ),
    .AxiUserWidth           ( Cfg.AxiUserWidth           ),
    .axi_req_t              ( cheshire_llc_req_t         ),
    .axi_resp_t             ( cheshire_llc_resp_t        )
  ) i_axi_llc_isolate       (
    .clk_i                  ( clk_i                    ),
    .rst_ni                 ( rst_ni                   ),
    .slv_req_i              ( axi_llc_mst_req          ),
    .slv_resp_o             ( axi_llc_mst_rsp          ),
    .mst_req_o              ( axi_llc_mst_isolated_req ),
    .mst_resp_i             ( axi_llc_mst_isolated_rsp ),
    .isolate_i              ( async_axi_llc_isolate_i  ),
    .isolated_o             ( async_axi_llc_isolated_o )
  );

  generate
    if (LlcCdcSyncStages > 0) begin : gen_ext_llc_cdc
      axi_cdc_src #(
        .LogDepth   ( LogDepth                       ),
        .SyncStages ( LlcCdcSyncStages               ),
        .aw_chan_t  ( cheshire_llc_aw_chan_t         ),
        .w_chan_t   ( cheshire_llc_w_chan_t          ),
        .b_chan_t   ( cheshire_llc_b_chan_t          ),
        .ar_chan_t  ( cheshire_llc_ar_chan_t         ),
        .r_chan_t   ( cheshire_llc_r_chan_t          ),
        .axi_req_t  ( cheshire_llc_req_t             ),
        .axi_resp_t ( cheshire_llc_resp_t            )
      ) i_cheshire_ext_llc_cdc_src   (
        // synchronous slave port
        .src_clk_i                   ( clk_i                    ),
        .src_rst_ni                  ( rst_ni                   ),
        .src_req_i                   ( axi_llc_mst_isolated_req ),
        .src_resp_o                  ( axi_llc_mst_isolated_rsp ),
        // asynchronous master port
        .async_data_master_aw_data_o ( async_axi_llc_aw_data_o ),
        .async_data_master_aw_wptr_o ( async_axi_llc_aw_wptr_o ),
        .async_data_master_aw_rptr_i ( async_axi_llc_aw_rptr_i ),
        .async_data_master_w_data_o  ( async_axi_llc_w_data_o  ),
        .async_data_master_w_wptr_o  ( async_axi_llc_w_wptr_o  ),
        .async_data_master_w_rptr_i  ( async_axi_llc_w_rptr_i  ),
        .async_data_master_b_data_i  ( async_axi_llc_b_data_i  ),
        .async_data_master_b_wptr_i  ( async_axi_llc_b_wptr_i  ),
        .async_data_master_b_rptr_o  ( async_axi_llc_b_rptr_o  ),
        .async_data_master_ar_data_o ( async_axi_llc_ar_data_o ),
        .async_data_master_ar_wptr_o ( async_axi_llc_ar_wptr_o ),
        .async_data_master_ar_rptr_i ( async_axi_llc_ar_rptr_i ),
        .async_data_master_r_data_i  ( async_axi_llc_r_data_i  ),
        .async_data_master_r_wptr_i  ( async_axi_llc_r_wptr_i  ),
        .async_data_master_r_rptr_o  ( async_axi_llc_r_rptr_o  )
      );

      assign axi_llc_req_o = '0;

    end else begin : gen_no_ext_llc_cdc
      assign axi_llc_req_o            = axi_llc_mst_isolated_req;
      assign axi_llc_mst_isolated_rsp = axi_llc_resp_i;
      
      assign async_axi_llc_aw_data_o = '0;
      assign async_axi_llc_aw_wptr_o = '0;
      assign async_axi_llc_w_data_o  = '0;
      assign async_axi_llc_w_wptr_o  = '0;
      assign async_axi_llc_b_rptr_o  = '0;
      assign async_axi_llc_ar_data_o = '0;
      assign async_axi_llc_ar_wptr_o = '0;
      assign async_axi_llc_r_rptr_o  = '0;
    end
  endgenerate

  // Async reg interface:
  // Convention: Sync ports are mapped first, Async ports are mapped sequentially after.
  for (genvar i = 0; i < RegNumSlvAsync; i++) begin : gen_ext_reg_async
    reg_cdc_src #(
      .CDC_KIND ( "cdc_4phase"              ),
      .req_t     ( cheshire_reg_req_t       ),
      .rsp_t     ( cheshire_reg_rsp_t       )
    ) i_reg_cdc_src (
        .src_clk_i    ( clk_i  ),
        .src_rst_ni   ( rst_ni ),
        .src_req_i    ( ext_reg_req[RegNumSlvSync + i] ),
        .src_rsp_o    ( ext_reg_rsp[RegNumSlvSync + i] ),
  
        .async_req_o  ( reg_async_mst_req_o[i]  ),
        .async_ack_i  ( reg_async_mst_ack_i[i]  ),
        .async_data_o ( reg_async_mst_data_o[i] ),
  
        .async_req_i  ( reg_async_mst_req_i[i]  ),
        .async_ack_o  ( reg_async_mst_ack_o[i]  ),
        .async_data_i ( reg_async_mst_data_i[i] )
    );
  end

endmodule : cheshire_isle

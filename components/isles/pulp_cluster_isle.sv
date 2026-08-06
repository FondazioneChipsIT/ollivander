// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the PULP Integer Cluster
//
// BENDER: name="pulp_cluster"
// BENDER: name="axi"
//
// The compilation contract of this wrapper, alongside its Bender requirements: hier-icache (a
// pulp_cluster dependency) declares its statistics counters under this ifdef but references them
// outside it, so its sources do not compile without the define. Declared here, every project
// that instantiates this isle inherits it - directly or through a macro that contains it.
// DEFINE: name="FEATURE_ICACHE_STAT"

`include "axi/typedef.svh"

module pulp_cluster_isle
  import axi_pkg::*;
#(
  // Geometry of the SoC this isle is attached to, driven by the generator at
  // instantiation (rtl_ir_builder.py): AxiInIdWidth receives the crossbar's slave-side
  // ID width (AxiSlvIdWidth), AxiOutIdWidth its manager-side AxiIdWidth. These were
  // localparams frozen at astral's values while the wrapped IP was reached through
  // pulp_cluster_wrap, a convenience shell that fixes the whole configuration to
  // PulpClusterDefaultCfg; the isle then had to reinterpret every CDC payload against
  // the frozen inner geometry, which truncated the AXI IDs (future_evolution_tasks.md
  // used to track this as section 3.5). pulp_cluster itself takes the full
  // configuration as a parameter and contains real axi_id_remap stages for both
  // directions, so instantiating it directly makes both sides of every CDC derive
  // from the same constants and no adaptation logic is needed here.
  parameter int unsigned AxiAddrWidth       = 48,
  parameter int unsigned AxiDataWidth       = 64,
  parameter int unsigned AxiUserWidth       = 10,
  parameter int unsigned AxiInIdWidth       = 5,
  parameter int unsigned AxiOutIdWidth      = 2,
  parameter int unsigned LogDepth           = 3,
  // Base of the SoC address region mapped to this cluster, driven by the generator
  // from the component's axi_slave 'base_addr'. The cluster decodes its own slave
  // traffic against ClusterBaseAddr + (cluster_id_i << 22) (cluster_bus_wrap), so
  // leaving the IP default here would send every external access to the wrong rule.
  parameter logic [63:0] ClusterBaseAddr    = 64'h1000_0000,
  // Not configurable: the cluster sources shipped by Bender hardwire the core count
  // in the `NB_CORES define (pulp_soc_defines.sv), which feeds PulpClusterDefaultCfg
  // and several sub-IP headers. Overriding only the Cfg field would desynchronize them.
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

  // ===============================================================================
  // CLUSTER CONFIGURATION
  // ===============================================================================
  // The shipped default configuration with the AXI boundary geometry and the address
  // decode replaced by this isle's parameters. Everything else (core count, TCDM,
  // caches, HMR, HWPEs, boot addresses) deliberately mirrors PulpClusterDefaultCfg:
  // those fields are entangled with compile-time defines of the cluster sources, and
  // no example exercises them yet - the residual items of future_evolution_tasks.md
  // section 3.5. A full assignment pattern is used instead of copying the default in
  // a constant function because Verilator's constant evaluator cannot read unpacked
  // struct constants (SimulateVisitor: unknown node, hit on 5.050); the 'default'
  // entry keeps the literal elaborable if upstream adds fields, and the counts that
  // must track the defines stay referenced from the package rather than restated.
  localparam pulp_cluster_package::pulp_cluster_cfg_t ClusterCfg = '{
    CoreType:               pulp_cluster_package::RI5CY,
    NumCores:               pulp_cluster_package::NumCores,          // = `NB_CORES
    DmaNumPlugs:            pulp_cluster_package::NumDmas,           // = `NB_DMAS
    DmaNumOutstandingBursts: 8,
    DmaBurstLength:         5,
    NumMstPeriphs:          pulp_cluster_package::NB_MPERIPHS,
    NumSlvPeriphs:          pulp_cluster_package::NB_SPERIPHS,
    ClusterAlias:           1,
    ClusterAliasBase:       'h0,
    NumSyncStages:          3,
    UseHci:                 1,
    TcdmSize:               128*1024,
    TcdmNumBank:            16,
    HwpePresent:            1,
    HwpeCfg:                '{NumHwpes: 3,
                              HwpeList: {pulp_cluster_package::SOFTEX,
                                         pulp_cluster_package::NEUREKA,
                                         pulp_cluster_package::REDMULE}},
    HwpeNumPorts:           9,
    HMRPresent:             1,
    HMRDmrEnabled:          1,
    HMRTmrEnabled:          1,
    HMRDmrFIxed:            0,
    HMRTmrFIxed:            0,
    HMRInterleaveGrps:      1,
    HMREnableRapidRecovery: 1,
    HMRSeparateDataVoters:  1,
    HMRSeparateAxiBus:      0,
    HMRNumBusVoters:        1,
    EnableECC:              1,
    ECCInterco:             1,
    iCacheNumBanks:         2,
    iCacheNumLines:         1,
    iCacheNumWays:          4,
    iCacheSharedSize:       4*1024,
    iCachePrivateSize:      512,
    iCachePrivateDataWidth: 32,
    EnableReducedTag:       1,
    L2Size:                 1000*1024,
    DmBaseAddr:             'h60203000,
    BootRomBaseAddr:        'h1C008080,
    BootAddr:               'h1C008080,
    EnablePrivateFpu:       1,
    EnablePrivateFpDivSqrt: 0,
    NumAxiIn:               pulp_cluster_package::NumAxiSubordinatePorts,
    NumAxiOut:              pulp_cluster_package::NumAxiManagerPorts,
    // The AXI boundary geometry and the address decode: the isle's own parameters,
    // the whole point of instantiating the IP directly (one constant, both sides).
    AxiIdInWidth:           AxiInIdWidth,
    AxiIdOutWidth:          AxiOutIdWidth,
    AxiAddrWidth:           AxiAddrWidth,
    AxiDataInWidth:         AxiDataWidth,
    AxiDataOutWidth:        AxiDataWidth,
    AxiUserWidth:           AxiUserWidth,
    AxiMaxInTrans:          64,
    AxiMaxOutTrans:         64,
    AxiCdcLogDepth:         LogDepth,
    AxiCdcSyncStages:       3,
    SyncStages:             3,
    ClusterBaseAddr:        ClusterBaseAddr,
    ClusterPeriphOffs:      'h00200000,
    ClusterExternalOffs:    'h00400000,
    EnableRemapAddress:     0,
    SnitchICache:           0,
    default:                '0
  };

  // Direct instantiation of the IP: with the CDC geometry on both sides derived from
  // the same parameters, every async port width matches by construction and the ID
  // adaptation happens inside pulp_cluster through its axi_id_remap stages. The old
  // pulp_cluster_wrap shell, besides freezing the geometry, silently tied off
  // axi_isolate_i, dbg_irq_valid_i and mbox_irq_i; connected directly, those inputs
  // now actually reach the cluster.
  pulp_cluster #(
    .Cfg ( ClusterCfg )
  ) i_pulp_cluster (
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
    // The cluster drives these through 'edge_propagator_tx', the transmit half of a four-phase
    // CDC handshake: it holds valid_o until it sees ack_i resynchronized. Tying ack HIGH is
    // therefore the correct way to leave them unused, because valid_o then simply follows the
    // internal event. Tying it LOW would latch valid_o high forever after the first event
    // (r_input_reg <= valid_i | (r_input_reg & ~sync_a[0])). The astral reference ties
    // dma_pe_evt_ack_i to '0 and has that stuck signal: do not "align" this to it.
    // Connecting them for real means instantiating the receive half in the destination clock
    // domain (olli_edge_propagator wraps both) and exposing the pulses as ordinary outputs, which
    // the existing 'interrupts' routing then handles like pulp_cluster.eoc_o.
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

    // Map to Ollivander standard AXI IN ports
    .async_data_slave_aw_wptr_i  ( async_axi_in_aw_wptr_i  ),
    .async_data_slave_aw_data_i  ( async_axi_in_aw_data_i  ),
    .async_data_slave_aw_rptr_o  ( async_axi_in_aw_rptr_o  ),
    .async_data_slave_ar_wptr_i  ( async_axi_in_ar_wptr_i  ),
    .async_data_slave_ar_data_i  ( async_axi_in_ar_data_i  ),
    .async_data_slave_ar_rptr_o  ( async_axi_in_ar_rptr_o  ),
    .async_data_slave_w_wptr_i   ( async_axi_in_w_wptr_i   ),
    .async_data_slave_w_data_i   ( async_axi_in_w_data_i   ),
    .async_data_slave_w_rptr_o   ( async_axi_in_w_rptr_o   ),
    .async_data_slave_r_wptr_o   ( async_axi_in_r_wptr_o   ),
    .async_data_slave_r_data_o   ( async_axi_in_r_data_o   ),
    .async_data_slave_r_rptr_i   ( async_axi_in_r_rptr_i   ),
    .async_data_slave_b_wptr_o   ( async_axi_in_b_wptr_o   ),
    .async_data_slave_b_data_o   ( async_axi_in_b_data_o   ),
    .async_data_slave_b_rptr_i   ( async_axi_in_b_rptr_i   ),

    // Map to Ollivander standard AXI OUT ports
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

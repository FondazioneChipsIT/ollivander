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

  // =================================================================================
  // AXI DATA ALIGNMENT & CDC FIFO MAPPING (FUNCTIONAL MISMATCH RESOLUTION)
  // =================================================================================
  // The external, immutable 'pulp_cluster_wrap' module is compiled with a fixed
  // AXI master ID width of 6 and slave ID width of 5.
  // However, the parent SoC configures the master ID width dynamically (typically 2),
  // causing the outer CDC FIFO data signals (like 'async_axi_out_r_data_i') to be
  // narrower than what the inner IP expects.
  //
  // An asynchronous CDC FIFO payload consists of multiple entries concatenated:
  //   {entry_7, entry_6, ..., entry_0}
  // If we perform a bit-slice of the entire concatenated vector (e.g. vector[663:0]),
  // the boundary offsets for every entry except entry_0 will shift and corrupt
  // the data read by the CDC read pointer.
  //
  // To resolve this mismatch functionally:
  // 1. We declare intermediate signals of fixed sizes matching the inner IP ports.
  // 2. We map the AXI data entry-by-entry for all 8 entries in the CDC queue.
  // 3. For inputs to the inner IP, we copy the dynamic payload to the lower bits of
  //    each entry, leaving the upper bits (ID fields) zero-extended.
  //    (This is functionally correct since the AXI ID field resides in the MSB).
  // 4. For outputs from the inner IP, we copy the lower bits of each entry to the
  //    wrapper ports, truncating the unused upper ID bits.

  // Fixed internal channel widths for the 'pulp_cluster_wrap' ports
  localparam int unsigned InnerSlvAwWidth = 81;
  localparam int unsigned InnerSlvArWidth = 75;
  localparam int unsigned InnerSlvRWidth  = 81;
  localparam int unsigned InnerSlvBWidth  = 16;
  localparam int unsigned InnerSlvWWidth  = 83;

  localparam int unsigned InnerMstAwWidth = 83;
  localparam int unsigned InnerMstArWidth = 77;
  localparam int unsigned InnerMstRWidth  = 83;
  localparam int unsigned InnerMstBWidth  = 18;
  localparam int unsigned InnerMstWWidth  = 83;

  // Dynamic entry widths calculated from the outer wrapper's parameters
  localparam int unsigned OuterSlvAwWidth = AsyncAxiInAwWidth / 8;
  localparam int unsigned OuterSlvArWidth = AsyncAxiInArWidth / 8;
  localparam int unsigned OuterSlvRWidth  = AsyncAxiInRWidth / 8;
  localparam int unsigned OuterSlvBWidth  = AsyncAxiInBWidth / 8;
  localparam int unsigned OuterSlvWWidth  = AsyncAxiInWWidth / 8;

  localparam int unsigned OuterMstAwWidth = AsyncAxiOutAwWidth / 8;
  localparam int unsigned OuterMstArWidth = AsyncAxiOutArWidth / 8;
  localparam int unsigned OuterMstRWidth  = AsyncAxiOutRWidth / 8;
  localparam int unsigned OuterMstBWidth  = AsyncAxiOutBWidth / 8;
  localparam int unsigned OuterMstWWidth  = AsyncAxiOutWWidth / 8;

  // Intermediate wires matching the fixed internal IP port sizes
  logic [647:0] inner_slv_aw_data;
  logic [599:0] inner_slv_ar_data;
  logic [647:0] inner_slv_r_data;
  logic [127:0] inner_slv_b_data;

  logic [663:0] inner_mst_aw_data;
  logic [615:0] inner_mst_ar_data;
  logic [663:0] inner_mst_r_data;
  logic [143:0] inner_mst_b_data;

  always_comb begin
    // 1. Slave AW (Input to inner): zero-pad/slice entry-by-entry
    inner_slv_aw_data = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterSlvAwWidth < InnerSlvAwWidth) begin
        inner_slv_aw_data[i * InnerSlvAwWidth +: OuterSlvAwWidth] = async_axi_in_aw_data_i[i * OuterSlvAwWidth +: OuterSlvAwWidth];
      end else begin
        inner_slv_aw_data[i * InnerSlvAwWidth +: InnerSlvAwWidth] = async_axi_in_aw_data_i[i * OuterSlvAwWidth +: InnerSlvAwWidth];
      end
    end

    // 2. Slave AR (Input to inner): zero-pad/slice entry-by-entry
    inner_slv_ar_data = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterSlvArWidth < InnerSlvArWidth) begin
        inner_slv_ar_data[i * InnerSlvArWidth +: OuterSlvArWidth] = async_axi_in_ar_data_i[i * OuterSlvArWidth +: OuterSlvArWidth];
      end else begin
        inner_slv_ar_data[i * InnerSlvArWidth +: InnerSlvArWidth] = async_axi_in_ar_data_i[i * OuterSlvArWidth +: InnerSlvArWidth];
      end
    end

    // 3. Slave R (Output from inner): slice entry-by-entry and drive wrapper output
    async_axi_in_r_data_o = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterSlvRWidth < InnerSlvRWidth) begin
        async_axi_in_r_data_o[i * OuterSlvRWidth +: OuterSlvRWidth] = inner_slv_r_data[i * InnerSlvRWidth +: OuterSlvRWidth];
      end else begin
        async_axi_in_r_data_o[i * OuterSlvRWidth +: InnerSlvRWidth] = inner_slv_r_data[i * InnerSlvRWidth +: InnerSlvRWidth];
      end
    end

    // 4. Slave B (Output from inner): slice entry-by-entry and drive wrapper output
    async_axi_in_b_data_o = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterSlvBWidth < InnerSlvBWidth) begin
        async_axi_in_b_data_o[i * OuterSlvBWidth +: OuterSlvBWidth] = inner_slv_b_data[i * InnerSlvBWidth +: OuterSlvBWidth];
      end else begin
        async_axi_in_b_data_o[i * OuterSlvBWidth +: InnerSlvBWidth] = inner_slv_b_data[i * InnerSlvBWidth +: InnerSlvBWidth];
      end
    end

    // 5. Master AW (Output from inner): slice entry-by-entry and drive wrapper output
    async_axi_out_aw_data_o = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterMstAwWidth < InnerMstAwWidth) begin
        async_axi_out_aw_data_o[i * OuterMstAwWidth +: OuterMstAwWidth] = inner_mst_aw_data[i * InnerMstAwWidth +: OuterMstAwWidth];
      end else begin
        async_axi_out_aw_data_o[i * OuterMstAwWidth +: InnerMstAwWidth] = inner_mst_aw_data[i * InnerMstAwWidth +: InnerMstAwWidth];
      end
    end

    // 6. Master AR (Output from inner): slice entry-by-entry and drive wrapper output
    async_axi_out_ar_data_o = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterMstArWidth < InnerMstArWidth) begin
        async_axi_out_ar_data_o[i * OuterMstArWidth +: OuterMstArWidth] = inner_mst_ar_data[i * InnerMstArWidth +: OuterMstArWidth];
      end else begin
        async_axi_out_ar_data_o[i * OuterMstArWidth +: InnerMstArWidth] = inner_mst_ar_data[i * InnerMstArWidth +: InnerMstArWidth];
      end
    end

    // 7. Master R (Input to inner): zero-pad/slice entry-by-entry
    inner_mst_r_data = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterMstRWidth < InnerMstRWidth) begin
        inner_mst_r_data[i * InnerMstRWidth +: OuterMstRWidth] = async_axi_out_r_data_i[i * OuterMstRWidth +: OuterMstRWidth];
      end else begin
        inner_mst_r_data[i * InnerMstRWidth +: InnerMstRWidth] = async_axi_out_r_data_i[i * OuterMstRWidth +: InnerMstRWidth];
      end
    end

    // 8. Master B (Input to inner): zero-pad/slice entry-by-entry
    inner_mst_b_data = '0;
    for (int i = 0; i < 8; i++) begin
      if (OuterMstBWidth < InnerMstBWidth) begin
        inner_mst_b_data[i * InnerMstBWidth +: OuterMstBWidth] = async_axi_out_b_data_i[i * OuterMstBWidth +: OuterMstBWidth];
      end else begin
        inner_mst_b_data[i * InnerMstBWidth +: InnerMstBWidth] = async_axi_out_b_data_i[i * OuterMstBWidth +: InnerMstBWidth];
      end
    end
  end

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
    .async_data_slave_aw_wptr_i  ( async_axi_in_aw_wptr_i ),
    .async_data_slave_aw_data_i  ( inner_slv_aw_data ),
    .async_data_slave_aw_rptr_o  ( async_axi_in_aw_rptr_o ),
    .async_data_slave_ar_wptr_i  ( async_axi_in_ar_wptr_i ),
    .async_data_slave_ar_data_i  ( inner_slv_ar_data ),
    .async_data_slave_ar_rptr_o  ( async_axi_in_ar_rptr_o ),
    .async_data_slave_w_wptr_i   ( async_axi_in_w_wptr_i  ),
    .async_data_slave_w_data_i   ( async_axi_in_w_data_i  ),
    .async_data_slave_w_rptr_o   ( async_axi_in_w_rptr_o  ),
    .async_data_slave_r_wptr_o   ( async_axi_in_r_wptr_o  ),
    .async_data_slave_r_data_o   ( inner_slv_r_data ),
    .async_data_slave_r_rptr_i   ( async_axi_in_r_rptr_i ),
    .async_data_slave_b_wptr_o   ( async_axi_in_b_wptr_o ),
    .async_data_slave_b_data_o   ( inner_slv_b_data ),
    .async_data_slave_b_rptr_i   ( async_axi_in_b_rptr_i  ),

    // Map to Ollivander standard AXI OUT ports
    .async_data_master_aw_wptr_o ( async_axi_out_aw_wptr_o ),
    .async_data_master_aw_data_o ( inner_mst_aw_data ),
    .async_data_master_aw_rptr_i ( async_axi_out_aw_rptr_i ),
    .async_data_master_ar_wptr_o ( async_axi_out_ar_wptr_o ),
    .async_data_master_ar_data_o ( inner_mst_ar_data ),
    .async_data_master_ar_rptr_i ( async_axi_out_ar_rptr_i ),
    .async_data_master_w_wptr_o  ( async_axi_out_w_wptr_o  ),
    .async_data_master_w_data_o  ( async_axi_out_w_data_o  ),
    .async_data_master_w_rptr_i  ( async_axi_out_w_rptr_i  ),
    .async_data_master_r_wptr_i  ( async_axi_out_r_wptr_i  ),
    .async_data_master_r_data_i  ( inner_mst_r_data ),
    .async_data_master_r_rptr_o  ( async_axi_out_r_rptr_o  ),
    .async_data_master_b_wptr_i  ( async_axi_out_b_wptr_i  ),
    .async_data_master_b_data_i  ( inner_mst_b_data ),
    .async_data_master_b_rptr_o  ( async_axi_out_b_rptr_o  )
  );

endmodule : pulp_cluster_isle

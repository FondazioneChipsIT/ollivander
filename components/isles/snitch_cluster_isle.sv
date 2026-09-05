// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Snitch cluster isle (dual-network: one AXI pair per NoC network, narrow and wide)
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

module snitch_cluster_isle
  import floo_pkg::*;
  import floo_ollivander_noc_pkg::*;
  import snitch_cluster_pkg::*;
#(
  parameter bit UseHWPE = 1'b0,
  // The wide offload interface's types. They exist in the NoC package only when
  // the SoC declares a wide reduction channel (FlooGen emits them with it), so a
  // project without that channel must still be able to instantiate this isle:
  // the tile passes the package types when the channel is declared and leaves
  // these defaults - and the ports tied off - when it is not. The adapter below
  // is generated only when the network's collective configuration enables an FP
  // operation, so the defaults are never dereferenced.
  parameter type offload_wide_req_t = logic,
  parameter type offload_wide_rsp_t = logic,
  // -------------------------------------------------------------------------------
  // INSTANCE IDENTITY (see docs/hw/component_standardization.md, "Instance identity
  // parameters"). An isle that decodes its own slave window declares this pair and
  // Ollivander fills it PER INSTANCE at tile instantiation (rtl_ir_builder.py):
  // base_addr + index * size_per_instance for the base, size_per_instance for the
  // size - the same x-major enumeration the FlooGen address map and the auto control
  // group bit-selects use - the declared-parameter route every self-mapping
  // component shares (memory isles and clusters alike). Values are PROJECT-LOCAL in macro builds too: the
  // border adapters rebase incoming traffic before it reaches any tile.
  // -------------------------------------------------------------------------------
  // NOTE: the window BASE arrives as a PORT (instance_base_addr_i), not as a
  // parameter: see the port declaration for the measurement that forced the
  // change. The window SIZE stays a parameter - it is identical across the
  // instances of one component, so it costs no extra specialization.
  parameter longint unsigned InstanceWindowSize = 64'h0,
  // The geometry this isle cannot depart from, stated as literals so that Ollivander
  // can read it and validate the connection to the bus this isle is attached to
  // (soc_schema.py, HARDWARE CONSTRAINTS CHECK). Literal rather than a reference to
  // snitch_cluster_pkg because the check reads the value as written and cannot resolve
  // an expression; the elaboration checks in the body keep the literals honest against
  // the IP that actually defines them.
  //
  // Address and data demand equality: no adaptation exists for them. The ID widths
  // state a direction instead - what this isle emits (Out) and what it accepts (In)
  // - and the generator verifies capacity along the direction of travel: an ID this
  // isle emits is zero-extended by the tile if the network is wider, but a network
  // ID wider than the In width here would be truncated, aliasing transactions. All
  // four used to be wrong, the two directions swapped, while nothing read them.
  localparam int unsigned AxiAddrWidth        = 48,  // snitch_cluster_pkg::AddrWidth
  localparam int unsigned AxiNarrowDataWidth  = 64,  // snitch_cluster_pkg::NarrowDataWidth
  localparam int unsigned AxiWideDataWidth    = 512, // snitch_cluster_pkg::WideDataWidth
  localparam int unsigned AxiNarrowInIdWidth  = 2,   // snitch_cluster_pkg::NarrowIdWidthIn
  localparam int unsigned AxiNarrowOutIdWidth = 4,   // snitch_cluster_pkg::NarrowIdWidthOut
  localparam int unsigned AxiWideInIdWidth    = 1,   // snitch_cluster_pkg::WideIdWidthIn
  localparam int unsigned AxiWideOutIdWidth   = 3,   // snitch_cluster_pkg::WideIdWidthOut
  // ---------------------------------------------------------------------------------
  // Offload boot contract - "memory_mapped", the snitch-family protocol (semantics in
  // docs/hw/component_standardization.md section 8; the spatz isle carries the sibling
  // realization). The cores boot the cluster's internal PC-RELATIVE bootrom and park
  // in WFI; the host writes the payload entry point into scratch[1] of the cluster
  // peripherals, wakes every hart through cl_clint_set, and collects per-core
  // (value << 1) | 1 results from a slot array in the cluster TCDM.
  //
  // Authority for the offsets: the meta-generated RTL this isle wraps, produced by
  // the registry pre-build from the amended default cfg. Peripherals sit after the
  // napot-rounded TCDM (128 KiB) plus the 4 KiB internal bootrom, hence 'h2_1000;
  // scratch[1] and cl_clint_set offsets come from the generated register decoder
  // (snitch_cluster_peripheral_reg.sv: scratch[] at 'h180 + i*8, cl_clint_set 'h1a0).
  // Values must track the generated snitch_cluster_pkg (NrCores = 9 counts the DM
  // core: it boots and reports a slot like every other hart).
  localparam string       OffloadContract   = "memory_mapped",
  localparam int unsigned OffloadCtrlOffs   = 'h0002_1000,
  localparam int unsigned OffloadEntryOffs  = 'h188,
  localparam int unsigned OffloadWakeOffs   = 'h1a0,
  // Slots and payload stacks live in the TCDM, addressed by the PAYLOAD through the
  // cluster's ALIAS REGION (every instance sees ITSELF at OffloadLocalBase, so one
  // payload image serves all instances without knowing its own cluster - mandatory
  // here, since hart_base_id_i is tied to zero on every instance below and mhartid
  // carries no cluster identity). The host reaches the same slots through each
  // instance's own window. Tracks AliasRegionBase in the generated wrapper.
  localparam int unsigned OffloadLocalBase  = 'h1800_0000,
  localparam int unsigned OffloadReturnOffs = 'h0001_FF00,
  localparam int unsigned OffloadStackOffs  = 'h0001_F000,
  // Collective slots, at the very top of the TCDM above the return slots
  // (returns end at ReturnOffs + NumCores*4 = 'h1_FF24). These are the baked
  // DESTINATIONS of the narrow-reduction test: every member instance writes its
  // result GLOBALLY to instance 0's collect slot (the stamper window marks the
  // write IntAdd with the group mask, the network reduces the W payloads) and
  // its presence to the barrier slot (LsbAnd). Instance 0's address is the one
  // that matters: a reduction's member mask only converts to coordinates
  // through the SAM rule of its DESTINATION, so the destination must live
  // inside the collective group's own address region.
  // ALL windowed collective slots must be aligned to the narrow channel's beat
  // (8 bytes here): FlooNoC's collective machinery consumes the beat at channel
  // width - LsbAnd ANDs data bit 0 of the WHOLE beat (floo_reduction_arbiter)
  // and the integer ALU computes on the low word - so a 32-bit store at an
  // unaligned-to-8 offset puts the value in the beat's HIGH half and the
  // machinery silently reduces the unwritten low half. The barrier lived at
  // 'h1_FFFC and never converged for exactly that reason; the generator now
  // refuses unaligned slots at generation time.
  localparam int unsigned OffloadCollectOffs    = 'h0001_FFF8,  // final (row) landing, instance 0
  localparam int unsigned OffloadCollectColOffs = 'h0001_FFF0,  // column landing, one per column head
  localparam int unsigned OffloadBarrierOffs    = 'h0001_FFE8,  // LsbAnd slot (moved from 'h1_FFFC)
  // Plain-memory mailbox (no stamper window): the host writes each instance's
  // collective meta ({y_dim, is_head}) here BEFORE waking it - cluster hartids
  // restart at zero per instance, so the payload has no identity of its own
  // and the head election must arrive from the side that knows the geometry.
  localparam int unsigned OffloadCollMetaOffs    = 'h0001_FFE0,
  // Multicast landing slot. Unlike the reduction slots this one is NOT a single
  // destination: one member issues a write into the stamped window and the
  // network replicates it to every member, each landing at ITS OWN copy of this
  // offset (the destination chimney rebuilds the local address from the member
  // id). The host then reads all of them. Beat-aligned like the others.
  localparam int unsigned OffloadMcastOffs      = 'h0001_FFD8,
  // Wide collective landing. Two things set it apart from the slots above: it
  // is a full 512-bit BEAT, so it must be aligned to 64 bytes and not to 8 (a
  // wide transfer at a sub-beat offset makes iDMA emit strobed narrow beats
  // instead of one full one), and it is written by the cluster's DMA rather
  // than by a core, since Snitch cores store 64 bits at a time. Placed below
  // the narrow slots and above the return array (which ends at ReturnOffs +
  // NumCores*4 = 'h1_FF24), so the 64 bytes from here to 'h1_FF7F are free.
  localparam int unsigned OffloadWideOffs       = 'h0001_FF40,
  // Source buffer of the wide contribution: the eight FP64 lanes the DMA sends
  // into the reduction. Separate from the landing above because on the group's
  // instance 0 source and destination would otherwise coincide. 64-byte aligned,
  // in the free stretch below the narrow slots ('h1_FF80..'h1_FFBF).
  localparam int unsigned OffloadWideSrcOffs    = 'h0001_FF80,
  // Mailbox: the REAL address of this instance's column-head wide landing, written
  // by the host (which knows every base) before the wake. The wide path has no
  // stamper to rewrite an address, and a payload does not know its own base
  // (hartids restart per instance), so the first phase of the dimension-ordered
  // wide reduction reads its destination from here. 64-bit word, beat-aligned.
  localparam int unsigned OffloadWideColDstOffs = 'h0001_FFC0,
  // The alias base the PAYLOAD writes the collective slots through. A member's
  // contribution must always leave its cluster - the destination instance's
  // router expects it back on the local port (expected_in_route_loopback) - but
  // snitch's internal decode serves the cluster's own global range in the TCDM
  // without ever exiting. The alias is a range that decode does NOT claim, so
  // the write is forwarded out; the tile's stamper then rewrites it to the real
  // slot address (and stamps it) BEFORE the chimney, so the alias never reaches
  // the NoC and the SoC map never learns it exists.
  localparam int unsigned OffloadCollAliasBase = 'h3800_0000,
  localparam int unsigned OffloadNumCores   = 9,
  // WHICH HART CAN MOVE WIDE DATA. The Snitch cores store 64 bits; the only
  // master on the 512-bit channel is the cluster iDMA, and it is driven by
  // CUSTOM INSTRUCTIONS that exactly one hart may execute - on every other one
  // they trap as illegal. Declared here rather than derived by the generator
  // because "the DMA sits on the last hart" is a fact of THIS cluster's ISA
  // configuration, not a law: another IP will state another number, and
  // Ollivander must read it instead of knowing it. The elaboration check below
  // keeps the literal honest against the package that actually defines it.
  // WHAT THIS SUBTILE'S WIDE USER MEANS. With the wide collectives generated in,
  // the cluster's DMA drives {collective_mask, collective_op} - FlooNoC's own layout,
  // mask on top - on the AW user of every wide transfer, and its slave wide port
  // expects the same layout: that is how software issues a wide collective with no
  // stamping outside the cluster. Declared as a SEMANTIC, not as a width: the
  // generator needs to know the layout to type the isolate, the chimney and the
  // inbound adapter, and no number can say that. The width itself is not declared
  // - the tile checks it in elaboration on the real port against the network's
  // collective type, which is stricter than any literal typed here. A component
  // whose wide user carries something else leaves this undeclared and must then be
  // no wider than the network's plain wide user, or generation refuses it.
  localparam string       OffloadWideUserLayout = "floo_collective",
  localparam int unsigned OffloadDmaHart    = 8,
  // WHICH HART CARRIES THE RESULT. Convention rather than hardware: exactly one
  // core per instance must issue a collective, and this is the one that runs the
  // workload and therefore holds the value to reduce (every other core returns
  // the fixed secondary code). Declared for the same reason as above - so the
  // software templates stop hardcoding an index that belongs to the component.
  localparam int unsigned OffloadPrimaryHart = 0,
  // Snitch executes rv32imafd; the payload keeps the conservative integer subset.
  localparam string       OffloadIsa        = "rv32im_zicsr",
  localparam string       OffloadAbi        = "ilp32"
) (
  input  logic                                    clk_i,
  input  logic                                    rst_ni,
  input  logic                                    test_mode_i,
  // INSTANCE IDENTITY AS A PORT, not a parameter. The window
  // base differs per instance, and for Verilator a differing parameter value makes
  // a DISTINCT module: sixteen identical cluster tiles became sixteen hierarchical
  // specializations, elaborated and compiled sixteen times over, and elaboration is
  // half of a cold build (docs/developer/wip, section 5.2.-1). Nothing here needs
  // the value at elaboration time - it only reaches the cluster's own
  // cluster_base_addr_i input - so a constant driven from the top synthesizes
  // identically while collapsing the sixteen specializations into one.
  input  logic [63:0]                             instance_base_addr_i,
  
  // Cluster ports
  input  logic                      [snitch_cluster_pkg::NrCores-1:0] debug_req_i,
  input  logic                      [snitch_cluster_pkg::NrCores-1:0] meip_i,
  input  logic                      [snitch_cluster_pkg::NrCores-1:0] mtip_i,
  input  logic                      [snitch_cluster_pkg::NrCores-1:0] msip_i,

  // Dual-Network AXI Master Ports
  output snitch_cluster_pkg::narrow_out_req_t     axi_narrow_req_o,
  input wire snitch_cluster_pkg::narrow_out_resp_t    axi_narrow_resp_i,
  output snitch_cluster_pkg::wide_out_req_t       axi_wide_req_o,
  input wire snitch_cluster_pkg::wide_out_resp_t      axi_wide_resp_i,

  // Dual-Network AXI Slave Ports
  input wire snitch_cluster_pkg::narrow_in_req_t      axi_narrow_req_i,
  output snitch_cluster_pkg::narrow_in_resp_t     axi_narrow_resp_o,
  input wire snitch_cluster_pkg::wide_in_req_t        axi_wide_req_i,
  output snitch_cluster_pkg::wide_in_resp_t       axi_wide_resp_o,

  // Offload interface
  input wire offload_wide_req_t  offload_wide_req_i,
  output offload_wide_rsp_t      offload_wide_rsp_o
);

  // The address and data widths above are literals because that is what Ollivander can
  // read and validate against the bus this isle is attached to; these elaboration
  // checks are what keeps the literals honest against the IP that actually defines them.
  // Written as generate-scope $fatal rather than assertions on purpose: the regression
  // runs with -nosva -noimmedassert, which would silence an immediate assert, while an
  // elaboration-time error cannot be waived.
  if (AxiAddrWidth != snitch_cluster_pkg::AddrWidth)
    $fatal(1, "snitch_cluster_isle: AxiAddrWidth (%0d) contradicts snitch_cluster_pkg::AddrWidth (%0d)",
           AxiAddrWidth, snitch_cluster_pkg::AddrWidth);
  if (AxiNarrowDataWidth != snitch_cluster_pkg::NarrowDataWidth)
    $fatal(1, "snitch_cluster_isle: AxiNarrowDataWidth (%0d) contradicts snitch_cluster_pkg::NarrowDataWidth (%0d)",
           AxiNarrowDataWidth, snitch_cluster_pkg::NarrowDataWidth);
  if (AxiWideDataWidth != snitch_cluster_pkg::WideDataWidth)
    $fatal(1, "snitch_cluster_isle: AxiWideDataWidth (%0d) contradicts snitch_cluster_pkg::WideDataWidth (%0d)",
           AxiWideDataWidth, snitch_cluster_pkg::WideDataWidth);
  if (AxiNarrowInIdWidth != snitch_cluster_pkg::NarrowIdWidthIn)
    $fatal(1, "snitch_cluster_isle: AxiNarrowInIdWidth (%0d) contradicts snitch_cluster_pkg::NarrowIdWidthIn (%0d)",
           AxiNarrowInIdWidth, snitch_cluster_pkg::NarrowIdWidthIn);
  if (AxiNarrowOutIdWidth != snitch_cluster_pkg::NarrowIdWidthOut)
    $fatal(1, "snitch_cluster_isle: AxiNarrowOutIdWidth (%0d) contradicts snitch_cluster_pkg::NarrowIdWidthOut (%0d)",
           AxiNarrowOutIdWidth, snitch_cluster_pkg::NarrowIdWidthOut);
  if (AxiWideInIdWidth != snitch_cluster_pkg::WideIdWidthIn)
    $fatal(1, "snitch_cluster_isle: AxiWideInIdWidth (%0d) contradicts snitch_cluster_pkg::WideIdWidthIn (%0d)",
           AxiWideInIdWidth, snitch_cluster_pkg::WideIdWidthIn);
  if (OffloadDmaHart >= OffloadNumCores || !snitch_cluster_pkg::IsaCfg[OffloadDmaHart].Xdma)
    $fatal(1, "snitch_cluster_isle: OffloadDmaHart (%0d) is not the hart this cluster gives the DMA instructions to (its IsaCfg entry has Xdma = 0). Ollivander reads this literal to decide which core issues wide transfers, so a wrong value would surface as an illegal-instruction trap in simulation instead of failing here.", OffloadDmaHart);
  if (OffloadPrimaryHart >= OffloadNumCores)
    $fatal(1, "snitch_cluster_isle: OffloadPrimaryHart (%0d) is outside the %0d cores of this cluster.",
           OffloadPrimaryHart, OffloadNumCores);
  if (AxiWideOutIdWidth != snitch_cluster_pkg::WideIdWidthOut)
    $fatal(1, "snitch_cluster_isle: AxiWideOutIdWidth (%0d) contradicts snitch_cluster_pkg::WideIdWidthOut (%0d)",
           AxiWideOutIdWidth, snitch_cluster_pkg::WideIdWidthOut);

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

  logic          [snitch_cluster_pkg::NrCores-1:0] mxip;

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
      // CutOffloadIntf asks for a CUT; the cell's parameters ask whether to
      // BYPASS one. Passing the flag straight through inverted the intent - the
      // configuration requesting a cut built none, and the one declining it
      // built one (found 2026-09-01 by reading, before the interface had ever
      // carried a transaction). The FlooNoC router cuts its side under the same
      // flag, so this keeps both ends of the offload interface consistent.
      .BypassReq (!RouteCfg.CollectiveCfg.WideRedCfg.CutOffloadIntf),
      .BypassRsp (!RouteCfg.CollectiveCfg.WideRedCfg.CutOffloadIntf)
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
    // Whole-struct tie-off on purpose: with no wide channel declared the response
    // type is the parameter's default, and a member access would not elaborate.
    assign offload_dca_req_cut = '0;
    assign offload_dca_rsp     = '0;
    assign offload_wide_rsp_o  = '0;
  end

  snitch_cluster_wrapper i_cluster (
    .clk_i             (clk_i),
    .rst_ni            (rst_ni),
    .debug_req_i,
    .meip_i,
    .mtip_i,
    .msip_i,
    // Every instance keeps hart base ZERO: mhartid identifies a core only within
    // its own cluster, which is why the offload payload runs through the alias
    // region (unique global IDs are an open question, docs/developer/wip).
    .hart_base_id_i        ('0),
    // The instance identity parameters, filled per instance by the generator.
    .cluster_base_addr_i   (snitch_cluster_pkg::addr_t'(instance_base_addr_i)),
    .cluster_base_offset_i (snitch_cluster_pkg::addr_t'(InstanceWindowSize)),
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
      .NrCores      (snitch_cluster_pkg::NrCores),
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

// Copyright 2026 Fondazione Chips-IT.
// Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Collective-operation stamper for a FlooNoC injector tile.
//
// FlooNoC's chimney reads the collective opcode and the member mask from the AXI
// USER field of the incoming AW and W beats ({mask, op, user} packed, mask on top).
// No CPU store can drive per-transaction user bits, so a software-visible way to
// issue a collective is required: this module sits between the isle's narrow
// master port and the chimney's slave port and STAMPS the collective fields onto
// transactions whose AW address falls into a generated window - the op and the
// member mask are baked at generation time from the SoC description, so the
// firmware expresses a collective by choosing an address, exactly as it already
// expresses a destination. Everything else passes through unchanged, and the
// SoC-wide user width stays untouched: the widened {mask, op, user} signal exists
// only between this module and the chimney.
//
// Only the AW user needs the stamp: the chimney itself stores the AW's collective
// fields and applies them to every following W beat ("the W doesn't have a user
// field, so the AW user field is stored for all following W beats" - its own
// comment), so this module is purely combinational.


module olli_collective_stamper #(
  /// Number of generated collective windows (0 windows degenerates to a pure
  /// user-width adapter, everything stamped Unicast).
  parameter int unsigned NumWindows = 0,
  /// Address, plain-user and collective-field geometries.
  parameter int unsigned AddrWidth = 48,
  parameter int unsigned UserWidth = 5,
  parameter int unsigned MaskWidth = 48,
  parameter int unsigned OpWidth   = 4,
  /// Isle-side (plain user) and chimney-side (collective user) AXI types.
  parameter type slv_req_t = logic,
  parameter type slv_rsp_t = logic,
  parameter type mst_req_t = logic,
  parameter type mst_rsp_t = logic,
  /// One generated window: an inclusive address range and the stamp it carries.
  parameter type win_rule_t = logic,
  parameter win_rule_t [(NumWindows > 0 ? NumWindows : 1)-1:0] Windows = '0
) (
  input  logic                 clk_i,
  input  logic                 rst_ni,
  /// The tile's instance identity (the same per-instance window base the isle
  /// receives): value-carrying (sequential) reductions merge exactly TWO inputs
  /// per router in FlooNoC, so the member set is a generated SUBGROUP and each
  /// instance decides at runtime whether it belongs. Non-members still write -
  /// one payload image serves every instance - but their write is rewritten to
  /// their OWN slot (a harmless local loopback) instead of being stamped.
  input  logic [AddrWidth-1:0] instance_base_i,
  input  slv_req_t             slv_req_i,
  output slv_rsp_t             slv_rsp_o,
  output mst_req_t             mst_req_o,
  input  mst_rsp_t             mst_rsp_i
);

  typedef struct packed {
    logic [MaskWidth-1:0] mask;
    logic [OpWidth-1:0]   op;
    logic [AddrWidth-1:0] dest;
    logic                 hit;
  } stamp_t;

  // A window carries TWO masks with distinct jobs. member_mask elects who may
  // stamp: this instance is a member of window w when its base matches the
  // window's group base under it (a ROW window's member_mask spans only the x
  // bits, so the column heads pass and everyone else is deflected). coll_mask
  // is the 1D reduction set stamped into the header - sequential reductions
  // merge at most two contributions per node, so 2D groups reduce in two
  // dimension-ordered phases and each window's set is a chain (reference
  // behaviour: MAGIA's column-then-row software phases; verified 2026-08-31).
  logic [(NumWindows > 0 ? NumWindows : 1)-1:0] window_member;
  for (genvar w = 0; w < NumWindows; w++) begin : gen_window_membership
    assign window_member[w] =
        ((instance_base_i ^ Windows[w].group_base) & ~Windows[w].member_mask) == '0;
  end

  // ---------------------------------------------------------------------------
  // AW window match: combinational, priority to the first matching window (the
  // generator emits disjoint windows, so priority never decides anything).
  // ---------------------------------------------------------------------------
  stamp_t aw_stamp;
  always_comb begin
    aw_stamp = '0;  // Unicast, empty mask: the stamp of every ordinary write
    for (int unsigned w = 0; w < NumWindows; w++) begin
      if ((slv_req_i.aw.addr >= Windows[w].base) && (slv_req_i.aw.addr <= Windows[w].last)) begin
        // The windows sit on ALIAS addresses (a range the isle's internal
        // decode forwards out, so even the destination instance's own write
        // reaches the network); the real destination is restored here, before
        // the chimney routes by address. A non-member's write is rewritten to
        // its OWN slot instead - unstamped, it loops back at this tile's
        // router and lands locally, so the payload never needs to know the
        // subgroup it is (not) part of.
        if (window_member[w]) begin
          aw_stamp.op   = Windows[w].op;
          aw_stamp.mask = Windows[w].coll_mask;
          // The destination is the writer's own CHAIN HEAD: clearing the
          // collective-mask bits off this instance's base yields the group
          // base under a full mask (yesterday's absolute-dest behaviour) and
          // the head of the writer's own column under a 1D mask - the
          // dimension-ordered two-phase pattern with no per-instance table.
          aw_stamp.dest = (instance_base_i & ~Windows[w].coll_mask) + Windows[w].offs
                          + (slv_req_i.aw.addr - Windows[w].base);
        end else begin
          aw_stamp.dest = instance_base_i + Windows[w].offs
                          + (slv_req_i.aw.addr - Windows[w].base);
        end
        aw_stamp.hit  = 1'b1;
      end
    end
  end

  // ---------------------------------------------------------------------------
  // Request path: pass-through plus the user rebuild. The chimney-side user is
  // {mask, op, user} packed (mask on top), matching floogen's collective user
  // struct by construction.
  // ---------------------------------------------------------------------------
  // FIELD BY FIELD, never a whole-channel assignment: the two sides' channel
  // structs differ in USER width, and SystemVerilog assigns packed structs
  // BIT-WISE, right-aligned - a blanket `mst.aw = slv.aw` shifts every field
  // by the user-width difference (addr/user were fixed after, but size/len/
  // id/burst stayed garbled: aw.size 4B arrived as 1B, and the W's data/strb
  // shifted out of their lanes, feeding ZEROS to the reduction ALU - found
  // 2026-08-31 on the first stamped W ever to leave a cluster; latent before
  // because the standard test's cluster-originated narrow traffic never
  // exits the tile). MAGIA's collective_gen is field-by-field for the same
  // reason.
  always_comb begin
    mst_req_o = '0;
    // AW: rebuilt field by field, user carries the matched stamp.
    mst_req_o.aw.id     = slv_req_i.aw.id;
    mst_req_o.aw.addr   = aw_stamp.hit ? aw_stamp.dest : slv_req_i.aw.addr;
    mst_req_o.aw.len    = slv_req_i.aw.len;
    mst_req_o.aw.size   = slv_req_i.aw.size;
    mst_req_o.aw.burst  = slv_req_i.aw.burst;
    mst_req_o.aw.lock   = slv_req_i.aw.lock;
    mst_req_o.aw.cache  = slv_req_i.aw.cache;
    mst_req_o.aw.prot   = slv_req_i.aw.prot;
    mst_req_o.aw.qos    = slv_req_i.aw.qos;
    mst_req_o.aw.region = slv_req_i.aw.region;
    mst_req_o.aw.atop   = slv_req_i.aw.atop;
    mst_req_o.aw.user   = {aw_stamp.mask, aw_stamp.op, slv_req_i.aw.user[UserWidth-1:0]};
    mst_req_o.aw_valid  = slv_req_i.aw_valid;
    // W: data/strb/last in their own lanes - the chimney reads the collective
    // fields from the AW only and carries them to the W beats itself.
    mst_req_o.w.data    = slv_req_i.w.data;
    mst_req_o.w.strb    = slv_req_i.w.strb;
    mst_req_o.w.last    = slv_req_i.w.last;
    mst_req_o.w.user    = {{(MaskWidth + OpWidth){1'b0}}, slv_req_i.w.user[UserWidth-1:0]};
    mst_req_o.w_valid   = slv_req_i.w_valid;
    // AR: reads never carry a collective stamp (the chimney hardwires the AR
    // channel's collective_op to zero - reductions are write-side by design).
    mst_req_o.ar.id     = slv_req_i.ar.id;
    mst_req_o.ar.addr   = slv_req_i.ar.addr;
    mst_req_o.ar.len    = slv_req_i.ar.len;
    mst_req_o.ar.size   = slv_req_i.ar.size;
    mst_req_o.ar.burst  = slv_req_i.ar.burst;
    mst_req_o.ar.lock   = slv_req_i.ar.lock;
    mst_req_o.ar.cache  = slv_req_i.ar.cache;
    mst_req_o.ar.prot   = slv_req_i.ar.prot;
    mst_req_o.ar.qos    = slv_req_i.ar.qos;
    mst_req_o.ar.region = slv_req_i.ar.region;
    mst_req_o.ar.user   = {{(MaskWidth + OpWidth){1'b0}}, slv_req_i.ar.user[UserWidth-1:0]};
    mst_req_o.ar_valid  = slv_req_i.ar_valid;
    // Response-side ready straight through.
    mst_req_o.b_ready   = slv_req_i.b_ready;
    mst_req_o.r_ready   = slv_req_i.r_ready;
  end

  // ---------------------------------------------------------------------------
  // Response path: pass-through, user narrowed back to the plain width.
  // ---------------------------------------------------------------------------
  // Same field-by-field rule in reverse: a blanket narrower = wider struct
  // assignment truncates the TOP bits, garbling id/resp instead of the user.
  always_comb begin
    slv_rsp_o          = '0;
    slv_rsp_o.aw_ready = mst_rsp_i.aw_ready;
    slv_rsp_o.w_ready  = mst_rsp_i.w_ready;
    slv_rsp_o.ar_ready = mst_rsp_i.ar_ready;
    slv_rsp_o.b.id     = mst_rsp_i.b.id;
    slv_rsp_o.b.resp   = mst_rsp_i.b.resp;
    slv_rsp_o.b.user   = mst_rsp_i.b.user[UserWidth-1:0];
    slv_rsp_o.b_valid  = mst_rsp_i.b_valid;
    slv_rsp_o.r.id     = mst_rsp_i.r.id;
    slv_rsp_o.r.data   = mst_rsp_i.r.data;
    slv_rsp_o.r.resp   = mst_rsp_i.r.resp;
    slv_rsp_o.r.last   = mst_rsp_i.r.last;
    slv_rsp_o.r.user   = mst_rsp_i.r.user[UserWidth-1:0];
    slv_rsp_o.r_valid  = mst_rsp_i.r_valid;
  end

endmodule

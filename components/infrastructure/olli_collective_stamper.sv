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

  // A window may carry a member subgroup narrower than the whole array (the
  // binary-merge constraint above): this instance is a member of window w when
  // its base matches the window's group base under the member mask.
  logic [(NumWindows > 0 ? NumWindows : 1)-1:0] window_member;
  for (genvar w = 0; w < NumWindows; w++) begin : gen_window_membership
    assign window_member[w] =
        ((instance_base_i ^ Windows[w].group_base) & ~Windows[w].mask) == '0;
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
          aw_stamp.mask = Windows[w].mask;
          aw_stamp.dest = Windows[w].dest + (slv_req_i.aw.addr - Windows[w].base);
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
  always_comb begin
    mst_req_o = '0;
    // AW: whole channel forwarded, user rebuilt with the matched stamp.
    mst_req_o.aw        = slv_req_i.aw;
    mst_req_o.aw.user   = {aw_stamp.mask, aw_stamp.op, slv_req_i.aw.user[UserWidth-1:0]};
    if (aw_stamp.hit) mst_req_o.aw.addr = aw_stamp.dest;
    mst_req_o.aw_valid  = slv_req_i.aw_valid;
    // W: forwarded untouched but for the user widening - the chimney reads the
    // collective fields from the AW only and carries them to the W beats itself.
    mst_req_o.w         = slv_req_i.w;
    mst_req_o.w.user    = {{(MaskWidth + OpWidth){1'b0}}, slv_req_i.w.user[UserWidth-1:0]};
    mst_req_o.w_valid   = slv_req_i.w_valid;
    // AR: reads never carry a collective stamp (the chimney hardwires the AR
    // channel's collective_op to zero - reductions are write-side by design).
    mst_req_o.ar        = slv_req_i.ar;
    mst_req_o.ar.user   = {{(MaskWidth + OpWidth){1'b0}}, slv_req_i.ar.user[UserWidth-1:0]};
    mst_req_o.ar_valid  = slv_req_i.ar_valid;
    // Response-side ready straight through.
    mst_req_o.b_ready   = slv_req_i.b_ready;
    mst_req_o.r_ready   = slv_req_i.r_ready;
  end

  // ---------------------------------------------------------------------------
  // Response path: pass-through, user narrowed back to the plain width.
  // ---------------------------------------------------------------------------
  always_comb begin
    slv_rsp_o          = '0;
    slv_rsp_o.aw_ready = mst_rsp_i.aw_ready;
    slv_rsp_o.w_ready  = mst_rsp_i.w_ready;
    slv_rsp_o.ar_ready = mst_rsp_i.ar_ready;
    slv_rsp_o.b        = mst_rsp_i.b;
    slv_rsp_o.b.user   = mst_rsp_i.b.user[UserWidth-1:0];
    slv_rsp_o.b_valid  = mst_rsp_i.b_valid;
    slv_rsp_o.r        = mst_rsp_i.r;
    slv_rsp_o.r.user   = mst_rsp_i.r.user[UserWidth-1:0];
    slv_rsp_o.r_valid  = mst_rsp_i.r_valid;
  end

endmodule

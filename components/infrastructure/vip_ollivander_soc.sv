// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Formatted for Ollivander SoC generator
//
// BENDER: name="riscv-dbg"
//
// The timescale is NOT optional. Without it Questa assigns the module the
// simulator resolution as its time unit (the suppressed warning-3009 class),
// and ClkPeriodJtag's "20ns" literal degenerates: measured TCK was 20 ps -
// a thousand times too fast - so every DMI op collided inside the DTM's CDC
// and every write of a burst but the first was silently dropped.
`timescale 1ns / 1ps
//
// ============================================================================
// vip_ollivander_soc - the generic, IP-agnostic verification IP (wip 2.1)
// ============================================================================
// Simulation-only. Instantiated by the GENERATED testbench, never by the SoC:
// it lives in the Verilator top unit by construction, where the class-based
// jtag_test stack it reuses is legal (the --lib-create restrictions govern the
// hierarchical children, not the top).
//
// MECHANISM vs POLICY: this module owns the mechanism only - the JTAG clock,
// the TAP driver stack (riscv-dbg's jtag_test, proven upstream against the
// same Cheshire this generator integrates) and generic Debug-Spec operations
// (init, 32-bit system-bus reads and writes). Everything project-specific -
// WHICH registers to write, in WHAT order, at WHICH addresses - stays in the
// generated testbench, which receives the addresses from the generator the
// same way the firmware headers do. This is the IP-agnostic constraint of
// wip 2.1: the VIP talks the RISC-V Debug Spec and pins, never a host's
// internals.
//
// The system-bus access size is fixed to 32 bits here BY THE TARGETS, not by
// the channel: the system-controller and scratch registers this agent exists
// to reach are 32-bit registers (the gwaihir lesson - granularity is a
// property of the target; a wider engine corrupts narrow targets).
// ============================================================================

module vip_ollivander_soc #(
  // TCK half-period granularity is the driver's own; 20 ns mirrors the
  // upstream VIP and stays comfortably slower than any generated system clock.
  parameter realtime ClkPeriodJtag = 20ns,
  // Expected IDCODE, passed by the generated testbench (the generator knows
  // the debug module's identity from the host component's configuration).
  parameter logic [31:0] DbgIdCode = 32'h1
) (
  // JTAG side, wired by the testbench straight onto the SoC top's pins.
  output logic jtag_tck_o,
  output logic jtag_trst_no,
  output logic jtag_tms_o,
  output logic jtag_tdi_o,
  input  logic jtag_tdo_i
);

  import jtag_test::*;

  // --------------------------------------------------------------------------
  // JTAG clock and driver stack
  // --------------------------------------------------------------------------
  logic tck = 1'b0;
  always #(ClkPeriodJtag / 2) tck = ~tck;
  assign jtag_tck_o = tck;

  JTAG_DV jtag_dv (tck);

  // TT is deliberately NOT the upstream 0.9: with TA=0.1 and TT=0.9 the
  // driver's sampling delay lands EXACTLY on the next TCK posedge (TA+TT =
  // one full period), and whether the sample precedes or follows the edge
  // becomes a delta-cycle race against the clock generator - upstream wins
  // that race by scheduling luck, this instantiation lost it and read the
  // whole TDO stream one cycle early (IDCODE arrived as (idcode<<1)|1).
  // Sampling at 0.75 lands after the TDO-driving negedge (+0.5) with a
  // quarter-period guard band on both sides: deterministic at any ratio.
  typedef jtag_test::riscv_dbg #(
    .IrLength (5),
    .TA       (ClkPeriodJtag * 0.1),
    .TT       (ClkPeriodJtag * 0.75)
  ) riscv_dbg_t;

  riscv_dbg_t::jtag_driver_t jtag_driver = new (jtag_dv);
  riscv_dbg_t                jtag_dbg    = new (jtag_driver);

  assign jtag_trst_no = jtag_dv.trst_n;
  assign jtag_tms_o   = jtag_dv.tms;
  assign jtag_tdi_o   = jtag_dv.tdi;
  assign jtag_dv.tdo  = jtag_tdo_i;

  // --------------------------------------------------------------------------
  // Generic Debug-Spec operations (the testbench composes the sequence)
  // --------------------------------------------------------------------------


  // One DMI write that is actually GUARANTEED to land: the DTM drops any
  // request issued while the previous one is still crossing the CDC, and
  // jtag_test's write_dmi is fire-and-forget (it never captures the DMI
  // status, so the drop is invisible). Parking in Run-Test/Idle after the
  // shift gives the op time to drain for any plausible TCK/system-clock
  // ratio; the read path needs no twin because read_dmi idles internally.
  task automatic write_dmi_safe(input dm::dm_csr_e csr, input logic [31:0] data);
    jtag_dbg.write_dmi(csr, data);
    jtag_dbg.wait_idle(10);
  endtask

  // TAP liveness and debug-module activation: reset, IDCODE check against the
  // expected value, dmactive handshake, system-bus readiness. Mirrors the
  // upstream jtag_init contract.
  task automatic jtag_init();
    automatic logic [31:0]  idcode;
    automatic dm::dmcontrol_t dmcontrol = '{dmactive: 1, default: '0};
    automatic dm::sbcs_t      sbcs      = '{sbautoincrement: 1'b0,
                                            sbreadondata:    1'b0,
                                            sbaccess:        3'h2,
                                            default:         '0};
    jtag_dbg.reset_master();
    repeat (100) @(posedge tck);
    jtag_dbg.get_idcode(idcode);
    if (idcode != DbgIdCode)
      $fatal(1, "[VIP-JTAG] Unexpected IDCODE: expected 0x%h, got 0x%h", DbgIdCode, idcode);
    write_dmi_safe(dm::DMControl, dmcontrol);
    do jtag_dbg.read_dmi_exp_backoff(dm::DMControl, dmcontrol);
    while (~dmcontrol.dmactive);
    write_dmi_safe(dm::SBCS, sbcs);
    // Read the capability fields back: sbasize=0 with no sbaccess32 means the
    // debug module has NO system bus - every later op would no-op silently.
    jtag_dbg.read_dmi_exp_backoff(dm::SBCS, sbcs);
    if (sbcs.sbasize == 0 && !sbcs.sbaccess32)
      $fatal(1, "[VIP-JTAG] debug module reports NO system bus access");
    $display("[VIP-JTAG] TAP alive, debug module active, system bus ready");
  endtask

  // One 32-bit system-bus write: address, data, then wait for the bus to
  // drain. Every bring-up and boot register this agent exists for is 32-bit.
  task automatic sba_write32(input logic [63:0] addr, input logic [31:0] data);
    automatic dm::sbcs_t sbcs;
    write_dmi_safe(dm::SBAddress1, addr[63:32]);
    write_dmi_safe(dm::SBAddress0, addr[31:0]);
    write_dmi_safe(dm::SBData0, data);
    do jtag_dbg.read_dmi_exp_backoff(dm::SBCS, sbcs);
    while (sbcs.sbbusy);
    // A routing or size failure is NOT silent: sberror latches until cleared,
    // and a bring-up that half-landed is the worst possible state to debug from.
    if (sbcs.sberror != 3'h0) begin
      $fatal(1, "[VIP-JTAG] SBA WRITE FAILED at 0x%h (sberror=%0d)", addr, sbcs.sberror);
    end
  endtask

  // One 32-bit system-bus read, for polling-style checks (EOC, readbacks).
  task automatic sba_read32(input logic [63:0] addr, output logic [31:0] data);
    automatic dm::sbcs_t sbcs = '{sbreadonaddr: 1'b1, sbaccess: 3'h2, default: '0};
    write_dmi_safe(dm::SBCS, sbcs);
    write_dmi_safe(dm::SBAddress1, addr[63:32]);
    write_dmi_safe(dm::SBAddress0, addr[31:0]);
    do jtag_dbg.read_dmi_exp_backoff(dm::SBCS, sbcs);
    while (sbcs.sbbusy);
    jtag_dbg.read_dmi_exp_backoff(dm::SBData0, data);
    if (sbcs.sberror != 3'h0) begin
      $fatal(1, "[VIP-JTAG] SBA READ FAILED at 0x%h (sberror=%0d)", addr, sbcs.sberror);
    end
    // Restore write-mode SBCS so the next sba_write32 starts from a known state.
    sbcs = '{sbaccess: 3'h2, default: '0};
    write_dmi_safe(dm::SBCS, sbcs);
  endtask

  // Write-then-verify, for the handoff's final register: a bring-up that claims
  // completion must have OBSERVED its own effect, not merely posted it.
  task automatic sba_write32_verify(input logic [63:0] addr, input logic [31:0] data);
    automatic logic [31:0] readback;
    sba_write32(addr, data);
    sba_read32(addr, readback);
    if (readback !== data) begin
      $fatal(1, "[VIP-JTAG] readback mismatch at 0x%h: wrote 0x%h, read 0x%h",
             addr, data, readback);
    end
  endtask

endmodule

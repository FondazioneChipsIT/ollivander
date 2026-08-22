// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Formatted for Ollivander SoC generator
//
// BENDER: name="riscv-dbg"
// BENDER: name="axi"
// BENDER: name="apb"
// BENDER: name="serial_link"
//
// The timescale is NOT optional. Without it Questa assigns the module the
// simulator resolution as its time unit (the suppressed warning-3009 class),
// and ClkPeriodJtag's "20ns" literal degenerates: measured TCK was 20 ps -
// a thousand times too fast - so every DMI op collided inside the DTM's CDC
// and every write of a burst but the first was silently dropped.
`timescale 1ns / 1ps
`include "axi/typedef.svh"
`include "axi/assign.svh"
`include "apb/typedef.svh"
//
// ============================================================================
// vip_ollivander_soc - the generic, IP-agnostic verification IP (wip 2.1)
// ============================================================================
// Simulation-only. Instantiated by the GENERATED testbench, never by the SoC.
// The JTAG transport is a self-contained procedural driver (see below): it
// replicates riscv-dbg's jtag_test semantics task by task, but without class
// constructs or queue-typed arguments - Verilator 5.050 crashes on those, and
// a testbench that only one simulator can build is half a testbench. Only the
// dm:: package (types and register offsets) is still imported from riscv-dbg.
//
// MECHANISM vs POLICY: this module owns the mechanism only - the JTAG clock,
// the TAP transport and generic Debug-Spec operations (init, 32-bit
// system-bus reads and writes). Everything project-specific -
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
  parameter logic [31:0] DbgIdCode = 32'h1,
  // --------------------------------------------------------------------------
  // Clock agent. Every period below arrives PRE-RESOLVED from the generated
  // testbench (the generator's formulas are the single source of truth); the
  // only runtime decision the agent keeps is the +fast_boot override of the
  // first generator clock, exactly as the inline testbench used to do.
  // --------------------------------------------------------------------------
  parameter real MainClkPeriodNs = 10.0,           // clk_o, used when NumGenClocks == 0
  parameter int unsigned NumGenClocks = 0,         // domain clock generators (max 64)
  parameter real GenPeriodsNs [64] = '{default: 10.0},
  parameter real GenPeriod0FastNs = 20.0,          // +fast_boot period of generator 0
  parameter bit HasRtClk = 1'b0,
  parameter real RtClkPeriodNs = 1000.0,           // already fast-variant-resolved
  // Reset agent: POR low for PorDelayNs, then released together with rst_no;
  // the lock indicator (clock-generator SoCs) follows LockDelayNs later.
  parameter real PorDelayNs = 100.0,
  parameter bit HasClkGenLock = 1'b0,
  parameter real LockDelayNs = 1000.0,
  // UART RX agent: bit period pre-computed on the divisor the firmware
  // actually programs (integer divisor, so the real rate differs from the
  // nominal baud by percents at high speed - enough to mis-sample a frame).
  parameter bit HasUart = 1'b0,
  parameter real UartBitPeriodNs = 8680.0,
  // --------------------------------------------------------------------------
  // Serial-link agent (wip 2.1, wave two): the off-chip TWIN of the DUT's
  // serial link. The AXI geometry arrives from the host's Slink* contract via
  // the generated testbench; the twin builds its own types from the widths,
  // because the wire protocol needs a STRUCTURAL width match, not type
  // identity - which is what keeps this VIP IP-agnostic. Channel count and
  // lane width come from slink_reg_pkg, the same package the DUT-side
  // instance reads, so the two sides cannot disagree.
  // --------------------------------------------------------------------------
  parameter bit HasSlink = 1'b0,
  parameter int unsigned SlinkAxiAddrWidth = 48,
  parameter int unsigned SlinkAxiDataWidth = 64,
  parameter int unsigned SlinkAxiIdWidth   = 2,
  parameter int unsigned SlinkAxiUserWidth = 10
) (
  // Clocks and resets, driven for the testbench from time zero.
  output logic       clk_o,
  output logic [63:0] gen_clk_o,
  output logic       rt_clk_o,
  output logic       pwr_on_rst_no,
  output logic       rst_no,
  output logic       clk_gen_lock_o,
  // The SoC's UART TX line, observed by the RX agent.
  input  logic       uart_tx_i,
  // JTAG side, wired by the testbench straight onto the SoC top's pins.
  output logic jtag_tck_o,
  output logic jtag_trst_no,
  output logic jtag_tms_o,
  output logic jtag_tdi_o,
  input  logic jtag_tdo_i,
  // Serial-link side, wired straight onto the SoC top's pins (this module is
  // the off-chip end). Tie the inputs to '0 in testbenches without slink.
  input  logic [slink_reg_pkg::NumChannels-1:0]                              slink_rcv_clk_i,
  output logic [slink_reg_pkg::NumChannels-1:0]                              slink_rcv_clk_o,
  input  logic [slink_reg_pkg::NumChannels-1:0][slink_reg_pkg::NumLanes-1:0] slink_i,
  output logic [slink_reg_pkg::NumChannels-1:0][slink_reg_pkg::NumLanes-1:0] slink_o
);


  // --------------------------------------------------------------------------
  // Clock agent
  // --------------------------------------------------------------------------
  initial begin
    clk_o = 1'b0;
    forever #(MainClkPeriodNs / 2.0) clk_o = ~clk_o;
  end

  // Generator clocks: generator 0 honors +fast_boot at runtime (a slower TCK
  // keeps CDCs lockable during the bootrom's frequency measurement); the
  // same-period siblings get a small phase offset to avoid simulation races,
  // both behaviours inherited verbatim from the inline testbench they replace.
  // The 64-clock capacity is arbitrary but free (unused indices elaborate to
  // a single tie) and far above any plausible number of EXTERNAL clock
  // generators; the guard turns a future overflow into a speaking error
  // instead of a mystery.
  if (NumGenClocks > 64) begin : gen_clock_capacity_check
    initial $fatal(1, "[VIP] NumGenClocks=%0d exceeds the clock agent's capacity (64)", NumGenClocks);
  end

  for (genvar i = 0; i < 64; i++) begin : gen_domain_clocks
    if (i < NumGenClocks) begin : gen_active
      initial begin
        automatic real period = GenPeriodsNs[i];
        gen_clk_o[i] = 1'b0;
        if (i == 0) begin
          if ($test$plusargs("fast_boot")) period = GenPeriod0FastNs;
          #0.1; // Small initial phase alignment delay
        end else if (GenPeriodsNs[i] == 10.0) begin
          #(1.1 * i); // Phase offset to prevent simulation clock races
        end
        forever #(period / 2.0) gen_clk_o[i] = ~gen_clk_o[i];
      end
    end else begin : gen_tied
      initial gen_clk_o[i] = 1'b0;
    end
  end

  if (HasRtClk) begin : gen_rt_clk
    initial begin
      rt_clk_o = 1'b0;
      forever #(RtClkPeriodNs / 2.0) rt_clk_o = ~rt_clk_o;
    end
  end else begin : gen_no_rt_clk
    initial rt_clk_o = 1'b0;
  end

  // --------------------------------------------------------------------------
  // Reset agent: the standard power-on sequence the inline testbench used to
  // drive - POR held for PorDelayNs with clocks running, then released along
  // with the functional reset; the generator-lock indicator follows later.
  // --------------------------------------------------------------------------
  initial begin
    pwr_on_rst_no  = 1'b0;
    rst_no         = 1'b0;
    clk_gen_lock_o = 1'b0;
    #(PorDelayNs);
    pwr_on_rst_no = 1'b1;
    rst_no        = 1'b1;
    if (HasClkGenLock) begin
      #(LockDelayNs);
      clk_gen_lock_o = 1'b1; // Assert FLL lock after reset is stable
    end
  end

  // --------------------------------------------------------------------------
  // UART RX agent. The transcript strings are the regression suite's pass
  // criterion and MUST stay byte-identical to the inline monitor's.
  // --------------------------------------------------------------------------
  if (HasUart) begin : gen_uart_rx
    logic [7:0] rx_char;
    string rx_string;
    int rx_char_num = 0;

    initial begin
      rx_string = "";
    end

    always begin
      // 1. Wait for falling edge on the TX line (Start bit)
      @(negedge uart_tx_i);

      // 2. Wait 1.5 bit periods to align sampling at the center of the first data bit
      #(UartBitPeriodNs * 1.5);

      // 3. Sample 8 data bits at 1.0 bit period intervals
      for (int i = 0; i < 8; i++) begin
        rx_char[i] = uart_tx_i;
        #(UartBitPeriodNs);
      end

      // 4. Print the character or accumulate the line of text
      if (rx_char == 8'h04) begin // EOT (End of Transmission)
        $display("[TB] EOT received. Simulation finished.");
        $finish;
      end else if (rx_char == 8'h0A) begin // Newline (\n)
        $write("[UART]: \"%s\"\n", rx_string);
        $fflush(32'h8000_0001); // Flush stdout to see character immediately
        rx_string = "";
        rx_char_num = 0;
      end else if (rx_char >= 32 && rx_char <= 126) begin // Printable ASCII
        rx_string = {rx_string, rx_char};
        rx_char_num = rx_char_num + 1;
      end
    end
  end

  // --------------------------------------------------------------------------
  // JTAG clock and driver stack
  // --------------------------------------------------------------------------
  logic tck = 1'b0;
  always #(ClkPeriodJtag / 2) tck = ~tck;
  assign jtag_tck_o = tck;

  // --------------------------------------------------------------------------
  // Procedural JTAG driver (module-level tasks, packed vectors, no classes).
  //
  // This replicates riscv-dbg's jtag_test driver stack task by task - each
  // task below names its jtag_test counterpart - but with two deliberate
  // departures, both learned the hard way:
  //  * NO class constructs and NO queue-typed arguments: Verilator 5.050
  //    crashes (Internal Error) on fixed arrays passed to class-task queue
  //    args through a virtual interface; packed vectors + an explicit length
  //    are bread-and-butter for every simulator. The transported words are
  //    all <= 64 bits (DMI 41, IDCODE/DTMCS 32, IR 5).
  //  * The sample point is 0.75 of the TCK period, not upstream's 0.9: with
  //    apply at 0.1 and sample at 0.9 the sampling delay lands EXACTLY on the
  //    next posedge (0.1 + 0.9 = one period) and the read becomes a
  //    delta-cycle race against the clock generator - this instantiation
  //    lost it and read the whole TDO stream one bit early. 0.75 lands after
  //    the TDO-driving negedge with a quarter-period guard band on each side.
  // --------------------------------------------------------------------------
  localparam int unsigned IrLength = 5;
  localparam logic [IrLength-1:0] JtagIrIdcode = 'h01;  // selected by TAP reset
  localparam logic [IrLength-1:0] JtagIrDtmcs  = 'h10;
  localparam logic [IrLength-1:0] JtagIrDmi    = 'h11;
  localparam int unsigned DmiWidth = $bits(dm::dmi_req_t);  // {addr, data, op} = 41
  localparam realtime JtagTA = ClkPeriodJtag * 0.10;  // stimuli application time
  localparam realtime JtagTT = ClkPeriodJtag * 0.75;  // TDO sample time

  logic jtag_tms_q  = 1'b0;
  logic jtag_tdi_q  = 1'b0;
  logic jtag_trst_q = 1'b1;
  assign jtag_tms_o   = jtag_tms_q;
  assign jtag_tdi_o   = jtag_tdi_q;
  assign jtag_trst_no = jtag_trst_q;

  // IR cache, exactly as jtag_test::jtag_driver keeps it: a scan is skipped
  // when the IR already holds the wanted opcode; TAP resets restore IDCODE.
  logic [IrLength-1:0] drv_ir_cache = 'h1;

  // jtag_test: clock() - one full TCK cycle, stimuli already applied at +TA.
  task automatic drv_clock();
    #(JtagTT);
    @(posedge tck);
  endtask

  // jtag_test: write_tms()
  task automatic drv_tms(input logic val);
    jtag_tms_q <= #(JtagTA) val;
    drv_clock();
  endtask

  // jtag_test: write_bits() - LSB-first shift, TMS raised with the last bit.
  task automatic drv_write_bits(input logic [63:0] wdata, input int unsigned len,
                                input logic tms_last);
    for (int unsigned i = 0; i < len; i++) begin
      jtag_tdi_q <= #(JtagTA) wdata[i];
      if (i == len - 1) jtag_tms_q <= #(JtagTA) tms_last;
      drv_clock();
    end
    jtag_tms_q <= #(JtagTA) 1'b0;
  endtask

  // jtag_test: readwrite_bits() - same shift, TDO sampled at +TT each cycle.
  task automatic drv_readwrite_bits(output logic [63:0] rdata,
                                    input logic [63:0] wdata,
                                    input int unsigned len, input logic tms_last);
    rdata = '0;
    for (int unsigned i = 0; i < len; i++) begin
      jtag_tdi_q <= #(JtagTA) wdata[i];
      if (i == len - 1) jtag_tms_q <= #(JtagTA) tms_last;
      #(JtagTT);
      rdata[i] = jtag_tdo_i;
      @(posedge tck);
    end
    jtag_tms_q <= #(JtagTA) 1'b0;
  endtask

  // jtag_test: set_ir() - IR scan, skipped when cached.
  task automatic drv_set_ir(input logic [IrLength-1:0] opcode);
    if (drv_ir_cache == opcode) return;
    drv_tms(1);  // select DR scan
    drv_tms(1);  // select IR scan
    drv_tms(0);  // capture IR
    drv_tms(0);  // shift IR
    drv_write_bits(64'(opcode), IrLength, 1'b1);
    drv_tms(1);  // update IR
    drv_tms(0);  // run test idle
    drv_ir_cache = opcode;
  endtask

  // jtag_test: shift_dr() / update_dr()
  task automatic drv_shift_dr();
    drv_tms(1);  // select DR scan
    drv_tms(0);  // capture DR
    drv_tms(0);  // shift DR
  endtask

  task automatic drv_update_dr(input logic exit_1_dr);
    if (exit_1_dr) drv_tms(1);  // exit 1 DR
    drv_tms(1);  // update DR
    drv_tms(0);  // run test idle
  endtask

  // jtag_test: wait_idle() - park in Run-Test/Idle.
  task automatic drv_wait_idle(input int unsigned cycles);
    repeat (cycles) drv_clock();
  endtask

  // jtag_test: riscv_dbg::reset_master() = hard trst pulse + soft reset walk.
  task automatic drv_reset_master();
    jtag_tms_q  <= #(JtagTA) 1'b1;
    jtag_tdi_q  <= #(JtagTA) 1'b0;
    jtag_trst_q <= #(JtagTA) 1'b0;
    repeat (2) drv_clock();
    jtag_trst_q <= #(JtagTA) 1'b1;
    drv_ir_cache = 'h1;
    drv_clock();
    jtag_tms_q <= #(JtagTA) 1'b1;
    jtag_tdi_q <= #(JtagTA) 1'b0;
    repeat (6) drv_clock();  // 5+ TMS-high cycles: Test-Logic-Reset from anywhere
    jtag_tms_q <= #(JtagTA) 1'b0;
    drv_clock();             // Run-Test/Idle
    drv_ir_cache = 'h1;      // TAP reset selects IDCODE
  endtask

  // jtag_test: get_idcode()
  task automatic drv_get_idcode(output logic [31:0] idcode);
    logic [63:0] rd;
    drv_set_ir(JtagIrIdcode);
    drv_shift_dr();
    drv_readwrite_bits(rd, 64'h0, 32, 1'b0);
    drv_update_dr(1'b1);
    idcode = rd[31:0];
  endtask

  // jtag_test: write_dtmcs() / reset_dmi() - dmireset clears the DTM's sticky
  // busy error (set when an op is issued while the previous one is in flight).
  task automatic drv_write_dtmcs(input logic [31:0] data);
    drv_set_ir(JtagIrDtmcs);
    drv_shift_dr();
    drv_write_bits(64'(data), 32, 1'b1);
    drv_update_dr(1'b0);
  endtask

  task automatic drv_reset_dmi();
    drv_write_dtmcs(32'h1 << 16);
  endtask

  // jtag_test: write_dmi() - one DMI write scan: {addr, data, op} LSB-first.
  task automatic drv_write_dmi(input dm::dm_csr_e address, input logic [31:0] data);
    logic [DmiWidth-1:0] req;
    req = {address, data, dm::DTM_WRITE};
    drv_set_ir(JtagIrDmi);
    drv_shift_dr();
    drv_write_bits(64'(req), DmiWidth, 1'b1);
    drv_update_dr(1'b0);
  endtask

  // jtag_test: read_dmi() - read command scan, idle window for the CDC round
  // trip, then a NOP scan that shifts the response out; op status in [1:0].
  task automatic drv_read_dmi(input dm::dm_csr_e address, output logic [31:0] data,
                              input int unsigned wait_cycles,
                              output dm::dtm_op_status_e op);
    logic [DmiWidth-1:0] req;
    logic [63:0] rsp;
    req = {address, 32'b0, dm::DTM_READ};
    drv_set_ir(JtagIrDmi);
    drv_shift_dr();
    drv_write_bits(64'(req), DmiWidth, 1'b1);
    drv_update_dr(1'b0);
    drv_wait_idle(wait_cycles);
    drv_shift_dr();
    req = {address, 32'b0, dm::DTM_NOP};
    drv_readwrite_bits(rsp, 64'(req), DmiWidth, 1'b1);
    drv_update_dr(1'b0);
    op   = dm::dtm_op_status_e'(rsp[1:0]);
    data = rsp[33:2];
  endtask

  // jtag_test: read_dmi_exp_backoff() - retry on DTM busy with exponentially
  // growing idle windows, clearing the sticky error between attempts.
  task automatic drv_read_dmi_exp_backoff(input dm::dm_csr_e address,
                                          output logic [31:0] data);
    dm::dtm_op_status_e op;
    int unsigned trial_idx = 0;
    int unsigned wait_cycles = 8;
    op = dm::DTM_SUCCESS;
    do begin
      if (trial_idx != 0) drv_reset_dmi();
      drv_read_dmi(address, data, wait_cycles, op);
      wait_cycles *= 2;
      trial_idx++;
    end while (op == dm::DTM_BUSY);
  endtask

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
    drv_write_dmi(csr, data);
    drv_wait_idle(10);
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
    drv_reset_master();
    repeat (100) @(posedge tck);
    drv_get_idcode(idcode);
    if (idcode != DbgIdCode)
      $fatal(1, "[VIP-JTAG] Unexpected IDCODE: expected 0x%h, got 0x%h", DbgIdCode, idcode);
    write_dmi_safe(dm::DMControl, dmcontrol);
    do drv_read_dmi_exp_backoff(dm::DMControl, dmcontrol);
    while (~dmcontrol.dmactive);
    write_dmi_safe(dm::SBCS, sbcs);
    // Read the capability fields back: sbasize=0 with no sbaccess32 means the
    // debug module has NO system bus - every later op would no-op silently.
    drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
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
    do drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
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
    do drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
    while (sbcs.sbbusy);
    drv_read_dmi_exp_backoff(dm::SBData0, data);
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

  // Streamed system-bus load: an image of 32-bit words delivered to 'base'
  // through SBA autoincrement - the architected replacement for hierarchical
  // $readmemh preloads (interleaving happens in the DUT's own hardware, and
  // the same sequence works against silicon). Cost is the reason this task
  // exists next to sba_write32: the one-word task pays FOUR DMI operations
  // per word (two address writes, a data write, a status poll - measured
  // 5.36 us/word at the default TCK), which multiplied by an image costs
  // more simulated time than the test it feeds. With sbautoincrement the
  // address is written once and every SBData0 write both fires a bus beat
  // and advances the address, so the steady state is ONE DMI write per beat;
  // where the debug module offers sbaccess64 (read back from SBCS, never
  // assumed) the beats are 64-bit - SBData1 first, SBData0 last, because
  // writing SBData0 is what triggers the beat. Note what 64-bit does NOT buy:
  // each beat still costs two DMI writes, so the JTAG-side traffic stays at
  // one DMI write per 32-bit word either way; the gain is halved bus beats
  // (and parity with Cheshire's own loader, which streams the same way).
  // Errors are checked ONCE at the end: sberror and sbbusyerror are sticky
  // by spec, so a mid-stream failure cannot be missed, only reported with
  // the stream (not the beat) as context - the price of not polling per word.
  // The optional 'verify' pass re-reads the whole image through the same
  // channel (sbreadondata streaming: the address is written once, and every
  // SBData0 READ both returns the current word and fires the next bus read).
  // Measured on the 699-word mesh image: 2199 us with verify against 792 us
  // without - the read stream costs ~1.8x the write stream, because a DMI
  // read is two scans (issue, then capture with backoff) where a write is
  // one. Roughly a 2.8x total, so it is OFF by default:
  // the intended use is one verifying configuration in the regression fleet,
  // the fast path everywhere else - the same split astral's CI applies to
  // its one JTAG-preload entry.
  task automatic sba_load(input logic [63:0] base,
                          input logic [31:0] image[],
                          input int unsigned num_words,
                          input bit verify = 1'b0);
    automatic dm::sbcs_t sbcs;
    automatic int unsigned w = 0;
    automatic bit use64;
    // Capability probe: 64-bit beats only if the hardware declares them.
    drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
    use64 = sbcs.sbaccess64 && !base[2];  // 64-bit needs an 8-byte-aligned base
    sbcs = '{sbautoincrement: 1'b1, sbaccess: use64 ? 3'h3 : 3'h2, default: '0};
    write_dmi_safe(dm::SBCS, sbcs);
    write_dmi_safe(dm::SBAddress1, base[63:32]);
    write_dmi_safe(dm::SBAddress0, base[31:0]);
    if (use64) begin
      for (; w + 1 < num_words; w += 2) begin
        write_dmi_safe(dm::SBData1, image[w+1]);
        write_dmi_safe(dm::SBData0, image[w]);
      end
      if (w < num_words) begin
        // Odd tail: one last 32-bit beat at the already-incremented address.
        sbcs = '{sbautoincrement: 1'b1, sbaccess: 3'h2, default: '0};
        write_dmi_safe(dm::SBCS, sbcs);
        write_dmi_safe(dm::SBData0, image[w]);
        w++;
      end
    end else begin
      for (; w < num_words; w++) write_dmi_safe(dm::SBData0, image[w]);
    end
    // Drain, then the one sticky-error check for the whole stream.
    do drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
    while (sbcs.sbbusy);
    if (sbcs.sberror != 3'h0 || sbcs.sbbusyerror)
      $fatal(1, "[VIP-JTAG] SBA LOAD FAILED (base 0x%h, %0d words: sberror=%0d sbbusyerror=%0d)",
             base, num_words, sbcs.sberror, sbcs.sbbusyerror);
    if (verify) begin
      // Streamed readback: sbreadonaddr fires the read of word 0 when the
      // address is written, then every SBData0 READ both returns the current
      // word and fires the next (sbreadondata + autoincrement). The pass stays
      // on 32-bit beats even where the store used 64: streamed-read DMI cost
      // is ~one operation per 32-bit word in BOTH modes (SBData1+SBData0 per
      // double word vs SBData0 per word), and DMI dominates, so 64-bit would
      // buy nothing here. Like the write stream, no per-word status polling:
      // the sticky sberror/sbbusyerror check at the end covers the stream.
      automatic logic [31:0] rdata;
      sbcs = '{sbreadonaddr: 1'b1, sbreadondata: 1'b1, sbautoincrement: 1'b1,
               sbaccess: 3'h2, default: '0};
      write_dmi_safe(dm::SBCS, sbcs);
      write_dmi_safe(dm::SBAddress1, base[63:32]);
      write_dmi_safe(dm::SBAddress0, base[31:0]);
      for (w = 0; w + 1 < num_words; w++) begin
        drv_read_dmi_exp_backoff(dm::SBData0, rdata);
        if (rdata !== image[w])
          $fatal(1, "[VIP-JTAG] SBA VERIFY MISMATCH at 0x%h: wrote 0x%h, read 0x%h",
                 base + 64'(w) * 4, image[w], rdata);
      end
      // Last word: drop sbreadondata BEFORE consuming it, or the final SBData0
      // read would fire a bus read beyond the image - possibly into unmapped
      // space, latching a spurious sticky sberror. Wait out sbbusy first:
      // writing SBCS while the prefetched read is in flight sets sbbusyerror.
      do drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
      while (sbcs.sbbusy);
      sbcs = '{sbaccess: 3'h2, default: '0};
      write_dmi_safe(dm::SBCS, sbcs);
      drv_read_dmi_exp_backoff(dm::SBData0, rdata);
      if (rdata !== image[num_words-1])
        $fatal(1, "[VIP-JTAG] SBA VERIFY MISMATCH at 0x%h: wrote 0x%h, read 0x%h",
               base + 64'(num_words - 1) * 4, image[num_words-1], rdata);
      // The one sticky-error check for the whole read stream.
      drv_read_dmi_exp_backoff(dm::SBCS, sbcs);
      if (sbcs.sberror != 3'h0 || sbcs.sbbusyerror)
        $fatal(1, "[VIP-JTAG] SBA VERIFY FAILED (base 0x%h, %0d words: sberror=%0d sbbusyerror=%0d)",
               base, num_words, sbcs.sberror, sbcs.sbbusyerror);
      $display("[VIP-JTAG] SBA verify complete: %0d words match at 0x%h", num_words, base);
    end
    // Restore the write-mode SBCS every other task assumes (no autoincrement).
    sbcs = '{sbaccess: 3'h2, default: '0};
    write_dmi_safe(dm::SBCS, sbcs);
    $display("[VIP-JTAG] SBA load complete: %0d words at 0x%h (%s beats%s)",
             num_words, base, use64 ? "64-bit" : "32-bit",
             verify ? ", verified" : "");
  endtask

  // ==========================================================================
  // Serial-link agent (wip 2.1, wave two): the off-chip twin.
  // ==========================================================================
  // Cheshire's shape, simplified: one class driver injects AXI transactions
  // into a mirror serial_link whose DDR pins cross-connect to the DUT's; a
  // random slave terminates the opposite direction. The class constructs and
  // the queue-typed argument below are DELIBERATE: both were probed clean
  // under an unthreaded and cache-free build on 2026-08-22, retiring the
  // poison-era belief that they could not be used (the procedural JTAG
  // driver above predates that finding and stays as is - it works).
  if (HasSlink) begin : gen_slink_agent

    typedef logic [SlinkAxiAddrWidth-1:0]   slink_addr_t;
    typedef logic [SlinkAxiDataWidth-1:0]   slink_data_t;
    typedef logic [SlinkAxiDataWidth/8-1:0] slink_strb_t;
    typedef logic [SlinkAxiIdWidth-1:0]     slink_id_t;
    typedef logic [SlinkAxiUserWidth-1:0]   slink_user_t;
    `AXI_TYPEDEF_ALL(slink_axi, slink_addr_t, slink_id_t, slink_data_t, slink_strb_t, slink_user_t)

    // The twin's config port wants REAL APB structs even though it is tied
    // off: the module body reads the request fields unconditionally. 32-bit
    // geometry per the slink header's own defaults.
    typedef logic [31:0] slink_apb_addr_t;
    typedef logic [31:0] slink_apb_data_t;
    typedef logic [3:0]  slink_apb_strb_t;
    `APB_TYPEDEF_REQ_T(slink_apb_req_t, slink_apb_addr_t, slink_apb_data_t, slink_apb_strb_t)
    `APB_TYPEDEF_RESP_T(slink_apb_rsp_t, slink_apb_data_t)

    slink_axi_req_t  twin_in_req, twin_out_req;
    slink_axi_resp_t twin_in_rsp, twin_out_rsp;

    // Driver side (VIP -> DUT); the terminator side below takes the structs
    // natively, so only the driver needs a DV interface.
    AXI_BUS_DV #(
      .AXI_ADDR_WIDTH (SlinkAxiAddrWidth), .AXI_DATA_WIDTH (SlinkAxiDataWidth),
      .AXI_ID_WIDTH   (SlinkAxiIdWidth),   .AXI_USER_WIDTH (SlinkAxiUserWidth)
    ) slink_mst_dv (.clk_i (clk_o));

    `AXI_ASSIGN_TO_REQ(twin_in_req, slink_mst_dv)
    `AXI_ASSIGN_FROM_RESP(slink_mst_dv, twin_in_rsp)

    // The mirror instance: same slink_reg_pkg as the DUT side, so channel
    // count, lane width and framing agree by construction. Config registers
    // stay at their reset defaults, exactly like the DUT side's - the link
    // comes up from reset, which is the property the preload relies on.
    slink #(
      .axi_req_t (slink_axi_req_t),
      .axi_rsp_t (slink_axi_resp_t),
      .aw_chan_t (slink_axi_aw_chan_t),
      .ar_chan_t (slink_axi_ar_chan_t),
      .r_chan_t  (slink_axi_r_chan_t),
      .w_chan_t  (slink_axi_w_chan_t),
      .b_chan_t  (slink_axi_b_chan_t),
      .apb_req_t (slink_apb_req_t),
      .apb_rsp_t (slink_apb_rsp_t),
      .NoRegCdc  (1'b1)
    ) i_slink_twin (
      .clk_i         (clk_o),
      .rst_ni        (rst_no),
      .clk_sl_i      (clk_o),
      .rst_sl_ni     (rst_no),
      .clk_reg_i     (clk_o),
      .rst_reg_ni    (rst_no),
      .testmode_i    (1'b0),
      .axi_in_req_i  (twin_in_req),
      .axi_in_rsp_o  (twin_in_rsp),
      .axi_out_req_o (twin_out_req),
      .axi_out_rsp_i (twin_out_rsp),
      .apb_req_i     ('0),
      .apb_rsp_o     (),
      .ddr_rcv_clk_i (slink_rcv_clk_i),
      .ddr_rcv_clk_o (slink_rcv_clk_o),
      .ddr_i         (slink_i),
      .ddr_o         (slink_o),
      .isolated_i    ('0),
      .isolate_o     (),
      .clk_ena_o     (),
      .reset_no      ()
    );

    typedef axi_test::axi_driver #(
      .AW (SlinkAxiAddrWidth), .DW (SlinkAxiDataWidth),
      .IW (SlinkAxiIdWidth),   .UW (SlinkAxiUserWidth),
      .TA (MainClkPeriodNs * 0.1 * 1ns), .TT (MainClkPeriodNs * 0.9 * 1ns)
    ) slink_drv_t;
    slink_drv_t slink_drv = new (slink_mst_dv);

    // Terminator of the twin's outbound side. A MODULE, not an axi_test
    // rand_slave: it drives the response channel from reset without a run()
    // task (so no X wedges the shared data-link state machines, the failure
    // an earlier class-based revision had to dodge by starting at time zero),
    // and it contains no constrained randomization - axi_rand_slave's
    // rand_wait is the one construct of this agent Verilator 5.050 cannot
    // execute ("Failed to randomize wait cycles!" at t=0), while the driver
    // class above runs fine. Nothing reads back through the link in the
    // preload flow, so a plain always-ready memory is also the more honest
    // model of what this side must do.
    axi_sim_mem #(
      .AddrWidth (SlinkAxiAddrWidth),
      .DataWidth (SlinkAxiDataWidth),
      .IdWidth   (SlinkAxiIdWidth),
      .UserWidth (SlinkAxiUserWidth),
      .axi_req_t (slink_axi_req_t),
      .axi_rsp_t (slink_axi_resp_t),
      .ApplDelay (MainClkPeriodNs * 0.1 * 1ns),
      .AcqDelay  (MainClkPeriodNs * 0.9 * 1ns)
    ) i_slink_term_mem (
      .clk_i              (clk_o),
      .rst_ni             (rst_no),
      .axi_req_i          (twin_out_req),
      .axi_rsp_o          (twin_out_rsp),
      .mon_w_valid_o      (),
      .mon_w_addr_o       (),
      .mon_w_data_o       (),
      .mon_w_id_o         (),
      .mon_w_user_o       (),
      .mon_w_beat_count_o (),
      .mon_w_last_o       (),
      .mon_r_valid_o      (),
      .mon_r_addr_o       (),
      .mon_r_data_o       (),
      .mon_r_id_o         (),
      .mon_r_user_o       (),
      .mon_r_beat_count_o (),
      .mon_r_last_o       ()
    );

    initial begin
      #1ns;  // let the reset agent drive rst_no before touching the bus
      slink_drv.reset_master();
    end

    // One AXI write burst through the twin. INCR, 64-bit beats; the last
    // beat's strobe masks the pad when the payload ends mid-beat. Bursts
    // never cross a 4 KiB page: the caller below slices accordingly.
    task automatic slink_write_beats(input logic [63:0] addr,
                                     ref slink_data_t beats [$],
                                     input slink_strb_t last_strb);
      automatic slink_drv_t::ax_beat_t ax = new();
      automatic slink_drv_t::w_beat_t  w  = new();
      automatic slink_drv_t::b_beat_t  b;
      // EDGE-ALIGN before the first drive, Cheshire's own discipline: the
      // driver's first ready sample lands TT after the CALL time, and a call
      // from an unaligned instant lets that window straddle the very edge
      // where this link's Mealy ready consumes the beat and falls - the
      // driver then waits forever for a handshake that already happened
      // (one lost afternoon, 2026-08-22).
      @(posedge clk_o);
      ax.ax_addr  = addr[SlinkAxiAddrWidth-1:0];
      ax.ax_len   = beats.size() - 1;
      ax.ax_size  = $clog2(SlinkAxiDataWidth / 8);
      ax.ax_burst = axi_pkg::BURST_INCR;
      slink_drv.send_aw(ax);
      for (int unsigned i = 0; i < beats.size(); i++) begin
        w.w_data = beats[i];
        w.w_strb = (i == beats.size() - 1) ? last_strb : '1;
        w.w_last = (i == beats.size() - 1);
        slink_drv.send_w(w);
      end
      slink_drv.recv_b(b);
      if (b.b_resp != axi_pkg::RESP_OKAY)
        $fatal(1, "[VIP-SLINK] write burst at 0x%h answered %0d", addr, b.b_resp);
    endtask

    // Single 32-bit write, the serial-link counterpart of sba_write32: one
    // aligned 64-bit beat with a half strobe, the word shifted into its lane.
    // This is the CONTROL channel of the slink mode - bring-up of the gated
    // domains and the boot handoff both ride it, because with SerialLink
    // enabled the debug module's SBA writes into cheshire's internal register
    // path vanish behind an OKAY (see the upstream registry), while the same
    // registers answer perfectly from the external AXI ingress this task uses.
    // Gwaihir's slink_enable_tiles() is the reference for the pattern.
    task automatic slink_write32(input logic [63:0] addr,
                                 input logic [31:0] data);
      automatic slink_data_t beats [$];
      automatic logic [63:0] beat_addr = {addr[63:3], 3'b000};
      automatic slink_strb_t strb;
      if (addr[1:0] != 2'b00)
        $fatal(1, "[VIP-SLINK] write32 at 0x%h is not 4-byte aligned", addr);
      beats.delete();
      if (addr[2]) begin
        beats.push_back({data, 32'h0});
        strb = slink_strb_t'(8'hF0);
      end else begin
        beats.push_back({32'h0, data});
        strb = slink_strb_t'(8'h0F);
      end
      slink_write_beats(beat_addr, beats, strb);
    endtask

    // Streamed image load, the serial-link counterpart of sba_load: the SAME
    // contract (base + flat word array), so the generated testbench emits the
    // same packing whatever the transport. Words pair into 64-bit beats;
    // bursts are capped below and sliced at 4 KiB pages as AXI demands.
    task automatic slink_load(input logic [63:0] base,
                              input logic [31:0] image[],
                              input int unsigned num_words);
      automatic slink_data_t beats [$];
      automatic logic [63:0] addr = base;
      automatic int unsigned w = 0;
      automatic slink_strb_t tail_strb;
      if (base[2:0] != 3'b000)
        $fatal(1, "[VIP-SLINK] base 0x%h is not 8-byte aligned", base);
      while (w < num_words) begin
        automatic int unsigned page_left  = (13'h1000 - addr[11:0]) >> 3;
        automatic int unsigned words_left = (num_words - w + 1) >> 1;
        automatic int unsigned n_beats    = (words_left < page_left) ? words_left : page_left;
        // 1 KiB bursts, cheshire upstream's own SlinkBurstBytes cap. The AXI4
        // maximum of 256 beats is PROVEN on both families (dedicated probe,
        // 2026-08-22: full offload to EOT on super_crux and noc_isle) - the
        // one stall ever observed at this line was the twin-geometry framing
        // skew plus the SBA-eaten bring-up, never the burst length. 128 is
        // kept anyway as deliberate practice parity with upstream's VIP.
        if (n_beats > 128) n_beats = 128;
        beats.delete();
        tail_strb = '1;
        for (int unsigned i = 0; i < n_beats; i++) begin
          automatic logic [63:0] beat;
          beat[31:0] = image[w];
          if (w + 1 < num_words) beat[63:32] = image[w+1];
          else begin beat[63:32] = 32'h0; tail_strb = slink_strb_t'(8'h0F); end
          beats.push_back(beat);
          w += 2;
        end
        $display("[VIP-SLINK] burst: %0d beats at 0x%h...", n_beats, addr);
        slink_write_beats(addr, beats, tail_strb);
        $display("[VIP-SLINK] burst done (B received), %0d/%0d words", w, num_words);
        addr += n_beats * 8;
      end
      $display("[VIP-SLINK] load complete: %0d words at 0x%h", num_words, base);
    endtask

  end else begin : gen_no_slink
    assign slink_rcv_clk_o = '0;
    assign slink_o         = '0;
  end

endmodule

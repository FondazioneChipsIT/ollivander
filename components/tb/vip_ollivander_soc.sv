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
  parameter real UartBitPeriodNs = 8680.0
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
  input  logic jtag_tdo_i
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

endmodule

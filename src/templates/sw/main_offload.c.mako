<%namespace file="/license_header.mako" import="license"/>\
${license(prefix='//')}\
/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD TEST FIRMWARE
 * =============================================================================
 * Host-side program of the 'offload' test application: a strict superset of the
 * hello_world firmware. It prints the same greeting first (so the UART coverage
 * of the standard regression is preserved), then drives the five-phase offload
 * sequence on every generated target - load payload, configure entry, start,
 * wait, collect - through the helpers of the generated offload header.
 *
 * Failure policy: on any failed phase the firmware reports the failure on the
 * UART and parks WITHOUT emitting the end-of-transmission character, so the
 * testbench runs into its timeout and the regression marks the test FAILED.
 * The EOT only ever follows a fully passing sequence.
 *
 * The UART machinery and the boot glue below deliberately mirror main.c.mako
 * (the hello_world template): this file must stay self-contained so that the
 * hello_world output remains byte-identical when the offload app is not used.
 * =============================================================================
 */

#include <stdint.h>
#include "${config.project.name}_map.h"
% if config.system_controller:
#include "${top_level_module_name}_regs.h"
% endif
#include "${config.project.name}_offload.h"
% for t_name in offload_targets:
#include "payload_${t_name}.h"
% endfor

<%
# Stack pointer derivation - hello_world places the stack at the very end of the
# boot memory; the offload app does the same UNLESS the payload region is carved
# out of that memory (the default, no 'payload_memory' declared), in which case
# the stack is capped at the payload base so image, stack and payload can never
# meet. The generator resolves both cases into one value (rtl_generator.py).
stack_pointer = hex(offload_host_stack_top)

# UART discovery - same logic as main.c.mako.
all_comps = [config.host] + (config.components if config.components else [])
uart_base = None
for comp in all_comps:
    c_name = getattr(comp, "name", "").lower()
    c_type = getattr(comp, "type", "").lower()
    if "uart" in c_name or "uart" in c_type:
        interfaces = getattr(comp, "interfaces", {}) or {}
        slaves = interfaces.get("axi_slave", [])
        if isinstance(slaves, dict): slaves = [slaves]
        reg_slaves = interfaces.get("regbus_slave", [])
        if isinstance(reg_slaves, dict): reg_slaves = [reg_slaves]
        all_slaves = slaves + reg_slaves
        if all_slaves:
            b_addr = all_slaves[0].get("base_addr", 0)
            uart_base = hex(b_addr) if isinstance(b_addr, int) else str(b_addr)
            break
if not uart_base:
    host_type = getattr(config.host, "type", "").lower()
    if ("cheshire" in host_type or "manager" in host_type) and getattr(config.host, "parameters", {}).get("Uart", True):
        uart_base = "0x03002000" # Default internal Cheshire UART base

# The 16550 divisor, resolved by the generator from software_stack.test_app.baudrate
# so that the testbench monitor times itself on the very same value (rtl_generator.py).
divisor = uart_divisor

# Expected payload result, computed at generation time from the same two constants
# the payload is compiled with (-DOFFLOAD_CHECK_N / -DOFFLOAD_CHECK_XOR): the two
# sides of the comparison share their single source in rtl_generator.py.
expected = (sum(i * i for i in range(1, offload_check_n + 1)) ^ offload_check_xor) & 0xFFFFFFFF
%>\
% if uart_base:
/* Detected UART base address from SoC configuration */
#define UART_BASE ((volatile uint32_t *) ${uart_base})

/* 16550 compatible UART register offsets */
#define UART_RXTX          0
#define UART_IER           1
#define UART_FCR           2
#define UART_LCR           3
#define UART_MCR           4
#define UART_LSR           5
#define UART_MSR           6
#define UART_SCR           7

#define UART_DLL           0
#define UART_DLM           1

/* Initialize UART, 8N1, FIFO enabled - divisor resolved by the generator */
void uart_init(uint16_t div) {
    // Enable DLAB (Divisor Latch Access Bit)
    UART_BASE[UART_LCR] = 0x80;
    // Write divisor LSB and MSB
    UART_BASE[UART_DLL] = div & 0xFF;
    UART_BASE[UART_DLM] = (div >> 8) & 0xFF;
    // Clear DLAB and configure 8N1 (8 data bits, no parity, 1 stop bit)
    UART_BASE[UART_LCR] = 0x03;
    // Enable FIFO and clear TX/RX FIFOs
    UART_BASE[UART_FCR] = 0x07;
}

void print_str(const char *str) {
    while (*str) {
        // Wait until Transmitter Holding Register (THR) / TX FIFO is empty (LSR bit 5)
        while (!(UART_BASE[UART_LSR] & 0x20));
        UART_BASE[UART_RXTX] = *str++;
    }
}
% else:
void print_str(const char *str) {
    // No UART detected in SoC YAML.
    // Dummy function to prevent compiler optimizations from removing the string.
    volatile const char *ptr = str;
    (void)ptr;
}
% endif

/* Hex printer for the collected return values (no libc in this firmware). */
void print_hex(uint32_t v) {
    static const char digits[] = "0123456789abcdef";
    char buf[11] = "0x????????";
    for (int i = 0; i < 8; i++) {
        buf[9 - i] = digits[v & 0xF];
        v >>= 4;
    }
    print_str(buf);
}

/* A failed offload parks here: no EOT is ever sent, the testbench timeout turns
 * the hang into an explicit regression failure instead of a false pass. */
static void offload_fail(const char *target, const char *phase) {
    print_str("[OFFLOAD] FAIL: ");
    print_str(target);
    print_str(" - ");
    print_str(phase);
    print_str("\n");
    while (1) { __asm__ volatile("nop"); }
}

int main(void) {
% if uart_base:
    uart_init(${divisor});
% endif
    print_str("Just take it and give it a wave...\n");

    /* The resolved target list, recorded on the UART so every simulation log
     * documents what this firmware was actually generated to test. */
    print_str("[OFFLOAD] Targets: ${", ".join(offload_targets.keys())}\n");

% if offload_payload_ctrl_group:
    /* The payload memory powers on gated: bring its control group up before
     * the first payload write (helper rationale in the offload header). */
    offload_payload_mem_enable();

% endif
% for t_name, t in offload_targets.items():
    /* ------------------------------------------------------------------
     * Target '${t_name}' ('${t["contract"]}' contract)
     * ------------------------------------------------------------------ */
% if t["sys_ctrl_group"] and offload_power_cycles:
    /* POWER-CYCLE REGRESSION: the whole phase runs TWICE.
     * Cycle 0 proves the function; cycle 1 proves the domain comes back from
     * its own power-down - re-ungate through the FFAR window, re-load the
     * payload (the local memory forgot it), re-run, re-check exactly. This is
     * the test the single-pass flow could never perform: an ungate sequence
     * that only works on the slack of a cold power-on dies here. Emitted for
     * the ARCHITECTED boot only: a force-mode bench pins the power state by
     * construction, and cycling against it hangs the interconnect. */
    for (uint32_t ${t_name}_cycle = 0; ${t_name}_cycle < 2u; ${t_name}_cycle++) {
% endif
% if t["sys_ctrl_group"]:
    ${t_name}_enable();
% endif
% if t["sys_isolate"]:
    if (${t_name}_deisolate() != 0) offload_fail("${t_name}", "de-isolation timed out");
% endif
    ${t_name}_load_payload(payload_${t_name}_image, PAYLOAD_${t_name.upper()}_SIZE_WORDS);
% if t["contract"] == "control_wire":
    ${t_name}_set_bootaddress(OFFLOAD_PAYLOAD_BASE);
    ${t_name}_start();
    if (${t_name}_wait_eoc() != 0) {
        /* Dump the observable state before parking: the return register tells
         * whether the payload's stores ever reached the control unit, and the
         * busy/EOC flags tell how the target looks from the System Controller. */
        print_str("[OFFLOAD] ${t_name} state at EOC timeout: ret_reg=");
        print_hex(${t_name}_get_return());
% if t["sys_busy_status"]:
        print_str(" busy=");
        print_hex(OFFLOAD_SYS_REGS->busy_status.f.${t_name}_busy);
% endif
        print_str(" eoc=");
        print_hex(OFFLOAD_SYS_REGS->eoc_status.f.${t_name}_eoc);
        print_str("\n");
        offload_fail("${t_name}", "EOC timed out");
    }
    {
        uint32_t ret = ${t_name}_get_return();
        if (ret != ${hex(expected)}u) {
            print_str("[OFFLOAD] ${t_name} returned ");
            print_hex(ret);
            print_str(", expected ${hex(expected)}\n");
            offload_fail("${t_name}", "wrong return value");
        }
        print_str("[OFFLOAD] ${t_name} PASS (ret=");
        print_hex(ret);
        print_str(")\n");
    }
% else:
    /* Parallel launch: configure and wake EVERY instance before polling any,
     * so all clusters of the array run the payload concurrently. */
    for (uint32_t n = 0; n < ${t_name.upper()}_OFFLOAD_NUM_INSTANCES; n++) {
        ${t_name}_init_returns(n);
% if t.get("collective_test"):
        if (n == 0) ${t_name}_init_collective();
% endif
        ${t_name}_set_entry(n, OFFLOAD_PAYLOAD_BASE);
    }
    for (uint32_t n = 0; n < ${t_name.upper()}_OFFLOAD_NUM_INSTANCES; n++) {
        ${t_name}_start(n);
    }
    if (${t_name}_wait_done() != 0) {
        /* Dump the slots before parking: which instances/cores never reported
         * localizes the failure (none woke / one hung / a broken write path). */
        print_str("[OFFLOAD] ${t_name} slots at timeout:");
        for (uint32_t n = 0; n < ${t_name.upper()}_OFFLOAD_NUM_INSTANCES; n++) {
            print_str(" |");
            for (uint32_t c = 0; c < ${t_name.upper()}_OFFLOAD_NUM_CORES; c++) {
                print_str(" ");
                print_hex(*(volatile uint32_t *)(uintptr_t)(${t_name.upper()}_OFFLOAD_RETURN_BASE(n) + c * 4u));
            }
        }
        print_str("\n");
        offload_fail("${t_name}", "return slots timed out");
    }
    {
        /* Core 0 of every instance carries the checksum, every other core
         * reports a bare done. */
        for (uint32_t n = 0; n < ${t_name.upper()}_OFFLOAD_NUM_INSTANCES; n++) {
            uint32_t ret = ${t_name}_get_return(n, 0);
            if (ret != ${hex(expected)}u) {
                print_str("[OFFLOAD] ${t_name} inst ");
                print_hex(n);
                print_str(" core 0 returned ");
                print_hex(ret);
                print_str(", expected ${hex(expected)}\n");
                offload_fail("${t_name}", "wrong return value");
            }
            /* Exact per-core accounting (gwaihir's practice): every secondary
             * must return the distinctive code - a dead core is caught by the
             * done-bit poll above, a WRONG-PATH core is caught here, and the
             * two failures print differently on purpose. */
            for (uint32_t c = 1; c < ${t_name.upper()}_OFFLOAD_NUM_CORES; c++) {
                uint32_t sret = ${t_name}_get_return(n, c);
                if (sret != ${hex(offload_secondary_code)}u) {
                    print_str("[OFFLOAD] ${t_name} inst ");
                    print_hex(n);
                    print_str(" core ");
                    print_hex(c);
                    print_str(" returned ");
                    print_hex(sret);
                    print_str(", expected ${hex(offload_secondary_code)}\n");
                    offload_fail("${t_name}", "secondary core returned the wrong code");
                }
            }
        }
% if t.get("collective_test"):
<%
  # The reduced sum, derived INDEPENDENTLY of the payload from the same two
  # constants it is compiled with - the collective twin of 'expected' above.
  exp_sum = (t["num_instances"] * expected) & 0xFFFFFFFF
%>\
        /* Collective phase: the group's core-0 stores were stamped IntAdd and
         * LsbAnd by the tile windows; the network merged them into instance
         * 0's slots. Sum and barrier are checked against generator-derived
         * values, so a lost member, a ghost member or a wrong merge can never
         * pass by accident. */
        if (${t_name}_wait_collective(${hex(exp_sum)}u) != 0) {
            print_str("[COLLECTIVE] ${t_name} collect=");
            print_hex(*(volatile uint32_t *)(uintptr_t)${t_name.upper()}_OFFLOAD_COLLECT_ADDR);
            print_str(" (expected ${hex(exp_sum)}) barrier=");
            print_hex(*(volatile uint32_t *)(uintptr_t)${t_name.upper()}_OFFLOAD_BARRIER_ADDR);
            print_str(" (expected 0x1)\n");
            offload_fail("${t_name}", "collective reduction/barrier");
        }
        print_str("[COLLECTIVE] ${t_name} IntAdd sum + LsbAnd barrier PASS\n");
% endif
        print_str("[OFFLOAD] ${t_name} PASS (");
        print_hex(${t_name.upper()}_OFFLOAD_NUM_INSTANCES);
        print_str(" instances, ret=");
        print_hex(${t_name}_get_return(0, 0));
        print_str(")\n");
    }
% endif
% if t["sys_ctrl_group"]:

    /* Phase over: hand the group back to its power-on state, so the next
     * cycle (and the next target) does not pay for this one (isolate first,
     * then reset and clock - see the helper's rationale). */
    ${t_name}_disable();
% if offload_power_cycles:
    }
    print_str("[OFFLOAD] ${t_name} POWER-CYCLE PASS (2 cycles)\n");
% endif
% if t["num_instances"] > 1 and offload_power_cycles:

    /* SELECTIVE POWER: park the LAST instance ALONE, then run the FIRST one and require it to
     * finish.
     *
     * ARCHITECTED BOOT ONLY, the same condition the power-cycle loop above carries and for
     * the same reason: a force-mode bench pins the power state of every domain by
     * construction, so a firmware write that parks one instance changes nothing the forces
     * do not immediately contradict - and the first transaction addressed to the instance
     * that IS running never completes. The bench cannot express the difference, so the
     * phase would not be a witness there, only a hang: 8.4 ms of simulated silence on
     * noc_subtile until the testbench timeout, with no diagnostic possible because a hung
     * AXI read has nothing to time out against (a hang, not a wrong result: the guard below exists for this). Everything above moves the whole group at once, which is why a control group
     * whose bit indices ALIASED went unnoticed for as long as it did: with one write covering
     * every bit, two instances sharing a bit behave exactly like two instances on their own.
     *
     * This phase is the witness for that. Without the group-relative rule the bit index would be the
     * instance's position inside its own COMPONENT rather than inside the GROUP, so a second
     * component of one isle type restarted from bit 0 - and parking the last instance would
     * have parked the first as well. The first instance would then never answer, and this phase
     * fails by timeout: loudly, and precisely in the case the defect produces.
     *
     * Nothing addresses the parked instance while it is down - a transaction into a gated isle
     * does not complete and no inbound fence exists to terminate it - which is why only
     * instance 0 is driven here. */
    ${t_name}_enable();
% if t["sys_isolate"]:
    /* The whole group first: instance 0 has to inject into the network to report its EOC, and
     * every instance comes out of reset isolated. */
    if (${t_name}_deisolate() != 0) {
        offload_fail("${t_name}", "de-isolation timed out (selective-power phase)");
    }
% endif
    ${t_name}_load_payload(payload_${t_name}_image, PAYLOAD_${t_name.upper()}_SIZE_WORDS);
% if t.get("collective_test"):
    /* One instance alone is not a group: park the collective phase via the
     * meta word (see the payload's guard). This write must happen while EVERY
     * instance is still powered - a store into the gated last instance would
     * never complete and park the host (learned the hard way, 2026-08-31). */
    ${t_name}_disable_collective();
% endif
    ${t_name}_disable_instance(${t_name.upper()}_OFFLOAD_NUM_INSTANCES - 1u);
% if t["sys_isolate"]:
    /* WITNESS FOR THE ISOLATION VECTOR: the parked instance must report isolated while
     * instance 0 must not. A scalar isolation field cannot express that difference - every
     * instance would read the same bit - so this check fails outright on the shape the
     * register had before it was widened to one bit per instance. */
    {
        const uint32_t iso = OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated;
        const uint32_t last = 1u << (${t_name.upper()}_OFFLOAD_NUM_INSTANCES - 1u);
        if ((iso & last) == 0u || (iso & 1u) != 0u) {
            offload_fail("${t_name}", "isolation is not per instance: the parked instance and "
                                      "instance 0 report the same state");
        }
    }
% endif
    ${t_name}_init_returns(0);
% if t["contract"] == "memory_mapped":
    ${t_name}_set_entry(0, OFFLOAD_PAYLOAD_BASE);
    ${t_name}_start(0);
% endif
    if (${t_name}_wait_done_instance(0) != 0) {
        /* Names the SYMPTOM and the suspect, because a diagnostic that does not localize
         * costs hours: instance 0 answered before, and the only thing that changed is that
         * the last instance was parked. */
        offload_fail("${t_name}", "instance 0 stalled with the last instance parked - the "
                                  "control group's bit indices may alias");
    }
    print_str("[OFFLOAD] ${t_name} SELECTIVE-POWER PASS (last parked, first ran)\n");
    ${t_name}_disable();
% endif
% endif

% endfor
    print_str("[OFFLOAD] All targets passed.\n\x03");

    return 0;
}

/*
 * Boot entry point. Placed at the very beginning of the boot memory.
 * The linker script will ensure this function is placed at the exact
 * address the CPU jumps to upon reset de-assertion.
 */
__attribute__((naked, section(".text.init"))) void _start(void) {
    // Initialize the Stack Pointer
    __asm__ volatile("li sp, ${stack_pointer}");

    // Jump to main application
    __asm__ volatile("call main");

    // Catch return from main and halt
    while(1) {
        __asm__ volatile("nop");
    }
}

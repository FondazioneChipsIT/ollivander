/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD PAYLOAD
 * =============================================================================
 * The program the offload test runs ON the accelerator cores. It is deliberately
 * generic: everything target-specific (the stack top, the control registers the
 * result is delivered through, the size of the toy workload) arrives as -D macros
 * from the generated software Makefile, which derives them from the target's
 * Offload* contract. The same source is therefore compiled once per offload
 * target, each time with that target's ISA/ABI and register layout.
 *
 * Execution model ("control_wire" contract):
 *   - every core of the cluster is released at once by the SoC-side fetch-enable
 *     and starts here, at _start, from the per-core boot address the host wrote;
 *   - core 0 sets up a stack in the cluster's local memory and runs main();
 *   - the other cores park in a wfi loop immediately - the toy workload is
 *     single-core on purpose, multi-core payloads are a later evolution;
 *   - main() computes a deterministic checksum, writes it to the cluster's
 *     return-value register and raises EOC, which the host observes through the
 *     System Controller's EOC status flag.
 * =============================================================================
 */

#include <stdint.h>

/* Compile-time contract, provided by the generated Makefile:
 *   OFFLOAD_STACK_TOP   top of the cluster-local memory usable as core-0 stack
 *   OFFLOAD_RETURN_ADDR cluster-internal return value register
 *   OFFLOAD_EOC_ADDR    cluster EoC register (bit 0 raises the eoc wire)
 *   OFFLOAD_CHECK_N     iterations of the toy workload
 *   OFFLOAD_CHECK_XOR   final whitening constant of the toy workload
 * The host firmware computes the same expected value at generation time
 * (main.c, offload section) - the two sides must agree by construction. */
#ifndef OFFLOAD_STACK_TOP
#error "OFFLOAD_STACK_TOP must be provided by the build (see the generated sw/Makefile)"
#endif

/* Stringification for the naked-function inline assembly below: naked functions
 * cannot take asm operands, so the immediate is spliced into the mnemonic text. */
#define _OFFLOAD_STR(x) #x
#define OFFLOAD_STR(x) _OFFLOAD_STR(x)

int main(void) {
    volatile uint32_t *ret_reg = (volatile uint32_t *)OFFLOAD_RETURN_ADDR;
    volatile uint32_t *eoc_reg = (volatile uint32_t *)OFFLOAD_EOC_ADDR;

    /* Toy workload: a sum of squares staged through the cluster-local memory,
     * well below the stack (which grows down from OFFLOAD_STACK_TOP). The
     * volatile round-trip is the point: without it -O2 folds the whole loop
     * into a constant and the cores would prove nothing about the local
     * memory path. Whitened so that the reset value of the return register
     * (zero) can never be mistaken for a passing result. */
    volatile uint32_t *scratch = (volatile uint32_t *)(OFFLOAD_STACK_TOP - 0x8000);
    for (uint32_t i = 1; i <= (uint32_t)OFFLOAD_CHECK_N; i++) {
        scratch[i - 1] = i * i;
    }
    uint32_t acc = 0;
    for (uint32_t i = 0; i < (uint32_t)OFFLOAD_CHECK_N; i++) {
        acc += scratch[i];
    }
    *ret_reg = acc ^ (uint32_t)OFFLOAD_CHECK_XOR;

    /* Signal completion: the write below reaches the cluster control unit and
     * drives the eoc_o wire sampled by the System Controller. */
    *eoc_reg = 1;

    while (1) {
        __asm__ volatile("wfi");
    }
}

/*
 * Common entry point of every core. The PULP-style mhartid packs the core index
 * in its low bits ({cluster_id, 1'b0, core_id[3:0]}): core 0 gets the stack and
 * the workload, everyone else parks. No .data/.bss initialization is performed:
 * the payload keeps its writable state in registers and MMIO on purpose, so the
 * flat binary image is complete as loaded and needs no runtime.
 */
__attribute__((naked, section(".text.init"))) void _start(void) {
    __asm__ volatile(
        "csrr t0, mhartid\n"
        "andi t0, t0, 0xF\n"
        "bnez t0, 1f\n"
        "li   sp, " OFFLOAD_STR(OFFLOAD_STACK_TOP) "\n"
        "call main\n"
        "1:\n"
        "wfi\n"
        "j 1b\n"
    );
}

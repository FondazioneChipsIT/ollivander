<%namespace file="/license_header.mako" import="license"/>\
${license(prefix='//')}\
/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD PAYLOAD
 * =============================================================================
 * The program the offload test runs ON the accelerator cores. It is deliberately
 * generic: everything target-specific (the stack top, the registers or memory the
 * result is delivered through, the size of the toy workload) arrives as -D macros
 * from the generated software Makefile, which derives them from the target's
 * Offload* contract. The same source is therefore compiled once per offload
 * target, each time with that target's ISA/ABI, register layout and CONTRACT KIND:
 *
 *   - "control_wire" (default): every core is released by the SoC-side fetch
 *     enable from the per-core boot address the host wrote; core 0 runs the
 *     workload and delivers the result through the cluster's return-value and
 *     EoC registers, the other cores park immediately.
 *   - "memory_mapped" (-DOFFLOAD_MM): every core wakes from the bootrom's WFI via
 *     the cluster CLINT and jumps here; each core writes (value << 1) | 1 into its
 *     own slot of a return array in the cluster-local memory - core 0 after the
 *     workload, the others right away - and parks. No EoC wire exists: the host
 *     polls the slots through the slave window.
 * =============================================================================
 */

#include <stdint.h>

/* Compile-time contract, provided by the generated Makefile:
 *   OFFLOAD_STACK_TOP   top of the cluster-local memory usable as stack(s)
 *   OFFLOAD_CHECK_N     iterations of the toy workload
 *   OFFLOAD_CHECK_XOR   final whitening constant of the toy workload
 * control_wire only:
 *   OFFLOAD_RETURN_ADDR cluster-internal return value register
 *   OFFLOAD_EOC_ADDR    cluster EoC register (bit 0 raises the eoc wire)
 * memory_mapped only (-DOFFLOAD_MM):
 *   OFFLOAD_RETURN_ADDR base of the per-core return slot array (local memory)
 *   OFFLOAD_HART_BASE   mhartid of the cluster's first core
 * The host firmware computes the same expected value at generation time
 * (main.c, offload section) - the two sides must agree by construction. */
#ifndef OFFLOAD_STACK_TOP
#error "OFFLOAD_STACK_TOP must be provided by the build (see the generated sw/Makefile)"
#endif

/* Stringification for the naked-function inline assembly below: naked functions
 * cannot take asm operands, so the immediate is spliced into the mnemonic text. */
#define _OFFLOAD_STR(x) #x
#define OFFLOAD_STR(x) _OFFLOAD_STR(x)

/* Toy workload: a sum of squares staged through the cluster-local memory, well
 * below the stack region. The volatile round-trip is the point: without it -O2
 * folds the whole loop into a constant and the cores would prove nothing about
 * the local memory path. Whitened so that a reset-value zero can never be
 * mistaken for a passing result. */
static uint32_t offload_workload(void) {
    volatile uint32_t *scratch = (volatile uint32_t *)(OFFLOAD_STACK_TOP - 0x8000);
    for (uint32_t i = 1; i <= (uint32_t)OFFLOAD_CHECK_N; i++) {
        scratch[i - 1] = i * i;
    }
    uint32_t acc = 0;
    for (uint32_t i = 0; i < (uint32_t)OFFLOAD_CHECK_N; i++) {
        acc += scratch[i];
    }
    return acc ^ (uint32_t)OFFLOAD_CHECK_XOR;
}

#ifdef OFFLOAD_MM

int main(void) {
    /* Core index within the cluster: snitch-family harts are numbered globally. */
    uint32_t hartid;
    __asm__ volatile("csrr %0, mhartid" : "=r"(hartid));
    uint32_t idx = hartid - (uint32_t)OFFLOAD_HART_BASE;

    volatile uint32_t *slots = (volatile uint32_t *)OFFLOAD_RETURN_ADDR;
    /* Core 0 carries the checksum; every OTHER core returns the distinctive
     * secondary code, NOT zero - zero is what a wrong code path would store,
     * so the host's exact per-core check could never tell them apart. */
    uint32_t value = (idx == 0) ? offload_workload() : (uint32_t)OFFLOAD_SECONDARY_CODE;

    /* One store closes the protocol: result in the upper bits, done in bit 0. */
    slots[idx] = (value << 1) | 1u;

#ifdef OFFLOAD_COLLECT_ADDR
    /* Narrow-reduction collect: every instance's core 0 writes its RAW result
     * to instance 0's collect slot. The write hits the tile's stamped window
     * (IntAdd plus the group mask), the network merges the group's W payloads
     * and the B response returns only once the whole group has written - the
     * store itself is the rendezvous. The barrier slot exercises LsbAnd the
     * same way. Both come AFTER the slot store above, so the per-core
     * verification never depends on the collective machinery. */
    if (idx == 0) {
        /* Dimension-ordered reduction (FlooNoC's sequential engine merges at
         * most TWO contributions per node, so 2D groups reduce as 1D chains,
         * columns first): every instance adds into its own column head; the
         * heads - elected by the host through the meta word, since hartids
         * restart per instance - then add the column sums along their row
         * onto the final slot the host polls. */
        uint32_t coll_meta = *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_META_LOCAL;
        /* meta == 0 means "collectives off for this run": the host parks the
         * phase in runs where the group is not whole (the selective-power
         * pass wakes ONE instance - a column store there would wait forever
         * for parked peers and leave held state in the routers). */
        if (coll_meta != 0u) {
#ifdef OFFLOAD_COLLECT_COL_ADDR
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_COL_ADDR = value;
        if (coll_meta & 1u) {
            /* Column head: wait for the whole column to land LOCALLY (any
             * partial state reads as the initial zero, so the exact match is
             * race-free), then carry the column sum into the row phase. An
             * absent column parks this poll - the host's bounded
             * wait_collective is the failure detector, by design. */
            uint32_t coll_ydim = (coll_meta >> 1) & 0x7FFFu;
            while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_COL_LOCAL
                   != value * coll_ydim) {}
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_ADDR = value * coll_ydim;
        }
#else
        /* Degenerate 1D group: single phase, straight onto the final slot. */
        (void)coll_meta;
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_ADDR = value;
#endif
        /* PHASE SERIALIZATION before the barrier: two collective streams with
         * different masks interleaved toward one destination can head-of-line
         * deadlock in the router's reduction join (same dst, different mask -
         * the join admits only same-mask flits, and the ones it waits for can
         * be queued behind the ones it ignores). The reference environment
         * never interleaves phases either. Reads do not reduce: every core 0
         * confirms the FINAL sum landed before it arms the barrier stream. */
        {
            uint32_t coll_num = coll_meta >> 16;
            while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_READ_ADDR
                   != value * coll_num) {}
        }
        /* Full-group parallel barrier (LsbAnd is n-ary): the slot is
         * beat-aligned so bit 0 of the beat IS our bit - the machinery ANDs
         * the whole beat's bit 0, never the strobed word (2026-08-31). */
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_BARRIER_ADDR = 1u;
        __asm__ volatile("fence" ::: "memory");
        }
    }
#endif

    while (1) {
        __asm__ volatile("wfi");
    }
}

/*
 * Common entry point, reached by every core the CLINT wakes out of the cluster
 * bootrom. Each core carves its own small stack below OFFLOAD_STACK_TOP (the
 * workload scratch sits far lower), then runs main; parking happens there.
 */
__attribute__((naked, section(".text.init"))) void _start(void) {
    __asm__ volatile(
        "csrr t0, mhartid\n"
        "li   t1, " OFFLOAD_STR(OFFLOAD_HART_BASE) "\n"
        "sub  t0, t0, t1\n"
        "slli t0, t0, 9\n"                              /* 512 B of stack per core */
        "li   sp, " OFFLOAD_STR(OFFLOAD_STACK_TOP) "\n"
        "sub  sp, sp, t0\n"
        "call main\n"
        "1:\n"
        "wfi\n"
        "j 1b\n"
    );
}

#else /* control_wire */

int main(void) {
    volatile uint32_t *ret_reg = (volatile uint32_t *)OFFLOAD_RETURN_ADDR;
    volatile uint32_t *eoc_reg = (volatile uint32_t *)OFFLOAD_EOC_ADDR;

    *ret_reg = offload_workload();

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

#endif /* OFFLOAD_MM */

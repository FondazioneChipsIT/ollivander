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
static uint32_t offload_workload(uint32_t inst_offs) {
    /* inst_offs relocates the scratch area to this instance's window (control_wire
     * arrays); the memory_mapped payloads see themselves at the local alias and pass 0. */
    volatile uint32_t *scratch = (volatile uint32_t *)(OFFLOAD_STACK_TOP - 0x8000 + inst_offs);
    for (uint32_t i = 1; i <= (uint32_t)OFFLOAD_CHECK_N; i++) {
        scratch[i - 1] = i * i;
    }
    uint32_t acc = 0;
    for (uint32_t i = 0; i < (uint32_t)OFFLOAD_CHECK_N; i++) {
        acc += scratch[i];
    }
    return acc ^ (uint32_t)OFFLOAD_CHECK_XOR;
}

#ifdef OFFLOAD_COLLECTIVE_PHASE
/*
 * THE COLLECTIVE PHASES, shared by both contracts. 'idx' is the core index within the
 * cluster, 'value' this instance's contribution (its checksum) and 'coll_meta' the
 * meta word the host wrote before the wake ({num_instances, y_dim, is_mcast_issuer,
 * is_column_head}; zero parks the whole block). Every core of a memory-mapped cluster
 * calls it - core 0 runs the narrow phases, the DMA hart the wide one - while a
 * wire-released cluster calls it from its single running core.
 */
static void offload_collective_phases(uint32_t idx, uint32_t value, uint32_t coll_meta) {
#ifdef OFFLOAD_WIDE_RED
    /* WIDE REDUCTION, DMA HART - two dimension-ordered phases, like the narrow
     * one: a sequential reduction merges at most TWO contributions per router, so
     * a 2D mask cannot be reduced in one pass (measured 2026-09-02: a monolithic
     * mask fired ReductionFrom2MoreInputs on every junction router). Phase 1:
     * every member sends its eight FP64 lanes to its COLUMN head's landing (the
     * host wrote that address in a mailbox - the payload knows neither its base
     * nor its column) with the column mask. Core 0 then runs a barrier across the
     * group, so no column is still merging when a row stream enters the routers.
     * Phase 2: the heads send their column sum to instance 0 with the row mask.
     * No alias on the wide: a write with a non-zero collective mask leaves the
     * cluster through the SoC port whatever its address. Every drain is observed
     * the only way a participant can - a plain remote READ of the landing, which
     * does not reduce - before a flag releases the next step. */
    if (idx == (uint32_t)OFFLOAD_DMA_HART && coll_meta != 0u) {
        register uint32_t zero = 0u, size = (uint32_t)OFFLOAD_WIDE_BYTES, txid, busy;
        uint32_t dst_lo = *(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_COLDST_LOCAL;
        uint32_t dst_hi = *(volatile uint32_t *)(uintptr_t)(OFFLOAD_WIDE_COLDST_LOCAL + 4u);
        /* Phase 1: own lanes -> column head's landing, column mask. */
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_GO_LOCAL != 1u) {}
        {
            register uint32_t ulo = (uint32_t)OFFLOAD_WIDE_USER_COL_LO, uhi = (uint32_t)OFFLOAD_WIDE_USER_COL_HI;
            register uint32_t slo = (uint32_t)OFFLOAD_WIDE_SRC_LOCAL, dlo = dst_lo, dhi = dst_hi;
            __asm__ volatile(".insn r 0x2b, 0, 0x08, x0, %[a], %[b]" :: [a] "r"(ulo), [b] "r"(uhi));
            __asm__ volatile(".insn r 0x2b, 0, 0x00, x0, %[a], %[b]" :: [a] "r"(slo), [b] "r"(zero));
            __asm__ volatile(".insn r 0x2b, 0, 0x01, x0, %[a], %[b]" :: [a] "r"(dlo), [b] "r"(dhi));
            __asm__ volatile(".insn r 0x2b, 0, 0x02, %[t], %[n], x0" : [t] "=r"(txid) : [n] "r"(size));
            do { __asm__ volatile(".insn r 0x2b, 0, 0x04, %[b], x0, x2" : [b] "=r"(busy)); } while (busy != 0u);
        }
        /* The column has merged when the head's landing lane 0 holds y_dim * 1.0
         * (num_instances * 1.0 for a degenerate 1D group): remote plain read. */
        while (*(volatile uint32_t *)(uintptr_t)(dst_lo + 4u) != (uint32_t)OFFLOAD_WIDE_EXP_COL0_HI) {}
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL = 1u;
        __asm__ volatile("fence" ::: "memory");
#ifdef OFFLOAD_WIDE_TWO_PHASE
        /* Phase 2, heads only: own landing (the column sum) -> instance 0, row mask. */
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_GO_LOCAL != 2u) {}
        if (coll_meta & 1u) {
            register uint32_t ulo = (uint32_t)OFFLOAD_WIDE_USER_ROW_LO, uhi = (uint32_t)OFFLOAD_WIDE_USER_ROW_HI;
            register uint32_t slo = (uint32_t)OFFLOAD_WIDE_LANDING_LOCAL, dlo = (uint32_t)OFFLOAD_WIDE_DST_ADDR;
            __asm__ volatile(".insn r 0x2b, 0, 0x08, x0, %[a], %[b]" :: [a] "r"(ulo), [b] "r"(uhi));
            __asm__ volatile(".insn r 0x2b, 0, 0x00, x0, %[a], %[b]" :: [a] "r"(slo), [b] "r"(zero));
            __asm__ volatile(".insn r 0x2b, 0, 0x01, x0, %[a], %[b]" :: [a] "r"(dlo), [b] "r"(zero));
            __asm__ volatile(".insn r 0x2b, 0, 0x02, %[t], %[n], x0" : [t] "=r"(txid) : [n] "r"(size));
            do { __asm__ volatile(".insn r 0x2b, 0, 0x04, %[b], x0, x2" : [b] "=r"(busy)); } while (busy != 0u);
        }
        /* Everyone observes the final landing before releasing the cluster. */
        while (*(volatile uint32_t *)(uintptr_t)(OFFLOAD_WIDE_DST_ADDR + 4u) != (uint32_t)OFFLOAD_WIDE_EXP0_HI) {}
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL = 2u;
        __asm__ volatile("fence" ::: "memory");
#endif
        /* Back to a plain user: dmuser persists across transfers. */
        __asm__ volatile(".insn r 0x2b, 0, 0x08, x0, %[a], %[b]" :: [a] "r"(zero), [b] "r"(zero));
        (void)txid;
    }
#endif
    /* COLLECTIVE PHASES. All of them come AFTER the slot store above, so the
     * per-core verification never depends on the collective machinery.
     *
     * ORDER IS PART OF THE DESIGN, not a detail. Two collective streams must
     * never be in flight toward the same node at once: the router's reduction
     * join admits only flits of the same stream, and the ones it waits for can
     * end up queued behind the ones it ignores - a head-of-line block with no
     * diagnostic. So each phase must be DRAINED before the next begins, and the
     * drain has to be observable by every participant, not just by the issuer.
     * That ranks the phases:
     *   1. BARRIER first, because it drains itself: a member's store returns
     *      only once the whole group has written, so when any core resumes, the
     *      phase is over for everyone. It also aligns the group for what follows.
     *   2. REDUCTION next: internally serialized (column landing, then row) and
     *      closed by a read of the final sum - reads do not reduce, so every
     *      core can confirm the drain.
     *   3. MULTICAST last, because its drain is the hardest to observe: members
     *      see the value land locally while the issuer is still collecting the
     *      B responses. Nothing follows it, so nothing can collide with it.
     * Measured 2026-09-01: with the multicast immediately before the barrier,
     * the barrier-only profile wedged exactly this way. */
    if (idx == 0) {
        /* meta == 0 means "collectives off for this run": the host parks the
         * phase in runs where the group is not whole (the selective-power
         * pass wakes ONE instance - a collective store there would wait
         * forever for parked peers and leave held state in the routers). */
        if (coll_meta != 0u) {
        /* 1. Full-group parallel barrier (LsbAnd is n-ary): the slot is
         * beat-aligned so bit 0 of the beat IS our bit - the machinery ANDs
         * the whole beat's bit 0, never the strobed word (2026-08-31). */
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_BARRIER_ADDR = 1u;
        __asm__ volatile("fence" ::: "memory");
#ifdef OFFLOAD_COLLECT_COL_ADDR
        /* 2. Dimension-ordered reduction (FlooNoC's sequential engine merges at
         * most TWO contributions per node, so 2D groups reduce as 1D chains,
         * columns first): every instance reduces into its own column head; the
         * heads - elected by the host through the meta word, since hartids
         * restart per instance - then reduce the column results along their
         * row onto the final slot the host polls. The operations are whatever
         * the collective_ctrl register holds: the payload never assumes one. */
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_COL_ADDR = value;
        if (coll_meta & 1u) {
            /* Column head: wait for the column result to land LOCALLY. The
             * network writes it in one piece, so "no longer the EMPTY sentinel
             * the host filled" is race-free and needs no expected value; then
             * carry WHAT LANDED into the row phase. An absent column parks this
             * poll - the host's bounded wait_collective is the failure
             * detector, by design. */
            while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_COL_LOCAL == OFFLOAD_COLL_EMPTY) {}
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_ADDR =
                *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_COL_LOCAL;
        }
#elif defined(OFFLOAD_COLLECT_ADDR)
        /* Degenerate 1D group: single phase, straight onto the final slot. */
        *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_ADDR = value;
#endif
#ifdef OFFLOAD_COLLECT_READ_ADDR
        /* Everyone waits for the final landing (op-agnostic, as above) before
         * the next phase: the observable drain the phase order rests on. */
#ifdef OFFLOAD_ROOT_SHADOWED
        /* This cluster decodes instance 0's addresses as its OWN memory (no local alias
         * base in the contract), so only instance 0 - the multicast issuer, meta bit 1 -
         * can observe the landing; the others would spin on their own unwritten slot.
         * The drain still holds: the issuer of the next phase is the one that waits. */
        if (coll_meta & 2u)
#endif
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_COLLECT_READ_ADDR == OFFLOAD_COLL_EMPTY) {}
#endif
#ifdef OFFLOAD_WIDE_RED
        /* 2b. Wide reduction: fill the eight FP64 lanes of this instance's
         * contribution (lane k = (k+1).0, as bit patterns - the payload does no
         * floating point), release the DMA hart, and wait for its completion flag,
         * which it raises only after observing the merged landing. Its drain is
         * therefore observable by everyone, which is what lets it sit before the
         * multicast. Lanes are little-endian doubles: low word first. */
        {
            volatile uint32_t *lanes = (volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_SRC_LOCAL;
            const uint32_t lane_hi[8] = {
                OFFLOAD_WIDE_LANE_HI_0, OFFLOAD_WIDE_LANE_HI_1, OFFLOAD_WIDE_LANE_HI_2, OFFLOAD_WIDE_LANE_HI_3,
                OFFLOAD_WIDE_LANE_HI_4, OFFLOAD_WIDE_LANE_HI_5, OFFLOAD_WIDE_LANE_HI_6, OFFLOAD_WIDE_LANE_HI_7 };
            for (uint32_t k = 0; k < 8u; k++) { lanes[2u * k] = 0u; lanes[2u * k + 1u] = lane_hi[k]; }
            __asm__ volatile("fence" ::: "memory");
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_GO_LOCAL = 1u;
            while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL != 1u) {}
#ifdef OFFLOAD_WIDE_TWO_PHASE
            /* Barrier between the two wide phases (self-draining: this store
             * returns only once the whole group has written), so no column is
             * still merging when a row stream enters the routers. Then phase 2. */
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_BARRIER_ADDR = 1u;
            __asm__ volatile("fence" ::: "memory");
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_GO_LOCAL = 2u;
            while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL != 2u) {}
#endif
        }
#endif
#ifdef OFFLOAD_MCAST_ADDR
        /* 3. Multicast: exactly one member (the meta word elects it) writes
         * once into the stamped window; the network replicates the beat to
         * every member, each landing it at its OWN copy of the slot. Every
         * core 0 waits to see it locally, which is what the host's per-member
         * check verifies from the other side. */
        if (coll_meta & 2u) {
            *(volatile uint32_t *)(uintptr_t)OFFLOAD_MCAST_ADDR = OFFLOAD_MCAST_VALUE;
        }
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_MCAST_LOCAL != OFFLOAD_MCAST_VALUE) {}
#endif
        }
    }
}
#endif

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
    uint32_t value = (idx == 0) ? offload_workload(0u) : (uint32_t)OFFLOAD_SECONDARY_CODE;

    /* One store closes the protocol: result in the upper bits, done in bit 0. */
    slots[idx] = (value << 1) | 1u;

#ifdef OFFLOAD_WIDE_PROBE
    /* WIDE BURST PROBE (no collective involved). The Snitch cores store 64
     * bits, so the only master that can put a 512-bit beat on the wide channel
     * is the cluster iDMA - and it is driven by CUSTOM INSTRUCTIONS that only
     * one hart may execute (the contract names it; on any other hart they trap
     * as illegal). The mnemonics live in the Snitch LLVM only, so they are
     * emitted through `.insn r` on opcode 0x2b, which plain rv32im assembles:
     *   funct7 0x00 dmsrc  rs1=lo rs2=hi     source address
     *   funct7 0x01 dmdst  rs1=lo rs2=hi     destination address
     *   funct7 0x02 dmcpyi rd=txid rs1=size  rs2 field is an IMMEDIATE: bits
     *                                        [21:20] config (0 = 1D), [24:22] channel
     *   funct7 0x04 dmstati rd=status        rs2 immediate: [21:20] 2 = busy
     * The size must be a MULTIPLE OF 64 BYTES or iDMA emits strobed narrow
     * beats instead of full wide ones - which would make this probe pass while
     * proving nothing. */
    if (idx == (uint32_t)OFFLOAD_DMA_HART) {
        register uint32_t slo = (uint32_t)OFFLOAD_WIDE_SRC_LOCAL;
        register uint32_t dlo = (uint32_t)OFFLOAD_WIDE_DST_ADDR;
        register uint32_t zero_hi = 0u;
        register uint32_t size = (uint32_t)OFFLOAD_WIDE_BYTES;
        register uint32_t txid, busy;
        /* dmuser (funct7 0x08): the AXI user the transfers will carry. There is no
         * separate user register in the frontend - the instruction writes the user
         * field of the request being built - so it is set EXPLICITLY to zero
         * (Unicast, empty mask) before a plain transfer, never left to whatever the
         * request register held: with the wide collectives generated in, the
         * chimney READS this field. The reduction step will set {mask, op} here. */
        __asm__ volatile(".insn r 0x2b, 0, 0x08, x0, %[ulo], %[uhi]" ::
                         [ulo] "r"(zero_hi), [uhi] "r"(zero_hi));
        __asm__ volatile(".insn r 0x2b, 0, 0x00, x0, %[slo], %[shi]" ::
                         [slo] "r"(slo), [shi] "r"(zero_hi));
        __asm__ volatile(".insn r 0x2b, 0, 0x01, x0, %[dlo], %[dhi]" ::
                         [dlo] "r"(dlo), [dhi] "r"(zero_hi));
        __asm__ volatile(".insn r 0x2b, 0, 0x02, %[txid], %[size], x0"
                         : [txid] "=r"(txid) : [size] "r"(size));
        do {
            __asm__ volatile(".insn r 0x2b, 0, 0x04, %[busy], x0, x2" : [busy] "=r"(busy));
        } while (busy != 0u);
        (void)txid;
    }
#endif
#ifdef OFFLOAD_COLLECTIVE_PHASE
    /* Every core reads the meta word: core 0 to run the phases, the DMA hart to
     * know whether a wide phase happens this run, the other cores to know how
     * long they must stay awake (see the end of this function). */
    uint32_t coll_meta = *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_META_LOCAL;
    offload_collective_phases(idx, value, coll_meta);
#endif
#if defined(OFFLOAD_COLLECTIVE_PHASE) && defined(OFFLOAD_WIDE_RED)
    /* The DCA computes the wide reduction on THE CORES' FPUs, one lane each: a
     * core parked in WFI is a lane that never answers and a router that never
     * drains. Every core stays spinning until the wide phase has completed. */
    if (coll_meta != 0u) {
#ifdef OFFLOAD_WIDE_TWO_PHASE
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL != 2u) {}
#else
        while (*(volatile uint32_t *)(uintptr_t)OFFLOAD_WIDE_DONE_LOCAL != 1u) {}
#endif
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

/* The build gives the image instance 0's addresses. Two decodes meet inside a PULP
 * cluster, and the two runs that taught it are recorded here so nobody relearns them:
 * the cores' TCDM path is decoded WITHOUT the cluster id - instance 0's local-memory
 * addresses are every cluster's own TCDM, and the space above them is refused as
 * "unmapped" (ERROR_2 when the stack was relocated) - while the peripheral path, where
 * the control unit lives, is decoded WITH the id (an unrelocated EoC landed in instance
 * 0: one EoC out of four). So the stack and the scratch stay at instance 0's addresses
 * and only the control-unit registers move by the instance ordinal read in mhartid:
 * mhartid = OFFLOAD_HART_BASE + instance * OFFLOAD_HART_INST_STRIDE + core, the
 * contract's one description of the hart numbering (a stride of zero says the harts
 * carry no ordinal, and the image serves one instance). */
static inline uint32_t offload_inst_offs(void) {
#if OFFLOAD_HART_INST_STRIDE
    uint32_t hartid;
    __asm__ volatile("csrr %0, mhartid" : "=r"(hartid));
    return ((hartid - (uint32_t)OFFLOAD_HART_BASE) / (uint32_t)OFFLOAD_HART_INST_STRIDE)
           * (uint32_t)OFFLOAD_INST_STRIDE;
#else
    return 0u;
#endif
}

int main(void) {
    const uint32_t inst_offs = offload_inst_offs();
    volatile uint32_t *ret_reg = (volatile uint32_t *)(OFFLOAD_RETURN_ADDR + inst_offs);
    volatile uint32_t *eoc_reg = (volatile uint32_t *)(OFFLOAD_EOC_ADDR + inst_offs);

    const uint32_t value = offload_workload(0u);   /* local memory: canonical, see above */
    *ret_reg = value;

#ifdef OFFLOAD_COLLECTIVE_PHASE
    /* The collective phases, BEFORE the end-of-computation: the host polls the landings
     * only after every instance has signalled, so a phase that never completes shows up
     * as an EoC timeout, and one that completes wrong as a collective verdict. */
    offload_collective_phases(0u, value,
                              *(volatile uint32_t *)(uintptr_t)OFFLOAD_COLL_META_LOCAL);
#endif

    /* Signal completion: the write below reaches the cluster control unit and
     * drives the eoc_o wire sampled by the System Controller. */
    *eoc_reg = 1;

    while (1) {
        __asm__ volatile("wfi");
    }
}

/*
 * Common entry point of every core. The core index comes out of the contract's
 * hart numbering (mhartid = base + instance * stride + core): core 0 gets the
 * stack and the workload, everyone else parks. No .data/.bss initialization is performed:
 * the payload keeps its writable state in registers and MMIO on purpose, so the
 * flat binary image is complete as loaded and needs no runtime.
 */
__attribute__((naked, section(".text.init"))) void _start(void) {
    __asm__ volatile(
        "csrr t0, mhartid\n"
        "li   t1, " OFFLOAD_STR(OFFLOAD_HART_BASE) "\n"
        "sub  t0, t0, t1\n"                            /* mhartid - base */
#if OFFLOAD_HART_INST_STRIDE
        "li   t1, " OFFLOAD_STR(OFFLOAD_HART_INST_STRIDE) "\n"
        "remu t0, t0, t1\n"                            /* core = (mhartid - base) % stride */
#endif
        "bnez t0, 1f\n"                                /* only core 0 runs */
        "li   sp, " OFFLOAD_STR(OFFLOAD_STACK_TOP) "\n"  /* local memory: canonical address */
        "call main\n"
        "1:\n"
        "wfi\n"
        "j 1b\n"
    );
}

#endif /* OFFLOAD_MM */

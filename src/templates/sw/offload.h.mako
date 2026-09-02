<%namespace file="/license_header.mako" import="license"/>\
${license(prefix='//')}\
/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD HELPERS
 * =============================================================================
 * One set of static-inline helpers per offload target, generated from the union
 * of the two halves of the boot contract:
 *   - the SoC-side half (which isolation/fetch-enable/EOC registers exist in the
 *     System Controller) comes from the component's 'system_config' and is
 *     accessed through the PeakRDL-generated types, so a register renamed there
 *     breaks this header at compile time instead of silently misbehaving;
 *   - the IP-internal half (register layout behind the component's slave window,
 *     ISA of its cores) comes from the Offload* localparams of the isle wrapper.
 * Neither half is hand-written here: this file cannot drift from the RTL.
 * =============================================================================
 */

#ifndef ${project_name.upper()}_OFFLOAD_H
#define ${project_name.upper()}_OFFLOAD_H

#include <stdint.h>
#include "${project_name}_map.h"
#include "${top_level_module_name}_regs.h"

<%
sys_ctrl_base_macro = f"{project_name.upper()}_{sys_ctrl.get('name', 'sys_ctrl').upper()}_BASE_ADDR"
sys_regs_type = f"{top_level_module_name}_sys_regs_t"
%>\
/* The System Controller, through its PeakRDL struct overlay. */
#define OFFLOAD_SYS_REGS ((volatile ${sys_regs_type} *)(uintptr_t)${sys_ctrl_base_macro})

/* Payload region, shared by every target (loaded once, fetched by all): either
 * the second quarter of the boot memory (default carve) or the window of the
 * explicit 'test_app.payload_memory' component. Must match payload.ld; both
 * modes and their reasons are explained in rtl_generator.py. */
#define OFFLOAD_PAYLOAD_BASE ${hex(offload_payload_base)}u

/* NO CLOCKED RESET WINDOW HERE, AND NONE IS NEEDED - the ORDER replaces it.
 *
 * Flip-flops with an asynchronous reset sampled synchronously need clock edges while reset is
 * still asserted before the release is safe. A clocked settling window would buy those edges
 * with a spin loop of 512 iterations (measured: 14 cycles each, 7168 host cycles, ~72 us at
 * 100 MHz) because it released the reset with the clock ALREADY RUNNING. The window was a
 * fleet-wide constant justified by "the slowest divided clock any gated domain runs at" - a
 * property of no project in particular - and it had never been tested against a real divisor.
 *
 * The sequence now toggles the reset only while the domain's clock is GATED, so no clock edge
 * falls near the deassertion and the constraint is met by construction rather than by margin.
 * That is the Carfield discipline, and it is also what makes the software-reset path a false
 * path in synthesis (soc_rstgen.sv.mako explains the other half). Cost: nothing, and one
 * fewer magic number to keep true.
 *
 * KEEP THE ORDER. Releasing the reset after starting the clock reintroduces the hazard the
 * window used to paper over, and it will not fail in RTL simulation - recovery and removal are
 * not checked there - so the gate will not catch a regression here. */

% if offload_payload_ctrl_group:
/* The payload memory sits under the '${offload_payload_ctrl_group}' auto control
 * group and powers on gated AND in reset: release the reset FIRST, while the clock is still
 * gated, then start the clock. See the ordering note above for why that direction and not the
 * other. The read-backs drain the posted writes so no later access can overtake either step. */
static inline void offload_payload_mem_enable(void) {
    OFFLOAD_SYS_REGS->${offload_payload_ctrl_group}_rst.w = 0u;
    (void)OFFLOAD_SYS_REGS->${offload_payload_ctrl_group}_rst.w;
    OFFLOAD_SYS_REGS->${offload_payload_ctrl_group}_clk_en.w = 0xFFFFFFFFu;
    (void)OFFLOAD_SYS_REGS->${offload_payload_ctrl_group}_clk_en.w;
}
% endif

/* Bound on every polling loop: sized so a dead target is reported on the UART
 * well before the testbench sim_timeout turns the run into a silent hang (an
 * MMIO poll costs some hundred ns of simulated time - 10k polls stay within a
 * few ms, while the expected EOC latency is tens of microseconds). */
#define OFFLOAD_POLL_LIMIT 10000u

% for t_name, t in offload_targets.items():
<%
T = t_name.upper()
P = project_name.upper()
%>\
/* ===========================================================================
 * Target '${t_name}' - contract '${t["contract"]}'
 * =========================================================================== */

/* IP-internal register layout, from the Offload* contract of the isle. */
#define ${T}_OFFLOAD_CTRL_BASE      (${P}_${T}_BASE_ADDR + ${hex(t["ctrl_offs"])}u)
#define ${T}_OFFLOAD_NUM_CORES      ${t["num_cores"]}u
% if t["contract"] == "control_wire":
#define ${T}_OFFLOAD_EOC_REG        (${T}_OFFLOAD_CTRL_BASE + ${hex(t["eoc_offs"])}u)
#define ${T}_OFFLOAD_BOOT_ADDR_REG  (${T}_OFFLOAD_CTRL_BASE + ${hex(t["boot_addr_offs"])}u)
#define ${T}_OFFLOAD_RETURN_REG     (${T}_OFFLOAD_CTRL_BASE + ${hex(t["return_offs"])}u)
% else:
/* Instance array: a placement box generates N instances at a fixed stride; the
 * firmware drives all of them in parallel. Single-instance targets degenerate
 * to N = 1, stride 0, and the very same code. */
#define ${T}_OFFLOAD_NUM_INSTANCES  ${t["num_instances"]}u
#define ${T}_OFFLOAD_INST_STRIDE    ${hex(t["instance_stride"])}u
#define ${T}_OFFLOAD_INST_BASE(i)   (${P}_${T}_BASE_ADDR + (i) * ${T}_OFFLOAD_INST_STRIDE)
#define ${T}_OFFLOAD_ENTRY_REG(i)   (${T}_OFFLOAD_INST_BASE(i) + ${hex(t["ctrl_offs"])}u + ${hex(t["entry_offs"])}u)
#define ${T}_OFFLOAD_WAKE_REG(i)    (${T}_OFFLOAD_INST_BASE(i) + ${hex(t["ctrl_offs"])}u + ${hex(t["wake_offs"])}u)
#define ${T}_OFFLOAD_RETURN_BASE(i) (${T}_OFFLOAD_INST_BASE(i) + ${hex(t["return_offs"])}u)
/* This target's first bit in its control group, and the group's width: both resolved by
 * the generator from the authority that assigns the RTL bit indices. */
#define ${T}_SYS_CTRL_BIT_BASE      ${t["sys_ctrl_bit_base"]}u
#define ${T}_SYS_CTRL_GROUP_WIDTH   ${t["sys_ctrl_group_width"]}u
% if t["sys_isolate"]:
/* Every instance of this target isolated at once. The isolation field is ONE BIT PER INSTANCE
 * (soc_regs.rdl.mako sizes it from num_instances), so writing a bare 1 would isolate instance 0
 * and RELEASE the other ${t["num_instances"] - 1} - the mask is what makes the whole-target
 * helpers mean the whole target. */
#define ${T}_ISOLATE_MASK          ${"0x%xu" % ((1 << t["num_instances"]) - 1)}
% endif
% endif

% if t["sys_ctrl_group"]:
/* This target's instances sit under the '${t["sys_ctrl_group"]}' auto control
 * group and power on gated: ungate the WHOLE group (clock on, reset released)
 * before the first slave-window access - a transaction into a gated isle never
 * completes and would hang the host. The tile's NoC router itself stays on the
 * always-on system clock (universal_tile.sv), so the network is routable while
 * gated; only the isle behind the chimney needs this bring-up. */
static inline void ${t_name}_enable(void) {
    /* Reset released FIRST, while the clock is still gated, then the clock started - see the
     * ordering note at the top of this header. The read-backs drain the posted writes so the
     * clock cannot start before the release has landed. */
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w = 0u;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w;
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w = 0xFFFFFFFFu;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w;
}

% if t["sys_isolate"]:
/* PER-INSTANCE isolation, the counterpart of ${t_name}_enable_instance / _disable_instance.
 *
 * The status bit is NOT a mere echo of the control bit: it is the cell's own report that the
 * outbound path has drained (axi_isolate raises it only once both channels reached the Isolate
 * state), so the wait is a real handshake and the timeout a real failure. It also reads asserted
 * while the cell is IN RESET - the state registers reset to Isolate - which is exactly why
 * de-isolation is the operation that must be waited on before addressing the block.
 *
 * The clock matters here and differs by topology: a tile-owned cell sits on the always-on
 * network clock and answers whatever the tile's clock does, while an isle-owned cell sits inside
 * the isle on the GATED clock and cannot move until that clock runs. Calling _deisolate_instance
 * after _enable_instance is therefore the order that works in both. */
static inline int ${t_name}_isolate_instance(uint32_t inst) {
    const uint32_t bit = 1u << inst;
    OFFLOAD_SYS_REGS->isolate_ctrl.f.${t_name}_isolate |= bit;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if ((OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated & bit) != 0u) return 0;
    }
    return -1;
}

static inline int ${t_name}_deisolate_instance(uint32_t inst) {
    const uint32_t bit = 1u << inst;
    OFFLOAD_SYS_REGS->isolate_ctrl.f.${t_name}_isolate &= ~bit;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if ((OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated & bit) == 0u) return 0;
    }
    return -1;
}
% endif

/* PER-INSTANCE clock and reset, for the instances of THIS target only.
 *
 * The group's registers carry one bit per controlled tile, and this target's instances start at
 * ${T}_SYS_CTRL_BIT_BASE - published by the generator from the same authority that assigns the
 * bit indices in the RTL (soc_schema.control_group_members), never recomputed here. Read-modify
 * -write is safe: the host is the only writer, single-threaded, and MMIO cannot cache.
 *
 * Same ORDER as the whole-group helpers, and for the same reason: reset released while the
 * clock is still gated on the way up, clock gated before the reset is asserted on the way down.
 *
 * WHAT THESE CANNOT DO: nothing may address an instance that is parked. A transaction into a
 * gated isle does not complete, and no inbound fence exists in either topology to terminate it
 * (see the correction in the disable rationale below). The caller owns that discipline. */
static inline void ${t_name}_enable_instance(uint32_t inst) {
    const uint32_t bit = 1u << (${T}_SYS_CTRL_BIT_BASE + inst);
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w &= ~bit;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w;
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w |= bit;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w;
}

static inline void ${t_name}_disable_instance(uint32_t inst) {
    const uint32_t bit = 1u << (${T}_SYS_CTRL_BIT_BASE + inst);
% if t["sys_isolate"]:
    /* Isolate THIS instance first, exactly as the whole-group helper does and for the same
     * reason - the outbound path must be drained before the clock that would drain it stops.
     * Best-effort, like the group helper: the caller that needs the handshake checked calls
     * ${t_name}_isolate_instance() itself and reads its return value. */
    (void)${t_name}_isolate_instance(inst);
% endif
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w &= ~bit;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w;
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w |= bit;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w;
}

/* Wait for ONE instance's cores, so a phase can require a single instance to finish while its
 * siblings are parked - which ${t_name}_wait_done cannot express, sweeping all of them. */
static inline int ${t_name}_wait_done_instance(uint32_t inst) {
    uint32_t done = 0;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        uint32_t slot = *(volatile uint32_t *)(uintptr_t)(
            ${T}_OFFLOAD_RETURN_BASE(inst) + done * 4u);
        if ((slot & 1u) == 0u) continue;
        if (++done == ${T}_OFFLOAD_NUM_CORES) return 0;
    }
    return -1;
}

/* Put the group back to its power-on state once this target's phase is over.
 *
 * The ORDER IS THE WHOLE POINT and it is the mirror image of the bring-up:
 * isolate FIRST, then remove reset and clock. A block whose clock is stopped
 * cannot answer anything, so a transaction that arrives after the clock is gone
 * hangs the interconnect forever; with the fence closed first, that same
 * transaction terminates cleanly against the isolation instead. The target is
 * quiescent by construction at this point - its EOC has been observed and its
 * return value read - so no traffic of its own is in flight.
 *
 * Beyond the simulated-cycle saving (a gated block has no clock edges to
 * evaluate, which is what makes a 16-cluster array affordable one phase at a
 * time), this exercises the power-down half of the domain's life cycle, which
 * nothing in the suite used to cover. Re-enabling later goes back through
 * ${t_name}_enable(), which releases the reset while the clock is still gated - the ordering
 * that removed the need for a clocked window at all (note at the top of this header).
 *
 * ONE CORRECTION, since this comment carried it for months: the sentence above about a
 * transaction "terminating cleanly against the isolation" describes an INBOUND fence, and no
 * such fence exists in either topology. Every isolation cell in the tree sits on the OUTBOUND
 * path and stops the block injecting into the network; none of them ever sees a transaction
 * arriving at a gated block. Not addressing a gated instance is therefore a firmware
 * responsibility, not a hardware guarantee - which is why the phases below never touch a
 * target they have parked. */
static inline void ${t_name}_disable(void) {
% if t["contract"] == "control_wire":
    /* Power-on state includes the SoC-side wire: fetch_enable lives in the
     * ALWAYS-ON controller and would survive the target's power-down - a
     * re-enabled cluster would then start fetching from its reset-default
     * boot address before the host reconfigures it (power-cycle trap).
     * Stop the fetch first, then isolate, then cut. */
    OFFLOAD_SYS_REGS->fetch_enable.f.${t_name}_fetch_enable = 0;
% endif
% if t["sys_isolate"]:
    OFFLOAD_SYS_REGS->isolate_ctrl.f.${t_name}_isolate = ${T}_ISOLATE_MASK;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if (OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated == ${T}_ISOLATE_MASK) break;
    }
% endif
    /* Clock gated FIRST, then the reset asserted: the assert is asynchronous and needs no
     * edge, so cutting the clock before it means no edge falls near the transition - the
     * mirror of the bring-up order, and the same reason. */
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w = 0u;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_clk_en.w;
    OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w = 0xFFFFFFFFu;
    (void)OFFLOAD_SYS_REGS->${t["sys_ctrl_group"]}_rst.w;
}
% endif

% if t["sys_isolate"]:
/* Bring the domain out of isolation (it resets isolated) and wait for the fence
 * to actually open: returns 0 on success, -1 if the status never cleared. */
static inline int ${t_name}_deisolate(void) {
    OFFLOAD_SYS_REGS->isolate_ctrl.f.${t_name}_isolate = 0;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if (OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated == 0u) return 0;
    }
    return -1;
}

% endif

/* Copy the payload image into the shared payload region and make it visible to
 * the target: fence.i on this host (CVA6 flushes its caches on fence.i, so the
 * bytes actually reach the memory another master will read - the astral lesson,
 * see wip 2.2 reference analysis). */
static inline void ${t_name}_load_payload(const uint32_t *image, uint32_t n_words) {
    volatile uint32_t *dst = (volatile uint32_t *)(uintptr_t)OFFLOAD_PAYLOAD_BASE;
    for (uint32_t i = 0; i < n_words; i++) dst[i] = image[i];
    __asm__ volatile("fence.i" ::: "memory");
}

% if t["contract"] == "control_wire":
/* Point every core of the target at the payload entry, through the per-core
 * boot-address registers behind the slave window. */
static inline void ${t_name}_set_bootaddress(uint32_t boot_addr) {
    for (uint32_t i = 0; i < ${T}_OFFLOAD_NUM_CORES; i++) {
        *(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_BOOT_ADDR_REG + i * ${hex(t["boot_addr_stride"])}u) = boot_addr;
    }
}

/* Release the cores. Deliberately only the fetch-enable wire: the stand-alone
 * boot enable is sampled by the cluster's boot FSM once, right after reset, and
 * raising it here would be a no-op at best (cluster_control_unit.sv). */
static inline void ${t_name}_start(void) {
    OFFLOAD_SYS_REGS->fetch_enable.f.${t_name}_fetch_enable = 1;
}

/* Poll the EOC status flag: 0 on completion, -1 if the target never signalled. */
static inline int ${t_name}_wait_eoc(void) {
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if (OFFLOAD_SYS_REGS->eoc_status.f.${t_name}_eoc) return 0;
    }
    return -1;
}

/* Read back the result the payload left in the target's return register. */
static inline uint32_t ${t_name}_get_return(void) {
    return *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_RETURN_REG;
}
% else:
/* Zero one instance's return slots BEFORE waking it: each slot reads as done
 * only once its core stores (value << 1) | 1, so a stale bit 0 from a previous
 * run must never survive into the poll below. */
static inline void ${t_name}_init_returns(uint32_t inst) {
    for (uint32_t i = 0; i < ${T}_OFFLOAD_NUM_CORES; i++) {
        *(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE(inst) + i * 4u) = 0;
    }
}
% if t.get("collective_test"):

/* Collective (narrow-reduction) slots: instance 0's collect and barrier words,
 * behind the tile's stamped windows. The host reaches them as plain unicast
 * (its own tile carries no stamper), so zeroing and reading are ordinary
 * accesses; only the GROUP's writes are stamped. */
#define ${T}_OFFLOAD_BARRIER_ADDR  ${hex(t["base_addr"] + t["barrier_offs"])}u
#define ${T}_OFFLOAD_COLL_META_ADDR(inst) (${hex(t["base_addr"] + t["coll_meta_offs"])}u + (inst) * ${hex(t["instance_stride"])}u)
#define ${T}_OFFLOAD_COLL_Y_DIM    ${t["y_dim"]}u
% if t.get("collective_reduce"):
#define ${T}_OFFLOAD_COLLECT_ADDR  ${hex(t["base_addr"] + t["collect_offs"])}u
#define ${T}_OFFLOAD_COLL_COL_ADDR(inst)  (${hex(t["base_addr"] + t["collect_col_offs"])}u + (inst) * ${hex(t["instance_stride"])}u)
% endif
% if t.get("collective_wide"):
<%
import struct
_exp = [struct.unpack('<Q', struct.pack('<d', float(t["num_instances"]) * (k + 1)))[0] for k in range(8)]
%>\
/* Wide reduction landing (instance 0): eight FP64 lanes, each the sum over the
 * group of (k+1).0 - compared as BIT PATTERNS the generator computed, so the host
 * does no floating point either and the check is exact. */
#define ${T}_OFFLOAD_WIDE_ADDR     ${hex(t["base_addr"] + t["wide_offs"])}u
#define ${T}_OFFLOAD_WIDE_GO_ADDR(inst)   (${hex(t["base_addr"] + t["coll_meta_offs"] + 4)}u + (inst) * ${hex(t["instance_stride"])}u)
#define ${T}_OFFLOAD_WIDE_DONE_ADDR(inst) (${hex(t["base_addr"] + t["mcast_offs"] + 4)}u + (inst) * ${hex(t["instance_stride"])}u)
#define ${T}_OFFLOAD_WIDE_LANDING(inst)   (${hex(t["base_addr"] + t["wide_offs"])}u + (inst) * ${hex(t["instance_stride"])}u)
#define ${T}_OFFLOAD_WIDE_COLDST(inst)    (${hex(t["base_addr"] + t["wide_col_dst_offs"])}u + (inst) * ${hex(t["instance_stride"])}u)
/* Column head of an instance: its base with the column bits cleared. */
#define ${T}_OFFLOAD_WIDE_COL_HEAD_LANDING(inst) \
    (((${hex(t["base_addr"])}u + (inst) * ${hex(t["instance_stride"])}u) & ~${hex(t["y_mask"])}u) + ${hex(t["wide_offs"])}u)
static const uint64_t ${t_name}_wide_expected[8] = {
% for v in _exp:
    ${hex(v)}ull,
% endfor
};
% endif
% if t.get("collective_mcast"):
/* Multicast landing: one member issues, the network replicates, and each
 * member lands the value at ITS OWN copy of the slot - so verification reads
 * all of them, not one. */
#define ${T}_OFFLOAD_MCAST_ADDR(inst) (${hex(t["base_addr"] + t["mcast_offs"])}u + (inst) * ${hex(t["instance_stride"])}u)
#define ${T}_OFFLOAD_MCAST_VALUE   0x5A11ED00u
% endif

/* Zero every collective landing slot and hand each instance its collective
 * meta word ({y_dim, is_head}): cluster hartids restart at zero per instance,
 * so the payload cannot know its own place in the grid - the head election
 * travels through plain memory, written before any instance wakes. Bases
 * enumerate y-fastest, so instance n's row index is n % y_dim. */
static inline void ${t_name}_init_collective(void) {
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_BARRIER_ADDR = 0;
% if t.get("collective_wide"):
    for (uint32_t k = 0; k < 8u; k++)
        *(volatile uint64_t *)(uintptr_t)(${T}_OFFLOAD_WIDE_ADDR + 8u * k) = 0ull;
% endif
% if t.get("collective_reduce"):
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_COLLECT_ADDR = 0;
% endif
    for (uint32_t n = 0; n < ${T}_OFFLOAD_NUM_INSTANCES; n++) {
% if t.get("collective_reduce"):
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_COLL_COL_ADDR(n) = 0;
% endif
% if t.get("collective_mcast"):
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_MCAST_ADDR(n) = 0;
% endif
% if t.get("collective_wide"):
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_WIDE_GO_ADDR(n) = 0;
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_WIDE_DONE_ADDR(n) = 0;
        /* Every landing zeroed (heads receive column sums), and each instance told
         * where its column head's landing is - the payload cannot compute it. */
        for (uint32_t k = 0; k < 8u; k++)
            *(volatile uint64_t *)(uintptr_t)(${T}_OFFLOAD_WIDE_LANDING(n) + 8u * k) = 0ull;
        *(volatile uint64_t *)(uintptr_t)${T}_OFFLOAD_WIDE_COLDST(n) = (uint64_t)${T}_OFFLOAD_WIDE_COL_HEAD_LANDING(n);
% endif
        /* meta = {num_instances[31:16], y_dim[15:2], is_mcast_issuer[1],
         * is_column_head[0]}. Exactly ONE instance issues the multicast:
         * sixteen issuers would be sixteen multicasts. */
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_COLL_META_ADDR(n) =
            (((n % ${T}_OFFLOAD_COLL_Y_DIM) == 0u) ? 1u : 0u)
            | ((n == 0u) ? 2u : 0u)
            | (${T}_OFFLOAD_COLL_Y_DIM << 2)
            | (${T}_OFFLOAD_NUM_INSTANCES << 16);
    }
}

/* Collectives OFF for the next run: a zero meta word makes every payload skip
 * the whole collective block - used before the selective-power pass, where a
 * lone instance's column store would wait forever for its parked peers. */
static inline void ${t_name}_disable_collective(void) {
    for (uint32_t n = 0; n < ${T}_OFFLOAD_NUM_INSTANCES; n++) {
        *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_COLL_META_ADDR(n) = 0;
    }
}

/* The reduced sum appears in one piece once the network has merged the whole
 * group, so polling for the exact expected value is race-free: any partial
 * state reads as the initial zero. The barrier lands as the LsbAnd of the
 * group's ones. */
static inline int ${t_name}_wait_collective(uint32_t exp_sum) {
    (void)exp_sum;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
% if t.get("collective_reduce"):
        if (*(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_COLLECT_ADDR != exp_sum) continue;
% endif
        if (*(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_BARRIER_ADDR != 1u) continue;
% if t.get("collective_wide"):
        {
            uint32_t ok = 0;
            for (uint32_t k = 0; k < 8u; k++)
                if (*(volatile uint64_t *)(uintptr_t)(${T}_OFFLOAD_WIDE_ADDR + 8u * k) == ${t_name}_wide_expected[k]) ok++;
            if (ok != 8u) continue;
        }
% endif
% if t.get("collective_mcast"):
        /* Every member must hold the multicast value in its own slot: this is
         * what distinguishes a replication from a single write that landed. */
        {
            uint32_t seen = 0;
            for (uint32_t n = 0; n < ${T}_OFFLOAD_NUM_INSTANCES; n++) {
                if (*(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_MCAST_ADDR(n)
                    == ${T}_OFFLOAD_MCAST_VALUE) seen++;
            }
            if (seen != ${T}_OFFLOAD_NUM_INSTANCES) continue;
        }
% endif
        return 0;
    }
    return -1;
}
% endif

/* Publish the payload entry point where the instance's bootrom will read it. */
static inline void ${t_name}_set_entry(uint32_t inst, uint32_t entry) {
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_ENTRY_REG(inst) = entry;
}

/* Wake every core of one instance through its cluster CLINT: the cores sit in
 * the bootrom's WFI since reset, no fetch-enable wire exists on this contract.
 * The caller wakes ALL instances before polling any, so they run in parallel. */
static inline void ${t_name}_start(uint32_t inst) {
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_WAKE_REG(inst) =
        (1u << ${T}_OFFLOAD_NUM_CORES) - 1u;
}

/* Poll the return slots of every instance until every core reported (bit 0
 * set), reading through the slave windows - MMIO on this side, so no cache can
 * hold a stale copy. The budget counts SLOT READS (the sweep resumes at the
 * first pending slot), so the bound holds regardless of the population and the
 * diagnostic failure below still prints well before the testbench timeout. */
static inline int ${t_name}_wait_done(void) {
    uint32_t done = 0;
    const uint32_t total = ${T}_OFFLOAD_NUM_INSTANCES * ${T}_OFFLOAD_NUM_CORES;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        uint32_t inst = done / ${T}_OFFLOAD_NUM_CORES;
        uint32_t core = done % ${T}_OFFLOAD_NUM_CORES;
        uint32_t slot = *(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE(inst) + core * 4u);
        if ((slot & 1u) == 0u) continue;
        if (++done == total) return 0;
    }
    return -1;
}

/* Result a given core of a given instance left in its return slot. */
static inline uint32_t ${t_name}_get_return(uint32_t inst, uint32_t core) {
    return (*(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE(inst) + core * 4u)) >> 1;
}
% endif

% endfor
#endif /* ${project_name.upper()}_OFFLOAD_H */

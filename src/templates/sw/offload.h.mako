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

/* Payload region: the second quarter of the boot memory, shared by every target
 * in turn (the offload test is sequential and blocking). Must match payload.ld;
 * the carve is explained in rtl_generator.py (dyn_mem view aliasing). */
#define OFFLOAD_PAYLOAD_BASE ${hex(offload_payload_base)}u

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
#define ${T}_OFFLOAD_ENTRY_REG      (${T}_OFFLOAD_CTRL_BASE + ${hex(t["entry_offs"])}u)
#define ${T}_OFFLOAD_WAKE_REG       (${T}_OFFLOAD_CTRL_BASE + ${hex(t["wake_offs"])}u)
#define ${T}_OFFLOAD_RETURN_BASE    (${P}_${T}_BASE_ADDR + ${hex(t["return_offs"])}u)
% endif

% if t["sys_isolate"]:
/* Bring the domain out of isolation (it resets isolated) and wait for the fence
 * to actually open: returns 0 on success, -1 if the status never cleared. */
static inline int ${t_name}_deisolate(void) {
    OFFLOAD_SYS_REGS->isolate_ctrl.f.${t_name}_isolate = 0;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        if (!OFFLOAD_SYS_REGS->isolate_status.f.${t_name}_isolated) return 0;
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
/* Zero the per-core return slots BEFORE waking the cores: each slot reads as
 * done only once its core stores (value << 1) | 1, so a stale bit 0 from a
 * previous run must never survive into the poll below. */
static inline void ${t_name}_init_returns(void) {
    for (uint32_t i = 0; i < ${T}_OFFLOAD_NUM_CORES; i++) {
        *(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE + i * 4u) = 0;
    }
}

/* Publish the payload entry point where the cluster bootrom will read it. */
static inline void ${t_name}_set_entry(uint32_t entry) {
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_ENTRY_REG = entry;
}

/* Wake every core at once through the cluster CLINT: the cores sit in the
 * bootrom's WFI since reset, no fetch-enable wire exists on this contract. */
static inline void ${t_name}_start(void) {
    *(volatile uint32_t *)(uintptr_t)${T}_OFFLOAD_WAKE_REG =
        (1u << ${T}_OFFLOAD_NUM_CORES) - 1u;
}

/* Poll the return slots until every core reported (bit 0 set), reading through
 * the slave window - MMIO on this side, so no cache can hold a stale copy. */
static inline int ${t_name}_wait_done(void) {
    /* The budget counts SLOT READS (the sweep restarts on the first pending core),
     * so the bound holds regardless of the core count and the diagnostic failure
     * below still prints well before the testbench timeout. */
    uint32_t done = 0;
    for (uint32_t i = 0; i < OFFLOAD_POLL_LIMIT; i++) {
        uint32_t slot = *(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE + done * 4u);
        if ((slot & 1u) == 0u) continue;
        if (++done == ${T}_OFFLOAD_NUM_CORES) return 0;
    }
    return -1;
}

/* Result a given core left in its return slot (the value above the done bit). */
static inline uint32_t ${t_name}_get_return(uint32_t core) {
    return (*(volatile uint32_t *)(uintptr_t)(${T}_OFFLOAD_RETURN_BASE + core * 4u)) >> 1;
}
% endif

% endfor
#endif /* ${project_name.upper()}_OFFLOAD_H */

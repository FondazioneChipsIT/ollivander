# Ollivander Testbench Guide: Structure and Test Operation

This guide explains the verification environment Ollivander generates: how the testbench is structured, what each agent does, how the SoC is brought up and booted in each mode, what the test applications actually execute, and how to read a transcript. It complements the [SoC Configuration Guide](soc_configuration_guide.md) (which documents the `testbench:` and `simulation:` YAML sections that *parameterize* what is described here) and the [component standardization contract](hw/component_standardization.md) (which documents the `Offload*`, `Preload*` and `ForceBoot*` localparams that components declare and this environment consumes).

The same generated testbench serves both simulators: `make run-sim` (QuestaSim) and `make run-sim-verilator` compile and run the identical `tb_<top>.sv` against the identical firmware, and the suite applies the identical pass criterion to both. Divergences between the two flows are treated as defects, not as facts of life.

---

## 1. What Gets Generated

Two pieces form the environment:

*   **`generated/tb/tb_<top>.sv`** — the per-project testbench, rendered by `src/templates/tb/tb_soc.sv.mako` from the SoC description. It contains no reusable verification logic: it instantiates the DUT, ties off the inputs no agent owns, emits the project-specific preload and monitor blocks, and drives the boot sequence that the project's `boot_mode` calls for.
*   **`components/tb/vip_ollivander_soc.sv`** — the verification IP, hand-written and shared by every project. All reusable agents live here (clocks, reset, UART, JTAG); the testbench instantiates it once as `i_vip` and calls its tasks. This split is deliberate: everything an external agent would do to a real chip goes through the VIP's pins and tasks, while the testbench keeps only what is simulation-only by nature (hierarchical preload, monitors).

## 2. Anatomy of the Generated Testbench

In file order, `tb_<top>.sv` contains:

1.  **Clock and reset declarations** — the DUT-facing signals. Clock *generation* lives in the VIP's clock agent; every period is resolved at generation time (from the project's clock tree) and reaches the VIP as an elaboration parameter, so the only runtime decision left is the `+fast_boot` plusarg, which shortens generator 0's period for simulation speed.
2.  **Time-zero tie-offs** — one `initial` block assigning, with no delays, every DUT input that no agent owns: strap pins (`boot_mode_i`, `test_mode_i`), idle levels (UART RX idle-high), and the per-instance inputs the configuration routed to the top (e.g. `*_debug_req_i`). Nothing here sequences anything: it is the "everything else is quiet" baseline.
3.  **The DUT instantiation** — the SoC top (not the chip top: pads are exercised by synthesis flows, not by this bench).
4.  **Memory preload** (`$readmemh`, or a streamed load inside the boot sequence under `preload_mode: jtag`/`slink`) — see section 5.
5.  **AXI transaction monitors** — see section 6.
6.  **The VIP instantiation** — with the resolved clock periods, the JTAG IDCODE, and the UART bit period pre-computed on the same divisor the firmware programs (so monitor and firmware cannot disagree about the baud rate; see `software_stack.baudrate`).
7.  **The test sequence** — one `initial` block: wait for power-on reset release, then the boot sequence of the project's `boot_mode` (section 4), then a long watchdog delay and `$finish`. The watchdog is the *failure* path: a passing run terminates earlier, from inside the VIP, when the firmware signals EOT (section 7). A `CUSTOM TEST STIMULI` marker inside this block is the intended place for user-written stimulus.
8.  **A time beacon** — `[TB_TIME] Simulation time: ...` printed every 100 us of simulated time, so a hung run is distinguishable from a slow one by transcript alone.

## 3. The Verification IP and Its Agents

*   **Clock agent** — generates the main clock and up to 64 additional generated clocks, all with pre-resolved periods. Runtime knob: `+fast_boot` only.
*   **Reset agent** — the standard power-on sequence: POR asserted for a fixed delay, then `pwr_on_rst_ni` and `rst_ni` released together. The testbench's boot sequence starts by waiting on this release.
*   **UART RX agent** — samples the SoC's TX line at the pre-computed bit period and prints every received character under the `[UART]:` tag. It is also the **end-of-test detector**: when the received character is `0x04` (EOT), it prints `[TB] EOT received. Simulation finished.` and calls `$finish`. The firmware, not the testbench, decides when the test is over.
*   **JTAG driver stack** — a procedural replica of riscv-dbg's `jtag_test` driver, task by task, but without class-based timing constructs (which is what lets the same VIP compile under Verilator). Public tasks: `jtag_init()` (TAP reset, IDCODE check, debug module activation) and the System Bus Access family `sba_write32(addr, data)`, `sba_read32(addr, data)`, `sba_write32_verify(addr, data)`, plus the streamed `sba_load` that carries the whole firmware image under `preload_mode: jtag` — memory-mapped accesses through the debug module, i.e. the same path an external debugger would use on silicon.
*   **Serial-link agent** (`gen_slink_agent`, elaborated only when the host declares `HasSlinkPreload`) — an off-chip twin of the host's own `serial_link` instance, driven by an `axi_test` driver class on its AXI side and terminated by an `axi_sim_mem` on the outbound side. Public tasks: `slink_write32(addr, data)` (the control channel: gated-domain bring-up and boot handoff under `preload_mode: slink`) and the streamed `slink_load` (the image, 1 KiB bursts). The classes live in the top unit, where Verilator accepts them; the one construct it cannot execute, `axi_rand_slave`'s constrained randomization, is exactly why the terminator is a module.

## 4. Boot Sequences by `boot_mode`

### 4.1 `jtag` and `slink` (the architected paths)

The timeline, entirely through pins and registers, with nothing forced:

1.  Wait for POR release, then a short settle delay.
2.  `i_vip.jtag_init()` — TAP and debug module up. **`jtag` boot only**: under `boot_mode: slink` this step does not exist — the TAP is never touched, and the serial link carries every write of the steps below (the exact shape of the reference testbenches' `PRELMODE=1` branches, which never initialize JTAG). The hybrid — `jtag` boot with `slink` preload — keeps this step as a per-project liveness check of the debug path while the link carries the writes.
3.  **Bring-up of gated domains, clocks first**: the testbench writes the system controller's clock-enable registers for every domain its `bring_up` mask covers (section 4.3). Domains left out are commented out explicitly in the generated code, one line each, with the reason.
4.  **A clocked reset window** (~1 us), then reset release for the same domains. Two phases because gated domains with flip-flops using asynchronous reset sampled synchronously (FFAR) need clock edges while reset is asserted before the release is safe.
5.  **Architected image load** (`preload_mode: jtag` or `slink`, section 5): one streamed load per preload region — `sba_load` over the debug module, or `slink_load` over the serial-link twin — after the bring-up (the image may live in a gated tile) and before the handoff (the host must find it on wake-up). Under `slink` the bring-up and handoff writes ride the serial link too.
6.  **Boot handoff via SBA**: the entry pointer and `argc` are written first, and the boot-mode/go register **last** — the host's preboot loop polls that register, so write ordering replaces any force-and-release dance. The entry-pointer write uses `sba_write32_verify` (its readback is race-free because the boot flow never writes that register); the scratch registers the bootrom clears on use are deliberately not read back.

### 4.2 `force` (the legacy path, kept under regression)

The testbench forces the system controller's clock-enable and reset registers directly from time zero, holds the host's entry point through the `ForceBoot*` localparams the host wrapper declares (`ForceBootPath` names the scratch register hierarchically, `ForceBootVal` the value), and releases the forces either after `testbench.boot_force_delay_ns` or when the AXI monitor on the boot memory observes the first instruction fetch — whichever the project configures. This path costs simulation performance under Verilator (the forced/observed modules cannot be hierarchical blocks) and is scheduled for replacement by the architected path everywhere (wip chapter 2); it stays covered on two example projects precisely so the schema default remains under regression.

### 4.3 `bring_up` masks

`testbench.bring_up` decides how much of the SoC the testbench powers up: `all` (every managed domain) or `minimal` — only the domains the test actually needs at boot: the boot-critical set (host plus whatever holds the boot image) plus the declared targets of the test application. Everything else stays gated, and the *firmware* ungates it when its own phase requires it — which is what makes the firmware's bring-up code a tested artifact rather than dead code. The derivation is printed into the generated testbench as comments, one per domain, so "why is this domain not enabled?" is answered by reading the file.

## 5. Memory Preload

The firmware image reaches the boot memory by one of three roads, chosen per project with `testbench.preload_mode`.

**`readmemh` (the default)** is simulation-only: hierarchical `$readmemh` into the physical SRAM arrays, after that memory's reset releases. For interleaved memories the image is pre-split by `src/core/split_hex.py` into one hex file per group/bank pair (`<app>_g<G>_b<B>.hex`) according to the component's `Preload*` contract (`PreloadTemplate` names the per-bank path; `PreloadInterleave` selects the `lane-group` or `word-group` address mapping — a wrong value places the firmware in the wrong physical locations with no error). The run launches from `logs/`, where a `generated` symlink makes the relative hex paths resolve. Two facts worth knowing: this mechanism (together with its AXI monitors) is what keeps the preloaded memory's module out of Verilator's hierarchical blocks — the dotted paths cannot cross a block boundary — and it is release-ordered, not time-ordered: the `$readmemh` block waits on the memory's own reset, so it works regardless of how long bring-up takes.

**`jtag`** is the architected road (requires `boot_mode: jtag`): the testbench reads the *flat* hex into a local array and streams it through the debug module's System Bus Access (`vip_ollivander_soc.sba_load`, autoincrement, 64-bit beats where the hardware declares them, one sticky-error check per stream). No dotted path reaches the DUT: interleaving happens in the SoC's own decoder hardware, the identical sequence would work against silicon, and the preload target stays eligible as a Verilator hierarchical block — which is the reason this mode exists. One call is emitted per `preload_memories` entry, its base resolved by the generator from the component's `axi_slave` interface. The optional `testbench.preload_verify: true` re-reads the whole image through the same channel and compares word by word (`sbreadondata` streaming); it costs ~2.8x the plain load's simulated time (measured 2.2 ms against 0.8 ms on the 699-word mesh image), so the intended use is one verifying configuration in the regression fleet, not every project.

**`slink`** is the fast architected road (requires `boot_mode: jtag` and a host that builds and exports its serial link — `SerialLink: true` plus `"slink"` in `export_interfaces`, both validated at generation time): the VIP instantiates an off-chip twin of the host's own `serial_link` (same register package as the DUT side, so channel count, lane width and framing agree by construction; the twin's AXI geometry is resolved by the generator to the instance's true widths — one bit of id-width skew is enough to desynchronize the wire framing and hang the very first transaction) and drives the image as 1 KiB AXI write bursts through the DDR pins, at bus speed instead of DMI speed. In this mode the gated-domain bring-up and the boot handoff ride the serial link too (`slink_write32`): with the link built into the host, debug-module SBA writes into the host's internal register path complete with an OKAY but never land — an upstream anomaly under investigation — while the link's external AXI ingress reaches the same registers reliably. `preload_verify` is not available on this road.

**ELF images** (`image: elf` on a preload region, `jtag` and `slink` only): the testbench reads the file through the vendored cheshire `elfloader` DPI and streams every loadable segment through the configured road — the loaders never learn the source format. The entry point is taken from the ELF header at runtime and written to the handoff scratch registers in place of the generator's map-derived literal. Sections stage through a static buffer sized by `testbench.elf_max_section_bytes` (default 4 MiB; static because Verilator cannot yet pass dynamic arrays to DPI open arrays) — an oversized segment stops the run with a fatal that names the knob, before anything is streamed.

## 6. Monitors and the Transcript

Every message is tagged, and the tags are stable interfaces — the regression suite greps them:

| Tag | Source | Meaning |
| --- | --- | --- |
| `[UART]:` | VIP UART agent | a character/line the firmware printed; the primary test output |
| `[TB]` | testbench / VIP | lifecycle: start, reset, preload, boot steps, EOT |
| `[TB_AXI_MON]` | generated AXI monitors | request/acceptance/data on watched ports (e.g. the boot memory's read port); on `force` projects this monitor also drives the force release. **Emitted only under `preload_mode: readmemh`**: the monitors watch through dotted paths into the DUT, which the architected modes (`jtag`, `slink`) exist to eliminate — on those projects the same diagnostic duty is covered by the load-progress and handoff lines (`[VIP-JTAG]`/`[VIP-SLINK]`, `[TB] ... handoff complete`) |
| `[TB_TIME]` | testbench beacon | simulated-time heartbeat every 100 us |
| `[VIP]` | VIP internals | agent-level diagnostics (e.g. JTAG IDCODE mismatch) |

## 7. Pass Criterion

A run passes when **both** hold, and the suite (`make test-all`) checks exactly this on both simulators:

1.  the transcript contains `[UART]:` output (the firmware ran and spoke), and
2.  the transcript contains `[TB] EOT received. Simulation finished.` — the firmware's final byte was `0x04`, received over the real UART path.

The EOT byte is appended by the test application itself (it is the `\x04` at the end of its last message). A run that hangs instead hits the testbench watchdog, `$finish`es *without* the EOT line, and fails the criterion; the `[TB_TIME]` beacons and the last `[UART]:` line then localize where it stopped.

## 8. The Test Applications

Selected per run with `TEST_APP` (`make generate TEST_APP=hello_world`); the offload-capable examples default to `offload`.

*   **`hello_world`** — prints the greeting over UART and terminates with EOT. It exercises boot, the UART path, and whatever bring-up the boot needs — nothing else. Its target set for `bring_up: minimal` derivation is exactly the boot-critical set.
*   **`offload`** — a strict superset: the same greeting and EOT, plus, for **each** component that declares the `Offload*` contract, a full offload round driven by the host: (1) enable the payload memory's control group and load the payload — the payload travels *inside the host binary* as a generated C array (`payload_<target>.h`, produced by `bin2header.py` from the target-compiled ELF) and is copied by the host CPU, the silicon-representative route; (2) de-isolate and ungate the target's control group; (3) start the target's cores on the payload entry; (4) wait for end-of-computation, with a timeout that dumps the target's state registers on expiry; (5) verify the return code, print `[OFFLOAD] <target> PASS (...)`, and hand the group back to its power-on state so the next target starts from a clean slate. Under the architected boot (`boot_mode: jtag`), every group-gated target runs this whole phase **twice** — power-up, run, check, power-down, then again through a payload re-load — and prints `[OFFLOAD] <target> POWER-CYCLE PASS (2 cycles)`: the second pass is the regression of the domain re-entry path silicon depends on (the enable helpers honor the FFAR clocked reset window, and `disable()` returns the always-on `fetch_enable` to its power-on state precisely so a re-enabled cluster cannot restart from its reset-default boot address). Force-mode projects keep the single pass: their bench pins the power state by construction, and cycling against it would fight the forces. The final line, `[OFFLOAD] All targets passed.`, carries the EOT byte. Multi-instance targets (component arrays) run their instances in parallel and verify per-instance slots.

**How an offload pass is decided.** The payload runs a small generated workload (a checksum over a scratch buffer, XORed with a compile-time constant) and delivers the result over the channel its contract declares: the cluster's return-value register plus an EOC wire (`control_wire`), or per-core return slots in cluster-local memory - core 0 writes the checksum with a done bit, every other core a bare done. The **expected value is derived independently**: the generator computes the same checksum at generation time and bakes it into the host as a constant, so payload and host must agree through two separate derivations - a corrupted load, a wrong entry point or a bad window decode yields a mismatch, never a lucky pass (and the scratch buffer is pre-initialized precisely so a payload that never ran cannot leave a value mistaken for a result). Verification is strict: EOC/done within a timeout, core 0 of **every** instance equal to the expected value, and every secondary core of a memory_mapped cluster equal to one distinctive generator-owned code, exactly — a dead core is caught by the done poll, a wrong-path core by the code check, and the two print differently.

**A failed offload parks on purpose.** Any failing phase prints `[OFFLOAD] FAIL: <target> - <phase>`, dumps the phase's diagnostics first (on EOC timeout: `ret_reg`, `busy` and `eoc` as seen from the System Controller; on slot timeout: the full instances-by-cores slot matrix), and then spins forever **without ever sending EOT** - the testbench watchdog turns the park into an explicit regression failure instead of a false pass. In the transcript a failure therefore reads: the FAIL line with target and phase, the dump, then silence up to the watchdog `$finish`, and no EOT line - which is what the suite's criterion rejects.

The five phases make the firmware's power-management code — de-isolation, ungating, restoring — part of the regression, not decoration: with `bring_up: minimal`, if the firmware forgot a phase the target would simply not answer, and the run would fail on timeout rather than pass by accident.

## 9. Reading a Failure

Start from the last `[UART]:` line (how far the firmware got), then the last `[TB]` line (how far the boot got), then `[TB_TIME]` (whether time still advanced afterwards). On `readmemh` projects, `[TB_AXI_MON]` lines tell whether the host ever fetched from the boot memory — the divide between "boot never started" and "firmware died"; on architected-preload projects that same divide is read from the `[VIP-*]` load lines and the handoff line instead (absence of `[TB_AXI_MON]` there is by construction, not a symptom). Per-step suite logs and their locations are listed in the project README's debugging section; waveforms come from `make gui` (QuestaSim), since batch runs deliberately dump none.

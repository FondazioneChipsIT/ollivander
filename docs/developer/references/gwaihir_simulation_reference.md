# Gwaihir: Simulation Strategies — Reference Analysis

This document reconstructs how the **Gwaihir** project (ETH FlooNoC mesh SoC: Cheshire host tile, 4x4 Snitch cluster mesh, 8 L2 memory tiles) organizes its simulation and verification. It describes a READ-ONLY reference tree as surveyed on 2026-08-09 (`/data2/alessio.mangone/gwaihir_github/gwaihir`, HEAD `ae78edf`); nothing here is Ollivander behaviour. Companion of `astral_simulation_reference.md` in this directory - the two are deliberate opposites in several dimensions, and the closing section compares them.

---

## 1. The shape of the whole

Gwaihir's verification is a **minimal fork of Cheshire's**, extended only where the mesh demands it:

- **One 105-line testbench** (`target/sim/src/tb_gwaihir_top.sv`) - a direct fork of `tb_cheshire_soc` with the same plusargs and dispatch, plus a Snitch binary channel and the tile bring-up calls. One 142-line fixture instantiates the DUT at SoC level (not chip/pad level) plus the Cheshire VIP and a tristate adapter.
- **The Cheshire VIP is reused UNCHANGED** (`vip_cheshire_soc` from the dependency checkout): clock/reset master, JTAG debug agent, UART debug agent, serial-link mirror with AXI driver, I2C EEPROM and SPI flash models. Everything gwaihir-specific lives in one 273-line include of tasks (`tb_gwaihir_tasks.svh`).
- **Software is the test**, as in Astral, but with a single uniform offload model: one host launcher (`simple_offload.c`) serves every cluster test; the cluster binary is a plusarg.
- The fixture hardwires `clk_rst_bypass = 1'b0`: **tiles are really gated off out of reset in every simulation**, and enabling them through architected registers is a mandatory, exercised step - not a testbench cheat.

## 2. Testbench and VIP layer

### 2.1 Tile bring-up through real interfaces

The signature move: `jtag_enable_tiles()` / `slink_enable_tiles()` write four generated SoC-control registers (`gw_soc_regs` at `0x1800_3000`: cluster/mem-tile resets and clock enables) through the *debug module system bus* or *serial-link AXI* respectively - a reset pulse (assert-deassert-assert of the active-low mask) then clock ungating, for all 16 clusters (`0xFFFF`) and 8 memory tiles (`0xFF`), each write read back and `$fatal` on mismatch. The register addresses come from a PeakRDL-generated `gw_addrmap.svh`. This is the silicon-representative counterpart of the register *forces* Ollivander's generated testbench uses today, and the direct model for the JTAG agent of wip 2.1.

### 2.2 Load channels and the 32-bit subtlety

The inherited Cheshire tasks (`jtag_elf_preload/_run/_wait_for_eoc`, `slink_*`, `uart_debug_*`) are complemented by gwaihir-specific **32-bit variants** (`jtag_32b_elf_preload`, `slink_32b_elf_preload` over a misalignment-aware `slink_write_generic` doing read-modify-write of partial beats and 4 KiB-crossing splits): Snitch ELF sections are only 32-bit aligned and the 64-bit SBA path corrupts them. A lesson directly relevant to any generic preload agent: **the loader's access size is a property of the target, not of the channel**.

### 2.3 Fast mode: SRAM backdoor via virtual classes

`PRELMODE=3` preloads the Snitch binary straight into the L2 SRAM arrays. Because SystemVerilog cannot parameterize hierarchical paths, the task file registers one small class instance per `(mem_tile, bank, macro)` from inside the generate loops (each holding a `write_word`/`read_word` into `` `L2_SRAM_PATH ``), and the preloader indexes the class table from the address decomposition. The same hook dumps all of L2 to `l2mem.bin` at end of test for external verification. The `` `L2_SRAM_PATH `` macro is the override point the closed netlist flow uses.

### 2.4 End of test

Identical protocol chain to Astral's host domain, plus a cluster-side generalization:

1. Snitch cores: the gwaihir runtime port defines `SNRT_CRT0_ALTERNATE_EXIT` so **every core writes `(exit_code << 1) | 1` into its own slot** of a per-cluster return array; the array's address arrives in the cluster's `scratch[0]`, the entry point in `scratch[1]` (read by the PC-relative cluster bootrom on CLINT wake).
2. The host launcher polls all `16 x N` slots (array placed at `0x707F_F000`, explicitly "a region which is not cached"), sums the shifted codes and returns the sum.
3. Cheshire `crt0.S` `_exit` writes `SCRATCH[2] = (retval << 1) | 1`; the VIP polls it and prints `[JTAG|SLINK|UART] SUCCESS` or `$error("... FAILED: return code %0d")`.

The sum convention makes expected-failure tests exact: `non_null_exitcode.elf` returning 14 on 64 reporting cores yields exactly `896`, which CI matches literally.

## 3. Boot and preload modes

Plusargs: `+BOOTMODE` (default 0), `+PRELMODE` (**default 1**, serial link - upstream Cheshire defaults to 0), `+CHS_BINARY`, `+SN_BINARY`, `+IMAGE`. The TB also drops `.chsbinary`/`.rtlbinary` marker files consumed by the trace flow.

| PRELMODE | Tile bring-up | Snitch ELF | Cheshire ELF |
| :--- | :--- | :--- | :--- |
| 0 JTAG | JTAG | JTAG 32-bit SBA | JTAG |
| 1 serial link | serial link | slink 32-bit generic writer | slink (scratch launch) |
| 2 UART | JTAG | unsupported (`$fatal`) | UART debug protocol |
| 3 fast mode | JTAG | SRAM backdoor | JTAG (no fast path for the host SPM: `$fatal` if attempted) |

`BOOTMODE 2/3` = autonomous boot from the backdoor-loaded EEPROM/flash image, EOC over JTAG - and notably **without tile bring-up**, so booted software would have to enable tiles itself. No watchdog/timeout exists anywhere in the TB.

## 4. Software test suite

### 4.1 Families

- **Host tests** (6 C files, `sw/cheshire/tests/`): `sanity` (return 0), `sanity_fail` (return 7 - a first-class *expected failure* test), `helloworld` (the only UART producer), `access_l2` (packing-static-asserted walk of all banks of all 8 L2 tiles), `access_clk_gating_rst_ctrl_reg` (R/W of the tile-control registers the TB bring-up uses), `simple_offload` (the universal launcher).
- **Cluster tests** (13 in-tree + ~90 inherited upstream into the same build directory): SPM access via narrow port and wide DMA, mesh collectives (`mcast_barrier`, `multi_mcast`, `row_col_mcast` with row/column masks), `multicluster_atomics`, deadlock/stress barrier tests over mesh communicators, parameterized benchmarks (multicast/reduction/barrier with `IMPL=SW|TREE|HW` cdefines), and accelerator HAL tests (`redmule`, `redmule_quant`, `datamover`) against static golden headers.
- **Apps** (`sw/snitch/apps/`): mostly thin wrappers over upstream snitch kernels (`gemm`, `axpy`, `mha`, ...), plus mesh-aware `gemm_2d`/`summa_gemm` (staging tiles into the *nearest* L2 tile via `gw_closest_mem_tile()`) and `power_benchmarks` with ROI specs.
- **Experiments** (`experiments/`): Python sweep drivers over the snitch experiment framework (`multicast`, `reduction`, `barrier`, `summa_gemm`), each with analytical `model.py`, `fit.py` (linregress of alpha/beta), `plot.py`, `verify.py`, and Mako ROI templates. `--ci` collapses sweeps for the pipeline.

### 4.2 Toolchains and placement

Host: GCC `rv64gc_zifencei/lp64d` with LTO, linked in **one mode only** (`GW_LINK_MODE ?= spm` - the Cheshire SPM). Cluster: **LLVM `-mcpu=snitch`/ilp32d, compiled as C++** (the runtime port uses constexpr/overloads); everything links into `L3 @0x7000_0000` = the L2 SPM tiles, matching the entry pointer the launcher writes. The snRuntime *platform port* lives in gwaihir (`sw/snitch/runtime/impl/`: `snrt.h/.cc/.S`, `memory.ld`, start header with the alternate exit) with mesh topology helpers (`gw_team.h`: row/column indices, neighbours, closest mem tile) and mesh communicators (`gw_sync.h`) layered on top. Cluster `printf` is a stub (`_putchar` empty - TODO upstream).

### 4.3 Generated single sources

The address map is generated end to end: FlooNoC config (`cfg/gwaihir_noc.yml`) → `floogen rdl` → PeakRDL → `gw_addrmap.h` (C struct overlay used by host tests), `gw_raw_addrmap.h`, `gw_addrmap.svh` (used by the TB tasks). The cluster count in the snitch config is kept in sync with the FlooNoC config by a `sed` driven by `floogen query`. Host tests `static_assert` their hand-modelled memory structs against the generated types - packing errors die at compile time.

## 5. Simulation flow, scripts, metrics

### 5.1 Flow

- `bender script vsim --compilation-mode common` generated at build time (not checked in), plus the appended DPI elfloader compile. **No explicit `vopt` step**: GUI runs use `-voptargs=+acc`, batch runs rely on Questa auto-optimization. Message policy is a short hard-coded suppression list; nothing is escalated to error.
- The simulation runs **in the repo root** by default (`SIM_DIR = $(GW_ROOT)`, overridable per run - the experiment framework runs each point in its own directory against a shared compiled `work`).
- A make-level optimization worth noting: expensive dependency scans (`sn_include_deps`, which shells out to a Python make-target lister) are skipped for `vsim-%` and other listed goals.
- **QuestaSim only** ("currently only supports Questasim"); VCS/Verilator/GVSOC exist in the inherited dependency makefiles and the Python framework's simulator classes, but have no gwaihir backend. No FPGA target for the mesh (only plain Cheshire's, inherited). The netlist/power flow lives in a closed PD repo (`pd/`), reached through documented hooks (`` `L2_SRAM_PATH `` override, `NETLISTS=`, VCD windows, PrimeTime).

### 5.2 CI - fully observable, grep-adjudicated

Unlike Astral, the whole regression is in-tree (`.gitlab-ci.yml` + `.gitlab/sw-tests.yml`): stages init/build/run, a **22-entry parallel matrix** naming `CHS_BINARY`, `SN_BINARY`, `PRELMODE` and the expected outcome per row. The verdict logic is explicit shell over the transcript:

- pass = `grep "] SUCCESS"`;
- expected failure = `grep "] FAILED: return code ${NZ_EXIT_CODE}"` **and exactly one** `Error:` line;
- optional UART string match (`USTR`);
- any `Fatal:` fails; compile logs are checked with `! grep "** Error"`;
- data-heavy apps skip transcript checks entirely and run a Python `Verifier` (numpy `allclose`) against the fast-mode `l2mem.bin` dump.

UART preload is commented out of the matrix ("takes over 1h"). No nightly/schedule split, no job timeouts (the GitHub mirror action polls for at most 3 h). Lint on GitHub: Verible (fail-on-error) + format check + REUSE license lint. **No coverage of any kind** - same as Astral.

### 5.3 Trace and performance pipeline

The most developed part of the metrics story, inherited from snitch_cluster and extended to the host: cores dump `.dasm`/`.log` traces unconditionally; `gen_trace.py` produces per-hart text traces + per-hart/DMA perf JSONs; `annotate.py` (addr2line) produces source-annotated traces for both Snitch harts and CVA6 (binary names recovered from the `.chsbinary`/`.rtlbinary` files the TB wrote); `join.py` merges perf JSONs; `roi.py` applies Mako ROI specs (hart -> labelled regions); `visualize.py` emits Chrome-trace JSON. The experiment framework reads the ROI JSON (`SimResults.get_timespan(SimRegion(...))`) and converts to cycles for model fitting. This is a complete measurement stack Ollivander has no counterpart of.

## 6. What Ollivander should take (and has taken) from this

- **Taken already**: the memory_mapped boot contract (scratch entry pointer + CLINT wake + per-core `(code << 1) | 1` return slots in an uncached region) is exactly wip 2.2's second contract; the PC-relative cluster bootrom pattern justified the spatz bootrom patch; the tile bring-up over real interfaces is the declared model for the wip 2.1 JTAG agent.
- **For the VIP task (wip 2.1)**: the whole architecture is the minimal-delta model - reuse an existing VIP unchanged, add one task include for platform bring-up; the 32-bit preload variants argue for access-size as a target property in the agent interface; fast-mode's virtual-class SRAM backdoor is the clean solution to parameterized hierarchical paths (Ollivander's generated TB can generate the paths instead, but macros face the same problem).
- **For the suite**: the explicit in-tree test matrix with per-row expected outcomes (including exact nonzero exit codes and the "exactly one Error" idiom) is the discipline Ollivander's suite should evolve toward as the test population grows beyond one app per project.
- **To do better, deliberately**: propagate verdicts into exit codes (gwaihir also adjudicates by transcript grep); implement cluster-side printf (their `_putchar` stub silently swallows diagnostics); avoid hand-maintained duplicates of generated constants (their mesh dimensions carry a TODO - Ollivander's contract/one-hop-reference rule exists precisely against this).

## 7. Latent inconsistencies observed (as of this survey)

| Where | Observation |
| :--- | :--- |
| `tb_gwaihir_top.sv` | The default branch of the PRELMODE case prints `boot_mode` instead of `preload_mode` in its `$fatal` message |
| `.gitlab-ci.yml` | The `vsim-compile` job declares `extends:` twice; YAML keeps the second, silently dropping the dependency cache configuration (the same duplicate-key class Ollivander's strict loader now refuses) |
| `vsim.mk` | The elfloader compile omits the `-cpppath` Cheshire's own flow passes; `LOG_FILE` is declared in CI but the greps use the bare filename |
| fixture | `axi_llc_mst_req` is declared and passed to the VIP but never driven (gwaihir has no external DRAM); the VIP's DRAM model is unreachable |
| runtime | Cluster `_putchar` is an empty stub; `snrt_cluster_alias()` ignores the alias region; mesh dimensions are hand-maintained duplicates of the FlooNoC config |
| autonomous boot | `BOOTMODE>=2` performs no tile bring-up: booted software would find every cluster and L2 tile gated |

## 8. Astral vs Gwaihir - the two reference models side by side

| Dimension | Astral | Gwaihir |
| :--- | :--- | :--- |
| Testbench | 647-line TB + 1130-line fixture, pad-level DUT, 5 bespoke per-domain flows | 105-line TB + 142-line fixture, SoC-level DUT, 1 uniform flow |
| VIP strategy | 4 per-island VIPs aggregated (mux + ID remap into one serial link) | 1 VIP reused unchanged + 1 task include |
| Gated-block bring-up | TB writes PCRs over JTAG/serial link, per domain, ad hoc | TB writes 4 generated registers over JTAG/serial link, uniformly, read-back-checked |
| Offload contract | control-wire (per-core boot addr regs, fetch enable, EOC wire + return register) | memory-mapped (scratch entry pointer, CLINT wake, per-core return slots in uncached memory) |
| Boot media | I2C EEPROM, SPI flash, HyperRAM with SDF timing | EEPROM/flash inherited; L2 SRAM backdoor fast mode instead |
| Test population | 15 host tests x 4 link flavours + 4 island families from dependency repos | 6 host tests x 1 flavour + 13 mesh tests + upstream snitch tests + apps + experiment sweeps |
| Expected-failure tests | none (failures are ad hoc) | first-class (`sanity_fail`, exact-code matching, exactly-one-Error rule) |
| CI | closed (`nonfree` child pipeline), weekly tags | fully in-tree matrix with explicit grep criteria |
| Verdict mechanics | transcript `$error` only, no exit codes, no in-repo parsing (except litmus) | same transcript mechanics, but the grep adjudication is versioned in CI; Python verifiers for data apps |
| Metrics | none (no coverage, no perf pipeline; litmus golden-model compare) | no coverage, but a complete trace/perf/ROI/visualization stack + experiment fitting |
| Simulators | QuestaSim only (2 front-ends: vsim, qsim/Visualizer) | QuestaSim only (vsim; framework stubs for VCS/Verilator/GVSOC) |
| Reproducibility | `FORCE_SEED = date +%s` by default | deterministic (static golden headers, seeded datagen) |

For Ollivander the synthesis is: **Gwaihir's testbench economy and CI discipline, Astral's channel/media breadth** - which is precisely the split wip 2.1 (VIP stages) and wip 2.2 (contract kinds) already encode.

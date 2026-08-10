# Astral: Simulation Strategies — Reference Analysis

This document reconstructs how the **Astral** project (Carfield-derived SoC, Fondazione Chips-IT fork of the ETH/UniBo platform) organizes its simulation and verification: testbench architecture, boot/preload machinery, software test suite, scripts, CI and metrics. It describes a READ-ONLY reference tree as surveyed on 2026-08-09 (`/data2/alessio.mangone/astral_github/astral`, branch `scarv`, HEAD `2289626`); nothing here is Ollivander behaviour. Its purpose is to inform Ollivander's own work: the generic VIP (wip 2.1), the offload test family (wip 2.2) and multi-simulator compatibility (wip 8).

Companion of this file: the gwaihir observations recorded in wip 2/2.1 (testbench-driven tile bring-up over JTAG/serial link, plusarg-selected boot modes in a 105-line fixture). A dedicated gwaihir reference can join this directory when needed.

---

## 1. The shape of the whole

One testbench simulates the whole chip, and everything else is orchestration around it:

- **One top testbench** (`target/sim/src/astral_tb.sv`, `module tb_astral`, ~650 lines) with **five independent `initial` blocks, one per bootable domain** (Cheshire host, safety island, security island, PULP cluster, Spatz cluster), each guarded by the island-enable generate condition. A domain's block only acts if its `+<X>_BINARY` plusarg is non-empty, so one compiled testbench serves every single-domain and multi-domain scenario purely through run-time arguments.
- **One fixture** (`astral_fix.sv`, `module astral_fixture`, ~1100 lines) instantiating the DUT at pad level (`astral_wrap i_dut`, hence `fix.i_dut.i_dut.*` hierarchical references), all pad wires/pullups, and all VIPs. The testbench never touches the DUT directly - only fixture tasks and VIP tasks.
- **Per-domain VIPs** reused from each IP's own repository: `vip_cheshire_soc` (clock/reset master, JTAG, UART, serial link, SPI flash, I2C EEPROM, DRAM model), `vip_carfield_soc` (HyperRAM models, AXI aggregation into the serial link), `vip_safety_island_soc` (JTAG + AXI master), `vip_security_island_soc` (OpenTitan JTAG + UART + SPI flash).
- **Software is the test**: there is no scenario generator or scoreboard. A test is an ELF per domain; the testbench loads it through a selectable channel, starts the domain, and polls a completion register. All checking lives in the software and in the exit-code convention.

## 2. Testbench and VIP layer

### 2.1 Clock, reset, boot pins

`vip_cheshire_soc` is the single clock/reset source for the whole bench (the other VIPs' generators are left unconnected). The fixture parameterizes it with the FLL reference period (56.79 ns under `GF22_FLL`, 20 ns otherwise), a 1 MHz external clock, 100 ns JTAG clock, and scales the UART baud accordingly (`UartBaudRate = (10ns/ClkPeriodRef) * 115200`). An FLL-lock handshake task (`wait_fll_lock`) gates the boot sequences unless `+BYPASS_PLL=1`.

### 2.2 Load channels

Three independent JTAG agents (host, safety island, security island - the last with OpenTitan-specific debug packages), each exposing the same task family: `*_init` (IDCODE check against the config package), `*_elf_preload` (DPI-based ELF walk, SBA writes with auto-increment), `*_elf_run` (halt, write DPC, resume), `*_wait_for_eoc`. The host serial-link agent mirrors the DUT's `serial_link` in the VIP and drives it with an `axi_test` driver; island VIP AXI masters are aggregated (`axi_mux` + `axi_id_remap` in `vip_carfield_soc`) into the same serial link, which is how the safety island VIP reaches the SoC "from outside". A UART debug agent implements the Cheshire bootrom's passive-boot protocol (command bytes for read/write/exec, ACK/EOT framing).

### 2.3 Memory and peripheral models

HyperRAM (`s27ks0641` with SDF back-annotation, 2 PHYs x 2 chips, `$readmemh` backdoor), SPI NOR flash (`s25fs512s`, host and security island instances), I2C EEPROM (`24FC1025` x2), and optional `axi_sim_mem`/DRAMsys on the Cheshire LLC port (unused in Astral: LLC traffic goes to HyperRAM). Models are fetched at `sim-init` time (wget/git clone), not vendored.

### 2.4 End-of-test detection

Every wait task polls a completion register through a load channel (JTAG or serial link), then prints `SUCCESS` via `$display` or raises `$error("... FAILED: return code %0d")`. Structural violations (`IDCODE` mismatch, unsupported boot mode, ELF load failure) are `$fatal`. The host block additionally waits for the UART monitor to finish the in-flight byte before `$finish`.

## 3. Boot and preload modes

All run-time selectable via plusargs assembled by the make flow (`+CHS_BOOTMODE/+CHS_PRELMODE/+CHS_BINARY/+CHS_IMAGE`, and per island `+SAFED_*`, `+SECD_*` (+ its inner cluster binary), `+PULPD_*`, `+SPATZD_*`, plus `+BYPASS_PLL`, `+SECURE_BOOT`, `+CAR_PHY_SEL`, `+HYP_USER_PRELOAD`):

| Domain | BOOTMODE | PRELMODE | Path |
| :--- | :--- | :--- | :--- |
| any | 0 | 0 | JTAG preload + run + EOC poll |
| any | 0 | 1 | serial link preload (currently `$fatal`-ed out for the host: the padframe-config task it needs is disabled) |
| host | 0 | 2 | UART debug protocol (bootrom passive boot) |
| host | 0 | 3 | secure boot: OpenTitan boots CVA6, EOC still checked over JTAG |
| host | 1..3 | - | autonomous boot from media image (`+CHS_IMAGE` backdoor-loaded into both I2C EEPROM and SPI flash; SD (1) unsupported) |

The host bootmode values map 1:1 onto the Cheshire boot ROM's `switch (bootmode)`; passive boot spins on a scratch register that the serial-link/JTAG/UART agents write - the same "scratch + doorbell" protocol Ollivander's testbench forces emulate today with direct register forces.

Two per-domain sequences worth keeping in mind as offload references:

- **PULP cluster standalone**: the TB itself un-gates and de-isolates the domain through PCRs, preloads the cluster ELF, writes the 8 per-core boot-address registers, raises boot/fetch enable, polls the EOC PCR, then reads the return register from cluster memory. This is the sequence Ollivander's `control_wire` offload contract generates *in firmware* instead.
- **HyperRAM time-0 preload**: `+HYP_USER_PRELOAD=1` with `.slm` images baked in at *compile* time (`+define+HYP0/1_PRELOAD_MEM_FILE`); the docs explicitly warn it "may hide bugs in the physical interfaces" - the same honesty Ollivander applies to `$readmemh` vs the future JTAG preload path.

## 4. Software test suite

### 4.1 Families

| Family | Domain | Sources | Toolchain |
| :--- | :--- | :--- | :--- |
| `hostd` | Cheshire/CVA6 | in-tree, 15 C files | riscv64 gcc, `rv64gc_zifencei/lp64d`, LTO |
| `safed` | safety island | dependency repo (pulp-runtime apps) | pulp-gcc rv32 |
| `pulpd` | PULP cluster | dependency repo `regression_tests` | pulp-gcc 1.0.16 rv32 |
| `secd` | OpenTitan + its inner cluster | dependency repo | `rv32imc_zicsr/ilp32` |
| `spatzd` | Spatz cluster | NOT integrated (dangling symlink, build commented out) | - |
| `linux` | host under Linux (FPGA) | in-tree | buildroot gcc |

`hostd` covers: smoke (`minimal`, `helloworld`), infrastructure registers (`clock_divider`, `irq_router_rw`, `system_timer_test`, `sw_rst_seq`), analog/clocking (`fll_basic` - explicitly "no automatic checking"), memory stress (`addressability_test`: LFSR write/read sweeps over HyperRAM with PHY selection), platform features (`mbox_test` with PLIC handler, `snooper_test`/`snooper_stress_test` for the trace unit), and the **offloaders** (`pulpd_offloader_blocking`, `pulp-offload-intf` - the latter adds host-side cache interference while the cluster runs). Two sources are fully commented out but still compiled (`idma.c`, `cache_partitioning_basic.c`).

### 4.2 Build machinery

- Every hostd test is linked in **four flavours** against different linker scripts (`*.car.l2.elf`, `.spm`, `.dram`, `.rom`), one make pattern rule per script found in the link directories. The L2 script places text at `0x78000000` with the stack at the top of the 128 KB region.
- **Payload embedding** (`offload_tests_template` in `sw/sw.mk`): for each island test, `scripts/elf2header.py` (pyelftools) converts the island ELF into a `payload.h` (one volatile store per word + `#define ELF_BOOT_ADDR` + `load_binary()`), which is temporarily copied next to the offloader source and compiled into a host ELF per island test: `pulpd_offloader_blocking.<test>.car.l2.elf`. Ollivander's `bin2header.py` is the same idea reduced to stdlib + objcopy.
- **HyperRAM images**: `scripts/elf2slm.py` splits an ELF into two 16-bit-interleaved `.slm` files (one per physical chip), consumed by the HyperRAM model's `$readmemh`.
- Register headers are regenerated from HJSON via OpenTitan `reggen` (`regtool.py`), the same single-source philosophy Ollivander gets from PeakRDL.
- The runtime is header-heavy: `car_util.h` provides clock/reset/isolation helpers (X-macro generated register offsets), the IRQ-router API, and the offload helper families (`pulp_cluster_*`, `safed_*`); `libcheshire.a` provides UART/CLINT DIFs and the embedded `printf`. (`libcarfield.a` exists in the build system but is an empty archive - see 8.)

### 4.3 Pass/fail conventions

- **Host**: `crt0.S` `_exit` writes `SCRATCH[2] = (retval << 1) | 1` - bit 0 done, bits [31:1] code. `main` returning 0 is the only pass.
- **Safety island**: `CORESTATUS` register, bit 31 done, bits [30:0] code.
- **PULP cluster**: EOC PCR bit 0 + a separate cluster-memory return register.
- **Spatz**: peripheral EOC register with the same `(code << 1) | 1` shift.
- **Security island**: RISC-V `tohost` word at a fixed address, polled over JTAG; pass is exactly `1`.
- Semantic error codes (`EHOSTDEXEC=1` ... `EPERIPHNOACCES=10`) partition failures by domain and by execute-vs-access.
- UART is for diagnostics, not verdicts: a free-running monitor line-buffers into `[UART] <line>` transcript prints; tests use `printf` with conventional `[ERROR]`-style markers.

## 5. Simulation flow, scripts, metrics

### 5.1 Flow

- Compile scripts are **generated on every invocation** (`.PHONY` target): `bender script vsim <targets/defines> --vlog-arg="<runtime defines>" --compilation-mode separate`, then an appended `vlog elfloader.cpp` (DPI) and the `vopt`/`qopt` line. `--compilation-mode separate` wraps each IP's `vlog` in `if {[catch ...]} {return 1}`, and the build target runs the script under `quit -code [source ...]` - so **compile failures propagate as exit codes, run failures do not** (the run's do-string is `run -all; exit` without `-code`; verdicts require transcript parsing).
- Two Questa front-ends are maintained in parallel: classic `vsim`/`vopt` and `qsim`/`qopt` with the Visualizer wave database. `DEBUG` unset = batch + `-O5 +acc=p+tb.` (ports-only visibility); `DEBUG=1` = GUI + full `+acc` + `log -r /*`; qsim adds a `DEBUG=live` interactive-wave mode.
- Message policy: `-permissive -suppress 3009 -suppress 8386 -error 7 +nospecify -sdfnoerror -suppress 1565 -suppress 13271` - the last four self-described in a comment as a workaround "to enable simulations with Thales IP". Compare Ollivander's per-message documented suppression table in the generated Makefile.sim.
- Compile-time defines include the icache family Ollivander re-discovered the hard way (`FEATURE_ICACHE_STAT`, `PRIVATE_ICACHE`, **`HIERARCHY_ICACHE_32BIT`**, `ICAHE_USE_FF` (sic), `CLUSTER_ALIAS`, `SNITCH_ICACHE`) - declared globally in `bender-common.mk`, which is exactly the integrator-obligation model that motivated Ollivander's per-component `// DEFINE:` pragma instead.
- Gate-level: `TECH_SIM=1` adds `-t tech_sim -t asic -t gf22` and technology sources; the TB has `CHS_NETLIST`/`ASTRAL_TOP_NETLIST` guards replacing hierarchical waits with plain delays. Offload tests are positioned in the docs as the vehicle for dynamic timing analysis on the netlist.
- Only QuestaSim is supported ("we plan on supporting more simulators in the future"); the inherited Cheshire VCS flow is reachable but not wired for the top level. Verilator appears solely as a filelist generator for Spyglass lint.

### 5.2 CI and metrics

- The public GitHub side runs **no simulation**: a mirror job forwards to GitLab and polls the result (up to ~12 h), plus license-header lint, Verible lint (`paths: hw`, waiver file, fail-on-error) and a docs deploy.
- The authoritative CI (job matrix, test lists, timeouts, nightly-vs-push behaviour) lives in a **closed `nonfree` repository** cloned at pipeline start and injected as a child pipeline + makefile include; it is not observable from the open tree. Weekly tags (`weekly_YYYYMMDD`) mark the regression cadence.
- **No coverage of any kind** (no covergroups, no `-coverage`, no UCDB machinery) anywhere in the open tree; UVM is linked but used only for a regex helper.
- The single in-repo report pipeline is the **litmus flow**: each CHERI-Litmus ELF runs through the standard sim target, `[UART]` lines are sed-scraped into per-test logs, concatenated, and compared against the herd7 golden model; the verdict is `grep`-based ("negative differences" fail the target).

## 6. FPGA complement

Vivado targets for VCU128 in two flavours (`vanilla`, block-design), with elaboration-only and check-timing knobs shaped for CI use; Linux boot via a 16 MB GPT image (ZSL/DTB/firmware/uImage/rootfs) built in the SW tree and flashed via a TCL script; Linux userspace tests `mmap` the SoC windows through a platform driver. The docs recommend OpenMP offload on FPGA/ASIC as the successor of bare-metal offload regressions.

## 7. What Ollivander should take (and has taken) from this

- **Taken already**: the offload boot sequences and their hazards (fence.i after payload load; per-core boot addresses; EOC+return separation) fed wip 2.2 phase 1; the `HIERARCHY_ICACHE_32BIT` obligation became a component-declared `// DEFINE:` pragma instead of a global makefile define; `elf2header` became the leaner `bin2header`.
- **For the VIP task (wip 2.1)**: the one-fixture/plusarg-selected-boot-mode architecture is the model (as is gwaihir's smaller variant); the UART debug protocol and the serial-link mirror show what a "load channel" agent needs to expose (`*_elf_preload/_run/_wait_for_eoc` as the uniform task family). The VIP-side aggregation of island masters into one serial link is a clean pattern for multi-agent benches.
- **To do better, deliberately**: propagate the run verdict into the simulator exit code (Astral greps transcripts outside the repo; Ollivander's suite greps too, but owns the criterion in-tree and can graduate to `$fatal`-on-fail or `quit -code`); keep test lists explicit rather than implicit in dependency checkouts; keep seeds reproducible by default (Astral's `FORCE_SEED` defaults to `date +%s`); and if coverage ever matters, neither reference provides a model to copy.

## 8. Latent inconsistencies observed (as of this survey)

Recorded because they are instructive about long-lived verification trees; none of them affects Ollivander directly.

| Where | Observation |
| :--- | :--- |
| `astral_tb.sv` | Host serial-link preload (`CHS_PRELMODE=1`) is `$fatal`-ed out while the docs still present it as the canonical flow; the padframe-config tasks it depends on are commented out |
| `astral_tb.sv` / `bender-safed.mk` | The TB guards a call on `` `ifdef SAFED_PRESENT `` but the build only ever defines `SAFED_ENABLE` (`SAFED_PRESENT` is a shell variable) - the guarded call is never compiled |
| `bender-sim.mk` / `astral_fix.sv` | The tech define is emitted as `GF22_FFL` while the fixture tests `GF22_FLL`, so the FLL reference period silently stays at the 20 ns dummy value |
| `vip_carfield_soc.sv` | `HypUserPreloadMemFiles[i]` indexes a byte of a string localparam, so the second PHY's preload file is effectively unused |
| `sw/sw.mk` | `safed_offloader_blocking.c` is referenced but absent from the tree; `$(CHS_LD_DIR)` is undefined (real name `CHS_SW_LD_DIR`), so one link rule expands to `-T/dram.ld`; `libcarfield.a` is an empty archive |
| `qsim.mk` | The post-simulation Visualizer command points at the `vsim/` twin's wave database; `car-qsim-sim-init` lacks the checkout prerequisite its `vsim` twin has |
| run targets | `exit` without `-code`: a failing test does not fail the shell; `FORCE_SEED` defaults to the current epoch, so binaries are not reproducible unless overridden |

# Ollivander Example Projects

The nine projects in this directory serve two purposes: they showcase every usage scenario a downstream project may need, and they are the regression fleet the developers validate every change against (`make test-all`, see the repository root). Each project is the same three-line `Makefile` pattern an external project is expected to follow — `OLLIVANDER_ROOT`, `SOC_YAML`, `ENV_YAML`, `OUT_DIR`, include `ollivander.mk` — and the commands (`make generate`, `fast-check`, `build-sim`, `run-sim`, and the Verilator twins) are documented in the [getting started guide](../docs/getting_started.md).

## Which example to start from

| project | top module | topology | boot | image preload | padframe | what it uniquely witnesses |
| --- | --- | --- | --- | --- | --- | --- |
| [`crossbar`](crossbar/) | `crux` | AXI crossbar (inspired by **Astral**) | `jtag` | `jtag` (SBA) | **yes** — all three padlist formats | the complete chip: padframe, chip wrapper, gated power-on with testbench bring-up |
| [`crossbar_isle`](crossbar_isle/) | `crux_isle` | AXI crossbar, **macro** build | `force` | `readmemh` | no | the crossbar macro export, and the legacy force+readmemh path |
| [`crossbar_micro`](crossbar_micro/) | `crux_micro` | AXI crossbar, minimal | `spi_flash` | none — the image lives in the flash | no | the **autonomous boot** class: GPT disk image, bootrom-driven load, no JTAG at all |
| [`crossbar_mini`](crossbar_mini/) | `crux_mini` | AXI crossbar, minimal | `uart` | `uart` | no | the smallest configuration that boots — read its YAML first |
| [`noc`](noc/) | `mesh` | 2D-mesh NoC (inspired by **Gwaihir**) | `jtag` | `jtag` (SBA) | no | Gwaihir's exact address map; boot from the always-on scratchpad; per-instance power control |
| [`noc_isle`](noc_isle/) | `mesh_isle` | 2D-mesh NoC, **macro** build | `jtag` | `slink` | no | the NoC macro export, and the gated-L2 boot the testbench must bring up |
| [`noc_subtile`](noc_subtile/) | `mesh_subtile` | 2D-mesh NoC, **subtile macro** | `force` | `readmemh` | no | the subtile export (dual-network AXI ports), on the force path |
| [`super_crossbar`](super_crossbar/) | `super_crux` | crossbar parent nesting the **`mesh_isle`** macro | `jtag` | `slink` | yes — Python padlist | cross-topology nesting: a NoC SoC compiled inside a crossbar parent |
| [`super_noc`](super_noc/) | `super_mesh` | NoC parent nesting **`crux_isle`** and **`mesh_subtile`** | `slink` | `slink` | no | cross-topology nesting the other way, package coexistence, deepest gated boot |

Two facts about the fleet's shape are deliberate and must not be "unified":

* **Boot memory is distributed on purpose.** `noc` and `noc_subtile` boot from the always-on narrow scratchpad (the SoC starts on its own, as silicon would); `noc_isle` and `super_noc` keep the boot image in a gated L2 tile and depend on the generated testbench to bring that tile up. Both power-on paths stay covered this way.
* **The two super examples cross the topologies.** `super_crossbar` nests the Mesh macro, `super_noc` nests the Crux macro, so each resolves and simulates the external IPs of **both** families in one Bender graph — the standing regression test of the dependency catalogue in `ollivander_config.yml`.

## The projects, one by one

### `crossbar` — crux, the complete chip

Inspired by the **Astral** chip: a Cheshire host, PULP and Spatz clusters, L2 SRAM, HyperBus, and industrial peripherals (Ethernet, CAN, UART) on a central AXI4 crossbar. The System Controller defaults to `power_on_state: "gated"`, and the boot memory sits in a managed domain, so the generated testbench performs the bring-up that real silicon would delegate to an external agent — Ollivander warns about this at generation time.

It is also the demonstrator of the **three equivalent padlist formats**: a flat CSV (`crux_pads.csv`), a procedural Python script (`crux_pads.py`), and native YAML lists split per voltage domain (`crux_pad_list_1v8.yml`, `crux_pad_list_3v3.yml`). The active format is selected in [crux.yml](crossbar/crux.yml) under `padframe` (`pad_csv`, `pad_py`, or `domains.pad_list`).

### `crossbar_isle` — crux_isle, the crossbar macro

The same SoC as `crux`, exported as a standalone hard macro (`build_mode: "macro"`) for integration into a larger design: no padframe, no chip wrapper. Every generated name carries the `crux_isle` prefix — derived from the top-level module, never from the bare project name — which is what lets this macro coexist with other builds in one simulation library, as `super_crux` requires.

### `crossbar_micro` — crux_micro, the autonomous product

A single-core Cheshire host and one ECC L2 SRAM, with `SpiHost` on (the bootrom boots from CS1) and the **JTAG export deliberately gone**: an autonomous product needs no debugger. `boot_mode: "spi_flash"` — the testbench instantiates the behavioral flash model preloaded with a **GPT disk image** built by the generated software flow, and the bootrom does everything a finished product would: GPT scan, load into the internal scratchpad, jump. No preload, no agent; the bench just waits for the end-of-test byte. The `i2c_eeprom` twin road is pilot-validated and will join as a named simulation once per-project simulation lists land.

The L2 lives at `0x7800_0000`, inside the host's CIE window — Astral's own shape, and the fleet's regression witness for the cached+executable external-memory practice. Autonomous simulation is QuestaSim-only: the vendor flash model's dynamic delays verilate to `#0`.

### `crossbar_mini` — crux_mini, the minimum that boots

A single-core Cheshire host and one ECC L2 SRAM; every optional host feature off, no padframe. **Read [crux_mini.yml](crossbar_mini/crux_mini.yml) top to bottom before the larger examples**: every block in it is the minimum a real project needs. `boot_mode: "uart"` boots through the bootrom's own serial debug server — the poorest external agent silicon can count on — at the 115200 baudrate baked into the ROM. Its job in the fleet is regression of the near-empty configuration space, which surfaced defects the seven larger projects could never hit.

### `noc` — mesh, the Gwaihir clone

A 2D-mesh NoC of compute, memory and peripheral tiles routed by **FlooNoC**. The address map mirrors the Gwaihir reference exactly (clusters at `0x2000_0000`, scratchpads at `0x6000_0000`, L2 tiles at `0x7000_0000`, DRAM at `0x8000_0000`), including the alternating 1 MB / 512 KB L2 depths on a uniform stride, expressed through per-instance `base_addr` lists. The firmware boots from the always-on narrow scratchpad, unaided; L2 tiles and clusters stay gated until software enables them — including per-instance clock, reset and AXI isolation, which the generated `offload` application exercises tile by tile. Its preload geometry (64-bit AXI word on 64-bit banks: one group of 16 banks) is a degenerate case no other example covers.

### `noc_isle` — mesh_isle, the NoC macro

The Mesh SoC exported as a macro (`build_mode: "macro"`, `mesh_isle` prefix on every generated name). Its firmware is deliberately placed in a **gated L2 tile**: the host cannot fetch until the testbench enables that tile, keeping the gated boot path and the 4-group × 128-bit interleaved preload covered by the regression.

### `noc_subtile` — mesh_subtile, the subtile macro

The Mesh SoC exported as a **subtile** macro: the variant whose dual AXI ports plug straight into both of a parent's networks (see the [subtile contract](../docs/hw/component_standardization.md)). Boots from the always-on scratchpad like `mesh`, on the force path.

### `super_crossbar` — super_crux, the crossbar parent

Identical to `crux`, plus the pre-generated **`mesh_isle`** macro as a nested subsystem. **Generate `noc_isle` first**: the parent consumes the macro's generated tree rather than regenerating it. The padframe is defined procedurally ([super_crux_pads.py](super_crossbar/super_crux_pads.py)), and the whole SoC description is Python ([super_crux.py](super_crossbar/super_crux.py)) — the fleet's demonstrator of the Python input format.

### `super_noc` — super_mesh, the NoC parent

A NoC parent nesting **two** macros: `crux_isle` (joined through a narrow/wide adapter) and `mesh_subtile` (dual ports straight into both networks). **Generate `crossbar_isle` and `noc_subtile` first.** It also proves the naming rules: `super_mesh` and `mesh_subtile` both stem from "mesh", yet their packages coexist in one library because every name derives from the top-level module. A **single** `mesh_subtile` instance is instantiated — each one is a complete SoC (Cheshire host, 16 Snitch clusters, 8 L2 tiles), and an array exceeded what the simulator could map; dummy tiles (pure FlooNoC routers) keep the grid rectangular. The boot image lives in one of the parent's own gated L2 tiles: the deepest testbench bring-up of the set.

## Environment and reproducibility

Each project's `<name>_env.yml` declares nothing beyond the project's own paths. The external IP revisions and the forced resolutions that make the build reproducible are the **dependency catalogue** shipped in `ollivander_config.yml`, shared by every example; a project may override an entry, and the override replaces the catalogue's entirely (see the [environment guide](../docs/env_configuration_guide.md)). `Bender.yml`, `Bender.lock` and `Bender.local` are local build state: never copy them between machines or working copies.

## Collective witnesses (decided 2026-09-02)

Each collective mechanism the generator supports has exactly one example that exercises it, so that a regression names its mechanism instead of hiding behind another project's coverage. The distribution is deliberate; do not merge the profiles back into one project.

| example | reduction channel | collective phases exercised | mechanism |
| --- | --- | --- | --- |
| `noc` | wide (FP) | FpAdd wide (two dimension-ordered phases), multicast, barrier | the gwaihir-like profile: DMA-issued, `dmuser` sets `{mask, op}`, routers offload to the cores' FPUs through the DCA |
| `noc_isle` | narrow (integer) | IntAdd two-phase, multicast, barrier | the stamper: address windows stamp op and mask on core stores |
| `noc_subtile` | none | multicast, barrier | the collectives that need no reduction channel; also the macro `super_crossbar` nests |
| `super_noc` | wide (FP) | as `noc`, inside a macro consumer | the DCA path across a nested boundary |

The barrier and the multicast are network capabilities always present in the emission and follow the component's contract slots, so every project with `cluster_subtile` carries them; the reduction channels are what the SoC description distributes.

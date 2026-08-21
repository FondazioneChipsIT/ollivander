# Ollivander Documentation

Every guide in this tree, organized by what you are trying to do. The three sections match the three roles the documentation serves: using the generator, feeding it hardware, and developing it.

---

## I use Ollivander to build an SoC

Read in this order:

| Guide | What it covers |
| :--- | :--- |
| [Getting Started](getting_started.md) | Integrating Ollivander as a submodule, the project Makefile, the environment bridge file, build modes, generation and simulation |
| [SoC Configuration Guide](soc_configuration_guide.md) | **The authoritative reference** for the SoC description (YAML or Python): every accepted block and field, and — in section 6 — what each kind of mistake reports |
| [Environment Configuration Guide](env_configuration_guide.md) | Paths, the centralized dependency registry, patches and pre-build commands, forced resolutions (`overrides`) and their escape hatches |
| [Padframe Configuration Guide](padframe_configuration_guide.md) | Physical I/O ring and pinmux via Padrick: CSV, Python, or native YAML pad lists, technology catalogs, power domains |

The seven projects under [`soc_cfg_examples/`](../soc_cfg_examples/) are working references for everything above — each has a README stating what it demonstrates, and together they form the generator's own regression suite.

---

## I am wrapping a hardware IP for Ollivander

A component enters the generator through a standardized SystemVerilog wrapper. Which standard applies depends on how the IP meets the interconnect:

| Guide | Wrapper kind |
| :--- | :--- |
| [Testbench Guide](testbench_guide.md) | The generated verification environment: testbench anatomy, VIP agents, boot sequences per mode, preload mechanics, monitors, pass criterion, and what the test applications execute. |
| [Component Standardization](hw/component_standardization.md) | The single contract for `*_isle.sv`, `*_subtile.sv` and `*_tile.sv`: one common part, then the particularities of each level. Start here to wrap an IP. |
| [Clocking, Reset & CDC Requirements](hw/clocking_reset_cdc_requirements.md) | The clock/reset interface every wrapper must honour, and where the CDC boundaries sit |
| [APB Subsystem Isle](hw/apb_subsystem_isle.md) | The one dynamically *generated* isle: how the peripheral subsystem is assembled and which IPs it knows |

---

## I am developing Ollivander itself

| Resource | What it covers |
| :--- | :--- |
| [SystemVerilog Intermediate Representation](developer/intermediate_representation.md) | The SV-IR data model, its construction flow, and the static verification engine that runs before rendering |
| [Future Evolution Tasks](developer/wip/future_evolution_tasks.md) | Planned work and open decisions — read it **before** proposing an architectural change: the work may already be planned there, with its trade-offs discussed |
| [Astral Simulation Reference](developer/references/astral_simulation_reference.md) | How the Astral reference project simulates and verifies — testbench/VIP architecture, boot modes, test suite, scripts, CI. `developer/references/` hosts these analyses of the read-only reference trees |
| [Gwaihir Simulation Reference](developer/references/gwaihir_simulation_reference.md) | The same analysis for the Gwaihir mesh SoC, closing with a side-by-side comparison of the two reference verification models |

The `developer/wip/` directory contains only work in progress or not yet started: how Ollivander *currently* behaves is documented in the guides above, never there.

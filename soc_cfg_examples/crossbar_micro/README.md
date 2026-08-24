# Crux Micro - the Autonomous-Boot SoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration of **Crux Micro**, the fleet's autonomous-boot witness: crux_mini minus the debugger. A bare Cheshire host, one L2 memory, a UART for the console and an SPI port for the boot flash — and nothing driving the chip at all.

## 1. Project Overview
* **Architecture**: a single-core Cheshire host and one ECC L2 SRAM on a central **AXI4 crossbar**, same shape as [crux_mini](../crossbar_mini/). The differences are exactly the autonomous-boot ones: `SpiHost` is on (two chip selects — the bootrom boots from CS1), and the **JTAG export is gone**: an autonomous product needs no debugger, and dropping it is the point of this project.
* **Boot road**: `boot_mode: "spi_flash"` — the strap selects the SPI-NOR source, the generated testbench instantiates the behavioral flash model named by the host contract, preloaded with a **GPT disk image** the generated software flow builds (upstream's own `truncate` + `sgdisk` + `dd` recipe), and the bootrom does everything a finished product would: GPT scan, load of the ZSL-type partition into the host's internal scratchpad, jump. No preload, no agent sequence; the bench just waits for the end-of-test byte. Measured: end-of-test at **4.86 ms simulated (~1 wall-clock minute)** under QuestaSim.
* **Reference-coherent memory map**: the L2 lives at `0x7800_0000`, inside the host's CIE window `[0x7800_0000, 0x8000_0000)` (`Cva6ExtCieOnTop` — astral's own shape), the designed way to make external memory cached+executable for CVA6, instead of being parked inside the `LlcOutRegion` where it would shadow cheshire's DRAM decode rule.
* **No padframe, on purpose** — same rationale as crux_mini.

## 2. Why this project exists
* **The autonomous boot class**: force, jtag, slink and uart all model *someone* driving the chip; this project models the chip on a bench with only a flash soldered next to it — the one boot class the rest of the fleet cannot witness.
* **The i2c_eeprom twin road**: the second autonomous source (`boot_mode: "i2c_eeprom"`, a one-line flip plus `I2c: true` and the `i2c` export) shares the same GPT image and strap mechanism; it is pilot-validated (24 ms simulated) and will join this project as a named simulation once per-project simulation lists land.
* **Witness of the coherent map**: with its L2 below `0x8000_0000`, it regression-tests the crossbar family's CIE-window practice.

## 3. Declared limitation: the simulation leg is QuestaSim-only
The vendor flash model **compiles** under Verilator (its `specify` blocks are ignored with a warning, as expected), but its functional timing machinery is built on dynamically-valued `#` delays that Verilator approximates as `#0` (`ZERODLY`), and the device stays mute on the bus: the boot never starts. Upstream has no Verilator precedent for these models either — its own Verilator lane never exercises the flash boot. The test suite therefore runs this project's *simulation* under QuestaSim only (`SIM_TOOLS_crossbar_micro="questa"`, printed in the suite's summary header); `fast-check` still runs under **both** tools, since it elaborates stubs and never touches the device model.

## 4. Environment & Reproducibility
* The environment configuration file [crux_micro_env.yml](crux_micro_env.yml) declares nothing beyond the project's own paths: the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

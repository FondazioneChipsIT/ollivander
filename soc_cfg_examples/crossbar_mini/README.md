# Crux Mini - the Minimal SoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration of **Crux Mini**, the smallest SoC of the example fleet and the recommended starting point for a new Ollivander project: a bare Cheshire host, one L2 memory, a UART and a JTAG port — nothing else.

## 1. Project Overview
* **Architecture**: a single-core Cheshire host and one ECC L2 SRAM on a central **AXI4 crossbar**. Every optional host feature (DMA, serial link, VGA, SPI, I2C) is off: this is the minimum that boots.
* **No padframe, on purpose**: the `padframe` block is optional, and this project omits it — the generator skips Padrick and the chip wrapper entirely and the flow stops at the SoC top, which is also all the testbench simulates. A real chip adds the block back (see the [padframe guide](../../docs/padframe_configuration_guide.md)).
* **Boot road**: `boot_mode: "uart"` — the testbench boots the SoC through the **bootrom's own serial debug server** (ACK challenge, block writes of the image, EXEC jump), the poorest external agent silicon can count on. The protocol runs at the baudrate baked into the ROM (115200), which is why this project keeps `software_stack.baudrate` at 115200 too and why the uart road lives on the fleet's smallest SoC: the upload is pure simulated time (~4 wall-clock minutes here under QuestaSim).

## 2. Why this project exists
* **Getting started**: every block in [crux_mini.yml](crux_mini.yml) is the minimum a real project needs, with none of the optional machinery — read it top to bottom before the larger examples.
* **Regression of the near-empty configuration space**: no clusters, no gated domains, no control groups, no padframe. Its first three generations surfaced five latent generator defects the seven larger projects could never hit — that is its job.
* **Fast vehicle**: light enough that slow boot transports and future host-level experiments stay affordable in the per-commit suite.

## 3. Environment & Reproducibility
* The environment configuration file [crux_mini_env.yml](crux_mini_env.yml) declares nothing beyond the project's own paths: the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

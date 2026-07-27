# Mesh Isle NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files for **Mesh Isle**, a modular variant of the Mesh SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Mesh Isle is functionally analogous to the standard Mesh SoC, utilizing a 2D Mesh Network-on-Chip (NoC) interconnect topology.
* **Isle Export (Macro Build)**: Unlike the top-level Mesh project, this configuration is exported as a modular subsystem macro (an "Isle") with `build_mode: "macro"`.
* **Export Verification**: The primary purpose of Mesh Isle is to test and verify the macro export flow specifically for SoC architectures built around a Network-on-Chip (NoC) topology.
* **Boot Memory**: Unlike the top-level Mesh project, the firmware is deliberately placed in an L2 tile, which belongs to the `mem_tile_ctrl` auto control group and is therefore clock-gated and held in reset at power-on. The host cannot fetch its boot image until something external enables that tile, so Ollivander emits a warning at generation time and the generated testbench performs the bring-up. This keeps the gated boot path, along with the 4-group by 128-bit interleaved preload, covered by the regression.
* **Name Suffixing**: Because this is a `macro` build, the top-level module, the SoC and FlooNoC packages, the Bender package and every generated module carry the `mesh_isle` prefix rather than the bare project name. That is what allows this macro and its `subtile` sibling to be compiled into a single simulation library by a parent SoC.

## 2. No Padframe Configuration
* Because Mesh Isle is compiled as a modular IP block/macro rather than a complete chip-level wrapper, **there is no padframe or pinmux generation**.
* The physical I/O ring and package-level pin multiplexing are omitted from this configuration, as these are typically managed by the parent SoC.

## 3. Environment & Reproducibility
* The environment configuration file [mesh_isle_env.yml](mesh_isle_env.yml) defines the local settings for compiling and checking Mesh Isle.
* It includes a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This ensures a 100% reproducible build without requiring manual conflict resolution.

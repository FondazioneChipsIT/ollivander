# Mesh Subtile NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files for **Mesh Subtile**, a modular variant of the Mesh SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Mesh Subtile is functionally analogous to the standard Mesh SoC, utilizing a 2D Mesh Network-on-Chip (NoC) interconnect topology.
* **Subtile Export (Macro Build)**: Unlike the top-level Mesh project, this configuration is exported as a modular "subtile" macro with `build_mode: "macro"`.
* **Export Verification**: The primary purpose of Mesh Subtile is to test and verify the subtile macro export flow specifically for SoC architectures built around a Network-on-Chip (NoC) topology.
* **Boot Memory**: As in the top-level Mesh project, the firmware is placed in the always-on `top_spm_narrow` scratchpad, so the design boots without depending on any bring-up sequence.
* **Name Suffixing**: Because this is a `macro` build, the top-level module, the SoC and FlooNoC packages, the Bender package and every generated module carry the `mesh_subtile` prefix rather than the bare project name. That is what allows this macro and its `isle` sibling to be compiled into a single simulation library by a parent SoC.

## 2. No Padframe Configuration
* Because Mesh Subtile is compiled as a modular IP block/macro rather than a complete chip-level wrapper, **there is no padframe or pinmux generation**.
* The physical I/O ring and package-level pin multiplexing are omitted from this configuration, as these are typically managed by the parent SoC.

## 3. Environment & Reproducibility
* The environment configuration file [mesh_subtile_env.yml](mesh_subtile_env.yml) defines the local settings for compiling and checking Mesh Subtile.
* It declares nothing beyond the project's own paths: the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

# Crux Isle Crossbar Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files for **Crux Isle**, a modular variant of the Crux SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Crux Isle is functionally analogous to the standard Crux SoC, featuring the same internal components and AXI4 central crossbar topology.
* **Isle Export (Macro Build)**: Unlike the main Crux project, this configuration is exported as a standalone, modular IP block (an "Isle") with `build_mode: "macro"`. This is intended for integration as a hard macro/block into a larger top-level design.
* **Name Suffixing**: Because this is a `macro` build, the top-level module, the SoC package, the Bender package and every generated module carry the `crux_isle` prefix rather than the bare project name, which is `crux` here just as in the standalone project. That suffixing is what allows both builds to coexist in one simulation library, as `super_crux` requires.

## 2. No Padframe Generation
* Because Crux Isle is compiled as a sub-system macro (an Isle) rather than a complete chip-level wrapper, **there is no padframe or pinmux generation**.
* The chip-level physical ring and package-level pin multiplexing are omitted from this configuration, as these tasks are typically handled by the parent SoC wrapper.

## 3. Environment & Reproducibility
* The environment configuration file [crux_isle_env.yml](crux_isle_env.yml) defines the local settings for compiling and checking Crux Isle.
* It declares nothing beyond the project's own paths: the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

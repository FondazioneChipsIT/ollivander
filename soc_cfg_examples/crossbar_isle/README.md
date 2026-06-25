# Crux Isle Crossbar Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. None of these configurations are functionally verified or intended for use in production or real hardware designs.

This directory contains the configuration files for **Crux Isle**, a modular variant of the Crux SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Crux Isle is functionally analogous to the standard Crux SoC, featuring the same internal components and AXI4 central crossbar topology.
* **Isle Export (Macro Build)**: Unlike the main Crux project, this configuration is exported as a standalone, modular IP block (an "Isle") with `build_mode: "macro"`. This is intended for integration as a hard macro/block into a larger top-level design.

## 2. No Padframe Generation
* Because Crux Isle is compiled as a sub-system macro (an Isle) rather than a complete chip-level wrapper, **there is no padframe or pinmux generation**.
* The chip-level physical ring and package-level pin multiplexing are omitted from this configuration, as these tasks are typically handled by the parent SoC wrapper.

## 3. Environment & Reproducibility
* The environment configuration file [crux_isle_env.yml](crux_isle_env.yml) defines the local settings for compiling and checking Crux Isle.
* It contains a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This guarantees a 100% reproducible build without requiring manual conflict resolution.

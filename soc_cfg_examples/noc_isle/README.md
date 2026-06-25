# Mesh Isle NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. None of these configurations are functionally verified or intended for use in production or real hardware designs.

This directory contains the configuration files for **Mesh Isle**, a modular variant of the Mesh SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Mesh Isle is functionally analogous to the standard Mesh SoC, utilizing a 2D Mesh Network-on-Chip (NoC) interconnect topology.
* **Isle Export (Macro Build)**: Unlike the top-level Mesh project, this configuration is exported as a modular subsystem macro (an "Isle") with `build_mode: "macro"`.
* **Export Verification**: The primary purpose of Mesh Isle is to test and verify the macro export flow specifically for SoC architectures built around a Network-on-Chip (NoC) topology.

## 2. No Padframe Configuration
* Because Mesh Isle is compiled as a modular IP block/macro rather than a complete chip-level wrapper, **there is no padframe or pinmux generation**.
* The physical I/O ring and package-level pin multiplexing are omitted from this configuration, as these are typically managed by the parent SoC.

## 3. Environment & Reproducibility
* The environment configuration file [mesh_isle_env.yml](mesh_isle_env.yml) defines the local settings for compiling and checking Mesh Isle.
* It includes a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This ensures a 100% reproducible build without requiring manual conflict resolution.

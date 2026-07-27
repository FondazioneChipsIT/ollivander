# Mesh SoC NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files for **Mesh**, a sample SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Mesh is an example SoC configuration inspired by the **Gwaihir** chip.
* **Interconnect Topology**: It is based on a **2D Mesh Network-on-Chip (NoC)** interconnect. The system routes packets dynamically across a grid of modular compute, memory, and peripheral tiles using the **FlooNoC** router IP.
* **Address Map**: The physical address map mirrors the Gwaihir reference exactly, down to the base address and size of every region (clusters at `0x2000_0000`, scratchpads at `0x6000_0000`, L2 tiles at `0x7000_0000`, off-chip DRAM at `0x8000_0000`).
* **Boot Memory**: The firmware is placed in `top_spm_narrow`, the narrow scratchpad. That component belongs to no auto control group, so it is never clock-gated and the host can fetch its first instruction unaided. This is the configuration a real design would adopt: the SoC starts on its own, and the L2 tiles and compute clusters stay gated until software enables them.
* **Preload Geometry**: With a 64-bit AXI word and a 64-bit SRAM bank, the interleaved preload degenerates to a single group of 16 banks, a case none of the other examples exercises.

## 2. No Padframe Configuration
* There is **no physical padframe or pinmux configuration** defined for this project.
* The design exports logical interfaces at the boundary of the NoC subsystem, without wrapping them into a physical pad ring or chip-level package layout.

## 3. Environment & Reproducibility
* The environment configuration file [mesh_env.yml](mesh_env.yml) defines the local paths and settings for building the Mesh SoC.
* It includes a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This ensures the project is completely reproducible on clean checkouts without requiring manual conflict resolution.

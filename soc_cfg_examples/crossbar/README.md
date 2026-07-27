# Crux SoC Crossbar Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files and padlists for **Crux**, a sample SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Crux is an example SoC microarchitecture inspired by the **Astral** chip.
* **Interconnect Topology**: It uses a central **AXI4 crossbar** topology, routing memory-mapped transactions between the host processor (manager), compute clusters (PULP, Spatz), memories (L2 SRAM, HyperBus), and industrial peripherals (Ethernet, CAN, UART).
* **Power-On State**: The System Controller defaults to `power_on_state: "gated"`, so every managed clock domain comes out of reset clock-gated and held in reset. The boot memory sits in the `l2` domain, so Ollivander warns at generation time and the generated testbench brings the domains up before the host starts fetching, standing in for the JTAG or boot agent that real silicon would need.

## 2. Alternative Padlist Formats
To define the chip I/O ring and pinmux configurations, Ollivander supports three functionally equivalent and alternative input modalities. Crux provides files for all three formats:
* **CSV Flat File (`crux_pads.csv`)**: A single tabular spreadsheet detailing the pad definitions across all voltage domains.
* **Python Generator Script (`crux_pads.py`)**: A procedural Python script that dynamically generates the pad lists using programming loops.
* **Native YAML Padlists (`crux_pad_list_1v8.yml` and `crux_pad_list_3v3.yml`)**: Static YAML specifications, split into one file per power/voltage domain.

> [!NOTE]
> The active input format is selected in the main SoC configuration file, [crux.yml](crux.yml), under the `padframe` section by configuring either `pad_csv`, `pad_py`, or the `domains.pad_list` keys.

## 3. Environment & Reproducibility
* The environment configuration file [crux_env.yml](crux_env.yml) defines the local paths and settings for building Crux.
* It contains a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This guarantees a 100% reproducible build without requiring manual conflict resolution.

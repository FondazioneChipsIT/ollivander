# Crux SoC Crossbar Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. None of these configurations are functionally verified or intended for use in production or real hardware designs.

This directory contains the configuration files and padlists for **Crux**, a sample SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Crux is an example SoC microarchitecture inspired by the **Astral** chip.
* **Interconnect Topology**: It uses a central **AXI4 crossbar** topology, routing memory-mapped transactions between the host processor (manager), compute clusters (PULP, Spatz), memories (L2 SRAM, HyperBus), and industrial peripherals (Ethernet, CAN, UART).

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

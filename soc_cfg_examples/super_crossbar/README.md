# Super Crux SoC Crossbar Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files and padlists for **Super Crux**, a hierarchical SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Super Crux is identical to the Crux SoC (featuring the same top-level components and interconnect), but additionally integrates a pre-generated modular subsystem macro: the **`mesh_isle`** exported by the `noc_isle` example.
* **Dependency Requirement**: Since Super Crux integrates `mesh_isle` as a pre-compiled macro subsystem, the `noc_isle` project must be generated first before running code generation for `super_crux`.
* **Cross-Topology Verification**: The nesting is deliberately crossed with `super_noc` (which nests the Crux macro): a complete NoC-based SoC — FlooNoC mesh, Snitch clusters, its own generated packages — is integrated, wired and compiled inside an AXI4-crossbar parent. Each super example therefore resolves and simulates the external IPs of **both** topology families in a single Bender graph, which makes the pair the standing regression test of the dependency catalogue shipped in `ollivander_config.yml`.

## 2. Padframe Configuration
* The chip-level physical I/O ring and pin multiplexing are defined procedurally using the Python generator script [super_crux_pads.py](super_crux_pads.py).
* The main Python-based SoC configuration script, [super_crux.py](super_crux.py), references this script under the `padframe` settings to build the physical padlist across voltage domains.

## 3. Environment & Reproducibility
* The environment configuration file [super_crux_env.yml](super_crux_env.yml) defines the paths and settings for building Super Crux.
* It declares nothing beyond the project's own paths — including where to find the pre-generated macro (`../noc_isle/generated`): the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

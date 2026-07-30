# Super Mesh SoC NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. The automated test suite generates it, elaborates it under both QuestaSim and Verilator, and runs a hello-world firmware through to completion; that is a smoke test of the generator, not functional verification of the design. None of these configurations are intended for production or real hardware.

This directory contains the configuration files for **Super Mesh**, a hierarchical SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Super Mesh is structurally similar to the Mesh SoC, utilizing a Network-on-Chip (NoC) interconnect, but additionally integrates two pre-generated subsystem macros: the **`crux_isle`** exported by the `crossbar_isle` example, joined onto the NoC through a narrow/wide join adapter, and the NoC-native **`mesh_subtile`**, which plugs its dual AXI ports straight into both networks.
* **Dependency Requirement**: Since Super Mesh integrates `crux_isle` and `mesh_subtile` as pre-compiled subsystem macros, both the `crossbar_isle` and `noc_subtile` projects must be generated first before running code generation for `super_mesh`.
* **Cross-Topology Verification**: The nesting is deliberately crossed with `super_crossbar` (which nests the Mesh macro): a complete crossbar-based SoC — Cheshire host, OpenTitan, Safety Island, PULP and Spatz clusters — is integrated and compiled inside a NoC parent. Each super example therefore resolves and simulates the external IPs of **both** topology families in a single Bender graph, which makes the pair the standing regression test of the dependency catalogue shipped in `ollivander_config.yml`.
* **Package Coexistence**: this example also proves the naming rules hold: `super_mesh` and `mesh_subtile` both stem from "mesh", yet `mesh_subtile_soc_pkg` and `super_mesh_soc_pkg` (plus their FlooNoC packages) coexist in one simulation library because every generated name derives from the top-level module name, never from the bare project name.
* **Scale**: A single instance of each macro is instantiated. Every `mesh_subtile` instance is a complete SoC in its own right (a Cheshire host, 16 Snitch clusters and 8 L2 tiles), so the array of eight this example used to declare exceeded what the simulator could map into memory while adding nothing to what the example demonstrates. The grid keeps its rectangular shape: the freed coordinates are filled with dummy tiles, which are pure FlooNoC routers.
* **Boot Memory**: The firmware is placed in one of the parent's own L2 tiles, which is gated at power-on, so this example exercises the testbench bring-up inside the deepest hierarchy of the set.

## 2. No Padframe Configuration
* There is **no physical padframe or pinmux configuration** defined for this project.
* The design exports logical interfaces at the boundaries of the parent SoC without wrapping them into a physical pad ring.

## 3. Environment & Reproducibility
* The environment configuration file [super_mesh_env.yml](super_mesh_env.yml) defines the local settings for compiling and checking Super Mesh.
* It declares nothing beyond the project's own paths — including where to find the pre-generated macros (`../crossbar_isle/generated`, `../noc_subtile/generated`): the external IP revisions and the forced resolutions that make the build reproducible are the dependency catalogue shipped in `ollivander_config.yml`, shared by every example.

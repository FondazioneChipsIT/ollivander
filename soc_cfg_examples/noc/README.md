# Mesh SoC NoC Example

> [!IMPORTANT]
> **Disclaimer**: This example project is provided solely to demonstrate Ollivander's configurations and test its code generation capabilities. None of these configurations are functionally verified or intended for use in production or real hardware designs.

This directory contains the configuration files for **Mesh**, a sample SoC configuration designed for Ollivander.

## 1. Project Overview
* **Architecture**: Mesh is an example SoC configuration inspired by the **Gwaihir** chip.
* **Interconnect Topology**: It is based on a **2D Mesh Network-on-Chip (NoC)** interconnect. The system routes packets dynamically across a grid of modular compute, memory, and peripheral tiles using the **FlooNoC** router IP.

## 2. No Padframe Configuration
* There is **no physical padframe or pinmux configuration** defined for this project.
* The design exports logical interfaces at the boundary of the NoC subsystem, without wrapping them into a physical pad ring or chip-level package layout.

## 3. Environment & Reproducibility
* The environment configuration file [mesh_env.yml](mesh_env.yml) defines the local paths and settings for building the Mesh SoC.
* It includes a comprehensive list of version `overrides` that lock external dependencies to specific, verified Git revisions. This ensures the project is completely reproducible on clean checkouts without requiring manual conflict resolution.

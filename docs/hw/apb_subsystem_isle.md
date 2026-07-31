# APB Subsystem Isle Generation & Architecture

The `apb_subsystem_isle` is a unique component within the Ollivander framework. Unlike other static Isles (which are handwritten SystemVerilog files), this Isle is **dynamically generated** by Ollivander during the build process to perfectly match the user's YAML configuration.

This document details how its generation works, its dependencies, and the peripherals it supports out-of-the-box.

---

## 1. How Generation Works

The generation of the `apb_subsystem_isle.sv` file happens during **Phase 1 (Dynamic Isles Generation)** in `ollivander.py`:

1. **YAML Parsing**: Ollivander reads the `components` list inside the `apb_subsystem` block of your SoC configuration.
2. **Interrupt Auto-Injection**: For known standard peripherals, Ollivander automatically populates their `interrupts` dictionary. This keeps the user's YAML extremely clean.
3. **Mako Rendering**: The script feeds this list to the `apb_subsystem_isle.sv.mako` template.
4. **Protocol Pipeline Generation**: The template generates a robust, multi-stage protocol conversion pipeline:
   * `Async AXI4 (64-bit)` $\rightarrow$ `Sync AXI4 (64-bit)` (via `axi_cdc_dst`)
   * `Sync AXI4` $\rightarrow$ `AXI4 Atomics` (via `axi_riscv_atomics_structs`)
   * `AXI4 Atomics` $\rightarrow$ `AXI4 (32-bit)` (via `axi_dw_converter` and `axi_modify_address`)
   * `AXI4 (32-bit)` $\rightarrow$ `AXI4-Lite` (via `axi_to_axi_lite`)
   * `AXI4-Lite` $\rightarrow$ `APB` (via `axi_lite_to_apb`)
5. **Demux & Instantiation**: Finally, it instantiates the requested IP cores and routes the APB array (`apb_req`, `apb_rsp`) to them.

---

## 2. Dependencies and Libraries

To achieve this complex protocol conversion and IP integration, the generated `apb_subsystem_isle.sv` imports the following standard libraries:

*   **`axi_pkg`** (PULP Platform): Used for AXI types, macros, CDC, atomics, downsize, and AXI-Lite conversion.
*   **`apb_pkg`** (PULP Platform): Used for APB types and the AXI-Lite to APB bridge.
*   **`register_interface_pkg`** (PULP Platform): Used for the intermediate `REG_BUS` bridging.
*   **`tlul_ot_pkg`** (OpenTitan): Used to adapt OpenTitan IPs (TileLink Uncached Lightweight) to the PULP ecosystem.
*   **Ollivander Infrastructure**: Instantiates `edge_propagator` (from `components/infrastructure/`) to safely convert pulsed/edge-triggered interrupts into stable level-sensitive signals across clock domains.

---

## 3. Supported Peripherals

The template currently knows how to instantiate the following peripheral IPs. Each requires its specific source repository to be present in the compilation environment.

| IP Name / Type | Description | Source / Library |
| :--- | :--- | :--- |
| **`apb_timer_unit`** | 64-bit generic system timer (can run as two 32-bit) | PULP Platform |
| **`apb_adv_timer`** | Advanced timer for PWM and event capture | PULP Platform |
| **`aon_timer`** | Always-On (AON) Timer used for Watchdog and Wakeup | OpenTitan (`tlul` based) |
| **`can_top_apb`** | Controller Area Network (CAN) bus controller | Third-Party / OpenCores |

*Note on `aon_timer`: Because it is an OpenTitan IP, Ollivander automatically generates an `apb_to_reg` $\rightarrow$ `reg_to_tlul` conversion chain specifically for this module.*

---

## 4. Known Interfaces & Auto-Injected Interrupts

Because Ollivander is "aware" of the exact hardware interfaces exposed by the supported peripherals, it automatically injects their interrupt definitions during Phase 1. 

**The hardware designer does NOT need to define these in the YAML configuration.** They will be automatically exposed as output ports on the `apb_subsystem_isle` boundary, ready to be referenced by the `manager` (Host) in the YAML.

### `apb_timer_unit`
*   `irq_hi` (Width: 1)
*   `irq_lo` (Width: 1)

### `apb_adv_timer`
*   `events` (Width: 4)
*   `channels` (Width: 4)

### `aon_timer` (Watchdog)
*   `aon_timer_rst_req` (Width: 1)
*   `wkup_req` (Width: 1)
*   `nmi_wdog_timer_bark` (Width: 1)
*   `intr_wdog_timer_bark` (Width: 1)
*   `intr_wkup_timer_expired` (Width: 1)

### `can_top_apb`
*   `event` (Width: 1)

### Usage Example in YAML
You can seamlessly route these auto-injected interrupts to the Host by prefixing them with the component instance name and the interrupt name.

```yaml
host:
  # ...
  interrupts:
    intr_ext_i:
      source: >
        {
          [21] : apb_subsystem.system_timer_irq_hi_o,
          [11] : apb_subsystem.can_bus_event_o
        }
```
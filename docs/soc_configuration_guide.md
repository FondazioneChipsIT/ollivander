# Ollivander SoC Generator: YAML Configuration Guide

The YAML configuration file is the **Single Source of Truth (SSoT)** for the Ollivander SoC Generator. It defines the topology, clock domains, system parameters, and the hardware components instantiated in the system.

Ollivander uses a "Hardware-First" validation engine (`soc_schema.py`) to parse this file and guarantee that the requested configuration is physically compatible with the underlying SystemVerilog modules.

---

## 1. Root Structure

A valid Ollivander YAML configuration must contain the following top-level blocks:

```yaml
project: ...             # 1. Project metadata
topology: ...            # 2. Global interconnect style
system_settings: ...     # 3. Microarchitectural tuning
clock_tree: ...          # 4. Clock and reset domains
system_controller: ...   # 5. Central PCRs (Optional but recommended)
host: ...                # 6. Main Manager component
components: ...          # 7. List of Subordinate/Peripheral components
```

---

## 2. Block Definitions

### 2.1 Project (`project`)
Basic metadata used to name the generated packages and top-level modules.

| Field         | Type   | Description                                                                     |
| :------------ | :----- | :------------------------------------------------------------------------------ |
| `name`        | String | The name of the project (e.g., `carfield`). Dictates the top-level module name. |
| `description` | String | Brief description of the SoC.                                                   |
| `author`      | String | Author or organization name.                                                    |

### 2.2 Topology (`topology`)
Defines the global interconnect architecture. Determines which templates are used for generation.

| Field          | Type   | Description                                                          |
| :------------- | :----- | :------------------------------------------------------------------- |
| `type`         | String | Must be `"crossbar"` (standard AXI) or `"noc"` (FlooNoC mesh).       |
| `global_bus`   | Object | **Required if `type` is "crossbar"**. Defines global AXI geometries. |
| `noc_settings` | Object | **Required if `type` is "noc"**. Defines FlooNoC parameters.         |

**Global Bus (`global_bus`)**:
*   `protocol`: String (e.g., `"AXI4"`).
*   `data_width`, `addr_width`, `user_width`, `mst_id_width`: Integers representing AXI bit-widths.

**NoC Settings (`noc_settings`)**:
*   `routing_algorithm`: String (e.g., `"XY"`).
*   `networks`: Dictionary defining parallel physical networks (e.g., `narrow`, `wide`), each with `data_width` and `addr_width`.
*   `default_tile`: String representing the fallback router (e.g., `"dummy_tile"`).

### 2.3 System Settings (`system_settings`)
Microarchitectural definitions for system-wide coherence.

| Field          | Type   | Description                                                                         |
| :------------- | :----- | :---------------------------------------------------------------------------------- |
| `user_mapping` | Object | Maps AXI `user` bits: `amo_msb`, `amo_lsb`, `ecc_err_bit`.                          |
| `llc`          | Object | L2 Cache limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut`. |
| `reg_bus`      | Object | RegBus limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut`.   |

### 2.4 Clock Tree (`clock_tree`)
Defines the hardware clock distribution network, generating glitch-free muxes and dividers.

| Field     | Type    | Description                                                    |
| :-------- | :------ | :------------------------------------------------------------- |
| `flls`    | Integer | Total number of Frequency Locked Loops (FLLs) driving the SoC. |
| `domains` | List    | List of clock domain objects.                                  |

**Domain Object**:
*   `name`: String. Name of the domain (e.g., `periph`).
*   `is_real_time`: Boolean. If `true`, avoids dynamic division/muxing.
*   `source_fll`: Integer. Hardwired FLL index (avoids deadlocks).
*   `static_div`: Integer. Static division factor.
*   `has_mux`: Boolean. Generates a software-controllable glitch-free mux.
*   `has_divider`: Boolean. Generates a software-controllable integer divider.
*   `has_debug_divider`: Boolean. Generates a parallel clock branch for JTAG/Debug.
*   `default_div`: Integer. Default division factor at reset (default `1`).

### 2.5 System Controller (`system_controller`)
Instructs Ollivander to generate a unified Control and Status Register (CSR) block.

| Field                 | Type    | Description                                                                            |
| :-------------------- | :------ | :------------------------------------------------------------------------------------- |
| `name`                | String  | Name of the PCR block (e.g., `sys_ctrl`).                                              |
| `base_addr`           | Int/Hex | Memory-mapped base address.                                                            |
| `size`                | Int/Hex | Size of the memory region.                                                             |
| `scratch_registers`   | Integer | Number of generic R/W scratch registers.                                               |
| `version_registers`   | Integer | Number of read-only version registers.                                                 |
| `jedec_id`            | Int/Hex | Value for the JEDEC IDCODE register.                                                   |
| `fll_status_regs`     | Boolean | Exposes FLL lock inputs as read-only registers.                                        |
| `external_registers`  | List    | External RegBus blocks to route (`name`, `base_addr`, `size`).                         |
| `auto_control_groups` | List    | Auto-generates arrays of clock gates/resets for NoC components (e.g., `cluster_ctrl`). |

---

## 3. Host and Components (`host`, `components`)

The `host` block and the items in the `components` list share the **exact same schema**. They represent the hardware IPs (Isles/Tiles) stitched together by Ollivander.

| Field               | Type    | Description                                                                                       |
| :------------------ | :------ | :------------------------------------------------------------------------------------------------ |
| `name`              | String  | **Required**. Unique instance name in the SoC.                                                    |
| `type`              | String  | **Required**. Must match the exact filename of the SystemVerilog wrapper (e.g., `cheshire_isle`). |
| `clock_domain`      | String  | **Required**. Assigns the component to a domain in the `clock_tree`.                              |
| `reset_domain`      | String  | *Optional*. Derived automatically from `clock_domain` if omitted.                                 |
| `base_addr`         | Int/Hex | *Optional*. Used mainly for APB sub-components.                                                   |
| `size`              | Int/Hex | *Optional*. Used mainly for APB sub-components.                                                   |
| `export_interfaces` | List    | *Optional*. Raw I/O pins to route directly to the SoC top-level (e.g., `["uart", "jtag"]`).       |
| `interfaces`        | Object  | *Optional*. Standardized bus connections (AXI, RegBus, NoC).                                      |
| `system_config`     | Object  | *Optional*. Links the component to the System Controller (resets, clock gating, boot).            |
| `interrupts`        | Object  | *Optional*. Defines IRQ routing logic.                                                            |
| `parameters`        | Object  | *Optional*. Overrides `parameter` values in the SV hardware wrapper.                              |
| `placement`         | Object  | **Required in NoC**. Defines X/Y coordinates on the mesh.                                         |
| `components`        | List    | *Optional*. Nested components (e.g., IPs inside an APB Subsystem).                                |

### 3.1 Interfaces (`interfaces`)
*   `axi_master`: Boolean (`true` / `false`).
*   `axi_slave`: List of memory regions. Each region takes `name`, `base_addr`, `size` (or `size_per_instance`), `ports` (integer, default 1), and `sync_domain` (Boolean, default `true`).
*   `regbus_slave`: List of register regions. Same format as `axi_slave`, plus an `external` boolean flag.
*   `llc_port`: List of memory regions. Point-to-point asynchronous AXI link to the Host.
*   `noc_networks` (NoC Only): Dictionary with `master` (list of networks, e.g. `["narrow"]`), `slave` (list of networks), and `noc_mode` (`"joined"` or `"dual"`).

### 3.2 System Configuration (`system_config`)
Wires the component to the central `system_controller`.
*   `isolate`: Boolean. Generates AXI isolation fences and status registers.
*   `fetch_enable` / `boot_enable`: Boolean. Generates a core wake-up register.
*   `boot_addr`: Int/Hex. Generates a programmable boot address register.
*   `debug_req`: Boolean. Generates a programmable debug request register.
*   `has_busy_status` / `has_eoc_status`: Boolean. Exposes status flags to software.

### 3.3 Parameters (`parameters`)
Key-value pairs corresponding to SystemVerilog `parameter` declarations in the Isle/Tile wrapper. 
*   Ollivander verifies that the parameter physically exists in the SV file.
*   Ollivander ensures you do not attempt to override a fixed `localparam`.

### 3.4 Interrupts (`interrupts`)
Defines the routing of level-sensitive interrupts. Key is the destination port name, value is an object defining the source.

*   **Simple Wire Routing:**
    ```yaml
    interrupts:
      cfi_req_irq_i: 
        source: "manager.intr_ext_o[23]"
        cdc: false # Optional: disables the clock-domain crossing synchronizer
    ```
*   **Sparse Array Mapping (e.g., Host aggregators):**
    ```yaml
    interrupts:
      intr_ext_i:
        source: >
          {
            [22] : ethernet.eth_rx_irq_o,
            [19:16] : apb_subsystem.advanced_timer_events_o
          }
    ```

### 3.5 NoC Placement (`placement`) - *Topology: "noc" only*
Maps the component to the physical 2D FlooNoC mesh grid.

*   **Single Node:**
    ```yaml
    placement:
      logical: { x: 9, y: 3 }
    ```
*   **Multi-Node Region (Box):**
    ```yaml
    placement:
      logical:
        box: { x_start: 4, x_end: 7, y_start: 0, y_end: 3 }
    ```
*   **Fragmented Regions:**
    ```yaml
    placement:
      logical:
        - box: { x_start: 0, x_end: 0, y_start: 0, y_end: 3 }
        - box: { x_start: 8, x_end: 8, y_start: 0, y_end: 3 }
    ```
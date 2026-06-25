# Ollivander SoC Generator: YAML & Python Configuration Guide

The configuration file is the **Single Source of Truth (SSoT)** for the Ollivander SoC Generator. It defines the topology, clock domains, system parameters, and the hardware components instantiated in the system. 

You can write this configuration using either **YAML** (static, easy to read) or **native Python** (`.py`). Using Python (Configuration-as-Code) allows you to use variables for the memory map, loops for placing NoC clusters, and benefits from IDE autocompletion via Pydantic models.

Ollivander uses a "Hardware-First" validation engine (combining `soc_schema.py` for configuration schema checking and `sv_parser.py` for SystemVerilog AST parsing) to validate these configurations and guarantee that they are physically compatible with the underlying SystemVerilog modules.

---

## 1. Root Structure

A valid Ollivander configuration must contain the following top-level blocks. If using Python, these are instantiated as a `config` variable of type `OllivanderConfig`:

```yaml
project: ...             # 1. Project metadata
topology: ...            # 2. Global interconnect style
system_settings: ...     # 3. Microarchitectural tuning
clock_tree: ...          # 4. Clock and reset domains
system_controller: ...   # 5. Central PCRs (Optional but recommended)
padframe: ...            # 6. Physical Padframe and Pinmux (Optional)
host: ...                # 7. Main Manager component
components: ...          # 8. List of Subordinate/Peripheral components
testbench: ...           # 9. Simulation configuration (Optional)
software_stack: ...      # 10. Firmware compilation setup (Optional)
```

---

## 2. Block Definitions

### 2.1 Project (`project`)
Basic metadata used to name the generated packages and top-level modules.

| Field            | Type   | Description                                                                      |
| :--------------- | :----- | :------------------------------------------------------------------------------- |
| `name`           | String | The name of the project (e.g., `carfield`). Dictates the top-level module name.  |
| `description`    | String | Brief description of the SoC.                                                    |
| `author`         | String | Author or organization name.                                                     |
| `build_mode`     | String | *Optional*. `"standalone"` (default) or `"macro"`. If `"macro"`, generates a     |
|                  |        | reusable IP block instead of a complete SoC.                                     |
| `macro_settings` | Object | *Optional*. Configuration for macro generation. Evaluated only if                |
|                  |        | `build_mode` is `"macro"`.                                                       |
| `vendor`         | String | *Optional*. Vendor name for IP-XACT component metadata (default: `"Ollivander"`).|
| `library`        | String | *Optional*. Library name for IP-XACT component metadata (default: `"SoC"`).       |
| `version`        | String | *Optional*. Version string for IP-XACT component metadata (default: `"1.0"`).     |

**Macro Settings (`macro_settings`)**:
Defines the interfaces exported at the top-level boundaries when the SoC is generated as a macro.
*   `export_type`: String. `"isle"` (default, exposes a single unified standard AXI interface) or `"subtile"` (exposes the native narrow and wide networks separately). Note: `"subtile"` is only valid for `"noc"` topologies.
*   `masters` / `slaves`: List of objects defining the AXI interfaces exported by the macro.

**Macro Export Object**:
*   `bus_type`: String. `"standard"`, `"narrow"`, or `"wide"`.
*   `target`: String. The internal connection target. For NoC topology, it is the boundary router's coordinate and side (e.g., `"[9,3].East"`). For Crossbar topology, it is typically `"host"`.

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

| Field          | Type   | Description                                                                        |
| :------------- | :----- | :--------------------------------------------------------------------------------- |
| `user_mapping` | Object | Maps AXI `user` bits: `amo_msb`, `amo_lsb`, `ecc_err_bit`.                         |
| `llc`          | Object | L2 Cache limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut` |
| `reg_bus`      | Object | RegBus limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut`   |

### 2.4 Clock Tree (`clock_tree`)
Defines the hardware clock distribution network, generating glitch-free muxes and dividers.

| Field       | Type    | Description                                                                          |
| :---------- | :------ | :----------------------------------------------------------------------------------- |
| `generators`| Integer | Total number of Clock Generators available. Setting to `0` means clocks are          |
|             |         | external.                                                                            |
| `domains`   | List    | List of clock domain objects.                                                        |

**Domain Object**:
*   `name`: String. Name of the clock domain (e.g., `periph`).
*   `is_real_time`: Boolean. If `true`, the domain bypasses software control (always-on, cannot be gated).
*   `source_gen`: Integer. Hardwired Clock Generator index. Critical for the host clock to ensure it ticks at boot and avoids deadlocks.
*   `static_div`: Integer. Static, non-programmable division factor (e.g., `100` for an RTC).
*   `has_mux`: Boolean. Generates a software-controllable glitch-free multiplexer to switch between clock generators.
*   `has_divider`: Boolean. Generates a software-controllable integer divider with glitch-free gating.
*   `has_debug_divider`: Boolean. Generates a parallel, slower clock branch specifically for JTAG and Debug Module Interfaces.
*   `default_div`: Integer. Default division factor applied at power-on reset (default `1`).

### 2.5 System Controller (`system_controller`)
Instructs Ollivander to generate a unified Control and Status Register (CSR) block via PeakRDL.

| Field                 | Type    | Description                                                                |
| :-------------------- | :------ | :------------------------------------------------------------------------- |
| `name`                | String  | Name of the PCR block (e.g., `sys_ctrl`).                                  |
| `base_addr`           | Int/Hex | Memory-mapped base address.                                                |
| `size`                | Int/Hex | Size of the memory region.                                                 |
| `scratch_registers`   | Integer | Number of generic R/W scratch registers.                                   |
| `version_registers`   | Integer | Number of read-only version registers.                                     |
| `jedec_id`            | Int/Hex | Value for the JEDEC IDCODE register.                                       |
| `clk_gen_status_regs` | Boolean | Exposes Clock Generator lock inputs as read-only registers.                |
| `external_registers`  | List    | External RegBus blocks to route (`name`, `base_addr`, `size`).             |
| `auto_control_groups` | List    | Auto-generates arrays of clock gates/resets for NoC components (e.g.,      |
|                       |         | `cluster_ctrl`).                                                           |

### 2.6 Padframe (`padframe`)
Delegates the physical pad ring definition to **Padrick**, while Ollivander automatically handles the top-level RegBus, CDC adapters, and signal wiring in the Chip Wrapper Engine.

*Note: This section is completely ignored (and chip wrapper generation is skipped) if `project.build_mode` is set to `"macro"`.*

| Field          | Type    | Description                                                                       |
| :------------- | :------ | :-------------------------------------------------------------------------------- |
| `name`         | String  | Name of the padframe module (e.g., `carfield_padframe`).                          |
| `description`  | String  | *Optional*. Brief description of the padframe.                                    |
| `base_addr`    | Int/Hex | Memory-mapped base address for the Padrick-generated Pinmux CSRs.                 |
| `size`         | Int/Hex | *Optional*. Size of the memory region (default: `0x1000`).                        |
| `sync_domain`  | Boolean | *Optional*. `true` = Host Clock, `false` = Uses async CDC adapter for the         |
|                |         | configuration bus (default: `false`).                                             |
| `domains`       | List    | A list of power/voltage domains containing the physical pad definitions.          |
| `padrick_cfg`  | String  | *Optional*. Path to a custom Padrick `config_top.yml` (overrides the `domains`    |
|                |         | list).                                                                            |
| `pad_csv`      | String  | *Optional*. Path to a CSV file defining the padlist dynamically across domains.    |
| `pad_py`       | String  | *Optional*. Path to a Python file defining the padlist dynamically across domains. |
| `header_file`  | String  | *Optional*. Path to a text file for the RTL header (auto-generates standard       |
|                |         | license if omitted).                                                              |

**Domain Object (`domains` list):**
Used to partition pads into multiple power or I/O domains (e.g., 1.8V vs 3.3V).
*   `name`: String. Name of the domain (e.g., `domain_1v8`).
*   `tech`: String. Name of the technology catalog file to use (e.g., `behavioral`, `tsmc28_io`). Ollivander looks for this catalog as `padframes/<tech_name>/<tech_name>.yml` under the component search paths (e.g. `components/padframes/<tech_name>/<tech_name>.yml`).
*   `pad_list`: String. *Optional*. Path to the YAML file detailing the specific pads for this domain. Required only if neither `pad_csv` nor `pad_py` is specified.

**Example Padframe Configuration (showing the 3 alternative definition methods):**
```yaml
padframe:
  name: "crux_padframe"
  base_addr: 0x200A0000
  sync_domain: false

  # --- Alternative 1: CSV Padlist (Default) ---
  pad_csv: "crux_pads.csv"
  domains:
    - name: "domain_1v8"
      tech: "behavioral"
    - name: "domain_3v3"
      tech: "behavioral"

  # --- Alternative 2: Python Dynamic Padlist ---
  # pad_py: "crux_pads.py"
  # domains:
  #   - name: "domain_1v8"
  #     tech: "behavioral"
  #   - name: "domain_3v3"
  #     tech: "behavioral"

  # --- Alternative 3: YAML Padlists ---
  # domains:
  #   - name: "domain_1v8"
  #     tech: "behavioral"
  #     pad_list: "crux_pad_list_1v8.yml"
  #   - name: "domain_3v3"
  #     tech: "behavioral"
  #     pad_list: "crux_pad_list_3v3.yml"
```

For a comprehensive guide explaining the padframe definition options and technology directory layouts in detail, see the [Padframe Configuration Guide](padframe_configuration_guide.md).


## 3. Host and Components (`host`, `components`)

The `host` block and the items in the `components` list share the **exact same schema**. They represent the hardware IPs (Isles/Tiles) stitched together by Ollivander.

| Field               | Type    | Description                                                                  |
| :------------------ | :------ | :--------------------------------------------------------------------------- |
| `name`              | String  | **Required**. Unique instance name in the SoC. Used to prefix generated      |
|                     |         | wires and CSRs.                                                              |
| `type`              | String  | **Required**. Must match the exact filename of the SystemVerilog wrapper     |
|                     |         | (e.g., `cheshire_isle`).                                                     |
| `clock_domain`      | String  | **Required**. Assigns the component's `clk_i` to a domain in the             |
|                     |         | `clock_tree`.                                                                |
| `reset_domain`      | String  | *Optional*. Derived automatically from `clock_domain` if omitted.            |
| `base_addr`         | Int/Hex | *Optional*. Base address in the memory map. (Mainly used for APB             |
|                     |         | sub-components; AXI slaves declare it in `interfaces`).                      |
| `size`              | Int/Hex | *Optional*. Size of the memory region.                                       |
| `export_interfaces` | List    | *Optional*. Raw I/O pins to route directly to the SoC top-level (e.g.,       |
|                     |         | `["uart", "jtag"`).                                                          |
| `interfaces`        | Object  | *Optional*. Standardized bus connections (AXI Master/Slave, RegBus, NoC      |
|                     |         | routing).                                                                    |
| `system_config`     | Object  | *Optional*. Links the component to the System Controller (isolation, fetch   |
|                     |         | enable, status flags).                                                       |
| `interrupts`        | Object  | *Optional*. Defines IRQ routing logic.                                       |
| `dedicated_clock_div`| Object | *Optional*. Auto-generates an independent clock divider specifically for     |
|                     |         | this IP (e.g., for Ethernet RGMII).                                          |
| `parameters`        | Object  | *Optional*. Overrides `parameter` values in the SV hardware wrapper.         |
| `placement`         | Object  | **Required in NoC**. Defines X/Y coordinates on the mesh.                    |
| `components`        | List    | *Optional*. Nested components (e.g., Timers/Watchdogs instantiated inside an |
|                     |         | APB Subsystem wrapper).                                                      |

### 3.1 Interfaces (`interfaces`)
*   `axi_master`: Boolean (`true` / `false`).
*   `axi_slave`: List of memory regions. Each region takes `name`, `base_addr`, `size` (or `size_per_instance`), `ports` (integer, default 1), and `sync_domain` (Boolean, default `true`). Setting `sync_domain: false` instructs Ollivander to automatically instantiate an asynchronous Clock Domain Crossing (CDC) adapter.
*   `regbus_slave`: List of register regions. Same format as `axi_slave`, plus an `external` boolean flag. Setting `external: true` means the IP is physically outside the generated Top-Level (e.g., in the Padframe); Ollivander will NOT instantiate it, but will export its RegBus ports to the SoC I/O.
*   `llc_port`: List of memory regions. Point-to-point asynchronous AXI link to the Host.
*   `noc_networks` (NoC Only): Dictionary with `master` (list of networks, e.g. `["narrow"]`), `slave` (list of networks), and `noc_mode` (`"joined"` or `"dual"`). `"joined"` automatically instantiates a FlooNoC Join adapter to merge narrow and wide traffic into a single AXI port. `"dual"` requires the component to natively expose two separate AXI ports.

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
*   You can pass standard integer values, booleans (`true`/`false`), or even SystemVerilog macros (e.g., `pkg::MyParam`).

### 3.4 Interrupts (`interrupts`)
Defines the routing of level-sensitive interrupts. The key is the destination port name on the component, and the value is an object defining the source.
Ollivander will automatically instantiate edge-to-level propagators or synchronizers if the source is in a different clock domain and `cdc: false` is not explicitly set.

*   **Simple Wire Routing:**
    ```yaml
    interrupts:
      cfi_req_irq_i: 
        source: "manager.intr_ext_o[23]"
        cdc: false # Optional: disables the clock-domain crossing synchronizer
    ```
*   **Bitwise Logic and Tie-Offs:**
    ```yaml
    interrupts:
      # Standard bitwise logic operators are supported
      irq_ibex_i: { source: "mailbox.snd_irq_o[5] | mailbox.snd_irq_o[14]", cdc: false }
      # Tie the input to 0 to avoid floating wires
      meip_i: { source: "none" }
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
Maps the component to the logical 2D FlooNoC mesh grid.

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

## 4. Testbench (`testbench`)

Instructs the simulation environment on how to initialize the SoC. Since Ollivander targets bare-metal validation, the most common action is preloading compiled software binaries directly into the hardware memory arrays before the processor comes out of reset.

| Field              | Type | Description                                                                      |
| :----------------- | :--- | :------------------------------------------------------------------------------- |
| `preload_memories` | List | A list of memory arrays to be initialized in the SystemVerilog testbench using   |
|                    |      | `$readmemh`.                                                                     |

**Memory Preload Object**
*   `instance`: String. The hierarchical RTL path to the memory array instance inside the top-level.
    *   *For Crossbar topologies*: It is usually `<component_name>.sram_array`.
    *   *For NoC topologies*: Memories are physically split across tiles. You must target the specific tile instance, typically the first one where the Host expects to boot (e.g., `i_tile_0_0.sram_array`).
*   `file`: String. The path to the compiled hex binary (e.g., `generated/sw/hello_world.hex`).

**Example (Crossbar):**
```yaml
testbench:
  preload_memories:
    - instance: "l2_shared_memory.sram_array"
      file: "generated/sw/hello_world.hex"
```

---

## 5. Software Stack (`software_stack`)

Defines the parameters for automated bare-metal C firmware generation and compilation. Ollivander uses these settings to dynamically construct a **Linker Script** (`link.ld`) that aligns exactly with the physical memory map defined in the `components` section, preventing hard-to-debug memory faults.

| Field         | Type   | Description                                                                         |
| :------------ | :----- | :---------------------------------------------------------------------------------- |
| `toolchain`   | String | The GCC toolchain prefix (e.g., `"riscv64-unknown-elf-"`).                          |
| `boot_memory` | String | **Required**. The `name` of the memory component (from the `components` list) where |
|               |        | the boot`.text`, `.data`, and `.bss` sections will be placed. Ollivander will       |
|               |        | automatically fetch its `base_addr` and `size`.                                     |
| `test_app`    | Object | Configuration for the automatically generated test application.                     |

**Test App Object**:
*   `name`: String. The base name used for the output files (`<name>.elf`, `<name>.hex`).
*   `auto_generate_c`: Boolean. If `true`, Ollivander creates a starter `main.c` file. This file automatically `#include`s the generated hardware headers (e.g., `<project>_map.h` and `<project>_regs.h`) so you have immediate access to all peripheral base addresses, IRQs, and PeakRDL generated CSR macros.

**Example:**
```yaml
software_stack:
  toolchain: "riscv64-unknown-elf-"
  boot_memory: "l2_shared_memory"
  test_app:
    name: "hello_world"
    auto_generate_c: true
```
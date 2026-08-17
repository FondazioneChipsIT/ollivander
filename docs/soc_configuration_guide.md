# Ollivander SoC Generator: YAML & Python Configuration Guide

The configuration file is the **Single Source of Truth (SSoT)** for the Ollivander SoC Generator. It defines the topology, clock domains, system parameters, and the hardware components instantiated in the system. 

You can write this configuration using either **YAML** (static, easy to read) or **native Python** (`.py`). Using Python (Configuration-as-Code) allows you to use variables for the memory map, loops for placing NoC clusters, and benefits from IDE autocompletion via Pydantic models.

Ollivander uses a "Hardware-First" validation engine (combining `soc_schema.py` for configuration schema checking and `sv_parser.py` for SystemVerilog AST parsing) to validate these configurations and guarantee that they are physically compatible with the underlying SystemVerilog modules.

**Nothing in this file is accepted silently.** An unknown field is refused with its full path, a value of the wrong shape is refused with the shape expected, and a name that refers to something else in the file — a clock domain, a boot memory — must resolve to a declaration. This guide is therefore the authoritative list of what is accepted, not merely a description of it: a field it does not mention is a field the generator refuses. Section 6 shows what each kind of mistake reports.

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

**Macro Settings (`macro_settings`)**: Defines the interfaces exported at the top-level boundaries when the SoC is generated as a macro.
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
*   `type`: String. **Required.** The NoC generator backend; `"floo_noc"` is the one Ollivander supports.
*   `routing_algorithm`: String (e.g., `"XY"`).
*   `networks`: Dictionary defining parallel physical networks (e.g., `narrow`, `wide`), each with `data_width` and `addr_width`. Both a `narrow` and a `wide` network are required: that is what the generator always emits, and omitting or misspelling one is refused rather than absorbed.
*   `default_tile`: String representing the fallback router (e.g., `"dummy_tile"`).

**Network ID width (`networks.<name>.id_width`)**

Optional, and normally best left out: the width of the AXI ID a network accepts on its input side is **derived** from what the components attached to it need, with FlooNoC's own defaults (4 narrow, 3 wide) as the floor. Every generation reports the value it resolved and where it came from:

```
  -> Narrow network ID width: 6 (imposed by 'crux_subsystem')
  -> Wide network ID width: 3 (FlooNoC default)
```

Only a **nested macro** can raise it. A hand-written isle is told which ID width to produce, and adapts; a macro generated by another Ollivander run cannot, because the width of its exported master port comes from the interconnect built into it. That number is published in the macro's own SoC package and read back here, so declaring it by hand is unnecessary.

Declaring `id_width` explicitly makes it fixed rather than derived, and it is then checked in both directions:

*   a value **smaller** than a nested macro's exported master port is refused — retyping that port narrower would alias its IDs;
*   a value (declared or derived) **larger** than what a nested subtile macro accepts is also refused, since that macro feeds its slave ports straight into the chimneys of its own network and the extra bits would be truncated at the boundary.

The second case is the one worth understanding, because it reaches across projects. The ID width of a network is shared by every macro attached to it, while the macros are generated independently and none of them can see the others: a macro imposing 6 bits forces the network to 6, and any other macro on that same network must have been generated wide enough to accept 6. When it was not, the generator says which project to change:

```
[ERROR] The 'narrow' network resolves to an ID width of 6 bits, but the macro
        'ai_mesh_macro' accepts at most 4.
        Declare 'id_width: 6' on the 'narrow' network of the project that
        generates 'ai_mesh_macro' and regenerate it.
```

This is why `noc_subtile` declares `id_width: 6` while needing only 4 for itself — it shares a network with a Crux macro in `super_noc`. The output side of each network (2 narrow, 1 wide) is the compressed side that FlooNoC chooses for itself and is not configurable.

### 2.3 System Settings (`system_settings`)
Microarchitectural definitions for system-wide coherence.

| Field          | Type   | Description                                                                        |
| :------------- | :----- | :--------------------------------------------------------------------------------- |
| `user_mapping` | Object | Maps AXI `user` bits: `amo_msb`, `amo_lsb`, `ecc_err_bit`.                         |
| `llc`          | Object | L2 Cache limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut` |
| `reg_bus`      | Object | RegBus limits: `max_read_txns`, `max_write_txns`, `amo_num_cuts`, `amo_post_cut`   |

In a NoC, `user_mapping` does more than name bits: the span up to the highest of `amo_msb` and `ecc_err_bit` **is** the user width the narrow network carries, and the `AxiUserWidth` of the whole SoC is derived from it. Moving `ecc_err_bit` therefore resizes every narrow link, and a nested macro whose meaningful span exceeds the network it injects on is refused (see "Network ID width" in section 2.2 for the sibling rule on IDs). A crossbar SoC instead takes `AxiUserWidth` from the `global_bus` declaration, and the mapping must fit inside it.

### 2.4 Clock Tree (`clock_tree`)
Defines the hardware clock distribution network, generating glitch-free muxes and dividers.

| Field                  | Type    | Description                                                                          |
| :--------------------- | :------ | :----------------------------------------------------------------------------------- |
| `generators`           | Integer | Total number of Clock Generators available. Setting to `0` means clocks are          |
|                        |         | external.                                                                            |
| `generator_periods_ns` | List    | Optional list of floats. Defines the simulation periods (in ns) for each clock        |
|                        |         | generator. Default is `10.0` ns for all generators.                                  |
| `domains`              | List    | List of clock domain objects.                                                        |

**Domain Object**:
*   `name`: String. Name of the clock domain (e.g., `periph`).
*   `is_real_time`: Boolean. If `true`, the domain bypasses software control, software gating, and multiplexing (always-on, fixed source, cannot be gated or switched at run-time). It can still have a static, hardwired hardware divider if `static_div` is configured.
*   `source_gen`: Integer. Hardwired Clock Generator index. Critical for the host clock to ensure it ticks at boot and avoids deadlocks.
*   `static_div`: Integer. Static, non-programmable hardware division factor. Instantiates a hardwired clock divider (`olli_clk_int_div`) with a fixed ratio, keeping the clock always-on at a static frequency. Supported for both real-time and managed domains.
*   `has_mux`: Boolean. Generates a software-controllable glitch-free multiplexer to switch between clock generators (ignored for real-time domains).
*   `has_divider`: Boolean. Generates a software-controllable integer divider with glitch-free gating (ignored for real-time domains).
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
| `power_on_state`      | String  | *Optional*. `"gated"` (default) or `"enabled"`. Power-on state of every    |
|                       |         | clock-enable and software-reset register generated below.                  |

#### Clock and Reset Control Registers

The System Controller generates clock-enable and software-reset registers through two independent mechanisms, both of which follow the **same convention**:

*   **Managed clock domains** — one `<domain>_clk_en` and one `<domain>_rst` register per domain served by the global reset tree. A domain is *managed* when it is neither a real-time domain (free-running, never gated) nor the host's own domain (which has a dedicated root reset generator). Each field is **1 bit** wide.
*   **Auto control groups** — one `<group>_clk_en` and one `<group>_rst` register per group, each field **as wide as the number of tiles the group controls** (16 bits for a group of 16 clusters, and so on), with one bit per tile.

| Field       | Polarity    | Meaning of a `1`      |
| :---------- | :---------- | :-------------------- |
| `*_clk_en`  | Active high | Clock enabled         |
| `*_rst`     | Active high | Block held in reset   |

`*_rst` is inverted once in RTL to produce the active-low reset the hardware expects; the register itself is always active high, so a value of `0` means "running".

> **Note for firmware**: PeakRDL emits a 1-bit SystemRDL field as a *scalar*, so a single-bit field (every domain register, and any group controlling exactly one tile) is referenced without a bit index.

#### `power_on_state`

This single setting drives the reset value of **every** register above, so the two mechanisms can never end up with opposite power-on behaviour.

*   **`"gated"` (default)**: `*_clk_en = 0` and `*_rst = all ones` — every managed domain and every controlled tile comes up clock-gated and held in reset. This is the safe hardware default and matches the behaviour of the gwaihir reference SoC. Software, or an external agent, must bring the blocks up before using them.
*   **`"enabled"`**: `*_clk_en = all ones` and `*_rst = 0` — the SoC comes up fully running without any CSR write. Convenient during bring-up, at the cost of leaving every controlled block powered from reset.

> **Boot dependency**: with `"gated"`, if the memory named by `software_stack.boot_memory` sits inside a managed domain or a controlled group, the host cannot fetch its own first instruction until something external enables that region — and firmware cannot do it, since it would have to be running already. Ollivander emits a warning at generation time when this is the case. The generated testbench performs the bring-up automatically, standing in for the JTAG / boot agent / `clk_rst_bypass_i` pin that real silicon requires.

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

**Domain Object (`domains` list):** Used to partition pads into multiple power or I/O domains (e.g., 1.8V vs 3.3V).
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
|                     |         | `clock_tree`. The name must be one of the declared domains: a value that      |
|                     |         | matches none stops generation, suggesting the closest one. Omitting the field  |
|                     |         | is legitimate and inherits the host's domain.                                 |
| `reset_domain`      | String  | *Optional*. Derived automatically from `clock_domain` if omitted.            |
| `isa`               | String  | *Optional (Host only)*. Host Instruction Set Architecture (e.g., `rv64imafdc`).|
| `abi`               | String  | *Optional (Host only)*. Host Application Binary Interface (e.g., `lp64d`).     |
| `cmodel`            | String  | *Optional (Host only)*. Host Code Model for GCC compiler (e.g., `medany`).     |
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
    *   An AXI port and the network it rides on are **two halves of one statement**: `axi_master` says the component has a master port, `noc_networks.master` says which network that port injects into. Declaring either half without the other is refused, in both directions and for both `master` and `slave`. Nothing can be inferred here — a 64-bit master port injected on the wide network instead of the narrow one is a silently malformed connection, not a detail the generator can guess.

> [!IMPORTANT]
> The entries above are the complete set: `interfaces` accepts nothing else, and neither do the nested address ranges. An unknown entry is refused by name, with the closest accepted one suggested, and a value of the wrong shape is refused too (`'interfaces'.axi_slave[0].size should be an integer, not str`). The same holds for every block of this section, which makes this guide the authoritative list of what is accepted rather than a description of it.

### 3.2 System Configuration (`system_config`)
Wires the component to the central `system_controller`.
*   `isolate`: Boolean. Generates AXI isolation fences and status registers.
*   `fetch_enable` / `boot_enable`: Boolean. Generates a core wake-up register.
*   `boot_addr`: Int/Hex. Generates a programmable boot address register.
*   `debug_req`: Boolean. Generates a programmable debug request register.
*   `is_l2_mem`: Boolean. Set to `true` if this component acts as the Level 2 (L2) shared memory. Used by the generator to identify L2 components and parameterize their base addresses/sizes.
*   `has_busy_status` / `has_eoc_status`: Boolean. Exposes status flags to software.

### 3.3 Features (`features`)
Optional switches that change how the generator treats the component, rather than what it contains.
*   `multicast_target`: Boolean. Marks the component as a destination of NoC collective (multicast) traffic, so its endpoint is generated with collective support.
*   `error_slaves`: List of strings. Names the slave ports of this component that must be terminated with an error slave instead of being connected.
*   `terminate_ports`: List of strings. Names the ports to tie off at the top level, for interfaces the SoC deliberately leaves unused.

### 3.4 Parameters (`parameters`)
Key-value pairs corresponding to SystemVerilog `parameter` declarations in the Isle/Tile wrapper. 
*   Ollivander verifies that the parameter physically exists in the SV file.
*   Ollivander ensures you do not attempt to override a fixed `localparam`.
*   You can pass standard integer values, booleans (`true`/`false`), or even SystemVerilog macros (e.g., `pkg::MyParam`).

Unlike the blocks above, the *names* here are not checked against a fixed list: they are checked against the module itself, which is stricter. An unsupported parameter stops generation naming the component and its wrapper.

### 3.5 Dedicated Clock Divider (`dedicated_clock_div`)
Gives the component its own programmable clock branch, derived from the domain it sits in — used, for instance, by an Ethernet MAC that needs a slower reference than the rest of the peripheral domain.
*   `name`: String. Name of the derived clock; the generator appends `_clk` and creates the divider registers under it.
*   `default_div`: Integer. Division factor at boot.
*   `port`: String. *Optional*. The component port the derived clock drives, when it is not the main `clk_i`.

```yaml
dedicated_clock_div:
  name: "eth"
  default_div: 10
```

### 3.6 Compilation Macros (`defines`)
A list of `+define+` macros the component's sources must be compiled with, applied to every `vlog` invocation of the project (the compilation library is one, so a define is global by nature):

```yaml
defines:
  - "MY_FEATURE"
  - "MY_DEPTH=4"    # valued defines are supported
```

Most components do not need this field: a wrapper that *requires* a define declares it itself, with a `// DEFINE: name="..."` pragma next to its `// BENDER:` ones (see the Isle standardization guide, section 7.1), and the project inherits it automatically - including through a nested macro, which re-exports the defines its internals were generated with. Declare `defines` in the SoC description only for project-level choices; entries here are merged with the inherited ones **by macro name**, and the project's value wins, so this field is also how a valued define from a wrapper is overridden.

### 3.7 Interrupts (`interrupts`)
Defines the routing of level-sensitive interrupts. The key is the destination port name on the component, and the value is an object defining the source. Ollivander will automatically instantiate edge-to-level propagators or synchronizers if the source is in a different clock domain and `cdc: false` is not explicitly set.

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

### 3.8 NoC Placement (`placement`) - *Topology: "noc" only*
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

| Field                       | Type    | Description                                                    |
| :-------------------------- | :------ | :------------------------------------------------------------- |
| `preload_memories`          | List    | Memory arrays to initialize in the testbench via `$readmemh`.   |
| `boot_mode`                 | String  | How the testbench boots the host: `"force"` (default) or `"jtag"`. See section 4.1. |
| `boot_force_delay_ns`       | Integer | How long the testbench holds the boot-mode and scratchpad force |
|                             |         | values, in ns. Must outlast the host's internal reset sequence. |
| `boot_force_fast_delay_ns`  | Integer | The same, for the shorter `fast` variant of the run.            |
| `boot_timeout_ns`           | Integer | Deadline for the design to start fetching, in ns.               |
| `boot_timeout_fast_ns`      | Integer | The same, for the `fast` variant.                               |
| `sim_timeout_ns`            | Integer | Overall simulation deadline, in ns.                             |

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

### 4.1 Boot modes: `force` and `jtag`

`boot_mode` selects how the generated testbench brings the SoC out of reset and starts the firmware. Memory preload is `$readmemh` in both modes (it is the fast regression path); what changes is everything after it.

*   `"force"` (the default) drives the host's boot-mode and scratch registers, and the system controller's clock-enable and reset registers, through hierarchical `force` statements. It is fast and needs nothing from the design, but it exercises no architectural path: silicon has no `force`.
Every generated testbench instantiates the verification IP (`components/tb/vip_ollivander_soc.sv`), which hosts all the bench's agents: the clock and reset drivers, the UART RX monitor (timed on the divisor the firmware actually programs), and the JTAG agent below. The testbench itself owns only the policy: input ties, memory preloads and the boot sequence.

*   `"jtag"` boots the SoC exactly the way silicon would, through an external JTAG debugger, and the testbench contains **no forces at all**. The VIP's JTAG agent (built on riscv-dbg's `jtag_test` driver stack) drives the SoC's `jtag_*` pins with the full sequence: TAP reset and IDCODE liveness check, debug-module activation, power-on bring-up of the gated domains via system-bus writes to the system controller (every `*_clk_en` register first, a settling pause, then every `*_rst` release), and finally the boot handoff to the host's scratch registers, with the entry pointer written read-back-verified. Any system-bus error (`sberror`) is fatal, not silent.

Requirements for `"jtag"`, both checked or supplied by the generator:

*   The host must list `"jtag"` in `export_interfaces`, otherwise its TAP pins never reach the SoC top-level. This is validated at generation time with an explicit error, because the failure mode is otherwise perfectly silent: every DMI read returns X, and X falls open through every liveness check a testbench agent can make.
*   The host component must declare the JTAG boot contract in its header: `HasJtagBoot`, `JtagIdCode` (the expected IDCODE) and `JtagScratchOffset` (the scratch-register offset inside the host's address window). `cheshire_isle` declares all three.

Among the example projects, five run `boot_mode: "jtag"` as their standard configuration (`noc`, `crossbar_isle`, `noc_isle`, `noc_subtile`, `super_crossbar`), keeping the architectural boot path under permanent regression. `crossbar` and `super_noc` deliberately stay on `"force"`: it is the schema default and a supported feature, and it would lose regression coverage if no example exercised it.

---

## 5. Software Stack (`software_stack`)

Defines the parameters for automated bare-metal C firmware generation and compilation. Ollivander uses these settings to dynamically construct a **Linker Script** (`link.ld`) that aligns exactly with the physical memory map defined in the `components` section, preventing hard-to-debug memory faults.

| Field         | Type   | Description                                                                         |
| :------------ | :----- | :---------------------------------------------------------------------------------- |
| `toolchain`   | String | The GCC toolchain prefix (e.g., `"riscv64-unknown-elf-"`). Compiler flags (ISA, ABI, Code Model) are defined under the `host` block. |
| `boot_memory` | String | **Required**. The `name` of the memory component (from the `components` list) where |
|               |        | the boot`.text`, `.data`, and `.bss` sections will be placed. Ollivander will       |
|               |        | automatically fetch its `base_addr` and `size`. The name must resolve to a declared  |
|               |        | component: a value that names nothing stops generation, suggesting the closest one.  |
| `test_app`    | Object | Configuration for the automatically generated test application.                     |

**Test App Object**:
*   `name`: String. The base name used for the output files (`<name>.elf`, `<name>.hex`). Two names select a **generated application** rather than just naming the artifacts: `hello_world` (the default UART greeting) and `offload` (see below). Any other name simply labels a `main.c` you provide yourself.
*   `auto_generate_c`: Boolean. If `true`, Ollivander creates a starter `main.c` file. This file automatically `#include`s the generated hardware headers (e.g., `<project>_map.h` and `<project>_regs.h`) so you have immediate access to all peripheral base addresses, IRQs, and PeakRDL generated CSR macros.
*   `baudrate`: Integer, optional (default `115200`). The UART rate the generated firmware programs. The generator converts it into the 16550 divisor and times the testbench's UART monitor on that **same divisor**, so the two sides cannot disagree — the divisor is an integer, and at high rates the true line rate differs from the nominal value by a few percent. Raising it is the single largest lever on simulation wall-clock time, because at 115200 a character costs ~87 µs of simulated time and the UART dominates a hello-world run: at `2000000` (divisor 3) the shipped examples close about **11× sooner**, which under Verilator turns an hour-long run into minutes. The examples ship with this value; lower it back to `115200` (or omit the key) when the firmware must drive a physical terminal.
*   `offload_targets`: List of component names, optional and meaningful only with `name: "offload"`. Restricts the offload test to a subset of the offload-capable components; by default every capable component is tested. A name that is not offload-capable stops generation with the reason — never a silent skip.
*   `payload_memory`: Component name, optional and meaningful only with `name: "offload"`. Hosts the shared payload region at the base of that component's (instance-0) window instead of carving it out of the boot memory — required when the boot memory is not fetchable by every target (see section 5.1).

**Example:**
```yaml
software_stack:
  toolchain: "riscv64-unknown-elf-"
  boot_memory: "l2_shared_memory"
  test_app:
    name: "hello_world"
    auto_generate_c: true
    baudrate: 2000000
```

### 5.1 The `offload` test application

With `test_app.name: "offload"` (which requires `auto_generate_c: true`, since every piece of this application is generated), the firmware is a strict superset of `hello_world`: it prints the same greeting, then drives a five-phase offload sequence — load payload, configure entry, start, wait, collect — on each target, and only emits the end-of-transmission character after **every** target has passed. A failed phase is reported on the UART and the firmware parks without EOT, so the testbench timeout turns it into an explicit regression failure.

A component qualifies as an **offload target** when both halves of its boot contract exist:

*   the isle wrapper declares the `Offload*` localparam contract — the IP-internal half: the register layout behind its slave window, the core count and the payload ISA/ABI (see `docs/hw/isle_standardization.md`);
*   its SoC-side half matches the contract kind: a `control_wire` target needs `system_config` with `fetch_enable: true` and `has_eoc_status: true` (plus `isolate: true` where the domain resets isolated — the generated helpers then open the fence first), while a `memory_mapped` target needs only its slave window.

When a target's component type sits under a `clk_rst_control` auto control group (so its instances power on gated), the generated helpers ungate the whole group before the first slave-window access; the same happens for the payload memory's group, before the payload load.

A `memory_mapped` component whose placement is a **box** (an instance array) is driven as an array: the helpers address each instance through its own window (base plus index times `size_per_instance`), the firmware configures and wakes **every** instance before polling any — a genuinely parallel launch — and the checksum is verified per instance. A single-instance target is simply the N = 1 case of the same code.

The resolved target list is printed at generation time (`[INFO] Offload test targets ...`) and again by the firmware itself on the UART (`[OFFLOAD] Targets: ...`), so both the generation log and every simulation transcript record what was actually tested.

What gets generated: per-target helper functions built on the PeakRDL headers (`<project>_offload.h` — no hand-written register address anywhere), a generic payload cross-compiled per target for the ISA/ABI its contract declares, a payload linker script pinned to a **dedicated quarter of the boot memory** (the host image and its stack stay below it; the region deliberately avoids the aliased non-interleaved view that dyn_mem-based memories expose in their upper window half), and the `bin2header.py` embedder that turns each payload into a C header of the host firmware. The payload runs a small deterministic workload staged through the target's local memory and returns a whitened checksum the host compares against the expected value.

The boot-memory carve is not universally **fetchable**: on the mesh examples the boot image lives in a narrow-network scratchpad, while the snitch instruction caches refill through the clusters' wide master — a payload there could be written but never executed. `test_app.payload_memory` names the component whose (instance-0) window hosts the payload instead; the host image and stack then keep the whole boot memory. Two cache-coherence caveats travel with this application on Cheshire-class hosts: the CVA6 CIE/LLC-out windows must leave the targets' slave windows **uncached** (the firmware polls its return slots through them — a cached poll spins on a stale line forever), and the payload region itself may be cached, because the generated loader publishes it with `fence.i`. The mesh examples document the working calibrations (`Cva6ExtCieLength`/`Cva6ExtCieOnTop`, and `LlcOutRegionStart/End` for maps living above `0x8000_0000`).

Two command-line overrides avoid editing the YAML during bring-up and debug, following the usual rule that the command line wins over the description file:

```
make generate TEST_APP=hello_world             # run the plain greeting on an offload-configured project
make generate OFFLOAD_TARGETS="pulp_cluster"   # restrict the offload test to a subset
```

**Toolchain prerequisite**: the payloads are cross-compiled with the *host* toolchain, so it must provide the multilibs for every target ISA/ABI pair (e.g. `rv32im/ilp32` next to the host's `rv64`). Check with `riscv64-unknown-elf-gcc -print-multi-lib`; a toolchain built without multilib support fails at payload compile time.
---

## 6. What Happens When the Configuration Is Wrong

Ollivander refuses a configuration it cannot make sense of, rather than generating from the part it understood. Every check below runs before any file is written, so the report you get is the whole story and the output directory is left untouched.

### 6.1 An unknown field

Fields are matched exactly. A misspelling is reported with the path that leads to it, so a typo deep inside a nested block is as easy to find as one at the top:

```
Location : topology -> global_bus -> data_widht
Error    : Extra inputs are not permitted
```

This applies to every block described in this guide. It is the reason the guide is the authoritative list of what is accepted: **a field it does not mention is a field the generator refuses.** If you need one that does not exist, the generator has no code reading it, so accepting it would only postpone the surprise.

### 6.2 An unknown entry, or one of the wrong shape

The blocks whose contents are free-form dictionaries — `interfaces`, `system_config`, `features`, `placement`, `dedicated_clock_div`, `testbench`, `software_stack` — are checked entry by entry, at every level of nesting, and the closest accepted entry is suggested:

```
[l2_shared_memory] 'interfaces' does not accept the entry 'axi_slaves'. Did you mean 'axi_slave'?
[l2_shared_memory] 'interfaces'.axi_slave[0] does not accept the entry 'siez'. Did you mean 'size'?
'testbench'.preload_memories[0] does not accept the entry 'fil'. Did you mean 'file'?
```

Values are checked too, against the shape each entry expects:

```
[l2_shared_memory] 'interfaces'.axi_slave[0].size should be an integer, not str.
[l2_shared_memory] 'interfaces'.axi_master should be true or false, not str.
```

All the mismatches found are reported together, so a configuration with several mistakes takes one run to fix rather than one run each.

### 6.3 A name that refers to nothing

Some values name something else in the same file. Those references are resolved, and a name that matches no declaration stops generation — with the closest declared name when there is one, and the full list when there is not:

```
[hyperbus] clock_domain 'perifh' is not declared in clock_tree.domains. Did you mean 'periph'?
[software_stack] boot_memory 'l2_shared_memry' is not a component of this SoC. Did you mean 'l2_shared_memory'?
```

These references are resolved rather than trusted because of what they become: a component's `clock_domain` is used as the name of a signal in the generated top-level, so a domain that does not exist would yield a signal nobody declares — and SystemVerilog turns an undeclared identifier into an implicit wire, leaving the peripheral with a floating clock instead of an elaboration error.

### 6.4 A name that must match the hardware

`parameters` and the keys of `interrupts` are SystemVerilog names, and they are checked against the wrapper itself rather than against a list in the generator — a stricter test, and one that stays correct as an IP evolves:

```
[mailbox] Parameter 'NumMailboxez' is not supported by component 'mailbox_isle'.
[ERROR] Port 'mbox_irq_j_i' connected on instance 'i_pulp_cluster' does not exist in module definition.
```

The same mechanism refuses an attempt to override a parameter the wrapper declares as a fixed `localparam`, and reports when a value violates a constraint the hardware imposes.

### 6.5 An environment file that cannot be parsed

Environment files (see [the environment configuration guide](env_configuration_guide.md)) are optional to exist but not optional to parse. A YAML syntax error in one of them stops the generator, naming the file and the position the parser reports:

```
[ERROR] Cannot parse the project environment configuration 'my_project_env.yml':
while parsing a block mapping
  in "my_project_env.yml", line 2, column 3
expected <block end>, but found '<block mapping start>'
```

### 6.6 Two declarations that contradict each other

Some values are only meaningful together, and a check on each one separately cannot see the contradiction: both keys are legitimate, both are spelled correctly, and only their combination is wrong. The AXI-port-versus-network pair of section 3.1 is one case:

```
[crux_subsystem] declares 'axi_master' but noc_networks names no 'master' network for it to use.
[crux_subsystem] noc_networks lists a 'slave' network (['narrow']) but the component declares no 'axi_slave'.
```

The geometry checks are the other members of this class, since each of them reads a component declaration against the bus it is attached to:

*   a component whose fixed `localparam` address or data width differs from its bus is refused — no adaptation exists for those two, so the connection would silently truncate or pad every transfer;
*   a component's fixed AXI ID widths are checked **along the direction of travel**: what it emits may be narrower than the network (the tile zero-extends it) but never wider, and what it accepts must cover the network's output side — either violation would alias transactions, and is refused;
*   on a crossbar, a component whose asynchronous CDC port widths resolve differently from the bus side is refused: the flattened payload carries `2**LogDepth` FIFO slots, so a width difference is not a truncation at the top but a shift running through every packet after the first, corrupting all traffic across that boundary;
*   the ID and user widths a nested macro publishes are checked against the network it plugs into, with the three refusals described in "Network ID width" (section 2.2) and under `user_mapping` (section 2.3).

This class deserves its own attention because the checks of the previous sections cannot reach it: unknown keys, wrong shapes and dangling names are each detectable by looking at one place at a time, whereas a pair of coherent-looking declarations that disagree only shows up when the two are read together. The consequence, when it slips through, is a connection that elaborates and is wrong — a 64-bit master port injected on a 512-bit network, for instance.

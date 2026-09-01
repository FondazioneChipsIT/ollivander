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
simulation: ...          # 11. Simulator flags & options for power users (Optional)
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
*   `collectives`: Object, optional. The schema-exposed half of FlooNoC's collective feature set — see below.

**Collectives (`noc_settings.collectives`)**

FlooNoC's reduction channels are declared here, symmetrically and per channel: `narrow_reduction` carries integer ALU operations on the narrow routers, `wide_reduction` floating-point operations on the wide ones. Each channel takes `enable` (Boolean, **default false** for both — a NoC carries exactly the reduction hardware its description asks for), `rd_pipeline_depth` (default 5) and `cut_offload_intf` (default true). The two channels are independent: enabling one does not require the other.

```yaml
    collectives:
      wide_reduction: { enable: true, rd_pipeline_depth: 5, cut_offload_intf: true }
```

The depth and cut defaults mirror the FlooNoC RTL's own `RedDefaultCfg`, and the generator always writes both values into the FlooGen configuration explicitly. This is deliberate: FlooGen's model defaults (depth 0, no cut) disagree with the RTL's, so a bare `en_*_reduction: true` handed to FlooGen would build a combinational reduction path where the RTL's default is pipelined and cut. Through Ollivander, neither party's "default" is ever relied upon.

Multicast (`en_narrow_multicast`, `en_wide_multicast`) and the hardware barrier (`en_barrier`) are currently constants of the emission, always on; a component opts into being a multicast target through its `features: { multicast_target: true }` declaration.

Enabling `narrow_reduction` has consequences beyond the routers: every tile gains FlooNoC's integer offload ALU (`floo_alu_top`, 32-bit operations — the IP's current limit), and the multicast group's tiles gain a generated *collective stamper* between isle and chimney. No CPU store can drive per-transaction AXI user bits, so the stamper is how software issues a collective: writes into the generated windows are stamped with an opcode and the member mask, everything else passes through untouched, and the SoC-wide user width never changes. The FP (wide) reduction set stays confined to the compute tiles, the only place an FPU backs the offload interface.

Three properties of FlooNoC's reduction machinery shape what the generator emits, and each is enforced rather than documented-and-hoped:

*   **A merge node accepts at most two contributions.** A monolithic 2D member mask creates fold-join nodes that expect three (own injection plus both axes) and the reduction never completes, so a 2D group reduces in two dimension-ordered phases: every instance adds into its own COLUMN head, the heads then add along their row into the final slot. The stamper derives each writer's chain head from its own instance base, so no per-instance table exists; a group that is degenerate in one dimension collapses to a single phase automatically.
*   **The group's instances must form a power-of-two aligned box**, and its enumeration must be column-fastest: the member mask is a coordinate wildcard, and a set it cannot express exactly — or a grid whose address order does not match its geometry — is refused at generation with the offending mask in the message.
*   **Every windowed slot is aligned to the narrow beat.** The collective machinery consumes the beat at channel width (`LsbAnd` reduces data bit 0 of the whole beat, the integer ALU computes on the low word), so a 32-bit store at an offset not aligned to the beat lands in the high half and is silently reduced as garbage. Unaligned contract offsets are refused at generation.

Collective phases must not interleave toward one destination: two streams with different masks and the same destination can head-of-line block each other in a router's reduction join. The generated test firmware therefore confirms that a phase's result has landed — with an ordinary read, which does not reduce — before arming the next.

The generated offload test exercises the collectives wherever the hardware can carry them - the phase needs no switch of its own to appear. It has one to DISAPPEAR: `software_stack.test_app.collective_test: false` silences the firmware phase while leaving the emission untouched, for debugging or for a project that wants the hardware without the extra simulated milliseconds. The default is deliberately opt-OUT: collectives that ship enabled and never exercised are how this feature spent months looking healthy while being broken, so a project that skips the test states it in its own description.

One simulator caveat, handled for the user: QuestaSim's default optimizer mis-schedules `floo_reduction_sync` and the collective transport wedges with no diagnostic. Ollivander applies an order-safe rewrite of that module at fetch time (`scripts/patch_floo_reduction_sync.py`), so no simulation flag has to be special-cased; the analysis is in `docs/developer/wip/upstream_pr_candidates.md`.

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
|                       |         | clock-enable register generated below. Resets are always held at power-on. |

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

**The order of the two writes is part of the contract**, and it is not symmetric:

*   **Bringing a block up**: release the reset FIRST, then enable the clock. The reset release is what needs a clock edge to be seen cleanly by the block's flops, and the safest edge is the first one after the clock starts — so the reset must already be released when it arrives.
*   **Taking a block down**: gate the clock FIRST, then assert the reset. The assert is asynchronous and needs no edge, and with the clock already stopped no edge falls near the transition.

This ordering is what removed the need for a *clocked settling window* between the two writes: the generated `offload` application used to spin a fixed number of iterations between them, a number valid only for the clock ratio of the project it was measured on. The generated helpers (`<target>_enable()` / `<target>_disable()`, and their per-instance forms) implement the order, so firmware that uses them inherits it.

**The bit index inside a group register is the instance's position in the GROUP**, not in its own component: a group controlling two components of four instances each is eight bits wide, the first component taking bits 0-3 and the second bits 4-7. The order in which components are assigned is the order they appear in the SoC description, and that order is a **contract** — the generated `<TARGET>_SYS_CTRL_BIT_BASE` macro publishes each target's first bit so firmware never recomputes it. Until 2026-08-27 the index was the position inside the component, so a second component restarted from bit 0 and silently aliased onto the first.

#### `power_on_state`

This single setting drives the reset value of the **clock-enable** registers above, so the two mechanisms can never end up with opposite power-on behaviour.

*   **`"gated"` (default)**: `*_clk_en = 0` — every managed domain and every controlled tile comes up clock-gated. This is the safe hardware default and matches the behaviour of the gwaihir reference SoC. Software, or an external agent, must bring the blocks up before using them.
*   **`"enabled"`**: `*_clk_en = all ones` — the clocks run from power-on without any CSR write. Convenient during bring-up, at the cost of leaving every controlled block clocked from reset.

> **`*_rst` is not affected, in either setting: a software reset always powers on ASSERTED.** That is what carries the power-on reset into the controlled block — the register's own reset value, and nothing else. Before 2026-08-27 the reset value followed `power_on_state` too, and the tile compensated by ANDing the software reset with the synchronised POR; that combinational term downstream of two independently synchronised reset sources was the hazard, so the AND is gone and the register now holds the block by itself. The consequence for the user is that **`"enabled"` no longer means "fully running": one write to `*_rst` is still required**, and it must come before the clock is enabled (see the ordering note below).

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
    *   **`base_addr` and `size_per_instance` each accept a scalar or a list**, and a list carries exactly one value per instance, in instance order. A list is only meaningful where the component expands into several instances — a `placement.logical` box on a NoC mesh — and is refused elsewhere, because a crossbar component is always a single instance. The instance order is the generator's canonical one: placement items in declaration order, and within a box **x outer, y inner**; it is the order FlooGen's own address map uses, and it is a contract you may rely on. The four combinations describe different hardware:

        | `base_addr` | `size_per_instance` | Resulting layout                                                                 |
        | :---------- | :------------------ | :------------------------------------------------------------------------------- |
        | scalar      | scalar              | Contiguous, stride equal to the size. The default, and what every project without lists produces. |
        | scalar      | list                | Contiguous and **packed**: each instance starts where the previous one ended, so the stride varies and there are no holes. |
        | list        | scalar              | Placement given explicitly, depth uniform. Holes are allowed.                     |
        | list        | list                | Placement and depth independent — a uniform stride with alternating depths, where the shallow instances leave the rest of their slot unmapped. |

        The second row is the one worth reading twice: with one base and sizes `[2 MB, 1 MB, 2 MB, …]` the third instance lands at base + 3 MB, **not** on a 2 MB stride. If you want a uniform stride with alternating depths, state the bases too (fourth row). `soc_cfg_examples/noc/mesh.yml` is the worked example.

        Everything downstream follows the resolved windows rather than recomputing them: the address map, the RDL description, the generated SoC package, the firmware headers and FlooGen's configuration. Where an external format can only express a uniform stride — RDL's `name[N] @ base += stride` and FlooGen's `array:` — the array is **unrolled** into one declaration per instance. The region the host is allowed to reach spans from the lowest base to the end of the highest window, holes included: an upstream decoder cannot exclude a gap, and what happens to an address inside one is the component's own decode to answer.
*   `regbus_slave`: List of register regions. Same format as `axi_slave`, plus an `external` boolean flag. Setting `external: true` means the IP is physically outside the generated Top-Level (e.g., in the Padframe); Ollivander will NOT instantiate it, but will export its RegBus ports to the SoC I/O.
*   `llc_port`: List of memory regions. Point-to-point asynchronous AXI link to the Host.
*   `noc_networks` (NoC Only): Dictionary with `master` (list of networks, e.g. `["narrow"]`), `slave` (list of networks), and `noc_mode` (`"joined"` or `"dual"`). `"joined"` automatically instantiates a FlooNoC Join adapter to merge narrow and wide traffic into a single AXI port. `"dual"` requires the component to natively expose two separate AXI ports.
    *   An AXI port and the network it rides on are **two halves of one statement**: `axi_master` says the component has a master port, `noc_networks.master` says which network that port injects into. Declaring either half without the other is refused, in both directions and for both `master` and `slave`. Nothing can be inferred here — a 64-bit master port injected on the wide network instead of the narrow one is a silently malformed connection, not a detail the generator can guess.

> [!IMPORTANT]
> The entries above are the complete set: `interfaces` accepts nothing else, and neither do the nested address ranges. An unknown entry is refused by name, with the closest accepted one suggested, and a value of the wrong shape is refused too (`'interfaces'.axi_slave[0].size should be an integer, not str`). The two fields that accept a list say so in their refusal — `base_addr should be an integer, or a list with one integer per instance, not str` — and a list of the wrong length is refused separately, by section 7. The same holds for every block of this section, which makes this guide the authoritative list of what is accepted rather than a description of it.

### 3.2 System Configuration (`system_config`)
Wires the component to the central `system_controller`.
*   `isolate`: Boolean. Generates an **outbound** AXI isolation fence per instance, plus the control and status registers to drive it. Available in **both topologies** and on any component declaring `interfaces.axi_master` — a component without one is refused, since isolation acts on the master path and there would be nothing for the fence to sit on.
    *   **Direction.** The fence stops the component **injecting into the network**; it protects the network from the block, not the converse. Nothing prevents a transaction *arriving* at a block that is isolated or gated, and no such inbound fence exists in either topology: not addressing a parked block is a firmware responsibility. (Should an inbound fence ever be wanted, it would be a new function with its own name, not a widening of this flag.)
    *   **Registers.** `isolate_ctrl.<component>_isolate` and `isolate_status.<component>_isolated`, both **one bit per instance** and both powering on `isolate = all ones` — every instance comes out of reset isolated and must be released explicitly.
    *   **`isolated` means "drained OR in reset".** The status bit is the cell's own report that both channels reached the isolate state, so waiting on it is a real handshake rather than an echo of the control bit — but the cell's state registers reset *to* that state, so the bit also reads asserted while the block is held in reset. It is therefore meaningful to wait for isolation to be *released*, and misleading to read an asserted bit as proof that traffic was drained.
    *   **Which clock the fence runs on** depends on who owns it. Where the isle exposes `axi_isolate_i` / `axi_isolated_o` the cell lives inside the isle, on the **gated** clock, and cannot move until that clock runs; otherwise the generated tile instantiates the cell itself on the **always-on network clock**. De-isolating *after* enabling the clock is the order that works in both cases, and it is the order the generated helpers use.
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
| `preload_memories`          | List    | Memory regions to initialize with the firmware image.           |
| `boot_mode`                 | String  | How the testbench boots the host: `"force"` (default), `"jtag"`, `"slink"`, `"uart"`, or the autonomous `"spi_flash"` / `"i2c_eeprom"`. See section 4.1. |
| `preload_mode`              | String  | How the image reaches the memories: `"readmemh"` (default), `"jtag"` or `"slink"`. See section 4.2. |
| `preload_verify`            | Boolean | `jtag` preload only: re-read and compare the whole image (default `false`). See section 4.2. |
| `elf_max_section_bytes`     | Integer | Capacity of the static ELF section buffer (default 4 MiB). See section 4.2. |
| `bring_up`                  | String  | How much of a gated SoC the testbench powers up: `"all"` (default) or `"minimal"`. See section 4.3. |
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
*   `file`: String. The path to the compiled image (e.g., `generated/sw/hello_world.hex`, or the `.elf` when `image: elf`). `{test_app}` resolves at generation time to the firmware actually built.
*   `image`: String, optional. The image format: `"hex"` (default, the flat objcopy output) or `"elf"` — see section 4.2. `elf` requires an architected `preload_mode` (`jtag` or `slink`): the hierarchical `readmemh` path only understands the split per-bank hex files.

**Example (Crossbar):**
```yaml
testbench:
  preload_memories:
    - instance: "l2_shared_memory.sram_array"
      file: "generated/sw/hello_world.hex"
```

### 4.1 Boot modes: `force`, `jtag`, `slink`, `uart` and the autonomous pair `spi_flash` / `i2c_eeprom`

`boot_mode` selects how the generated testbench brings the SoC out of reset and starts the firmware. It is one of two independent axes: how the *image* reaches the memories is `preload_mode` (section 4.2), and the two compose — `jtag` boot with `readmemh` preload is a supported (and shipped) combination. The two autonomous modes are the exception: they take no preload at all (the image travels inside the boot device, see below).

*   `"force"` (the default) drives the host's boot-mode and scratch registers, and the system controller's clock-enable and reset registers, through hierarchical `force` statements. It is fast and needs nothing from the design, but it exercises no architectural path: silicon has no `force`.
Every generated testbench instantiates the verification IP (`components/tb/vip_ollivander_soc.sv`), which hosts all the bench's agents: the clock and reset drivers, the UART RX monitor (timed on the divisor the firmware actually programs), and the JTAG agent below. The testbench itself owns only the policy: input ties, memory preloads and the boot sequence.

*   `"jtag"` boots the SoC exactly the way silicon would, through an external JTAG debugger, and the testbench contains **no forces at all**. The VIP's JTAG agent (built on riscv-dbg's `jtag_test` driver stack) drives the SoC's `jtag_*` pins with the full sequence: TAP reset and IDCODE liveness check, debug-module activation, power-on bring-up of the gated domains via system-bus writes to the system controller (every `*_clk_en` register first, a settling pause, then every `*_rst` release), and finally the boot handoff to the host's scratch registers, with the entry pointer written read-back-verified. Any system-bus error (`sberror`) is fatal, not silent.

Requirements for `"jtag"`, both checked or supplied by the generator:

*   The host must list `"jtag"` in `export_interfaces`, otherwise its TAP pins never reach the SoC top-level. This is validated at generation time with an explicit error, because the failure mode is otherwise perfectly silent: every DMI read returns X, and X falls open through every liveness check a testbench agent can make.
*   The host component must declare the JTAG boot contract in its header: `HasJtagBoot`, `JtagIdCode` (the expected IDCODE) and `JtagScratchOffset` (the scratch-register offset inside the host's address window). `cheshire_isle` declares all three.

*   `"slink"` is the **self-sufficient serial-link boot**: no `jtag_init`, the TAP is never touched — bring-up of the gated domains, the image and the boot handoff all ride the serial link through the VIP's twin agent. It is the exact shape of the reference testbenches' serial-link branches (cheshire's and gwaihir's `PRELMODE=1`, which never initialize JTAG), and it models a chip that needs no debugger to boot. Requirements: the host builds and exports its serial link (`SerialLink: true` plus `"slink"` in `export_interfaces`) and `preload_mode: "slink"`; the JTAG export is deliberately **not** required. The host contract block (`HasJtagBoot`, `JtagScratchOffset`) is still consulted — the handoff needs the scratch offset — but no TAP pin is driven.

*   `"uart"` boots through the **bootrom's own serial debug server**: in the passive preboot loop the ROM listens on the UART alongside the scratch registers, and the VIP's uart-boot agent speaks its protocol — ACK challenge, block writes of the image, then an EXEC command that jumps the host straight to the entry (no scratch-register handoff exists on this road). It models the poorest external agent silicon can count on — no debugger, no link partner, one serial line — and it is a road **neither reference exercises in regression** (gwaihir's CI disabled it for cost on their mesh). The protocol runs at the baudrate **baked into the ROM** (115200 through the integer divisor), so the upload is pure simulated time: pair this mode with a small project (`crux_mini` is the fleet's representative, measured at ~146 us/s while the design idles on UART bits — about four wall-clock minutes for a hello-world boot), and keep `software_stack.baudrate` at 115200 — a firmware that immediately reprograms the divisor to a faster console corrupts the EXEC acknowledge still shifting out at the ROM's rate. Requirements: `"uart"` in `export_interfaces` and `preload_mode: "uart"`.

*   `"spi_flash"` and `"i2c_eeprom"` are the **autonomous boots**: nobody drives the chip at all. The testbench sets the `boot_mode_i` strap to the bootrom's own case value (from the host contract: `BootModeSpiFlash` / `BootModeI2cEeprom`), instantiates the behavioral device model the host contract names (`BootSpiFlashModel` / `BootI2cEepromModel` — the models ship with the host's own dependency graph), and waits for the end-of-test byte. The bootrom does everything a finished product would: it scans the device's GPT, loads the partition carrying the contract's ZSL type GUID into the host's **internal scratchpad** (`BootSpmOffset`/`BootSpmSize`), and jumps there. Two consequences follow. First, the firmware is **linked for the scratchpad**, not for the project's boot memory — the generated linker script switches base and size automatically. Second, the image is not a flat hex but a **GPT disk image**: the generated software Makefile builds `<app>.gpt.bin` / `.gpt.memh` with the exact upstream recipe (truncate + `sgdisk` + `dd`, geometry from the host contract's `BootImgPayloadLba`/`BootImgPadLbas`), and the testbench hands it to the device model — through the model's own preload parameter for the flash (its initial block blank-fills the array, so any external `$readmemh` would lose a time-zero race), through a testbench-side fill-and-load for the EEPROM (that model never initializes its array). Requirements: `"spi"` (respectively `"i2c"`) in `export_interfaces`, the matching peripheral built (`SpiHost: true` with `SpihNumCs` covering the contract's `BootSpiFlashCs`; `I2c: true`), and **no** `preload_mode`/`preload_memories` — both validated at generation time. Measured on the mini class (`crux_micro` is the fleet's shipped witness): the SPI-flash boot reaches end-of-test at 4.86 ms simulated (63 s of wall clock), the I2C-EEPROM boot at 24.0 ms simulated (3 m 41 s) — both per-commit-gate territory on a SoC this small. Expect the EEPROM run to log sporadic advisory `$width` timing-check messages (see the testbench guide, section 4.4).

The `jtag` boot composes with the `slink` *preload* into a hybrid the references do not have: the TAP liveness check (`jtag_init`: IDCODE, dmactive, SBA readiness) still runs, keeping the debug path under per-project regression, while every write rides the link. Choose the hybrid when the chip exports JTAG anyway (the liveness comes free); choose `slink` boot for reference parity or when modeling a debugger-less bring-up.

Among the example projects, four run `boot_mode: "jtag"` (`crossbar`, `noc`, `noc_isle`, `super_crossbar` — the last two as the hybrid with `preload_mode: slink`), `super_noc` runs the self-sufficient `"slink"` boot, `crux_mini` runs the `"uart"` debug boot, `crux_micro` runs the autonomous `"spi_flash"` boot (its `"i2c_eeprom"` twin is a one-line flip, pilot-verified at 24 ms simulated), and `crossbar_isle` and `noc_subtile` deliberately stay on `"force"`: it is the schema default and a supported feature, and it would lose regression coverage if no example exercised it. Every boot mode has at least one fleet witness.

### 4.2 Preload modes: `readmemh`, `jtag`, `slink` and `uart`

`preload_mode` selects the road the compiled image takes into the `preload_memories` regions.

*   `"readmemh"` (the default) injects the hex files through hierarchical `$readmemh` into the physical SRAM arrays — simulation-only, fast, and the reason interleaved memories need their image pre-split per bank. The dotted paths it (and its AXI monitors) plant into the DUT keep the preloaded module out of Verilator's hierarchical blocks.
*   `"jtag"` streams the *flat* hex through the debug module's System Bus Access, from inside the JTAG boot sequence: one `sba_load` call per `preload_memories` entry, its base address resolved by the generator from the component's `axi_slave` interface, autoincrement addressing, 64-bit beats where the debug module declares them, and one sticky-error check per stream. Interleaving happens in the SoC's own decoder hardware, and the identical sequence would work against silicon. Because no dotted path reaches the DUT, the preload target stays eligible as a Verilator hierarchical block — the practical reason to choose this mode. It requires `boot_mode: "jtag"` (validated at generation time: the system bus only exists once the debug module is up).
*   `"slink"` loads at AXI speed through the host's serial link: the VIP instantiates an off-chip twin of the host's own `serial_link` instance (same register package, so framing agrees by construction) and drives the image as AXI write bursts — 1 KiB each, cheshire upstream's own practice — through the DDR pins. In this mode *everything* rides the link: the gated-domain bring-up writes, the image, and the boot handoff, because with the serial link built into the host (`SerialLink: true`, required and validated together with the `slink` export) the debug module's SBA writes into the host's internal register path complete with an OKAY but never land — an upstream anomaly under investigation; the link's external AXI ingress reaches the same registers reliably. It requires an architected `boot_mode` — `"jtag"` (the hybrid: TAP liveness check, link transport) or `"slink"` (self-sufficient, section 4.1) — because only those arm the passive preboot loop the handoff writes into. Like `jtag`, no dotted path reaches the DUT, so every preload target stays eligible for Verilator's hierarchical blocks — on `noc_isle` this releases all eight L2 tiles at once.

*   `"uart"` streams the image through the debug server's block writes (256-byte bursts, each acknowledged and closed by the protocol's own EOT byte). Available under `boot_mode: "uart"` only — the server is what that boot sequence challenges — and like the other architected roads it plants no dotted path in the DUT.

With `preload_verify: true` the testbench re-reads the whole image through the same channel (`sbreadondata` streaming) and compares word by word, failing fatally on the first mismatch. It costs ~2.8x the plain load's simulated time, so the intended use is one verifying configuration in the regression fleet rather than every project. It is implemented for `jtag` only.

**ELF images.** With `image: elf` on a preload region, the testbench reads the file through the vendored cheshire `elfloader` DPI (`components/tb/elfloader.cpp`, compiled unconditionally by both simulator flows) and streams **every loadable segment** through whichever transport the project configured — the loaders never learn the source format. Two things change with respect to a hex image: the **entry point comes from the ELF header at runtime** instead of the generator's map-derived literal (with a multi-segment ELF the linker owns that truth), and the sections pass through a **static staging buffer** whose capacity is the `elf_max_section_bytes` knob (default 4 MiB) — static because Verilator cannot yet pass dynamic arrays to DPI open arrays. A segment larger than the buffer stops the run with a fatal that names the knob; nothing is streamed partially. The first section's address is checked against the configured region's base with a loud message (not a fatal): an ELF may legitimately scatter loadable segments across several memories, which is precisely its advantage over the flat hex.

Among the examples the two axes compose into a deliberate coverage matrix: `crossbar_isle` and `noc_subtile` stay on `readmemh` (the schema default), `mesh` runs `jtag`+hex and `crux` runs `jtag`+ELF, the serial-link trio runs `slink` — `super_noc` and `super_crux` with hex, `noc_isle` with ELF — and `crux_mini` runs `uart`+hex.

### 4.3 `bring_up`: how much of the SoC the testbench powers up

`bring_up` decides how many of the gated clock domains and control groups the generated testbench enables before handing control to the firmware. It applies to `boot_mode: "jtag"` only - the force path has no per-phase story - and it splits one job across two owners.

*   `"all"` (the default) enables every managed domain and every auto control group during bring-up. The firmware finds the whole SoC awake, which is what a hello-world test wants.
*   `"minimal"` enables only the boot-critical set: the domains and groups whose component type matches the boot memory. Everything else stays gated, and the **firmware** ungates each block when it needs it - the generated `offload` application already does, calling `<target>_enable()` before using a target and `<target>_disable()` after (see section 5.1). The result is closer to how a real chip runs: a domain is powered only while it is in use, and the power-down path gets exercised by the test itself instead of being dead code.

Measured on the `noc` example, `"minimal"` cut the simulated run from 11m55s to 9m30s under QuestaSim, because the idle clusters no longer consume simulator cycles while the host boots. The saving grows with the number of gated blocks the test does not touch.

---

## 5. Software Stack (`software_stack`)

Defines the parameters for automated bare-metal C firmware generation and compilation. Ollivander uses these settings to dynamically construct a **Linker Script** (`link.ld`) that aligns exactly with the physical memory map defined in the `components` section, preventing hard-to-debug memory faults.

| Field         | Type   | Description                                                                         |
| :------------ | :----- | :---------------------------------------------------------------------------------- |
| `toolchain`   | String | The GCC toolchain prefix (e.g., `"riscv64-unknown-elf-"`). Compiler flags (ISA, ABI, Code Model) are defined under the `host` block. |
| `boot_memory` | String | **Required**. The `name` of the memory component (from the `components` list) where |
|               |        | the boot`.text`, `.data`, and `.bss` sections will be placed. Ollivander will       |
|               |        | automatically fetch its `base_addr` and `size` — of its **first instance**, when the |
|               |        | component declares per-instance lists. The name must resolve to a declared          |
|               |        | component: a value that names nothing stops generation, suggesting the closest one.  |
|               |        | Naming the **host** selects its own internal scratchpad instead — see below.         |
| `test_app`    | Object | Configuration for the automatically generated test application.                     |

**Test App Object**:
*   `name`: String. The base name used for the output files (`<name>.elf`, `<name>.hex`). Two names select a **generated application** rather than just naming the artifacts: `hello_world` (the default UART greeting) and `offload` (see below). Any other name simply labels a `main.c` you provide yourself.
*   `auto_generate_c`: Boolean. If `true`, Ollivander creates a starter `main.c` file. This file automatically `#include`s the generated hardware headers (e.g., `<project>_map.h` and `<project>_regs.h`) so you have immediate access to all peripheral base addresses, IRQs, and PeakRDL generated CSR macros.
*   `baudrate`: Integer, optional (default `115200`). The UART rate the generated firmware programs. The generator converts it into the 16550 divisor and times the testbench's UART monitor on that **same divisor**, so the two sides cannot disagree — the divisor is an integer, and at high rates the true line rate differs from the nominal value by a few percent. Raising it is the single largest lever on simulation wall-clock time, because at 115200 a character costs ~87 µs of simulated time and the UART dominates a hello-world run: at `2000000` (divisor 3) the shipped examples close about **11× sooner**, which under Verilator turns an hour-long run into minutes. The examples ship with this value; lower it back to `115200` (or omit the key) when the firmware must drive a physical terminal.
*   `offload_targets`: List of component names, optional and meaningful only with `name: "offload"`. Restricts the offload test to a subset of the offload-capable components; by default every capable component is tested. A name that is not offload-capable stops generation with the reason — never a silent skip.
*   `payload_memory`: Component name, optional and meaningful only with `name: "offload"`. Hosts the shared payload region at the base of that component's (instance-0) window instead of carving it out of the boot memory — required when the boot memory is not fetchable by every target (see section 5.1).

**Booting from the host's internal scratchpad.** Setting `boot_memory` to the **host's own name** links the firmware for the scratchpad the host keeps inside itself, located by its contract (`BootSpmOffset`/`BootSpmSize`, standardization section 5.4) rather than by any window of the SoC map. The point is that this memory is **always on**: nothing external has to be powered, ungated and mapped before the first fetch, so a SoC can boot without depending on the testbench to bring a gated tile up — which is why `noc_isle` uses it, while `super_noc` keeps the boot-image-in-a-gated-L2 path under regression.

Three things follow from what that memory actually is — on a cheshire-class host, the last-level cache with its ways switched to scratchpad duty:

*   **It requires an architected `preload_mode`** (`jtag`, `slink` or `uart`). Those write by address and the cache dispatches; a `readmemh` would need a hierarchical path into the cache's way arrays, addressed through the IP's own way/set mapping, and is refused at generation time rather than half-supported.
*   **It does not exist at reset.** The host's bootrom creates it — it waits for the cache's built-in self test, then switches every way to scratchpad. The generated testbench therefore *waits for that fact* before loading, polling the register the host contract names (`BootSpmReadyOffs`/`Mask`) over the same transport the preload uses, and printing `host scratchpad ready after N poll(s)`. An agent that loaded immediately after reset would get a bus error, which is exactly what the first implementation did.
*   **It is small** (64 KiB on cheshire, and its size is contract knowledge). With the `offload` app it also forces `payload_memory` to be declared: the scratchpad sits inside the host, and on a NoC the clusters refill their instruction caches through a different network, so the payload must live in a memory they can reach.

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

*   the isle wrapper declares the `Offload*` localparam contract — the IP-internal half: the register layout behind its slave window, the core count and the payload ISA/ABI (see `docs/hw/component_standardization.md`);
*   its SoC-side half matches the contract kind: a `control_wire` target needs `system_config` with `fetch_enable: true` and `has_eoc_status: true` (plus `isolate: true` where the domain resets isolated — the generated helpers then open the fence first), while a `memory_mapped` target needs only its slave window.

When a target's component type sits under a `clk_rst_control` auto control group (so its instances power on gated), the generated helpers ungate the whole group before the first slave-window access; the same happens for the payload memory's group, before the payload load.

With `bring_up: minimal` (section 4.3) that ungating is no longer redundant but load-bearing: the testbench leaves everything but the boot path gated, so the firmware's `<target>_enable()` is what makes a target reachable at all. Symmetrically, the generated application calls `<target>_disable()` at the end of each phase - isolate the target and wait for the isolation status, then assert its reset and drop its clock enable, in that order, so no transaction is cut mid-flight. The pair therefore tests the full power cycle of every target, not only its wake-up.

A `memory_mapped` component whose placement is a **box** (an instance array) is driven as an array: the helpers address each instance through its own **resolved** window, the firmware configures and wakes **every** instance before polling any — a genuinely parallel launch — and the checksum is verified per instance. With scalar fields that window is base plus index times `size_per_instance`; with a list on either field it is whatever the layout in section 3.1 assigns, and the firmware reads the resolved value rather than recomputing the product. A single-instance target is simply the N = 1 case of the same code.

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

## 6. Simulation Flags & Options (`simulation`)

An optional section for users who know the simulators and want direct control over the generated flows. Everyone else should omit it: the defaults are exactly what the test suite validates, and an absent section produces the same Makefiles as a section spelling the defaults out.

Three rules govern every field. **Values are raw** - what you write is what the tool receives, with no translation layer that would have to track the tools' own option sets. **A field either APPENDS to a structural set or REPLACES a default, and each is marked below** - the extras and the guard lists (`suppress`, `warnings`, `flist_exclude`, `bender_targets`) append, so a guard can be extended from here but not removed; `plusargs`, the `firmware` flag lists and `run_do` replace their defaults, so the defaults can be dropped on purpose (writing `plusargs: ["+foo"]` loses `+fast_boot`). **Everything lands only in the generated Makefiles** - a project exported as a macro does not carry its `simulation` section to the parent, whose own section (or defaults) always wins.

Appending is not a cage. Every derived list lives in one `?=` Makefile variable, so the command line replaces it wholesale for a single run (`make run-sim QUESTA_RUN_SUPPRESS=3009,8386` un-suppresses 13314 for that run); Verilator warnings need no override at all, because the tool's own negation appends - `warnings: ["-Wwarn-TIMESCALEMOD"]` re-enables a structurally suppressed warning, last flag wins. What has no YAML escape by design are the structural file-list exclusions: they are load-bearing (removing them breaks the build), and a structural entry that turns out wrong for a project is a generator defect to report, not something to work around silently.

What Ollivander owns stays out of this section on purpose: the structural flags of each flow (`--cc --main --hierarchical --timing`, timescales, the hierarchical parameters file), the sets derived from the design (bender targets from the dependency registry, `+define+` from component `DEFINE:` pragmas, the hierarchical block set), and coupled pairs - `verilator.threads` is the visible half of one, and the generator emits or drops the `-DVL_TIME_CONTEXT` that must travel with `--threads` (both directions were measured to crash when mixed).

```yaml
simulation:
  assertions: false             # renders ASSERTIONS ?= 0 (QuestaSim -nosva set). The
                                # Verilator flow is structurally assertion-free either way.
  plusargs: ["+fast_boot"]      # run plusargs of BOTH simulators. REPLACES the
                                # default (["+fast_boot"]): list it to keep it
  bender_targets: ["my_feat"]   # extra -t on both dependency resolutions
  firmware:
    cflags: ["-O2", "-g3"]      # replaces the host application's default -g -O0 tail
    ldflags: ["-Wl,-Map=fw.map"]
    cluster_cflags: ["-O3"]     # replaces the offload payload's default -O2 -g

  questa:
    vlog: ["+cover"]            # extra --vlog-arg values at compile-script generation
    vsim: ["-sv_seed", "1234"]  # extra args of the batch run
    gui: ["-assertdebug"]       # extra args of the GUI run only
    run_do: "run 100us; quit"   # REPLACES the batch -do script. The one non-additive
                                # field: you own the whole sequence, and forgetting
                                # 'quit' leaves a batch suite waiting forever.
    suppress: [9999]            # message numbers ADDED to every derived -suppress list
                                # (compile driver, elaboration, run, fast-check)
    waveform:
      enable: true              # batch runs elaborate with +acc, log to $(TOP_MOD).wlf
      scope: "tb_mesh/dut"      # subtree to log; empty logs the whole design. Costly:
                                # +acc lowers vopt optimization exactly like the GUI.

  verilator:
    threads: 4                  # value of --threads; 0 and 1 both mean "no threading"
                                # (Verilator's own --threads 1 builds the threaded
                                # scheduler, which is the broken half on this flow)
    verilate_jobs: 32           # -j of the emission phase. Capped by default: -j48
                                # produced truncated generated C++ (see the Makefile note)
    compile_jobs: 32            # -j of the compile phase, safe to raise independently
    bender_targets: ["vl_only"] # extra -t of the Verilator file list only
    flist_exclude: ["my_ip/bad_file\\.sv"]  # regexes ADDED to the structural exclusions
    verilate: ["--trace-depth", "3"]        # raw extras on the verilation command line
    warnings: ["-Wno-WIDTH"]    # ADDED to the shared warning list (build AND fast-check)
    compile: ["OPT_FAST=-O3"]   # raw make assignments of the C++ compile phase
    run: ["+verilator+seed+42"] # raw args appended to the built executable
    keep_work: false            # 1 keeps verilator_work across builds (warm rebuilds)
```

The example above is illustrative and mixes defaults with non-defaults. The authoritative per-field behaviour:

| Field | Behaviour | Default when omitted / structural base it appends to |
| --- | --- | --- |
| `assertions` | replaces | `true` (renders `ASSERTIONS ?= 1`; `false` renders `0`) |
| `plusargs` | **replaces** | `["+fast_boot"]` - list it again to keep it |
| `bender_targets` | appends | base: the resolved dependency-registry targets (`BENDER_TARGETS`) |
| `firmware.cflags` | **replaces** | `-g -O0` (the tail after the derived `-march/-mabi/-mcmodel/-f*-sections`) |
| `firmware.ldflags` | appends | base: `-T linker.ld -nostartfiles -Wl,--gc-sections` |
| `firmware.cluster_cflags` | **replaces** | `-O2 -g` (the offload payload's tail) |
| `questa.vlog` | appends | base: `--vlog-arg="-timescale 1ns/1ps"` |
| `questa.vsim` | appends | base: none (empty) |
| `questa.gui` | appends | base: `-voptargs=+acc` |
| `questa.run_do` | **replaces** | `run -all; quit` (with `waveform.enable`: prefixed by `log -r ...; `) |
| `questa.suppress` | appends | bases per context: compile `13233`, elaboration `13314,13233`, run `13314,3009,8386` |
| `questa.waveform.enable` | replaces | `false` |
| `questa.waveform.scope` | replaces | empty = log the whole design (`log -r /*`) |
| `verilator.threads` | replaces | `4`; values 0 and 1 drop `--threads` AND `-DVL_TIME_CONTEXT` together |
| `verilator.verilate_jobs` | replaces | `32` (the emission-truncation cap - see the Makefile note) |
| `verilator.compile_jobs` | replaces | `32` |
| `verilator.bender_targets` | appends | base: `-t verilator -t cv32e40p_exclude_tracer -t scm_use_latch_scm` (on top of `BENDER_TARGETS`) |
| `verilator.flist_exclude` | appends | base: `behavioral/tc_pad\.sv\|common_verification/src/rand_verif_pkg\.sv` |
| `verilator.verilate` | appends | base: the structural verilation flags (see `VERILATOR_SIM_FLAGS`) |
| `verilator.warnings` | appends | base: `-Wno-fatal -Wno-TIMESCALEMOD -Wno-ASCRANGE -Wno-SYMRSVDWORD -Wno-ENUMVALUE` |
| `verilator.compile` | appends | base: `CFG_CXXFLAGS_STD=-std=gnu++20` (make assignments of the C++ phase) |
| `verilator.run` | appends | base: the common `plusargs` |
| `verilator.keep_work` | replaces | `false` (the work directory is wiped before every build) |

There is no `verilator.waveform`: under the hierarchical flow a dump needs a generated main that owns it, and a flag here would ship a segfault - the analysis and the reference implementation are tracked in the developer notes. For waveforms today, use the QuestaSim flow (`make gui`, or `questa.waveform` for batch runs).

The test suite validates the **defaults**, not user-composed combinations: a configuration built from these fields is yours to validate, and the first check is always the same - the run still prints its `[UART]` output and the testbench's EOT line.

---

## 7. What Happens When the Configuration Is Wrong

Ollivander refuses a configuration it cannot make sense of, rather than generating from the part it understood. Every check below runs before any file is written, so the report you get is the whole story and the output directory is left untouched.

### 7.1 An unknown field

Fields are matched exactly. A misspelling is reported with the path that leads to it, so a typo deep inside a nested block is as easy to find as one at the top:

```
Location : topology -> global_bus -> data_widht
Error    : Extra inputs are not permitted
```

This applies to every block described in this guide. It is the reason the guide is the authoritative list of what is accepted: **a field it does not mention is a field the generator refuses.** If you need one that does not exist, the generator has no code reading it, so accepting it would only postpone the surprise.

### 7.2 An unknown entry, or one of the wrong shape

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

### 7.3 A name that refers to nothing

Some values name something else in the same file. Those references are resolved, and a name that matches no declaration stops generation — with the closest declared name when there is one, and the full list when there is not:

```
[hyperbus] clock_domain 'perifh' is not declared in clock_tree.domains. Did you mean 'periph'?
[software_stack] boot_memory 'l2_shared_memry' is not a component of this SoC. Did you mean 'l2_shared_memory'?
```

These references are resolved rather than trusted because of what they become: a component's `clock_domain` is used as the name of a signal in the generated top-level, so a domain that does not exist would yield a signal nobody declares — and SystemVerilog turns an undeclared identifier into an implicit wire, leaving the peripheral with a floating clock instead of an elaboration error.

### 7.4 A name that must match the hardware

`parameters` and the keys of `interrupts` are SystemVerilog names, and they are checked against the wrapper itself rather than against a list in the generator — a stricter test, and one that stays correct as an IP evolves:

```
[mailbox] Parameter 'NumMailboxez' is not supported by component 'mailbox_isle'.
[ERROR] Port 'mbox_irq_j_i' connected on instance 'i_pulp_cluster' does not exist in module definition.
```

The same mechanism refuses an attempt to override a parameter the wrapper declares as a fixed `localparam`, and reports when a value violates a constraint the hardware imposes.

### 7.5 An environment file that cannot be parsed

Environment files (see [the environment configuration guide](env_configuration_guide.md)) are optional to exist but not optional to parse. A YAML syntax error in one of them stops the generator, naming the file and the position the parser reports:

```
[ERROR] Cannot parse the project environment configuration 'my_project_env.yml':
while parsing a block mapping
  in "my_project_env.yml", line 2, column 3
expected <block end>, but found '<block mapping start>'
```

### 7.6 Two declarations that contradict each other

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

### 7.7 A per-instance list that does not match the instance count

`base_addr` and `size_per_instance` accept a list carrying one value per instance (section 3.1), so their length is a statement about the hardware and is checked against it. The check is keyed to the **instance count**, not to the topology: a list is meaningful wherever a component expands into several instances, and keying it to `topology.type` would bake in a coupling that may change.

```
[l2_shared_memory] 'interfaces'.axi_slave[0].size_per_instance declares 6 values but the component
expands into 8 instances; a list must carry exactly one value per instance, in instance order.
```

The single-instance case is worth its own wording, because it is the mistake someone will actually make — copying a NoC component into a crossbar project, where the same declaration is suddenly one instance:

```
[l2_shared_memory] 'interfaces'.axi_slave[0].base_addr declares 4 values but the component expands
into 1 instance; a list applies to components that expand into several, through a
'placement.logical' box on a NoC mesh.
```

Both are refused before anything is written, like every other check in this chapter. The values themselves are resolved once, immediately after validation, so that every later step — address map, RDL, SoC package, firmware, FlooGen — reads the same windows instead of each deriving its own.

### 7.8 Isolation asked for where there is nothing to isolate

`system_config.isolate` places an **outbound** fence on the component's master path (section 3.2), so a component that declares no `interfaces.axi_master` is asking for something no topology can build.

```
Component 'l2_shared_memory' declares system_config.isolate but has no 'axi_master' interface.
Isolation acts on the OUTBOUND path (it protects the network from the block, not the converse),
so there is nothing for the fence to sit on. Declare interfaces.axi_master, or drop the isolate
flag.
```

The request is refused rather than ignored because ignoring it is not inert: the control and status registers are generated from the flag alone, so the status bit would be left without a driver — reading `X` in simulation, and telling a firmware that waits on it that the block is *not* isolated, forever. The failure would then surface as a boot that hangs, hours away from the line that caused it.


### 7.9 An interrupt wire without a driver, and an interrupt index beyond the port

Two checks close the class SafeConnect's findings belonged to (2026-08-29). First, **every consumed interrupt wire must have a driver** in the generated top: an `intr_*` wire that is read but never driven elaborates perfectly and reads zero forever — the CAN event spent months routed to a PLIC bit that could not fire, because the exported `can_bus` interface had claimed the port and the interrupt lost. (Both roles are now honoured: the port drives the interrupt wire, and the exported top-level signal is fed from it by an assignment.) Second, **an index into the host's `intr_ext_o` beyond `NumIntrsOut` is refused**: the line would be constant by configuration. The outbound-target count itself is no longer assumed but **derived** — `NumIntrTgtsOut` becomes 1 whenever the description routes from that port, which is what keeps cheshire out of its tie-off branch.
# Ollivander Unified Component Model: The "Tile" Standardization

## 1. Overview
In the Ollivander SoC Generator configured for a Network-on-Chip (NoC) topology, hardware components can be integrated either as standard IP wrappers (**Subtiles**) or as fully custom NoC nodes (**Tiles**).

*   **Subtiles (`*_subtile.sv`)**: Standard IPs exposing only AXI/RegBus interfaces. Ollivander automatically wraps them, instantiating the FlooNoC Router and Chimneys.
*   **Custom Tiles (`*_tile.sv`)**: Highly coupled components where the user provides a handwritten wrapper that *manually instantiates* the `floo_nw_router` or connects directly to the 2D NoC mesh. 

Custom Tiles are required for specialized NoC nodes, such as:
1.  **Dummy Tiles** (`dummy_tile.sv`): Empty routing nodes used to bridge physical distances in the mesh floorplan.
2.  **Custom Offload Nodes**: Tiles that manipulate custom NoC packets (e.g., multicast or reductions) directly at the router level without going through standard AXI Chimneys.
3.  **Third-Party Pre-Packaged Tiles**: IPs that already include a FlooNoC-compatible router inside their top-level RTL.

This document provides the definitive guide for hardware designers creating **Custom Tiles**.

---

## 2. Mandatory NoC Boundary Interfaces
Because a Custom Tile is instantiated directly within the NoC 2D mesh array by the `noc_soc_top.sv.mako` template, it **MUST** expose the exact FlooNoC routing interfaces in all four cardinal directions (`[West:North]`).

The following ports are mandatory and strictly checked by the generator:

```systemverilog
import floo_pkg::*;
// Note: You should also import your project-specific NoC package 
// (e.g., floo_gwaihir_noc_pkg::*) to get the correct struct definitions.

// Narrow Network
output floo_req_t  [West:North] floo_req_o,
input  floo_rsp_t  [West:North] floo_rsp_i,
input  floo_req_t  [West:North] floo_req_i,
output floo_rsp_t  [West:North] floo_rsp_o,

// Wide Network (Required even if internally tied to zero)
output floo_wide_t [West:North] floo_wide_o,
input  floo_wide_t [West:North] floo_wide_i
```

---

## 3. Autonomous System Signals
Just like Isles and Subtiles, Custom Tiles receive system signals automatically wired by Ollivander based on the YAML configuration.

### Mandatory Signals
*   **`clk_i`** (`logic`): Main clock input, wired to the clock domain assigned in the YAML.
*   **`rst_ni`** (`logic`): Main reset input (active low), wired to the reset domain assigned in the YAML.
*   **`test_mode_i`** (`logic`): DFT/Scan-chain bypass enable flag.
*   **`id_i`** (`id_t`): The physical X/Y coordinate ID assigned to this Tile by the mesh generator. Essential for the internal router to know its position.

### Optional Clock/Reset Control (Auto Control Groups)
If the Tile is subject to an `auto_control_group` in the System Controller, it can optionally receive the following signals to implement local clock gating and reset isolation:
*   **`tile_clk_en_i`** (`logic`): Software-controlled clock enable.
*   **`tile_rst_ni`** (`logic`): Software-controlled reset (active low).
*   **`clk_rst_bypass_i`** (`logic`): Hardware override to bypass clock gating and software resets during test modes.

### Optional Interconnect Signals
*   **`sys_clk_i`** / **`sys_rst_ni`**: Global system clock and reset (`host_clk`).
*   **`rt_clk_i`**: Real-Time Clock domain.

---

## 4. Custom I/O and Interrupts
Custom Tiles support the same generic port export and interrupt routing mechanisms as standard Isles.

Any port listed in the `export_interfaces` YAML list (e.g., `uart`, `jtag`, `gpio`) or mapped in the `interrupts` dictionary will be automatically extracted from the Tile's SystemVerilog header and routed to the SoC top-level or the appropriate destination component.

> **⚠️ STRICT NAMING ENFORCEMENT**
> The naming conventions for standard interfaces are **strictly enforced**. No deviations, custom prefixes, or alternative spellings (e.g., using `bootmode` instead of `boot_mode`) are permitted. 
> The primary purpose of the wrapper is to adapt the inner IP's arbitrary port names to match the exact Ollivander standard. Failure to expose these exact names at the boundary will result in unconnected wires and architectural validation errors.

---

## 5. Parameter Interface (`parameter` vs `localparam`)
Ollivander dynamically parses the Tile's header to map parameters from the YAML:

*   **`parameter` (Configurable):** Ollivander will override these at instantiation time based on the YAML configuration.
*   **`localparam` (Fixed Constraint):** Hardcoded IP constraints. Ollivander will strictly validate that the global YAML configuration does not violate them.

### 5.1 NoC Struct Parameter Types (Strict Type Equivalence for Portability)
Because Custom Tiles natively interact with the NoC router, the quickest integration method is to hardcode the import of the local NoC package (e.g., `import floo_gwaihir_noc_pkg::*;`) inside the wrapper to access the `floo_req_t` and `id_t` structs.

However, if you are designing a **truly reusable** Custom Tile meant to be instantiated across different SoCs (or exported within different Macros), hardcoding the package will cause strict type equivalence errors during compilation. To make the Custom Tile fully portable, you should expose the NoC structs as `parameter type` in the module header:
*   `floo_req_t`, `floo_rsp_t`, `floo_wide_t`
*   `id_t`
*   `sam_rule_t` (if handling address mapping directly)

*(Note: Because Ollivander currently auto-injects AXI types but not NoC types into Custom Tiles, you must explicitly map these NoC types in the `parameters` block of your YAML configuration if you choose to parameterize them).*

*Note: Because Custom Tiles natively instantiate the NoC router, they must often rely on the auto-generated NoC configuration package (e.g., `AxiCfgN`, `AxiCfgW`, `RouteCfg`) provided by FlooGen, rather than relying solely on scalar parameters.*

---

## 6. Dependency Management
Ollivander features an automated dependency resolution engine that scans your Tiles to populate the `Bender.yml` manifest. This ensures that only the files and IP packages actually instantiated in the SoC are included in the compilation flow.

### Static Dependencies (SystemVerilog Files)
For standard `.sv` files, declare dependencies using special comments anywhere in the file (typically at the top):

*   **Bender Packages**: Use `// BENDER: name="<package_name>"` to link an external repository. Ollivander will look up the git URL and version in the `ollivander_config.yml` registry.
    ```systemverilog
    // BENDER: name="axi"
    // BENDER: name="floo_noc"
    ```

*   **Local Infrastructure Files**: Use `// OLLIVANDER: require="<filename.sv>"` to include a local file from the `components/` directories. Ollivander will automatically locate it and add its relative path to the manifest.
    ```systemverilog
    // OLLIVANDER: require="tc_clk_gating.sv"
    ```

### Dynamic Dependencies (Mako Templates)
If your Custom Tile is dynamically generated (a `.sv.mako` file), avoid hardcoding dependency comments if the underlying hardware instantiation is conditional.

Instead, use the injected Python functions to dynamically register dependencies *only if* the Mako condition is met.

```mako
% if has_clk_ctrl:
  ${require_file("tc_clk_gating.sv")}
  tc_clk_gating i_tc_clk_gating ( ... );
% endif

% if enable_axi:
  ${require_bender("axi")}
% endif
```
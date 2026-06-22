# Ollivander Unified Component Model: The "Subtile" Standardization

## 1. Overview
In the Ollivander SoC Generator configured for a Network-on-Chip (NoC) topology, hardware components (memories, peripherals, and hosts) can be provided by the user in two ways:

1.  **Custom Tiles (`*_tile.sv`)**: Highly coupled components where the user manually instantiates the FlooNoC router to manipulate custom NoC packets (e.g., multicast or reductions).
2.  **Subtiles (`*_subtile.sv`)**: Standardized IP wrappers. The user provides pure AXI/RegBus interfaces. Ollivander automatically generates the enclosing `*_tile.sv` wrapper, instantiating the FlooNoC Router, Chimneys, Bus Joins, and (if applicable) the Central System Controller.

**Cross-Topology Reusability (`_isle` vs `_subtile`)**:
To maximize IP reuse, Ollivander establishes a strict hierarchical naming convention:
*   **`*_isle.sv` (Topology-Agnostic)**: Uses standard single-network AXI/RegBus ports. Can be instantiated safely in both Crossbar and NoC topologies. In a NoC, Ollivander automatically generates a Tile wrapper for it.
*   **`*_subtile.sv` (NoC-Specific)**: Designed natively for NoC topologies (e.g., uses `noc_mode: "dual"` to expose physically separate narrow and wide AXI networks). **Cannot** be used in a Crossbar topology. Ollivander will reject it during validation if attempted.

This document provides the definitive guide for hardware designers creating **Subtiles**.

---

## 2. Parameter Interface (`parameter` vs `localparam`)
Every Subtile MUST expose a standardized set of parameters to define bus geometries and microarchitectural behaviors. 
Ollivander's parser (`sv_parser.py`) actively scans the module header:

*   **`parameter` (Configurable):** Ollivander will dynamically override these at instantiation time in the generated Tile wrapper based on the YAML configuration.
*   **`localparam` (Fixed Constraint):** Hardcoded IP constraints (e.g., a memory that strictly requires a 64-bit data bus). Ollivander will strictly validate that the global YAML configuration does not violate them.

### 2.1 Expected Bus Geometries
These parameters define the physical width of the AXI lines. 
If the Subtile connects to multiple independent NoC networks simultaneously (e.g., `noc_mode: "dual"` in YAML), the parameters MUST be prefixed with `AxiNarrow...` or `AxiWide...`.

*   **Standard / Joined Mode:**
    *   `AxiAddrWidth`, `AxiDataWidth`, `AxiUserWidth`
    *   `AxiInIdWidth` / `AxiOutIdWidth`
*   **Dual Mode (Dual-Network Subtiles):**
    *   `AxiNarrowDataWidth`, `AxiWideDataWidth`
    *   `AxiNarrowUserWidth`, `AxiWideUserWidth`
    *   `AxiNarrowInIdWidth`, `AxiWideInIdWidth` (and equivalent `OutIdWidth` for masters)
    *   *(Note: `AxiAddrWidth` is assumed global for the SoC, but `AxiNarrowAddrWidth` is supported).*

### 2.2 Clock Domain Crossing (CDC) Widths
Since most Subtiles reside in independent clock domains, they expose pre-calculated widths for the asynchronous AXI channels to avoid complex `$clog2` macros in the top-level.
*   `LogDepth`: Log2 depth of the CDC FIFOs.
*   `AsyncAxiInAwWidth`, `AsyncAxiInWWidth`, `AsyncAxiInBWidth`, `AsyncAxiInArWidth`, `AsyncAxiInRWidth`
*   `AsyncAxiOutAwWidth`, `AsyncAxiOutWWidth`, `AsyncAxiOutBWidth`, `AsyncAxiOutArWidth`, `AsyncAxiOutRWidth`

### 2.3 System Microarchitecture
To guarantee system-wide coherence without tight coupling to a specific system package, Subtiles use the dynamic project package (e.g., `gwaihir_soc_pkg`) as their default value source for system properties:
*   `AxiMaxReadTxns` / `AxiMaxWriteTxns`: Depth of outstanding transactions.
*   `AxiUserAmoMsb` / `AxiUserAmoLsb`: Bit mapping for Atomic Memory Operation (AMO) reservation IDs.
*   `AxiUserEccErrBit`: Bit mapping for the ECC error flag within the `user` field.

### 2.4 AXI Struct Parameter Types (Strict Type Equivalence)
To avoid strict type equivalence errors, Subtiles should expose their AXI structs as `parameter type` in the module header.
*   **Standard / Joined Mode:**
    *   `axi_req_t`, `axi_resp_t`
*   **Dual Mode:**
    *   `axi_narrow_req_t`, `axi_narrow_resp_t`
    *   `axi_wide_req_t`, `axi_wide_resp_t`

Ollivander will automatically inject the appropriate network types from the local NoC package when instantiating the Subtile.

---

## 3. Supported Interfaces & Port Naming
Subtiles abstract away the native interfaces of their underlying IPs. Ollivander automatically maps these interfaces during Tile generation if they match the exact naming conventions below.
The expected naming convention depends strictly on the **`noc_mode`** and **`sync_domain`** fields defined in the YAML configuration.

> **⚠️ STRICT NAMING ENFORCEMENT**
> The naming conventions defined below are **strictly enforced**. No deviations, custom prefixes, or alternative spellings (e.g., using `spih_` instead of `spi_`, or `bootmode` instead of `boot_mode`) are permitted. 
> The primary purpose of the Subtile wrapper is to adapt the inner IP's arbitrary port names to match this exact Ollivander standard. Failure to expose these exact names at the Subtile boundary will result in unconnected wires and architectural validation errors.

### 3.1 AXI Slave (`axi_slave` in YAML)
Subtiles receiving requests from the NoC.

**A) Default or Joined Mode (`noc_mode: "joined"`, Synchronous):**
Used when the IP connects to a single network, or when Ollivander is instructed to instantiate a Hardware Join to merge multiple networks into one.
*   **`axi_req_i`** (`axi_pkg::axi_req_t` or equivalent struct)
*   **`axi_resp_o`** (`axi_pkg::axi_resp_t` or equivalent struct)

**B) Dual Mode (`noc_mode: "dual"`, Synchronous):**
Used for "Smart" IPs (like compute clusters) that natively handle multiple networks. Ollivander directly connects these to the NoC Chimney.
*   **`axi_narrow_req_i`** / **`axi_narrow_resp_o`**
*   **`axi_wide_req_i`** / **`axi_wide_resp_o`**

**C) Asynchronous Mode (`sync_domain: false`):**
Used when the IP resides in a different clock domain. Ollivander instantiates CDC (Clock Domain Crossing) FIFOs.
*   **`async_axi_in_aw_data_i`** (`logic [AsyncAxiInAwWidth-1:0]`)
*   **`async_axi_in_aw_wptr_i`** (`logic [LogDepth:0]`)
*   **`async_axi_in_aw_rptr_o`** (`logic [LogDepth:0]`)
*   *(... applies to w, b, ar, r channels. If `noc_mode: "dual"`, prefix with `async_axi_narrow_in_...` and `async_axi_wide_in_...`)*

### 3.2 AXI Master (`axi_master` in YAML)
Subtiles sending requests into the NoC (e.g., DMA engines).

**A) Default or Joined Mode (Synchronous):**
*   **`axi_req_o`**
*   **`axi_resp_i`**

**B) Dual Mode (Synchronous):**
*   **`axi_narrow_req_o`** / **`axi_narrow_resp_i`**
*   **`axi_wide_req_o`** / **`axi_wide_resp_i`**

**C) Asynchronous Mode:**
*   **`async_axi_out_aw_data_o`**
*   **`async_axi_out_aw_wptr_o`**
*   **`async_axi_out_aw_rptr_i`**
*   *(... applies to all channels)*

### 3.3 RegBus Slave (`regbus_slave`)
Standard narrow-bus (32-bit) used for configuration registers.

**Asynchronous:**
*   `reg_async_slv_req_i`, `reg_async_slv_ack_o`, `reg_async_slv_data_i`
*   `reg_async_slv_req_o`, `reg_async_slv_ack_i`, `reg_async_slv_data_o`

**Synchronous:**
*   `reg_req_i` (`reg_intf_pkg::reg_req_t`)
*   `reg_rsp_o` (`reg_intf_pkg::reg_rsp_t`)

### 3.4 Common Peripherals (Exported to SoC Top-Level)
All peripheral ports are passed through the generated Tile and exposed as top-level SoC I/O pins.
*   **JTAG**: `jtag_tck_i`, `jtag_trst_ni`, `jtag_tms_i`, `jtag_tdi_i`, `jtag_tdo_o`, `jtag_tdo_oe_o`
*   **UART**: `uart_tx_o`, `uart_rx_i`
*   **SPI Host**: `spi_sck_o`, `spi_sck_en_o`, `spi_csb_o`, `spi_csb_en_o`, `spi_sd_o`, `spi_sd_en_o`, `spi_sd_i`
*   **I2C**: `i2c_sda_o`, `i2c_sda_i`, `i2c_sda_en_o`, `i2c_scl_o`, `i2c_scl_i`, `i2c_scl_en_o`

---

## 4. Autonomous System Signals
Ollivander automatically wires up specific system/control signals if it finds them in your Subtile's header. You do not need to specify these in the YAML `interfaces` list.

### Mandatory Signals
*   **`clk_i`** (`logic`): Main clock input, wired to the clock domain assigned in the YAML.
*   **`rst_ni`** (`logic`): Main reset input (active low), wired to the reset domain assigned in the YAML.

### Optional Signals
*   **`pwr_on_rst_ni`** (`logic`): Power-On Reset (active low).
*   **`sys_clk_i`** / **`sys_rst_ni`**: Global system clock and reset (`host_clk`).
*   **`rt_clk_i`**: Real-Time Clock domain (usually 32.768 kHz).
*   **`test_mode_i`**: DFT/Scan-chain bypass enable flag.
*   **`boot_mode_i`**: System boot mode strapping pins.

---

## 5. The Host Subtile Exception (Hierarchy Flattening)

The Host component (e.g., `cheshire_subtile.sv`) is treated specially by Ollivander to avoid unnecessary hierarchy levels.

When a Subtile is defined as the `host` in the YAML configuration, Ollivander generates a `*_tile.sv` wrapper that does **four** things:

1.  Instantiates the **FlooNoC Router**.
2.  Instantiates the **Chimneys** to convert the Host's AXI traffic to NoC packets.
3.  Instantiates the **Host Subtile** itself.
4.  Instantiates the **System Controller (`_reg_top`)**.

### 5.1 RegBus Orchestration
The Host Subtile must act as the RegBus master for the entire SoC. It should expose multi-dimensional arrays for the RegBus:

*   `reg_req_o` (`sync_reg_out_req_t [RegNumSlvSync-1:0]`)
*   `reg_rsp_i` (`sync_reg_out_rsp_t [RegNumSlvSync-1:0]`)
*   *(And corresponding `reg_async_mst_*` arrays for asynchronous slaves).*

**The Flattening Mechanism:**
Inside the generated Tile wrapper, Ollivander intercepts the **lowest index** of the synchronous RegBus (`reg_req_o[0]`) and routes it directly to the locally instantiated System Controller (`_reg_top`). 
The remaining RegBus array slices (`[RegNumSlvSync-1:1]`) are routed out of the Tile and up to the SoC Top-Level, where they are distributed to the other Subtiles/Tiles in the system.

### 5.2 Auto-Calculated Host Parameters
Ollivander automatically calculates and injects the following parameters into the Host Subtile. The user should not define them in the YAML `parameters` block:

*   **`AxiNumMstSync` / `AxiNumMstAsync`**: Number of external AXI masters injecting traffic into the Host.
*   **`AxiNumSlvSync` / `AxiNumSlvAsync`**: Number of external AXI slaves receiving traffic from the Host.
*   **`RegNumSlvSync` / `RegNumSlvAsync`**: Total number of RegBus slaves in the system (including the System Controller).
*   **`NumIntrsIn` / `NumIntrsOut` / `NumIrqHarts` / `NumDbgHarts`**: Sizes for the interrupt vectors based on the YAML routing matrix.

---

## 6. Dependency Management

Ollivander features an automated dependency resolution engine that scans your Subtiles (and their generated Tile wrappers) to populate the `Bender.yml` manifest. This ensures that only the files and IP packages actually instantiated in the SoC are included in the compilation flow.

### 6.1 Static Dependencies (SystemVerilog Files)
For standard `.sv` files, declare dependencies using special comments anywhere in the file (typically at the top):

*   **Bender Packages**: Use `// BENDER: name="<package_name>"` to link an external repository. Ollivander will look up the git URL and version in the `ollivander_config.yaml` registry.
    ```systemverilog
    // BENDER: name="axi"
    // BENDER: name="floo_noc"
    ```

*   **Local Infrastructure Files**: Use `// OLLIVANDER: require="<filename.sv>"` to include a local file from the `components/` directories. Ollivander will automatically locate it and add its relative path to the manifest.
    ```systemverilog
    // OLLIVANDER: require="tc_clk_gating.sv"
    ```

### 6.2 Dynamic Dependencies (Mako Templates)
If your Subtile is dynamically generated (a `.sv.mako` file), avoid hardcoding dependency comments if the underlying hardware instantiation is conditional.

Instead, use the injected Python functions to dynamically register dependencies *only if* the Mako condition is met. These functions will automatically print the correct `// OLLIVANDER:` or `// BENDER:` tag into the generated `.sv` file and register it in the manifest.

```mako
% if has_clk_ctrl:
  ${require_file("tc_clk_gating.sv")}
  tc_clk_gating i_tc_clk_gating ( ... );
% endif

% if enable_axi:
  ${require_bender("axi")}
% endif
```
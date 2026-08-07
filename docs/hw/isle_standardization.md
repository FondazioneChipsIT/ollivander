# Ollivander Unified Component Model: The "Isle" Standardization

## 1. Overview
In the Ollivander SoC Generator, all hardware components (clusters, memories, peripherals, and hosts) must be encapsulated within standardized SystemVerilog wrappers referred to as **Isles** (e.g., `pulp_cluster_isle.sv`, `l2_isle.sv`).

The purpose of the Isle is to provide a **uniform, generator-friendly interface** that decouples the complexity and the specific dialects of individual IPs from the Python generator logic. Python only sees standard parameters and standard ports, allowing it to seamlessly stitch together complex SoCs (either Crossbar-based or NoC-based) without embedding IP-specific SystemVerilog code.

**Cross-Topology Reusability (`_isle` vs `_subtile`)**: To maximize IP reuse, Ollivander establishes a strict hierarchical naming convention:
*   **`*_isle.sv` (Topology-Agnostic)**: Uses standard single-network AXI/RegBus ports. Can be instantiated safely in both Crossbar and NoC topologies. In a NoC, Ollivander automatically generates a Tile wrapper for it.
*   **`*_subtile.sv` (NoC-Specific)**: Designed natively for NoC topologies (e.g., uses `noc_mode: "dual"` to expose physically separate narrow and wide AXI networks). **Cannot** be used in a Crossbar topology. (See the [Subtile standardization guide](subtile_standardization.md) for details).

This document provides the definitive guide for hardware designers looking to integrate a Topology-Agnostic component or a custom Host into the Ollivander ecosystem.

---

## 2. Parameter Interface (`parameter` vs `localparam`)
Every Isle MUST expose a standardized set of parameters to define bus geometries and microarchitectural behaviors. Ollivander's parser (`sv_parser.py`) actively scans the module header and treats `parameter` and `localparam` differently:

*   **`parameter` (Configurable):** Use this for values that the IP can adapt to dynamically. Ollivander will override these at instantiation time in the top-level based on the YAML configuration.
*   **`localparam` (Fixed Constraint):** Use this in the module header for values that **cannot** be changed (e.g., a hardware IP that strictly requires a 64-bit data bus). Ollivander will add these to a `fixed_params` list, skip them during parameter assignment in the top-level, and **strictly validate** that the global YAML configuration does not violate them. If a violation occurs, the generator halts with an architectural error.

### 2.1 Expected Bus Geometries
These parameters define the physical width of the AXI lines, and the generator drives each from the geometry of the interconnect the Isle is attached to. *(Note: Isles support only a single, unified AXI network. For dual-network NoC IPs, see Subtiles).*
*   `AxiAddrWidth`, `AxiDataWidth`, `AxiUserWidth`: taken from the `global_bus` declaration (crossbar) or from the network (NoC).
*   `AxiInIdWidth`: Width of the AXI ID for incoming requests (required if `axi_slave` is used). Driven with the interconnect's **slave-side** ID width — in a crossbar that is not a `global_bus` field but a computed value, the manager ID width plus the arbitration bits for the number of managers, so it grows when components are added.
*   `AxiOutIdWidth`: Width of the AXI ID for outgoing requests (required if `axi_master` is used). Driven with the manager-side ID width (`mst_id_width`, or the network's input width in a NoC).

Declaring one of these as a `localparam` instead states a geometry the Isle cannot depart from, and switches it from *driven* to *verified*: address and data widths must then equal the bus exactly, and the ID widths are checked along the direction of travel — see the same contract in the [Subtile standardization guide, section 2.1](subtile_standardization.md#21-expected-bus-geometries), which applies unchanged.

### 2.2 Clock Domain Crossing (CDC) Widths
Since most Isles reside in independent clock domains, they expose pre-calculated widths for the asynchronous AXI channels. This prevents the generator from having to compute complex SystemVerilog `$clog2` macros in the top-level.
*   `LogDepth`: Log2 depth of the CDC FIFOs.
*   `AsyncAxiInAwWidth`, `AsyncAxiInWWidth`, `AsyncAxiInBWidth`, `AsyncAxiInArWidth`, `AsyncAxiInRWidth`
*   `AsyncAxiOutAwWidth`, `AsyncAxiOutWWidth`, `AsyncAxiOutBWidth`, `AsyncAxiOutArWidth`, `AsyncAxiOutRWidth`

### 2.3 System Microarchitecture
To guarantee system-wide coherence without introducing tight coupling to a specific Host package (e.g., Cheshire's `Cfg` struct), Isles use the `ollivander_soc_pkg` as their default value source for system properties:
*   `AxiMaxReadTxns` / `AxiMaxWriteTxns`: Depth of outstanding transactions.
*   `AxiUserAmoMsb` / `AxiUserAmoLsb`: Bit mapping for Atomic Memory Operation (AMO) reservation IDs within the `user` field.
*   `AxiUserEccErrBit`: Bit mapping for the ECC error flag within the `user` field.
*   `AxiAmoNumCuts`: Number of pipeline registers in the AXI ATOP adapters.

### 2.4 AXI Struct Parameter Types (Strict Type Equivalence)
SystemVerilog enforces strict type equivalence for structs. To avoid compilation errors when instantiating Isles in different SoCs (or when exporting an entire SoC as a Macro IP), Isles should expose their AXI structs as `parameter type` in the module header, rather than hardcoding a specific package.
*   `axi_req_t`: Synchronous AXI request type for slave interfaces.
*   `axi_resp_t`: Synchronous AXI response type for slave interfaces.
*   `axi_master_req_t`: Synchronous AXI request type for master interfaces.
*   `axi_master_resp_t`: Synchronous AXI response type for master interfaces.
*   `axi_aw_chan_t`, `axi_w_chan_t`, `axi_b_chan_t`, `axi_ar_chan_t`, `axi_r_chan_t`: Asynchronous channel types (optional, if the IP supports CDC internally).

Ollivander will automatically inject the local SoC package types (e.g., `my_soc_pkg::soc_axi_req_t`) when instantiating the Isle.

In a **NoC**, the types injected are those of the network the port rides on, chosen per direction: the master pair takes the network's input types, the slave pair its output types (or the joined type, where a Join adapter merges the two networks). Exposing the pairs as `parameter type` is therefore what lets an Isle carry the ID and user widths of whatever network it is placed in, and `AxiOutIdWidth` is set to the network's input width for the same reason.

An Isle that instead types its AXI ports from its own IP package — legitimate for a hand-written wrapper around an IP whose widths are fixed, as the snitch cluster subtile does — keeps them, and the tile adapts around it: the ID is zero-extended to the network width on the way out and truncated back on the response, field-wise, so that only `id` is touched. Nothing is lost either way, but the two cases must not be mixed by hand: whether the port types were injected is what decides which of the two the generator applies.

The package name follows the **top-level module name**, not the bare project name, so it carries the same suffix that `build_mode: "macro"` adds. A project `crux` built standalone produces `crux_soc_pkg`, while the same project built as a macro with `export_type: "isle"` produces `crux_isle_soc_pkg`. This is what allows both builds of a project — and a parent SoC that instantiates one of them — to be compiled into a single simulation library without the two packages colliding under the same name.

### 2.5 Memory Mapping Parameters
For topology-agnostic memory wrappers (e.g., L2 memory wrapper `l2_isle.sv`), the wrapper should expose standard configurable parameters defining its size and base address:
*   `L2BaseAddr` (`parameter logic [63:0]`): Base address of the memory mapping range. Defaults to a standard constant (e.g., `64'h88000000`).
*   `L2MemSize` (`parameter int unsigned`): Size of the memory block in bytes. Defaults to a standard constant (e.g., `32'h00200000` / 2 MB).

These parameters are dynamically overridden at instantiation time by the generator based on the YAML configuration interfaces mapping, ensuring that the local address decoding and interleaving rules computed within the Isle scale correctly.

The same mechanism serves compute components that decode part of their own slave region internally:

*   `ClusterBaseAddr` (`parameter logic [63:0]`): base of the SoC region mapped to the component, driven from the `base_addr` of the first `axi_slave` entry. `pulp_cluster_isle` exposes it to align the cluster's internal decode (TCDM, peripherals, external escape) with the region the SoC description maps it at — an internal decode left at the IP default would silently route every external access to the wrong rule.

Like every entry of the standard parameter vocabulary, these are matched **by parameter name, per instance**: each component that exposes the parameter receives the base of its own `axi_slave` mapping, so a design may instantiate any number of such components, each decoding its own region. When the SoC is built as a macro (`build_mode: "macro"`), both `L2BaseAddr` and `ClusterBaseAddr` are emitted as `MACRO_BASE_ADDR + <base>`, so the decode relocates with the macro wherever the parent maps it.

---

## 3. Supported Interfaces & Port Naming
Isles abstract away the native interfaces of their underlying IPs. Ollivander automatically maps these interfaces during generation if they are declared in the YAML and match the exact naming conventions below.

> **⚠️ STRICT NAMING ENFORCEMENT** The naming conventions defined below are **strictly enforced**. No deviations, custom prefixes, or alternative spellings (e.g., using `spih_` instead of `spi_`, or `bootmode` instead of `boot_mode`) are permitted. The primary purpose of the Isle wrapper is to adapt the inner IP's arbitrary port names to match this exact Ollivander standard. Failure to expose these exact names at the Isle boundary will result in unconnected wires and architectural validation errors.

**Dimensionality (Scalars vs. Arrays) & Direction:** 
*   **Standard Components**: Typically expose flat vectors (a single connection). However, if a component defines multiple interfaces of the same type in the YAML (e.g., `ports: 2` for a dual-port `l2_shared_memory`), its ports MUST be packed into arrays indexed by the port number (e.g., `logic [NumPort-1:0][AsyncAxiInAwWidth-1:0] async_axi_in_aw_data_i`).
*   **Host Component**: Because the Host Isle contains the central routing crossbar, its AXI and RegBus ports are complementary to standard components and *always* exposed as multi-dimensional arrays (e.g., `[AxiNumMst-1:0][Width-1:0]`) to aggregate all system traffic.
*   **Direction**: When a component acts as a slave, the Host acts as a master, and vice versa.

### 3.1 AXI Slave (`axi_slave`)
Depending on the `sync_domain` YAML flag, an Isle can receive AXI requests either synchronously or asynchronously.

**Asynchronous (Default, requires CDC):**
*   `async_axi_in_aw_data_i` (`logic [AsyncAxiInAwWidth-1:0]`): Write address channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_aw_data`. Host -> Array connected to `xbar_mst_aw_data`.
*   `async_axi_in_aw_wptr_i` (`logic [LogDepth:0]`): Write address channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_aw_wptr`. Host -> Array connected to `xbar_mst_aw_wptr`.
*   `async_axi_in_aw_rptr_o` (`logic [LogDepth:0]`): Write address channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_aw_rptr`. Host -> Array connected to `xbar_mst_aw_rptr`.
*   `async_axi_in_w_data_i` (`logic [AsyncAxiInWWidth-1:0]`): Write data channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_w_data`. Host -> Array connected to `xbar_mst_w_data`.
*   `async_axi_in_w_wptr_i` (`logic [LogDepth:0]`): Write data channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_w_wptr`. Host -> Array connected to `xbar_mst_w_wptr`.
*   `async_axi_in_w_rptr_o` (`logic [LogDepth:0]`): Write data channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_w_rptr`. Host -> Array connected to `xbar_mst_w_rptr`.
*   `async_axi_in_b_data_o` (`logic [AsyncAxiInBWidth-1:0]`): Write response channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_b_data`. Host -> Array connected to `xbar_mst_b_data`.
*   `async_axi_in_b_wptr_o` (`logic [LogDepth:0]`): Write response channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_b_wptr`. Host -> Array connected to `xbar_mst_b_wptr`.
*   `async_axi_in_b_rptr_i` (`logic [LogDepth:0]`): Write response channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_b_rptr`. Host -> Array connected to `xbar_mst_b_rptr`.
*   `async_axi_in_ar_data_i` (`logic [AsyncAxiInArWidth-1:0]`): Read address channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_ar_data`. Host -> Array connected to `xbar_mst_ar_data`.
*   `async_axi_in_ar_wptr_i` (`logic [LogDepth:0]`): Read address channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_ar_wptr`. Host -> Array connected to `xbar_mst_ar_wptr`.
*   `async_axi_in_ar_rptr_o` (`logic [LogDepth:0]`): Read address channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_ar_rptr`. Host -> Array connected to `xbar_mst_ar_rptr`.
*   `async_axi_in_r_data_o` (`logic [AsyncAxiInRWidth-1:0]`): Read data channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_r_data`. Host -> Array connected to `xbar_mst_r_data`.
*   `async_axi_in_r_wptr_o` (`logic [LogDepth:0]`): Read data channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_r_wptr`. Host -> Array connected to `xbar_mst_r_wptr`.
*   `async_axi_in_r_rptr_i` (`logic [LogDepth:0]`): Read data channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_slv_r_rptr`. Host -> Array connected to `xbar_mst_r_rptr`.

**Synchronous:**
*   `axi_req_i` (`axi_req_t`): Synchronous AXI request struct.
    *   **Ollivander Handling**: Component -> Connected to `xbar_sync_slv_req`. Host -> Array connected to `xbar_sync_mst_req`.
*   `axi_resp_o` (`axi_resp_t`): Synchronous AXI response struct.
    *   **Ollivander Handling**: Component -> Connected to `xbar_sync_slv_rsp`. Host -> Array connected to `xbar_sync_mst_rsp`.

### 3.2 AXI Master (`axi_master`)
**Asynchronous:**
*   `async_axi_out_aw_data_o` (`logic [AsyncAxiOutAwWidth-1:0]`): Write address channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_aw_data`. Host -> Array connected to `xbar_slv_aw_data`.
*   `async_axi_out_aw_wptr_o` (`logic [LogDepth:0]`): Write address channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_aw_wptr`. Host -> Array connected to `xbar_slv_aw_wptr`.
*   `async_axi_out_aw_rptr_i` (`logic [LogDepth:0]`): Write address channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_aw_rptr`. Host -> Array connected to `xbar_slv_aw_rptr`.
*   `async_axi_out_w_data_o` (`logic [AsyncAxiOutWWidth-1:0]`): Write data channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_w_data`. Host -> Array connected to `xbar_slv_w_data`.
*   `async_axi_out_w_wptr_o` (`logic [LogDepth:0]`): Write data channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_w_wptr`. Host -> Array connected to `xbar_slv_w_wptr`.
*   `async_axi_out_w_rptr_i` (`logic [LogDepth:0]`): Write data channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_w_rptr`. Host -> Array connected to `xbar_slv_w_rptr`.
*   `async_axi_out_b_data_i` (`logic [AsyncAxiOutBWidth-1:0]`): Write response channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_b_data`. Host -> Array connected to `xbar_slv_b_data`.
*   `async_axi_out_b_wptr_i` (`logic [LogDepth:0]`): Write response channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_b_wptr`. Host -> Array connected to `xbar_slv_b_wptr`.
*   `async_axi_out_b_rptr_o` (`logic [LogDepth:0]`): Write response channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_b_rptr`. Host -> Array connected to `xbar_slv_b_rptr`.
*   `async_axi_out_ar_data_o` (`logic [AsyncAxiOutArWidth-1:0]`): Read address channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_ar_data`. Host -> Array connected to `xbar_slv_ar_data`.
*   `async_axi_out_ar_wptr_o` (`logic [LogDepth:0]`): Read address channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_ar_wptr`. Host -> Array connected to `xbar_slv_ar_wptr`.
*   `async_axi_out_ar_rptr_i` (`logic [LogDepth:0]`): Read address channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_ar_rptr`. Host -> Array connected to `xbar_slv_ar_rptr`.
*   `async_axi_out_r_data_i` (`logic [AsyncAxiOutRWidth-1:0]`): Read data channel data payload.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_r_data`. Host -> Array connected to `xbar_slv_r_data`.
*   `async_axi_out_r_wptr_i` (`logic [LogDepth:0]`): Read data channel CDC write pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_r_wptr`. Host -> Array connected to `xbar_slv_r_wptr`.
*   `async_axi_out_r_rptr_o` (`logic [LogDepth:0]`): Read data channel CDC read pointer.
    *   **Ollivander Handling**: Component -> Connected to `xbar_mst_r_rptr`. Host -> Array connected to `xbar_slv_r_rptr`.

**Synchronous:**
*   `axi_req_o` (`axi_master_req_t`): Synchronous AXI request struct.
    *   **Ollivander Handling**: Component -> Connected to `xbar_sync_mst_req`. Host -> Array connected to `xbar_sync_slv_req`.
*   `axi_resp_i` (`axi_master_resp_t`): Synchronous AXI response struct.
    *   **Ollivander Handling**: Component -> Connected to `xbar_sync_mst_rsp`. Host -> Array connected to `xbar_sync_slv_rsp`.

### 3.3 Dedicated LLC Port (`llc_port`)
Certain Hosts (like Cheshire) expose a dedicated asynchronous AXI Master port intended specifically to route high-bandwidth traffic directly to an external memory controller (e.g., HyperBus), bypassing the main system crossbar entirely.

**Host Side (Master):**
*   `async_axi_llc_aw_data_o` (`logic [AsyncAxiLlcAwWidth-1:0]`): Write address channel data payload.
*   `async_axi_llc_aw_wptr_o` (`logic [LogDepth:0]`): Write address channel CDC write pointer.
*   `async_axi_llc_aw_rptr_i` (`logic [LogDepth:0]`): Write address channel CDC read pointer.
*   *(... and all other standard AXI channels following the `async_axi_llc_*` prefix)*
*   `async_axi_llc_isolate_i` / `async_axi_llc_isolated_o`: Dedicated isolation fence for the LLC domain.

**Peripheral Side (Slave):** Components marked with the `llc_port` interface in the YAML (e.g., `hyperbus_isle`) simply expose the standard asynchronous AXI Slave ports (`async_axi_in_*`).
*   **Ollivander Handling**: The generator automatically creates direct point-to-point wires between the Host's `async_axi_llc_*` master ports and the peripheral's `async_axi_in_*` slave ports, creating a private high-speed link.

### 3.4 RegBus Slave (`regbus_slave`)
Standard narrow-bus (32-bit) used for configuration registers.

**Asynchronous (`sync_domain: false`):**
*   `reg_async_slv_req_i` (`logic`): Asynchronous register request valid signal.
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_req_out` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_req_i`.
*   `reg_async_slv_ack_o` (`logic`): Asynchronous register request acknowledge.
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_ack_in` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_ack_o`.
*   `reg_async_slv_data_i` (`reg_intf_pkg::reg_req_t`): Register request payload (address, data, write flag).
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_data_out` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_data_i`.
*   `reg_async_slv_req_o` (`logic`): Asynchronous register response valid signal.
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_req_in` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_req_o`.
*   `reg_async_slv_ack_i` (`logic`): Asynchronous register response acknowledge.
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_ack_out` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_ack_i`.
*   `reg_async_slv_data_o` (`reg_intf_pkg::reg_rsp_t`): Register response payload (read data, error flag).
    *   **Ollivander Handling**: Component -> Connected to the host's `async_reg_data_in` bus. If marked `external: true` in YAML, exposed at the SoC top-level as `<component_name>_reg_data_o`.

**Synchronous (`sync_domain: true`):**
*   `reg_req_i` (`reg_intf_pkg::reg_req_t`): Synchronous register request struct.
    *   **Ollivander Handling**: Component -> Connected to the corresponding slice of the host's synchronous RegBus master port (`sys_reg_req`).
*   `reg_rsp_o` (`reg_intf_pkg::reg_rsp_t`): Synchronous register response struct.
    *   **Ollivander Handling**: Component -> Connected to the corresponding slice of the host's synchronous RegBus master port (`sys_reg_rsp`).

### 3.5 RegBus Master (Host Only)
The Host Isle acts as the central RegBus orchestrator and exposes multi-dimensional arrays to drive all configuration registers in the system.

**Asynchronous:**
*   `reg_async_mst_req_o` (`logic [RegNumSlvAsync-1:0]`): Connected to `async_reg_req_out`.
*   `reg_async_mst_ack_i` (`logic [RegNumSlvAsync-1:0]`): Connected to `async_reg_ack_in`.
*   `reg_async_mst_data_o` (`async_reg_out_req_t [RegNumSlvAsync-1:0]`): Connected to `async_reg_data_out`.
*   `reg_async_mst_req_i` (`logic [RegNumSlvAsync-1:0]`): Connected to `async_reg_req_in`.
*   `reg_async_mst_ack_o` (`logic [RegNumSlvAsync-1:0]`): Connected to `async_reg_ack_out`.
*   `reg_async_mst_data_i` (`async_reg_out_rsp_t [RegNumSlvAsync-1:0]`): Connected to `async_reg_data_in`.

**Synchronous:**
*   `reg_req_o` (`sync_reg_out_req_t [RegNumSlvSync-1:0]`): Connected to `sys_reg_req`.
*   `reg_rsp_i` (`sync_reg_out_rsp_t [RegNumSlvSync-1:0]`): Connected to `sys_reg_rsp`.

### 3.6 JTAG (`jtag`)
Standard 4-wire JTAG interface. Output enable (`_oe_o`) is provided for tristate pad integration at the chip level.
*   `jtag_tck_i` (`logic`): JTAG Test Clock.
    *   **Ollivander Handling**: Exposed as a top-level SoC I/O pin. The pin is named `jtag_<component_name>_tck_i` (e.g., `jtag_safety_island_tck_i`). For the host component, the prefix is omitted.
*   `jtag_trst_ni` (`logic`): JTAG Test Reset (active low).
    *   **Ollivander Handling**: Exposed as a top-level SoC I/O pin named `jtag_<component_name>_trst_ni`.
*   `jtag_tms_i` (`logic`): JTAG Test Mode Select.
    *   **Ollivander Handling**: Exposed as a top-level SoC I/O pin named `jtag_<component_name>_tms_i`.
*   `jtag_tdi_i` (`logic`): JTAG Test Data In.
    *   **Ollivander Handling**: Exposed as a top-level SoC I/O pin named `jtag_<component_name>_tdi_i`.
*   `jtag_tdo_o` (`logic`): JTAG Test Data Out.
    *   **Ollivander Handling**: Exposed as a top-level SoC I/O pin named `jtag_<component_name>_tdo_o`.
*   `jtag_tdo_oe_o` (`logic`): JTAG Test Data Out Enable (high when driving TDO). **[OPTIONAL]**
    *   **Ollivander Handling**: Ollivander automatically parses the Isle's SystemVerilog header. If this port is declared in the module, it is wired and exposed at the SoC top-level as `jtag_<component_name>_tdo_oe_o`. If omitted from the wrapper, Ollivander safely ignores it without causing compilation errors.

### 3.7 Common Peripherals
All common peripheral ports are exposed as top-level SoC I/O pins. If the component is not the host, the pin names are prefixed with the component's name (e.g., `uart_security_island_tx_o`).

*   **UART (`uart`)**: 
    *   `uart_tx_o` (`logic`): Transmit data.
    *   `uart_rx_i` (`logic`): Receive data.
*   **SPI Host (`spi_host`)**: 
    *   `spi_sck_o` (`logic`): Serial Clock output.
    *   `spi_sck_en_o` (`logic`): Serial Clock output enable.
    *   `spi_csb_o` (`logic [3:0]` or `logic`): Chip Select (active low).
    *   `spi_csb_en_o` (`logic [3:0]` or `logic`): Chip Select output enable.
    *   `spi_sd_o` (`logic [3:0]`): Serial Data output (for Single/Dual/Quad SPI).
    *   `spi_sd_en_o` (`logic [3:0]`): Serial Data output enable. 
    *   `spi_sd_i` (`logic [3:0]`): Serial Data input.
*   **I2C (`i2c`)**: 
    *   `i2c_sda_o` (`logic`): Serial Data output. 
    *   `i2c_sda_i` (`logic`): Serial Data input.
    *   `i2c_sda_en_o` (`logic`): Serial Data output enable (for open-drain pad).
    *   `i2c_scl_o` (`logic`): Serial Clock output.
    *   `i2c_scl_i` (`logic`): Serial Clock input.
    *   `i2c_scl_en_o` (`logic`): Serial Clock output enable (for open-drain pad).
*   **HyperBus PHY (`hyperbus_phy`)**: 
    *   `cs_no` (`logic [1:0]`): Chip Select (active low) for multiple devices.
    *   `ck_o` (`logic`): Differential Clock positive.
    *   `ck_no` (`logic`): Differential Clock negative.
    *   `rwds_o` (`logic`): Read/Write Data Strobe output.
    *   `rwds_i` (`logic`): Read/Write Data Strobe input.
    *   `rwds_oe_o` (`logic`): Read/Write Data Strobe output enable.
    *   `dq_i` (`logic [7:0]`): Data Bus input.
    *   `dq_o` (`logic [7:0]`): Data Bus output.
    *   `dq_oe_o` (`logic`): Data Bus output enable.
    *   `reset_no` (`logic`): Device hardware reset (active low). 
*   **RGMII PHY (`rgmii_phy`)**: 
    *   `phy_rx_clk_i` (`logic`): Receive Clock.
    *   `phy_rxd_i` (`logic [3:0]`): Receive Data nibble.
    *   `phy_rx_ctl_i` (`logic`): Receive Control (RX_DV).
    *   `phy_tx_clk_o` (`logic`): Transmit Clock.
    *   `phy_txd_o` (`logic [3:0]`): Transmit Data nibble.
    *   `phy_tx_ctl_o` (`logic`): Transmit Control (TX_EN).
    *   `phy_resetn_o` (`logic`): PHY Reset (active low).
    *   `phy_mdio_i` (`logic`): Management Data Input/Output (Input).
    *   `phy_mdio_o` (`logic`): Management Data Input/Output (Output).
    *   `phy_mdio_oe` (`logic`): Management Data Input/Output enable.
    *   `phy_mdc_o` (`logic`): Management Data Clock.
*   **CAN Bus (`can_top_apb` sub-component)**: 
    *   `rx_i` (`logic`): CAN receive pin.
    *   `tx_o` (`logic`): CAN transmit pin.
    *   **Ollivander Handling**: Automatically exposed at the SoC top-level when instantiated inside an `apb_subsystem`. The pin names are prefixed with the sub-component name (e.g., `can_bus_rx_i`).

---

## 4. Interrupt Guidelines (Strictly Level-Triggered)
Ollivander establishes a strict hardware contract for the SoC Top-Level: **All interrupt routing is assumed to be level-triggered.**

If your IP natively generates edge-triggered or pulsed interrupts (like some APB timers), **the Isle wrapper must encapsulate an `edge_propagator`** (or equivalent pulse-to-level logic) and expose a stable, level-triggered signal to the outside world.

---

## 5. Autonomous System Signals
Ollivander's parser reads the SystemVerilog header of your Isle and automatically wires up specific system/control signals if it finds them. You do not need to specify these in the YAML interfaces list.

### Mandatory Signals
Every Isle must implement these basic clocking and reset signals:
*   **`clk_i`** (`logic`): Main clock input, automatically wired to the clock domain assigned in the YAML.
    *   **Ollivander Handling**: Connected to the output of the corresponding clock domain logic (e.g., `periph_clk`).
*   **`rst_ni`** (`logic`): Main reset input (active low), automatically wired to the reset domain assigned in the YAML.
    *   **Ollivander Handling**: Connected to the output of the corresponding reset generator logic (e.g., `rsts_n[ollivander_soc_pkg::DomainIdx_periph]`). If `reset_domain` is not specified in the YAML, it is automatically inferred from the `clock_domain` (e.g., `periph_clk` implies `periph_rst`).

### Optional Signals
These signals are mapped automatically if their exact name is found in the module declaration (all names listed are actively supported by Ollivander):
*   **`pwr_on_rst_ni`** (`logic`): Power-On Reset (active low) associated with the Isle's assigned clock domain. Used for persistent logic.
    *   **Ollivander Handling**: Connected to the power-on-reset output of the corresponding reset generator (e.g., `pwr_on_rsts_n[DomainIdx_periph]`).
*   **`sys_clk_i`** (`logic`): Global system clock (`host_clk`). Useful for IPs that operate in a peripheral clock domain but need a reference to the global system time.
    *   **Ollivander Handling**: Hardwired to the main `host_clk` signal.
*   **`sys_rst_ni`** (`logic`): Global system Power-On Reset (`host_pwr_on_rst_n`, active low).
    *   **Ollivander Handling**: Hardwired to the main `host_pwr_on_rst_n` signal.
*   **`rt_clk_i`** (`logic`): The global Real-Time Clock domain (usually 32.768 kHz), used for always-on timers and CLINTs.
    *   **Ollivander Handling**: Hardwired to the main `rt_clk` signal.
*   **`test_mode_i`** (`logic`): DFT/Scan-chain bypass enable flag.
    *   **Ollivander Handling**: Hardwired to the top-level `test_mode_i` input pin.
*   **`boot_mode_i`** (`logic [1:0]`): The system boot mode strapping pins.
    *   **Ollivander Handling**: Hardwired to the top-level `boot_mode_i` input pins.
*   **`boot_addr_i`** (`logic [31:0]` or `[63:0]`): Boot address override provided by the System Controller registers.
    *   **Ollivander Handling**: Intended to be connected to the `sys_regs_reg2hw.<component_name>_boot_addr.q` register output from the System Controller.
*   **`fetch_en_i`** (`logic`): The core fetch enable signal driven by the System Controller registers (allows the Host to wake up the Isle).
    *   **Ollivander Handling**: Connected to the `sys_regs_reg2hw.<component_name>_fetch_enable.q` (or `_boot_enable.q`) register output.
*   **`axi_isolate_i`** (`logic`): AXI isolation request driven by the System Controller, ensuring the Isle's AXI traffic is fenced during its own reset sequences.
    *   **Ollivander Handling**: Connected to the `sys_regs_reg2hw.<component_name>_isolate.q` register output.
*   **`axi_isolated_o`** (`logic`): AXI isolation acknowledgment returned to the System Controller.
    *   **Ollivander Handling**: Connected to the `sys_regs_hw2reg.<component_name>_isolate_status.d` register input.
*   **`debug_req_i`** (`logic [1:0]` or `logic`): External debug request signal driven by the System Controller.
    *   **Ollivander Handling**: Connected to the `sys_regs_reg2hw.<component_name>_debug_req.q` register output (enabled via `debug_req: true` in `system_config`).
*   **`busy_o`** (`logic`): Busy status flag exported to the System Controller.
    *   **Ollivander Handling**: Connected to the `sys_regs_hw2reg.<component_name>_busy.d` register input (enabled via `has_busy_status: true` in `system_config`).
*   **`eoc_o`** (`logic`): End of Computation status flag exported to the System Controller (and optionally mapped as an interrupt).
    *   **Ollivander Handling**: Connected to the `sys_regs_hw2reg.<component_name>_eoc.d` register input (enabled via `has_eoc_status: true` in `system_config`).

---

## 6. The Host Isle & Interconnect Requirement
The Host Isle (e.g., `cheshire_isle.sv`) is the most critical component, acting as the system orchestrator.

### 6.1 The Crossbar Mandate
In a Crossbar-based topology, **the Host Isle MUST internally contain the AXI crossbar** (or the NoC injection points). Ollivander builds the address map and routing arrays in the Python generator and passes them via the `ollivander_soc_pkg`. The Host Isle is responsible for reading these arrays and instantiating the physical crossbar that demultiplexes `axi_ext_slv` traffic and multiplexes `axi_ext_mst` traffic.

### 6.2 Dynamic Configuration Builder Pattern
To maintain a standardized interface while supporting massive Host configurations (like Cheshire's `cheshire_cfg_t` struct), the Host Isle implements the **Dynamic Configuration Builder Pattern**:

1.  **Standard Interface:** It exposes only flat, scalar parameters (`AxiNumMst`, `NumCores`, `FeatureUart`, etc.) and system arrays.
2.  **Internal Builder:** A SystemVerilog `function automatic cheshire_cfg_t build_cheshire_cfg()` is defined locally inside the wrapper.
3.  **Struct Assembly:** The function takes the scalar parameters and the arrays provided by the generator package and translates them into the complex struct required by the inner IP.

This strictly enforces a unidirectional data flow: `YAML Topology -> Python Generator -> ollivander_soc_pkg.sv -> cheshire_isle.sv -> cheshire_soc`

### 6.3 Auto-Calculated Host Parameters

To further simplify the configuration, Ollivander automatically calculates several key architectural and interrupt-related parameters for the Host Isle based on the connectivity defined in the YAML sections. The user **should not** specify these in the `parameters` block of the host, as the generator will override them.

#### Bus Interface Counts (Crossbar/NoC Sizing)
To properly dimension the Host's internal crossbar arrays or NoC injection points, Ollivander aggregates the total number of master and slave interfaces in the system:

*   **`AxiNumMstSync` / `AxiNumMstAsync`**: Calculated by counting the total number of `axi_master` interfaces declared by other components in the system. Ollivander routes them to the synchronous or asynchronous parameter based on the overall topology type (e.g., NoC uses Sync, Crossbar typically uses Async).
*   **`AxiNumSlvSync` / `AxiNumSlvAsync`**: Calculated by summing the number of `ports` requested by all `axi_slave` interfaces across the SoC, segregated by their `sync_domain` YAML flag.
*   **`RegNumSlvSync` / `RegNumSlvAsync`**: Calculated by counting all `regbus_slave` interfaces across the SoC (segregated by their `sync_domain` YAML flag), plus one synchronous slave reserved for the central System Controller.

#### Interrupt Vector Sizing
Ollivander infers the required size of the Host's interrupt aggregators by inspecting the bit indices used in the YAML routing matrix.

*   **`NumIntrsIn`**: Automatically calculated by finding the highest bit index used in the `source` mapping for the Host's main input interrupt (e.g., `manager.intr_ext_i`). This determines the required width of the external interrupt aggregator.

*   **`NumIntrsOut`**: Automatically calculated by scanning all components' interrupt sources. It finds the highest bit index requested from the Host's main output interrupt bus (e.g., `manager.intr_ext_o[...]`) and sizes the bus accordingly.

*   **`NumIrqHarts`**: Automatically calculated by counting the total width of all component interrupts that are sourced from the Host's standard RISC-V hart interrupt outputs (`mtip_ext_o`, `msip_ext_o`, `xeip_ext_o`).

*   **`NumDbgHarts`**: Automatically calculated by counting the total width of all component interrupts sourced from the Host's debug interrupt output (`dbg_ext_req_o`).

This auto-sizing mechanism ensures that the Host's interrupt interface is always correctly dimensioned to match the system's connectivity, removing the burden of manual calculation from the user.

### 6.4 Simulation Force-Boot Parameters
To support dynamic force-booting in simulation, a Host Isle wrapper (e.g., `cheshire_isle.sv`) can optionally expose standard parameters defining the startup control:
*   `HasForceBoot` (`localparam bit`): Set to `1` if this host supports software force-booting in simulation.
*   `ForceBootPath` (`localparam string`): Hierarchical path from the host wrapper top to the entry point scratch register (e.g., `"i_cheshire_soc.i_regs.field_storage.scratch[0].scratch.value"`).
*   `ForceBootVal` (`localparam string`): Force value template (e.g., `"32'h00000000"`).

These parameters are read by the testbench generator to automatically drive the boot entry sequence.

---

## 7. Dependency Management

Ollivander features an automated dependency resolution engine that scans your Isles and populates the `Bender.yml` manifest. This ensures that only the files and IP packages actually instantiated in the SoC are included in the compilation flow.

### 7.1 Static Dependencies (SystemVerilog Files)
For standard `.sv` files, declare dependencies using special comments anywhere in the file (typically at the top):

*   **Bender Packages**: Use `// BENDER: name="<package_name>"` to link an external repository. Ollivander will look up the git URL and version in the `ollivander_config.yml` registry.
    ```systemverilog
    // BENDER: name="axi"
    // BENDER: name="common_cells"
    ```
    You can also override the registry inline (though not recommended for SSoT): `// BENDER: name="my_ip" git="https://..." version="1.0"`

*   **Local Infrastructure Files**: Use `// OLLIVANDER: require="<filename.sv>"` to include a local file from the `components/` directories. Ollivander will automatically locate it and add its relative path to the manifest.
    ```systemverilog
    // OLLIVANDER: require="edge_propagator.sv"
    // OLLIVANDER: require="tc_clk_gating.sv"
    ```

*   **Compilation Macros**: Use `// DEFINE: name="<macro>"` when the IPs this Isle pulls in do not compile without a `+define+`. It is the compile-time counterpart of the `BENDER` pragma: every project that instantiates the Isle inherits the define, without having to know why it is needed, and a project exported as a macro re-exports it to its own consumers, so the define travels across nesting levels together with the RTL that needs it.
    ```systemverilog
    // DEFINE: name="FEATURE_ICACHE_STAT"
    ```
    Defines are merged **by macro name**, and a `defines` entry in the project's own SoC description wins over the pragma, so a project can replace a valued define (`NAME=VAL`) without editing the wrapper. Note that `+define+` applies to the whole compilation library, not just to this Isle's sources.

### 7.2 Dynamic Dependencies (Mako Templates)
If your Isle is dynamically generated (a `.sv.mako` file), you should avoid hardcoding dependency comments if the underlying hardware instantiation is conditional (e.g., inside an `% if` block). 

Instead, use the injected Python functions to dynamically register dependencies *only if* the Mako condition is met. These functions will automatically print the correct `// OLLIVANDER:` or `// BENDER:` tag into the generated `.sv` file and register it in the manifest.

```mako
% if use_custom_divider:
  ${require_file("custom_divider.sv")}
  custom_divider i_div ( ... );
% endif

% if enable_axi:
  ${require_bender("axi")}
% endif
```

---

## 8. Memory Preloading Standardization

For memory Isles that require simulation-only binary preloading (via `$readmemh`), the wrapper can optionally expose standard `localparam` values in its SystemVerilog module declaration. This allows Ollivander to automatically determine how to format and load firmware files without any hardcoded component knowledge.

### 8.1 Parameters Definition
Declare the following localparams inside your memory wrapper's parameter list:

*   **`PreloadType`** (`string`): The preload mode. Supported values:
    *   `"interleaved"`: Indicates the memory contains multiple physical SRAM banks in an interleaved arrangement, requiring a split firmware HEX binary.
    *   If omitted or set to any other value, a standard flat preloading is performed.
*   **`PreloadTemplate`** (`string`): The internal hierarchical path template from the Isle wrapper top to the individual physical SRAM array. It supports bracket formatting variables `{group}` and `{bank}`:
    *   Example: `"i_l2_top.gen_bank_group[{group}].i_dyn_mem_bank_group.genblk1[{bank}].i_ecc_sram_wrap.i_bank.sram"`
*   **`PreloadNumGroups`** (`int unsigned`): The number of bank groups.
*   **`PreloadBankWidth`** (`int unsigned`): The data width of a single physical SRAM bank in bits.
*   **`PreloadBanksPerGroup`** (`int unsigned`): The number of physical SRAM banks in each group (optional, dynamically calculated as `AxiDataWidth / PreloadBankWidth` if omitted or set to 0).
*   **`PreloadInterleave`** (`string`): The physical interleaving scheme of the memory, i.e. what the `{group}` and `{bank}` indices of `PreloadTemplate` actually select. Supported values are `"lane-group"` and `"word-group"`, described in the next section. Defaults to `"word-group"` if omitted, which preserves the behaviour of legacy wrappers.

### 8.2 Interleaving Schemes

**Declaring the wrong scheme is never caught by a tool.** Generation, hex splitting, compilation and elaboration all succeed: the firmware is simply written into the wrong physical locations, and nothing compares it against what the RTL will read back.

The simulation does fail, but late and with a misleading symptom. The CPU boots normally, executes correctly until the end of the first AXI word that happens to land where the RTL expects it, then fetches whatever the mis-split image left behind — typically raising an illegal-instruction exception. Because the host reboots and retries, the log fills with identical exceptions at a fixed PC and the run ends on the testbench timeout with no UART output, which looks far more like a broken boot flow than a corrupted memory image.

If you suspect this failure mode, compare a wide read from the memory against the linked binary: the first `PreloadBankWidth` bits will match and the rest will not. Pick the value that matches how your wrapper is actually wired.

Throughout this section, `W` is the AXI word index of a byte address relative to the base of the memory, `W = rel_addr / (AxiDataWidth / 8)`, and a *lane* is one `PreloadBankWidth`-wide slice of the AXI data word.

#### `"lane-group"` — groups are data lanes

Used by `sram_isle` and `spm_isle`. Every AXI word is spread across **all** groups simultaneously, one lane each, and the `{bank}` index is the depth (row-select) coordinate taken from the high address bits:

*   `{group}` = the lane index, holding bits `[group*PreloadBankWidth +: PreloadBankWidth]` of every AXI word. `PreloadNumGroups` therefore equals `AxiDataWidth / PreloadBankWidth`.
*   `{bank}` = `W / words_per_macro`, where `words_per_macro = (MemSize / (AxiDataWidth/8)) / PreloadBanksPerGroup`.
*   The word address inside the selected SRAM macro is `W % words_per_macro`.

#### `"word-group"` — groups are address-interleaved

Used by `l2_isle`. Consecutive AXI words rotate across the groups, and each AXI word is then sliced lane by lane across consecutive banks *of the selected group*:

*   `{group}` = `W % PreloadNumGroups`.
*   `{bank}` = `d * num_lanes + lane`, where `num_lanes = AxiDataWidth / PreloadBankWidth` and `d` is the depth index derived from `W / PreloadNumGroups`.

### 8.3 Execution Workflow
When Ollivander parses a YAML configuration where `preload_memories` refers to a component wrapper declaring `PreloadType = "interleaved"`, the generator:
1.  **Testbench Generation**: Automatically iterates over `PreloadNumGroups` and `PreloadBanksPerGroup` (falling back to `AxiDataWidth / PreloadBankWidth` if undefined) to generate individual `$readmemh` statements targeted at each physical bank using the resolved hierarchical path from `PreloadTemplate`.
2.  **Hex Splitting Target**: Automatically appends a call to the generic `split_hex.py` script under the Makefile's `build-sw` target, passing the base address, size, and parsed width/group parameters, plus `--interleave <PreloadInterleave>` so the split matches the physical wiring described above.

---

## 9. Offload Boot Contract Standardization

An Isle that wraps a **programmable accelerator** (a compute cluster the host can hand work to) can declare an *offload boot contract*: a block of `Offload*` localparams in its module parameter list, following exactly the mechanism the `Preload*` localparams of section 8 use for memories. The contract is the **IP-internal half** of what the generated `offload` test application (see the SoC configuration guide, section 5.1) needs to drive the component; the SoC-side half — which isolation, fetch-enable and EOC status registers exist in the System Controller — is declared by the user in the component's `system_config` and never restated here. The Isle declares only what the YAML cannot know: the register layout behind its own slave window, and the ISA its cores execute.

### 9.1 Parameters Definition

*   **`OffloadContract`** (`string`): The kind of boot protocol the IP implements. Currently supported: `"control_wire"` — payload and per-core boot addresses are written by the host through the slave window, the cores are released by the SoC-side fetch-enable wire, completion is signalled on `eoc_o` and the result read back from an MMIO register. (A `"memory_mapped"` kind, for snitch-style clusters driven through scratch registers and a CLINT, is planned.)
*   **`OffloadCtrlOffs`** (`int unsigned`): Offset of the IP's control unit from the component's `axi_slave` base address.
*   **`OffloadEocOffs`** (`int unsigned`): Offset, inside the control unit, of the EoC register the payload writes to raise `eoc_o`.
*   **`OffloadBootAddrOffs`** / **`OffloadBootAddrStride`** (`int unsigned`): Offset of the first per-core boot-address register and the distance between consecutive ones.
*   **`OffloadReturnOffs`** (`int unsigned`): Offset of the register the payload leaves its result in.
*   **`OffloadStackOffs`** (`int unsigned`): Top of the IP-local memory the payload may use as its stack, as an offset from the component's base address.
*   **`OffloadNumCores`** (`int unsigned`): Number of cores the boot-address loop and the payload's hart demux must cover. May reference another literal parameter of the same header (e.g. `= NumCores`): the generator resolves one hop of indirection.
*   **`OffloadIsa`** / **`OffloadAbi`** (`string`): The `-march` / `-mabi` pair the payload is cross-compiled with. Spell extensions out the way modern binutils want them (`rv32im_zicsr`, not `rv32im`), and keep the ISA conservative: any multilib of the host toolchain must be able to serve it.

Two rules keep the contract robust, both inherited from hard-won constraints:

*   **Scalars and strings only, never `localparam type`**: a type parameter in a wrapper header evicts the module from hierarchical Verilation (see `docs/getting_started.md`, section 8.3).
*   **Self-contained literals**: every value must be a literal or a one-hop reference to another literal of the same header, because the contract is parsed from the wrapper file alone, without elaborating its package dependencies.

### 9.2 Eligibility and Discovery

The contract alone does not make a component an offload target: the generated firmware also needs the SoC-side half, so the component's `system_config` must declare at least `fetch_enable: true` and `has_eoc_status: true` (plus `isolate: true` when the domain resets isolated, which shapes the generated bring-up prologue). Discovery is automatic — every component satisfying both halves is tested, unless `test_app.offload_targets` restricts the list. A component that declares a contract but misses the SoC-side half is reported and skipped in auto-discovery, and is a hard error when named explicitly.

### 9.3 Reference Implementation

`pulp_cluster_isle.sv` carries the reference `"control_wire"` contract; the authority for its offsets is the wrapped IP's own control unit (`cluster_control_unit.sv` of `cluster_peripherals`), and the header comment of the block records that derivation. When wrapping a new cluster IP, derive the offsets the same way — from the RTL of the register file behind the slave window, never from a software header of a reference project.

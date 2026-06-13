# Ollivander Clocking, Reset, and CDC Requirements

This document specifies the hardware modules required by the Ollivander-generated SoC Top-Level to correctly implement the clock distribution tree, system reset networks, and inter-domain synchronizers.

> **🏗️ HARDWARE ABSTRACTION LAYER (HAL)**
> Ollivander automatically generates a Hardware Abstraction Layer for these modules in the `components/infrastructure` directory (prefixed with `olli_`). By default, these wrappers instantiate behavioral models from the PULP `common_cells` library, providing a fully functional out-of-the-box experience for **Simulation**.
> 
> **For ASIC or FPGA Synthesis**, the hardware designer must map these wrappers to technology-specific standard cells (e.g., TSMC/GlobalFoundries macros for ASIC, or BUFG/BUFGCE/XPM primitives for Xilinx FPGA) by defining the `TARGET_SYNTHESIS` preprocessor macro in their backend toolchain.

These modules are instantiated in the generated top-level SystemVerilog file (and within standardized component wrappers) primarily across the following sections:
1. `1. CLOCK TREE MANAGEMENT`
2. `2. SYSTEM RESETS`
3. `3. INTER-DOMAIN SYNCHRONIZERS (CDC)`

---

## 1. Clock Tree Management

The clock tree relies on glitch-free multiplexers, configurable integer dividers, and proper CDC handling for the configuration registers.

### 1.1 `olli_clk_gen`
*   **Name**: Analog Clock Generator Wrapper (PLL/FLL)
*   **Purpose**: Physical wrapper for the SoC's analog clock generators. It takes a slow reference clock (usually from a crystal oscillator pad) and generates multiple high-speed output clocks. It exposes an asynchronous RegBus interface for dynamic configuration and frequency scaling.
*   **Parameters**:
    *   `NUM_CLOCKS` (int unsigned): Total number of independent clock outputs to generate.
    *   `reg_req_t` (type): Type of the RegBus request payload.
    *   `reg_rsp_t` (type): Type of the RegBus response payload.
*   **Interfaces**:
    *   `ref_clk_i` (input logic): Static reference clock from the Padframe.
    *   `clk_o` (output logic [NUM_CLOCKS-1:0]): Array of generated output clocks.
    *   `lock_o` (output logic [NUM_CLOCKS-1:0]): Lock status signals indicating the clocks are stable.
    *   `cfg_req_i`, `cfg_ack_o`, `cfg_data_i` (inputs/outputs): Asynchronous RegBus request channel.
    *   `cfg_req_o`, `cfg_ack_i`, `cfg_data_o` (outputs/inputs): Asynchronous RegBus response channel.

### 1.2 `olli_clk_mux_glitch_free`
*   **Name**: Glitch-Free Clock Multiplexer
*   **Purpose**: Safely switches between multiple asynchronous clock sources (e.g., different PLLs/FLLs) without producing runt pulses or glitches on the output clock.
*   **Parameters**:
    *   `NUM_INPUTS` (int unsigned): Number of input clock sources.
    *   `NUM_SYNC_STAGES` (int unsigned): Number of flip-flop stages used for synchronization.
    *   `CLOCK_DURING_RESET` (bit): If 1, allows the clock to propagate even when reset is asserted.
*   **Interfaces**:
    *   `clks_i` (input logic [NUM_INPUTS-1:0]): Array of input clocks.
    *   `test_clk_i` (input logic): Dedicated clock for DFT/test mode.
    *   `test_en_i` (input logic): Enable signal for test mode.
    *   `async_rstn_i` (input logic): Asynchronous reset (active low).
    *   `async_sel_i` (input logic [$clog2(NUM_INPUTS)-1:0]): Asynchronous selection signal (driven by CSR).
    *   `clk_o` (output logic): The multiplexed, glitch-free output clock.

### 1.3 `olli_clk_int_div`
*   **Name**: Clock Integer Divider
*   **Purpose**: Divides the input clock by an integer value. It must support dynamic division ratio updates and safe clock gating (enable/disable) without glitching.
*   **Parameters**:
    *   `DIV_VALUE_WIDTH` (int unsigned): Width of the division value signal.
    *   `DEFAULT_DIV_VALUE` (int unsigned): Division value applied after reset.
    *   `ENABLE_CLOCK_IN_RESET` (bit): If 1, ensures the clock toggles during reset to propagate reset correctly.
*   **Interfaces**:
    *   `clk_i` (input logic): Source clock.
    *   `rst_ni` (input logic): Asynchronous reset (active low).
    *   `en_i` (input logic): Clock gate enable (driven by CSR).
    *   `test_mode_en_i` (input logic): Test mode enable to bypass gating/division.
    *   `div_i` (input logic [DIV_VALUE_WIDTH-1:0]): The target division ratio.
    *   `div_valid_i` (input logic): Handshake valid for the division ratio.
    *   `div_ready_o` (output logic): Handshake ready for the division ratio.
    *   `clk_o` (output logic): The divided and gated output clock.
    *   `cycl_count_o` (output logic [DIV_VALUE_WIDTH-1:0]): Current internal counter value (optional).

### 1.4 `olli_lossy_valid_to_stream`
*   **Name**: Lossy Valid to Stream Adapter
*   **Purpose**: Decouples a static CSR register output (which might change unpredictably) into a valid/ready stream protocol. If the downstream logic is busy, it safely drops intermediate values, guaranteeing that only the most recent value is eventually transmitted.
*   **Parameters**:
    *   `DATA_WIDTH` (int unsigned): Bit width of the data.
    *   `T` (type): Type of the data payload (defaults to `logic [DATA_WIDTH-1:0]`).
*   **Interfaces**:
    *   `clk_i` (input logic): Clock.
    *   `rst_ni` (input logic): Reset.
    *   `valid_i` (input logic): Input valid (usually tied to the CSR write-enable signal).
    *   `data_i` (input type T): Input data.
    *   `valid_o` (output logic): Output stream valid.
    *   `ready_i` (input logic): Output stream ready.
    *   `data_o` (output type T): Output stream data.
    *   `busy_o` (output logic): Status indicating a pending transfer.

### 1.5 `olli_cdc_4phase`
*   **Name**: 4-Phase Clock Domain Crossing
*   **Purpose**: Safely transfers multi-bit data (such as clock divider configurations) between two asynchronous clock domains using a robust 4-phase handshake protocol.
*   **Parameters**:
    *   `T` (type): Type of the data payload.
    *   `DECOUPLED` (bit): Decouples the valid/ready handshake on both sides.
    *   `SEND_RESET_MSG` (bit): Send a reset message across domains.
    *   `RESET_MSG` (T): Value of the reset message payload.
*   **Interfaces**:
    *   `src_rst_ni` (input logic): Source domain reset.
    *   `src_clk_i` (input logic): Source domain clock.
    *   `src_data_i` (input type T): Source data.
    *   `src_valid_i` (input logic): Source valid.
    *   `src_ready_o` (output logic): Source ready.
    *   `dst_rst_ni` (input logic): Destination domain reset.
    *   `dst_clk_i` (input logic): Destination domain clock.
    *   `dst_data_o` (output type T): Destination data.
    *   `dst_valid_o` (output logic): Destination valid.
    *   `dst_ready_i` (input logic): Destination ready.

---

## 2. System Resets

The reset network generates synchronized resets for each clock domain, combining global power-on resets with software-controlled resets.

### 2.1 `olli_rstgen`
*   **Name**: Standard Reset Generator
*   **Purpose**: Synchronizes an asynchronous reset input (like an external pin) into a specific clock domain. It asserts the reset asynchronously but ensures a synchronous, glitch-free de-assertion to prevent metastability in the target domain.
*   **Interfaces**:
    *   `clk_i` (input logic): The target clock domain.
    *   `rst_ni` (input logic): Asynchronous reset input (active low).
    *   `test_mode_i` (input logic): Test mode enable to bypass synchronization.
    *   `rst_no` (output logic): The synchronized reset output (active low).
    *   `init_no` (output logic): Initialization pulse (optional).

### 2.2 `<project_name>_rstgen` (e.g., `carfield_rstgen`)
*   **Name**: SoC Global Reset Tree Wrapper
*   **Note**: **Automatically generated by Ollivander.** You do not need to implement this module manually. It relies on the `rstgen` primitive described above.
*   **Purpose**: A project-specific wrapper that aggregates multiple `olli_rstgen` instances, one for each clock domain defined in the SoC. It takes the global Power-On Reset (POR) and an array of software-controlled resets, and outputs the final synchronized resets for all domains.
*   **Parameters**:
    *   `NumRstDomains` (int): The total number of reset domains.
*   **Interfaces**:
    *   `clks_i` (input logic [NumRstDomains-1:0]): Array of clocks for each domain.
    *   `pwr_on_rst_ni` (input logic): Global asynchronous power-on reset.
    *   `sw_rsts_ni` (input logic [NumRstDomains-1:0]): Array of software-controlled resets (driven by CSRs, active low).
    *   `test_mode_i` (input logic): Test mode enable.
    *   `rsts_no` (output logic [NumRstDomains-1:0]): Array of synchronized standard resets.
    *   `pwr_on_rsts_no` (output logic [NumRstDomains-1:0]): Array of synchronized power-on resets (bypassing SW control).
    *   `inits_no` (output logic [NumRstDomains-1:0]): Array of initialization pulses (optional).

---

## 3. Inter-Domain Synchronizers (CDC)

Interrupt routing in heterogeneous SoCs often involves signals crossing different clock boundaries. 

### 3.1 `olli_sync`
*   **Name**: Multi-Stage Bit Synchronizer
*   **Purpose**: Synchronizes a 1-bit asynchronous signal (such as a level-sensitive interrupt) into a destination clock domain using a chain of flip-flops to mitigate the risk of metastability.
*   **Parameters**:
    *   `STAGES` (int unsigned): The number of flip-flop stages in the synchronizer chain (e.g., 2 or 3).
    *   `ResetValue` (bit): The value assumed by the flip-flops upon reset.
*   **Interfaces**:
    *   `clk_i` (input logic): Destination clock domain.
    *   `rst_ni` (input logic): Destination reset domain (active low).
    *   `serial_i` (input logic): Asynchronous input signal.
    *   `serial_o` (output logic): Synchronized output signal.

### 3.2 `olli_edge_propagator`
*   **Name**: Edge-to-Level CDC Propagator
*   **Purpose**: Captures a short pulse (edge) in the source clock domain, safely crosses it to the destination clock domain, and outputs it as a stable level-sensitive signal. Used extensively to adapt legacy pulsed interrupts to the SoC's level-sensitive requirement.
*   **Interfaces**:
    *   `clk_tx_i` (input logic): Source domain clock.
    *   `rstn_tx_i` (input logic): Source domain reset (active low).
    *   `edge_i` (input logic): Input edge/pulse signal.
    *   `clk_rx_i` (input logic): Destination domain clock.
    *   `rstn_rx_i` (input logic): Destination domain reset (active low).
    *   `edge_o` (output logic): Output level-sensitive, synchronized signal.
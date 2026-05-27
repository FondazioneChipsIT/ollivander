# Top-Level Unencapsulated Blocks Analysis

After encapsulating the main hardware IPs into standardized "Isle" wrappers (`*_isle.sv`), the remaining blocks instantiated in the SoC top-level (e.g., `carfield.sv` or `gwaihir_top.sv`) fall into three main functional categories. These are the foundational blocks that Ollivander will dynamically generate or instantiate based on the YAML configuration.

## 1. Clock and Reset Management (The Clock Tree)
This logic translates the `clock_tree` section of the YAML into actual hardware, routing and dividing clocks for the various domains (`host_clk`, `periph_clk`, etc.).

*   `clk_mux_glitch_free`: Selects the clock source for a domain at runtime without creating glitches. Instantiated for domains with `has_mux: true` in the YAML.
*   `clk_int_div`: Integer clock divider. Generates the effective clock for a domain or for debug interfaces (`has_divider: true` / `has_debug_divider: true`).
*   `lossy_valid_to_stream`: Protocol converter. Transforms the "register write" signal (from the RegBus) into a continuous stream to dynamically drive the divider change in `clk_int_div` without stalling the bus.
*   `cdc_4phase`: Synchronizes the new clock division value from the Host domain to the original source clock (FLL) domain.
*   `rstgen` / `carfield_rstgen`: System reset generators. `rstgen` generates the power-on-reset for the Host, while `carfield_rstgen` combines power-on-resets with software-triggered resets (driven by control registers) for all other domains.

## 2. Signal Synchronization and Interrupts (The Glue Logic)
Since the *Isles* reside in different clock domains, asynchronous "loose" signals (like interrupts) cannot travel directly from one to another.

*   `edge_propagator`: Used to safely cross clock domains for *edge-triggered* interrupts (e.g., timer interrupts going from `periph_clk` to `host_clk`).
*   `sync`: Standard 2-stage or 3-stage synchronizer (cascaded flip-flops) used for *level-sensitive* signals, such as CFI requests from the Security Island or DMA interrupts.

## 3. System Registers (System Controller)
This is the global control panel of the chip, generated from the `system_controller` section of the YAML.

*   `carfield_reg_top`: The automatically generated module (typically via tools like PeakRDL or reggen) containing the physical registers. It exposes a RegBus interface on one side and hardware structs (`carfield_reg2hw_t`, `carfield_hw2reg_t`) on the other to drive clocks, resets, and isolation signals (`*_isolate_req`).
*   `reg_cut`: A simple pipeline stage (flip-flop) inserted on the RegBus before entering `carfield_reg_top` to ease *timing closure* during synthesis.

## Summary
What remains in the top-level is the pure essence of a SoC integration layer:
1.  Receives external clocks.
2.  Divides and distributes clocks to the various domains.
3.  Generates resets.
4.  Instantiates the control register block (System Controller).
5.  Instantiates the macro-blocks (the *Isles*).
6.  Synchronizes interrupts and wires AXI/RegBus connections.

This predictable structure is exactly what the Python script (Ollivander) will generate dynamically using Jinja/Mako templates.
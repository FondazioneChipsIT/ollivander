# Comparative Analysis: Ollivander SV-IR vs. CIRCT

This document evaluates the feasibility, advantages, and architectural trade-offs of adopting LLVM's CIRCT (Circuit IR Compilers and Tools) framework in the Ollivander SoC Generator compared to the current custom SystemVerilog Intermediate Representation (SV-IR).

---

## 1. Feasibility of Adopting CIRCT in Ollivander

It is technically feasible to adopt CIRCT in Ollivander. However, because CIRCT requires exact knowledge of all module port signatures and types during the construction of its in-memory graph, it cannot operate in isolation when external IPs are missing. 

To adopt CIRCT, Ollivander's generation flow would need to be restructured into a **two-pass compilation flow**:

```
[SoC Config] ──> [Pass 1: Manifest Gen] ──> [Bender Fetch (git checkouts)] ──> [Pass 2: IR Construction & RTL Gen]
```

1.  **Pass 1 (Manifest Generation)**: Ollivander parses the SoC configuration and generates only the dependency manifest (`Bender.yml`).
2.  **IP Fetching**: The build system invokes `bender update` to check out and download all external IP dependencies (e.g., `cheshire`, `pulp_cluster`) into the `bender_work/` directory.
3.  **Pass 2 (IR Construction and Code Generation)**: Ollivander parses the downloaded IP wrapper source files using `pyslang` to build the complete port/parameter database. It then constructs the CIRCT/MLIR representation using the Python bindings, runs verification, and invokes the `ExportVerilog` backend to generate the final top-level RTL wrapper files (`crossbar_soc_top.sv` / `*_chip.sv`).

---

## 2. Advantages of Adopting CIRCT

Integrating CIRCT into the Ollivander pipeline would provide several compiler-level advantages:

*   **Formal Validation and SSA Verification**: CIRCT sits on top of LLVM/MLIR, which strictly enforces Single Static Assignment (SSA) properties and strong typing. The MLIR verifier automatically catches connectivity issues, feedback loops, and type mismatches during IR construction.
*   **Built-in Optimization Passes**: CIRCT features mature compiler optimization passes, including:
    *   *Dead Code Elimination (DCE)*: Pruning unused wires, instances, or ports.
    *   *Constant Propagation*: Folding static expressions and logical equations.
    *   *Port Pruning*: Removing unused port interfaces dynamically.
*   **Highly Compliant Code Generation**: The `ExportVerilog` backend is designed to emit SystemVerilog that conforms strictly to standard IEEE standards, ensuring high compatibility with downstream commercial synthesis tools (e.g., Synopsys Design Compiler, Cadence Genus) and simulators.
*   **HLS and Multi-Language Integration**: Adopting CIRCT opens up compatibility with High-Level Synthesis (HLS) tools, Chisel/FIRRTL frontends, and other compiler-driven hardware flows within the LLVM ecosystem.

---

## 3. Risks and Architectural Disadvantages

Replacing the custom Python-based SV-IR with CIRCT introduces specific architectural constraints and trade-offs.

### 3.1 Parameter-Aware High-Level Semantics (The `localparam` Context)
*   **The Issue**: CIRCT and MLIR are designed as lowering compilers. They typically resolve and flatten parameters during compilation passes, emitting hardcoded bit-widths (e.g., `logic [63:0]`) instead of symbolic parameter names (e.g., `logic [AxiDataWidth-1:0]`).
*   **Functional Impact**: In the current Ollivander templates, top-level parameters (such as `AxiAddrWidth` and `AxiDataWidth`) are declared as **`localparam`** in the module header. In SystemVerilog, a `localparam` cannot be overridden by parent modules at instantiation time. Therefore:
    *   The generated top-level wrapper behaves as a static, non-parameterizable macro from the outside.
    *   Consequently, CIRCT's parameter flattening does **not** result in any functional loss of configuration flexibility, since the top-level interface was already immutable.
    *   The drawback is purely **cosmetic** (reduced code readability within the generated file itself).

### 3.2 Two-Pass Flow Complexity and Network Coupling
*   **The Issue**: Restructuring the generator into a two-pass flow couples the generation of the SystemVerilog wrapper to the successful checkout of external libraries.
*   **Analysis**:
    *   *Network Coupling*: This coupling is already an inherent requirement of the design flow; generating the wrapper alone is functionally useless without the external libraries needed to compile and simulate the SoC.
    *   *Execution Overhead*: The slight increase in generation time during Pass 2 (due to parsing the downloaded dependencies and executing compiler passes) is negligible and easily compensated by the depth of formal validation, catching bugs before running long simulation or synthesis scripts.

### 3.3 Loss of Integration with Third-Party SV IPs
*   **The Issue**: Ollivander relies on parsing pre-existing, hand-written SystemVerilog IP wrappers (Isles like `cheshire_isle.sv`) using `pyslang` to extract their port signatures.
*   **CIRCT Limitation**: CIRCT does not natively parse arbitrary, legacy SystemVerilog code to extract signatures. Integrating third-party SV blocks into CIRCT requires compiling them first through a translator or manually declaring signature stubs within the MLIR environment, significantly complicating the simple `pyslang` integration currently implemented.

### 3.4 Steep Learning Curve and Reduced Flexibility
*   **The Issue**: Modifying the generator logic or adjusting wiring patterns (e.g., introducing a new clock gating scheme or custom testbench hooks) in the custom `rtl_ir_builder.py` is straightforward.
*   **CIRCT Complexity**: The MLIR C++ and Python APIs are verbose and have a steep learning curve. Defining custom behaviors requires writing custom MLIR passes or table-driven rewrite patterns, which increases development time and reduces the agility of the core codebase.

---

## 4. API Verbosity Comparison (Python APIs)

To illustrate the complexity gap, the following examples compare the instantiation and port connection of a hardware block (`cheshire_isle`) using the custom Ollivander IR versus the LLVM/CIRCT Python bindings.

### 4.1 Ollivander Custom IR (High-Level Structural Wiring)
```python
# 1. Create the module instance
inst = ir.add_instance("i_cheshire_isle", "crux_cheshire_isle")

# 2. Define parameters as simple strings (preserved in final RTL)
inst.parameters["AxiDataWidth"] = "64"

# 3. Add port mappings using string expressions
inst.connections.append(PortConnection("clk_i", "host_clk"))
inst.connections.append(PortConnection("rst_ni", "host_rst_n"))
```

### 4.2 CIRCT Python API (Formal Compiler SSA Operations)
```python
from mlir.ir import Context, Location, Module, InsertionPoint
import circt.dialects.hw as hw

with Context() as ctx, Location.unknown():
    # Register dialects
    hw.register_dialect(ctx)
    
    # Create the top-level MLIR Module
    m = Module.create()
    with InsertionPoint(m.body):
        # 1. Define the port signatures and types (required for MLIR validation)
        clk_type = hw.Type.get_logic(ctx)
        rst_type = hw.Type.get_logic(ctx)
        
        # 2. Define the target module signature first
        target_mod = hw.HWModuleOp(
            name="crux_cheshire_isle",
            input_ports=[("clk_i", clk_type), ("rst_ni", rst_type)],
            output_ports=[]
        )
        
        # 3. Retrieve SSA Value operands representing the parent module wires
        # (Must be extracted from the active block context, e.g. parent inputs)
        clk_val = parent_module.inputs["host_clk"]
        rst_val = parent_module.inputs["host_rst_n"]
        
        # 4. Map parameters as formal MLIR attributes
        params = {"AxiDataWidth": hw.ParamDeclAttr.get("AxiDataWidth", "integer", 64)}
        
        # 5. Create the instance operation passing inputs as positional SSA operands
        inst = hw.InstanceOp(
            result_types=[],
            instance_name="i_cheshire_isle",
            module_name="crux_cheshire_isle",
            inputs=[clk_val, rst_val],
            parameters=params
        )
```

---

## 5. Summary Matrix

| Feature | Custom Ollivander SV-IR | LLVM CIRCT |
| :--- | :--- | :--- |
| **Primary Focus** | High-level SoC structural integration. | Low-level RTL compilation, optimization, and synthesis. |
| **Dependencies** | Existing modules (QuestaSim, RISC-V GCC) + lightweight binaries (Bender, Verible). | **Additional** LLVM/MLIR libraries, C++ binaries, and compiled Python bindings. |
| **Parameter Preservation** | High (keeps symbolic names like `AxiDataWidth` internally). | Low (tends to flatten/elaborate parameters to constants). |
| **Functional Impact of Flattening** | None (top-level parameters are already `localparam` and non-overridable). | None (functionally identical interface to the outside). |
| **RTL Import (Isles)** | Native and automated via `pyslang` AST parser. | Requires manual stubbing or complex translations. |
| **Development Agility** | High (direct Python classes, easy to customize). | Low (requires writing complex MLIR passes and dialects). |
| **Optimizations** | Basic connectivity checks only. | Advanced (DCE, constant folding, logic minimization). |
| **Syntax Guarantees** | Structural verification script (`verify`). | Formal compiler-level SSA verification. |
| **Compilation Flow** | One-pass (generates RTL and downloads dependencies after). | Two-pass (must download dependencies first to extract signatures). |

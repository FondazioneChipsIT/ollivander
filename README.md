```
						     .                                              	 
						     *          .*..                                	
						   *. ..      .*    .                               	
						       *      .   ..                                	
						         *.   * ..*                                 	
						  	        *..*      ==**.                         	
    ____  _ _ _                      _  *....*   -#%*=                     
   / __ \| | (_)                    | |              :*%#-                  
  | |  | | | |___   ____ _ _ __   __| | ___ _ __        *%%%=                   
  | |  | | | | \ \ / / _` | '_ \ / _` |/ _ \ '__|         -*%@%%*=         
  | |__| | | | |\ V / (_| | | | | (_| |  __/ |                **%%%*=.          
   \____/|_|_|_| \_/ \__,_|_| |_|\__,_|\___|_|                  -=+*##**+.      
                                                                     -=#%%%#.    
  "Tricky customer, eh? Not to worry, we'll find                        =*#%#*=.    
   the perfect match here somewhere..."                                    =*##*=

                                                                  
```

# Ollivander SoC Generator

**Ollivander** is a highly automated, hardware-first, heterogeneous Multi-Core System-on-Chip (SoC) generator. It is designed to take a high-level YAML specification of an architecture and automatically generate the complete, synthesis-ready SystemVerilog top-level (or reusable Macro IPs), interconnects, clock/reset trees, and software register maps.

---

## 1. Core Philosophy

Ollivander bridges the gap between high-level architectural exploration and low-level physical implementation by enforcing two key paradigms:

### 1.1 The "Isle" Standardization (Unified Component Model)
In Ollivander, every hardware IP (whether it's a RISC-V host, a neural network accelerator, or a simple SPI controller) is encapsulated in a standardized SystemVerilog wrapper called an **Isle**. 
Isles abstract away IP-specific dialects, exposing only standardized interfaces (AXI4, RegBus, APB, JTAG, level-sensitive interrupts, and standard clock/reset pins). This allows the generator to stitch together incredibly complex, heterogeneous systems using a unified routing matrix without needing to "know" the internal details of any specific IP.

For Network-on-Chip topologies, this concept is extended to **Subtiles** (standard IPs automatically wrapped with NoC routers and chimneys) and **Tiles** (custom NoC nodes).

### 1.2 "Hardware-First" Validation
Ollivander refuses to generate broken RTL. Before generating the top-level SoC, it reads the physical SystemVerilog headers of your Isles and validates them against your YAML configuration. If you attempt to configure a 64-bit bus on an IP that strictly requires 32 bits, or map an interrupt to a pin that doesn't exist, Ollivander will halt and point out the architectural error before any code is generated.

---

## 2. Supported Topologies

Ollivander currently supports two major routing topologies:
*   **Crossbar (`example_crossbar.yaml`)**: Ideal for traditional embedded SoCs. The Manager (Host) encapsulates the central AXI routing matrix, exposing multidimensional arrays to the top-level where all other components connect.
*   **Network-on-Chip (`example_noc.yaml`)**: Fully supported for massively parallel, AI/ML accelerator arrays (e.g., FlooNoC). Maps logical coordinates to physical tiles on a 2D mesh, automatically instantiating routers, chimneys, and AXI joins.

---

## 3. The Generation Flow

The generation engine (`ollivander.py`) combines Python and Mako templates in a rigorous 9-Phase pipeline:

### Phase 1: Dynamic Isles Generation
Ollivander reads the YAML configuration and generates intermediate SystemVerilog wrappers for composite blocks. For example, the `apb_subsystem` is built dynamically: Ollivander injects standard peripheral interrupts, generates the `AXI -> AXI-Lite -> APB` conversion pipeline, and instantiates the requested IP cores (Timers, Watchdogs, CAN, etc.) into a single, cohesive Isle.

### Phase 2: Hardware-First Validation
The generator cross-checks the user's YAML configuration against the actual physical parameters (`parameter`, `localparam`) and ports (`input`, `output`) defined in the SystemVerilog Isles. It verifies sync/async boundaries, parameter limits, and exact interrupt port names.

### Phase 3: Top-Level Code Generation
Ollivander builds a massive connection matrix and uses Mako templates to generate:
*   `<project_name>_soc_pkg.sv`: The SystemVerilog package containing the memory map and routing indices.
*   `<project_name>.sv`: The complete Top-Level SystemVerilog file, including glitch-free clock muxes, fractional dividers, reset synchronizers, and cross-domain crossing (CDC) logic for all interrupts.
*   `<project_name>_regs.rdl` & `<project_name>_memory_map.rdl`: The SystemRDL specifications for the central System Controller registers and the global SoC memory map.
*   `Bender.yml`: A complete compilation manifest auto-populated with external IP packages and linked local dependencies.

### Phase 4: Fetch External IPs & Pre-Build
Ollivander invokes **Bender** to fetch all the external IP repositories defined in the dependencies registry. Once downloaded, it executes any defined pre-build scripts or applies on-the-fly text patches to prepare the IPs for compilation.

### Phase 5: Network-on-Chip Generation (Optional)
If the NoC topology is selected, Ollivander invokes `floogen` to generate the NoC configuration, router instances, and standard FlooNoC packages based on the physical placement defined in the YAML.

### Phase 6: Register RTL Generation
Ollivander invokes **PeakRDL** to parse the generated SystemRDL files. This produces the synthesis-ready SystemVerilog for the System Controller (handling software resets, AXI isolation, and clock gating) and the C-header files (`.h`) for bare-metal software drivers.

### Phase 7: Padframe Generation (Optional)
If a padframe is defined, Ollivander delegates the physical I/O ring and pinmux generation to **Padrick**. It supports multiple power domains and generates the CSRs and the RTL for the complete pad ring.

### Phase 8: Chip Wrapper Engine (Optional)
Ollivander parses the Core RTL and the Padrick-generated Padframe package, cross-validating the exact port struct signatures. It then safely renders the final `<project_name>_chip.sv` physical wrapper, instantiating the core, the padframe, and the necessary Clock Domain Crossing (CDC) adapters for the configuration bus.

### Phase 9: RTL Formatting
To ensure a clean, professional, and highly readable output, Ollivander invokes **Verible** to automatically format all generated SystemVerilog code according to strict formatting standards.

### Beyond Generation: Software Bridging & Testbench Preloading
To close the gap between hardware generation and bare-metal validation, Ollivander can fully automate the software build and simulation setup. If defined in your YAML, it will:
1. Generate a **Linker Script** (`link.ld`) perfectly synchronized with your SoC's physical memory map, eliminating manual offset errors.
2. Create a starter **`main.c` firmware skeleton** that automatically includes the generated hardware CSR headers.
3. Compile the application into `.elf` and `.hex` binaries using the specified RISC-V toolchain.
4. Configure the auto-generated SystemVerilog testbench (`_tb.sv`) to seamlessly preload your `.hex` binary into the correct physical SRAM instances using `$readmemh` before the host processor exits reset.

---

## 4. Key Automated Features

*   **Standalone vs Macro Build Modes**: Generate a complete, standalone Chip (including physical padframes and physical I/O) or export your architecture as a reusable **Macro IP**. Macros expose standard AXI boundaries, allowing you to easily instantiate complex Ollivander subsystems inside larger Parent SoCs.
*   **Intelligent Clock & Reset Trees**: Automatically generates software-controllable glitch-free muxes and integer dividers for every defined clock domain, complete with 4-phase CDC handshakes for the configuration registers.
*   **Automatic CDC for Interrupts**: Analyzes the clock domains of interrupt sources and destinations. If they differ, it automatically injects multi-stage synchronizers or edge-to-level propagators.
*   **Automated Dependency Management**: Ollivander actively parses your SystemVerilog files and Mako templates to extract `// BENDER:` and `// OLLIVANDER:` dependencies, automatically building a precise `Bender.yml` manifest that links standard IP libraries and local infrastructure files without duplicating code.
*   **Implicit Interrupt Routing**: You only need to define the interrupt *destination* in the YAML (e.g., `manager` listens to `ethernet.rx_irq`). Ollivander automatically infers the output port on the source component and wires them together.
*   **Decoupled Register Specifications**: Third-party IP registers are discovered dynamically via the `// PEAKRDL: source="..." map="..."` pragma inside their SystemVerilog wrappers, allowing Ollivander to automatically build a unified global C-header for the software stack.
*   **AXI Isolation**: Heterogeneous SoCs require IPs to be powered down or reset independently. Ollivander automatically generates AXI isolation fences controlled by the central System Controller to prevent bus deadlocks.
*   **Hardware-to-Software Synchronization**: Linker scripts and C-headers are dynamically generated directly from the hardware specification, guaranteeing that your bare-metal software always targets the correct memory map and peripheral base addresses.
*   **Physical Chip Wrapping**: Fully automates the tedious and error-prone process of instantiating hundreds of physical I/O pads and routing them to the internal SoC logic.

---

## 5. Usage

Ollivander provides a fully automated `Makefile` workflow. To start a new project:

1. **Setup the Environment**: Copy the sample Makefile and install dependencies (it automatically uses `uv` if available, or falls back to `pip`):
```bash
cp Makefile.sample Makefile
make setup
```

2. **Prepare YAML Configurations**: Create your SoC architectural specification YAML (e.g., `my_project.yaml`) and your environment bridge YAML (e.g., `my_project_env.yaml`). You can find examples in the `soc_cfg/` directory.

3. **Configure the Makefile**: Open your newly copied `Makefile` and update the `SOC_YAML` and `ENV_YAML` variables to point to your files.

4. **Generate the SoC**: Run the generator using the `make` target:
```bash
make generate
```

5. **Simulate**: You can compile the generated hardware and run the simulation using QuestaSim:
```bash
make build-sim
make run-sim
```

The output will be cleanly organized into subdirectories inside `<outdir>` (e.g., `generated/` or the path specified by `-o`):

```text
<outdir>/
├── <sub_hw>/                     # Hardware RTL (*.sv)
│   ├── <project_name>.sv
│   ├── <project_name>_chip.sv    # The final physical chip wrapper (if padframe is used)
│   ├── <project_name>_soc_pkg.sv
│   ├── padframe/                 # Auto-generated RTL and packages from Padrick
│   └── ...
├── <sub_sw>/                     # Software bridging artifacts:
│   ├── <project_name>_soc_regs.h # Auto-generated C-headers for bare-metal CSR access
│   ├── link.ld                   # Memory-mapped Linker Script
│   ├── main.c                    # Starter C firmware skeleton
│   └── *.elf, *.hex              # Compiled software binaries ready for simulation
├── <sub_reg>/                    # Register specification files (*.rdl)
├── <sub_tb>/                     # Auto-generated SystemVerilog testbench with memory preloading (*.sv)
├── <sub_cfg>/                    # Generated configuration files for tools like FlooGen (*.yml)
├── <sub_doc>/                    # Output documentation and mapping tables (*.csv)
└── Makefile.vsim                 # Auto-generated targets for QuestaSim simulation

<bender_manifest>                 # Main compilation manifest linking external IPs and generated RTL
```

---

## 6. Directory Structure

*   `Makefile.sample`: The starting point for project automation and environment setup.
*   `ollivander_config.yaml`: Environment configuration and centralized dependency registry.
*   `src/`: The core engine, containing the Python scripts (`ollivander.py`, `soc_schema.py`, `wiring.py`) and the `templates/` folder (Mako blueprints for SystemVerilog and C).
*   `soc_cfg_examples/`: Contains example YAML configurations (the "Single Source of Truth" for the SoC).
*   `components/isles/`: Standardized SystemVerilog wrappers (and their Mako templates if dynamically generated) for the hardware IPs.
*   `components/tiles/`: Specialized wrappers for Network-on-Chip (NoC) topologies, automatically instantiating routers and network adapters.
*   `components/infrastructure/`: The Hardware Abstraction Layer (HAL) containing simulation-ready physical primitives (glitch-free clock muxes, integer dividers, reset generators, CDCs, and edge-to-level propagators) intended to be mapped to technology-specific standard cells during ASIC/FPGA synthesis.
*   `docs/`: Official documentation, tutorials, and configuration guides.
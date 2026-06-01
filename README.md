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

**Ollivander** is a highly automated, hardware-first, heterogeneous Multi-Core System-on-Chip (SoC) generator. It is designed to take a high-level YAML specification of an architecture and automatically generate the complete, synthesis-ready SystemVerilog top-level, interconnects, clock/reset trees, and software register maps.

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

The generation engine (`ollivander.py`) combines Python and Mako templates in a rigorous 5-Phase pipeline:

### Phase 1: Dynamic Isles Generation
Ollivander reads the YAML configuration and generates intermediate SystemVerilog wrappers for composite blocks. For example, the `apb_subsystem` is built dynamically: Ollivander injects standard peripheral interrupts, generates the `AXI -> AXI-Lite -> APB` conversion pipeline, and instantiates the requested IP cores (Timers, Watchdogs, CAN, etc.) into a single, cohesive Isle.

### Phase 2: Hardware-First Validation
The generator cross-checks the user's YAML configuration against the actual physical parameters (`parameter`, `localparam`) and ports (`input`, `output`) defined in the SystemVerilog Isles. It verifies sync/async boundaries, parameter limits, and exact interrupt port names.

### Phase 3: Top-Level Code Generation
Ollivander builds a massive connection matrix and uses Mako templates to generate:
*   `<project_name>_soc_pkg.sv`: The SystemVerilog package containing the memory map and routing indices.
*   `<project_name>.sv`: The complete Top-Level SystemVerilog file, including glitch-free clock muxes, fractional dividers, reset synchronizers, and cross-domain crossing (CDC) logic for all interrupts.
*   `<project_name>_regs.hjson`: The specification for the central System Controller registers.
*   `Bender.yml`: A complete compilation manifest auto-populated with external IP packages and linked local dependencies.

### Phase 4: Network-on-Chip Generation (Optional)
If the NoC topology is selected, Ollivander invokes `floogen` to generate the NoC configuration, router instances, and standard FlooNoC packages based on the physical placement defined in the YAML.

### Phase 5: Register RTL Generation
Ollivander invokes external tools (like OpenTitan's `regtool.py` or PeakRDL) to parse the generated HJSON file. This produces the synthesis-ready SystemVerilog for the System Controller (handling software resets, AXI isolation, and clock gating) and the C-header files (`.h`) for bare-metal software drivers.

---

## 4. Key Automated Features

*   **Intelligent Clock & Reset Trees**: Automatically generates software-controllable glitch-free muxes and integer dividers for every defined clock domain, complete with 4-phase CDC handshakes for the configuration registers.
*   **Automatic CDC for Interrupts**: Analyzes the clock domains of interrupt sources and destinations. If they differ, it automatically injects multi-stage synchronizers or edge-to-level propagators.
*   **Automated Dependency Management**: Ollivander actively parses your SystemVerilog files and Mako templates to extract `// BENDER:` and `// OLLIVANDER:` dependencies, automatically building a precise `Bender.yml` manifest that links standard IP libraries and local infrastructure files without duplicating code.
*   **Implicit Interrupt Routing**: You only need to define the interrupt *destination* in the YAML (e.g., `manager` listens to `ethernet.rx_irq`). Ollivander automatically infers the output port on the source component and wires them together.
*   **AXI Isolation**: Heterogeneous SoCs require IPs to be powered down or reset independently. Ollivander automatically generates AXI isolation fences controlled by the central System Controller to prevent bus deadlocks.

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
├── <sub_hw>/          # Hardware RTL (*.sv)
│   ├── <project_name>.sv
│   ├── <project_name>_soc_pkg.sv
│   └── ...
├── <sub_sw>/          # Software headers for bare-metal drivers (*.h)
├── <sub_reg>/         # Register specification files (*.hjson)
├── <sub_tb>/          # Auto-generated SystemVerilog testbench (*.sv)
├── <sub_cfg>/         # Generated configuration files for tools like FlooGen (*.yml)
├── <sub_doc>/         # Output documentation and mapping tables (*.csv)
├── Makefile.hw        # Auto-generated targets for hardware dependencies
└── Makefile.vsim      # Auto-generated targets for QuestaSim simulation

<bender_manifest>      # Main compilation manifest linking external IPs and generated RTL
```

---

## 6. Directory Structure

*   `Makefile.sample`: The starting point for project automation and environment setup.
*   `ollivander_config.yaml`: Environment configuration and centralized dependency registry.
*   `src/`: The core engine, containing the Python scripts (`ollivander.py`, `soc_schema.py`, `wiring.py`) and the `templates/` folder (Mako blueprints for SystemVerilog and C).
*   `soc_cfg/`: Contains example YAML configurations (the "Single Source of Truth" for the SoC).
*   `components/isles/`: Standardized SystemVerilog wrappers (and their Mako templates if dynamically generated) for the hardware IPs.
*   `components/infrastructure/`: The Hardware Abstraction Layer (HAL) containing simulation-ready physical primitives (glitch-free clock muxes, integer dividers, reset generators, CDCs, and edge-to-level propagators) intended to be mapped to technology-specific standard cells during ASIC/FPGA synthesis.
*   `tools/`: External utilities (e.g., OpenTitan's regtool).
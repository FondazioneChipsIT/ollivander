# Getting Started: Integrating Ollivander

This guide explains the recommended workflow for integrating the Ollivander SoC Generator into a new hardware project. 

Because Ollivander is a flexible generator designed to weave together both standard and custom hardware IPs, the best practice is to include it as a **Git Submodule** rather than copying its source code directly into your repository.

This approach guarantees:
1. **Reproducibility**: Your SoC will always build exactly the same way, even years from now.
2. **Cleanliness**: Your custom IPs and YAML configurations remain completely separated from the generator's source code.
3. **Easy Updates**: You can pull new features or bug fixes from Ollivander without merge conflicts.

---

## 1. Ideal Repository Structure

Imagine you are building a new chip called "Prometheus". Your repository should look like this:

```text
prometheus_soc/
├── .git/
├── tools/
│   └── ollivander/          <-- Git Submodule (Read-Only)
├── hw_ips/                  <-- Your custom IPs and wrappers (*_isle.sv)
│   ├── aes_crypto_isle.sv
│   └── padframes/           <-- Custom Padframe technology catalogs (Optional)
│       └── tech/
│           └── my_custom_io.yml
├── prometheus_env.yaml      <-- Environment bridge file (YAML)
├── prometheus.yaml          <-- Your SoC specification (YAML or .py script)
└── Makefile                 <-- Project automation
```

---

## 2. Prerequisites

Before running the generator, ensure you have `make` installed on your system.
You don't even need to worry about having the correct version of Python installed: the `make setup` command will automatically download and configure a fully isolated Python environment (using `uv`) along with all the required dependencies.

---

## 3. Step-by-Step Integration

### Step 1: Initialize your repository
Create your project folder and initialize Git.
```bash
mkdir prometheus_soc
cd prometheus_soc
git init
```

### Step 2: Add Ollivander as a Submodule
Add the Ollivander repository into a `tools/` directory.
```bash
git submodule add https://github.com/FondazioneChipsIT/ollivander.git tools/ollivander
```

### Step 3: "Freeze" the Version (Crucial)
To ensure long-term reproducibility, checkout a specific tag, release, or commit hash. Do not track the `main` branch dynamically.
```bash
cd tools/ollivander
git checkout v1.0.0  # Or a specific commit hash like a1b2c3d
cd ../..
git add .gitmodules tools/ollivander
git commit -m "chore: add Ollivander v1.0.0 as submodule"
```

When your colleagues clone the repository, they simply run:
```bash
git clone --recursive https://github.com/your-org/prometheus_soc.git
```

### Step 4: Setup the Makefile & Environment
Ollivander provides a ready-to-use Makefile template to automate your entire workflow, including environment setup and simulation.
```bash
cp tools/ollivander/Makefile.sample Makefile
```
Then, install all the required Python dependencies (it will automatically use `uv` if available, otherwise it falls back to `pip`):
```bash
make setup
```

---

## 4. Injecting Custom IPs

If you want to instantiate your own custom hardware block (e.g., an AES accelerator) inside the SoC, or provide custom Padframe technology catalogs to Padrick, you place your files inside your `hw_ips/` folder.

You must never modify the files inside `tools/ollivander/components/`.

Instead, create the **Environment Bridge File** (`prometheus_env.yaml`):

```yaml
# prometheus_env.yaml
paths:
  components:
    - "hw_ips"  # Instructs Ollivander to search here for Isles/Tiles and padframes/tech/
  rdl_includes:
    - "custom_regs" # Optional: Custom SystemRDL files to override external IPs

# You can also register custom Git dependencies for Bender!
dependencies:
  aes_ip:
    git: "https://github.com/my-org/aes_ip.git"
    version: "1.0.0"
    rdl_include_dirs: ["hw/regs"] # Optional: Instructs PeakRDL where to find the IP's registers
```

---

## 5. Build Modes (Standalone vs Macro)

Before generating, you should decide how your architecture will be used by setting the `build_mode` in your `prometheus.yaml` (or .py):

*   **Standalone (`build_mode: "standalone"`)**: The default behavior. Ollivander generates a complete System-on-Chip top-level, wrapping it with the padframe (if defined) and exposing physical I/O pins (e.g., UART, SPI, JTAG). This is ready for physical synthesis or full-chip simulation.
*   **Macro (`build_mode: "macro"`)**: Generates your architecture as a reusable IP block (a Macro). Instead of physical I/O pins and padframes, it exposes standard AXI Master/Slave interfaces at its boundaries, allowing you to easily instantiate this entire subsystem inside a larger "Parent" SoC.

Example for Macro mode:
```yaml
project:
  name: "prometheus"
  build_mode: "macro"
  macro_settings:
    export_type: "isle" # Exposes a standard AXI interface
    slaves:
      - bus_type: "standard"
        target: "host"
```

---

## 6. Validation, Generation and Simulation

Open the `Makefile` you copied in Step 4 and ensure the variables (`SOC_YAML`, `ENV_YAML`) match your actual filenames. 

### Hardware Generation

To build your SoC and automatically compile the bare-metal software, run:
```bash
make generate
```
Ollivander will create the `generated/` directory containing your complete SoC RTL, the `Bender.yml` manifest in your project root, and a ready-to-use SystemVerilog testbench!

### Iterative Development (fast-check)

For rapid structural validation during iterative development, you can use the fast-check command: 
```bash
make fast-check
```
This command stubs all the external modules, in order to avoid their complete compilation.
> ⚠️ Warning: The `fast-check` mode is intended primarily for the development of Ollivander itself. It performs "dirty" in-place operations on the source files of external libraries to resolve dependencies.
> * It requires that the RTL code has already been generated at least once.
> * If you change the pointers to external libraries or add new components, this mode might fail or produce incorrect results.

For a clean and definitive build, always rely on the full `make generate` command.

---

## 7. Software Development and Simulation

If you configured the `software_stack` and `testbench` sections in your YAML, Ollivander bridges the gap between hardware and software by automatically generating a memory-mapped Linker Script (`link.ld`) and a starter C firmware.

### 6.1 Modifying the Firmware (`main.c`)
When `auto_generate_c: true` is set, you will find a `main.c` file inside your output software directory (e.g., `generated/sw/main.c`). 
This file is ready to be enriched with your custom application logic. It automatically includes the hardware abstraction headers generated by Ollivander:

```c
#include "prometheus_map.h"  // Gives access to all peripheral base addresses and IRQs
#include "prometheus_regs.h" // Gives access to PeakRDL generated C-Structs for the System Controller

int main(void) {
    // Example: Write to a peripheral using auto-generated macros
    volatile uint32_t *uart_tx = (volatile uint32_t *)(PROMETHEUS_UART_BASE_ADDR);
    *uart_tx = 'H';
    
    while(1) {
        // Your custom logic here
    }
    return 0;
}
```

> **Tip:** In a real-world scenario, you should place your custom `main.c` and software drivers in your source repository (e.g., `prometheus_soc/sw/`) and update your Makefile to compile from there, keeping the `generated/` directory purely as an output folder for build artifacts.

### 6.2 Running the Simulation

Once your `main.c` is ready, the Makefile handles the compilation of the `.elf` and `.hex` binaries. To compile the generated hardware, build the firmware, and run the simulation using QuestaSim:
```bash
make build-sim
make run-sim
```

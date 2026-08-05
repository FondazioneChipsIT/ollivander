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
│       └── my_custom_io/
│           ├── my_custom_io.yml
│           └── my_custom_io_cells.sv
├── prometheus_env.yaml      <-- Environment bridge file (YAML)
├── prometheus.yaml          <-- Your SoC specification (YAML or .py script)
└── Makefile                 <-- Project automation
```

---

## 2. Prerequisites

Before running the generator, ensure you have `make` installed on your system. You don't even need to worry about having the correct version of Python installed: the `make setup` command will automatically download and configure a fully isolated Python environment (using `uv`) along with all the required dependencies.

Two environment prerequisites are worth knowing before the first `make generate`:

*   **Bender** must be reachable on `PATH` (it is not covered by `make setup`). It is a single static binary; the official installer drops it in the current directory, so installing it straight into the virtual environment's `bin/` — which the Makefile targets already prepend to `PATH` — works well: `cd .venv/bin && curl --proto '=https' --tlsv1.2 -sSf https://pulp-platform.github.io/bender/init | bash && cd -`.
*   **Some transitive dependencies hardcode SSH URLs** (`git@github.com:...`) in their own manifests. GitHub does not allow anonymous SSH, so on a machine without a registered key those fetches fail. Redirect them to HTTPS once per machine: `git config --global url."https://github.com/".insteadOf "git@github.com:"`.

---

## 3. Step-by-Step Integration

### 3.1 Step 1: Initialize your repository
Create your project folder and initialize Git.
```bash
mkdir prometheus_soc
cd prometheus_soc
git init
```

### 3.2 Step 2: Add Ollivander as a Submodule
Add the Ollivander repository into a `tools/` directory.
```bash
git submodule add https://github.com/FondazioneChipsIT/ollivander.git tools/ollivander
```

### 3.3 Step 3: "Freeze" the Version (Crucial)
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

### 3.4 Step 4: Setup the Makefile & Environment
Create a file named `Makefile` in the root of your project directory (`prometheus_soc/Makefile`). Set the environment variables to point to the Ollivander submodule directory, your SoC design YAML, and your environment YAML, and then include the shared `ollivander.mk` file:

```makefile
OLLIVANDER_ROOT := tools/ollivander
SOC_YAML        := prometheus.yaml
ENV_YAML        := prometheus_env.yaml
OUT_DIR         := generated

include $(OLLIVANDER_ROOT)/ollivander.mk
```

Then, install all the required Python dependencies and tools (it will automatically use `uv` if available, otherwise it falls back to `pip`):
```bash
make setup
```

---

## 4. The Environment Bridge File (`*_env.yml`)

The Environment Configuration file (e.g., `prometheus_env.yaml`) is the bridge between the SoC specification and the physical workstation layout. It defines where files are read from, where they are generated, and how third-party dependencies are retrieved and patched.

Ollivander merges this project-specific environment file with the base configuration (`ollivander_config.yml`). **Your custom settings always take precedence.**

Below is a detailed guide on how to configure this file, along with complete examples for each section.

### 4.1 Paths Configuration (`paths`)

The `paths` block controls input lookup and generated output directories. Relative paths are resolved relative to the location of the environment YAML file itself.

```yaml
paths:
  # --- Output Directories ---
  outdir: "generated"              # Base output directory
  sub_hw: "hw"                     # SV RTL subdirectory (resolves to generated/hw)
  sub_sw: "sw"                     # Firmware, linker scripts, and CSR headers (generated/sw)
  sub_doc: "doc"                   # Mapping tables, design reports, and DRC outputs (generated/doc)
  sub_cfg: "cfg"                   # Configuration manifests for FlooGen/Padrick (generated/cfg)
  sub_reg: "reg"                   # SystemRDL and register specs (generated/reg)
  sub_tb: "tb"                     # Testbench RTL and config (generated/tb)
  bender_manifest: "{outdir}/Bender.yml" # Auto-generated compilation manifest

  # --- Input Search Paths ---
  templates:
    - "custom_templates"           # Directories with custom *.mako templates (precedes src/templates)
  components:
    - "hw_ips"                     # Look for local custom isles, tiles, or padframe catalogs (e.g. hw_ips/padframes/) here
  rdl_includes:
    - "custom_regs"                # Search path for priority SystemRDL specs (overrides external registers)
```

### 4.2 Centralized Dependency Registry (`dependencies`)

Ollivander uses **Bender** to manage external SystemVerilog dependencies. The `dependencies` registry defines where to fetch repositories, which targets to use, and how to compile or patch the source code.

#### 4.2.1 Git Repository Resolution
Specify either a semantic `version` or a specific commit hash or tag using `rev`.
```yaml
dependencies:
  # Using a pinned semantic version
  floo_noc:
    git: "https://github.com/pulp-platform/floo_noc.git"
    version: "0.2.1"

  # Using a specific commit hash or tag
  cva6:
    git: "https://github.com/openhwgroup/cva6.git"
    rev: "8fa2b1d"
```

> [!IMPORTANT]
> Point `rev` at a commit hash or a tag, never at a branch name. A branch moves, so the build stops being reproducible; and a branch cannot satisfy the semantic-version ranges other IPs may express against the same package, which pushes the project into a forced resolution for no reason. The catalogue shipped with Ollivander contains no branch references, deliberately.

#### 4.2.2 Specifying Compilation Targets (`bender_targets`)
Bender handles ASIC/FPGA variants via targets. You can replace the default targets of a dependency:
```yaml
dependencies:
  common_cells:
    git: "https://github.com/pulp-platform/common_cells.git"
    version: "1.31.1"
    bender_targets:
      - "fpga_synth"
      - "simulation"
```
> [!IMPORTANT]
> Defining `bender_targets` in your custom file will completely replace the targets defined in the base `ollivander_config.yml`. To append targets, you must list both the defaults and your new additions.

#### 4.2.3 Pre-Build Commands (`pre_build_cmds`)
Some hardware components require pre-generation steps (e.g., generating register files or compiling intermediate tooling). Ollivander executes these immediately after downloading the dependency.
- Use `{bender_work}` to reference the dependency's local checkout directory.
- Use `{ollivander_dir}` to reference the generator's root directory.
- Use macros like `$(PYTHON)`, `$(MAKE)` and `$(BENDER)` to invoke the correct environments.
- Any other tool must be reachable on `PATH`; an external script is invoked as an ordinary command.

```yaml
dependencies:
  idma:
    git: "https://github.com/FondazioneChipsIT/iDMA.git"
    rev: "2e637216e0455d77706a50d0639b86891e2a83aa"
    pre_build_cmds:
      # Install required Python dependencies inside the isolated environment
      - "$(PYTHON) -m pip install -q flatdict mako"
      # Run the project's internal Makefile to generate hardware descriptions
      - "$(MAKE) -C {bender_work}/idma idma_hw_all BENDER=\"$(BENDER)\""

  custom_crypto:
    git: "https://github.com/my-org/custom_crypto.git"
    rev: "7c2f9a1e4b83d05f6a0c9e21b478d3f5a61c8e04"
    # Execute a dedicated setup script, shipped alongside the generator
    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/setup_custom_crypto.py {bender_work}/custom_crypto"
```

> [!NOTE]
> Unlike `patches` below, these commands are not undone between runs. A command that modifies the checkout must therefore be idempotent: restore what it touches before editing it, or record the edited files in the checkout's `.ollivander_patched` ledger, which the generator restores before every run. Use `pre_build_cmds` when the repair needs logic a text substitution cannot express - generating RTL, or deciding *whether* to modify something at all.

#### 4.2.4 On-the-fly Code Patching (`patches`)
If an external IP contains a compilation error, a broken path, or requires a custom modification, you can specify text-replacement patches. Every occurrence of `search` is replaced, and a literal `\n` in `replace` becomes a newline.
```yaml
dependencies:
  opentitan:
    git: "https://github.com/AlSaqr-platform/opentitan.git"
    rev: "chips-it"
    patches:
      # Correct a bad file extension mapping inside Bender.yml
      - file: "{bender_work}/opentitan/Bender.yml"
        search: "prim_flop_macros.svh"
        replace: "prim_flop_macros.sv"
```

> [!IMPORTANT]
> Each target file is restored to its fetched state before the patches are applied, so the result never depends on how many times you have generated. Three consequences: editing a fetched file by hand is pointless, since the next run reverts it - use `bender clone` to work on a dependency; deleting a patch undoes it, because Ollivander records which files it has patched; and a `search` string that no longer occurs is reported as a stale patch, since on a freshly restored file it can only mean the IP has changed.

See section 4 of [the environment configuration guide](env_configuration_guide.md) for the companion mechanism, `overrides`, which forces a revision when Bender cannot reconcile the requirements at all. It also covers the two ways out when a forcing shipped with Ollivander gets in the way of an IP of your own: dropping that single entry, or declining the inherited set as a whole with `inherit_default_overrides: false`.

#### 4.2.5 Custom Register Inclusion (`rdl_include_dirs`)
To let PeakRDL know where to search for SystemRDL register specifications inside the dependency repository:
```yaml
dependencies:
  uart_apb:
    git: "https://github.com/pulp-platform/apb_uart.git"
    version: "0.1.0"
    rdl_include_dirs:
      - "hw/regs" # PeakRDL will search here for .rdl files matching the IP name
```

---

## 5. Injecting Custom IPs

If you want to instantiate your own custom hardware block (e.g., an AES accelerator) inside the SoC, or provide custom Padframe technology catalogs to Padrick, place your files inside your `hw_ips/` folder.

Similarly, if you have a custom padframe technology (e.g., `my_custom_io`), place it in `hw_ips/padframes/my_custom_io/`. Inside this directory, provide the Padrick-compatible technology configuration file (`my_custom_io.yml`) alongside any auxiliary SystemVerilog wrapper/cell files. Ollivander will automatically locate the `.yml` file and glob all `*.sv` files in that folder for compilation.

For details on how to write padframe configurations using the three modalities (CSV, Python, native YAML), see the [Padframe Configuration Guide](padframe_configuration_guide.md).

**Rule:** You must never modify the files inside `tools/ollivander/components/`.

Instead, register the folder in your `paths.components` list of your environment file (as shown in [Section 4.1](#41-paths-configuration-paths)).

---

## 6. Build Modes (Standalone vs Macro)

Before generating, decide how your architecture will be used by setting the `build_mode` in your `prometheus.yaml` (or `.py` script):

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

## 7. Validation, Generation and Simulation

Ensure the variables (`SOC_YAML`, `ENV_YAML`) in your project's `Makefile` match your actual filenames. 

### 7.1 Hardware Generation
To build your SoC and automatically compile the bare-metal software, run:
```bash
make generate
```
Ollivander will create the `generated/` directory containing your complete SoC RTL, the `Bender.yml` manifest in your project root, and a ready-to-use SystemVerilog testbench!

### 7.2 Iterative Development (fast-check)
For rapid structural validation during iterative development, you can use the fast-check command: 
```bash
make fast-check
```
This command stubs all the external modules, avoiding their complete compilation.

#### Simulator Backend Selection
Ollivander supports two different backend engines for compiling and validating your fast-check:
1. **QuestaSim** (`questa`): Default incremental compile validation.
2. **Verilator** (`verilator`): Fast monolithic lint compile validation.

You can configure the tool of choice by defining `fast_check_tool` inside your `*_env.yml` file, or dynamically override it at command-line:
```bash
# Run fast-check forcing Verilator
make fast-check FAST_CHECK_TOOL=verilator

# Run fast-check forcing QuestaSim
make fast-check FAST_CHECK_TOOL=questa
```

See the [Environment Configuration Guide](env_configuration_guide.md) for more details.

> [!WARNING]
> `fast-check` validates against a snapshot: it reads the previously generated RTL and the previously fetched external IPs, and writes nothing outside `generated/`.
> * It requires that `make generate` has completed at least once.
> * It does not re-resolve dependencies: after changing an external library pointer, an `*_env.yml`, or the component set, run `make generate` again first, or the stubs will describe the old state.
> For a clean and definitive build, always rely on the full `make generate` command.

### 7.3 IP-XACT Component Export & Validation
In addition to the SystemVerilog RTL, Ollivander automatically generates an IEEE 1685-2014 compliant IP-XACT component description XML representing the digital core top-level (without padframe). This XML is saved to `generated/hw/ipxact/<project_name>.xml`.

Every time you run `make generate`, Ollivander parses the written XML back and validates it against the official Accellera schema using `pyEDAA.IPXACT`. If schema validation fails, the generator raises an error and halts the build to ensure that only compliant metadata is produced.

---

## 8. Software Development and Simulation

If you configured the `software_stack` and `testbench` sections in your YAML, Ollivander bridges the gap between hardware and software by automatically generating a memory-mapped Linker Script (`linker.ld`) and a starter C firmware.

### 8.1 Modifying the Firmware (`main.c`)
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

> [!TIP]
> In a real-world scenario, you should place your custom `main.c` and software drivers in your source repository (e.g., `prometheus_soc/sw/`) and update your Makefile to compile from there, keeping the `generated/` directory purely as an output folder for build artifacts.

### 8.2 Running the Simulation
Once your `main.c` is ready, the Makefile handles the compilation of the `.elf` and `.hex` binaries. To compile the generated hardware, build the firmware, and run the simulation using QuestaSim:
```bash
make build-sim
make run-sim
```

### 8.3 Running the Simulation with Verilator (license-free)
The same testbench can be built and run with Verilator, with no simulator license involved:
```bash
make build-sim-verilator
make run-sim-verilator
```
The pass criterion is identical on both backends: the run prints the firmware's `[UART]:` output and ends with `[TB] EOT received. Simulation finished.` (the transcript is written to `logs/verilator_transcript`).

A few practical differences with respect to the QuestaSim flow are worth knowing:

* **The build is front-loaded**: Verilator compiles the whole SoC into a native executable (`verilator_work/Vtb_<name>`), which takes far longer than `vlog` (on the `noc` example: roughly 1.5 hours against minutes, with `ccache` absorbing most of a rebuild), while the run itself is a plain process with a tiny memory footprint (~300 MB where QuestaSim needs gigabytes). It suits regressions and CI machines rather than fast RTL iteration.
* **Repeated tiles are built once**: the flow uses hierarchical verilation, driven by the generated `generated/cfg/<name>.vlt`, so a tile instantiated N times is verilated a single time.
* **Toolchain requirements**: Verilator ≥ 5.044 and a C++20-capable compiler (`<coroutine>` support, g++ ≥ 11). On RHEL-family hosts the build recipe automatically enables the newest installed `gcc-toolset` when the default compiler is too old.
* **Assertions are structurally disabled** in the Verilator build (the equivalent of the suite's `ASSERTIONS=0`), and two-valued simulation semantics apply.

> [!NOTE]
> The Verilator simulation flow is validated end-to-end (identical UART output and EOT against QuestaSim) on the `noc` example. The crossbar-family examples currently stop in mid-elaboration inside two legacy IPs and remain QuestaSim-only for simulation; every example passes the Verilator `fast-check`. See `docs/developer/wip/future_evolution_tasks.md`, chapter 5, for the plan.

The test suite can drive the Verilator backend for its simulation leg with:
```bash
make test-all TEST_PROJECTS="noc" TEST_SIM=1 TEST_SIM_TOOL=verilator
```

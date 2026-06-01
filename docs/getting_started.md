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
│   └── aes_crypto_isle.sv
├── prometheus_env.yaml      <-- Environment bridge file
├── prometheus.yaml          <-- Your SoC specification (SSoT)
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

If you want to instantiate your own custom hardware block (e.g., an AES accelerator) inside the SoC, you place your `aes_crypto_isle.sv` inside your `hw_ips/` folder.

You must never modify the files inside `tools/ollivander/components/`.

Instead, create the **Environment Bridge File** (`prometheus_env.yaml`):

```yaml
# prometheus_env.yaml
paths:
  components:
    - "hw_ips"  # Instructs Ollivander to also search here for Isles/Tiles

# You can also register custom Git dependencies for Bender!
dependencies:
  aes_ip:
    git: "https://github.com/my-org/aes_ip.git"
    version: "1.0.0"
```

---

## 5. Validation, Generation and Simulation

Open the `Makefile` you copied in Step 4 and ensure the variables (`SOC_YAML`, `ENV_YAML`) match your actual filenames. 

### Hardware Generation

To build your SoC for the first time, run:
```bash
make generate
```
Ollivander will create the `generated/` directory containing your complete SoC RTL, the `Bender.yml` manifest in your project root, and a ready-to-use SystemVerilog testbench!

### Iterative Development (fast-check)

After running make generate at least once (so that the initial RTL and dependencies are fully resolved and generated), you can use the fast-check command for quicker development iterations: 
```bash
make fast-check
```
This command re-runs the generation process but skips the slow dependency fetching step.
> ⚠️ Warning: The `fast-check` mode is intended primarily for the development of Ollivander itself. It performs "dirty" in-place operations on the source files of external libraries to resolve dependencies.
> * It requires that the RTL code has already been generated at least once.
> * If you change the pointers to external libraries or add new components, this mode might fail or produce incorrect results.

For a clean and definitive build, always rely on the full `make generate` command.
To compile the generated hardware and run the simulation using QuestaSim:
```bash
make build-sim
make run-sim
```

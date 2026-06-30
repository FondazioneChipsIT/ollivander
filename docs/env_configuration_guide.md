# Ollivander Environment Configuration Guide

Ollivander enforces a strict **Separation of Concerns**. While your main SoC YAML file describes *what* hardware to build (the topology, the components, the memory map), the **Environment Configuration YAML** describes *how* and *where* to build it.

The environment configuration tells Ollivander:
* Where to output the generated files.
* Where to search for custom templates and component wrappers.
* How to resolve, fetch, patch, and compile external IP dependencies (via Bender).

---

## 1. File Precedence and Overrides

Ollivander uses a base configuration file, usually named `ollivander_config.yml`, located in the generator's root directory. **You should never modify this file directly.**

Instead, when integrating Ollivander into your project, you should create a project-specific environment file (e.g., `my_project_env.yaml`) and pass it to the generator using the `-a` (`--append-env`) flag:

```bash
make generate SOC_YAML=my_project.yaml ENV_YAML=my_project_env.yaml
```

Ollivander will automatically merge your custom environment file with the base one. If a path or a dependency is defined in both, **your custom file takes precedence**.

---

## 2. Paths Configuration (`paths`)

The `paths` section defines directories for inputs and outputs. All relative paths are resolved relative to the location of the YAML file that defines them.

### Output Directories
| Field             | Type   | Default                 | Description                                            |
| :---------------- | :----- | :---------------------- | :----------------------------------------------------- |
| `outdir`          | String | `"generated"`           | The base directory where all output files will be      |
|                   |        |                         | written.                                               |
| `sub_hw`          | String | `"hw"`                  | Subdirectory for SystemVerilog RTL files.              |
| `sub_sw`          | String | `"sw"`                  | Subdirectory for C headers, linker scripts, and        |
|                   |        |                         | firmware binaries.                                     |
| `sub_doc`         | String | `"doc"`                 | Subdirectory for documentation and mapping CSVs.       |
| `sub_cfg`         | String | `"cfg"`                 | Subdirectory for tool configs (e.g., FlooGen YAMLs).   |
| `sub_reg`         | String | `"reg"`                 | Subdirectory for register specifications (HJSON).      |
| `sub_tb`          | String | `"tb"`                  | Subdirectory for generated testbenches.                |
| `bender_manifest` | String | `"{outdir}/Bender.yml"` | Path where the final Bender manifest will be generated.|
|                   |        |                         | The `{outdir}` placeholder is resolved dynamically.    |

### Input Search Paths
These define where Ollivander looks when you declare a component `type` or a `require` pragma.

| Field         | Type            | Default                       | Description                                  |
| :------------ | :-------------- | :---------------------------- | :------------------------------------------- |
| `templates`   | List of Strings | `["src/templates"]`           | Directories containing `.mako` templates.    |
| `components`  | List of Strings | `["components"]`              | Directories containing SystemVerilog IP      |
|               |                 |                               | wrappers (`*_isle.sv` or `*_tile.sv`). To    |
|               |                 |                               | inject your custom IPs, add your project's   |
|               |                 |                               | hardware folder here. Ollivander also looks  |
|               |                 |                               | in these paths for custom Padframe           |
|               |                 |                               | technology catalogs (`padframes/tech/`).     |
| `rdl_includes`| List of Strings | `[]`                          | Directories where PeakRDL should search for  |
|               |                 |                               | custom `.rdl` files. Files found here have   |
|               |                 |                               | absolute priority and will override external |
|               |                 |                               | IP registers with the same name.             |

**Example of appending custom paths:**
```yaml
paths:
  components:
    - "../hw_ips" # Search for custom wrappers in my project's hw_ips folder
  rdl_includes:
    - "custom_rdls" # Highest priority for PeakRDL includes
```

---

## 3. Dependency Registry (`dependencies`)

This section is the **Centralized Dependency Registry**. When an IP wrapper or a template requires an external repository (via the `// BENDER: name="my_ip"` pragma), Ollivander looks up `"my_ip"` in this dictionary to know where to fetch it and how to compile it.

Each key in the `dependencies` dictionary represents the name of the IP.

### 3.1 Git Resolution
| Field     | Type   | Description                                                                              |
| :-------- | :----- | :--------------------------------------------------------------------------------------- |
| `git`     | String | **Required**. The Git repository URL of the dependency.                                  |
| `version` | String | Specifies a semantic version to checkout (e.g., `"1.0.4"`).                              |
| `rev`     | String | Specifies a specific commit hash, branch, or tag to checkout (e.g., `"main"` or          |
|           |        | `"0ec0bf8"`).                                                                            |

*(Note: You must specify either `version` or `rev`, but not both).*

### 3.2 Compilation Targets (`bender_targets`)
Some IPs contain multiple implementations (e.g., FPGA vs ASIC) or optional sub-modules. Bender uses targets (`-t`) to select the right source files.

| Field            | Type            | Description                                                              |
| :--------------- | :-------------- | :----------------------------------------------------------------------- |
| `bender_targets` | List of Strings | A list of targets that will be automatically passed to `bender script    |
|                  |                 | vsim` when compiling the SoC (e.g., `["cva6", "fpga_synth"]`).           |

*Note: If you define `bender_targets` for an existing IP in your custom project environment file, it will **completely replace** the default targets defined in the base `ollivander_config.yml`. If you want to add a target while keeping the default ones, you must list both the default targets and your new target in your custom file.*

### 3.3 Pre-Build Tooling and Scripts
Sometimes an IP needs to generate some files, download models, or install python libraries *before* the RTL can be compiled or simulated. Ollivander handles this automatically in Python immediately after fetching the IPs via Bender.

| Field             | Type            | Description                                                             |
| :---------------- | :-------------- | :---------------------------------------------------------------------- |
| `pre_build_cmds`  | List of Strings | Inline shell commands to execute. You can use `{bender_work}`           |
|                   |                 | (downloaded IP directory) and `{ollivander_dir}` (Ollivander root       |
|                   |                 | directory) as placeholders. Macros like `$(PYTHON)` are supported.      |
| `pre_build_script`| String          | Path to an external script (`.sh`, `.py`, `.tcl`) to execute.           |
|                   |                 | Supports {bender_work}` and `{ollivander_dir}` placeholders.            |
|                   |                 | Ollivander automatically detects the extension and runs it with the     |
|                   |                 | correct interpreter.                                                    |

**Example of complex pre-build execution:**
```yaml
dependencies:
  idma:
    git: "https://github.com/pulp-platform/idma.git"
    version: "0.6.5"
    bender_targets:
      - "idma"
    pre_build_cmds:
      - "$(PYTHON) -m pip install -q flatdict mako"
      - "$(MAKE) -C {bender_work}/idma idma_hw_all BENDER=\"$(BENDER)\""
  
  my_custom_ip:
    git: "https://github.com/my-org/custom_ip.git"
    rev: "main"
    pre_build_script: "{bender_work}/my_custom_ip/scripts/setup.py"
```

### 3.4 On-the-fly Code Patching (`patches`)
If an external IP contains a bug, a missing import, or requires a small tweak to compile within your specific environment, you can instruct Ollivander to patch the source code automatically using simple text replacement.

| Field     | Type            | Description                                                              |
| :-------- | :-------------- | :----------------------------------------------------------------------- |
| `patches` | List of Objects | A list of text replacements to perform inside the fetched IP repository. |

**Patch Object:**
* `file`: The path to the file to modify (supports `{bender_work}` placeholder).
* `search`: The exact string to look for.
* `replace`: The string to insert in its place.

**Example of patching a file:**
```yaml
dependencies:
  opentitan:
    git: "https://github.com/AlSaqr-platform/opentitan.git"
    rev: "chips-it"
    patches:
      - file: "{bender_work}/opentitan/Bender.yml"
        search: "prim_flop_macros.svh"
        replace: "prim_flop_macros.sv"
```

---

## 4. Fast-Check Simulator Configuration (`fast_check_tool`)

Ollivander supports multiple verification backends for structural fast-check compilation validation. You can declare the simulator of choice directly in your environment configuration YAML file.

### 4.1 Configuration YAML Field
You can add `fast_check_tool` at the root level of your environment YAML file:

```yaml
# my_project_env.yaml
fast_check_tool: "verilator"  # Options: "questa" (default) or "verilator"
```

### 4.2 Configuration Precedence & Command-Line Override
1. **YAML Files**: Ollivander evaluates the base `ollivander_config.yml` first, and overrides it with your custom appended environment file (passed via `-a`). The resulting simulator is used when you run `make generate` to write the compilation script targets inside the output `Makefile.vsim`.
2. **Command Line**: You can override the tool selection at run-time without re-generating the codebase by passing `FAST_CHECK_TOOL` directly to the `make` command:
   ```bash
   make fast-check FAST_CHECK_TOOL=verilator
   ```

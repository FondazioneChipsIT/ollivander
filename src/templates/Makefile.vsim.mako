# ==============================================================================
# Auto-generated QuestaSim Makefile for ${config.project.name}
# ==============================================================================

OUT_DIR  ?= ${rel_outdir_path}
TOP_MOD  ?= ${config.project.name}
VSIM     ?= vsim
BENDER   ?= bender
PYTHON   ?= python3
MAKE     ?= make
<%
  # Base standard targets for simulation
  b_targets = ["rtl", "simulation", "sim", "test"]
  # Extract specific targets required by the dependencies defined in the environment
  for dep_name, dep_info in env_config.get('dependencies', {}).items():
      targets = dep_info.get('bender_targets', [])
      if isinstance(targets, list):
          b_targets.extend(targets)
      elif isinstance(targets, str):
          b_targets.append(targets)
          
  # Remove duplicates preserving order
  b_targets = list(dict.fromkeys(b_targets))
  bender_targets_str = " ".join([f"-t {t}" for t in b_targets])
%>\
BENDER_TARGETS ?= ${bender_targets_str}

BENDER_PREREQ :=
ifeq (, $(shell command -v $(BENDER) 2> /dev/null))
  BENDER = $(abspath ./bender)
  BENDER_PREREQ = $(BENDER)
endif

% if global_defines:
define INJECT_MACROS_SCRIPT
import sys
import re
with open(sys.argv[1], 'r') as f:
    d = f.read()
d = re.sub(r'\bvlog\b\s+', 'vlog ${" ".join(["+define+"+d for d in global_defines])} ', d)
with open(sys.argv[1], 'w') as f:
    f.write(d)
endef
export INJECT_MACROS_SCRIPT
% endif

$(abspath ./bender):
	@echo "\n[MAKE] Downloading Bender..."
	@curl --proto '=https' --tlsv1.2 -sSf https://fabianschuiki.github.io/bender/init | bash -s -- 0.31.0

.PHONY: prep-sim build-sim run-sim fast-check build-sw

# Force Bender to be downloaded before updating hardware dependencies
Bender.lock: $(BENDER_PREREQ)

# Create a state file to ensure Bender fetches dependencies only when needed
bender_work/.fetched: $(BENDER_PREREQ) Bender.yml
	@echo "\n[MAKE] Fetching dependencies via Bender..."
	@$(BENDER) checkout --force || true
% for dep_name, dep_info in env_config.get('dependencies', {}).items():
% if 'pre_build_cmds' in dep_info or 'pre_build_script' in dep_info:
	@if [ -d bender_work/${dep_name} ]; then \
		echo "  -> Checking if ${dep_name} needs pre-processing..."; \
% for cmd in dep_info.get('pre_build_cmds', []):
		echo "  -> Running: ${cmd.replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)}"; \
		${cmd.replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)}; \
% endfor
% if 'pre_build_script' in dep_info:
<%
        script_path = dep_info['pre_build_script'].replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)
        if script_path.endswith('.py'):
            exec_cmd = f"$(PYTHON) {script_path}"
        elif script_path.endswith('.sh'):
            exec_cmd = f"bash {script_path}"
        elif script_path.endswith('.tcl'):
            exec_cmd = f"if ! command -v tclsh >/dev/null 2>&1; then echo \"[ERROR] 'tclsh' is required to run {script_path} but was not found in PATH.\"; echo \"[HINT] Please install TCL (e.g., 'sudo apt-get install tcl').\"; exit 1; fi; tclsh {script_path}"
        else:
            exec_cmd = f"chmod +x {script_path} ; ./{script_path}"
%>\
		echo "  -> Executing script: ${script_path}"; \
		${exec_cmd}; \
% endif
	fi
% endif
% endfor
	@mkdir -p bender_work
	@touch bender_work/.fetched

update-hw: bender_work/.fetched

build-sw:
% if config.get("software_stack"):
	@echo "\n[MAKE] Compiling C firmware..."
	@$(MAKE) -C $(OUT_DIR)/sw all || { echo "\n[ERROR] Software compilation failed!"; exit 1; }
% else:
	@echo "\n[MAKE] No software stack configured. Skipping firmware compilation."
% endif

prep-sim: update-hw
	@echo "\n[MAKE] Extracting SystemVerilog compilation script for QuestaSim via Bender..."
	$(BENDER) script vsim $(BENDER_TARGETS) > $(OUT_DIR)/compile_vsim.tcl
% if global_defines:
	@echo "\n[MAKE] Injecting compilation macros (+define+) into QuestaSim script..."
	@python3 -c "$$INJECT_MACROS_SCRIPT" $(OUT_DIR)/compile_vsim.tcl
% endif

build-sim: prep-sim build-sw
	@echo "\n[MAKE] Compiling RTL with QuestaSim (vlog)..."
	$(VSIM) -c -do "if {[source $(OUT_DIR)/compile_vsim.tcl]} {quit -code 1}; quit"

fast-check: prep-sim
	@echo "\n[MAKE] Generating exact stubs for heavy external IPs..."
	@$(PYTHON) $(OLLIVANDER) -c $(SOC_YAML) $$(if [ -n "$(ENV_YAML)" ]; then echo "-a $(ENV_YAML)"; fi) -o $(OUT_DIR) --generate-stubs || { echo "\n[ERROR] Stub generation failed!"; exit 1; }
	@echo "\n[MAKE] Compiling fast RTL (packages and stubs) with QuestaSim..."
	$(VSIM) -c -do "source $(OUT_DIR)/compile_vsim_fast.tcl; quit"
	@echo "\n[MAKE] Elaborating top-level with Unresolved Blackboxes..."
	$(VSIM) -c -do "if {[catch {vopt -suppress 13314,2912,2241 +bbox_u ${config.project.name} -o ${config.project.name}_fast_check}]} {quit -code 1}; quit"
	@echo "\n[SUCCESS] Fast architecture check passed!"

run-sim:
	@echo "\n[MAKE] Running simulation in QuestaSim..."
	$(VSIM) -c tb_$(TOP_MOD) -suppress 13314 -do "run -all; quit"

gui:
	@echo "\n[MAKE] Launching QuestaSim GUI..."
	$(VSIM) -gui tb_$(TOP_MOD) -suppress 13314

# ==============================================================================
# OLLIVANDER AUTO-GENERATED HARDWARE MAKEFILE
# ==============================================================================
# This file contains the pre-build commands and patches required by external IPs.
# It is automatically executed before QuestaSim compilation.

BENDER ?= bender
PYTHON ?= python3

.PHONY: patch-ips
patch-ips:
% for dep_name, dep_info in env_config.get("dependencies", {}).items():
  % if "pre_build_cmds" in dep_info or "patches" in dep_info or "pre_build_script" in dep_info:
	@echo "[OLLIVANDER] Checking if ${dep_name} needs pre-processing..."
	@if [ -d "bender_work/${dep_name}" ]; then \
    % for patch in dep_info.get("patches", []):
		echo "  -> Patching ${patch['file'].replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)}" ; \
		sed -i 's/${patch['search']}/${patch['replace']}/g' ${patch['file'].replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)} || true ; \
    % endfor
    % for cmd in dep_info.get("pre_build_cmds", []):
		echo "  -> Running: ${cmd.replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)}" ; \
		${cmd.replace('{bender_work}', 'bender_work').replace('{ollivander_dir}', rel_ollivander_dir)} ; \
    % endfor
    % if "pre_build_script" in dep_info:
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
		echo "  -> Executing script: ${script_path}" ; \
		${exec_cmd} ; \
    % endif
	fi
  % endif
% endfor

# We make update-hw depend on patch-ips so it runs first, 
# before any other hardware generation targets (like regtool or floogen).
update-hw: patch-ips
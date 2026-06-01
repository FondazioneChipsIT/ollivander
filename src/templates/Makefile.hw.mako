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
  % if "pre_build_cmds" in dep_info or "patches" in dep_info:
	@echo "[OLLIVANDER] Checking if ${dep_name} needs pre-processing..."
	@if [ -d "bender_work/${dep_name}" ]; then \
    % for patch in dep_info.get("patches", []):
		echo "  -> Patching ${patch['file'].replace('{bender_work}', 'bender_work')}" ; \
		sed -i 's/${patch['search']}/${patch['replace']}/g' ${patch['file'].replace('{bender_work}', 'bender_work')} || true ; \
    % endfor
    % for cmd in dep_info.get("pre_build_cmds", []):
		echo "  -> Running: ${cmd.replace('{bender_work}', 'bender_work')}" ; \
		${cmd.replace('{bender_work}', 'bender_work')} ; \
    % endfor
	fi
  % endif
% endfor

# We make update-hw depend on patch-ips so it runs first, 
# before any other hardware generation targets (like regtool or floogen).
update-hw: patch-ips
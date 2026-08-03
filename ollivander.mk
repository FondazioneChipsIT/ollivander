# Copiright Fondazione Chips-IT
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#

# ==============================================================================
# OLLIVANDER SoC - MAIN WORKFLOW MAKEFILE
# ==============================================================================
# Instructions:
# 1. Copy this file to the root of your project and rename it to 'Makefile'.
# 2. Run 'make setup' to install the required Python dependencies.
# 3. Adjust the variables below to match your project's YAML files.
# 4. Run 'make generate' to build your SoC.

# --- Ollivander Python script path ---
OLLIVANDER := $(OLLIVANDER_ROOT)/src/ollivander.py

# --- Project Configurations ---
VENV_DIR   := $(OLLIVANDER_ROOT)/.venv

# --- User-definable variables ---
SOC_YAML   ?= $(OLLIVANDER_ROOT)/soc_cfg_examples/crossbar/crux.yaml
ENV_YAML   ?= $(OLLIVANDER_ROOT)/soc_cfg_examples/crossbar/crux_env.yaml
OUT_DIR    ?= $(OLLIVANDER_ROOT)/generated
REQS_FILE  := $(OLLIVANDER_ROOT)/requirements.txt
PYTHON     ?= $(VENV_DIR)/bin/python
HOST_PYTHON ?= python3.12

# --- Tools ---
VERIBLE_VERSION ?= v0.0-4080-ga0a8d8eb

# ==============================================================================
# EXTERNAL TOOL RESOLUTION (Environment Modules preferred, PATH as fallback)
# ==============================================================================
# Every target that needs an external tool opens with $(call ensure-tools,...),
# passing "tool:module" pairs. The rule, in order:
#   1. A module already loaded is never touched: that is the user's deliberate
#      choice, whatever version it carries.
#   2. Otherwise the module is loaded and reported. The module default wins over
#      whatever happens to sit on PATH - /usr/bin/verilator 4.028 shadowing the
#      5.x module is the failure that taught us a bare PATH probe is not enough,
#      and the questa module also carries the license variables.
#   3. A failed or unavailable module falls back to the tool on PATH, silently:
#      that is the whole story on a host without Environment Modules.
#   4. Where nothing provides the tool, one [WARN] names it, and the step that
#      needs it fails in its own log instead of three phases later.
# A hand-built tool outside the module system is honoured by overriding the tool
# variable instead (VSIM=, BENDER=, VERILATOR= are all '?=').
# The suite used to source modules.sh unconditionally at the head of a &&
# chain: on a host without Environment Modules that broke every helper defined
# after it, and per-project targets did not attempt the load at all.
define ensure-tools
	if [ -f /etc/profile.d/modules.sh ]; then \
		. /etc/profile.d/modules.sh; \
		for pair in $(1); do \
			tool=$${pair%%:*}; mod=$${pair##*:}; \
			case ":$$LOADEDMODULES:" in \
				*:$$mod/*|*:$$mod:*) ;; \
				*) { module load $$mod 2>/dev/null && echo "[MODULES] Loaded '$$mod' for '$$tool'"; } || \
					{ command -v $$tool >/dev/null 2>&1 || \
						echo "[WARN] '$$tool' is unavailable: not on PATH, and 'module load $$mod' failed"; }; \
				;; \
			esac; \
		done; \
	else \
		missing=""; \
		for pair in $(1); do \
			tool=$${pair%%:*}; \
			command -v $$tool >/dev/null 2>&1 || missing="$$missing $$tool"; \
		done; \
		if [ -n "$$missing" ]; then \
			echo "[WARN] Environment Modules not available on this host and not on PATH:$$missing"; \
		fi; \
	fi; \
	export PATH
endef

OS := $(shell uname -s)
ARCH := $(shell uname -m)

ifeq ($(OS),Linux)
	ifeq ($(ARCH),x86_64)
		VERIBLE_PLATFORM = linux-static-x86_64
	else ifneq (,$(filter $(ARCH),aarch64 arm64))
		VERIBLE_PLATFORM = linux-static-arm64
	else
		$(error Unsupported Linux architecture: $(ARCH))
	endif
else ifeq ($(OS),Darwin)
	VERIBLE_PLATFORM = macOS
else
	$(error Unsupported OS: $(OS))
endif

# --- Default Target ---
.PHONY: all
all: generate build-sim run-sim

# ==============================================================================
# 0. ENVIRONMENT SETUP
# ==============================================================================
.PHONY: setup
setup:
	@printf "\n[MAKE] Setting up Python virtual environment in $(VENV_DIR)...\n"
	@if command -v uv >/dev/null 2>&1; then \
		echo "  -> 'uv' detected. Fast installation enabled."; \
		uv venv $(VENV_DIR); \
		uv pip install -p $(PYTHON) -r $(REQS_FILE); \
	elif $(HOST_PYTHON) -m pip --version >/dev/null 2>&1; then \
		echo "  -> 'pip' detected. Creating standard venv..."; \
		$(HOST_PYTHON) -m venv $(VENV_DIR); \
		$(PYTHON) -m pip install --upgrade pip; \
		$(PYTHON) -m pip install -r $(REQS_FILE); \
	else \
		printf "\n[ERROR] Neither 'uv' nor 'pip' is available in your PATH.\n"; \
		exit 1; \
	fi
	@printf "\n[MAKE] Fetching Verible release $(VERIBLE_VERSION) for $(VERIBLE_PLATFORM)...\n"
	@URL=$$(curl -s https://api.github.com/repos/chipsalliance/verible/releases/tags/$(VERIBLE_VERSION) | grep browser_download_url | grep $(VERIBLE_PLATFORM) | cut -d '"' -f 4); \
	if [ -z "$$URL" ]; then \
		printf "\n[ERROR] Could not find Verible release for $(VERIBLE_PLATFORM)!\n"; \
		exit 1; \
	fi; \
	echo "  -> Downloading from $$URL..."; \
	curl -fLsSo verible.tar.gz "$$URL"; \
	echo "  -> Extracting binaries..."; \
	mkdir -p $(VENV_DIR)/verible_tmp; \
	tar -xzf verible.tar.gz --strip-components=1 -C $(VENV_DIR)/verible_tmp; \
	cp $(VENV_DIR)/verible_tmp/bin/verible-verilog-format $(VENV_DIR)/bin/; \
	cp $(VENV_DIR)/verible_tmp/bin/verible-verilog-syntax $(VENV_DIR)/bin/; \
	rm -rf $(VENV_DIR)/verible_tmp verible.tar.gz
	@printf "\n[SUCCESS] Environment and tools created. Activate it with: source $(VENV_DIR)/bin/activate\n"

# ==============================================================================
# 1. HARDWARE GENERATION
# ==============================================================================
.PHONY: generate
generate:
	@printf "\n[MAKE] Generating the SoC with Ollivander...\n"
	@if [ ! -f $(PYTHON) ]; then echo "[ERROR] Virtual environment not found. Run 'make setup' first."; exit 1; fi
	@$(call ensure-tools,bender:bender); \
	echo "$(PYTHON) $(OLLIVANDER) -c $(SOC_YAML) -a $(ENV_YAML) -o $(OUT_DIR)"; \
	$(PYTHON) $(OLLIVANDER) -c $(SOC_YAML) -a $(ENV_YAML) -o $(OUT_DIR)

# ==============================================================================
# 2. SIMULATION
# ==============================================================================
# Include the QuestaSim simulation targets ('build-sim' and 'run-sim')
# automatically generated by Ollivander. Hardware dependency fetching (Bender)
# is handled by the 'update-hw' target defined in that same generated makefile.
-include $(OUT_DIR)/Makefile.vsim

# ==============================================================================
# UTILITIES
# ==============================================================================
.PHONY: clean
clean:
	@printf "\n[MAKE] Cleaning generated files...\n"
	rm -rf $(OUT_DIR) Bender.yml Bender.lock Bender.local bender_work/ work/

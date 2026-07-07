# Copyright Fondazione Chips-IT
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# ==============================================================================
# OLLIVANDER MULTI-PROJECT TEST SUITE
# ==============================================================================
# Provides a regression test target similar to the olli_test utility.
#
# Variables:
#   TEST_PROJECTS     : List of projects to test (defaults to all examples)
#   TEST_CLEAN        : Clean project output directories first (1/0, default 0)
#   TEST_CLEAN_SETUP  : Recreate Python virtual environment first (1/0, default 0)
#   FAST_CHECK_TOOLS  : Tools to use for the fast-check (e.g. questa, verilator)
#   TEST_SIM          : Build and run simulation tests (1/0, default 0); requires QuestaSim module
#
# Usage:
#   make test-all TEST_CLEAN=1 FAST_CHECK_TOOLS="questa" TEST_SIM=1

SHELL := /bin/bash

TEST_PROJECTS    ?= crossbar crossbar_isle noc noc_isle noc_subtile super_crossbar super_noc
TEST_CLEAN       ?= 0
TEST_CLEAN_SETUP ?= 0
# Enable full testbench simulation run (compiles firmware, compiles simulator models,
# and executes the testbench in QuestaSim). Requires QuestaSim module.
TEST_SIM         ?= 0
FAST_CHECK_TOOLS ?= questa

MODULES_TO_LOAD := bender riscv-gcc
ifneq ($(filter questa,$(FAST_CHECK_TOOLS)),)
  MODULES_TO_LOAD += questa
endif
ifneq ($(filter verilator,$(FAST_CHECK_TOOLS)),)
  MODULES_TO_LOAD += verilator
endif

.PHONY: test-all
test-all:
	@echo "======================================================================"
	@echo "[TEST] Starting Ollivander Fast-Check Test Suite"
	@echo "  -> Project directories to test : $(TEST_PROJECTS)"
	@echo "  -> Fast-check tools            : $(FAST_CHECK_TOOLS)"
	@echo "  -> Run simulation              : $(TEST_SIM)"
	@echo "  -> Clean setup                 : $(TEST_CLEAN)"
	@echo "  -> Rebuild venv                : $(TEST_CLEAN_SETUP)"
	@echo "======================================================================"
	@. /etc/profile.d/modules.sh && module load $(MODULES_TO_LOAD) && \
	export PATH && \
	echo "[TEST] Loaded modules: $(MODULES_TO_LOAD)" && \
	echo "[DEBUG] PATH inside test-all recipe: \$\${PATH}" && \
	if [ "$(TEST_CLEAN_SETUP)" = "1" ]; then \
		echo "\n[TEST] Rebuilding Python virtual environment..."; \
		rm -rf $(VENV_DIR); \
		$(MAKE) -C $(OLLIVANDER_ROOT) setup || exit 1; \
	elif [ ! -f "$(PYTHON)" ]; then \
		echo "\n[TEST] Virtual environment not found. Running root 'make setup'..."; \
		$(MAKE) -C $(OLLIVANDER_ROOT) setup || exit 1; \
	fi; \
	echo "  -> Cleaning previous log files for selected projects..."; \
	rm -f soc_cfg_examples/test_summary.log; \
	for p in $(TEST_PROJECTS); do \
		rm -f soc_cfg_examples/$$p/*.log; \
	done; \
	echo "======================================================================" > soc_cfg_examples/test_summary.log; \
	echo "OLLIVANDER TEST SUITE SUMMARY - $$(date)" >> soc_cfg_examples/test_summary.log; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	echo "Project Directories Tested : $(TEST_PROJECTS)" >> soc_cfg_examples/test_summary.log; \
	echo "Tools Checked   : $(FAST_CHECK_TOOLS)" >> soc_cfg_examples/test_summary.log; \
	echo "Run Simulation  : $(TEST_SIM)" >> soc_cfg_examples/test_summary.log; \
	echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; \
	failed_tests=""; \
	for p in $(TEST_PROJECTS); do \
		yaml_path=$$(make -C soc_cfg_examples/$$p -pn | grep "^SOC_YAML :=" | cut -d "=" -f 2- | xargs); \
		yaml_file=$$(echo $$yaml_path | sed 's|^\.\./\.\./||'); \
		proj_name=""; \
		if [ -f "$$yaml_file" ]; then \
			if [[ "$$yaml_file" == *.py ]]; then \
				proj_name=$$(grep -E "name\s*=\s*\"[^\"]+\"" $$yaml_file | head -n 1 | sed -E 's/.*name\s*=\s*"([^"]+)".*/\1/' | xargs); \
			else \
				proj_name=$$(grep -A 2 "^project:" $$yaml_file | grep "name:" | sed -E 's/.*name:\s*"?([^"]*)"?.*/\1/' | xargs); \
			fi; \
		fi; \
		if [ -z "$$proj_name" ]; then \
			proj_name="$$p"; \
		fi; \
		echo "\n----------------------------------------------------------------------"; \
		echo "[TEST] Project: $$proj_name ($$p)"; \
		echo "----------------------------------------------------------------------"; \
		echo "Project: $$proj_name ($$p)" >> soc_cfg_examples/test_summary.log; \
		if [ ! -d "soc_cfg_examples/$$p" ]; then \
			echo "[ERROR] Project directory soc_cfg_examples/$$p does not exist!"; \
			failed_tests="$$failed_tests $$p"; \
			echo "  -> Status: FAILED (Directory not found)" >> soc_cfg_examples/test_summary.log; \
			echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; \
			continue; \
		fi; \
		if [ "$(TEST_CLEAN)" = "1" ]; then \
			echo "  -> Cleaning project $$proj_name..."; \
			$(MAKE) -C soc_cfg_examples/$$p clean > soc_cfg_examples/$$p/clean.log 2>&1 || exit 1; \
		fi; \
		echo "  -> Generating RTL for project $$proj_name..."; \
		if ! $(MAKE) -C soc_cfg_examples/$$p generate > soc_cfg_examples/$$p/generate.log 2>&1; then \
			echo "[ERROR] RTL generation failed for project $$proj_name! Check soc_cfg_examples/$$p/generate.log"; \
			echo "  -> RTL Generation: FAILED (Check soc_cfg_examples/$$p/generate.log)" >> soc_cfg_examples/test_summary.log; \
			echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; \
			failed_tests="$$failed_tests $$p(generate)"; \
			continue; \
		fi; \
		echo "  -> RTL Generation: SUCCESS" >> soc_cfg_examples/test_summary.log; \
		for tool in $(FAST_CHECK_TOOLS); do \
			echo "  -> Running fast-check with tool: $$tool..."; \
			if ! $(MAKE) -C soc_cfg_examples/$$p fast-check FAST_CHECK_TOOL=$$tool > soc_cfg_examples/$$p/fastcheck_$$tool.log 2>&1; then \
				echo "[ERROR] Fast-check failed for project $$proj_name with tool $$tool! Check soc_cfg_examples/$$p/fastcheck_$$tool.log"; \
				echo "  -> Fast-Check ($$tool): FAILED (Check soc_cfg_examples/$$p/fastcheck_$$tool.log)" >> soc_cfg_examples/test_summary.log; \
				failed_tests="$$failed_tests $$p($$tool)"; \
			else \
				echo "  -> Fast-Check ($$tool): SUCCESS" >> soc_cfg_examples/test_summary.log; \
			fi; \
		done; \
		if [ "$(TEST_SIM)" = "1" ]; then \
			if [ -f "soc_cfg_examples/$$p/generated/Makefile.vsim" ]; then \
				echo "  -> Compiling simulation for project $$proj_name..."; \
				if ! $(MAKE) -C soc_cfg_examples/$$p build-sim > soc_cfg_examples/$$p/build_sim.log 2>&1; then \
					echo "[ERROR] Simulation build failed for project $$proj_name! Check soc_cfg_examples/$$p/build_sim.log"; \
					echo "  -> Simulation Build: FAILED (Check soc_cfg_examples/$$p/build_sim.log)" >> soc_cfg_examples/test_summary.log; \
					failed_tests="$$failed_tests $$p(build-sim)"; \
				else \
					echo "  -> Simulation Build: SUCCESS" >> soc_cfg_examples/test_summary.log; \
					echo "  -> Running simulation for project $$proj_name..."; \
					if ! $(MAKE) -C soc_cfg_examples/$$p run-sim ASSERTIONS=0 > soc_cfg_examples/$$p/run_sim.log 2>&1; then \
						echo "[ERROR] Simulation run failed for project $$proj_name! Check soc_cfg_examples/$$p/run_sim.log"; \
						echo "  -> Simulation Run: FAILED (Check soc_cfg_examples/$$p/run_sim.log)" >> soc_cfg_examples/test_summary.log; \
						failed_tests="$$failed_tests $$p(run-sim)"; \
					else \
						echo "  -> Simulation Run: SUCCESS" >> soc_cfg_examples/test_summary.log; \
					fi; \
				fi; \
			else \
				echo "  [INFO] No simulation Makefile found for project $$p. Skipping simulation."; \
			fi; \
		fi; \
		echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; \
	done; \
	echo "\n======================================================================"; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	if [ -n "$$failed_tests" ]; then \
		echo "Final Result    : FAILED" >> soc_cfg_examples/test_summary.log; \
	else \
		echo "Final Result    : SUCCESS" >> soc_cfg_examples/test_summary.log; \
	fi; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	if [ -n "$$failed_tests" ]; then \
		echo "[ERROR] Test suite failed for the following configurations:$$failed_tests"; \
		echo "======================================================================"; \
		exit 1; \
	else \
		echo "[SUCCESS] All selected projects generated and checked successfully!"; \
		echo "======================================================================"; \
	fi

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

# ------------------------------------------------------------------------------
# Timing instrumentation
# ------------------------------------------------------------------------------
# The recipe below is a single shell command, so no in-line '#' comments are
# possible inside it (make joins the backslash-continued lines before handing
# them to the shell, and a '#' would swallow the remainder of the command).
# The three shell helpers defined at the top of the recipe are documented here:
#
#   fmt_dur <seconds>        : formats an elapsed number of seconds as HH:MM:SS.
#   log_step <label> <text>  : appends one column-aligned "  -> <label> : <text>"
#                              entry to test_summary.log.
#   close_project <start_ts>  : appends the per-project total time (computed from
#                              the timestamp taken right after the project header)
#                              followed by the project separator line. It is
#                              invoked on every exit path of the project loop,
#                              including the early 'continue' branches, so the
#                              total is always reported.
#
# Three timestamps drive the measurements:
#   suite_start : taken once, before any project is processed -> total suite time.
#   proj_start  : taken per project, right after its header    -> project total.
#   step_start  : taken before each step (clean / generate / fast-check /
#                 build-sim / run-sim) -> per-step duration, reported for both
#                 the SUCCESS and the FAILED outcome.
#
# Every step captures the sub-make exit status into step_rc instead of testing it
# inline with 'if ! $(MAKE) ...', so that the elapsed time can be computed once
# and reused by both branches.
#
# ------------------------------------------------------------------------------
# Missing project directories
# ------------------------------------------------------------------------------
# A project directory that does not exist is detected as the very first thing in
# the project loop, before the SOC_YAML introspection: 'make -C <missing dir>'
# would otherwise fail noisily on stderr before the clean diagnostic is printed.
# For the same reason the log-cleanup loop above only creates 'logs/' inside
# directories that already exist - an unconditional 'mkdir -p <p>/logs' would
# create the project directory itself and make the check unreachable.
# A missing directory is reported per project and does not abort the suite: the
# remaining projects are still processed and the final exit status is non-zero.
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
	fmt_dur() { printf "%02d:%02d:%02d" $$(($$1/3600)) $$(($$1%3600/60)) $$(($$1%60)); } && \
	log_step() { printf "  -> %-22s : %s\n" "$$1" "$$2" >> soc_cfg_examples/test_summary.log; } && \
	close_project() { log_step "Project Total Time" "$$(fmt_dur $$(( $$(date +%s) - $$1 )))"; echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; } && \
	suite_start=$$(date +%s) && \
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
		if [ -d "soc_cfg_examples/$$p" ]; then \
			rm -rf soc_cfg_examples/$$p/logs; \
			mkdir -p soc_cfg_examples/$$p/logs; \
		fi; \
	done; \
	echo "======================================================================" > soc_cfg_examples/test_summary.log; \
	echo "OLLIVANDER TEST SUITE SUMMARY - $$(date)" >> soc_cfg_examples/test_summary.log; \
	echo "Suite Start Epoch  : $$suite_start" >> soc_cfg_examples/test_summary.log; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	echo "Project Directories Tested : $(TEST_PROJECTS)" >> soc_cfg_examples/test_summary.log; \
	echo "Tools Checked   : $(FAST_CHECK_TOOLS)" >> soc_cfg_examples/test_summary.log; \
	echo "Run Simulation  : $(TEST_SIM)" >> soc_cfg_examples/test_summary.log; \
	echo "----------------------------------------------------------------------" >> soc_cfg_examples/test_summary.log; \
	failed_tests=""; \
	for p in $(TEST_PROJECTS); do \
		if [ ! -d "soc_cfg_examples/$$p" ]; then \
			proj_start=$$(date +%s); \
			echo "\n----------------------------------------------------------------------"; \
			echo "[TEST] Project: $$p"; \
			echo "----------------------------------------------------------------------"; \
			echo "[ERROR] Project directory soc_cfg_examples/$$p does not exist!"; \
			echo "Project: $$p" >> soc_cfg_examples/test_summary.log; \
			log_step "Status" "FAILED (Directory not found)"; \
			failed_tests="$$failed_tests $$p(missing-dir)"; \
			close_project $$proj_start; \
			continue; \
		fi; \
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
		proj_start=$$(date +%s); \
		if [ "$(TEST_CLEAN)" = "1" ]; then \
			echo "  -> Cleaning project $$proj_name..."; \
			mkdir -p soc_cfg_examples/$$p/logs; \
			step_start=$$(date +%s); \
			$(MAKE) -C soc_cfg_examples/$$p clean > soc_cfg_examples/$$p/logs/test_clean.log 2>&1 || exit 1; \
			log_step "Clean" "SUCCESS [$$(fmt_dur $$(( $$(date +%s) - step_start )))]"; \
		fi; \
		echo "  -> Generating RTL for project $$proj_name..."; \
		mkdir -p soc_cfg_examples/$$p/logs; \
		step_start=$$(date +%s); \
		$(MAKE) -C soc_cfg_examples/$$p generate > soc_cfg_examples/$$p/logs/test_generate.log 2>&1; \
		step_rc=$$?; \
		step_dur=$$(fmt_dur $$(( $$(date +%s) - step_start ))); \
		if [ $$step_rc -ne 0 ]; then \
			echo "[ERROR] RTL generation failed for project $$proj_name! Check soc_cfg_examples/$$p/logs/test_generate.log"; \
			log_step "RTL Generation" "FAILED [$$step_dur] (Check soc_cfg_examples/$$p/logs/test_generate.log)"; \
			failed_tests="$$failed_tests $$p(generate)"; \
			close_project $$proj_start; \
			continue; \
		fi; \
		log_step "RTL Generation" "SUCCESS [$$step_dur]"; \
		for tool in $(FAST_CHECK_TOOLS); do \
			echo "  -> Running fast-check with tool: $$tool..."; \
			mkdir -p soc_cfg_examples/$$p/logs; \
			step_start=$$(date +%s); \
			$(MAKE) -C soc_cfg_examples/$$p fast-check FAST_CHECK_TOOL=$$tool > soc_cfg_examples/$$p/logs/test_fastcheck_$$tool.log 2>&1; \
			step_rc=$$?; \
			step_dur=$$(fmt_dur $$(( $$(date +%s) - step_start ))); \
			if [ $$step_rc -ne 0 ]; then \
				echo "[ERROR] Fast-check failed for project $$proj_name with tool $$tool! Check soc_cfg_examples/$$p/logs/test_fastcheck_$$tool.log"; \
				log_step "Fast-Check ($$tool)" "FAILED [$$step_dur] (Check soc_cfg_examples/$$p/logs/test_fastcheck_$$tool.log)"; \
				failed_tests="$$failed_tests $$p($$tool)"; \
			else \
				log_step "Fast-Check ($$tool)" "SUCCESS [$$step_dur]"; \
			fi; \
		done; \
		if [ "$(TEST_SIM)" = "1" ]; then \
			if [ -f "soc_cfg_examples/$$p/generated/Makefile.vsim" ]; then \
				echo "  -> Compiling simulation for project $$proj_name..."; \
				mkdir -p soc_cfg_examples/$$p/logs; \
				step_start=$$(date +%s); \
				$(MAKE) -C soc_cfg_examples/$$p build-sim > soc_cfg_examples/$$p/logs/test_build_sim.log 2>&1; \
				step_rc=$$?; \
				step_dur=$$(fmt_dur $$(( $$(date +%s) - step_start ))); \
				if [ $$step_rc -ne 0 ]; then \
					echo "[ERROR] Simulation build failed for project $$proj_name! Check soc_cfg_examples/$$p/logs/test_build_sim.log"; \
					log_step "Simulation Build" "FAILED [$$step_dur] (Check soc_cfg_examples/$$p/logs/test_build_sim.log)"; \
					failed_tests="$$failed_tests $$p(build-sim)"; \
				else \
					log_step "Simulation Build" "SUCCESS [$$step_dur]"; \
					echo "  -> Running simulation for project $$proj_name..."; \
					mkdir -p soc_cfg_examples/$$p/logs; \
					step_start=$$(date +%s); \
					$(MAKE) -C soc_cfg_examples/$$p run-sim ASSERTIONS=0 > soc_cfg_examples/$$p/logs/test_run_sim.log 2>&1; \
					step_rc=$$?; \
					step_dur=$$(fmt_dur $$(( $$(date +%s) - step_start ))); \
					if [ $$step_rc -ne 0 ]; then \
						echo "[ERROR] Simulation run failed for project $$proj_name! Check soc_cfg_examples/$$p/logs/test_run_sim.log"; \
						log_step "Simulation Run" "FAILED [$$step_dur] (Check soc_cfg_examples/$$p/logs/test_run_sim.log)"; \
						failed_tests="$$failed_tests $$p(run-sim)"; \
					elif ! grep -q "\[UART\]:" soc_cfg_examples/$$p/logs/test_run_sim.log; then \
						echo "[ERROR] Simulation run completed but no UART output was detected for project $$proj_name! Check soc_cfg_examples/$$p/logs/test_run_sim.log"; \
						log_step "Simulation Run" "FAILED [$$step_dur] (No UART output detected)"; \
						failed_tests="$$failed_tests $$p(run-sim-no-uart)"; \
					else \
						log_step "Simulation Run" "SUCCESS [$$step_dur]"; \
					fi; \
				fi; \
			else \
				echo "  [INFO] No simulation Makefile found for project $$p. Skipping simulation."; \
				log_step "Simulation" "SKIPPED (no generated/Makefile.vsim)"; \
			fi; \
		fi; \
		close_project $$proj_start; \
	done; \
	suite_dur=$$(fmt_dur $$(( $$(date +%s) - suite_start ))); \
	echo "\n======================================================================"; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	if [ -n "$$failed_tests" ]; then \
		echo "Final Result    : FAILED" >> soc_cfg_examples/test_summary.log; \
	else \
		echo "Final Result    : SUCCESS" >> soc_cfg_examples/test_summary.log; \
	fi; \
	echo "Total Suite Time: $$suite_dur" >> soc_cfg_examples/test_summary.log; \
	echo "======================================================================" >> soc_cfg_examples/test_summary.log; \
	echo "[TEST] Total suite time: $$suite_dur"; \
	if [ -n "$$failed_tests" ]; then \
		echo "[ERROR] Test suite failed for the following configurations:$$failed_tests"; \
		echo "======================================================================"; \
		exit 1; \
	else \
		echo "[SUCCESS] All selected projects generated and checked successfully!"; \
		echo "======================================================================"; \
	fi

# ------------------------------------------------------------------------------
# check-tested: pre-commit guard
# ------------------------------------------------------------------------------
# Answers one question: is the code about to be committed the code the suite
# actually validated? It fails when the last suite did not end with SUCCESS, and
# when any source is newer than the moment that suite started - the case that
# keeps happening, a file edited while the regression was already running, which
# silently turns a green summary into a statement about code that no longer
# exists.
#
# Documentation is excluded: a Markdown edit cannot change generated RTL or a
# simulation outcome, and failing on one would only teach us to skip the check.
# Untracked-but-not-ignored files are included, since a component added after the
# suite ran is exactly as unvalidated as one edited after it ran.
#
# The scope of the run (projects, simulators, TEST_SIM) is printed rather than
# enforced: committing after a suite restricted to the affected projects is
# legitimate per the contribution rules, so the reader decides whether that scope
# was enough. This target never runs as part of test-all - it only reads the
# summary the suite writes.
.PHONY: check-tested
check-tested:
	@summary=soc_cfg_examples/test_summary.log; \
	if [ ! -f "$$summary" ]; then \
		echo "[CHECK] $$summary is missing: run 'make test-all' before committing."; \
		exit 1; \
	fi; \
	if ! grep -q "^Final Result    : SUCCESS" "$$summary"; then \
		echo "[CHECK] The last test suite did not end with SUCCESS:"; \
		grep -E "^Final Result|FAILED" "$$summary" | sed 's/^/    /'; \
		exit 1; \
	fi; \
	start=$$(sed -n 's/^Suite Start Epoch  : //p' "$$summary"); \
	if [ -z "$$start" ]; then \
		echo "[CHECK] $$summary predates this check: re-run 'make test-all'."; \
		exit 1; \
	fi; \
	newer=$$(git ls-files -z --cached --others --exclude-standard | tr '\0' '\n' | \
		grep -vE '^docs/|\.md$$' | \
		while IFS= read -r f; do \
			if [ -f "$$f" ] && [ "$$(stat -c %Y "$$f")" -gt "$$start" ]; then echo "    $$f"; fi; \
		done); \
	echo "[CHECK] Scope of the last suite:"; \
	grep -E "^Project Directories Tested|^Tools Checked|^Run Simulation" "$$summary" | sed 's/^/    /'; \
	if [ -n "$$newer" ]; then \
		echo "[CHECK] These sources changed after that suite started:"; \
		echo "$$newer"; \
		echo "[CHECK] The green summary no longer describes the current code: re-run 'make test-all'."; \
		exit 1; \
	fi; \
	echo "[CHECK] Suite ended with SUCCESS and nothing changed since it started."

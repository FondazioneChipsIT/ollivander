<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE SIMULATION MAKEFILE (QuestaSim + Verilator backends)
  # ============================================================================
  # This template generates the main simulation Makefile: the QuestaSim flow
  # (build-sim/run-sim/gui) and the license-free Verilator flow (*-verilator).
  # It dynamically aggregates compilation targets from the central environment
  # registry (BENDER_TARGETS), automates the extraction of the SystemVerilog 
  # compilation script via Bender, handles C firmware compilation, and provides
  # advanced features like macro injection and rapid RTL stubbing (fast-check).
%>
# ==============================================================================
# Auto-generated simulation Makefile for ${config.project.name}
# ==============================================================================

OUT_DIR  ?= ${rel_outdir_path}
TOP_MOD  ?= ${top_level_module_name}
VSIM     ?= vsim
BENDER   ?= bender
PYTHON   ?= python3
MAKE     ?= make
FAST_CHECK_TOOL ?= ${env_config.get("fast_check_tool", "questa")}
VERILATOR ?= verilator
VSIM_FLAGS ?= +fast_boot
# vopt optimizes fully by default in current Questa releases: the -O<num> levels were removed
# and passing one only earns a "(vopt-14495) '-O' option is obsolete, and will be ignored"
# note on every run. There is nothing left to hand to vopt for a batch run, and no
# optimization level to restore here - do not reintroduce one. The only remaining lever acts
# in the opposite direction (+acc, which lowers optimization to expose signals) and is used
# by the 'gui' target alone.
VSIM_OPT_FLAGS ?=

# Assertions control (set ASSERTIONS=0 to disable SVA)
ASSERTIONS ?= 1
ifeq ($(ASSERTIONS),0)
  VSIM_OPT_FLAGS += -nosva -noimmedassert -nopsl
endif

# ==============================================================================
# Verilator simulation flow - the license-free twin of build-sim / run-sim.
# Validated end-to-end on the noc example (identical UART output and EOT against
# a QuestaSim run of the same tree); the other example projects are covered by
# fast-check only so far.
# ==============================================================================
VERILATOR_JOBS ?= 48
# bender's 'script verilator' format implicitly defines TARGET_SYNTHESIS, which turns the
# olli_* simulation placeholders (the reset generator above all) into empty shells and
# silently holds the whole SoC in reset under two-state semantics: prep-sim-verilator
# strips that define from the file list.
#
# One single exclusion remains, and it is structural rather than a workaround: the
# behavioral pad cells model tristate with drive strengths (bufif1 (weak1, weak0)),
# which Verilator does not support - and does not need to, because the generated
# testbench elaborates the SoC top, not the chip top that carries the padframe. The
# cells are NOT dead code: the Padrick-generated padframe instantiates them and both
# are shipped, so they stay in the QuestaSim flow.
# Everything that used to be listed here instead - IP testbenches, class-based
# verification drivers, the astral pads - was dead in a generated SoC for BOTH
# simulators, and is now removed at the source, in each IP's manifest, from the
# dependency registry (2026-08-06). A tool-specific exclusion is the last resort: if
# a file is useless, it is useless to QuestaSim too.
VERILATOR_FLIST_EXCLUDE ?= behavioral/tc_pad\.sv
# scm_use_latch_scm: scm's manifest swaps its latch-based register files for FF
# equivalents under the 'verilator' target, but that branch misses
# register_file_1r_1w_test_wrap, which hier-icache instantiates (MODMISSING).
# Forcing the latch set keeps Verilator compiling the same scm sources as
# QuestaSim - the flow's byte-equivalence principle; inert where scm is absent.
VERILATOR_TARGETS ?= $(BENDER_TARGETS) -t verilator -t cv32e40p_exclude_tracer -t scm_use_latch_scm
# Flag rationale, all measured on the mesh example:
# - hierarchical verilation is the only build mode: repeated tiles verilate once as child
#   libraries (declared in the generated cfg/$(TOP_MOD).vlt) and the monolithic build costs
#   hours and tens of GB instead of minutes and ~3 GB per unit;
# - --threads is deliberately absent: it inflated verilation from minutes to hours per unit;
# - OPT_FAST=-O2 (vs the verilated.mk default -Os) is a run-time win whose compile cost
#   ccache absorbs; the explicit -std is needed because the installed Verilator module was
#   configured against the system g++ 8.5 and records no standard at all, while --timing
#   generates C++20 coroutine code;
# - -Wno-ENUMVALUE is the twin of run-sim's '-suppress 8386' (FlooNoC assigns the collective
#   opcode from raw flit bits; upstream PR candidate);
# - assertions are structurally off: no --assert, plus ASSERTS_OFF for the common_cells
#   macros - the superset of the ASSERTIONS=0 vsim knob, matching the test suite's default;
# - HCI_ASSERT_DELAY is defined empty for the same reason, one step further: hci_interfaces.sv
#   builds a 1 ps-skewed copy of the clock to sample its three protocol assertions, and a
#   delay of any kind inside a hierarchically verilated block is what Verilator refuses
#   ("Unsupported: --lib-create with --timing and delays"). It killed the nested macro tile of
#   super_noc after 35 minutes of build, and nowhere else: the same RTL is fine when it is the
#   top, which is why the crossbar family never saw it. With assertions off nothing reads that
#   skewed copy, so emptying the hook the IP itself provides removes the delay and no
#   behaviour with it - and the define is inert in the projects that do not pull hci in;
# - --relative-includes replicates vlog's include resolution (relative to the including
#   file): without it every IP whose manifest omits its own include dir parses under vlog
#   and dies under Verilator - softex and vendored ibex on the crossbar family;
# - the component-declared defines (the DEFINE: mechanism, e.g. FEATURE_ICACHE_STAT) are
#   appended below, mirroring what INJECT_MACROS_SCRIPT patches into every vlog call.
VERILATOR_SIM_FLAGS ?= --cc --main --build --hierarchical -j $(VERILATOR_JOBS) \
	--MAKEFLAGS "CFG_CXXFLAGS_STD=-std=gnu++20 OPT_FAST=-O2" \
	--timing --timescale 1ns/1ps -Wno-fatal -Wno-TIMESCALEMOD -Wno-ASCRANGE \
	-Wno-SYMRSVDWORD -Wno-ENUMVALUE --error-limit 200 +define+ASSERTS_OFF \
	+define+HCI_ASSERT_DELAY= \
	--relative-includes${(" " + " ".join(["+define+" + d for d in global_defines])) if global_defines else ""}
VERILATOR_RUN_FLAGS ?= +fast_boot
VERILATOR_WORK ?= verilator_work
# The C++20 coroutines require a modern compiler; RHEL hosts ship them as gcc-toolset SCLs.
# The newest installed toolset is sourced in the build recipe when the default g++ cannot
# compile <coroutine> on its own.
GCC_TOOLSET := $(lastword $(sort $(wildcard /opt/rh/gcc-toolset-*)))
<%
import os
os.makedirs("logs/debug", exist_ok=True)
with open("logs/debug/debug_testbench.txt", "w") as f:
    f.write(f"cwd: {os.getcwd()}\n")
    f.write(f"config.testbench: {config.testbench}\n")
%>
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
  # Filter out FPGA-specific target for simulation
  b_targets = [t for t in b_targets if t != "scm_use_fpga_scm"]
  bender_targets_str = " ".join([f"-t {t}" for t in b_targets])
%>\
BENDER_TARGETS ?= ${bender_targets_str}

# Fallback when bender is neither on PATH nor loadable as a module: it is installed
# into the generator's virtual environment bin/, the same place getting_started.md
# tells a user to put a manual install - never into the project directory, where the
# 2026-08-07 audit found a stray binary polluting git status (it is not ignored there,
# and the installer's tarball timestamps make it look months old).
BENDER_PREREQ :=
ifeq (, $(shell command -v $(BENDER) 2> /dev/null))
  BENDER = $(OLLIVANDER_ROOT)/.venv/bin/bender
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

$(OLLIVANDER_ROOT)/.venv/bin/bender:
	@printf "\n[MAKE] Bender not found on PATH: installing 0.31.0 into the virtual environment...\n"
	@mkdir -p $(OLLIVANDER_ROOT)/.venv/bin
	@cd $(OLLIVANDER_ROOT)/.venv/bin && curl --proto '=https' --tlsv1.2 -sSf https://fabianschuiki.github.io/bender/init | bash -s -- 0.31.0

.PHONY: prep-sim build-sim run-sim fast-check build-sw prep-sim-verilator build-sim-verilator run-sim-verilator

# Force Bender to be downloaded before updating hardware dependencies
Bender.lock: $(BENDER_PREREQ)

# Create a state file to ensure Bender fetches dependencies only when needed
bender_work/.fetched: $(BENDER_PREREQ) Bender.yml
	@mkdir -p bender_work
	@touch bender_work/.fetched

update-hw: bender_work/.fetched

<%
  sw_toolchain = (config.get("software_stack") or {}).get("toolchain", "riscv64-unknown-elf-")
%>\
build-sw:
% if config.get("software_stack"):
	@printf "\n[MAKE] Compiling C firmware...\n"
	@$(call ensure-tools,${sw_toolchain}gcc:riscv-gcc); \
	$(MAKE) -C $(OUT_DIR)/sw all || { printf "\n[ERROR] Software compilation failed!\n"; exit 1; }
<%
testbench_cfg = config.testbench or {}
preload_mems = testbench_cfg.get("preload_memories", [])
app_name = config.get("software_stack", {}).get("test_app", {}).get("name", "hello_world")
all_comps = [config.host] + (config.components if config.components else [])

def find_component(comp_name, config):
    if config.topology.type == "noc" and "i_tile_" in comp_name:
        parts = comp_name.split('.')
        tile_part = [p for p in parts if p.startswith("i_tile_")]
        if tile_part:
            tile_sub = tile_part[0].replace("i_tile_", "")
            coords = tile_sub.split('_')
            if len(coords) >= 2:
                try:
                    tx, ty = int(coords[0]), int(coords[1])
                    comps = [config.host] + (config.components if config.components else [])
                    for c in comps:
                        p = getattr(c, 'placement', None)
                        if not p or 'logical' not in p: continue
                        log = p['logical']
                        items = log if isinstance(log, list) else [log]
                        for item in items:
                            if 'box' in item:
                                b = item['box']
                                if b['x_start'] <= tx <= b['x_end'] and b['y_start'] <= ty <= b['y_end']:
                                    return c
                            else:
                                if (item or {}).get('x') == tx and (item or {}).get('y') == ty:
                                    return c
                except ValueError:
                    pass
    clean_name = comp_name
    if '.' in clean_name:
        clean_name = clean_name.split('.')[0]
    if clean_name.startswith("i_"):
        clean_name = clean_name[2:]
    for comp in config.components:
        if comp.name == clean_name:
            return comp
    return None

def resolve_param_val(val, comp, fixed_params=None, extra_params=None):
    import re
    if not val:
        return 0
    if str(val).isdigit():
        return int(val)
    params = {}
    if comp and comp.parameters:
        params.update(comp.parameters)
    if fixed_params:
        for k, v in fixed_params.items():
            if k not in params:
                params[k] = v
    # Values that are module *parameters* rather than localparams never appear in
    # fixed_params, so an expression referring to them (for example the memory size in
    # PreloadBanksPerGroup) cannot be evaluated from the parsed wrapper alone. The caller
    # supplies them here, already resolved for this specific instance.
    if extra_params:
        params.update(extra_params)
    if "AxiDataWidth" not in params:
        if config.topology.type == "noc":
            interfaces = getattr(comp, "interfaces", {}) or {}
            noc_nets = interfaces.get("noc_networks", {}) or {}
            noc_mode = noc_nets.get("noc_mode", "")
            slv_nets = noc_nets.get("slave", [])
            mst_nets = noc_nets.get("master", [])
            if "wide" in slv_nets or "wide" in mst_nets or noc_mode == "joined":
                params["AxiDataWidth"] = 512
            else:
                params["AxiDataWidth"] = 64
        else:
            params["AxiDataWidth"] = 64
    val_str = str(val)
    for pk, pv in params.items():
        val_str = re.sub(rf'\b{pk}\b', str(pv), val_str)
    val_str = re.sub(rf'\(int unsigned\)|\(int\)', '', val_str)
    try:
        val_str = val_str.replace('/', '//')
        return int(eval(val_str, {"__builtins__": None}, {}))
    except Exception:
        # The expression still holds unresolved symbols. Falling back to the first integer
        # found in it yields an arbitrary number that merely looks plausible, so warn
        # loudly: a silently wrong preload geometry is far harder to diagnose downstream
        # than a missing parameter here.
        print(f"[WARN] Could not evaluate parameter expression '{val}' for "
              f"'{getattr(comp, 'name', '?')}'; it resolved to '{val_str}'. "
              f"Falling back to the first literal found, which is very likely wrong.")
        digits = re.findall(r'\d+', val_str)
        if digits:
            return int(digits[0])
        return 1

# Query explicit HasEcc and EccType properties from the memory component wrappers
has_ecc = False
ecc_scheme = "none"
for mem in preload_mems:
    comp_name = mem['instance']
    clean_name = comp_name[2:] if comp_name.startswith("i_") else comp_name
    c_info = comp_info.get(comp_name) or comp_info.get(clean_name) or {}
    fixed_params = c_info.get("fixed_params") or {}
    if fixed_params.get("HasEcc", "0").strip('"\'') == "1":
        has_ecc = True
        ecc_scheme = fixed_params.get("EccType", "none").strip('"\'')
        break
%>
  % for mem in preload_mems:
    <%
    comp_name = mem['instance']
    matched_comp = find_component(comp_name, config)
    comp_key = matched_comp.name if matched_comp else comp_name
    c_info = comp_info.get(comp_name) or comp_info.get(comp_key) or {}
    fixed_params = c_info.get("fixed_params") or {}
    supported_params = c_info.get("supported_params") or {}
    preload_type = fixed_params.get("PreloadType", "").strip('"\'')
    os.makedirs("logs/debug", exist_ok=True)
    with open("logs/debug/debug_vsim.txt", "a") as f:
        f.write(f"mem={mem}, matched_comp={matched_comp.name if matched_comp else None}, preload_type={preload_type}\n")
    %>
    % if preload_type == "interleaved":
      <%
      bank_width = resolve_param_val(fixed_params.get("PreloadBankWidth"), matched_comp, fixed_params)
      data_width = resolve_param_val("AxiDataWidth", matched_comp, fixed_params)
      mem_size = None
      if matched_comp:
          mem_size = (matched_comp.parameters or {}).get("MemSize") or (matched_comp.parameters or {}).get("InstanceWindowSize")
          if not mem_size:
              for slv in matched_comp.interfaces.get("axi_slave", []):
                  mem_size = slv.get("size", mem_size)
      mem_size = resolve_param_val(fixed_params.get("InstanceWindowSize") or mem_size, matched_comp, fixed_params)
      base_addr = "0x78000000"
      if matched_comp:
          for slv in matched_comp.interfaces.get("axi_slave", []):
               base_addr = slv.get("base_addr", base_addr)
      # The memory size resolved just above is the authoritative one for this instance and
      # is what the wrapper's own parameters carry; expose it under every name the isles
      # use for it, so that expressions like PreloadBanksPerGroup evaluate correctly.
      size_params = {"InstanceWindowSize": mem_size, "SpmTileSize": mem_size, "MemSize": mem_size}
      num_groups = resolve_param_val(fixed_params.get("PreloadNumGroups"), matched_comp, fixed_params, size_params)
      num_banks_per_group = resolve_param_val(fixed_params.get("PreloadBanksPerGroup"), matched_comp, fixed_params, size_params)
      # Physical interleaving scheme of the memory, declared by the isle itself via the
      # PreloadInterleave localparam. Legacy isles that do not declare it keep the historical
      # "word-group" behaviour (l2_isle / l2_top), so old components stay bit-identical.
      interleave = (fixed_params.get("PreloadInterleave") or "word-group").strip('"\'')
      %>
	@if [ -f ../../src/core/split_hex.py ]; then \
		echo "  -> Splitting hex for interleaved preloading: ${comp_name}..."; \
		$(PYTHON) ../../src/core/split_hex.py $(OUT_DIR)/sw/${app_name}.hex $(OUT_DIR)/sw/ \
			--base-addr ${base_addr} \
			--num-groups ${num_groups} \
			--data-width ${data_width} \
			--bank-width ${bank_width} \
			--mem-size ${mem_size} \
			--num-banks-per-group ${num_banks_per_group} \
			--interleave ${interleave} \
			${f"--ecc-scheme {ecc_scheme} --ecc-dir {ecc_schemes_dir}" if has_ecc else ""}; \
	fi
    % endif
  % endfor
% else:
	@printf "\n[MAKE] No software stack configured. Skipping firmware compilation.\n"
% endif

prep-sim: update-hw
	@printf "\n[MAKE] Extracting SystemVerilog compilation script via Bender...\n"
	@# -timescale gives a DEFAULT to compilation units that declare none (the
	@# warning-3009 class): without it Questa maps their delays to the simulator
	@# resolution, and a "#(20ns/2)" clock generator or a "#TT" sampling delay
	@# silently runs a thousand times too fast. Found the hard way in wip 2.1:
	@# the JTAG VIP's TCK ran at 20 ps and the riscv-dbg jtag_test driver
	@# sampled TDO at +15 ps, reading every DMI bit one cycle early. Units that
	@# declare their own timescale are unaffected.
	$(BENDER) script vsim $(BENDER_TARGETS) --vlog-arg="-timescale 1ns/1ps" > $(OUT_DIR)/compile_vsim.tcl
% if global_defines:
	@printf "\n[MAKE] Injecting compilation macros (+define+) into compilation script...\n"
	@python3 -c "$$INJECT_MACROS_SCRIPT" $(OUT_DIR)/compile_vsim.tcl
% endif

build-sim: prep-sim build-sw
	@printf "\n[MAKE] Compiling RTL with QuestaSim (vlog)...\n"
	@mkdir -p logs
	@$(call ensure-tools,vsim:questa); \
	$(VSIM) -c -l logs/compile.log -suppress 13233 -do "set err [source $(OUT_DIR)/compile_vsim.tcl]; if {\$$err == 1} {quit -code 1}; quit"

fast-check: prep-sim
	@printf "\n[MAKE] Generating exact stubs for external IPs...\n"
	@FAST_CHECK_TOOL=$(FAST_CHECK_TOOL) $(PYTHON) $(OLLIVANDER) -c $(SOC_YAML) $$(if [ -n "$(ENV_YAML)" ]; then echo "-a $(ENV_YAML)"; fi) -o $(OUT_DIR) --generate-stubs || { printf "\n[ERROR] Stub generation failed!\n"; exit 1; }
	@$(call ensure-tools,$(if $(filter verilator,$(FAST_CHECK_TOOL)),verilator:verilator,vsim:questa)); \
	if [ "$(FAST_CHECK_TOOL)" = "verilator" ]; then \
		printf "\n[MAKE] Linting/Checking fast RTL with Verilator...\n"; \
		$(VERILATOR) -Wno-TIMESCALEMOD -Wno-ASCRANGE -Wno-SYMRSVDWORD -f $(OUT_DIR)/compile_verilator_fast.f --top-module $(TOP_MOD); \
	else \
		printf "\n[MAKE] Compiling fast RTL (packages and stubs) with QuestaSim...\n"; \
		mkdir -p logs; \
		$(VSIM) -c -l logs/fast_compile.log -suppress 13233 -do "source $(OUT_DIR)/compile_vsim_fast.tcl; quit"; \
		printf "\n[MAKE] Elaborating top-level with Unresolved Blackboxes...\n"; \
		: '13314 and 13233 are noise: relaxed SV input port kind, and a design unit'; \
		: 'overwriting an earlier one in the library, which is normal with Bender.'; \
		: 'Message 2912 (port connected by name does not exist) and 2241 (connection'; \
		: 'width differs from the port) are deliberately NOT suppressed: checking that'; \
		: 'the generated wrappers match the IP signatures is the whole purpose of this'; \
		: 'stub-based elaboration, and those two are the errors that report a mismatch.'; \
		$(VSIM) -c -l logs/fast_check.log -do "if {[catch {vopt -suppress 13314,13233 +bbox_u ${top_level_module_name} -o ${top_level_module_name}_fast_check}]} {quit -code 1}; quit"; \
	fi
	@printf "\n[SUCCESS] Fast architecture check passed!\n"

run-sim:
	@printf "\n[MAKE] Running simulation in QuestaSim...\n"
	@# Message severity policy. Only genuine third-party noise is hidden; anything that can
	@# report a defect in the generated code stays visible. See section 3 of
	@# docs/developer/wip/future_evolution_tasks.md for the open items behind these choices.
	@#
	@# Suppressed - unavoidable noise from external IPs, hundreds of lines per run:
	@# - 13314: An SV input port declared with a type but without 'var' defaults to 'wire'
	@#          only under -svinputport=relaxed. Pure LRM strictness, no design impact.
	@# - 3009 : Module without a timescale directive in effect: it falls back to the
	@#          simulator resolution limit (e.g. hci, ibex).
	@# - 8386 : An enum variable assigned a raw vector without an explicit cast. On a NoC
	@#          with collectives enabled, FlooNoC does this ~250 times per run while
	@#          extracting 'collective_op' from the flit header (floo_reduction_unit,
	@#          floo_reduction_arbiter, floo_output_arbiter, floo_router, floo_nw_chimney).
	@#          Suppressed for volume alone: it means nobody checks that the collective
	@#          opcode carried in a flit is a legal enum value, and deserves an upstream fix.
	@#
	@# Downgraded to a warning rather than suppressed - it reports a silently dropped
	@# parameter override, which is precisely the defect class a generator produces:
	@# - 2732 : A parameter override names a parameter the target module does not declare,
	@#          so the override is discarded and the module keeps its default. This used to
	@#          be suppressed and was hiding every such case (crux: 2, mesh: 10). Kept
	@#          visible, kept non-fatal, so the run still reaches EOT.
	@#
	@# Deliberately NOT suppressed any more: 3999 (incompatible port type) and 8602
	@# (zero replication multiplier) produced no message at all on either crux or mesh.
	@# Clear cached optimized designs before every simulation launch: vsim's
	@# auto-vopt staleness check is unreliable - it reloaded pre-recompile
	@# images repeatedly on 2026-08-16 ("Loading existing optimized design"),
	@# silently simulating code that no longer existed. Re-optimizing on every
	@# run costs minutes; trusting a stale image costs a debugging day.
	@rm -rf work/_opt* 2>/dev/null || true
	@mkdir -p logs/stdout
	@ln -snf ../generated logs/generated
	@$(call ensure-tools,vsim:questa); \
	cd logs && $(VSIM) -c -lib ../work tb_$(TOP_MOD) $(VSIM_FLAGS) $(VSIM_OPT_FLAGS) -suppress 13314,3009,8386 -warning 2732 -do "run -all; quit"

gui:
	@printf "\n[MAKE] Launching QuestaSim GUI...\n"
	@# Same message severity policy as run-sim above, kept identical on purpose so that a
	@# failure reproduced in the GUI reports exactly what the batch run reported.
	@#
	@# Unlike the batch run, the interactive session is elaborated with -voptargs=+acc, which
	@# lowers vopt's optimization to keep internal signals accessible. It makes the simulation
	@# slower but lets signals be logged and waveforms be added without recompiling, which is
	@# the point of opening the GUI in the first place.
	@mkdir -p logs/stdout
	@ln -snf ../generated logs/generated
	@# Clear cached optimized designs before every simulation launch: vsim's
	@# auto-vopt staleness check is unreliable - it reloaded pre-recompile
	@# images repeatedly on 2026-08-16 ("Loading existing optimized design"),
	@# silently simulating code that no longer existed. Re-optimizing on every
	@# run costs minutes; trusting a stale image costs a debugging day.
	@rm -rf work/_opt* 2>/dev/null || true
	@$(call ensure-tools,vsim:questa); \
	cd logs && $(VSIM) -gui -lib ../work tb_$(TOP_MOD) $(VSIM_FLAGS) $(VSIM_OPT_FLAGS) -voptargs=+acc -suppress 13314,3009,8386 -warning 2732

prep-sim-verilator: update-hw
	@printf "\n[MAKE] Extracting Verilator file list via Bender...\n"
	@# TARGET_SYNTHESIS is stripped (see VERILATOR_FLIST_EXCLUDE comment above), and the
	@# +incdir entries are separated out: bender interleaves them per package, but the
	@# hierarchical child invocations only inherit include paths passed on the command line.
	$(BENDER) script verilator $(VERILATOR_TARGETS) | grep -vE "$(VERILATOR_FLIST_EXCLUDE)" | grep -v '^+define+TARGET_SYNTHESIS' > $(OUT_DIR)/compile_verilator.f
	@grep '^+incdir+' $(OUT_DIR)/compile_verilator.f | sort -u > $(OUT_DIR)/verilator_incdirs.f
	@grep -v '^+incdir+' $(OUT_DIR)/compile_verilator.f > $(OUT_DIR)/compile_verilator_src.f
	@# The license-free flow has no VHDL front-end, and bender's verilator script
	@# silently drops .vhd sources: every VHDL entity of the graph (the CTU CAN FD
	@# APB wrapper is the only one today) is replaced by an auto-generated SV stub
	@# with tied-low outputs - the flow's one declared coverage loss
	@# (docs/getting_started.md, section 8.3). The stubs land outside every
	@# Bender-visible tree and enter this file list alone: the QuestaSim flows
	@# keep simulating the true mixed-language sources.
	@$(BENDER) script flist $(VERILATOR_TARGETS) | grep -iE '\.vhdl?$$' > $(OUT_DIR)/vhdl_sources.f || true
	@if [ -s $(OUT_DIR)/vhdl_sources.f ]; then \
		$(PYTHON) $(OLLIVANDER_ROOT)/scripts/gen_vhdl_stubs.py $(OUT_DIR)/vhdl_sources.f $(OUT_DIR)/vhdl_stubs && \
		ls $(OUT_DIR)/vhdl_stubs/*.sv 2>/dev/null >> $(OUT_DIR)/compile_verilator_src.f || true; \
	fi

build-sim-verilator: prep-sim-verilator build-sw
	@printf "\n[MAKE] Building Verilator model (hierarchical)...\n"
	@# Three steps, because in hierarchical mode verilator's own --build stops at the child
	@# libraries and the model archive: the top makefile's default target is the library, so
	@# the executable link is issued explicitly. The link avoids -latomic (absent from the
	@# gcc-toolset SCLs, unnecessary on x86_64).
	@$(call ensure-tools,verilator:verilator); \
	if [ -n "$(GCC_TOOLSET)" ] && ! echo '#include <coroutine>' | g++ -std=gnu++20 -x c++ -fsyntax-only - >/dev/null 2>&1; then . $(GCC_TOOLSET)/enable; fi; \
	$(VERILATOR) $(VERILATOR_SIM_FLAGS) --top-module tb_$(TOP_MOD) --Mdir $(VERILATOR_WORK) \
		$(OUT_DIR)/cfg/$(TOP_MOD).vlt $$(cat $(OUT_DIR)/verilator_incdirs.f) +incdir+$(abspath $(OUT_DIR)/hw) \
		-f $(OUT_DIR)/compile_verilator_src.f && \
	$(MAKE) -C $(VERILATOR_WORK) -f Vtb_$(TOP_MOD).mk CFG_CXXFLAGS_STD=-std=gnu++20 OPT_FAST=-O2 -j $(VERILATOR_JOBS) && \
	cd $(VERILATOR_WORK) && g++ -o Vtb_$(TOP_MOD) Vtb_$(TOP_MOD)__main.o \
		-Wl,--start-group libVtb_$(TOP_MOD).a Vtb_$(TOP_MOD)__ALL.a libverilated.a $$(ls V*/lib*.a 2>/dev/null) -Wl,--end-group \
		-lpthread -lm
	@printf "\n[SUCCESS] Verilator model built: $(VERILATOR_WORK)/Vtb_$(TOP_MOD)\n"

run-sim-verilator:
	@printf "\n[MAKE] Running Verilator simulation...\n"
	@# Runs from logs/ through the same 'generated' symlink as run-sim, so the testbench's
	@# relative $$readmemh paths resolve identically on both backends. The pass criterion is
	@# unchanged: '[UART]:' output plus '[TB] EOT received.' in the transcript.
	@mkdir -p logs/stdout
	@ln -snf ../generated logs/generated
	@cd logs && set -o pipefail && ../$(VERILATOR_WORK)/Vtb_$(TOP_MOD) $(VERILATOR_RUN_FLAGS) 2>&1 | tee verilator_transcript

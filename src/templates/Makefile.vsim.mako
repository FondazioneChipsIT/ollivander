<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE QUESTASIM MAKEFILE
  # ============================================================================
  # This template generates the main simulation Makefile for QuestaSim.
  # It dynamically aggregates compilation targets from the central environment
  # registry (BENDER_TARGETS), automates the extraction of the SystemVerilog 
  # compilation script via Bender, handles C firmware compilation, and provides
  # advanced features like macro injection and rapid RTL stubbing (fast-check).
%>
# ==============================================================================
# Auto-generated QuestaSim Makefile for ${config.project.name}
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
	@printf "\n[MAKE] Downloading Bender...\n"
	@curl --proto '=https' --tlsv1.2 -sSf https://fabianschuiki.github.io/bender/init | bash -s -- 0.31.0

.PHONY: prep-sim build-sim run-sim fast-check build-sw

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
          mem_size = (matched_comp.parameters or {}).get("MemSize") or (matched_comp.parameters or {}).get("L2MemSize")
          if not mem_size:
              for slv in matched_comp.interfaces.get("axi_slave", []):
                  mem_size = slv.get("size", mem_size)
      mem_size = resolve_param_val(fixed_params.get("L2MemSize") or mem_size, matched_comp, fixed_params)
      base_addr = "0x78000000"
      if matched_comp:
          for slv in matched_comp.interfaces.get("axi_slave", []):
               base_addr = slv.get("base_addr", base_addr)
      # The memory size resolved just above is the authoritative one for this instance and
      # is what the wrapper's own parameters carry; expose it under every name the isles
      # use for it, so that expressions like PreloadBanksPerGroup evaluate correctly.
      size_params = {"L2MemSize": mem_size, "SpmTileSize": mem_size, "MemSize": mem_size}
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
	$(BENDER) script vsim $(BENDER_TARGETS) > $(OUT_DIR)/compile_vsim.tcl
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
	@$(call ensure-tools,vsim:questa); \
	cd logs && $(VSIM) -gui -lib ../work tb_$(TOP_MOD) $(VSIM_FLAGS) $(VSIM_OPT_FLAGS) -voptargs=+acc -suppress 13314,3009,8386 -warning 2732

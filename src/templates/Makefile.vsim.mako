# ==============================================================================
# Auto-generated QuestaSim Makefile for ${config.project.name}
# ==============================================================================

OUT_DIR  ?= ${rel_outdir_path}
TOP_MOD  ?= ${config.project.name}
VSIM     ?= vsim
BENDER   ?= bender
BENDER_TARGETS ?= -t rtl -t simulation -t sim -t test -t cva6 -t cv32e40p_use_ff_regfile -t scm_use_fpga_scm -t cv64a6splus_imafdc_sv39_hpdcache_wb -t cv64a6_imafdc_sv39 -t idma -t use_idma -t snitch_cluster -t deprecated -t carfield_secure_periph -t spatz -t cheshire

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

.PHONY: prep-sim build-sim run-sim fast-check

# Force Bender to be downloaded before updating hardware dependencies
Bender.lock: $(BENDER_PREREQ)

prep-sim: update-hw $(BENDER_PREREQ)
	@echo "\n[MAKE] Fetching dependencies and generating IPs..."
	@$(BENDER) checkout --force || true
	@echo "\n[MAKE] Applying patch to OpenTitan manifest..."
	@sed -i 's/prim_flop_macros.svh/prim_flop_macros.sv/g' bender_work/opentitan/Bender.yml || true
	@mkdir -p bender_work/idma/target/rtl/include
	@mkdir -p bender_work/cheshire/target/sim/models
	@touch bender_work/cheshire/target/sim/models/s25fs512s.v
	@touch bender_work/cheshire/target/sim/models/24FC1025.v
	@echo "\n[MAKE] Installing on-the-fly Python dependencies for IP generation..."
	@. .venv/bin/activate && pip install -q flatdict mako
	@. .venv/bin/activate && $(MAKE) -C bender_work/idma idma_hw_all BENDER="$(BENDER)"
	@echo "\n[MAKE] Extracting SystemVerilog compilation script for QuestaSim via Bender..."
	$(BENDER) script vsim $(BENDER_TARGETS) > $(OUT_DIR)/compile_vsim.tcl
% if global_defines:
	@echo "\n[MAKE] Injecting compilation macros (+define+) into QuestaSim script..."
	@python3 -c "$$INJECT_MACROS_SCRIPT" $(OUT_DIR)/compile_vsim.tcl
% endif

build-sim: prep-sim
	@echo "\n[MAKE] Compiling RTL with QuestaSim (vlog)..."
	$(VSIM) -c -do "if {[source $(OUT_DIR)/compile_vsim.tcl]} {quit -code 1}; quit"

define GEN_STUBS_SCRIPT
import os, re, glob

# 1. Auto-discover target boundary modules from our generated wrappers
our_files = glob.glob('${rel_outdir_path}/hw/*.sv')
defined_modules = set()
inst_modules = set()
for f in our_files:
    if 'stubs.sv' in f: continue
    try:
        content = open(f, 'r', encoding='utf-8').read()
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        for m in re.finditer(r'\bmodule\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', clean):
            defined_modules.add(m.group(1))
        for m in re.finditer(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:#\s*\([^;]*?\)\s*)?[a-zA-Z_][a-zA-Z0-9_]*\s*(?:\[[^;]*?\]\s*)?\(', clean, flags=re.MULTILINE):
            inst_modules.add(m.group(1))
    except: pass
keywords = {'if', 'case', 'for', 'while', 'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'logic', 'wire', 'reg', 'bit', 'int', 'struct', 'typedef', 'enum', 'return'}
targets = (inst_modules - defined_modules) - keywords
# Exclude complex deep-cluster IPs that have macro/generation issues. We provide hardcoded stubs for them.
targets -= {'axi_to_obi', 'snitch_cluster_wrapper', 'generic_reqrsp_cut', 'snitch_hwpe_subsystem', 'snitch_tcdm_aligner', 'axi_to_tcdm'}

# 2. Extract paths from compile_vsim.tcl
sv_files = []
with open('${rel_outdir_path}/compile_vsim.tcl', 'r') as f:
    tcl_code = re.sub(r'\\\s*\n', ' ', f.read())
    for line in tcl_code.split('\n'):
        if 'vlog ' in line:
            for p in line.split():
                p_clean = p.strip('\"\'').replace('$$ROOT', '.')
                if (p_clean.endswith('.sv') or p_clean.endswith('.v')) and os.path.exists(p_clean):
                    sv_files.append(p_clean)

def extract_module(text, mod_name):
    match = re.search(r'\bmodule\s+' + mod_name + r'\b', text)
    if not match: return None
    tail = text[match.start():]
    tail_no_imports = re.sub(r'\bimport\s+[^;]+;', lambda m: ' ' * len(m.group(0)), tail)
    paren_count = 0
    for i, char in enumerate(tail_no_imports):
        if char == '(': paren_count += 1
        elif char == ')': paren_count -= 1
        elif char == ';' and paren_count == 0:
            return tail[:i+1]
    return None

stubs_out = []
for path in sv_files:
    if not targets: break
    try:
        content = open(path, 'r', encoding='utf-8', errors='ignore').read()
        clean_content = re.sub(r'//.*', '', content)
        clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)
    except: continue
    
    for t in list(targets):
        sig = extract_module(clean_content, t)
        if sig:
            def to_wild(m): return re.sub(r'::\s*[a-zA-Z_0-9]+', '::*', m.group(0))
            sig = re.sub(r'\bimport\s+[^;]+;', to_wild, sig)
            match = re.search(r'\bmodule\s+' + t + r'\b', clean_content)
            if match:
                head = clean_content[:match.start()]
                imports_raw = re.findall(r'\bimport\s+[^;]+;', head) + re.findall(r'\bimport\s+[^;]+;', sig)
                wildcard_imports = set()
                for imp in imports_raw:
                    wildcard_imports.add(re.sub(r'::\s*[a-zA-Z_0-9]+', '::*', imp))
                imports = chr(10).join(sorted(list(wildcard_imports)))
                stubs_out.append(imports + chr(10) + sig + chr(10) + "endmodule")
            targets.remove(t)
            
    if not targets: break

os.makedirs('${rel_outdir_path}/.stubs', exist_ok=True)
with open('${rel_outdir_path}/.stubs/${config.project.name}_stubs.sv', 'w') as f:
    f.write("// AUTO-GENERATED STUBS FOR FAST-CHECK" + chr(10) + chr(10))
    f.write((chr(10) + chr(10)).join(stubs_out))

with open('${rel_outdir_path}/.stubs/snitch_cluster_pkg_stub.sv', 'w') as f:
    f.write("// AUTO-GENERATED STUB FOR FAST-CHECK\n")
    stub_content = (
        "package snitch_cluster_pkg;\n"
        "  localparam int unsigned NrCores = 9;\n"
        "  localparam int unsigned AddrWidth = 48;\n"
        "  localparam int unsigned NarrowDataWidth = 64;\n"
        "  localparam int unsigned WideDataWidth = 512;\n"
        "  localparam int unsigned NarrowIdWidthOut = 2;\n"
        "  localparam int unsigned NarrowIdWidthIn = 5;\n"
        "  localparam int unsigned WideIdWidthOut = 1;\n"
        "  localparam int unsigned WideIdWidthIn = 3;\n"
        "  localparam int unsigned TcdmAddrWidth = 32;\n"
        "  typedef logic [63:0] addr_t;\n"
        "  typedef logic narrow_out_req_t;\n"
        "  typedef logic narrow_out_resp_t;\n"
        "  typedef logic wide_out_req_t;\n"
        "  typedef logic wide_out_resp_t;\n"
        "  typedef logic narrow_in_req_t;\n"
        "  typedef logic narrow_in_resp_t;\n"
        "  typedef logic wide_in_req_t;\n"
        "  typedef logic wide_in_resp_t;\n"
        "  typedef logic tcdm_dma_req_t;\n"
        "  typedef logic tcdm_dma_rsp_t;\n"
        "  typedef logic dca_req_chan_t;\n"
        "  typedef logic dca_rsp_chan_t;\n"
        "  typedef logic narrow_out_aw_chan_t;\n"
        "  typedef logic narrow_out_w_chan_t;\n"
        "  typedef logic narrow_out_b_chan_t;\n"
        "  typedef logic narrow_out_ar_chan_t;\n"
        "  typedef logic narrow_out_r_chan_t;\n"
        "  typedef logic [NarrowIdWidthOut-1:0] narrow_out_id_t;\n"
        "  typedef logic [NarrowDataWidth-1:0] user_narrow_t;\n"
        "  typedef struct packed { logic [2:0][63:0] operands; logic [2:0] src_fmt; logic [2:0] dst_fmt; logic [2:0] int_fmt; logic vectorial_op; logic op_mod; logic [2:0] rnd_mode; logic [3:0] op; } dca_req_q_t;\n"
        "  typedef struct packed { logic q_valid; logic p_ready; dca_req_q_t q; } dca_req_t;\n"
        "  typedef struct packed { logic [63:0] result; } dca_rsp_p_t;\n"
        "  typedef struct packed { logic q_ready; logic p_valid; dca_rsp_p_t p; } dca_rsp_t;\n"
        "endpackage\n"
    )
    f.write(stub_content)

with open('${rel_outdir_path}/.stubs/hardcoded_stubs.sv', 'w') as f:
    f.write("// AUTO-GENERATED HARDCODED STUBS FOR DEEP INTERNALS\n\n")
    f.write("module axi_to_obi #(parameter int ObiCfg=0, parameter type obi_req_t=logic, parameter type obi_rsp_t=logic, parameter type obi_a_chan_t=logic, parameter type obi_r_chan_t=logic, parameter int AxiAddrWidth=0, parameter int AxiDataWidth=0, parameter int AxiIdWidth=0, parameter int AxiUserWidth=0, parameter int MaxTrans=0, parameter type axi_req_t=logic, parameter type axi_rsp_t=logic)(); endmodule\n\n")
    f.write("module snitch_cluster_wrapper(); endmodule\n\n")
    f.write("module generic_reqrsp_cut #(parameter type req_chan_t=logic, parameter type rsp_chan_t=logic, parameter bit BypassReq=1'b0, parameter bit BypassRsp=1'b0)(); endmodule\n\n")
    f.write("module snitch_hwpe_subsystem #(parameter type tcdm_req_t=logic, parameter type tcdm_rsp_t=logic, parameter type periph_req_t=logic, parameter type periph_rsp_t=logic, parameter int HwpeDataWidth=0, parameter int IdWidth=0, parameter int NrCores=0, parameter int TCDMDataWidth=0)(); endmodule\n\n")
    f.write("module snitch_tcdm_aligner #(parameter type tcdm_req_t=logic, parameter type tcdm_rsp_t=logic, parameter int DataWidth=0, parameter int TCDMDataWidth=0, parameter int AddrWidth=0)(); endmodule\n\n")
    f.write("module axi_to_tcdm #(parameter type axi_req_t=logic, parameter type axi_rsp_t=logic, parameter type tcdm_req_t=logic, parameter type tcdm_rsp_t=logic, parameter int IdWidth=0, parameter int AddrWidth=0, parameter int DataWidth=0)(); endmodule\n")

# 3. Create a fast compilation script that skips heavy RTL
fast_tcl = [
    'onerror {quit -code 1}',
    'if {[file exists work]} { file delete -force work }',
    'vlib work',
    'vlog -suppress 13314 -sv ${rel_outdir_path}/.stubs/snitch_cluster_pkg_stub.sv'
]

tcl_code = tcl_code.replace('return 1', 'quit -code 1')

for line in tcl_code.split('\n'):
    if 'vlog ' in line:
        new_tokens = []
        for p in line.split():
            p_clean = p.strip('\"\'')
            if (p_clean.endswith('.sv') or p_clean.endswith('.v')) and not p.startswith('+'):
                if '${rel_outdir_path}' in p_clean or p_clean.endswith('.svh') or p_clean.endswith('_pkg.sv'): new_tokens.append(p)
                else:
                    try:
                        c = open(p_clean.replace('$$ROOT', '.'), 'r', encoding='utf-8', errors='ignore').read()
                        c_clean = re.sub(r'//.*', '', c)
                        c_clean = re.sub(r'/\*.*?\*/', '', c_clean, flags=re.DOTALL)
                        if re.search(r'\b(?:virtual\s+)?(?:package|interface)\s+[a-zA-Z_0-9]+', c_clean): new_tokens.append(p)
                    except: pass
            else: new_tokens.append(p)
        if any((t.strip('\"\'').endswith('.sv') or t.strip('\"\'').endswith('.v')) and not t.startswith('+') for t in new_tokens):
            # Ensure noc_pkg is compiled before soc_pkg
            noc_pkg_idx = -1
            soc_pkg_idx = -1
            for i, t in enumerate(new_tokens):
                if '_noc_pkg.sv' in t: noc_pkg_idx = i
                elif '_soc_pkg.sv' in t: soc_pkg_idx = i
            if noc_pkg_idx != -1 and soc_pkg_idx != -1 and soc_pkg_idx < noc_pkg_idx:
                new_tokens[soc_pkg_idx], new_tokens[noc_pkg_idx] = new_tokens[noc_pkg_idx], new_tokens[soc_pkg_idx]
            fast_line = ' '.join(new_tokens)
            fast_line = fast_line.replace('vlog ', 'vlog -suppress 13314 ')
            fast_tcl.append(fast_line)
    else: fast_tcl.append(line)
fast_tcl.append('vlog -suppress 13314 -sv ${rel_outdir_path}/.stubs/${config.project.name}_stubs.sv')
fast_tcl.append('vlog -suppress 13314 -sv ${rel_outdir_path}/.stubs/hardcoded_stubs.sv')
open('${rel_outdir_path}/compile_vsim_fast.tcl', 'w').write('\n'.join(fast_tcl))
endef
export GEN_STUBS_SCRIPT

fast-check: prep-sim
	@echo "\n[MAKE] Generating exact stubs for heavy external IPs..."
	@python3 -c "$$GEN_STUBS_SCRIPT" || { echo "\n[ERROR] Stub generation failed!"; exit 1; }
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

# ==============================================================================
# Auto-generated QuestaSim Makefile for ${config.project.name}
# ==============================================================================

OUT_DIR  ?= ${rel_outdir_path}
TOP_MOD  ?= ${config.project.name}
VSIM     ?= vsim
BENDER   ?= bender

ifeq (, $(shell command -v $(BENDER) 2> /dev/null))
  BENDER = $(abspath ./bender)
endif

$(abspath ./bender):
	@echo "\n[MAKE] Downloading Bender..."
	@curl --proto '=https' --tlsv1.2 -sSf https://fabianschuiki.github.io/bender/init | bash -s -- 0.28.1

define PATCH_SCRIPT
import os, sys
t = sys.argv[1]
d = open(t).read()
stmts = []
cur_lines = []
for line in d.split(chr(10)):
    is_end = not line.strip().endswith(chr(92))
    clean_line = line.rstrip()
    if clean_line.endswith(chr(92)): clean_line = clean_line[:-1].rstrip()
    if all(x not in clean_line for x in ['bender_work/serial_link/test/', 'bender_work/idma/src/frontend/desc64/', 'bender_work/cheshire/target/sim/src/', 'bender_work/safety_island/rtl/tb/']):
        cur_lines.append(clean_line)
    if is_end:
        if cur_lines:
            stmt = chr(32).join(cur_lines)
            if 'vlog ' in stmt or 'vcom ' in stmt:
                if any(ext in stmt for ext in ['.v', '.sv', '.vhd']):
                    stmt = stmt.replace('vlog -incr', 'vlog -incr -suppress 13314,2388,2618,13311 +define+PRIVATE_ICACHE +define+HIERARCHY_ICACHE_32BIT +define+ICAHE_USE_FF +define+CLUSTER_ALIAS +define+SNITCH_ICACHE +define+PULPD_ENABLE +define+SAFED_ENABLE +define+SPATZ_ENABLE +define+SECURED_ENABLE')
                    if 'bender_work/spatz/' in stmt: stmt = stmt.replace('vlog -incr', 'vlog -incr +define+FPU=1 +define+RVV=1 +define+HARD_FLOAT=1 +define+RVF=1 +define+RVD=1 +define+XF16=1 +define+XF16ALT=1 +define+XF8=1 +define+XF8ALT=1 +define+XFVEC=1')
                    stmts.append(stmt)
            else:
                stmts.append(stmt)
        cur_lines = []
d = chr(10).join(stmts)
i = d.find('bender_work/cva6/core/include/config_pkg.sv')
if i != -1:
    s = i
    while s > 0 and d[s-1] not in ' ' + chr(10) + chr(34) + chr(39): s -= 1
    p = d[s:i]
    q = d[s-1] if s > 0 and d[s-1] in chr(34) + chr(39) else ''
    targets = ['cv64a6_imafdc_sv39_config_pkg.sv', 'cva6_config_pkg.sv']
    c = [os.path.relpath(os.path.join(r,f), 'bender_work/cva6').replace(chr(92),'/') for r,_,fs in os.walk('bender_work/cva6') for f in fs if f in targets]
    c.sort(key=lambda x: 0 if 'cva6_config_pkg' in x else 1)
    o = q + p + 'bender_work/cva6/core/include/config_pkg.sv' + q
    n = [o] + [q + p + 'bender_work/cva6/' + x + q for x in c]
    d = d.replace(o, chr(32).join(n))
open(t, 'w').write(d)
endef
export PATCH_SCRIPT

define IP_PATCH_SCRIPT
import os, re
def patch(f, p, r):
    if os.path.exists(f):
        with open(f, 'r') as file: d = file.read()
        with open(f, 'w') as file: file.write(re.sub(p, r, d))
# Fix vopt-2732/2912: Remove non-existent parameter overrides and floating ports causing mismatches
patch('bender_work/spatz/hw/ip/spatz_cc/src/axi_dma_tc_snitch_fe.sv', r'\.(?:protocol_req_[iot]|protocol_rsp_[iot])\s*\([^)]*\)\s*,?', '')
patch('bender_work/safety_island/rtl/cv32e40p_fpu_wrap.sv', r'\.PulpDivsqrt\s*\([^)]*\)\s*,?', '')
# Fix hanging commas left in parameter lists
patch('bender_work/spatz/hw/ip/spatz_cc/src/axi_dma_tc_snitch_fe.sv', r',\s*\)', ')')
patch('bender_work/safety_island/rtl/cv32e40p_fpu_wrap.sv', r',\s*\)', ')')
# Fix vopt-2912: Remove dummy testbench instantiations causing floating wires
patch('bender_work/safety_island/rtl/safety_island_top.sv', r'(?s)tb_fs_handler_debug\b.*?\bi_fs_handler\b.*?\)\s*;', '// tb_fs_handler_debug removed')
endef
export IP_PATCH_SCRIPT

.PHONY: build-sim run-sim

build-sim: update-hw $(BENDER)
	@echo "\n[MAKE] Fetching dependencies and patching missing simulation models..."
	@$(BENDER) checkout --force || true
	@mkdir -p bender_work/idma/target/rtl/include
	@mkdir -p bender_work/opentitan/hw/ip/lowrisc_ibex/rtl
	@mkdir -p bender_work/cheshire/target/sim/models
	@mkdir -p bender_work/safety_island/rtl
	@mkdir -p bender_work/spatz/hw/system/spatz_cluster/src/generated
	@echo "module s25fs512s(); endmodule" > bender_work/cheshire/target/sim/models/s25fs512s.v
	@echo "// dummy file to satisfy bender" > bender_work/cheshire/target/sim/models/24FC1025.v
	@echo "module bootrom(input clk_i, input req_i, input [63:0] addr_i, output [63:0] rdata_o); endmodule" > bender_work/spatz/hw/system/spatz_cluster/src/generated/bootrom.sv
	@echo "module spatz_cluster_wrapper(); endmodule" > bender_work/spatz/hw/system/spatz_cluster/src/generated/spatz_cluster_wrapper.sv
	@echo "module idma_generated(); endmodule" > bender_work/idma/target/rtl/idma_generated.sv
	@echo "\n[MAKE] Installing on-the-fly Python dependencies for IP generation..."
	@. .venv/bin/activate && pip install -q flatdict mako
	@. .venv/bin/activate && $(MAKE) -C bender_work/idma idma_hw_all BENDER="$(BENDER)"
	@. .venv/bin/activate && $(MAKE) -C bender_work/spatz hw/ip/snitch/src/riscv_instr.sv BENDER="$(BENDER)"
	@sed -i 's/.*global_L1_.*/\/\/ OLLIVANDER PATCH/g' bender_work/hier-icache/CTRL_UNIT/hier_icache_ctrl_unit.sv || true
	@sed -i 's/.*global_L2_.*/\/\/ OLLIVANDER PATCH/g' bender_work/hier-icache/CTRL_UNIT/hier_icache_ctrl_unit.sv || true
	@sed -i 's/snitch_icache_pkg::icache_l0_events_t/logic [31:0]/g' bender_work/pulp_cluster/rtl/pulp_cluster.sv || true
	@sed -i 's/snitch_icache_pkg::icache_l1_events_t/logic [31:0]/g' bender_work/pulp_cluster/rtl/pulp_cluster.sv || true
	@sed -i 's/snitch_icache_pkg::icache_l0_events_t/logic [31:0]/g' bender_work/pulp_cluster/rtl/cluster_peripherals.sv || true
	@sed -i 's/snitch_icache_pkg::icache_l1_events_t/logic [31:0]/g' bender_work/pulp_cluster/rtl/cluster_peripherals.sv || true
	@echo "\n[MAKE] Applying targeted Python patches to external IPs..."
	@python3 -c "$$IP_PATCH_SCRIPT" || { echo "\n[ERROR] Python IP patching script failed!"; exit 1; }
	@echo "\n[MAKE] Extracting SystemVerilog compilation script for QuestaSim via Bender..."
	$(BENDER) script vsim -t rtl -t simulation -t sim -t test -t cva6 -t cv32e40p_use_ff_regfile -t scm_use_fpga_scm -t cv64a6splus_imafdc_sv39_hpdcache_wb -t idma -t use_idma -t snitch_cluster -t deprecated -t carfield_secure_periph -t spatz > $(OUT_DIR)/compile_vsim.tcl
	
	@echo "\n[MAKE] Patching QuestaSim compilation script..."
	@python3 -c "$$PATCH_SCRIPT" $(OUT_DIR)/compile_vsim.tcl || { echo "\n[ERROR] Python patching script failed!"; exit 1; }

	@echo "\n[MAKE] Compiling RTL with QuestaSim (vlog)..."
	$(VSIM) -c -do "source $(OUT_DIR)/compile_vsim.tcl; quit"

run-sim:
	@echo "\n[MAKE] Running simulation in QuestaSim..."
	$(VSIM) -c tb_$(TOP_MOD) -suppress 3009,8386,8602,13276 -do "run -all; quit"

gui:
	@echo "\n[MAKE] Launching QuestaSim GUI..."
	$(VSIM) -gui tb_$(TOP_MOD) -suppress 3009,8386,8602,13276
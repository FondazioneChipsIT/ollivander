# ==============================================================================
# OLLIVANDER AUTO-GENERATED SOFTWARE MAKEFILE
# ==============================================================================

<%
sw_cfg = config.get("software_stack", {})
toolchain = sw_cfg.get("toolchain", "riscv64-unknown-elf-")
app_name = sw_cfg.get("test_app", {}).get("name", "hello_world")
%>
CC      = ${toolchain}gcc
OBJCOPY = ${toolchain}objcopy
OBJDUMP = ${toolchain}objdump

# Default compilation flags for Host (dynamic based on ISA/ABI/cmodel)
CFLAGS  = -march=${config.host.isa or "rv64imafdc"} -mabi=${config.host.abi or "lp64d"} -mcmodel=${config.host.cmodel or "medany"} -ffunction-sections -fdata-sections -g -O0
LDFLAGS = -T linker.ld -nostartfiles -Wl,--gc-sections

.PHONY: all clean
all: ${app_name}.hex

% if app_name == "offload":
# ------------------------------------------------------------------------------
# Offload payloads - one leg per target, all from the same generic source.
# ------------------------------------------------------------------------------
# Each target's payload is cross-compiled for the ISA/ABI its Offload* contract
# declares (the host toolchain provides them as multilibs - a documented
# prerequisite of the offload app), linked at the shared payload region, then
# flattened and embedded into the host firmware as a C header by bin2header.py,
# which the generator drops next to this Makefile: the whole flow is contained
# in the generated tree. bin2header.py is stdlib-only, any python3 works.
PYTHON ?= python3

% for t_name, t in offload_targets.items():
<%
# The contract kind selects both the payload's code path (-DOFFLOAD_MM) and where
# its results travel: through the control unit's registers (control_wire) or
# through a return-slot array in the cluster-local memory (memory_mapped).
ctrl_base = t["base_addr"] + t["ctrl_offs"]
# The PAYLOAD's view of its own cluster: multi-instance targets declare an alias
# base (OffloadLocalBase) at which every instance sees ITSELF, so one image serves
# the whole array; targets without one decode their own global base internally.
local_base = t.get("local_base", t["base_addr"])
common = [
    f'-DOFFLOAD_STACK_TOP={hex(local_base + t["stack_offs"])}',
    f'-DOFFLOAD_CHECK_N={offload_check_n}',
    f'-DOFFLOAD_CHECK_XOR={hex(offload_check_xor)}',
]
if t["contract"] == "control_wire":
    specific = [
        f'-DOFFLOAD_RETURN_ADDR={hex(ctrl_base + t["return_offs"])}',
        f'-DOFFLOAD_EOC_ADDR={hex(ctrl_base + t["eoc_offs"])}',
    ]
else:
    specific = [
        '-DOFFLOAD_MM=1',
        f'-DOFFLOAD_RETURN_ADDR={hex(local_base + t["return_offs"])}',
        f'-DOFFLOAD_HART_BASE={hex(t.get("hart_base", 0))}',
    ]
payload_defines = " ".join(common + specific)
%>\
# Target '${t_name}': ${t["isa"]}/${t["abi"]}, registers via the '${t["contract"]}' contract.
payload_${t_name}.elf: payload_main.c payload.ld
	$(CC) -march=${t["isa"]} -mabi=${t["abi"]} -mcmodel=medlow -O2 -g -ffreestanding -nostartfiles -nostdlib -T payload.ld ${payload_defines} -o $@ payload_main.c

payload_${t_name}.bin: payload_${t_name}.elf
	$(OBJCOPY) -O binary $< $@

payload_${t_name}.h: payload_${t_name}.bin
	$(PYTHON) bin2header.py --binary $< --output $@ --symbol payload_${t_name} --base ${hex(offload_payload_base)}

% endfor
# The host firmware embeds every payload header.
${app_name}.elf: main.c ${" ".join(f"payload_{t}.h" for t in offload_targets)}
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ main.c
% else:
${app_name}.elf: main.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
% endif

${app_name}.hex: ${app_name}.elf
	$(OBJCOPY) -O verilog $< $@

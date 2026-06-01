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

# Default compilation flags for Cheshire (RV64)
CFLAGS  = -march=rv64imafdc -mabi=lp64d -mcmodel=medany -ffunction-sections -fdata-sections -g -O0
LDFLAGS = -T linker.ld -nostartfiles -Wl,--gc-sections

.PHONY: all clean
all: ${app_name}.hex

${app_name}.elf: main.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

${app_name}.hex: ${app_name}.elf
	$(OBJCOPY) -O verilog $< $@
/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED LINKER SCRIPT
 * =============================================================================
 * This script is dynamically generated based on the SoC memory map defined
 * in the YAML configuration.
 * =============================================================================
 */

<%
boot_mem_name = config.get("software_stack", {}).get("boot_memory", "")
base_addr = "0x0"
size = "0x0"

# Dynamically resolve the physical address and size of the target boot memory
all_comps = [config.host] + (config.components if config.components else [])
for comp in all_comps:
    if getattr(comp, "name", "") == boot_mem_name:
        interfaces = getattr(comp, "interfaces", {}) or {}
        axi_slaves = interfaces.get("axi_slave", [])
        if isinstance(axi_slaves, dict):
            axi_slaves = [axi_slaves]
        if axi_slaves:
            b_addr = axi_slaves[0].get("base_addr", 0)
            b_size = axi_slaves[0].get("size", axi_slaves[0].get("size_per_instance", 0))
            base_addr = hex(b_addr) if isinstance(b_addr, int) else str(b_addr)
            size = hex(b_size) if isinstance(b_size, int) else str(b_size)
        break

# AUTONOMOUS BOOT: the bootrom's GPT flow loads the firmware into
# the host's INTERNAL scratchpad and jumps there, so the image must be linked
# for that memory - located by the host's contract (BootSpmOffset/Size, the
# JtagScratchOffset convention), not by any component of the parent map.
boot_mode = (config.get("testbench", {}) or {}).get("boot_mode", "force")
if boot_mode in ("spi_flash", "i2c_eeprom"):
    host_fixed = comp_info.get(config.host.name, {}).get("fixed_params", {})
    spm_off  = int(str(host_fixed.get("BootSpmOffset", "0")).strip('"\''))
    spm_size = int(str(host_fixed.get("BootSpmSize", "0")).strip('"\''))
    host_slvs = (config.host.interfaces or {}).get("axi_slave", [])
    if isinstance(host_slvs, dict):
        host_slvs = [host_slvs]
    hb = host_slvs[0].get("base_addr", 0) if host_slvs else 0
    hb = int(hb, 0) if isinstance(hb, str) else int(hb)
    base_addr = hex(hb + spm_off)
    size = hex(spm_size)
%>
OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = ${base_addr}, LENGTH = ${size}
}

SECTIONS
{
    .text : {
        *(.text.init)
        *(.text*)
    } > RAM

    .data : { *(.data*) } > RAM
    .bss  : { *(.bss*)  } > RAM
    .rodata : { *(.rodata*) } > RAM
}

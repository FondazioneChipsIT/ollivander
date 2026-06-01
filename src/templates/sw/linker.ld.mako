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
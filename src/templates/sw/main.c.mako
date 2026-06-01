/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED TEST FIRMWARE
 * =============================================================================
 * This is a minimalist bare-metal C application to validate the SoC boot flow.
 * =============================================================================
 */

#include <stdint.h>

<%
# 1. Calculate Stack Pointer (End of Boot Memory)
boot_mem_name = config.get("software_stack", {}).get("boot_memory", "")
base_addr = 0
size = 0
all_comps = [config.host] + (config.components if config.components else [])
for comp in all_comps:
    if getattr(comp, "name", "") == boot_mem_name:
        interfaces = getattr(comp, "interfaces", {}) or {}
        slaves = interfaces.get("axi_slave", [])
        if isinstance(slaves, dict):
            slaves = [slaves]
        if slaves:
            b_addr = slaves[0].get("base_addr", 0)
            if isinstance(b_addr, str): b_addr = int(b_addr, 0)
            base_addr = b_addr
            
            s_size = slaves[0].get("size", slaves[0].get("size_per_instance", 0))
            if isinstance(s_size, str): s_size = int(s_size, 0)
            size = s_size
        break
stack_pointer = hex(base_addr + size)

# 2. Try to find a UART for printing
uart_base = None
for comp in all_comps:
    c_name = getattr(comp, "name", "").lower()
    c_type = getattr(comp, "type", "").lower()
    if "uart" in c_name or "uart" in c_type:
        interfaces = getattr(comp, "interfaces", {}) or {}
        slaves = interfaces.get("axi_slave", [])
        if isinstance(slaves, dict): slaves = [slaves]
        reg_slaves = interfaces.get("regbus_slave", [])
        if isinstance(reg_slaves, dict): reg_slaves = [reg_slaves]
        all_slaves = slaves + reg_slaves
        if all_slaves:
            b_addr = all_slaves[0].get("base_addr", 0)
            uart_base = hex(b_addr) if isinstance(b_addr, int) else str(b_addr)
            break

# 3. If not found, check if host is Cheshire with its internal UART enabled
if not uart_base:
    if "cheshire" in getattr(config.host, "type", "").lower() and getattr(config.host, "parameters", {}).get("Uart", True):
        uart_base = "0x10000000" # Default internal Cheshire UART base
%>

% if uart_base:
/* Detected UART base address from SoC configuration */
#define UART_BASE ((volatile uint32_t *) ${uart_base})

void print_str(const char *str) {
    while (*str) {
        *UART_BASE = *str++; // Simple TX write
    }
}
% else:
void print_str(const char *str) {
    // No UART detected in SoC YAML. 
    // Dummy function to prevent optimization removal of the string.
    volatile const char *ptr = str;
    (void)ptr;
}
% endif

int main(void) {
    print_str("Hello, World from Ollivander SoC!\n");
    return 0;
}

/* 
 * Boot entry point. Placed at the very beginning of the boot memory.
 */
__attribute__((naked, section(".text.init"))) void _start(void) {
    // Initialize the Stack Pointer
    __asm__ volatile("li sp, ${stack_pointer}");
    
    // Jump to main application
    __asm__ volatile("call main");

    // Catch return from main and halt
    while(1) {
        __asm__ volatile("nop");
    }
}
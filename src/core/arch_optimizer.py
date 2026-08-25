# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import re
import sys

def optimize_clock_tree(soc_config):
    """
    Removes unused clock domains from the configuration to optimize
    Power, Performance, and Area (PPA) of the final design.
    """
    # Collect all clock domains that are actively used by instantiated components.
    used_clk_domains = set()
    if soc_config.host and soc_config.host.clock_domain:
        used_clk_domains.add(soc_config.host.clock_domain)
        
    if soc_config.components:
        for c in soc_config.components:
            if c.clock_domain:
                used_clk_domains.add(c.clock_domain)
            # Also check sub-components nested inside wrappers (e.g. APB peripherals)
            if c.components:
                for sub in c.components:
                    if sub.clock_domain:
                        used_clk_domains.add(sub.clock_domain)

    active_domains = []
    for dom in soc_config.clock_tree.domains:
        # Keep the domain only if it's explicitly assigned to a component,
        # or if it's marked as 'is_real_time' (always-on clocks like RTC).
        if dom.name in used_clk_domains or dom.is_real_time:
            active_domains.append(dom)
        else:
            print(f"[INFO] Clock domain '{dom.name}' is defined but not used by any component. Removing it from the generated project.")
            
    soc_config.clock_tree.domains = active_domains

def autoconfigure_host(soc_config):
    """
    Auto-calculates the required widths for the Host's interrupt vectors
    and AXI/RegBus interconnect arrays by inspecting the entire SoC topology 
    defined in the YAML. This makes the Host component highly adaptable 
    without requiring manual parameterization.
    """
    def get_all_irqs(comps):
        # Helper to get a flat list of all interrupts in the system.
        irqs = []
        for c in comps:
            if c.interrupts:
                for irq_name, irq_cfg in c.interrupts.items():
                    irqs.append((c, irq_name, irq_cfg))
        return irqs

    comps_list = soc_config.components if soc_config.components else []
    all_irqs = get_all_irqs([soc_config.host] + comps_list)
    
    # Initialize counters for Host boundary parameters.
    host_num_intrs_in = 0
    host_num_intrs_out = 0
    host_num_irq_harts = 0
    host_num_dbg_harts = 0

    # 1. Calculate the size of the main external interrupt vector (`intr_ext_i`).
    if soc_config.host.interrupts:
        for irq_name, irq_cfg in soc_config.host.interrupts.items():
            if 'intr_ext' in irq_name:
                src = str(irq_cfg.get('source', ''))
                # Find the highest index used in the source mapping dictionary.
                indices = re.findall(r'\[(\d+)(?::\d+)?\]\s*:', src)
                if indices:
                    host_num_intrs_in = max([int(i) for i in indices]) + 1

    # 2. Calculate sizes for other Host-exported interrupt/debug signals.
    for c, irq_name, irq_cfg in all_irqs:
        src = str(irq_cfg.get('source', ''))
        if c.name != soc_config.host.name:
            # `intr_ext_o` is an output from the Host that can be routed to other components.
            if f'{soc_config.host.name}.intr_ext_o' in src:
                indices = re.findall(rf'{soc_config.host.name}\.intr_ext_o\[(\d+)(?::\d+)?\]', src)
                if indices:
                    host_num_intrs_out = max(host_num_intrs_out, max([int(i) for i in indices]) + 1)
            
            # `mtip`, `msip`, `xeip` are standard RISC-V hart-level interrupts.
            if any(sig in src for sig in [f'{soc_config.host.name}.mtip_ext_o', f'{soc_config.host.name}.msip_ext_o', f'{soc_config.host.name}.xeip_ext_o']):
                host_num_irq_harts += int(irq_cfg.get('width', 1))
                
            # `dbg_ext_req_o` is for the external debug module interface.
            if f'{soc_config.host.name}.dbg_ext_req_o' in src:
                host_num_dbg_harts += int(irq_cfg.get('width', 1))

    # 3. Calculate AXI and RegBus array sizes based on the topology type.
    if soc_config.topology.type == "noc":
        # In a NoC, the Host is a single node. Its AXI counts are bounded to 1
        # (the connection to its local Chimney).
        host_axi_mst_sync = 1 if soc_config.host.interfaces and 'axi_slave' in soc_config.host.interfaces else 0
        host_axi_mst_async = 0
        host_axi_slv_sync = 1 if soc_config.host.interfaces and 'axi_master' in soc_config.host.interfaces else 0
        host_axi_slv_async = 0
        # For NoC, RegNumSlvSync must account for ALL slaves attached to the Host's
        # local RegBus. This includes external register blocks AND the internal System Controller.
        host_reg_slv_sync = (len(soc_config.system_controller.external_registers) if soc_config.system_controller and soc_config.system_controller.external_registers else 0) + (1 if soc_config.system_controller else 0)
        host_reg_slv_async = 0
    else:
        # In a Crossbar, the Host acts as the central switch, so its array sizes
        # are determined by the total number of masters and slaves in the system.
        host_axi_mst = sum(1 for c in comps_list if c.interfaces and c.interfaces.get('axi_master'))
        host_axi_mst_sync = 0
        host_axi_mst_async = host_axi_mst
        
        host_axi_slv_sync = 0
        host_axi_slv_async = 0
        for c in comps_list:
            if c.interfaces and 'axi_slave' in c.interfaces:
                slvs = c.interfaces['axi_slave']
                if not isinstance(slvs, list):
                    slvs = [slvs]
                for slv in slvs:
                    if slv.get('sync_domain', False):
                        host_axi_slv_sync += slv.get('ports', 1)
                    else:
                        host_axi_slv_async += slv.get('ports', 1)
        host_reg_slv_sync = 1 if soc_config.system_controller else 0
        host_reg_slv_async = 0
        for c in comps_list:
            if c.interfaces and 'regbus_slave' in c.interfaces:
                slvs = c.interfaces['regbus_slave']
                if not isinstance(slvs, list):
                    slvs = [slvs]
                for slv in slvs:
                    if slv.get('sync_domain', True):
                        host_reg_slv_sync += 1
                    else:
                        host_reg_slv_async += 1

    # If the SoC is being exported as a reusable macro, we need to add extra
    # AXI ports on the Host to bridge the internal interconnect to the outside world.
    # IMPORTANT: This applies ONLY to Crossbar topologies! In a NoC, exported macro 
    # interfaces are routed through the peripheral Border Routers, NOT the Host.
    if soc_config.project.build_mode == "macro" and soc_config.project.macro_settings:
        if soc_config.topology.type == "crossbar":
            if soc_config.project.macro_settings.slaves:
                # Exporting a slave port on the macro means the parent SoC acts as a master.
                # The host needs an extra synchronous master port to listen to it.
                host_axi_mst_sync += len(soc_config.project.macro_settings.slaves)
            if soc_config.project.macro_settings.masters:
                # Exporting a master port on the macro means it acts as a master to the parent.
                # The host needs an extra synchronous slave port for it to connect to.
                host_axi_slv_sync += len(soc_config.project.macro_settings.masters)

    # 4. Inject the calculated parameters into the Host component's configuration.
    if getattr(soc_config.host, 'parameters', None) is None:
        soc_config.host.parameters = {}
    
    soc_config.host.parameters.setdefault('NumIntrsIn', host_num_intrs_in)
    soc_config.host.parameters.setdefault('NumIntrsOut', host_num_intrs_out)
    soc_config.host.parameters.setdefault('NumIrqHarts', host_num_irq_harts)
    soc_config.host.parameters.setdefault('NumDbgHarts', host_num_dbg_harts)
    soc_config.host.parameters.setdefault('AxiNumMstSync', host_axi_mst_sync)
    soc_config.host.parameters.setdefault('AxiNumMstAsync', host_axi_mst_async)
    soc_config.host.parameters.setdefault('AxiNumSlvAsync', host_axi_slv_async)
    soc_config.host.parameters.setdefault('AxiNumSlvSync', host_axi_slv_sync)
    soc_config.host.parameters.setdefault('RegNumSlvAsync', host_reg_slv_async)
    soc_config.host.parameters.setdefault('RegNumSlvSync', host_reg_slv_sync)
    
    # Inject standard RegBus types to prevent SystemVerilog from flattening
    # parameterized structs into bits.
    #
    # NoC ONLY. On a NoC the host is reached through its TILE wrapper, which
    # resolves these package types at the isle instantiation instead of
    # re-exposing them as `parameter type` (a typed wrapper cannot be a Verilator
    # hier_block, and six pass-through types were keeping the host tile inlined in
    # the top unit). Injecting them here anyway would make the top override
    # parameters the tile no longer declares - a discarded override, reported as
    # vopt-2732, which is precisely the defect class the suite keeps visible.
    if soc_config.topology.type != "noc":
        soc_config.host.parameters.setdefault('sync_reg_out_req_t', f'{soc_config.project.soc_pkg_name}::soc_reg_req_t')
        soc_config.host.parameters.setdefault('sync_reg_out_rsp_t', f'{soc_config.project.soc_pkg_name}::soc_reg_rsp_t')
        soc_config.host.parameters.setdefault('async_reg_out_req_t', f'{soc_config.project.soc_pkg_name}::soc_reg_req_t')
        soc_config.host.parameters.setdefault('async_reg_out_rsp_t', f'{soc_config.project.soc_pkg_name}::soc_reg_rsp_t')

    # 5. Auto-configure mailbox components based on their interrupt definitions.
    for comp in comps_list:
        if 'mailbox' in comp.type and comp.interrupts:
            if getattr(comp, 'parameters', None) is None:
                comp.parameters = {}
            if 'NumMailboxes' not in comp.parameters:
                # The number of mailboxes is inferred from the number of output interrupt ports.
                comp.parameters['NumMailboxes'] = len([k for k, v in comp.interrupts.items() if not v.get('source')])

def warn_boot_memory_gated(soc_config, original_isle_types=None):
    """
    Warn when the firmware boot image lives in a region that is clock-gated and held
    in reset at power-on.

    With `power_on_state: gated` the safe hardware default applies to every managed
    clock domain and every auto control group. If the memory named by
    `software_stack.boot_memory` sits inside one of them, the host cannot fetch its
    own first instruction until something external brings that region up - and
    firmware cannot do it, because it would have to be running already.

    This is not an error: it is a legitimate configuration, matching how the gwaihir
    reference SoC behaves, and the generated testbench emits a bring-up sequence that
    stands in for that external agent. But the dependency is invisible in the YAML,
    so it is called out explicitly here rather than left to be discovered in a
    silicon bring-up lab.
    """
    if not soc_config.gated_at_power_on:
        return

    boot_mem_name = (soc_config.software_stack or {}).get("boot_memory")
    if not boot_mem_name:
        return

    boot_comp = next((c for c in (soc_config.components or []) if c.name == boot_mem_name), None)
    if boot_comp is None:
        return

    original_isle_types = original_isle_types or {}
    reason = None

    # Case 1: the boot memory is a tile driven by an auto control group.
    if soc_config.system_controller and soc_config.system_controller.auto_control_groups:
        orig_type = original_isle_types.get(boot_comp.name, boot_comp.type)
        candidates = [boot_comp.type, orig_type,
                      orig_type.replace('_isle', '_tile').replace('_subtile', '_tile')]
        for group in soc_config.system_controller.auto_control_groups:
            if group.target_component_type in candidates:
                reason = f"it is controlled by the '{group.name}' auto control group"
                break

    # Case 2: the boot memory sits in a clock domain served by the global reset tree.
    if reason is None:
        managed_names = {d.name for d in soc_config.managed_clock_domains}
        if boot_comp.clock_domain in managed_names:
            reason = f"it sits in the managed clock domain '{boot_comp.clock_domain}'"

    if reason:
        print(f"[WARN] Boot memory '{boot_mem_name}' is gated at power-on because {reason}.")
        print("       With power_on_state: 'gated' the host cannot fetch its boot image until an")
        print("       external agent (JTAG, a boot agent, or the clk_rst_bypass_i pin) enables that")
        print("       region. The generated testbench performs this bring-up automatically; real")
        print("       silicon needs an equivalent. Set power_on_state: 'enabled', or move the boot")
        print("       image to an always-on memory, to remove the dependency.")


def _first_axi_slave_window(comp):
    """(base, size) of a component's first AXI slave window, or (None, None)."""
    slaves = (getattr(comp, "interfaces", {}) or {}).get("axi_slave", [])
    if isinstance(slaves, dict):
        slaves = [slaves]
    if not slaves:
        return None, None
    base = slaves[0].get("base_addr", 0)
    size = slaves[0].get("size", slaves[0].get("size_per_instance", 0))
    base = int(base, 0) if isinstance(base, str) else int(base)
    size = int(size, 0) if isinstance(size, str) else int(size)
    return base, size


def check_boot_memory_executable(soc_config, comp_info):
    """
    Refuse a configuration whose boot image is linked for a memory the host cannot
    FETCH from.

    The relation that makes a boot work is spread over three declarations that never
    mention each other: which memory holds the image (`software_stack.boot_memory`),
    where that memory is (its `axi_slave` base), and whether the host may execute
    there (the host's CIE window, its LLC-out window, or its own internal
    scratchpad). Get it wrong and there is no error anywhere: the host simply never
    fetches, and the run dies before its first instruction.

    The executable set checked here is the one a cheshire-class host publishes to its
    core - internal scratchpad, CIE window, LLC-out window - reconstructed from the
    values THIS project declares. When the host declares none of them the check
    cannot run, and says so rather than passing silently; a host outside this family
    is not checked at all, which is why the guard keys on the parameters' presence
    and never on the host's type.
    """
    boot_mem_name = (soc_config.software_stack or {}).get("boot_memory")
    if not boot_mem_name:
        return

    host = soc_config.host
    host_fixed = (comp_info or {}).get(host.name, {}).get("fixed_params", {})

    def contract_int(key, default=None):
        raw = str(host_fixed.get(key, "")).strip('"\'')
        if not raw:
            return default
        try:
            return int(raw, 0)
        except ValueError:
            return default

    host_base, _ = _first_axi_slave_window(host)
    spm_off = contract_int("BootSpmOffset")
    spm_size = contract_int("BootSpmSize")

    # The host's own scratchpad: executable by construction (it is what its bootrom
    # runs from), so naming the host is always valid - provided the contract that
    # locates that memory exists at all. This is the check the schema pass defers
    # here, where the parsed header is available.
    if boot_mem_name == host.name:
        if spm_off is None or spm_size is None or host_base is None:
            print(f"[ERROR] boot_memory '{boot_mem_name}' names the host, meaning its internal")
            print(f"        scratchpad, but '{host.type}' declares no BootSpmOffset/BootSpmSize")
            print(f"        contract: there is no window to link the firmware for.")
            sys.exit(1)
        # That scratchpad is the last-level cache with its ways in SPM mode, so a
        # project that omits the LLC omits the memory too - and cheshire's own
        # documentation says an external substitute becomes mandatory in that case.
        # Left unchecked, the firmware would be linked for an address nothing serves.
        _bypass = (host.parameters or {}).get("LlcNotBypass")
        if _bypass is not None and not (int(_bypass, 0) if isinstance(_bypass, str) else int(_bypass)):
            print(f"[ERROR] boot_memory '{boot_mem_name}' names the host's internal scratchpad,")
            print(f"        but this project sets LlcNotBypass=0: that scratchpad IS the")
            print(f"        last-level cache in SPM mode, and without the LLC it does not exist.")
            print(f"        Name an external memory as boot_memory, or keep the LLC.")
            sys.exit(1)
        print(f"  -> Boot memory: the host's internal scratchpad at "
              f"{host_base + spm_off:#x} ({spm_size // 1024} KiB), always-on")
        return

    boot_comp = next((c for c in (soc_config.components or []) if c.name == boot_mem_name), None)
    if boot_comp is None:
        return  # unknown name: the cross-reference pass already reported it
    base, size = _first_axi_slave_window(boot_comp)
    if base is None:
        return  # no AXI window to reason about (regbus-only memory)

    # The windows this project declares. CIE geometry is the host's own: anchored
    # under 0x8000_0000 when OnTop, at 0x2000_0000 otherwise (cheshire's
    # gen_cva6_cfg). LLC-out is declared outright.
    params = host.parameters or {}

    def param_int(key):
        val = params.get(key)
        if val is None:
            return None
        if isinstance(val, bool):
            return int(val)
        return int(val, 0) if isinstance(val, str) else int(val)

    windows = []
    if host_base is not None and spm_off is not None and spm_size:
        windows.append(("the host's internal scratchpad",
                        host_base + spm_off, host_base + spm_off + spm_size))
    cie_len = param_int("Cva6ExtCieLength")
    if cie_len:
        cie_base = (0x8000_0000 - cie_len) if param_int("Cva6ExtCieOnTop") else 0x2000_0000
        windows.append(("the CIE window", cie_base, cie_base + cie_len))
    llc_start, llc_end = param_int("LlcOutRegionStart"), param_int("LlcOutRegionEnd")
    if llc_start is not None and llc_end is not None and llc_end > llc_start:
        windows.append(("the LLC-out window", llc_start, llc_end))

    if not windows:
        print(f"[WARN] Cannot verify that boot memory '{boot_mem_name}' is executable for the")
        print(f"       host: '{host.type}' declares neither a CIE window (Cva6ExtCieLength) nor")
        print(f"       an LLC-out window. If the host cannot fetch there, the run will die")
        print(f"       before its first instruction with no diagnostic.")
        return

    if any(base >= w_lo and base + size <= w_hi for _, w_lo, w_hi in windows):
        return

    print(f"[ERROR] Boot memory '{boot_mem_name}' spans [{base:#x}, {base + size:#x}), which no")
    print(f"        region the host can execute from covers. Declared executable windows:")
    for name, w_lo, w_hi in windows:
        print(f"          - {name}: [{w_lo:#x}, {w_hi:#x})")
    print(f"        The host would never fetch its first instruction, and nothing would say so")
    print(f"        at run time. Move the boot memory inside one of these windows, or size the")
    print(f"        host's CIE window (Cva6ExtCieOnTop/Cva6ExtCieLength) to cover it.")
    sys.exit(1)

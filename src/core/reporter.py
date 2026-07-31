# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

from core.utils import is_external

def print_generation_report(soc_config):
    """
    Prints a detailed textual summary of the parsed SoC topology.
    This report is displayed to the user right before generating the top-level
    RTL, acting as a final human-readable confirmation of the hardware 
    architecture that Ollivander is about to emit.
    """
    components_list = soc_config.components if soc_config.components else []
    
    # Split components based on whether they are instantiated inside the SoC (internal)
    # or exposed directly to the outer padframe/testbench (external).
    internal_comps = [c for c in components_list if not is_external(c)]
    external_comps = [c for c in components_list if is_external(c)]
    
    # 1. Compute AXI Slave indexes for Crossbar topologies
    axi_slaves = []
    for c in components_list:
        if c.interfaces and 'axi_slave' in c.interfaces:
            slvs = c.interfaces['axi_slave']
            if isinstance(slvs, dict):
                slvs = [slvs]
            for slv in slvs:
                for _ in range(slv.get('ports', 1)):
                    axi_slaves.append(c.name)
                
    # 2. Compute AXI Master indexes for Crossbar topologies
    axi_masters = [c.name for c in components_list if c.interfaces and c.interfaces.get('axi_master')]
    
    # 3. Compute RegBus Slave indexes, separating sync and async domains.
    # The System Controller is always the first synchronous RegBus slave (index 0).
    reg_slaves = [soc_config.system_controller.name] if soc_config.system_controller else []
    reg_slaves_async = []
    for c in components_list:
        if c.interfaces and 'regbus_slave' in c.interfaces:
            slvs = c.interfaces['regbus_slave']
            if isinstance(slvs, dict):
                slvs = [slvs]
            for slv in slvs:
                if slv.get('sync_domain', True):
                    reg_slaves.append(c.name)
                else:
                    reg_slaves_async.append(c.name)
                    
    # Combine them to show the overall index in the Host's flattened array
    all_reg_slaves = reg_slaves + reg_slaves_async

    def get_comp_report(comps):
        """Helper function to format the interface summary for a list of components."""
        lines = []
        is_noc = soc_config.topology.type == "noc"
        for c in comps:
            intfs = []
            
            # --- NoC Specific Reporting ---
            if is_noc:
                if getattr(c, 'placement', None) and c.placement.get('logical'):
                    logical = c.placement.get('logical')
                    if isinstance(logical, list):
                        intfs.append("NoC Placement [Multiple Regions]")
                    elif 'box' in logical:
                        box = logical['box']
                        intfs.append(f"NoC Placement [Box X:{box.get('x_start')}-{box.get('x_end')} Y:{box.get('y_start')}-{box.get('y_end')}]")
                    else:
                        intfs.append(f"NoC Placement [X:{logical.get('x')} Y:{logical.get('y')}]")
                        
                if c.interfaces and 'noc_networks' in c.interfaces:
                    intfs.append(f"NoC Networks  [{', '.join(c.interfaces['noc_networks'])}]")
                    
            # --- General Interfaces ---
            if c.interfaces:
                if c.interfaces.get('axi_master'): 
                    intfs.append("AXI Master    [Routed via NoC]" if is_noc else f"AXI Master    [MstIdx: {axi_masters.index(c.name)}]")
                if 'axi_slave' in c.interfaces:
                    slvs = c.interfaces['axi_slave'] if isinstance(c.interfaces['axi_slave'], list) else [c.interfaces['axi_slave']]
                    for slv in slvs:
                        ports = slv.get('ports', 1)
                        intfs.append(f"AXI Slave     ({ports} ports) [Routed via NoC]" if is_noc and ports > 1 else "AXI Slave     [Routed via NoC]" if is_noc else f"AXI Slave     ({ports} ports) [SlvIdx: {[i for i, name in enumerate(axi_slaves) if name == c.name]}]" if ports > 1 else f"AXI Slave     [SlvIdx: {axi_slaves.index(c.name)}]")
                if 'llc_port' in c.interfaces:
                    intfs.append("LLC Port      [Direct to Host]")
                if 'regbus_slave' in c.interfaces:
                    intfs.append(f"RegBus Slave  [RegIdx: {all_reg_slaves.index(c.name)}]")
            if getattr(c, 'components', None):
                intfs.append(f"APB Bridge    ({len(c.components)} peripherals)")
            if not intfs:
                intfs.append("No Interconnect Interfaces")
                
            lines.append(f"    - {c.name} ({c.type}):\n" + "\n".join([f"        > {i}" for i in intfs]))
        return "\n".join(lines)

    # Print the final formatted report to standard output
    print("=" * 70)
    print(f"Project      : {soc_config.project.name} - {soc_config.project.description}")
    print(f"Topology     : {soc_config.topology.type.upper()}")
    print(f"Host         : {soc_config.host.name} ({soc_config.host.type})")
    print(f"Components   : {len(internal_comps)} Internal, {len(external_comps)} External")
    print("\n  [Internal Components - Instantiated in Top-Level]")
    print(get_comp_report(internal_comps) if internal_comps else "    (None)")
    print("\n  [External Components - Exported to I/O]")
    print(get_comp_report(external_comps) if external_comps else "    (None)")
    print("=" * 70)
    print("[*] Starting Phase 3: Top-Level Code Generation...\n")

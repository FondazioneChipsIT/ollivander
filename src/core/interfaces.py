# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
Central dictionary and utilities for standard hardware interfaces.
Ensures that physical port definitions are strictly DRY between RTL 
wiring and Padframe generation.
"""

GLOBAL_COMP_INFO = {}

def get_interface_ports(interface_name, comp_name, is_host, c_info=None):
    """
    Returns a list of physical ports for a given abstract interface.
    
    Args:
        interface_name (str): The abstract interface name (e.g., "uart", "spi").
        comp_name (str): The name of the component exporting the interface.
        is_host (bool): True if the component is the SoC Host.
        c_info (dict): The component's parsed SV metadata (used for conditionals).
        
    Returns:
        list of dict: [{"internal": "...", "top": "...", "dir": "..."}, ...]
    """
    if not c_info:
        c_info = GLOBAL_COMP_INFO.get(comp_name, {})
        
    ports = []
    
    # 1. DYNAMIC INTERFACE EXTRACTION (The Smart Way)
    # Find all physical ports that start with the requested interface prefix
    c_ports = c_info.get("ports", {})
    if c_ports:
        for comp_port, p_info in c_ports.items():
            if comp_port.startswith(f"{interface_name}_") or comp_port == interface_name:
                p_dir = p_info.get("dir", "inout")
                if is_host:
                    p_top = comp_port
                else:
                    if comp_port.startswith(f"{comp_name}_"):
                        p_top = comp_port
                    else:
                        p_top = f"{comp_name}_{comp_port}"
                ports.append({"internal": comp_port, "top": p_top, "dir": p_dir})

    return ports

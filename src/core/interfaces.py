# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
Central dictionary and utilities for standard hardware interfaces.
Ensures that physical port definitions are strictly DRY between RTL 
wiring and Padframe generation.
"""

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
    if c_info is None:
        c_info = {}
        
    ports = []
    pfx = "" if is_host else f"{comp_name}_"
    
    if interface_name == "uart":
        uart_pfx = "uart_" if is_host else f"uart_{comp_name}_"
        ports.extend([
            {"internal": "uart_tx_o", "top": f"{uart_pfx}tx_o", "dir": "output"},
            {"internal": "uart_rx_i", "top": f"{uart_pfx}rx_i", "dir": "input"},
        ])
    elif interface_name == "i2c":
        i2c_pfx = "i2c_" if is_host else f"i2c_{comp_name}_"
        ports.extend([
            {"internal": "i2c_sda_o", "top": f"{i2c_pfx}sda_o", "dir": "output"},
            {"internal": "i2c_sda_i", "top": f"{i2c_pfx}sda_i", "dir": "input"},
            {"internal": "i2c_sda_en_o", "top": f"{i2c_pfx}sda_en_o", "dir": "output"},
            {"internal": "i2c_scl_o", "top": f"{i2c_pfx}scl_o", "dir": "output"},
            {"internal": "i2c_scl_i", "top": f"{i2c_pfx}scl_i", "dir": "input"},
            {"internal": "i2c_scl_en_o", "top": f"{i2c_pfx}scl_en_o", "dir": "output"},
        ])
    elif interface_name in ["spi", "spi_host"]:
        spi_pfx = "spi_" if is_host else f"spi_{comp_name}_"
        ports.extend([
            {"internal": "spih_sck_o", "top": f"{spi_pfx}sck_o", "dir": "output"},
            {"internal": "spih_sck_en_o", "top": f"{spi_pfx}sck_en_o", "dir": "output"},
            {"internal": "spih_csb_o", "top": f"{spi_pfx}csb_o", "dir": "output"},
            {"internal": "spih_csb_en_o", "top": f"{spi_pfx}csb_en_o", "dir": "output"},
            {"internal": "spih_sd_o", "top": f"{spi_pfx}sd_o", "dir": "output"},
            {"internal": "spih_sd_en_o", "top": f"{spi_pfx}sd_en_o", "dir": "output"},
            {"internal": "spih_sd_i", "top": f"{spi_pfx}sd_i", "dir": "input"},
        ])
    elif interface_name == "jtag":
        jtag_pfx = "jtag_" if is_host else f"jtag_{comp_name}_"
        ports.extend([
            {"internal": "jtag_tck_i", "top": f"{jtag_pfx}tck_i", "dir": "input"},
            {"internal": "jtag_trst_ni", "top": f"{jtag_pfx}trst_ni", "dir": "input"},
            {"internal": "jtag_tms_i", "top": f"{jtag_pfx}tms_i", "dir": "input"},
            {"internal": "jtag_tdi_i", "top": f"{jtag_pfx}tdi_i", "dir": "input"},
            {"internal": "jtag_tdo_o", "top": f"{jtag_pfx}tdo_o", "dir": "output"},
        ])
        if c_info.get("has_jtag_oe"):
            ports.append({"internal": "jtag_tdo_oe_o", "top": f"{jtag_pfx}tdo_oe_o", "dir": "output"})
    elif interface_name in ["hyperbus", "hyperbus_phy"]:
        for p in ['cs_no', 'ck_o', 'ck_no', 'rwds_o', 'rwds_i', 'rwds_oe_o', 'dq_i', 'dq_o', 'dq_oe_o', 'reset_no']:
            p_dir = 'output' if p.endswith('_o') or p.endswith('_no') else 'input'
            ports.append({"internal": p, "top": f"{pfx}{p}", "dir": p_dir})
    elif interface_name in ["phy", "rgmii_phy"]:
        for p in ['phy_rx_clk_i', 'phy_rxd_i', 'phy_rx_ctl_i', 'phy_tx_clk_o', 'phy_txd_o', 'phy_tx_ctl_o', 'phy_resetn_o', 'phy_mdio_i', 'phy_mdio_o', 'phy_mdio_oe', 'phy_mdc_o']:
            p_dir = 'output' if p.endswith('_o') or p.endswith('_oe') else 'input'
            ports.append({"internal": p, "top": f"{pfx}{p}", "dir": p_dir})
    elif interface_name == "can_bus":
        ports.extend([
            {"internal": f"{comp_name}_rx_i", "top": f"{comp_name}_rx_i", "dir": "input"},
            {"internal": f"{comp_name}_tx_o", "top": f"{comp_name}_tx_o", "dir": "output"},
        ])
    elif interface_name == "eth_clk200":
        ports.append({"internal": "eth_clk200", "top": f"{pfx}eth_clk200", "dir": "output"})
        
    return ports
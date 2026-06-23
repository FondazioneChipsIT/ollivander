# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
IP-XACT IEEE 1685-2014 Component XML Description Generator.
Extracts top-level port mappings, parameters, and memory map definitions 
to produce standard compliant EDA metadata.
"""

import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from pyEDAA.IPXACT.Component import Component
from pyEDAA.IPXACT import IPXACTException

def generate_ipxact(soc_config, env, generator, comp_info):
    """
    Generates a standard IEEE 1685-2014 IP-XACT component XML description for the digital top-level.
    """
    hw_dir = env.outdir_path / env.hw_sub
    ipxact_dir = hw_dir / "ipxact"
    ipxact_dir.mkdir(parents=True, exist_ok=True)
    
    top_level_module_name = generator.top_level_module_name
    xml_file_path = ipxact_dir / f"{top_level_module_name}.xml"
    
    print(f"[*] Starting Phase 10: Exporting IP-XACT XML description to {xml_file_path.relative_to(env.outdir_path)}...")
    
    # 1. Extract ports
    ports = get_top_level_ports(soc_config, generator, comp_info)
    
    # 2. Build XML using ElementTree
    ns = 'http://www.accellera.org/XMLSchema/IPXACT/1685-2014'
    xsi = 'http://www.w3.org/2001/XMLSchema-instance'
    
    ET.register_namespace('ipxact', ns)
    ET.register_namespace('xsi', xsi)
    
    root = ET.Element(f'{{{ns}}}component')
    root.set('xmlns:xsi', xsi)
    root.set('xsi:schemaLocation', f'{ns} {ns}/index.xsd')
    
    # VLNV metadata
    ET.SubElement(root, f'{{{ns}}}vendor').text = soc_config.project.vendor
    ET.SubElement(root, f'{{{ns}}}library').text = soc_config.project.library
    ET.SubElement(root, f'{{{ns}}}name').text = top_level_module_name
    ET.SubElement(root, f'{{{ns}}}version').text = soc_config.project.version
    
    # Bus Interfaces
    bus_interfaces = ET.SubElement(root, f'{{{ns}}}busInterfaces')
    add_clock_reset_interfaces(bus_interfaces, ports, ns)
    add_axi_interfaces(bus_interfaces, soc_config, ports, ns)
    
    # Model
    model = ET.SubElement(root, f'{{{ns}}}model')
    
    # Views
    views = ET.SubElement(model, f'{{{ns}}}views')
    view = ET.SubElement(views, f'{{{ns}}}view')
    ET.SubElement(view, f'{{{ns}}}name').text = "rtl"
    ET.SubElement(view, f'{{{ns}}}envIdentifier').text = "::"
    ET.SubElement(view, f'{{{ns}}}componentInstantiationRef').text = "inst-rtl"
    
    # Instantiations
    instantiations = ET.SubElement(model, f'{{{ns}}}instantiations')
    comp_inst = ET.SubElement(instantiations, f'{{{ns}}}componentInstantiation')
    ET.SubElement(comp_inst, f'{{{ns}}}name').text = "inst-rtl"
    ET.SubElement(comp_inst, f'{{{ns}}}language').text = "SystemVerilog"
    ET.SubElement(comp_inst, f'{{{ns}}}moduleName').text = top_level_module_name
    
    fs_ref = ET.SubElement(comp_inst, f'{{{ns}}}fileSetRef')
    ET.SubElement(fs_ref, f'{{{ns}}}localName').text = "fs-rtl"
    
    # Model Ports
    model_ports = ET.SubElement(model, f'{{{ns}}}ports')
    for p in ports:
        port_el = ET.SubElement(model_ports, f'{{{ns}}}port')
        ET.SubElement(port_el, f'{{{ns}}}name').text = p["name"]
        
        wire = ET.SubElement(port_el, f'{{{ns}}}wire')
        ET.SubElement(wire, f'{{{ns}}}direction').text = p["dir"]
        
        if p["left"] is not None and p["right"] is not None:
            vectors = ET.SubElement(wire, f'{{{ns}}}vectors')
            vector = ET.SubElement(vectors, f'{{{ns}}}vector')
            ET.SubElement(vector, f'{{{ns}}}left').text = str(p["left"])
            ET.SubElement(vector, f'{{{ns}}}right').text = str(p["right"])
            
    # File Sets
    file_sets = ET.SubElement(root, f'{{{ns}}}fileSets')
    file_set = ET.SubElement(file_sets, f'{{{ns}}}fileSet')
    ET.SubElement(file_set, f'{{{ns}}}name').text = "fs-rtl"
    
    # Top-Level SystemVerilog Source file (relative path to XML location)
    file_el = ET.SubElement(file_set, f'{{{ns}}}file')
    ET.SubElement(file_el, f'{{{ns}}}name').text = f"../{top_level_module_name}.sv"
    ET.SubElement(file_el, f'{{{ns}}}fileType').text = "systemVerilogSource"
    
    ET.SubElement(root, f'{{{ns}}}description').text = soc_config.project.description or "Generated SoC top-level"
    
    # 3. Format and save pretty XML
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ")
    pretty_xml = pretty_xml.replace('<?xml version="1.0" ?>', '<?xml version="1.0" encoding="UTF-8" ?>')
    
    with open(xml_file_path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    # 4. Programmatic Validation
    print("  -> Running schema validation via pyEDAA.IPXACT...")
    try:
        Component(xml_file_path, parse=True)
        print("  [SUCCESS] IP-XACT XML validation passed successfully.")
    except IPXACTException as e:
        print(f"\n[ERROR] IP-XACT XML validation failed for {xml_file_path.name}:\n{e}")
        raise ValueError(f"IP-XACT XML Validation Failed: {e}")

def get_top_level_ports(config, generator, comp_info):
    ports = []
    
    # 1. Global Clock and Reset
    if config.clock_tree.generators > 0:
        ports.append({"name": "domain_clk_i", "dir": "in", "left": str(config.clock_tree.generators - 1), "right": "0"})
        ports.append({"name": "clk_gen_lock_i", "dir": "in", "left": str(config.clock_tree.generators - 1), "right": "0"})
        ports.append({"name": "pwr_on_rst_ni", "dir": "in", "left": None, "right": None})
    else:
        ports.append({"name": "clk_i", "dir": "in", "left": None, "right": None})
        ports.append({"name": "rst_ni", "dir": "in", "left": None, "right": None})
        ports.append({"name": "pwr_on_rst_ni", "dir": "in", "left": None, "right": None})
        
    ports.append({"name": "test_mode_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "boot_mode_i", "dir": "in", "left": "1", "right": "0"})
    ports.append({"name": "rtc_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "clk_rst_bypass_i", "dir": "in", "left": None, "right": None})
    
    # 2. JTAG
    ports.append({"name": "jtag_tck_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "jtag_trst_ni", "dir": "in", "left": None, "right": None})
    ports.append({"name": "jtag_tms_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "jtag_tdi_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "jtag_tdo_o", "dir": "out", "left": None, "right": None})
    ports.append({"name": "jtag_tdo_oe_o", "dir": "out", "left": None, "right": None})
    
    # 3. Dynamic exported ports
    grid = {}
    max_x = 0
    max_y = 0
    comps = [config.host] + (config.components if config.components else [])
    for c in comps:
        p = getattr(c, 'placement', None)
        if not p or 'logical' not in p:
            continue
        log = p['logical']
        items = log if isinstance(log, list) else [log]
        inst_idx = 0
        for item in items:
            if 'box' in item:
                b = item['box']
                for x in range(b['x_start'], b['x_end']+1):
                    for y in range(b['y_start'], b['y_end']+1):
                        grid[(x,y)] = (c, inst_idx)
                        inst_idx += 1
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
            else:
                x, y = item['x'], item['y']
                grid[(x,y)] = (c, inst_idx)
                inst_idx += 1
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    from core.interfaces import get_interface_ports
    
    for comp in comps:
        exported_interfaces = comp.export_interfaces if comp.export_interfaces else []
        if not exported_interfaces:
            continue
            
        num_instances = 0
        inst_coords = {}
        for (gx, gy), (c_grid, idx) in grid.items():
            if c_grid and c_grid.name == comp.name:
                num_instances = max(num_instances, idx + 1)
                inst_coords[idx] = (gx, gy)
        if num_instances == 0:
            num_instances = 1
            
        c_info = comp_info.get(comp.name, {})
        is_host = (comp.name == config.host.name)
        
        for if_name in exported_interfaces:
            ports_to_export = get_interface_ports(if_name, comp.name, is_host, c_info)
            for p in ports_to_export:
                internal_port = p['internal']
                p_dir = p['dir']
                p_info = c_info.get("ports", {}).get(internal_port)
                if not p_info:
                    continue
                
                decl = p_info["decl"]
                known_params = {}
                known_params.update(c_info.get("supported_params", {}))
                known_params.update(c_info.get("fixed_params", {}))
                if comp.parameters:
                    for k, v in comp.parameters.items():
                        known_params[k] = "1" if v is True else "0" if v is False else str(v)
                
                for param_name, param_val in known_params.items():
                    decl = re.sub(rf'\b{param_name}\b', param_val, decl)
                    
                name_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\]\s*)*)$', decl)
                if not name_match:
                    continue
                    
                for inst_idx in range(num_instances):
                    if is_host:
                        top_port_name = p['top']
                    else:
                        if num_instances > 1:
                            cx, cy = inst_coords.get(inst_idx, (0,0))
                            top_port_name = f"{comp.name}_{cx}_{cy}_{internal_port}"
                        else:
                            top_port_name = p['top']
                            
                    type_dim = decl[:name_match.start()].strip()
                    unpacked = name_match.group(2).strip()
                    
                    dim_str = type_dim + " " + unpacked
                    m = re.search(r'\[\s*([^\]:]+)\s*:\s*([^\]]+)\s*\]', dim_str)
                    if m:
                        left = m.group(1).strip()
                        right = m.group(2).strip()
                    else:
                        left = None
                        right = None
                        
                    ipxact_dir = "in" if p_dir == "input" else "out" if p_dir == "output" else "inout"
                    
                    ports.append({
                        "name": top_port_name,
                        "dir": ipxact_dir,
                        "left": left,
                        "right": right
                    })
                    
    # 4. Macro AXI interfaces (if build_mode is macro)
    if config.project.build_mode == "macro" and config.project.macro_settings:
        slaves = config.project.macro_settings.slaves or []
        masters = config.project.macro_settings.masters or []
        
        if config.project.macro_settings.export_type == "custom" or config.project.macro_settings.export_type == "isle":
            if slaves:
                ports.append({"name": "axi_req_i", "dir": "in", "left": None, "right": None})
                ports.append({"name": "axi_resp_o", "dir": "out", "left": None, "right": None})
            if masters:
                ports.append({"name": "axi_req_o", "dir": "out", "left": None, "right": None})
                ports.append({"name": "axi_resp_i", "dir": "in", "left": None, "right": None})
        else: # subtile mode
            if slaves:
                for slv in slaves:
                    pfx = "narrow" if slv.bus_type == "narrow" else "wide"
                    ports.append({"name": f"axi_{pfx}_req_i", "dir": "in", "left": None, "right": None})
                    ports.append({"name": f"axi_{pfx}_resp_o", "dir": "out", "left": None, "right": None})
            if masters:
                for mst in masters:
                    pfx = "narrow" if mst.bus_type == "narrow" else "wide"
                    ports.append({"name": f"axi_{pfx}_req_o", "dir": "out", "left": None, "right": None})
                    ports.append({"name": f"axi_{pfx}_resp_i", "dir": "in", "left": None, "right": None})
                    
    # 5. External RegBus ports
    if config.system_controller and config.system_controller.external_registers:
        for ext_reg in config.system_controller.external_registers:
            ports.append({"name": f"{ext_reg.name}_reg_req_o", "dir": "out", "left": None, "right": None})
            ports.append({"name": f"{ext_reg.name}_reg_rsp_i", "dir": "in", "left": None, "right": None})
            
    # Deduplicate ports by name to prevent duplicate declarations and validation errors
    seen = set()
    deduped_ports = []
    for p in ports:
        if p["name"] not in seen:
            deduped_ports.append(p)
            seen.add(p["name"])
    return deduped_ports

def add_clock_reset_interfaces(bus_interfaces, ports, ns):
    clk_ports = [p["name"] for p in ports if "clk" in p["name"] or "clock" in p["name"]]
    rst_ports = [p["name"] for p in ports if "rst" in p["name"] or "reset" in p["name"]]
    
    for clk in clk_ports:
        bi = ET.SubElement(bus_interfaces, f'{{{ns}}}busInterface')
        ET.SubElement(bi, f'{{{ns}}}name').text = f"intf_clk_{clk}"
        
        bt = ET.SubElement(bi, f'{{{ns}}}busType')
        bt.set('vendor', 'accellera.org')
        bt.set('library', 'spirit')
        bt.set('name', 'clock')
        bt.set('version', '1.0')
        
        ats = ET.SubElement(bi, f'{{{ns}}}abstractionTypes')
        at = ET.SubElement(ats, f'{{{ns}}}abstractionType')
        ar = ET.SubElement(at, f'{{{ns}}}abstractionRef')
        ar.set('vendor', 'accellera.org')
        ar.set('library', 'spirit')
        ar.set('name', 'clock_rtl')
        ar.set('version', '1.0')
        
        pm = ET.SubElement(at, f'{{{ns}}}portMaps')
        pmap = ET.SubElement(pm, f'{{{ns}}}portMap')
        lp = ET.SubElement(pmap, f'{{{ns}}}logicalPort')
        ET.SubElement(lp, f'{{{ns}}}name').text = "CLK"
        pp = ET.SubElement(pmap, f'{{{ns}}}physicalPort')
        ET.SubElement(pp, f'{{{ns}}}name').text = clk
        
        sys = ET.SubElement(bi, f'{{{ns}}}system')
        ET.SubElement(sys, f'{{{ns}}}group').text = "clock"
        
    for rst in rst_ports:
        bi = ET.SubElement(bus_interfaces, f'{{{ns}}}busInterface')
        ET.SubElement(bi, f'{{{ns}}}name').text = f"intf_rst_{rst}"
        
        bt = ET.SubElement(bi, f'{{{ns}}}busType')
        bt.set('vendor', 'accellera.org')
        bt.set('library', 'spirit')
        bt.set('name', 'reset')
        bt.set('version', '1.0')
        
        ats = ET.SubElement(bi, f'{{{ns}}}abstractionTypes')
        at = ET.SubElement(ats, f'{{{ns}}}abstractionType')
        ar = ET.SubElement(at, f'{{{ns}}}abstractionRef')
        ar.set('vendor', 'accellera.org')
        ar.set('library', 'spirit')
        ar.set('name', 'reset_rtl')
        ar.set('version', '1.0')
        
        pm = ET.SubElement(at, f'{{{ns}}}portMaps')
        pmap = ET.SubElement(pm, f'{{{ns}}}portMap')
        lp = ET.SubElement(pmap, f'{{{ns}}}logicalPort')
        ET.SubElement(lp, f'{{{ns}}}name').text = "RST"
        pp = ET.SubElement(pmap, f'{{{ns}}}physicalPort')
        ET.SubElement(pp, f'{{{ns}}}name').text = rst

        sys = ET.SubElement(bi, f'{{{ns}}}system')
        ET.SubElement(sys, f'{{{ns}}}group').text = "reset"

def add_axi_interfaces(bus_interfaces, config, ports, ns):
    if not (config.project.build_mode == "macro" and config.project.macro_settings):
        return
        
    slaves = config.project.macro_settings.slaves or []
    masters = config.project.macro_settings.masters or []
    
    def add_axi_intf(name, mode, req_port, resp_port):
        bi = ET.SubElement(bus_interfaces, f'{{{ns}}}busInterface')
        ET.SubElement(bi, f'{{{ns}}}name').text = name
        
        bt = ET.SubElement(bi, f'{{{ns}}}busType')
        bt.set('vendor', 'amba.com')
        bt.set('library', 'AMBA4')
        bt.set('name', 'AXI4')
        bt.set('version', 'r1p0_0')
        
        ats = ET.SubElement(bi, f'{{{ns}}}abstractionTypes')
        at = ET.SubElement(ats, f'{{{ns}}}abstractionType')
        ar = ET.SubElement(at, f'{{{ns}}}abstractionRef')
        ar.set('vendor', 'amba.com')
        ar.set('library', 'AMBA4')
        ar.set('name', 'AXI4_rtl')
        ar.set('version', 'r1p0_0')
        
        pm = ET.SubElement(at, f'{{{ns}}}portMaps')
        
        pmap1 = ET.SubElement(pm, f'{{{ns}}}portMap')
        lp1 = ET.SubElement(pmap1, f'{{{ns}}}logicalPort')
        ET.SubElement(lp1, f'{{{ns}}}name').text = "REQ"
        pp1 = ET.SubElement(pmap1, f'{{{ns}}}physicalPort')
        ET.SubElement(pp1, f'{{{ns}}}name').text = req_port
        
        pmap2 = ET.SubElement(pm, f'{{{ns}}}portMap')
        lp2 = ET.SubElement(pmap2, f'{{{ns}}}logicalPort')
        ET.SubElement(lp2, f'{{{ns}}}name').text = "RSP"
        pp2 = ET.SubElement(pmap2, f'{{{ns}}}physicalPort')
        ET.SubElement(pp2, f'{{{ns}}}name').text = resp_port

        if mode == "slave":
            ET.SubElement(bi, f'{{{ns}}}slave')
        else:
            ET.SubElement(bi, f'{{{ns}}}master')

    if config.project.macro_settings.export_type == "custom" or config.project.macro_settings.export_type == "isle":
        if slaves:
            add_axi_intf("axi_slave", "slave", "axi_req_i", "axi_resp_o")
        if masters:
            add_axi_intf("axi_master", "master", "axi_req_o", "axi_resp_i")
    else: # subtile mode
        if slaves:
            for slv in slaves:
                pfx = "narrow" if slv.bus_type == "narrow" else "wide"
                add_axi_intf(f"axi_slave_{pfx}", "slave", f"axi_{pfx}_req_i", f"axi_{pfx}_resp_o")
        if masters:
            for mst in masters:
                pfx = "narrow" if mst.bus_type == "narrow" else "wide"
                add_axi_intf(f"axi_master_{pfx}", "master", f"axi_{pfx}_req_o", f"axi_{pfx}_resp_i")

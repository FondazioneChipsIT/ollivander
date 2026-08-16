# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
IP-XACT IEEE 1685-2014 Component XML Description Generator.
Extracts top-level port mappings, parameters, and memory map definitions 
to produce standard compliant EDA metadata using schema-compliant object bindings.
"""

import re
from pathlib import Path
from pyEDAA.IPXACT.Component import Component as EDAAComponent
from pyEDAA.IPXACT import IPXACTException
from core.utils import simplify_port_ranges, get_ollivander_version, get_ollivander_git_hash

# Import generated xsdata IP-XACT classes
from core.ipxact import (
    Component,
    BusInterfaces,
    BusInterface,
    ConfigurableLibraryRefType,
    AbstractionTypes,
    Model,
    ModelType,
    PortType,
    Port,
    PortWireType,
    Vectors,
    Vector,
    FileSets,
    FileSet,
    File,
    FileType,
    SimpleFileType,
    ComponentPortDirectionType,
    ComponentInstantiationType,
    FileSetRef,
    Description,
    Left,
    Right,
    StringUriexpression,
    Group
)
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


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
    
    # 2. Build Component model using xsdata
    comp = Component(
        vendor=soc_config.project.vendor,
        library=soc_config.project.library,
        name=top_level_module_name,
        version=soc_config.project.version
    )
    
    # Bus Interfaces
    bi_list = []
    add_clock_reset_interfaces(bi_list, ports)
    add_axi_interfaces(bi_list, soc_config, ports)
    if bi_list:
        comp.bus_interfaces = BusInterfaces(bus_interface=bi_list)
        
    # Model
    env_id = Model.Views.View.EnvIdentifier(value="::")
    view = Model.Views.View(
        name="rtl",
        env_identifier=[env_id],
        component_instantiation_ref="inst-rtl"
    )
    views = Model.Views(view=[view])
    
    fs_ref = FileSetRef(local_name="fs-rtl")
    comp_inst = ComponentInstantiationType(
        name="inst-rtl",
        language="SystemVerilog",
        module_name=top_level_module_name,
        file_set_ref=[fs_ref]
    )
    instantiations = Model.Instantiations(component_instantiation=[comp_inst])
    
    port_list = []
    for p in ports:
        wire = None
        if p["left"] is not None and p["right"] is not None:
            vector = Vector(
                left=Left(value=str(p["left"])),
                right=Right(value=str(p["right"]))
            )
            vectors = Vectors(vector=[vector])
            
            p_dir = p["dir"]
            dir_enum = ComponentPortDirectionType.IN
            if p_dir == "out":
                dir_enum = ComponentPortDirectionType.OUT
            elif p_dir == "inout":
                dir_enum = ComponentPortDirectionType.INOUT
                
            wire = PortWireType(direction=dir_enum, vectors=vectors)
        else:
            p_dir = p["dir"]
            dir_enum = ComponentPortDirectionType.IN
            if p_dir == "out":
                dir_enum = ComponentPortDirectionType.OUT
            elif p_dir == "inout":
                dir_enum = ComponentPortDirectionType.INOUT
                
            wire = PortWireType(direction=dir_enum)
            
        port_list.append(Port(name=p["name"], wire=wire))
    ports_elem = Model.Ports(port=port_list)
    
    comp.model = Model(
        views=views,
        instantiations=instantiations,
        ports=ports_elem
    )
    
    # File Sets
    file_type = FileType(value=SimpleFileType.SYSTEM_VERILOG_SOURCE)
    file_obj = File(
        name=StringUriexpression(value=f"../{top_level_module_name}.sv"),
        file_type=[file_type]
    )
    file_set = FileSet(
        name="fs-rtl",
        file=[file_obj]
    )
    comp.file_sets = FileSets(file_set=[file_set])
    
    if soc_config.project.description:
        comp.description = Description(value=soc_config.project.description)
    else:
        comp.description = Description(value="Generated SoC top-level")
        
    # 3. Serialize and save XML
    serializer_config = SerializerConfig(
        pretty_print=True,
        xml_declaration=True,
        encoding="utf-8",
        schema_location="http://www.accellera.org/XMLSchema/IPXACT/1685-2014 http://www.accellera.org/XMLSchema/IPXACT/1685-2014/index.xsd"
    )
    ns_map = {
        "ipxact": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance"
    }
    serializer = XmlSerializer(config=serializer_config)
    pretty_xml = serializer.render(comp, ns_map=ns_map)
    
    version = get_ollivander_version()
    git_hash = get_ollivander_git_hash(Path(xml_file_path).parent)
    comment = f"\n<!-- Generated by Ollivander v{version} ({git_hash}) -->\n"
    lines = pretty_xml.split("\n")
    if lines and lines[0].startswith("<?xml"):
        pretty_xml = lines[0] + comment + "\n".join(lines[1:])
    else:
        pretty_xml = comment + pretty_xml

    with open(xml_file_path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    # 4. Programmatic Validation
    print("  -> Running schema validation via pyEDAA.IPXACT...")
    try:
        EDAAComponent(xml_file_path, parse=True)
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
    ports.append({"name": "rt_clk_i", "dir": "in", "left": None, "right": None})
    ports.append({"name": "clk_rst_bypass_i", "dir": "in", "left": None, "right": None})
    
    # 2. Dynamic exported ports. JTAG is deliberately NOT listed statically:
    # the pins exist on the top only when the host exports the "jtag"
    # interface, and the macro-import path trusts this list to name real
    # ports of the child - a static entry would lie for non-jtag projects.
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
                decl = simplify_port_ranges(decl)

                    
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
                            
                    decl_type_dim = decl[:name_match.start()].strip()
                    unpacked = name_match.group(2).strip()
                    
                    dim_str = decl_type_dim + " " + unpacked
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


def add_clock_reset_interfaces(bus_interfaces_list, ports):
    clk_ports = [p["name"] for p in ports if "clk" in p["name"] or "clock" in p["name"]]
    rst_ports = [p["name"] for p in ports if "rst" in p["name"] or "reset" in p["name"]]
    
    for clk in clk_ports:
        logical_port = AbstractionTypes.AbstractionType.PortMaps.PortMap.LogicalPort(name="CLK")
        physical_port = AbstractionTypes.AbstractionType.PortMaps.PortMap.PhysicalPort(name=clk)
        port_map = AbstractionTypes.AbstractionType.PortMaps.PortMap(
            logical_port=logical_port,
            physical_port=physical_port
        )
        port_maps = AbstractionTypes.AbstractionType.PortMaps(port_map=[port_map])
        
        abstraction_ref = ConfigurableLibraryRefType(
            vendor="accellera.org",
            library="spirit",
            name="clock_rtl",
            version="1.0"
        )
        abstraction_type = AbstractionTypes.AbstractionType(
            abstraction_ref=abstraction_ref,
            port_maps=port_maps
        )
        abstraction_types = AbstractionTypes(abstraction_type=[abstraction_type])
        
        bus_type = ConfigurableLibraryRefType(
            vendor="accellera.org",
            library="spirit",
            name="clock",
            version="1.0"
        )
        
        system = BusInterface.System(group=Group(value="clock"))
        
        bi = BusInterface(
            name=f"intf_clk_{clk}",
            bus_type=bus_type,
            abstraction_types=abstraction_types,
            system=system
        )
        bus_interfaces_list.append(bi)
        
    for rst in rst_ports:
        logical_port = AbstractionTypes.AbstractionType.PortMaps.PortMap.LogicalPort(name="RST")
        physical_port = AbstractionTypes.AbstractionType.PortMaps.PortMap.PhysicalPort(name=rst)
        port_map = AbstractionTypes.AbstractionType.PortMaps.PortMap(
            logical_port=logical_port,
            physical_port=physical_port
        )
        port_maps = AbstractionTypes.AbstractionType.PortMaps(port_map=[port_map])
        
        abstraction_ref = ConfigurableLibraryRefType(
            vendor="accellera.org",
            library="spirit",
            name="reset_rtl",
            version="1.0"
        )
        abstraction_type = AbstractionTypes.AbstractionType(
            abstraction_ref=abstraction_ref,
            port_maps=port_maps
        )
        abstraction_types = AbstractionTypes(abstraction_type=[abstraction_type])
        
        bus_type = ConfigurableLibraryRefType(
            vendor="accellera.org",
            library="spirit",
            name="reset",
            version="1.0"
        )
        
        system = BusInterface.System(group=Group(value="reset"))
        
        bi = BusInterface(
            name=f"intf_rst_{rst}",
            bus_type=bus_type,
            abstraction_types=abstraction_types,
            system=system
        )
        bus_interfaces_list.append(bi)


def add_axi_interfaces(bus_interfaces_list, config, ports):
    if not (config.project.build_mode == "macro" and config.project.macro_settings):
        return
        
    slaves = config.project.macro_settings.slaves or []
    masters = config.project.macro_settings.masters or []
    
    def add_axi_intf(name, mode, req_port, resp_port):
        lp1 = AbstractionTypes.AbstractionType.PortMaps.PortMap.LogicalPort(name="REQ")
        pp1 = AbstractionTypes.AbstractionType.PortMaps.PortMap.PhysicalPort(name=req_port)
        port_map1 = AbstractionTypes.AbstractionType.PortMaps.PortMap(
            logical_port=lp1,
            physical_port=pp1
        )
        
        lp2 = AbstractionTypes.AbstractionType.PortMaps.PortMap.LogicalPort(name="RSP")
        pp2 = AbstractionTypes.AbstractionType.PortMaps.PortMap.PhysicalPort(name=resp_port)
        port_map2 = AbstractionTypes.AbstractionType.PortMaps.PortMap(
            logical_port=lp2,
            physical_port=pp2
        )
        
        port_maps = AbstractionTypes.AbstractionType.PortMaps(port_map=[port_map1, port_map2])
        
        abstraction_ref = ConfigurableLibraryRefType(
            vendor="amba.com",
            library="AMBA4",
            name="AXI4_rtl",
            version="r1p0_0"
        )
        abstraction_type = AbstractionTypes.AbstractionType(
            abstraction_ref=abstraction_ref,
            port_maps=port_maps
        )
        abstraction_types = AbstractionTypes(abstraction_type=[abstraction_type])
        
        bus_type = ConfigurableLibraryRefType(
            vendor="amba.com",
            library="AMBA4",
            name="AXI4",
            version="r1p0_0"
        )
        
        slave_mode = BusInterface.Slave() if mode == "slave" else None
        master_mode = BusInterface.Master() if mode == "master" else None
        
        bi = BusInterface(
            name=name,
            bus_type=bus_type,
            abstraction_types=abstraction_types,
            slave=slave_mode,
            master=master_mode
        )
        bus_interfaces_list.append(bi)

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

# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
NoC Placement Checker (NPC) and Latency Estimator

This module validates that components placed on a 2D routing mesh do not overlap
their physical coordinates (collisions). It also computes Manhattan distance 
between master and slave tiles to estimate communication latency (hops),
exporting a detailed report in Markdown format.
"""

from pathlib import Path
from core.utils import get_generation_comment

def parse_coord_val(v):
    """
    Parses coordinate values which might be integers or string representations.
    """
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        v = v.replace('_', '')
        return int(v, 16) if v.lower().startswith('0x') else int(v)
    return int(v)

def expand_placement(component):
    """
    Expands the placement configuration of a component into a list of
    physical (x, y, instance_idx) coordinate tuples on the NoC grid.
    """
    placement = getattr(component, 'placement', None)
    if not placement:
        return []
    
    logical = placement.get('logical')
    if not logical:
        return []
    
    items = logical if isinstance(logical, list) else [logical]
    coordinates = []
    inst_idx = 0
    for item in items:
        if 'box' in item:
            b = item['box']
            x_start = parse_coord_val(b['x_start'])
            x_end = parse_coord_val(b['x_end'])
            y_start = parse_coord_val(b['y_start'])
            y_end = parse_coord_val(b['y_end'])
            # Expand X first, then Y (matches the standard templates sequence)
            for x in range(x_start, x_end + 1):
                for y in range(y_start, y_end + 1):
                    coordinates.append((x, y, inst_idx))
                    inst_idx += 1
        else:
            x = parse_coord_val(item['x'])
            y = parse_coord_val(item['y'])
            coordinates.append((x, y, inst_idx))
            inst_idx += 1
    return coordinates

def get_net_lists(c):
    """
    Extracts the lists of master and slave networks defined for a component.
    """
    if not c.interfaces or 'noc_networks' not in c.interfaces:
        return [], []
    noc_nets_raw = c.interfaces.get('noc_networks', [])
    if isinstance(noc_nets_raw, dict):
        mst_nets = noc_nets_raw.get('master', [])
        slv_nets = noc_nets_raw.get('slave', [])
    else:
        mst_nets = noc_nets_raw
        slv_nets = noc_nets_raw
    return mst_nets, slv_nets

def run_noc_placement_check(soc_config, env):
    """
    Main NoC Placement Check execution block.
    Raises ValueError on coordinate collision, halts generation.
    Otherwise, generates the latency estimation report.
    """
    # Only execute for NoC topologies
    if getattr(soc_config.topology, 'type', None) != 'noc':
        return

    comps = [soc_config.host] + (soc_config.components if soc_config.components else [])
    occupied = {}
    collisions = []
    all_instances = []
    
    # 1. Coordinate expansion & collision verification
    for c in comps:
        coords = expand_placement(c)
        for x, y, inst_idx in coords:
            inst_name = f"{c.name}[{inst_idx}]" if len(coords) > 1 else c.name
            if (x, y) in occupied:
                collisions.append({
                    'coord': (x, y),
                    'existing': occupied[(x, y)],
                    'new': (c.name, inst_idx, inst_name)
                })
            else:
                occupied[(x, y)] = (c.name, inst_idx, inst_name)
            
            all_instances.append({
                'name': c.name,
                'type': c.type,
                'x': x,
                'y': y,
                'inst_idx': inst_idx,
                'inst_name': inst_name,
                'component': c
            })
            
    if collisions:
        err_msg = "\n[ERROR] NoC Grid Collision Detected!"
        err_msg += "\n========================================================"
        for col in collisions:
            x, y = col['coord']
            exist_comp, exist_idx, exist_name = col['existing']
            new_comp, new_idx, new_name = col['new']
            err_msg += f"\nCoordinate ({x}, {y}) is claimed by multiple instances:"
            err_msg += f"\n  - {exist_name} (from component '{exist_comp}')"
            err_msg += f"\n  - {new_name} (from component '{new_comp}')"
        err_msg += "\n========================================================"
        raise ValueError(err_msg)

    # 2. Extract network names
    networks = []
    if hasattr(soc_config.topology, 'noc_settings') and soc_config.topology.noc_settings:
        if hasattr(soc_config.topology.noc_settings, 'networks') and soc_config.topology.noc_settings.networks:
            networks = list(soc_config.topology.noc_settings.networks.keys())
    if not networks:
        networks = ["narrow", "wide"]

    # 3. Calculate master-slave routing hops (Manhattan Distance)
    network_paths = {net: [] for net in networks}
    for m in all_instances:
        c_m = m['component']
        if not c_m.interfaces or not c_m.interfaces.get('axi_master', False):
            continue
            
        mst_nets, _ = get_net_lists(c_m)
        
        for s in all_instances:
            if m['inst_name'] == s['inst_name']:
                continue
            c_s = s['component']
            if not c_s.interfaces:
                continue
                
            is_slave = bool(c_s.interfaces.get('axi_slave') or c_s.interfaces.get('regbus_slave'))
            if not is_slave:
                continue
                
            _, slv_nets = get_net_lists(c_s)
            common_nets = set(mst_nets).intersection(set(slv_nets))
            
            for net in common_nets:
                if net in network_paths:
                    hops = abs(m['x'] - s['x']) + abs(m['y'] - s['y'])
                    network_paths[net].append({
                        'master': m['inst_name'],
                        'master_coord': (m['x'], m['y']),
                        'slave': s['inst_name'],
                        'slave_coord': (s['x'], s['y']),
                        'hops': hops,
                        'network': net
                    })

    # 4. Generate the Markdown report
    max_x = max([inst['x'] for inst in all_instances]) if all_instances else 0
    max_y = max([inst['y'] for inst in all_instances]) if all_instances else 0
    
    report = []
    report.append(f"# NoC Placement and Latency Report\n")
    report.append(f"**Project:** {soc_config.project.name}  ")
    algo = getattr(soc_config.topology.noc_settings, 'routing_algorithm', 'XY')
    report.append(f"**Routing Topology:** NoC ({algo})  ")
    report.append(f"**Grid Dimensions:** {max_x + 1}x{max_y + 1}  \n")
    report.append("---")
    report.append("\n## NoC Placement Checker (NPC) Status\n")
    report.append("> [!NOTE]")
    report.append("> **NPC Status:** PASS  ")
    report.append("> No coordinate overlaps or collision violations were detected on the NoC physical grid. All components are safely placed.\n")
    report.append("---")
    report.append("\n## Grid Placement Map\n")
    report.append("The following table visualizes the physical 2D layout of tiles on the routing grid.  ")
    report.append("*Note: Y coordinates are represented from top (max_y) to bottom (0).*\n")
    
    headers = ["Y \\ X"] + [str(x) for x in range(max_x + 1)]
    report.append("| " + " | ".join(headers) + " |")
    report.append("| " + " | ".join([":---:" for _ in headers]) + " |")
    for y in range(max_y, -1, -1):
        row_cells = [f"**{y}**"]
        for x in range(max_x + 1):
            if (x, y) in occupied:
                _, _, inst_name = occupied[(x, y)]
                row_cells.append(inst_name)
            else:
                row_cells.append("-")
        report.append("| " + " | ".join(row_cells) + " |")
        
    report.append("\n---")
    report.append("\n## Hops & Latency Estimation\n")
    report.append("Latency on the 2D mesh is estimated using the **Manhattan Distance** (number of routing hops) between the source (Master) and target (Slave) tiles:")
    report.append("\\[\\text{Hops} = |x_{\\text{master}} - x_{\\text{slave}}| + |y_{\\text{master}} - y_{\\text{slave}}|\\]\n")
    report.append("For each physical network traffic class, the estimated routing hops are detailed below.\n")
    
    # 4.1 Summary statistics
    report.append("### Summary Metrics\n")
    report.append("| Network | Total Paths | Min Hops | Max Hops | Avg Hops |")
    report.append("| :--- | :---: | :---: | :---: | :---: |")
    for net in networks:
        paths = network_paths[net]
        if not paths:
            report.append(f"| **{net}** | 0 | - | - | - |")
            continue
        hops_list = [p['hops'] for p in paths]
        total_paths = len(paths)
        min_h = min(hops_list)
        max_h = max(hops_list)
        avg_h = sum(hops_list) / total_paths
        report.append(f"| **{net}** | {total_paths} | {min_h} | {max_h} | {avg_h:.2f} |")
        
    report.append("\n### Detailed Path Table\n")
    report.append("| Source (Master) | Dest (Slave) | Network | Master Coords | Slave Coords | Routing Hops |")
    report.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
    
    all_paths = []
    for net in networks:
        for p in network_paths[net]:
            all_paths.append(p)
            
    # Sort by network, then master, then slave for deterministic ordering
    all_paths.sort(key=lambda x: (x['network'], x['master'], x['slave']))
    for p in all_paths:
        report.append(
            f"| {p['master']} | {p['slave']} | {p['network']} | `({p['master_coord'][0]}, {p['master_coord'][1]})` | `({p['slave_coord'][0]}, {p['slave_coord'][1]})` | **{p['hops']}** |"
        )
        
    doc_dir = Path(env.outdir_path) / env.doc_sub
    doc_dir.mkdir(parents=True, exist_ok=True)
    report_file = doc_dir / "noc_placement_report.md"
    with open(report_file, 'w', encoding='utf-8') as rf:
        rf.write(get_generation_comment("<!--", env.base_dir).rstrip() + " -->\n\n")
        rf.write("\n".join(report) + "\n")

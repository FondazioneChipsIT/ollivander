# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
NoC Placement Checker (NPC) and placement report

Validates that the components placed on the 2D mesh do not overlap (a collision
halts generation), then writes generated/doc/noc_placement_report.md: the grid,
the hop distances of the paths the generated workload uses, the static router
load XY routing implies, the collective groups (from core/collective_geometry,
the same code the tile template uses), a per-tile inventory, and the all-pairs
table folded at the end. Hop counts, never latencies.
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

def _placement_data(soc_config):
    """The instances on the grid and their collisions - shared by the check and the report."""

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
            
    return comps, occupied, collisions, all_instances


def run_noc_placement_check(soc_config, env):
    """Phase 2: refuse a mesh where two instances claim one coordinate (ValueError
    halts generation). The report is written later, by write_noc_placement_report,
    once the staged isle headers and the offload targets exist."""
    if getattr(soc_config.topology, 'type', None) != 'noc':
        return
    _, _, collisions, _ = _placement_data(soc_config)
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


def write_noc_placement_report(soc_config, env, comp_info, offload_targets, original_isle_types=None):
    """After Phase 3: generated/doc/noc_placement_report.md. comp_info is the
    generator's own (the staged, de-typed isle headers with their contract
    localparams), offload_targets the dict the firmware generator resolved - the
    report reads the generator's truth instead of re-deriving it."""
    if getattr(soc_config.topology, 'type', None) != 'noc':
        return
    comps, occupied, _, all_instances = _placement_data(soc_config)

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

    # 4. The report. Hop DISTANCE, not latency: the Manhattan count between two tiles
    # under XY routing, with no traffic or arbitration in it. Sections, by value:
    # the grid; the paths the generated workload actually uses; the static link
    # load a placement implies; the collective groups; a per-tile inventory; the
    # all-pairs table last, folded, for the reader who wants it.
    max_x = max([inst['x'] for inst in all_instances]) if all_instances else 0
    max_y = max([inst['y'] for inst in all_instances]) if all_instances else 0
    by_name = {inst['inst_name']: inst for inst in all_instances}
    host_name = soc_config.host.name
    host_inst = by_name.get(host_name)
    boot_mem = (soc_config.software_stack or {}).get('boot_memory')
    sysctrl = soc_config.system_controller
    groups = (sysctrl.auto_control_groups or []) if sysctrl else []
    gated_types = {g.target_component_type for g in groups if g.target_component_type}
    power_on = getattr(sysctrl, 'power_on_state', 'gated') if sysctrl else 'enabled'

    def hops(a, b):
        return abs(a['x'] - b['x']) + abs(a['y'] - b['y'])

    def is_memory(c):
        ifs = c.interfaces or {}
        return bool(ifs.get('axi_slave')) and not ifs.get('axi_master') and c.name != host_name

    def gating(c):
        if c.name == host_name:
            return "host domain"
        if c.type in gated_types and power_on != 'enabled':
            return "gated at power-on (control group)"
        return "clocked from power-on"

    offload_targets = offload_targets or {}

    # 4.2 static link load under XY routing: every master->slave pair, per network,
    # walks X first then Y; each router it enters counts one visit.
    router_load = {net: {} for net in networks}
    for net in networks:
        for pth in network_paths[net]:
            (mx, my), (sx, sy) = pth['master_coord'], pth['slave_coord']
            x, y = mx, my
            visited = []
            while x != sx:
                x += 1 if sx > x else -1
                visited.append((x, y))
            while y != sy:
                y += 1 if sy > y else -1
                visited.append((x, y))
            for cell in visited[:-1]:  # the destination's own router is not transit
                router_load[net][cell] = router_load[net].get(cell, 0) + 1

    # 4.3 collective groups, from the shared geometry helper
    from core.collective_geometry import collective_geometry
    coll_groups = []
    # On a mesh the generator's comp_info holds the generated TILE headers (that is
    # what the IR builder wires), whose few parameters say nothing about the
    # collective contract: the contract localparams live in the ISLE header, so the
    # report reads the staged isle exactly as the tile template does -
    # <module_prefix>_<original isle type>, the shipped component as fallback.
    from core.sv_parser import get_isle_info
    comp_info_by_name = {}
    for c in comps:
        if not (c.features and c.features.get('multicast_target')):
            continue
        orig = (original_isle_types or {}).get(c.name, c.type)
        info = get_isle_info(f"{soc_config.project.module_prefix}_{orig}", env.search_paths, None) \
               or get_isle_info(orig, env.search_paths, env.exclude_dir) or {}
        comp_info_by_name[c.name] = info
    colls = getattr(soc_config.topology.noc_settings, 'collectives', None)
    narrow_red_on = bool(colls and colls.narrow_reduction.enable)
    nets_cfg = soc_config.topology.noc_settings.networks
    n_beat = getattr(nets_cfg.get('narrow'), 'data_width', 64) // 8 if nets_cfg.get('narrow') else 8
    w_beat = getattr(nets_cfg.get('wide'), 'data_width', 512) // 8 if nets_cfg.get('wide') else 64
    for c in comps:
        if c.name not in comp_info_by_name:
            continue
        info = comp_info_by_name[c.name]
        fx = info.get('fixed_params', {}) if info else {}
        try:
            geo = collective_geometry(c, fx, narrow_red_on, n_beat, w_beat)
        except ValueError as exc:
            print(f"  [WARNING] placement report: {c.name}: {exc}")
            geo = None
        if geo is not None:
            coll_groups.append((c, geo))
        else:
            # A multicast target without a group is worth a line in the log: either
            # the isle declares no barrier slot, or the component has one instance.
            print(f"  [INFO] placement report: '{c.name}' is a multicast target without a collective group "
                  f"(barrier slot: {fx.get('OffloadBarrierOffs')}, header params read: {len(fx)}, "
                  f"comp_info keys: {sorted((comp_info or {}).keys())[:6]})")

    report = []
    report.append(f"# NoC Placement Report\n")
    report.append(f"**Project:** {soc_config.project.name}  ")
    algo = getattr(soc_config.topology.noc_settings, 'routing_algorithm', 'XY')
    report.append(f"**Routing:** {algo} on a {max_x + 1}x{max_y + 1} mesh  ")
    report.append(f"**Placement check:** PASS - no two instances claim one coordinate.  \n")
    report.append("Distances below are hop counts (Manhattan distance under XY routing), not latencies: they carry no traffic, arbitration or link width.\n")
    report.append("---")

    # Grid
    report.append("\n## Grid\n")
    report.append("*Y from top (max_y) to bottom (0). `-` is a dummy tile: a router with no isle, kept for transit.*\n")
    headers = ["Y \\ X"] + [str(x) for x in range(max_x + 1)]
    report.append("| " + " | ".join(headers) + " |")
    report.append("| " + " | ".join([":---:" for _ in headers]) + " |")
    for y in range(max_y, -1, -1):
        row_cells = [f"**{y}**"]
        for x in range(max_x + 1):
            row_cells.append(occupied[(x, y)][2] if (x, y) in occupied else "-")
        report.append("| " + " | ".join(row_cells) + " |")
    dummies = [(x, y) for x in range(max_x + 1) for y in range(max_y + 1) if (x, y) not in occupied]
    report.append(f"\n{len(all_instances)} tiles with an isle, {len(dummies)} dummy tiles.\n")

    # The paths the workload uses
    report.append("---\n\n## Paths the generated workload uses\n")
    if host_inst:
        rows = []
        if boot_mem:
            bm = [i for i in all_instances if i['name'] == boot_mem]
            for b in bm:
                rows.append((f"{host_name} -> {b['inst_name']} (boot memory, {gating(b['component'])})", hops(host_inst, b)))
        for t_name in offload_targets:
            insts = [i for i in all_instances if i['name'] == t_name]
            if insts:
                hs = [hops(host_inst, i) for i in insts]
                rows.append((f"{host_name} -> {t_name} (offload target, {len(insts)} instances: payload load and polling)",
                             f"{min(hs)} .. {max(hs)}"))
        mems = [i for i in all_instances if is_memory(i['component']) and i['name'] != boot_mem]
        for t_name in offload_targets:
            insts = [i for i in all_instances if i['name'] == t_name]
            if insts and mems:
                nearest = [min(hops(i, m) for m in mems) for i in insts]
                rows.append((f"{t_name} -> nearest memory tile (each instance)", f"{min(nearest)} .. {max(nearest)}"))
        report.append("| Path | Hops |")
        report.append("| :--- | :---: |")
        for label, h in rows:
            report.append(f"| {label} | {h} |")
        if not rows:
            report.append("| (no boot memory or offload target declared) | - |")
    else:
        report.append("*The host has no placement; nothing to measure from.*")

    # Static link load
    report.append("\n---\n\n## Static router load under XY routing\n")
    report.append("How many master-to-slave pairs route THROUGH each router (the pair's own endpoints excluded), per network: the design-time twin of the run-time `[TB_ACTIVITY]` grid. A column of high numbers next to the host is where every poll and payload load funnels.\n")
    for net in networks:
        report.append(f"**{net}**\n")
        report.append("| Y \\ X | " + " | ".join(str(x) for x in range(max_x + 1)) + " |")
        report.append("| :---: | " + " | ".join(":---:" for _ in range(max_x + 1)) + " |")
        for y in range(max_y, -1, -1):
            report.append(f"| **{y}** | " + " | ".join(str(router_load[net].get((x, y), 0)) for x in range(max_x + 1)) + " |")
        report.append("")

    # Collective groups
    report.append("---\n\n## Collective groups\n")
    if not coll_groups:
        report.append("*No multicast-target component with collective slots.*")
    for c, geo in coll_groups:
        report.append(f"### {c.name}\n")
        xs = [x for x, _ in geo.coords]; ys = [y for _, y in geo.coords]
        report.append(f"- box x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}: {geo.x_dim} columns x {geo.y_dim} rows, {len(geo.bases)} members, "
                      f"bases 0x{geo.c0:08x} + n*0x{geo.stride:x}, group mask 0x{geo.mask:x}")
        report.append(f"- reduction: {'two dimension-ordered phases (column mask 0x%x, row mask 0x%x)' % (geo.y_mask, geo.x_mask) if geo.two_phase else 'single phase (one dimension degenerate)'}"
                      f"{'' if narrow_red_on else ' - narrow reduction not declared, barrier and multicast only'}")
        heads = geo.heads
        report.append(f"- column heads (instance -> coords): " + ", ".join(f"{i} -> {geo.coords[i]}" for i in heads))
        report.append(f"- longest chain: {geo.y_dim - 1} hops along a column, {geo.x_dim - 1} along the head row")
        crossed = [(x, y) for x in range(min(xs), max(xs) + 1) for y in range(min(ys), max(ys) + 1) if (x, y) not in geo.coords]
        report.append(f"- dummy or foreign tiles inside the box (transit for the multicast): {crossed if crossed else 'none'}")
        report.append(f"- alias base 0x{geo.alias:08x}; slots: " + ", ".join(f"{k} 0x{v:x}" for k, v in geo.slots.items()))
        report.append("- windows (op, kind, slot offset): " + ", ".join(f"{w[0]}/{w[7]}/0x{w[6]:x}" for w in geo.windows) + "\n")

    # Per-tile inventory
    report.append("---\n\n## Tile inventory\n")
    report.append("| Tile | Type | Networks (master / slave) | Role | Address window |")
    report.append("| :--- | :--- | :--- | :--- | :--- |")
    group_roles = {}
    for c, geo in coll_groups:
        for i, (x, y) in enumerate(geo.coords):
            group_roles[(x, y)] = "column head" if i in geo.heads else "member"
    from core.collective_geometry import instance_bases_and_coords
    win_of = {}
    for c in comps:
        try:
            bases, coords = instance_bases_and_coords(c)
        except Exception:
            bases, coords = None, []
        if bases and len(bases) == len(coords):
            for b, xy in zip(bases, coords):
                win_of[(c.name, xy)] = b
    for inst in sorted(all_instances, key=lambda i: (i['x'], i['y'])):
        c = inst['component']
        mst, slv = get_net_lists(c)
        kind = "host" if c.name == host_name else ("memory" if is_memory(c) else "compute")
        role = group_roles.get((inst['x'], inst['y']), "-")
        ifs = c.interfaces or {}
        s_ifs = ifs.get('axi_slave')
        s0 = s_ifs[0] if isinstance(s_ifs, list) and s_ifs else (s_ifs if isinstance(s_ifs, dict) else None)
        b = win_of.get((c.name, (inst['x'], inst['y'])))
        if b is None and s0 and s0.get('base_addr') is not None:
            try:
                b = int(str(s0.get('base_addr')), 0)
            except ValueError:
                b = None
        win = f"0x{b:08x}" if b is not None else "-"
        report.append(f"| {inst['inst_name']} ({inst['x']},{inst['y']}) | {kind} | {','.join(mst) or '-'} / {','.join(slv) or '-'} | {role} | {win} |")

    # All pairs, folded
    report.append("\n---\n\n## Hop distances\n")
    report.append("| Network | Pairs | Min | Max | Avg |")
    report.append("| :--- | :---: | :---: | :---: | :---: |")
    for net in networks:
        paths = network_paths[net]
        if not paths:
            report.append(f"| **{net}** | 0 | - | - | - |")
            continue
        hl = [p_['hops'] for p_ in paths]
        report.append(f"| **{net}** | {len(paths)} | {min(hl)} | {max(hl)} | {sum(hl) / len(hl):.2f} |")
    all_paths = sorted((p_ for net in networks for p_ in network_paths[net]), key=lambda x: (-x['hops'], x['network'], x['master'], x['slave']))
    report.append("\nThe ten longest:\n")
    report.append("| Source | Destination | Network | Hops |")
    report.append("| :--- | :--- | :---: | :---: |")
    for p_ in all_paths[:10]:
        report.append(f"| {p_['master']} | {p_['slave']} | {p_['network']} | {p_['hops']} |")
    report.append("\n<details><summary>All master-to-slave pairs</summary>\n")
    report.append("| Source | Destination | Network | Hops |")
    report.append("| :--- | :--- | :---: | :---: |")
    for p_ in sorted(all_paths, key=lambda x: (x['network'], x['master'], x['slave'])):
        report.append(f"| {p_['master']} | {p_['slave']} | {p_['network']} | {p_['hops']} |")
    report.append("\n</details>")

    doc_dir = Path(env.outdir_path) / env.doc_sub
    doc_dir.mkdir(parents=True, exist_ok=True)
    report_file = doc_dir / "noc_placement_report.md"
    with open(report_file, 'w', encoding='utf-8') as rf:
        rf.write(get_generation_comment("<!--", env.base_dir).rstrip() + " -->\n\n")
        rf.write("\n".join(report) + "\n")

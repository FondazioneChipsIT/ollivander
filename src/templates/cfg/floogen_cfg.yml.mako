<%
  import math
  p_name = config.project.name
  
  # 1. Largest coordinates the placements reach, i.e. the size of the router mesh.
  comps = [config.host] + config.components
  max_x, max_y = 0, 0
  
  for c in comps:
      p = getattr(c, 'placement', None)
      if not p or 'logical' not in p: continue
      log = p['logical']
      items = log if isinstance(log, list) else [log]
      for item in items:
          if 'box' in item:
              max_x = max(max_x, item['box']['x_end'])
              max_y = max(max_y, item['box']['y_end'])
          else:
              max_x = max(max_x, item['x'])
              max_y = max(max_y, item['y'])

  endpoints = []
  connections = []

  # 2. One endpoint and its physical connections per component that rides the NoC.
  for c in comps:
      if not c.interfaces or 'noc_networks' not in c.interfaces:
          continue
          
      noc_nets_raw = c.interfaces.get('noc_networks', [])
      mst_nets = noc_nets_raw.get('master', []) if isinstance(noc_nets_raw, dict) else noc_nets_raw
      slv_nets = noc_nets_raw.get('slave', []) if isinstance(noc_nets_raw, dict) else noc_nets_raw
      
      protocols_mgr = []
      protocols_sbr = []
      if c.interfaces.get('axi_master'):
          if "narrow" in mst_nets: protocols_mgr.append("narrow_in")
          if "wide" in mst_nets: protocols_mgr.append("wide_in")
          
      slaves = c.interfaces.get('axi_slave', [])
      if isinstance(slaves, dict): slaves = [slaves]
      if slaves:
          if "narrow" in slv_nets: protocols_sbr.append("narrow_out")
          if "wide" in slv_nets: protocols_sbr.append("wide_out")
          
      en_collective = c.features.get('multicast_target', False) if c.features else False
          
      # Placement: the logical coordinates become FlooGen ranges.
      p = getattr(c, 'placement', None)
      if not p or 'logical' not in p: continue
      log = p['logical']
      items = log if isinstance(log, list) else [log]

      boxes = []
      for item in items:
          if 'box' in item:
              b = item['box']
              boxes.append((b['x_start'], b['x_end'], b['y_start'], b['y_end']))
          else:
              boxes.append((item['x'], item['x'], item['y'], item['y']))

      array_str = None
      if len(boxes) == 1:
          x_len = boxes[0][1] - boxes[0][0] + 1
          y_len = boxes[0][3] - boxes[0][2] + 1
          if x_len > 1 and y_len > 1:
              array_str = f"[{x_len}, {y_len}]"
              connections.append({
                  'src': c.name,
                  'dst': "mesh_router",
                  'src_range': [[0, x_len - 1], [0, y_len - 1]],
                  'dst_range': [[boxes[0][0], boxes[0][1]], [boxes[0][2], boxes[0][3]]],
                  'dst_dir': "Eject"
              })
          elif x_len > 1 or y_len > 1:
              count = max(x_len, y_len)
              array_str = f"[{count}]"
              connections.append({
                  'src': c.name,
                  'dst': "mesh_router",
                  'src_range': [[0, count - 1]],
                  'dst_range': [[boxes[0][0], boxes[0][1]], [boxes[0][2], boxes[0][3]]],
                  'dst_dir': "Eject"
              })
          else:
              connections.append({
                  'src': c.name,
                  'dst': "mesh_router",
                  'dst_idx': [boxes[0][0], boxes[0][2]],
                  'dst_dir': "Eject"
              })
      else:
          # Several disjoint boxes: one flat array whose slices map to each box in turn.
          total = sum((b[1]-b[0]+1)*(b[3]-b[2]+1) for b in boxes)
          array_str = f"[{total}]"
          curr_idx = 0
          for b in boxes:
              count = (b[1]-b[0]+1)*(b[3]-b[2]+1)
              connections.append({
                  'src': c.name,
                  'dst': "mesh_router",
                  'src_range': [[curr_idx, curr_idx + count - 1]],
                  'dst_range': [[b[0], b[1]], [b[2], b[3]]],
                  'dst_dir': "Eject"
              })
              curr_idx += count
              
      endpoints.append({
          'name': c.name,
          'comp': c,
          'array': array_str,
          'slaves': slaves,
          'mgr': protocols_mgr,
          'sbr': protocols_sbr,
          'en_collective': en_collective
      })

  # 3. ENDPOINT UNROLLING.
  #
  # FlooGen's 'array:' form carries ONE base and ONE size, and derives each instance's window
  # as 'base + i * size'. Its output is already per-instance - an eight-instance array emits
  # eight independent SAM rules - but the input shorthand can only describe a uniform stride
  # and a uniform depth. So when a list on 'base_addr' or 'size_per_instance' breaks either,
  # the array is replaced by ONE ENDPOINT PER INSTANCE, each stating its own window, and its
  # range connection by one 'dst_idx' connection per instance. That is exactly how the
  # reference design describes the same hardware (l2_spm_0 .. l2_spm_3, each with its own
  # ranges), and RDL needs the identical treatment for the identical reason.
  #
  # Safe by construction on our side: nothing outside FlooGen's own package names an endpoint -
  # not the generated RTL, not the testbench, not one template - and a tile receives its
  # identity as a coordinate ('id_t'), never as an index into the endpoint list. Unrolling
  # therefore changes the SAM's contents and leaves every module interface untouched. Naming
  # the instances '<name>_<i>' also keeps FlooGen's enum entries in the same shape the array
  # produced. A uniform project takes the 'else' branch and its configuration is unchanged.
  from core.utils import instance_coords, instance_count, resolve_instance_windows

  final_endpoints, final_connections = [], list(connections)
  for ep in endpoints:
      comp, count = ep['comp'], instance_count(ep['comp'])
      uniform = True
      if ep['array'] and ep['slaves'] and count > 1:
          for slv in ep['slaves']:
              wins = resolve_instance_windows(slv, count)
              sizes = {size for _, size in wins}
              strides = {wins[k + 1][0] - wins[k][0] for k in range(count - 1)}
              # FlooGen's array is faithful only when every instance has the same depth and
              # the pitch equals it; anything else has to be spelled out.
              if len(sizes) > 1 or strides != sizes:
                  uniform = False
      if uniform:
          final_endpoints.append(ep)
          continue

      coords = instance_coords(comp)
      for k in range(count):
          per_instance = []
          for slv in ep['slaves']:
              base, size = resolve_instance_windows(slv, count)[k]
              window = dict(slv)
              window.pop('size_per_instance', None)
              window['base_addr'], window['size'] = base, size
              per_instance.append(window)
          final_endpoints.append(dict(ep, name=f"{ep['name']}_{k}", array=None,
                                      slaves=per_instance))
      final_connections = [cn for cn in final_connections if cn['src'] != ep['name']]
      for k in range(count):
          final_connections.append({'src': f"{ep['name']}_{k}", 'dst': "mesh_router",
                                    'dst_idx': [coords[k][0], coords[k][1]],
                                    'dst_dir': "Eject"})

  endpoints, connections = final_endpoints, final_connections
%><%namespace file="/license_header.mako" import="license"/>\
${license('#')}\
# AUTOMATICALLY GENERATED BY OLLIVANDER - DO NOT EDIT DIRECTLY
#
# FlooGen NoC Configuration for ${p_name}
# Description: ${config.project.description}

## FlooGen derives the generated package name from this field (floo_<name>_noc_pkg),
## so it must follow the top-level module name rather than the bare project name:
## two macros exported from the same project would otherwise produce two packages with
## the same name and different contents, and could not coexist in one library.
name: "${config.project.top_level_module_name}"
description: "${config.project.description}"
network_type: "narrow-wide"

## The routing algorithm comes from the SoC description, like everything else the user declares:
## the NoC placement checker validates placements against the same field, and the two must never
## be allowed to disagree.
routing:
  route_algo: "${config.topology.noc_settings.routing_algorithm}"
  use_id_table: true
  collective:
    en_narrow_multicast: true
    en_wide_multicast: true
    en_barrier: true
    en_wide_reduction:
      rd_pipeline_depth: 5
      cut_offload_intf: true
  decouple_rw: Phys
  vc_impl: naive

<%
  ## Both networks are guaranteed by the schema (Topology.check_topology_config), so neither the
  ## lookup nor the widths below need a fallback.
  narrow_net = config.topology.noc_settings.networks['narrow']
  ## Resolved in src/core/macro_boundary.py, from the ID widths the nested macros impose on
  ## each network, and handed to this template and to the SoC package alike so the two cannot
  ## disagree. A network declaring 'id_width' keeps that value and is only checked against
  ## what the macros need; one that leaves it unset has it derived. The branch that used to
  ## sit here guessed a width from the host parameters and the slave count, and was dead in
  ## every project, 'id_width' having a schema default that made it unreachable.
  g_id_w = noc_id_widths['narrow']
  g_wide_id_w = noc_id_widths['wide']
  ## The compressed output side of each network, from the same module that resolves the
  ## input side, so the capacity check a component is validated against (soc_schema.py)
  ## and the network emitted here cannot disagree.
  from core.macro_boundary import NOC_OUTPUT_ID_WIDTH
  g_out_id_w = NOC_OUTPUT_ID_WIDTH['narrow']
  g_wide_out_id_w = NOC_OUTPUT_ID_WIDTH['wide']

  ## Width of the AXI user field carried by the NARROW network: the span of the SoC user mapping
  ## that has defined semantics, i.e. up to the highest of the AMO reservation bits and the ECC
  ## error flag. Derived rather than hardcoded so the network keeps carrying every meaningful bit
  ## if the mapping ever moves.
  ##
  ## The WIDE network deliberately keeps a single user bit, and the reason is worth stating because
  ## widening it looks like an improvement and is not. Every endpoint that reads user bits sits
  ## behind a narrow/wide join, and floo_pkg::axi_join_cfg takes UserWidth as the *maximum* of the
  ## two configurations - so the joined port already carries the narrow width whatever the wide one
  ## is, and the L2, the only endpoint using those bits (AxiUserAtop over user[1:0]), gains nothing
  ## from a wider wide network. What it does gain is a mismatch: snitch_cluster generates its own
  ## wide port as 'typedef logic user_dma_t', one bit, because a DMA transfer carries no atomic
  ## reservation. Raising the network to 5 therefore moved the truncation from the network to every
  ## cluster port instead of removing it, at 4 user bits per channel - measured as 64 vopt-2241
  ## warnings across the 16 clusters of super_mesh.
  ## Resolved in src/core/macro_boundary.py, which also uses them to refuse a nested macro
  ## whose meaningful user span would not survive the network it injects on.
  g_narrow_user_w = noc_user_widths['narrow']
  g_wide_user_w = noc_user_widths['wide']

  ## Physical dimensions of the two networks, from the SoC description. The generated SoC
  ## package derives its narrow/wide channel types from the same fields (noc_soc_pkg.sv.mako),
  ## so reading them here is what keeps the FlooNoC network and the SoC-side types a single
  ## source of truth: a hardcoded copy would drift silently the day a project changes them.
  ## The multicast mask is an address mask, so its width IS the address width.
  wide_net = config.topology.noc_settings.networks['wide']
  n_data_w = narrow_net.data_width
  n_addr_w = narrow_net.addr_width
  w_data_w = wide_net.data_width
  w_addr_w = wide_net.addr_width
%>
protocols:
  - name: "narrow_in"
    type: "narrow"
    protocol: "AXI4"
    data_width: ${n_data_w}
    addr_width: ${n_addr_w}
    id_width: ${g_id_w}
    user_width:
      collective_mask: ${n_addr_w}
      collective_op: 4 # width of FlooNoC collect_op_e, fixed by the IP
      user: ${g_narrow_user_w}
  - name: "narrow_out"
    type: "narrow"
    protocol: "AXI4"
    data_width: ${n_data_w}
    addr_width: ${n_addr_w}
    id_width: ${g_out_id_w}
    user_width:
      collective_mask: ${n_addr_w}
      collective_op: 4
      user: ${g_narrow_user_w}
  - name: "wide_in"
    type: "wide"
    protocol: "AXI4"
    data_width: ${w_data_w}
    addr_width: ${w_addr_w}
    id_width: ${g_wide_id_w}
    user_width:
      collective_mask: ${w_addr_w}
      collective_op: 4
      user: ${g_wide_user_w}
  - name: "wide_out"
    type: "wide"
    protocol: "AXI4"
    data_width: ${w_data_w}
    addr_width: ${w_addr_w}
    id_width: ${g_wide_out_id_w}
    user_width:
      collective_mask: ${w_addr_w}
      collective_op: 4
      user: ${g_wide_user_w}

endpoints:
% for ep in endpoints:
  - name: "${ep['name']}"
  % if ep['array']:
    array: ${ep['array']}
  % endif
  % if ep['slaves']:
    addr_range:
   % if len(ep['slaves']) == 1:
    % if ep['array']:
      base: 0x${"%08X" % (ep['slaves'][0].get('base_addr', 0))}
    % else:
      start: 0x${"%08X" % (ep['slaves'][0].get('base_addr', 0))}
    % endif
      size: 0x${"%08X" % (ep['slaves'][0].get('size', ep['slaves'][0].get('size_per_instance', 0)))}
    % if ep['slaves'][0].get('name'):
      desc: "${ep['slaves'][0].get('name')}"
    % endif
    % if ep['en_collective']:
      en_collective: true
    % endif
   % else:
    % for slv in ep['slaves']:
     % if ep['array']:
      - base: 0x${"%08X" % slv.get('base_addr', 0)}
     % else:
      - start: 0x${"%08X" % slv.get('base_addr', 0)}
     % endif
       % if slv.get('size') or slv.get('size_per_instance'):
        size:  0x${"%08X" % slv.get('size', slv.get('size_per_instance', 0))}
       % endif
        desc: "${slv.get('name', 'region')}"
      % if ep['en_collective']:
        en_collective: true
      % endif
    % endfor
   % endif
  % endif
  % if ep['mgr']:
    mgr_port_protocol:
   % for p in ep['mgr']:
      - "${p}"
   % endfor
  % endif
  % if ep['sbr']:
    sbr_port_protocol:
   % for p in ep['sbr']:
      - "${p}"
   % endfor
  % endif
% endfor

routers:
  - name: "mesh_router"
    array: [${max_x + 1}, ${max_y + 1}]
    degree: 5

connections:
% for conn in connections:
  - src: "${conn['src']}"
    dst: "${conn['dst']}"
  % if 'src_range' in conn:
    src_range:
    % for sr in conn['src_range']:
      - [${sr[0]}, ${sr[1]}]
    % endfor
  % endif
  % if 'dst_range' in conn:
    dst_range:
    % for dr in conn['dst_range']:
      - [${dr[0]}, ${dr[1]}]
    % endfor
  % endif
  % if 'dst_idx' in conn:
    dst_idx: [${conn['dst_idx'][0]}, ${conn['dst_idx'][1]}]
  % endif
    dst_dir: "${conn['dst_dir']}"
% endfor

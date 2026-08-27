<%
  # Build the two-dimensional grid the tiles are placed on.
  from core.utils import instance_count, resolve_instance_windows

  comps = [config.host] + config.components
  max_x, max_y = 0, 0
  grid = {}

  for c in comps:
      p = getattr(c, 'placement', None)
      if not p or 'logical' not in p: continue
      
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
              
  header_row = "Y \\ X," + ",".join([str(x) for x in range(max_x + 1)])
%>\
${header_row}
% for y in range(max_y, -1, -1):
<%
  row_cells = [str(y)]
  for x in range(max_x + 1):
      if (x,y) in grid:
          c, idx = grid[(x,y)]
          lines = [c.name]
          if c.interfaces:
              # This cell's own windows, from the single resolver: with a list on 'base_addr'
              # or 'size_per_instance' the address is not 'base + idx * size', and an address
              # map that disagreed with the hardware would be worse than none at all.
              for block, label in (('regbus_slave', 'Reg'), ('axi_slave', 'Mem')):
                  if block not in c.interfaces:
                      continue
                  slvs = c.interfaces[block]
                  slvs = slvs if isinstance(slvs, list) else [slvs]
                  addr, _ = resolve_instance_windows(slvs[0], instance_count(c))[idx]
                  lines.append(f"{label}: 0x{addr:08X}")
          row_cells.append('"' + '\n'.join(lines) + '"')
      else:
          row_cells.append("dummy")
%>\
${",".join(row_cells)}
% endfor

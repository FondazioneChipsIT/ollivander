<%
  # Costruzione della griglia bidimensionale per il piazzamento delle Tile
  comps = [config.host] + config.components
  max_x, max_y = 0, 0
  grid = {}
  
  def parse_val(v):
      if isinstance(v, int): return v
      if isinstance(v, str):
          v = v.replace('_', '')
          return int(v, 16) if v.lower().startswith('0x') else int(v)
      return 0

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
              if 'regbus_slave' in c.interfaces:
                  slvs = c.interfaces['regbus_slave']
                  slvs = slvs if isinstance(slvs, list) else [slvs]
                  base = parse_val(slvs[0].get('base_addr', 0))
                  size = parse_val(slvs[0].get('size_per_instance', 0))
                  addr = base + (idx * size)
                  lines.append(f"Reg: 0x{addr:08X}")
              if 'axi_slave' in c.interfaces:
                  slvs = c.interfaces['axi_slave']
                  slvs = slvs if isinstance(slvs, list) else [slvs]
                  base = parse_val(slvs[0].get('base_addr', 0))
                  size = parse_val(slvs[0].get('size_per_instance', 0))
                  addr = base + (idx * size)
                  lines.append(f"Mem: 0x{addr:08X}")
          row_cells.append('"' + '\n'.join(lines) + '"')
      else:
          row_cells.append("dummy")
%>\
${",".join(row_cells)}
% endfor
<%
  def parse_hex(val):
      if isinstance(val, int): return f"0x{val:08X}"
      if not val: return "N/A"
      return "0x" + str(val).replace('0x', '').replace('_', '').upper().zfill(8)
     
  def get_val(v, default=0):
      if v is None: return default
      if isinstance(v, int): return v
      v_str = str(v).lower().replace('_', '')
      if v_str.startswith('0x'): return int(v_str, 16)
      if v_str.startswith('0b'): return int(v_str, 2)
      try: return int(v_str)
      except: return default

  axi_slaves = []
  axi_masters = []
  reg_slaves_sync = [config.system_controller.name] if config.system_controller else []
  reg_slaves_async = []

  if config.components:
      for c in config.components:
          if c.interfaces:
              if c.interfaces.get('axi_master'):
                  axi_masters.append(c.name)
              if 'axi_slave' in c.interfaces:
                  slvs = c.interfaces['axi_slave']
                  if isinstance(slvs, dict): slvs = [slvs]
                  for slv in slvs:
                      for _ in range(slv.get('ports', 1)):
                          axi_slaves.append(c.name)
              if 'regbus_slave' in c.interfaces:
                  slvs = c.interfaces['regbus_slave']
                  if isinstance(slvs, dict): slvs = [slvs]
                  for slv in slvs:
                      for _ in range(slv.get('ports', 1)):
                          if slv.get('sync_domain', True):
                              reg_slaves_sync.append(c.name)
                          else:
                              reg_slaves_async.append(c.name)
  all_reg_slaves = reg_slaves_sync + reg_slaves_async

  def get_indices(comp_name, lst):
      return [i for i, x in enumerate(lst) if x == comp_name]
%>\
Component,Type,Location,Interface,Sync/Async,Host Index,Base Address,Size (Bytes),Clock Domain
<%
  lines = []
  def add_entries(comp, parent_name=None):
      comp_name = f"{parent_name}.{comp.name}" if parent_name else comp.name
      clk = comp.clock_domain or config.host.clock_domain or "host_clk"
      loc = "External" if is_external(comp) else "Internal"
      
      intfs = []
      idxs = []
      bases = []
      sizes = []
      clks = []
      syncs = []

      if comp.interfaces:
          if comp.interfaces.get('axi_master'):
              idx_list = get_indices(comp.name, axi_masters)
              idx_str = str(idx_list[0]) if idx_list else "N/A"
              intfs.append("axi_master")
              idxs.append(idx_str)
              bases.append("N/A")
              sizes.append("N/A")
              clks.append(clk)
              syncs.append("Sync" if comp.name == config.host.name else "Async")
          if 'axi_slave' in comp.interfaces:
              slvs = comp.interfaces['axi_slave']
              if isinstance(slvs, dict): slvs = [slvs]
              idx_list = get_indices(comp.name, axi_slaves)
              port_counter = 0
              for slv in slvs:
                  num_ports = slv.get('ports', 1)
                  base = get_val(slv.get('base_addr'))
                  size = get_val(slv.get('size', slv.get('size_per_instance', 0)))
                  sync = "Sync" if slv.get('sync_domain', True) else "Async"
                  for p in range(num_ports):
                      idx_str = str(idx_list[port_counter]) if port_counter < len(idx_list) else "N/A"
                      intfs.append("axi_slave")
                      idxs.append(idx_str)
                      bases.append(parse_hex(base))
                      sizes.append(parse_hex(size))
                      clks.append(clk)
                      syncs.append(sync)
                      port_counter += 1
          if 'regbus_slave' in comp.interfaces:
              slvs = comp.interfaces['regbus_slave']
              if isinstance(slvs, dict): slvs = [slvs]
              idx_list = get_indices(comp.name, all_reg_slaves)
              port_counter = 0
              for slv in slvs:
                  num_ports = slv.get('ports', 1)
                  base = get_val(slv.get('base_addr'))
                  size = get_val(slv.get('size', 0x1000))
                  sync = "Sync" if slv.get('sync_domain', True) else "Async"
                  for p in range(num_ports):
                      idx_str = str(idx_list[port_counter]) if port_counter < len(idx_list) else "N/A"
                      intfs.append("regbus_slave")
                      idxs.append(idx_str)
                      bases.append(parse_hex(base))
                      sizes.append(parse_hex(size))
                      clks.append(clk)
                      syncs.append(sync)
                      port_counter += 1
                      
      if intfs:
          intfs_str = '"' + '\n'.join(intfs) + '"' if len(intfs) > 1 else intfs[0]
          idxs_str = '"' + '\n'.join(idxs) + '"' if len(idxs) > 1 else idxs[0]
          bases_str = '"' + '\n'.join(bases) + '"' if len(bases) > 1 else bases[0]
          sizes_str = '"' + '\n'.join(sizes) + '"' if len(sizes) > 1 else sizes[0]
          clks_str = '"' + '\n'.join(clks) + '"' if len(clks) > 1 else clks[0]
          syncs_str = '"' + '\n'.join(syncs) + '"' if len(syncs) > 1 else syncs[0]
          lines.append(f"{comp_name},{comp.type},{loc},{intfs_str},{syncs_str},{idxs_str},{bases_str},{sizes_str},{clks_str}")

      if comp.components:
          idx = 0
          for sub in comp.components:
              if getattr(sub, 'base_addr', None):
                  base = parse_hex(sub.base_addr)
                  size = parse_hex(getattr(sub, 'size', '0x1000'))
                  lines.append(f"{comp_name}.{sub.name},{sub.type},{loc},apb_slave,Sync,{idx},{base},{size},{clk}")
                  idx += 1
              
  if config.system_controller:
      base = parse_hex(config.system_controller.base_addr)
      size = parse_hex(config.system_controller.size)
      lines.append(f"{config.system_controller.name},system_controller,Internal,regbus_slave,Sync,0,{base},{size},host_clk")
      
  add_entries(config.host)
  if config.components:
      for c in config.components:
          add_entries(c)
%>\
% for line in lines:
${line}
% endfor
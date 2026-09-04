## Interrupt routing, shared by crossbar_soc_top.sv.mako and noc_soc_top.sv.mako.
## The Python half lives in core/interrupt_routing.py (irq_plan); 'irq' below is its
## result. The text is the crossbar top's, moved here verbatim so that the crossbar
## output stays byte-identical - keep it that way when touching either def.
<%!
  import re
  from core.utils import fmt_rst
%>
<%def name="interrupt_wires(irq)">\
  // Physical Interconnect Wires
% for (c_name, prt_name), dim in irq['out_ports'].items():
  logic ${dim + " " if dim else ""}intr_${c_name}_${prt_name};
% endfor
</%def>
<%def name="interrupt_routing(irq, pkg, require_file)">\
  // Logical Aliases for sparse interrupt mapping.
  // If an interrupt destination is just a single bit of a larger bus, we create an alias wire.
% for c, irq_name, irq_cfg, c_clk, c_rst in irq['all_irqs']:
 % if not irq_cfg.get('source'):
  % if irq_cfg.get('port') and irq_cfg.get('port') != irq_name:
  <% 
    bit_idx = irq_cfg.get('bit', 0)
    dim = irq['port_dim'](c.name, irq_name, False)
  %>
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name};
  assign intr_${c.name}_${irq_name} = intr_${c.name}_${irq_cfg['port']}[${bit_idx}];
  % endif
 % endif
% endfor

  // =========================================================================
  // 4. INTERRUPT ROUTING (MAPPED SOURCES)
  // =========================================================================
  // Generates continuous assignments for interrupts defined using the 
  // '{ [bit] : component.port }' dictionary syntax in the YAML.

% for c, irq_name, irq_cfg, source_str in irq['complex_irqs']:
  <% 
     dim = irq['port_dim'](c.name, irq_name, True)
     mappings = re.findall(r'(\[[^\]]+\])\s*:\s*([^,\n]+)', source_str[1:-1])
  %>\
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name};
  always_comb begin
    intr_${c.name}_${irq_name} = '0; // Unmapped bits default to zero
  % for idx, src in mappings:
    <% 
       is_valid, missing = irq['src_valid'](src)
       if is_valid:
           val_processed = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', src.strip())
       else:
           val_processed = f"'0 /* Missing component: {missing} */"
    %>\
    intr_${c.name}_${irq_name}${idx} = ${val_processed};
  % endfor
  end
% endfor

  // =========================================================================
  // 5. INTER-DOMAIN SYNCHRONIZERS (CDC)
  // =========================================================================
  // Automatically generates multi-stage synchronizers whenever an interrupt 
  // connection spans across two different clock domains, guaranteeing a safe 
  // transition without metastability.

% for c, irq_name, irq_cfg, c_clk, c_rst, source_str in irq['sync_irqs']:
  // Synchronizer for ${c.name} ${irq_name} (CDC to ${c_clk})
  <%
    dim = irq['port_dim'](c.name, irq_name, True)
  %>\
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name}_async;
  % if source_str.startswith('{'):
  assign intr_${c.name}_${irq_name}_async = intr_${c.name}_${irq_name};
  % else:
  <% 
     processed_str = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', r'intr_\1_\2', source_str)
     rep = ""
     src_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$', source_str.strip())
     if src_match and not irq['port_dim'](src_match.group(1), src_match.group(2), False):
         rep = irq['rep_factor'](dim)
  %>\
  assign intr_${c.name}_${irq_name}_async = ${f"'{{default: {processed_str}}}" if rep else processed_str};
  % endif
  
  ${require_file("olli_sync.sv")}
  logic ${dim + " " if dim else ""}intr_${c.name}_${irq_name}_sync;
  
  % if dim:
  for (genvar i = 0; i < $bits(intr_${c.name}_${irq_name}_async); i++) begin : gen_sync_${c.name}_${irq_name}
  olli_sync #(
    .STAGES    (3),
    .ResetValue(1'b0)
  ) i_sync_${c.name}_${irq_name} (
    .clk_i    ( ${c_clk} ),
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'} ),
    .serial_i ( intr_${c.name}_${irq_name}_async[i] ),
    .serial_o ( intr_${c.name}_${irq_name}_sync[i] )
  );
  end
  % else:
  olli_sync #(
    .STAGES    (3),
    .ResetValue(1'b0)
  ) i_sync_${c.name}_${irq_name} (
    .clk_i    ( ${c_clk} ),
    .rst_ni   ( ${'host_pwr_on_rst_n' if c_rst == 'host_rst' else f'pwr_on_rsts_n[{pkg}::DomainIdx_{fmt_rst(c_rst)}]'} ),
    .serial_i ( intr_${c.name}_${irq_name}_async ),
    .serial_o ( intr_${c.name}_${irq_name}_sync )
  );
  % endif

% endfor
</%def>

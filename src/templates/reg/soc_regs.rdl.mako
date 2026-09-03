<%namespace file="/license_header.mako" import="license"/>\
${license(prefix='//')}\
// =========================================================================
// OLLIVANDER AUTO-GENERATED SYSTEMRDL
// =========================================================================
// Project: ${config.project.name}
// Description: ${config.project.description}
//
// This template generates the System Controller (PCR) register map in 
// SystemRDL format. It dynamically includes registers for clock gating, 
// resets, AXI isolation, and boot control based on the specific hardware 
// components instantiated in the SoC configuration.
// =========================================================================

<%
  # =========================================================================
  # POWER-ON POLICY FOR CLOCK-ENABLE AND SOFTWARE-RESET REGISTERS
  # =========================================================================
  # A single convention is applied to every clock/reset control register in this
  # file, for managed clock domains and for auto control groups alike:
  #
  #   *_clk_en : active high, 1 = clock enabled
  #   *_rst    : active high, 1 = block held in reset
  #
  # Both are consumed in RTL with an explicit bit index; `*_rst` is inverted once
  # to obtain the active-low reset the hardware expects. The reset values below
  # come from `system_controller.power_on_state`, so the two mechanisms can never
  # end up with opposite power-on behaviour.
  gated_at_por = config.gated_at_power_on

  def por_clk_en(width):
      """Power-on value of a clock-enable field: all clocks off when gated."""
      return "0" if gated_at_por else f"{width}'h{(1 << width) - 1:x}"

  # ISOLATION FIELDS, ONE PER COMPONENT AND num_instances BITS WIDE.
  #
  # A single bit per component at its own position in the list would be wrong: it
  # made a multi-instance component impossible to isolate individually - and, worse, made every
  # instance's tile drive the SAME status bit, a driver conflict that only never appeared
  # because no NoC component declared 'isolate'. Bits are allocated cumulatively here so the
  # control and the status always agree, and the same allocation feeds the RTL: the IR indexes
  # this field, it does not recompute the offset.
  #
  # Reset value: ISOLATED (all ones). A block comes out of reset fenced and software opens it,
  # which matches the reset state of the axi_isolate cell itself (its state registers reset to
  # 'Isolate') and the software-reset registers above.
  iso_fields = []
  _iso_bit = 0
  for _c in components:
      _sc = _c.get('system_config') or {}
      if not _sc.get('isolate'):
          continue
      _n = _c.get('num_instances', 1) or 1
      iso_fields.append((_c, _iso_bit, _iso_bit + _n - 1))
      _iso_bit += _n
  if _iso_bit > 32:
      raise ValueError(
          f"isolation needs {_iso_bit} bits but the control register is 32 wide: "
          f"the components declaring 'isolate' expand into too many instances between them")

  def por_rst(width):
      """Power-on value of a software-reset field: ALWAYS held in reset, in both policies.

      Deliberately NOT a function of 'power_on_state'. A tile takes this bit as its ONLY
      reset source (universal_tile.sv.mako), so the power-on reset reaches a tile's payload
      THROUGH this reset value - the route the gwaihir reference uses. Were it to reset
      released, an 'enabled' project would bring its tiles out of reset at time zero while
      the rest of the SoC is still in POR, and the only way to prevent that would be to AND
      the two resets inside the tile: combinational logic on a reset net, downstream of the
      POR synchronizer, which undoes the synchronous release it just produced and can carry
      a glitch to part of the domain.

      'power_on_state' keeps its meaning where it belongs, on the clock enables: 'enabled'
      means the clocks are already running, not that the tiles skipped their reset.
      """
      return f"{width}'h{(1 << width) - 1:x}"
%>\
addrmap ${top_level_module_name}_sys_regs {
    name = "${config.project.name} System Controller";
    desc = "System Control and Status Registers";

    default regwidth = 32;
    default sw = rw;
    default hw = r;

    // ---------------------------------------------------------------------
    // Isolation Control & Status
    // ---------------------------------------------------------------------
    // Controls the AXI isolation cells to safely decouple clock/power domains 
    // before resetting a component, preventing interconnect hangs.
    % if any(c.get('system_config') and c.get('system_config').get('isolate') for c in components):
    reg {
        name = "Isolation Control";
        desc = "Assert to isolate component's AXI interface before applying reset";
        % for c, lo, hi in iso_fields:
        field {
            name = "${c['name']}_isolate";
            desc = "Isolate ${c['name']}${" (one bit per instance)" if hi > lo else ""}";
            hw = r; sw = rw;
        } ${c['name']}_isolate[${hi}:${lo}] = ${hi - lo + 1}'h${"%x" % ((1 << (hi - lo + 1)) - 1)};
        % endfor
    } isolate_ctrl;

    reg {
        name = "Isolation Status";
        desc = "Acknowledgment from the hardware that AXI isolation is complete and safe";
        default sw = r; default hw = w;
        % for c, lo, hi in iso_fields:
        field {
            name = "${c['name']}_isolated";
            desc = "${c['name']} isolated status${" (one bit per instance)" if hi > lo else ""}";
        } ${c['name']}_isolated[${hi}:${lo}] = 0;
        % endfor
    } isolate_status;
    % endif
<%
  # COLLECTIVE OPCODES, one register for the whole SoC, two 4-bit fields per
  # multicast-target component: the operation its column and row reduction
  # windows stamp (FlooNoC collect_op_e; reset IntAdd = 7). Emitted when the SoC
  # declares the narrow reduction channel; a component that turns out to have no
  # reduction windows leaves its fields unused. The tile takes them as ports.
  _nr = (config.topology.type == "noc" and config.topology.noc_settings.collectives.narrow_reduction.enable)
  coll_comps = [_c for _c in components if _nr and (_c.get('features') or {}).get('multicast_target')]
%>\
    % if coll_comps:
    reg {
        name = "Collective Opcodes";
        desc = "Operation stamped by each group's column and row reduction windows (FlooNoC collect_op_e: 7 IntAdd, 8 IntMul, 9 IntMinS, 10 IntMinU, 11 IntMaxS, 12 IntMaxU)";
        % for _c in coll_comps:
        field { hw = r; sw = rw; } ${_c['name']}_coll_col_op[${loop.index * 8 + 3}:${loop.index * 8}] = 4'h7;
        field { hw = r; sw = rw; } ${_c['name']}_coll_row_op[${loop.index * 8 + 7}:${loop.index * 8 + 4}] = 4'h7;
        % endfor
    } collective_ctrl;
    % endif

    // ---------------------------------------------------------------------
    // Fetch Enable
    // ---------------------------------------------------------------------
    // Allows the host software to hold compute clusters in a halted state 
    // after reset de-assertion until their local memories are preloaded.
    % if any(c.get('system_config') and c.get('system_config').get('fetch_enable') for c in components):
    reg {
        name = "Fetch Enable";
        desc = "Allow compute cores to start fetching instructions";
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('fetch_enable')]):
        field {
            name = "${c['name']}_fetch_enable";
            desc = "Fetch enable for ${c['name']}";
            hw = r; sw = rw;
        } ${c['name']}_fetch_enable[${i}:${i}] = 0;
        % endfor
    } fetch_enable;
    % endif

    // ---------------------------------------------------------------------
    // Boot Enable (Hardware Boot Sequence)
    // ---------------------------------------------------------------------
    // Triggers standalone hardware boot sequences, such as instructing a DMA 
    // to load firmware from an external SPI Flash into the L2 SRAM.
    % if any(c.get('system_config') and c.get('system_config').get('boot_enable') for c in components):
    reg {
        name = "Boot Enable";
        desc = "Triggers standalone hardware boot sequence";
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('boot_enable')]):
        field {
            name = "${c['name']}_boot_enable";
            desc = "Boot enable for ${c['name']}";
            hw = r; sw = rw;
        } ${c['name']}_boot_enable[${i}:${i}] = 0;
        % endfor
    } boot_enable;
    % endif

    // ---------------------------------------------------------------------
    // Debug Request
    // ---------------------------------------------------------------------
    // External debug request lines to manually halt CPUs for JTAG intervention.
    % if any(c.get('system_config') and c.get('system_config').get('debug_req') for c in components):
    reg {
        name = "Debug Request";
        desc = "Send external debug halt request to CPUs";
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('debug_req')]):
        field {
            name = "${c['name']}_debug_req";
            desc = "Debug request for ${c['name']}";
            hw = r; sw = rw;
        } ${c['name']}_debug_req[${i}:${i}] = 0;
        % endfor
    } debug_req;
    % endif

    // ---------------------------------------------------------------------
    // Boot Addresses
    // ---------------------------------------------------------------------
    // Programmable boot addresses fetched by the CPUs upon reset de-assertion.
    % for c in components:
        % if c.get('system_config') and 'boot_addr' in c.get('system_config'):
    reg {
        name = "${c['name']} Boot Address";
        desc = "Initial Program Counter (Boot Address) for ${c['name']}";
        field {
            name = "${c['name']}_boot_addr";
            desc = "Boot address for ${c['name']}";
            hw = r; sw = rw;
        } ${c['name']}_boot_addr[31:0] = ${c['system_config']['boot_addr']};
    } ${c['name']}_boot_addr;
        % endif
    % endfor

    // ---------------------------------------------------------------------
    // Clock and Reset Tree Control
    // ---------------------------------------------------------------------
    // Dynamic clock multiplexing, integer division, clock gating, and software 
    // resets for the globally managed clock domains.
    % for dom in domains:
        % if not dom.get('is_real_time'):
            % if dom.get('name') != (config.host.clock_domain or 'system_clk'):
                % if dom.get('has_mux'):
    reg {
        name = "${dom['name']} Clock Source Select";
        desc = "Selects the clock source for ${dom['name']}";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_clk_sel[31:0] = 0;
    } ${fmt_reg(dom['name'])}_clk_sel;
                % endif

                % if dom.get('has_divider'):
    reg {
        name = "${dom['name']} Clock Divider Value";
        desc = "Clock divider value for ${dom['name']}";
        field { hw = r; sw = rw; swmod; } ${fmt_reg(dom['name'])}_clk_div_value[31:0] = ${dom.get('default_div', 1)};
    } ${fmt_reg(dom['name'])}_clk_div_value;

    reg {
        name = "${dom['name']} Clock Enable";
        desc = "Clock enable for ${dom['name']} (Active High, 1 = clock enabled)";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_clk_en[0:0] = ${por_clk_en(1)};
    } ${fmt_reg(dom['name'])}_clk_en;
                % endif

    reg {
        name = "${dom['name']} Software Reset";
        desc = "Software reset for ${dom['name']} (Active High, 1 = held in reset)";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_rst[0:0] = ${por_rst(1)};
    } ${fmt_reg(dom['name'])}_rst;
            % endif

            % if dom.get('has_debug_divider'):
    reg {
        name = "${dom['name']} Debug Clock Divider Value";
        desc = "Debug clock divider value for ${dom['name']}";
        field { hw = r; sw = rw; swmod; } ${fmt_reg(dom['name'])}_debug_clk_div_value[31:0] = 10;
    } ${fmt_reg(dom['name'])}_debug_clk_div_value;

    reg {
        name = "${dom['name']} Debug Clock Enable";
        desc = "Debug clock enable for ${dom['name']} (Active High, 1 = clock enabled)";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_debug_clk_en[0:0] = ${por_clk_en(1)};
    } ${fmt_reg(dom['name'])}_debug_clk_en;
            % endif
        % endif
    % endfor

    // ---------------------------------------------------------------------
    // Dedicated Clock Dividers
    // ---------------------------------------------------------------------
    // Independent clock dividers dedicated to specific IP interfaces that require 
    // highly constrained or non-standard frequencies.
    % for c in components:
        % if c.get('dedicated_clock_div'):
    reg {
        name = "${c['dedicated_clock_div']['name']} Clock Divider Value";
        desc = "Clock divider value for ${c['dedicated_clock_div']['name']}";
        field { hw = r; sw = rw; swmod; } ${fmt_reg(c['dedicated_clock_div']['name'])}_clk_div_value[31:0] = ${c['dedicated_clock_div'].get('default_div', 1)};
    } ${fmt_reg(c['dedicated_clock_div']['name'])}_clk_div_value;

    reg {
        name = "${c['dedicated_clock_div']['name']} Clock Enable";
        desc = "Clock enable for ${c['dedicated_clock_div']['name']} (Active High, 1 = clock enabled)";
        field { hw = r; sw = rw; } ${fmt_reg(c['dedicated_clock_div']['name'])}_clk_en[0:0] = ${por_clk_en(1)};
    } ${fmt_reg(c['dedicated_clock_div']['name'])}_clk_en;
        % endif
    % endfor

    // ---------------------------------------------------------------------
    // Busy Status
    // ---------------------------------------------------------------------
    // Hardware-driven status flags indicating when a component is actively 
    // processing data. Useful for power management and sleep decisions.
    % if any(c.get('system_config') and c.get('system_config').get('has_busy_status') for c in components):
    reg {
        name = "Busy Status";
        desc = "Component busy status indicator";
        default sw = r; default hw = w;
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('has_busy_status')]):
        field {
            name = "${c['name']}_busy";
            desc = "${c['name']} busy status";
        } ${c['name']}_busy[${i}:${i}] = 0;
        % endfor
    } busy_status;
    % endif

    // ---------------------------------------------------------------------
    // End of Computation (EOC) Status
    // ---------------------------------------------------------------------
    // Hardware-driven status flags indicating when an accelerator has finished 
    // its workload, acting as an alternative or complement to interrupts.
    % if any(c.get('system_config') and c.get('system_config').get('has_eoc_status') for c in components):
    reg {
        name = "EOC Status";
        desc = "End of Computation status indicator";
        default sw = r; default hw = w;
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('has_eoc_status')]):
        field {
            name = "${c['name']}_eoc";
            desc = "${c['name']} EOC status";
        } ${c['name']}_eoc[${i}:${i}] = 0;
        % endfor
    } eoc_status;
    % endif

    // ---------------------------------------------------------------------
    // Scratch Registers
    // ---------------------------------------------------------------------
    // General purpose read/write registers. Often used by firmware for 
    // inter-core communication, boot flags, or testing.
    % if sys_ctrl.get('scratch_registers', 0) > 0:
    reg {
        name = "Scratch Register";
        desc = "General purpose read/write scratchpad register";
        field { hw = r; sw = rw; } val[31:0] = 0;
    } scratch[${sys_ctrl.get('scratch_registers', 0)}];
    % endif

    // ---------------------------------------------------------------------
    // Version & JEDEC ID
    // ---------------------------------------------------------------------
    // Read-only hardware identification for driver capability discovery.
    % if sys_ctrl.get('version_registers', 0) > 0:
    reg {
        name = "Version Register";
        desc = "Read-only hardware version information";
        default sw = r; default hw = w;
        field { } val[31:0] = 0;
    } version[${sys_ctrl.get('version_registers', 0)}];
    % endif

    % if sys_ctrl.get('jedec_id') is not None:
    reg {
        name = "JEDEC ID";
        desc = "JEDEC Manufacturer ID";
        default sw = r; default hw = r; // Constant
        field { } val[31:0] = ${sys_ctrl.get('jedec_id', 0)};
    } jedec_id;
    % endif

    // ---------------------------------------------------------------------
    // Clock Generator Lock Status
    // ---------------------------------------------------------------------
    // Hardware-driven flags indicating that the external Clock Generators 
    // have achieved frequency lock and are stable.
    % if sys_ctrl.get('clk_gen_status_regs'):
    reg {
        name = "FLL Lock Status";
        desc = "FLL Lock signals";
        default sw = r; default hw = w;
        field { } clk_gen_lock[${config.clock_tree.generators - 1}:0] = 0;
    } clk_gen_lock;
    % endif

    // ---------------------------------------------------------------------
    // Auto Control Groups (NoC Clock/Reset Gating)
    // ---------------------------------------------------------------------
    // Aggregated clock gating and reset controls for arrays of identical NoC tiles.
    // This reduces CSR address space fragmentation and allows software to control
    // an entire grid of compute clusters with a single register write.
    % if config.system_controller and config.system_controller.auto_control_groups:
        % for g in config.system_controller.auto_control_groups:
        <%
          # Exactly one bit per controlled tile, so the register documents the size of
          # the array it drives instead of exposing 32 bits of which only a few exist.
          gw = config.control_group_width(g, original_isle_types)
        %>\
    reg {
        name = "${g.name} Clock Enable";
        desc = "Clock enable for the ${gw} ${g.name} tiles (Active High, one bit per tile, 1 = clock enabled)";
        field { hw = r; sw = rw; } ${g.name.lower()}_clk_en[${gw - 1}:0] = ${por_clk_en(gw)};
    } ${g.name.lower()}_clk_en;

    reg {
        name = "${g.name} Reset";
        desc = "Software reset for the ${gw} ${g.name} tiles (Active High, one bit per tile, 1 = held in reset)";
        field { hw = r; sw = rw; } ${g.name.lower()}_rst[${gw - 1}:0] = ${por_rst(gw)};
    } ${g.name.lower()}_rst;
        % endfor
    % endif
};

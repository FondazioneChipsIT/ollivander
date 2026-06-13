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

addrmap ${config.project.name}_sys_regs {
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
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('isolate')]):
        field {
            name = "${c['name']}_isolate";
            desc = "Isolate ${c['name']}";
            hw = r; sw = rw;
        } ${c['name']}_isolate[${i}:${i}] = 1;
        % endfor
    } isolate_ctrl;

    reg {
        name = "Isolation Status";
        desc = "Acknowledgment from the hardware that AXI isolation is complete and safe";
        default sw = r; default hw = w;
        % for i, c in enumerate([c for c in components if c.get('system_config') and c.get('system_config').get('isolate')]):
        field {
            name = "${c['name']}_isolated";
            desc = "${c['name']} isolated status";
        } ${c['name']}_isolated[${i}:${i}] = 0;
        % endfor
    } isolate_status;
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
        desc = "Clock enable for ${dom['name']}";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_clk_en[31:0] = 32'hFFFFFFFF;
    } ${fmt_reg(dom['name'])}_clk_en;
                % endif

    reg {
        name = "${dom['name']} Software Reset";
        desc = "Software reset for ${dom['name']} (Active Low)";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_rst[31:0] = 32'hFFFFFFFF;
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
        desc = "Debug clock enable for ${dom['name']}";
        field { hw = r; sw = rw; } ${fmt_reg(dom['name'])}_debug_clk_en[31:0] = 32'hFFFFFFFF;
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
        desc = "Clock enable for ${c['dedicated_clock_div']['name']}";
        field { hw = r; sw = rw; } ${fmt_reg(c['dedicated_clock_div']['name'])}_clk_en[31:0] = 32'hFFFFFFFF;
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
    % if sys_ctrl.get('auto_control_groups'):
        % for g in sys_ctrl.get('auto_control_groups'):
    reg {
        name = "${g['name']} Clock Enable";
        desc = "Clock enable for ${g['name']} tiles";
        field { hw = r; sw = rw; } ${g['name'].lower()}_clk_en[31:0] = 32'hFFFFFFFF;
    } ${g['name'].lower()}_clk_en;

    reg {
        name = "${g['name']} Reset";
        desc = "Software reset for ${g['name']} tiles (Active High)";
        field { hw = r; sw = rw; } ${g['name'].lower()}_rst[31:0] = 0;
    } ${g['name'].lower()}_rst;
        % endfor
    % endif
};
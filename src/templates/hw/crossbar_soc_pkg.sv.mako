<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE SOC GLOBAL PACKAGE
  # ============================================================================
  # This template generates the main SystemVerilog package for the SoC.
  # It acts as the Single Source of Truth (SSoT) for address maps and routing.
  p_name = config.project.name
  pkg = "ollivander_soc_pkg"
  
  aw = config.topology.global_bus.addr_width
  # Formatting helpers
  def fmt_name(name): return name.replace('_clk', '').replace('_rst', '').lower()
  def camel_case(name): return ''.join(word.title() for word in name.split('_'))
  def parse_hex(val):
      if isinstance(val, int): return f"{val:X}"
      return str(val).replace('0x', '').replace('_', '').upper()

  # ============================================================================
  # 1. CLOCK DOMAINS EXTRACTION
  # ============================================================================
  # We only need indices for gateable (non-real-time) domains to generate the
  # reset arrays. The host clock is excluded as it is the root domain.
  gateable_domains = [d for d in config.clock_tree.domains if not d.is_real_time and d.name != 'host_clk']
  
  # ============================================================================
  # 2. AXI SLAVES (CROSSBAR TARGETS) EXTRACTION
  # ============================================================================
  # Scans all components for AXI slave interfaces. It unrolls multiple ports of 
  # the same component (e.g., a dual-port L2 Memory) into discrete routing targets 
  # for the central crossbar, categorizing them by synchronous/asynchronous domains.
  comp_info_dict = context.get('comp_info', {}) or {}
  axi_slaves_async = []
  axi_slaves_sync = []
  for c in config.components:
      if c.interfaces and 'axi_slave' in c.interfaces:
          for slv in c.interfaces['axi_slave']:
              is_sync = slv.get('sync_domain', False)
              c_info = comp_info_dict.get(c.name, {})
              if c_info and "ports" in c_info:
                  if not is_sync and "async_axi_in_aw_data_i" not in c_info["ports"]:
                      is_sync = True
              ports = slv.get('ports', 1)
              raw_base = slv['base_addr']
              base_int = int(raw_base, 16) if isinstance(raw_base, str) and raw_base.startswith('0x') else int(raw_base)
              raw_size = slv.get('size', slv.get('size_per_instance', '0x1000'))
              size_int = int(raw_size, 16) if isinstance(raw_size, str) and raw_size.startswith('0x') else int(raw_size)
              
              port_size = size_int // ports
              for p in range(ports):
                  name_suffix = f"_{p}" if ports > 1 else ""
                  port_base = base_int + p * port_size
                  obj = {
                      'name': f"{c.name}{name_suffix}",
                      'base': f"0x{port_base:08X}",
                      'size': f"0x{port_size:08X}"
                  }
                  if is_sync: axi_slaves_sync.append(obj)
                  else: axi_slaves_async.append(obj)
                  
  if config.project.build_mode == "macro" and config.project.macro_settings and config.project.macro_settings.masters:
      addr_width = getattr(config.topology.global_bus, 'addr_width', 48)
      for idx, mst in enumerate(config.project.macro_settings.masters):
          dummy_base = (1 << addr_width) - 0x100000 - (idx * 0x1000)
          axi_slaves_sync.append({
              'name': f'macro_export_{idx}',
              'base': f'0x{dummy_base:X}',
              'size': '0x1000'
          })

  axi_slaves = axi_slaves_async + axi_slaves_sync
                  
  # ============================================================================
  # 3. AXI MASTERS (CROSSBAR INITIATORS) EXTRACTION
  # ============================================================================
  axi_masters_async = []
  axi_masters_sync = []
  for c in config.components:
      if c.interfaces and c.interfaces.get('axi_master'):
          is_sync_mst = True
          c_info = comp_info_dict.get(c.name, {})
          if c_info and "ports" in c_info:
              if "async_axi_out_aw_data_o" in c_info["ports"]:
                  is_sync_mst = False
          if is_sync_mst:
              axi_masters_sync.append(c.name)
          else:
              axi_masters_async.append(c.name)
  axi_masters = axi_masters_async + axi_masters_sync
          
  # ============================================================================
  # 4. REGBUS SLAVES (PERIPHERAL TARGETS) EXTRACTION
  # ============================================================================
  # Scans for low-speed peripheral slaves on the RegBus. It separates synchronous
  # from asynchronous targets to route them to the correct conversion pipelines 
  # in the top-level.
  reg_sync = []
  reg_async = []
  # The central System Controller is always a synchronous RegBus slave
  reg_sync.append({
      'name': config.system_controller.name,
      'base': config.system_controller.base_addr,
      'size': config.system_controller.size if config.system_controller.size else '0x1000'
  })
  for c in config.components:
      if c.interfaces and 'regbus_slave' in c.interfaces:
          for slv in c.interfaces['regbus_slave']:
              is_sync = slv.get('sync_domain', False)
              obj = {
                  'name': c.name,
                  'base': slv['base_addr'],
                  'size': slv.get('size', '0x1000')
              }
              if is_sync: reg_sync.append(obj)
              else: reg_async.append(obj)
  all_reg_slaves = reg_sync + reg_async
%><%namespace file="/license_header.mako" import="license"/>\
${license()}//
// AUTOMATICALLY GENERATED BY OLLIVANDER - DO NOT EDIT DIRECTLY
//
// SoC Global SystemVerilog Package for ${p_name.upper()}
// Contains Memory Maps, Routing Indices, and architectural constants.

// BENDER: name="axi"
// BENDER: name="register_interface"

`include "axi/typedef.svh"
`include "register_interface/typedef.svh"

package ${pkg};

  // =========================================================================
  // 1. GLOBAL ARCHITECTURE PARAMETERS
  // =========================================================================
  // Extracted from the YAML `global_bus` section. Used to dimension the 
  // central AXI crossbars and generate the standard struct macros.
  localparam int unsigned AxiAddrWidth     = ${config.topology.global_bus.addr_width};
  localparam int unsigned AxiDataWidth     = ${config.topology.global_bus.data_width};
  localparam int unsigned AxiUserWidth     = ${config.topology.global_bus.user_width};
  localparam int unsigned AxiIdWidth       = ${config.topology.global_bus.mst_id_width};
  
<%
  # Calculate host's internal AXI masters to adjust ExtSlvIdWidth
  host_params = config.host.parameters or {}
  num_cores = host_params.get('NumCores', 1)
  has_dbg = 1 # Always present
  has_dma = 1 if host_params.get('Dma', True) else 0
  has_slink = 1 if host_params.get('SerialLink', True) else 0
  has_vga = 1 if host_params.get('Vga', True) else 0
  has_usb = 1 if host_params.get('Usb', True) else 0
  num_internal_masters = num_cores + has_dbg + has_dma + has_slink + has_vga + has_usb
  total_masters = len(axi_masters) + num_internal_masters
%>
  localparam int unsigned ExtSlvIdWidth    = AxiIdWidth + $clog2(${total_masters} > 1 ? ${total_masters} : 2);
  localparam int unsigned LlcIdWidth       = ExtSlvIdWidth + 1; // Margin for LLC bypass bit


  localparam int unsigned AxiUserAmoMsb    = ${config.system_settings.user_mapping.amo_msb};
  localparam int unsigned AxiUserAmoLsb    = ${config.system_settings.user_mapping.amo_lsb};
  localparam int unsigned AxiUserEccErrBit = ${config.system_settings.user_mapping.ecc_err_bit};

  // =========================================================================
  // 1a. GLOBAL BUS TYPES
  // =========================================================================
  // Defines the SystemVerilog structs and channels for the AXI and RegBus
  // interconnects. These types are used globally across all component wrappers.
  localparam int unsigned LogDepth   = 3;
  localparam int unsigned LlcAwWidth = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, LlcIdWidth, AxiUserWidth);
  localparam int unsigned LlcWWidth  = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth);
  localparam int unsigned LlcBWidth  = (2**LogDepth)*axi_pkg::b_width(LlcIdWidth, AxiUserWidth);
  localparam int unsigned LlcArWidth = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, LlcIdWidth, AxiUserWidth);
  localparam int unsigned LlcRWidth  = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, LlcIdWidth, AxiUserWidth);

  typedef logic [AxiAddrWidth-1:0] soc_reg_addr_t;
  typedef logic [31:0] soc_reg_data_t;
  typedef logic [ 3:0] soc_reg_strb_t;
  `REG_BUS_TYPEDEF_ALL(soc_reg, soc_reg_addr_t, soc_reg_data_t, soc_reg_strb_t)

  typedef logic [AxiAddrWidth-1:0]   soc_axi_addr_t;
  typedef logic [AxiDataWidth-1:0]   soc_axi_data_t;
  typedef logic [AxiDataWidth/8-1:0] soc_axi_strb_t;
  typedef logic [AxiUserWidth-1:0]   soc_axi_user_t;
  typedef logic [AxiIdWidth-1:0]     soc_axi_mst_id_t;
  typedef logic [ExtSlvIdWidth-1:0]  soc_axi_slv_id_t;
  typedef logic [LlcIdWidth-1:0]     soc_axi_llc_id_t;

  `AXI_TYPEDEF_ALL(soc_axi, soc_axi_addr_t, soc_axi_mst_id_t, soc_axi_data_t, soc_axi_strb_t, soc_axi_user_t)
  `AXI_TYPEDEF_ALL(soc_axi_slv, soc_axi_addr_t, soc_axi_slv_id_t, soc_axi_data_t, soc_axi_strb_t, soc_axi_user_t)
  `AXI_TYPEDEF_ALL(soc_axi_llc, soc_axi_addr_t, soc_axi_llc_id_t, soc_axi_data_t, soc_axi_strb_t, soc_axi_user_t)

  // =========================================================================
  // 1b. SYSTEM MICROARCHITECTURE PARAMETERS
  // =========================================================================
  // Deep microarchitectural sizing for transaction tracking FIFOs and RISC-V 
  // Atomic Memory Operations (AMOs) adapters within the crossbar.
  localparam int unsigned LlcMaxReadTxns  = ${config.system_settings.llc.max_read_txns};
  localparam int unsigned LlcMaxWriteTxns = ${config.system_settings.llc.max_write_txns};
  localparam int unsigned LlcAmoNumCuts   = ${config.system_settings.llc.amo_num_cuts};
  localparam bit          LlcAmoPostCut   = ${'1' if config.system_settings.llc.amo_post_cut else '0'};

  localparam int unsigned RegMaxReadTxns  = ${config.system_settings.reg_bus.max_read_txns};
  localparam int unsigned RegMaxWriteTxns = ${config.system_settings.reg_bus.max_write_txns};
  localparam int unsigned RegAmoNumCuts   = ${config.system_settings.reg_bus.amo_num_cuts};
  localparam bit          RegAmoPostCut   = ${'1' if config.system_settings.reg_bus.amo_post_cut else '0'};

  // =========================================================================
  // 2. CLOCK & RESET DOMAINS
  // =========================================================================
  // Enums used as array indices to map components to their respective reset wires.
  localparam int unsigned NumClkGen  = ${config.clock_tree.generators};
  localparam int unsigned NumDomains = ${len(gateable_domains)};
  
  typedef enum int {
% for dom in gateable_domains:
    DomainIdx_${fmt_name(dom.name)} = ${loop.index}${"," if not loop.last else ""}
% endfor
  } domain_idx_e;

  // =========================================================================
  // 3. AXI CROSSBAR (SYSTEM MEMORY MAP)
  // =========================================================================
  // Master and Slave enumeration indices. These are crucial to correctly wire 
  // components to specific ports of the central multidimensional AXI crossbar.
  localparam int unsigned NumAxiMastersAsync = ${len(axi_masters_async)};
  localparam int unsigned NumAxiMastersSync  = ${config.host.parameters.get('AxiNumMstSync', len(axi_masters_sync))};
  localparam int unsigned NumAxiMasters      = NumAxiMastersAsync + NumAxiMastersSync;
  typedef enum int {
% for mst in axi_masters:
    AxiMstIdx_${camel_case(mst)} = ${loop.index}${"," if not loop.last else ""}
% endfor
  } axi_mst_idx_e;

  localparam int unsigned NumAxiSlavesAsync = ${len(axi_slaves_async)};
  localparam int unsigned NumAxiSlavesSync  = ${config.host.parameters.get('AxiNumSlvSync', len(axi_slaves_sync))};
  localparam int unsigned NumAxiSlaves      = NumAxiSlavesAsync + NumAxiSlavesSync;
  typedef enum int {
% for slv in axi_slaves:
    AxiSlvIdx_${camel_case(slv['name'])} = ${loop.index}${"," if not loop.last else ""}
% endfor
  } axi_slv_idx_e;

  // AXI Memory Map Arrays (Reversed for correct SystemVerilog packed array syntax)
  // These arrays are read by the Host's internal crossbar to decode incoming 
  // addresses and route transactions to the correct AXI slave port.
  localparam int unsigned AxiExtNumRules = NumAxiSlaves;

  localparam logic [NumAxiSlaves-1:0][7:0] AxiExtRegionIdx = {
% for i in reversed(range(len(axi_slaves))):
    8'd${i}${"," if i != 0 else ""}
% endfor
  };

  localparam logic [NumAxiSlaves-1:0][63:0] AxiExtRegionStart = {
% for slv in axi_slaves[::-1]:
    64'h${parse_hex(slv['base'])}${"," if not loop.last else ""}
% endfor
  };

  localparam logic [NumAxiSlaves-1:0][63:0] AxiExtRegionEnd = {
% for slv in axi_slaves[::-1]:
    64'h${parse_hex(slv['base'])} + 64'h${parse_hex(slv['size'])}${"," if not loop.last else ""}
% endfor
  };

  // =========================================================================
  // 4. REGBUS SUBSYSTEM (SYSTEM REGISTERS MAP)
  // =========================================================================
  // Routing map for the secondary low-speed Register Bus.
  localparam int unsigned NumSyncRegSlaves  = ${len(reg_sync)};
  localparam int unsigned NumAsyncRegSlaves = ${len(reg_async)};
  localparam int unsigned NumTotalRegSlaves = NumSyncRegSlaves + NumAsyncRegSlaves;

  typedef enum int {
% for slv in all_reg_slaves:
    RegBusSlvIdx_${camel_case(slv['name'])} = ${loop.index}${"," if not loop.last else ""}
% endfor
  } regbus_slv_idx_e;

  localparam int unsigned RegExtNumRules = NumTotalRegSlaves;

  localparam logic [NumTotalRegSlaves-1:0][7:0] RegExtRegionIdx = {
% for i in reversed(range(len(all_reg_slaves))):
    8'd${i}${"," if i != 0 else ""}
% endfor
  };

  localparam logic [NumTotalRegSlaves-1:0][63:0] RegExtRegionStart = {
% for slv in all_reg_slaves[::-1]:
    64'h${parse_hex(slv['base'])}${"," if not loop.last else ""}
% endfor
  };

  localparam logic [NumTotalRegSlaves-1:0][63:0] RegExtRegionEnd = {
% for slv in all_reg_slaves[::-1]:
    64'h${parse_hex(slv['base'])} + 64'h${parse_hex(slv['size'])}${"," if not loop.last else ""}
% endfor
  };

  // =========================================================================
  // 5. DEBUG AND STATUS SIGNALS
  // =========================================================================
  typedef struct packed {
    logic                  rt_clk;
    logic                  host_clk;
    logic [NumDomains-1:0] domain_clk;
    logic [NumDomains-1:0] domain_rsts_n;
    logic                  host_pwr_on_rst_n;
  } ${p_name}_debug_sigs_t;

endpackage : ${pkg}
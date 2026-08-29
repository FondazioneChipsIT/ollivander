# ==============================================================================
# OLLIVANDER UNIFIED SoC ARCHITECTURE - PYTHON CONFIGURATION
# ==============================================================================
# This is a pure Python native configuration file for the Super Crux SoC.
# It leverages Pydantic models from soc_schema.py to provide type-hinting,
# autocompletion, and programmatic generation of the crossbar and nested macros.
# ==============================================================================

from core.soc_schema import (
    OllivanderConfig, Project, Topology, GlobalBus,
    SystemSettings, UserMapping, LlcMicroarch, RegBusMicroarch,
    ClockTree, ClockDomain, SystemController, PadframeConfig, PadDomainConfig,
    Component
)

# ------------------------------------------------------------------------------
# 1. CONSTANTS & ADDRESS MAP
# ------------------------------------------------------------------------------
# Using Python allows us to define the memory map using variables.
# We place the nested mesh macro safely beyond the 0x87FFFFFF hyperbus boundary.
BASE_MESH_MACRO = 0x90000000

# ------------------------------------------------------------------------------
# 2. CONFIGURATION OBJECT EXPORT
# ------------------------------------------------------------------------------
config = OllivanderConfig(
    project=Project(
        name="super_crux",
        description="Super Crux Heterogeneous Multi-Core SoC Specification with Nested Mesh Macro",
        author="Ollivander Generator",
        vendor="Chips-IT",     # IP-XACT component vendor metadata
        library="SoC",         # IP-XACT component library name metadata
        version="1.0.0",       # IP-XACT component version metadata
        build_mode="standalone"
    ),
    
    # --------------------------------------------------------------------------
    # TOPOLOGY & INTERCONNECT
    # --------------------------------------------------------------------------
    # We define a "crossbar" topology, mapping the components to a central AXI4 
    # global interconnect.
    topology=Topology(
        type="crossbar",
        global_bus=GlobalBus(
            protocol="AXI4",
            data_width=64,
            addr_width=48,
            user_width=10,
            mst_id_width=2
        )
    ),
    
    # --------------------------------------------------------------------------
    # SYSTEM MICROARCHITECTURE SETTINGS
    # --------------------------------------------------------------------------
    system_settings=SystemSettings(
        user_mapping=UserMapping(amo_msb=2, amo_lsb=0, ecc_err_bit=4),
        llc=LlcMicroarch(max_read_txns=32, max_write_txns=32, amo_num_cuts=1),
        reg_bus=RegBusMicroarch(max_read_txns=8, max_write_txns=8, amo_num_cuts=1, amo_post_cut=True)
    ),
    
    # --------------------------------------------------------------------------
    # CLOCK & RESET TREE
    # --------------------------------------------------------------------------
    clock_tree=ClockTree(
        generators=4,
        generator_periods_ns=[10.0, 10.0, 10.0, 10.0],
        domains=[
            ClockDomain(name="rt", description="Real-Time Clock for CLINT and AON timers", is_real_time=True, source_gen=0, static_div=100, has_mux=False, has_divider=False),
            ClockDomain(name="host", description="Main Host Clock for Cheshire CPU", has_divider=False, has_debug_divider=True, source_gen=1, has_mux=False),
            ClockDomain(name="periph", description="Clock domain for slow/medium speed peripherals", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1),
            ClockDomain(name="safety", description="Clock domain for the Safety Island", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1),
            ClockDomain(name="secure", description="Clock domain for the Security Island", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1),
            ClockDomain(name="pulp", description="Clock domain for the PULP Integer Cluster", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1),
            ClockDomain(name="spatz", description="Clock domain for the Spatz Vectorial Cluster", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1),
            ClockDomain(name="l2", description="Clock domain for the L2 Shared Memory", has_divider=True, has_mux=True, has_debug_divider=True, default_div=1)
        ]
    ),
    
    # --------------------------------------------------------------------------
    # GLOBAL SYSTEM CONTROLLER & REGISTERS
    # --------------------------------------------------------------------------
    system_controller=SystemController(
        name="sys_ctrl",
        description="Main system control and status registers (PCRs)",
        base_addr=0x20010000,
        size=0x1000,
        scratch_registers=2,
        version_registers=5,
        jedec_id=0x00000000,
        clk_gen_status_regs=True
    ),
    
    # --------------------------------------------------------------------------
    # PADFRAME & PINMUX
    # --------------------------------------------------------------------------
    padframe=PadframeConfig(
        name="super_crux_padframe",
        description="Global ASIC Padframe and Pinmux",
        base_addr=0x200A0000,
        sync_domain=False,
        pad_py="super_crux_pads.py",
        # The CAN event is deliberately unpadded (parity with astral): it reaches the PLIC,
        # and the SoC-level port survives because the exported can_bus interface carries it.
        unpadded_ports={"apb_subsystem_can_bus_event_o": "open"},
        domains=[
            PadDomainConfig(name="domain_1v8", tech="behavioral"),
            PadDomainConfig(name="domain_3v3", tech="behavioral")
        ]
    ),
    
    # --------------------------------------------------------------------------
    # HOST SYSTEM (Manager)
    # --------------------------------------------------------------------------
    host=Component(
        name="manager",
        description="Main application processor (Cheshire host)",
        type="cheshire_isle",
        clock_domain="host",
        # CVA6 implements fence.i (the offload app relies on it to publish the payload);
        # modern binutils want the extension spelled out in the -march string.
        isa="rv64imafdc_zifencei",
        abi="lp64d",
        cmodel="medany",
        # 'slink' joins the exports for the serial-link preload (wip ch. 2):
        # the image will stream through it while bring-up and handoff stay
        # on the proven JTAG path.
        export_interfaces=["jtag", "uart", "spi", "i2c", "gpio", "slink"],
        interfaces={
            "axi_master": True,
            "axi_slave": [
                {"name": "internal_subsystem", "base_addr": 0x00000000, "size": 0x20000000}
            ]
        },
        parameters={
            "NumCores": 1, "RtcFreq": 1000000, "Bootrom": True, "Uart": True,
            "I2c": True, "SpiHost": True, "Dma": True, "SerialLink": True,
            "Vga": False, "Snooper": True, "IrqRouter": True,
            "Cva6ExtCieOnTop": True,
            "Cva6ExtCieLength": 0x08000000
        },
        interrupts={
            "intr_ext_i": {
                "cdc": False,
                "source": "{\n"
                          "  [22] : ethernet.eth_rx_irq_o,\n"
                          "  [21] : apb_subsystem.system_timer_irq_hi_o,\n"
                          "  [20] : apb_subsystem.system_timer_irq_lo_o,\n"
                          "  [19:16] : apb_subsystem.advanced_timer_events_o,\n"
                          "  [15:12] : apb_subsystem.advanced_timer_channels_o,\n"
                          "  [11] : apb_subsystem.can_bus_event_o,\n"
                          "  [10] : apb_subsystem.watchdog_aon_timer_rst_req_o,\n"
                          "  [9] : apb_subsystem.watchdog_wkup_req_o,\n"
                          "  [8] : apb_subsystem.watchdog_nmi_wdog_timer_bark_o,\n"
                          "  [7] : apb_subsystem.watchdog_intr_wdog_timer_bark_o,\n"
                          "  [6] : apb_subsystem.watchdog_intr_wkup_timer_expired_o,\n"
                          "  [5] : l2_shared_memory.ecc_error_o,\n"
                          "  [4] : mailbox.snd_irq_o[11],\n"
                          "  [3] : mailbox.snd_irq_o[15],\n"
                          "  [2] : mailbox.snd_irq_o[7],\n"
                          "  [1] : mailbox.snd_irq_o[9],\n"
                          "  [0] : pulp_cluster.eoc_o\n"
                          "}"
            }
        }
    ),
    
    # --------------------------------------------------------------------------
    # SYSTEM COMPONENTS (Compute, Memories, Peripherals)
    # --------------------------------------------------------------------------
    components=[
        Component(
            name="hyperbus",
            description="High-speed external memory interface (DRAM/Flash)",
            type="hyperbus_isle",
            clock_domain="periph",
            export_interfaces=["hyperbus"],
            interfaces={
                "llc_port": [{"base_addr": 0x80000000, "size": 0x08000000}],
                "regbus_slave": [{"base_addr": 0x20009000, "size": 0x00001000, "sync_domain": False}]
            }
        ),
        
        Component(
            name="l2_shared_memory",
            description="Level 2 shared SRAM with ECC",
            type="l2_isle",
            clock_domain="l2",
            system_config={"is_l2_mem": True},
            interfaces={
                # Inside the host's CIE window [0x7800_0000, 0x8000_0000), astral's
                # own L2 base (see crux.yml for the shadowing rationale).
                "axi_slave": [{"ports": 2, "base_addr": 0x78000000, "size": 0x00200000, "sync_domain": False}],
                "regbus_slave": [{"base_addr": 0x2000B000, "size": 0x00001000, "sync_domain": False}]
            }
        ),
        
        Component(
            name="safety_island",
            description="Triple-Core-Lockstep RV32 system for ASIL compliant tasks",
            type="safety_island_isle",
            clock_domain="safety",
            export_interfaces=["jtag"],
            interfaces={
                "axi_master": True,
                "axi_slave": [{"base_addr": 0x60000000, "size": 0x00800000, "sync_domain": False}]
            },
            system_config={
                "isolate": True, "fetch_enable": True, "boot_addr": 0x70000000
            },
            interrupts={
                "irqs_i": {
                    "cdc": False,
                    "source": "{\n"
                              "  [55:29] : manager.intr_ext_o[55:29],\n"
                              "  [28:4]  : manager.intr_ext_o[24:0],\n"
                              "  [3] : mailbox.snd_irq_o[8],\n"
                              "  [2] : mailbox.snd_irq_o[10],\n"
                              "  [1] : mailbox.snd_irq_o[12],\n"
                              "  [0] : mailbox.snd_irq_o[6]\n"
                              "}"
                }
            }
        ),
        
        Component(
            name="security_island",
            description="Hardware Root-of-Trust (OpenTitan/Ibex)",
            type="security_island_isle",
            clock_domain="secure",
            export_interfaces=["jtag", "uart", "spi"],
            interfaces={
                "axi_master": True
            },
            system_config={
                "isolate": True, "fetch_enable": True, "boot_addr": 0x70000000
            },
            interrupts={
                "irq_ibex_i": {"source": "mailbox.snd_irq_o[5] | mailbox.snd_irq_o[14]", "cdc": False},
                "cfi_req_irq_i": {"source": "manager.intr_ext_o[23]"},
                "cfi_watermark_irq_i": {"source": "manager.intr_ext_o[22]"}
            }
        ),
        
        Component(
            name="pulp_cluster",
            description="Multicore array for integer math acceleration",
            type="pulp_cluster_isle",
            clock_domain="pulp",
            interfaces={
                "axi_master": True,
                "axi_slave": [{"base_addr": 0x50000000, "size": 0x00800000, "sync_domain": False}]
            },
            system_config={
                "isolate": True, "fetch_enable": True, "boot_enable": True, "boot_addr": 0x70000000,
                "has_busy_status": True, "has_eoc_status": True
            },
            interrupts={
                "mbox_irq_i": {"source": "mailbox.snd_irq_o[4]", "cdc": False},
                "dbg_irq_valid_i": {"source": "safety_island.debug_req_o[39:32]", "cdc": False}
            }
        ),
        
        Component(
            name="spatz_cluster",
            description="Vectorial / Floating-point accelerator",
            type="spatz_cluster_isle",
            clock_domain="spatz",
            interfaces={
                "axi_master": True,
                "axi_slave": [{"base_addr": 0x51000000, "size": 0x00800000, "sync_domain": False}]
            },
            system_config={
                "isolate": True, "fetch_enable": False, "boot_addr": 0x70000000,
                "has_busy_status": True, "debug_req": True
            },
            interrupts={
                "msip_i": {
                    "cdc": False,
                    "source": "{\n"
                              "  [1] : mailbox.snd_irq_o[3] | mailbox.snd_irq_o[1],\n"
                              "  [0] : mailbox.snd_irq_o[2] | mailbox.snd_irq_o[0]\n"
                              "}"
                },
                # Deliberately tied off (was {8{manager.mtip_ext_o}}): the snitch cores
                # park in their bootrom on WFI, whose wake logic samples the RAW pending
                # lines - the host CLINT's mtip is X while Cheshire is still booting and
                # permanently 1 afterwards (mtimecmp resets to 0), which breaks the
                # parking either way. The offload model wakes the cluster exclusively
                # through its internal CLINT (same rationale as crux).
                "mtip_i": {"source": "none"},
                "meip_i": {"source": "none"}
            }
        ),
        
        Component(
            name="mailbox",
            description="Centralized Mailbox for cross-domain Machine Software Interrupts (MSI)",
            type="mailbox_isle",
            clock_domain="host",
            interfaces={
                "axi_slave": [{"base_addr": 0x40000000, "size": 0x00001000, "sync_domain": True}]
            },
            parameters={
                "NumMailboxes": 16
            }
        ),
        
        Component(
            name="pll_config",
            description="PLL configuration registers",
            type="pll_cfg",
            interfaces={
                "regbus_slave": [{"external": True, "base_addr": 0x20020000, "size": 0x00001000, "sync_domain": False}]
            }
        ),
        
        Component(
            name="ethernet",
            description="Gigabit Ethernet MAC with built-in DMA",
            type="ethernet_isle",
            clock_domain="periph",
            export_interfaces=["phy", "eth_clk200"],
            interfaces={
                "axi_master": True,
                "regbus_slave": [{"base_addr": 0x20000000, "size": 0x00001000, "sync_domain": False}]
            },
            dedicated_clock_div={
                "name": "eth", "default_div": 10
            }
        ),
        
        Component(
            name="apb_subsystem",
            description="Subsystem for low-speed automotive/industrial peripherals",
            type="apb_subsystem_isle",
            clock_domain="periph",
            export_interfaces=["can_bus"],
            interfaces={
                "axi_slave": [{"base_addr": 0x20001000, "size": 0x00009000, "sync_domain": False}]
            },
            parameters={
                "ApbDataWidth": 32, "ApbAddrWidth": 32
            },
            components=[
                Component(
                    name="system_timer",
                    description="General purpose system timer",
                    type="apb_timer_unit",
                    base_addr=0x20004000,
                    size=0x00001000
                ),
                Component(
                    name="advanced_timer",
                    description="Advanced timer with PWM and event capabilities",
                    type="apb_adv_timer",
                    base_addr=0x20005000,
                    size=0x00001000
                ),
                Component(
                    name="watchdog",
                    description="Always-On (AON) watchdog timer",
                    type="aon_timer",
                    base_addr=0x20007000,
                    size=0x00001000
                ),
                Component(
                    name="can_bus",
                    description="Controller Area Network (CAN) bus interface",
                    type="can_top_apb",
                    base_addr=0x20001000,
                    size=0x00001000
                )
            ]
        ),
        
        # --- THE NESTED MESH ISLE MACRO ---
        # Instantiates the standalone Mesh macro (exported by the noc_isle example) inside
        # this crossbar parent. Deliberately cross-topology: together with super_mesh, which
        # nests the Crux macro, the two super examples exercise the external IPs of BOTH
        # families in a single Bender resolution.
        Component(
            name="mesh_subsystem",
            description="Nested Mesh Subsystem Macro",
            type="mesh_isle",
            clock_domain="host",
            interfaces={
                "axi_master": True,
                "axi_slave": [{"name": "mesh_isle_mem_map", "base_addr": BASE_MESH_MACRO, "size": 0x88000000, "sync_domain": False}]
            }
        )
    ],
    
    testbench={
        # Boot through the VIP's JTAG agent instead of hierarchical forces (wip 2.1).
        "boot_mode": "jtag",
        # Image and boot handoff over the exported serial link (wip 2.1):
        # the l2_shared_memory preload needs no hierarchical path, and the scratch
        # writes avoid the SBA-to-internal-regs anomaly cheshire shows with
        # SerialLink enabled (see the upstream registry). On the crossbar family
        # the id widths follow the host by construction (standardization 5.3).
        "preload_mode": "slink",
        # Only the boot-critical domains are enabled by the testbench; the firmware
        # ungates each target when it needs it and powers it down afterwards.
        "bring_up": "minimal",
        "boot_force_delay_ns": 5000000,
        "boot_force_fast_delay_ns": 1000000,
        "boot_timeout_ns": 10000000,
        "boot_timeout_fast_ns": 2000000,
        "sim_timeout_ns": 10000000,
        "preload_memories": [
            {"instance": "i_l2_shared_memory", "file": "generated/sw/{test_app}.hex"}
        ]
    },
    
    # --------------------------------------------------------------------------
    # SOFTWARE STACK & FIRMWARE
    # --------------------------------------------------------------------------

    # Simulator flags & options (power-user section, guide ch. 6). Phase 2 of the
    # Verilator build is pure g++ (the -j48 emission-truncation hazard cannot reach
    # it), and this project's twenty child libraries share the default 32 slots -
    # spatz and pulp alone spend ~6 min of already-parallel compilation (wip 5.2.2).
    simulation={
        "verilator": {"compile_jobs": 64},
        # compile_jobs 64: measured -26/-27% on both supers' cold builds (the
        # -j48 emission-truncation hazard cannot reach phase 2, which is pure
        # g++). threads stays at the default 4: 8 was tried and reverted -
        # it segfaults super_crux's top at time zero (isolated to
        # the thread count alone, jobs exonerated) and bought nothing on
        # super_mesh (22m20 vs 21m44); see wip 5.2.
    },
    software_stack={
        "toolchain": "riscv64-unknown-elf-",
        "boot_memory": "l2_shared_memory",
        # The offload app is a strict superset of hello_world: same greeting first, then
        # payload offload onto every component declaring an Offload* contract (here:
        # pulp_cluster via control_wire and spatz_cluster via memory_mapped, as on crux).
        "test_app": {"name": "offload", "auto_generate_c": True,
                     # Simulation-fast UART (divisor 3, ~2.08 Mbaud effective): at 115200
                     # the UART dominates the run. The generator keeps firmware and
                     # testbench monitor on the same divisor; drop the key to return to
                     # 115200 for a physical terminal.
                     "baudrate": 2000000}
    }
)

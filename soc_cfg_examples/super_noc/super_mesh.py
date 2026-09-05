# ==============================================================================
# OLLIVANDER UNIFIED SoC ARCHITECTURE - PYTHON CONFIGURATION
# ==============================================================================
# This is a pure Python native configuration file for the Super Mesh SoC.
# It leverages Pydantic models from soc_schema.py to provide type-hinting,
# autocompletion, and programmatic generation of the NoC grid.
# ==============================================================================

from core.soc_schema import (
    OllivanderConfig, Project, Topology, NoCSettings, NoCNetwork,
    NoCCollectives, NoCReductionChannel,
    SystemSettings, UserMapping, LlcMicroarch, RegBusMicroarch,
    ClockTree, ClockDomain, SystemController, AutoControlGroup,
    ExternalRegister, Component
)

# ------------------------------------------------------------------------------
# 1. CONSTANTS & ADDRESS MAP
# Using Python allows us to define the memory map using variables, formulas, 
# and base addresses. This completely eliminates hardcoded magic numbers 
# and makes address space modifications extremely safe and trivial!
# ------------------------------------------------------------------------------
BASE_CRUX_MACRO = 0x20000000
BASE_CLUSTERS   = 0xB0000000   # Moved beyond Crux's 0xA8000000 footprint
BASE_SPM_NARROW = 0xC0000000
BASE_SPM_WIDE   = 0xC0100000
BASE_L2         = 0xD0000000
BASE_MESH_MACRO = 0x100000000  # Start at 4GB (Safe in 48-bit AXI)
BASE_DRAM       = 0x800000000  # Start at 32GB

# ------------------------------------------------------------------------------
# 2. CONFIGURATION OBJECT EXPORT
# This 'config' variable is exactly what Ollivander's engine looks for when 
# parsing this script. We construct it using the strongly-typed Pydantic classes 
# imported above, which gives us IDE autocompletion and early validation.
# ------------------------------------------------------------------------------
config = OllivanderConfig(
    # --- PROJECT METADATA ---
    # Defines the global SoC name and how it will be built.
    # 'standalone' means Ollivander will generate a complete, bootable top-level.
    project=Project(
        name="super_mesh",
        description="Massive platform integrating the Mesh and Crux Macros",
        author="Ollivander Generator",
        build_mode="standalone",
        vendor="Chips-IT",     # IP-XACT component vendor metadata
        library="SoC",         # IP-XACT component library name metadata
        version="1.0.0",       # IP-XACT component version metadata
    ),
    
    # --- TOPOLOGY & INTERCONNECT ---
    # We define a Network-on-Chip (NoC) architecture using FlooNoC.
    topology=Topology(
        type="noc",
        noc_settings=NoCSettings(
            type="floo_noc",
            routing_algorithm="XY",
            networks={
                # FlooNoC supports multiple parallel physical networks to segregate traffic:
                # - "narrow" (64-bit) for register accesses and lightweight traffic.
                # - "wide" (512-bit) for heavy DMA and cache-line transfers.
                "narrow": NoCNetwork(data_width=64, addr_width=48),
                "wide": NoCNetwork(data_width=512, addr_width=48)
            },
            default_tile="dummy_tile",
            # Same declaration as the YAML family (see mesh.yml for the full rationale):
            # the schema defaults both reduction channels off, and the wide one is
            # declared explicitly with the RTL's own RedDefaultCfg values.
            collectives=NoCCollectives(
                wide_reduction=NoCReductionChannel(enable=True, rd_pipeline_depth=5, cut_offload_intf=True),
            )
        )
    ),
    
    # --- SYSTEM MICROARCHITECTURE SETTINGS ---
    # Defines global parameters to ensure system-wide coherence, such as AXI 'user' 
    # bit mapping and FIFO sizing for Atomics (AMOs).
    system_settings=SystemSettings(
        user_mapping=UserMapping(amo_msb=2, amo_lsb=0, ecc_err_bit=4),
        llc=LlcMicroarch(max_read_txns=32, max_write_txns=32, amo_num_cuts=1, amo_post_cut=True),
        reg_bus=RegBusMicroarch(max_read_txns=8, max_write_txns=8, amo_num_cuts=1, amo_post_cut=True)
    ),
    
    # --- CLOCK & RESET TREE ---
    # 'generators: 0' means we don't instantiate internal PLLs/FLLs; clocks 
    # will be supplied directly from the external chip pads.
    clock_tree=ClockTree(
        generators=0,
        domains=[
            ClockDomain(
                name="rt",
                description="Real-Time Clock for CLINT and AON timers",
                is_real_time=True,
                has_mux=False,
                has_divider=False
            ),
            ClockDomain(
                name="system",
                description="Main synchronous clock domain for the entire NoC",
                is_real_time=False,
                has_mux=False,
                has_divider=False,
                has_debug_divider=False
            )
        ]
    ),
    
    # --- GLOBAL SYSTEM CONTROLLER & REGISTERS ---
    # Automatically generates the SystemRDL and SystemVerilog for the central
    # configuration registers (PCRs).
    system_controller=SystemController(
        name="gw_soc_regs",
        description="Main system control and status registers",
        base_addr=0x18003000,
        size=0x1000,
        scratch_registers=2,
        version_registers=1,
        jedec_id=0x00000000,
        clk_gen_status_regs=False,
        external_registers=[
            ExternalRegister(name="fll", base_addr=0x18001000),
            ExternalRegister(name="gw_chip_regs", base_addr=0x18002000)
        ],
        # Auto Control Groups elegantly pack clock-gating and reset isolation signals 
        # for massive arrays of identical tiles into a single register array.
        auto_control_groups=[
            AutoControlGroup(name="cluster_ctrl", type="clk_rst_control", target_component_type="snitch_cluster_isle"),
            AutoControlGroup(name="mem_tile_ctrl", type="clk_rst_control", target_component_type="sram_isle")
        ]
    ),
    
    # --- HOST SYSTEM (Manager) ---
    # The main application processor (e.g., Cheshire) that boots the SoC.
    # It's placed at coordinate X=9, Y=3. It uses 'joined' mode, meaning Ollivander 
    # will automatically instantiate a NoC Join adapter to merge the narrow and 
    # wide networks into its single native AXI port.
    host=Component(
        name="manager",
        description="Main application processor (Cheshire host)",
        type="cheshire_isle",
        clock_domain="system",
        # CVA6 implements fence.i (the offload app relies on it to publish the payload);
        # modern binutils want the extension spelled out in the -march string.
        isa="rv64imafdc_zifencei",  # Host Instruction Set Architecture for the software compiler
        abi="lp64d",                # Host Application Binary Interface for the software compiler
        cmodel="medany",            # Host Code Model for the software compiler
        placement={"logical": {"x": 9, "y": 3}},
        # 'jtag' stays exported even though boot_mode 'slink' never drives it: the
        # pads exist on the real chip, and the export keeps them under pad checks.
        export_interfaces=["jtag", "gpio", "slink", "uart", "spi", "i2c"],
        interfaces={
            "axi_master": True,
            "noc_networks": {"master": ["narrow"], "slave": ["narrow", "wide"], "noc_mode": "joined_narrow"},
            "axi_slave": [
                {"name": "internal_rom_ram", "base_addr": 0x00000000, "size": 0x18000000}, # 384 MB
                {"name": "external_dram", "base_addr": BASE_DRAM, "size": 0x1800000000}
            ]
        },
        features={"error_slaves": ["async_axi_llc", "axi_llc"], "terminate_ports": ["async_axi_in", "async_axi_out"]},
        parameters={"Vga": False, "SerialLink": True, "Cva6ExtCieLength": 0x60000000, "Cva6ExtCieOnTop": True, "LlcCdcSyncStages": 0,
                    # The LLC-out window doubles as CVA6's cached+executable region above
                    # the CIE ceiling (see cheshire_isle.sv). This map boots from the L2 at
                    # BASE_L2, so the window covers exactly the 8 L2 tiles and nothing more:
                    # with the DefaultCfg window ([0x8000_0000, 4G)) the cluster windows at
                    # BASE_CLUSTERS would be CACHED, and the offload firmware's return-slot
                    # polls would spin forever on a stale line.
                    "LlcOutRegionStart": BASE_L2, "LlcOutRegionEnd": BASE_L2 + 8 * 0x00100000}
    ),
    
    # --- SYSTEM COMPONENTS (Compute, Memories, Peripherals) ---
    # Here we instantiate all the IPs in the system, mapping them to the 2D mesh.
    components=[
        # --- SHARED L2 MEMORY ---
        Component(
            name="l2_shared_memory",
            description="Level 2 shared SRAM memory",
            type="sram_isle",
            clock_domain="system",
            # Python allows us to pass complex lists easily. 
            # Here we place 8 memory banks split across two disjoint physical columns.
            placement={"logical": [
                {"box": {"x_start": 0, "x_end": 0, "y_start": 0, "y_end": 3}}, # West column
                {"box": {"x_start": 8, "x_end": 8, "y_start": 0, "y_end": 3}}  # East column
            ]},
            interfaces={
                "noc_networks": {"slave": ["narrow", "wide"], "noc_mode": "joined_wide"},
                "axi_slave": [{"name": "l2_spm_global", "base_addr": BASE_L2, "size_per_instance": 0x00100000}]
            },
            parameters={"AxiUserAtop": True, "SramDataWidth": 128, "SramNumWords": 1024, "MemSize": 0x00100000}
        ),
        
        # --- NESTED CRUX MACRO ---
        # This instantiates the Crux Isle Macro (exported by the crossbar_isle example).
        # Deliberately cross-topology: together with super_crux, which nests the Mesh macro,
        # the two super examples exercise the external IPs of BOTH families in a single
        # Bender resolution.
        Component(
            name="crux_subsystem",
            description="Nested Crux Subsystem Macro",
            type="crux_isle", # Uses 'isle' standard AXI ports
            clock_domain="system",
            placement={"logical": {"x": 1, "y": 1}},
            interfaces={
                "axi_master": True,
                # The macro exports one standard 64-bit AXI port, so its master side injects on the
                # narrow network - the same side the join adapts, per noc_mode below. Naming it is
                # not optional: without it the master port was wired to the wide injection instead,
                # putting a 64-bit request struct on a 512-bit port.
                "noc_networks": {"master": ["narrow"], "slave": ["narrow", "wide"], "noc_mode": "joined_narrow"},
                "axi_slave": [{"name": "crux_isle_mem_map", "base_addr": BASE_CRUX_MACRO, "size": 0x88000000}]
            }
        ),
        
        # --- NESTED NOC MACROS ---
        # This instantiates a complete Mesh Subsystem. Because it was exported as
        # 'subtile' from its own project, it natively exposes dual AXI ports and plugs
        # directly into our narrow/wide NoC networks ('dual' mode) without requiring a
        # Join adapter.
        #
        # A single instance is enough to demonstrate the composition. Each one is a full
        # SoC in its own right (a Cheshire host, 16 Snitch clusters and 8 L2 tiles):
        # an array of them pushes the simulation past what vsim can map into
        # memory, while adding nothing to what the example teaches.
        Component(
            name="ai_mesh_macro",
            description="Nested AI Mesh Subsystem Macro (NoC-native IP)",
            type="mesh_dual_isle", # dual boundary: one AXI pair per NoC network
            clock_domain="system",
            placement={"logical": {"x": 2, "y": 0}}, # Single instance; the rest of the grid gets dummy tiles
            interfaces={
                "axi_master": True,
                "noc_networks": {"master": ["narrow", "wide"], "slave": ["narrow", "wide"], "noc_mode": "dual"},
                "axi_slave": [{"name": "mesh_mem_map", "base_addr": BASE_MESH_MACRO, "size_per_instance": 0x40000000}] # 1 GB per instance
            }
        ),
        
        # --- COMPUTE CLUSTERS ---
        Component(
            name="compute_clusters",
            description="AI and Machine Learning compute clusters",
            type="snitch_cluster_isle",
            clock_domain="system",
            # A 'box' defines a 2D array. X[4..7] x Y[0..3] creates exactly 16 cluster instances.
            placement={"logical": {"box": {"x_start": 4, "x_end": 7, "y_start": 0, "y_end": 3}}}, # 16 instances!
            export_interfaces=["debug_req"],
            interfaces={
                "axi_master": True,
                "noc_networks": {"master": ["narrow", "wide"], "slave": ["narrow", "wide"], "noc_mode": "dual"},
                "axi_slave": [{"name": "cluster_tcdm_and_periph", "base_addr": BASE_CLUSTERS, "size_per_instance": 0x00040000}]
            },
            features={"multicast_target": True},
            parameters={"UseHWPE": True}
        ),
        
        # --- SCRATCHPAD MEMORIES ---
        # Independent narrow and wide endpoints explicitly placed on specific NoC networks.
        Component(
            name="top_spm_narrow",
            type="spm_isle",
            clock_domain="system",
            placement={"logical": {"x": 9, "y": 2}},
            interfaces={"noc_networks": {"slave": ["narrow"]}, "axi_slave": [{"name": "spm_narrow", "base_addr": BASE_SPM_NARROW, "size": 0x00040000}]},
            parameters={"SpmWordsPerBank": 2048, "SpmDataWidth": 64}
        ),
        Component(
            name="top_spm_wide",
            type="spm_isle",
            clock_domain="system",
            placement={"logical": {"x": 9, "y": 1}},
            interfaces={"noc_networks": {"slave": ["wide"]}, "axi_slave": [{"name": "spm_wide", "base_addr": BASE_SPM_WIDE, "size": 0x00040000}]},
            parameters={"SpmWordsPerBank": 1024, "SpmDataWidth": 128}
        )
    ],
    
    # --- TESTBENCH CONFIGURATION ---
    # Instructions for the simulation environment.
    testbench={
        # The SELF-SUFFICIENT serial-link boot: no jtag_init, the TAP
        # is never touched - bring-up, image and handoff all ride the link, the
        # exact shape of cheshire's and gwaihir's PRELMODE=1 branches. This
        # project is the fleet's slink-only representative; noc_isle and
        # super_crossbar deliberately keep the hybrid (JTAG liveness + slink
        # transport), the one row the references' menus do not have.
        "boot_mode": "slink",
        # The image and the boot handoff travel the serial link (wip 2.1):
        # no dotted path survives into the preloaded L2 tiles, and the
        # control writes ride the same proven channel (cheshire's PRELMODE
        # pattern; the SBA-to-internal-regs path is anomalous with SerialLink
        # enabled - see the upstream registry).
        "preload_mode": "slink",
        # Only the boot-critical domains are enabled by the testbench; the firmware
        # ungates each target when it needs it and powers it down afterwards.
        "bring_up": "minimal",
        # Duration in ns to hold scratchpad register force values during boot.
        # This must be long enough to survive internal Host reset sequences.
        "boot_force_delay_ns": 5000000,
        "boot_force_fast_delay_ns": 1000000,
        "boot_timeout_ns": 10000000,
        "boot_timeout_fast_ns": 2000000,
        "sim_timeout_ns": 10000000,
        "preload_memories": [
            # Hierarchical RTL path to the first L2 tile, placed at (0,0).
            {"instance": "i_tile_0_0.i_isle", "file": "generated/sw/{test_app}.hex"}
        ]
    },

    # --- SOFTWARE STACK & FIRMWARE ---
    # Defines the toolchain and target memory for automated bare-metal C compilation.
    # Ollivander uses this to automatically generate a memory-mapped Linker Script
    # aligned to the physical memory map.

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
        # payload offload onto every component declaring an Offload* contract (here: the
        # 16 directly-instantiated snitch_cluster_isle instances, launched in parallel; the
        # nested macros are opaque tops and correctly resolve as non-candidates). No
        # 'payload_memory': the boot L2 is reachable from both networks, so the default
        # carve (second quarter of its instance-0 window) is fetchable by the clusters.
        "test_app": {"name": "offload", "auto_generate_c": True,
                     # Simulation-fast UART (divisor 3, ~2.08 Mbaud effective): at 115200
                     # the UART dominates the run. The generator keeps firmware and
                     # testbench monitor on the same divisor; drop the key to return to
                     # 115200 for a physical terminal.
                     "baudrate": 2000000}
    }
)

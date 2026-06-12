# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
External Tool Runners for Ollivander.

This module encapsulates the logic to invoke external command-line tools
(FlooGen, PeakRDL, Verible) as subprocesses during the generation flow.
It also handles the execution of pre-build scripts and code patches on fetched IPs.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

def run_pre_build_steps(env):
    """
    Executes patches and pre-build commands defined in the environment registry.
    This runs after the external IPs have been fetched via Bender, preparing
    their internal state (e.g., generating simulation models, compiling LLVM)
    before the final simulation or synthesis steps.
    """
    registry = env.registry_dependencies
    bender_work = env.bender_dir / "bender_work"
    
    has_steps = any("patches" in d or "pre_build_cmds" in d for d in registry.values())
    if not has_steps:
        return
        
    print("=" * 70)
    print("[*] Starting Phase 0: Preparing External IPs...\n")
    
    for dep_name, dep_info in registry.items():
        dep_dir = bender_work / dep_name
        if not dep_dir.is_dir():
            continue
            
        if "patches" in dep_info:
            for patch in dep_info["patches"]:
                file_path_str = patch.get("file", "").replace("{bender_work}", str(bender_work))
                file_path = Path(file_path_str)
                search_str = patch.get("search", "")
                replace_str = patch.get("replace", "").replace("\\n", "\n")
                
                if file_path.is_file():
                    content = file_path.read_text(encoding='utf-8')
                    if search_str in content:
                        print(f"  -> Patching {file_path.name} in {dep_name}")
                        content = content.replace(search_str, replace_str)
                        file_path.write_text(content, encoding='utf-8')
                        
        if "pre_build_cmds" in dep_info:
            print(f"  -> Executing pre-build commands for {dep_name}...")
            for cmd in dep_info["pre_build_cmds"]:
                cmd = cmd.replace("{bender_work}", str(bender_work)).replace("{ollivander_dir}", str(env.base_dir))
                cmd = cmd.replace("$(PYTHON)", sys.executable).replace("$(MAKE)", "make").replace("$(BENDER)", "bender")
                cmd = cmd.replace("$$", "$")
                print(f"    $ {cmd}")
                try:
                    # Ensure the virtual environment's bin/ is at the front of PATH
                    # so that scripts using #!/usr/bin/env python pick up the venv python.
                    exec_env = os.environ.copy()
                    venv_bin = Path(sys.executable).parent
                    exec_env["PATH"] = f"{venv_bin}:{exec_env.get('PATH', '')}"
                    
                    subprocess.run(cmd, shell=True, check=True, executable='/bin/bash', env=exec_env)
                except subprocess.CalledProcessError:
                    print(f"\n[ERROR] Pre-build command failed for {dep_name}.")
                    sys.exit(1)
    print("  [SUCCESS] All IPs patched and prepared.")

def run_floogen(soc_config, cfg_dir: Path, hw_dir: Path):
    """
    Invokes FlooGen to generate NoC RTL and parameter packages.
    FlooGen reads the auto-generated YAML configuration to instantiate routers,
    links, and define physical network dimensions based on the logical placement.
    """
    if soc_config.topology.type != "noc":
        return
        
    floogen_file = cfg_dir / f"{soc_config.project.name}_floogen.yml"
    if not floogen_file.is_file():
        return
        
    print("=" * 70)
    print("[*] Starting Phase 4: Generating NoC RTL with FlooGen...\n")
    print(f"  -> Running FlooGen on {floogen_file.name}")
    
    # Try to find FlooGen in the system PATH first.
    floogen_exe = shutil.which("floogen")
    if not floogen_exe:
        # Fallback: look for it in the local Python virtual environment.
        venv_floogen = Path(sys.executable).parent / "floogen"
        if venv_floogen.is_file() and os.access(venv_floogen, os.X_OK):
            floogen_exe = str(venv_floogen)
    
    if floogen_exe:
        cmd = [floogen_exe, "pkg", "-c", str(floogen_file), "--outdir", str(hw_dir)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("  [SUCCESS] FlooNoC RTL and packages generated.")
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] FlooGen failed:\n{e.stderr}\n{e.stdout}")
            sys.exit(1)
    else:
        print("\n[ERROR] FlooGen executable not found in PATH.")
        print("[HINT] Please install dependencies using: pip install -r requirements.txt")
        sys.exit(1)

def run_peakrdl(soc_config, reg_dir: Path, hw_dir: Path, sw_dir: Path, registry_dependencies: dict = None, bender_dir: Path = None, custom_rdl_paths: list = None):
    """
    Invokes PeakRDL to generate RTL and C headers from SystemRDL specifications.
    This automatically bridges the gap between hardware registers (System Controller)
    and the software stack (drivers). It intelligently resolves include paths
    based on the environment registry to support complex third-party IP registers.
    """
    if not soc_config.system_controller:
        return
        
    rdl_file = reg_dir / f"{soc_config.project.name}_regs.rdl"
    if not rdl_file.is_file():
        return
        
    print("=" * 70)
    print("[*] Starting Phase 5: Generating Register RTL with PeakRDL...\n")
    
    # Try to find PeakRDL in the system PATH first.
    peakrdl_exe = shutil.which("peakrdl")
    if not peakrdl_exe:
        # Fallback: look for it in the local Python virtual environment.
        venv_peakrdl = Path(sys.executable).parent / "peakrdl"
        if venv_peakrdl.is_file() and os.access(venv_peakrdl, os.X_OK):
            peakrdl_exe = str(venv_peakrdl)

    include_args = ["-I", str(reg_dir)]
    
    # 1. Custom Environment RDL Paths (Highest Priority)
    # Any RDL file found here will override files with the same name in external IPs.
    if custom_rdl_paths:
        for path in custom_rdl_paths:
            custom_path = Path(path).resolve()
            if custom_path.is_dir():
                if str(custom_path) not in include_args:
                    include_args.extend(["-I", str(custom_path)])
            else:
                print(f"[WARNING] Custom RDL directory not found: {custom_path}")

    # 2. Registry Dependencies Auto-Discovery (Lower Priority)
    if registry_dependencies and bender_dir:
        explicit_deps = set()
        for dep_name, dep_info in registry_dependencies.items():
            has_explicit = False
            if "rdl_include_dirs" in dep_info:
                has_explicit = True
                for inc_dir in dep_info["rdl_include_dirs"]:
                    rdl_path = bender_dir / "bender_work" / dep_name / inc_dir
                    if str(rdl_path) not in include_args:
                        include_args.extend(["-I", str(rdl_path)])
            if "main_rdl" in dep_info:
                has_explicit = True
                rdl_path = bender_dir / "bender_work" / dep_name / Path(dep_info["main_rdl"]).parent
                if str(rdl_path) not in include_args:
                    include_args.extend(["-I", str(rdl_path)])
            if has_explicit:
                explicit_deps.add(dep_name)
                        
        # Fallback: Safe Auto-Discovery for Include Paths
        # Only auto-discover in bender_work/ subdirectories that were NOT explicitly configured.
        bender_work = bender_dir / "bender_work"
        if bender_work.is_dir():
            for dep_dir in bender_work.iterdir():
                if dep_dir.is_dir() and dep_dir.name not in explicit_deps:
                    for ext_rdl in dep_dir.rglob("*.rdl"):
                        if str(ext_rdl.parent) not in include_args:
                            include_args.extend(["-I", str(ext_rdl.parent)])

    if peakrdl_exe:
        print(f"  -> Running PeakRDL on {rdl_file.name}")
        try:
            # Generate the SystemVerilog RTL implementation of the registers
            cmd_sv = [peakrdl_exe, "regblock", str(rdl_file), "--cpuif", "apb4-flat", "--default-reset", "arst_n", "-o", str(hw_dir)]
            subprocess.run(cmd_sv, check=True, capture_output=True, text=True)
            print("  [SUCCESS] System Controller register RTL generated.")

            memory_map_file = reg_dir / f"{soc_config.project.name}_memory_map.rdl"
            if memory_map_file.is_file():
                rdl_source = memory_map_file
            else:
                rdl_source = rdl_file

            # Generate the C Defines Header for software driver development
            c_header_file = sw_dir / f"{soc_config.project.name}_regs.h"
            cmd_c = [peakrdl_exe, "c-header", str(rdl_source)] + include_args + ["-o", str(c_header_file), "-i", "-b", "ltoh"]
            subprocess.run(cmd_c, check=True, capture_output=True, text=True)
            print(f"  [SUCCESS] System Controller C header generated ({c_header_file.name}).")
            
            # Generate the SV Raw Header for Testbench usage (macros for register addresses)
            sv_header_file = hw_dir / f"{soc_config.project.name}_regs.svh"
            cmd_svh = [peakrdl_exe, "raw-header", str(rdl_source)] + include_args + ["-o", str(sv_header_file), "--format", "svh", "--no-prefix"]
            # We don't enforce check=True here because 'peakrdl-rawheader' is a third-party plugin 
            # that might not be installed in all environments.
            subprocess.run(cmd_svh, capture_output=True, text=True)

            # Generate the C Raw Header for alternative firmware usage
            c_raw_header_file = sw_dir / f"{soc_config.project.name}_raw_regs.h"
            cmd_c_raw = [peakrdl_exe, "raw-header", str(rdl_source)] + include_args + ["-o", str(c_raw_header_file), "--base_name", f"{soc_config.project.name}_raw_regs", "--format", "c"]
            subprocess.run(cmd_c_raw, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] PeakRDL failed:\n{e.stderr}\n{e.stdout}")
            sys.exit(1)
    else:
        print("\n[ERROR] PeakRDL executable not found in PATH.")
        print("[HINT] Please install dependencies using: pip install -r requirements.txt")
        sys.exit(1)

def run_verible(hw_dir: Path, tb_dir: Path):
    """
    Invokes Google's Verible to format the generated SystemVerilog source files.
    This ensures that the output RTL is not only syntactically correct but also
    human-readable, aligned, and adheres to strict formatting standards.
    """
    print("=" * 70)
    print("[*] Starting Phase 6: Formatting RTL with Verible...\n")
    
    # Try to find the Verible formatter in the system PATH.
    verible_exe = shutil.which("verible-verilog-format")
    if not verible_exe:
        # Fallback: check if it's installed locally in the Python venv.
        venv_verible = Path(sys.executable).parent / "verible-verilog-format"
        if venv_verible.is_file() and os.access(venv_verible, os.X_OK):
            verible_exe = str(venv_verible)
            
    if verible_exe:
        # Collect all generated SystemVerilog design and testbench files.
        sv_files = list(hw_dir.rglob("*.sv")) + list(hw_dir.rglob("*.svh")) + list(tb_dir.rglob("*.sv"))
        if sv_files:
            print(f"  -> Formatting {len(sv_files)} SystemVerilog files...")
            cmd = [verible_exe, "--inplace", "--column_limit=150", "--port_declarations_alignment=align", "--named_port_alignment=align", "--named_parameter_alignment=align"] + [str(f) for f in sv_files]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("  [SUCCESS] RTL formatting complete.")
    else:
        print("  [INFO] verible-verilog-format not found. Skipping RTL formatting.")
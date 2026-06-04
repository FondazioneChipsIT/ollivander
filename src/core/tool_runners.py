# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
External Tool Runners for Ollivander.

This module encapsulates the logic to invoke external command-line tools
(FlooGen, OpenTitan regtool, Verible) as subprocesses during the generation flow.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

def run_floogen(soc_config, cfg_dir: Path, hw_dir: Path):
    """
    Invokes FlooGen to generate NoC RTL and parameter packages.
    FlooGen reads a generated YAML configuration to instantiate routers,
    links, and define network dimensions.
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

def run_regtool(soc_config, reg_dir: Path, hw_dir: Path, sw_dir: Path, regtool_paths: list, base_dir: Path):
    """
    Invokes OpenTitan's regtool to generate RTL and C headers from HJSON.
    This automatically bridges the gap between hardware registers (System Controller)
    and the software stack (drivers) by compiling the standard HJSON specification.
    """
    if not soc_config.system_controller:
        return
        
    hjson_file = reg_dir / f"{soc_config.project.name}_regs.hjson"
    if not hjson_file.is_file():
        return
        
    print("=" * 70)
    print("[*] Starting Phase 5: Generating Register RTL with regtool...\n")
    
    # Find the regtool.py script from the configured environment paths.
    regtool_path = None
    for p in regtool_paths:
        if p.is_file():
            regtool_path = p
            break
    if not regtool_path:
        regtool_path = base_dir / "tools" / "reggen" / "regtool.py"

    if regtool_path.is_file():
        cmd = [
            sys.executable, 
            str(regtool_path), 
            "-r", 
            "-t", str(hw_dir), 
            str(hjson_file)
        ]
        print(f"  -> Running regtool on {hjson_file.name}")
        try:
            # Generate the SystemVerilog RTL implementation of the registers.
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("  [SUCCESS] System Controller register RTL generated.")

            # Generate the C Defines Header for software driver development.
            c_header_file = sw_dir / f"{soc_config.project.name}_regs.h"
            cmd_c = [
                sys.executable, 
                str(regtool_path), 
                "--cdefines", 
                "-o", str(c_header_file), 
                str(hjson_file)
            ]
            print("  -> Running regtool to generate C header...")
            subprocess.run(cmd_c, check=True, capture_output=True, text=True)
            print(f"  [SUCCESS] System Controller C header generated ({c_header_file.name}).")
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] regtool failed:\n{e.stderr}")
            if "ModuleNotFoundError" in e.stderr:
                print("[HINT] A dependency for regtool is missing in your environment.")
                print("       Run: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print(f"[WARNING] regtool.py not found at {regtool_path}. Skipping register RTL generation.")

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
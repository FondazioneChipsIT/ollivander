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
import yaml
from pathlib import Path
from core.utils import get_generation_comment

def run_pre_build_steps(env):
    """
    Executes patches and pre-build commands defined in the environment registry.
    This runs after the external IPs have been fetched via Bender, preparing
    their internal state (e.g., generating simulation models, compiling LLVM)
    before the final simulation or synthesis steps.
    """
    registry = env.registry_dependencies
    bender_work = env.bender_dir / "bender_work"
    
    ledgers = sorted(bender_work.glob("*/.ollivander_patched")) if bender_work.is_dir() else []
    has_steps = ledgers or any(
        "patches" in d or "pre_build_cmds" in d for d in registry.values() if d)
    if not has_steps:
        return

    print("=" * 70)
    print("[*] Phase 4 (cont'd): Preparing External IPs...\n")

    # Restoration is driven by the ledgers found on disk, not by the registry, and happens before
    # anything else. Those are two deliberate choices, each learned from getting it wrong: a
    # dependency whose entry was deleted outright would never be visited if the registry drove the
    # loop, and its last patches would stay applied forever; and restoring inside the per-dependency
    # loop left files patched whenever the entry no longer declared any patch. The ledger is the
    # authority on what Ollivander has modified, so it is what decides what to undo.
    for ledger in ledgers:
        for line in ledger.read_text(encoding="utf-8").split("\n"):
            f = Path(line.strip())
            if not line.strip() or not f.parent.is_dir():
                continue
            r = subprocess.run(["git", "-C", str(f.parent), "checkout", "--", f.name],
                               capture_output=True, text=True)
            if r.returncode != 0 and f.is_file():
                # Failing silently here would resume applying patches on top of themselves, the
                # defect this restore exists to remove, so stop rather than continue blindly.
                print(f"\n[ERROR] Could not restore '{f}' to its fetched state.\n{r.stderr.strip()}")
                sys.exit(1)

    for dep_name, dep_info in registry.items():
        dep_dir = bender_work / dep_name
        if not dep_dir.is_dir() or not dep_info:
            continue

        if "patches" in dep_info:
            # Everything is applied to freshly restored files, so patching is idempotent by
            # construction: a file always goes from pristine to patched, whatever ran before.
            # Applying blindly would re-apply any patch whose replacement contains its own search
            # string - that had silently accumulated 54 copies of one line in cva6 and 27 in
            # pulp_cluster, which is also what kept those checkouts dirty and made Bender degrade
            # them to path dependencies. It also means editing a patch replaces the old text instead
            # of layering over it, and a hand-edited file is reabsorbed on the next run: to work on
            # a dependency, use `bender clone` rather than touching the checkout.
            #
            # The ledger records, append-only, every file this dependency has ever had patched, so
            # that the restore pass above can undo a patch that has since been removed from the
            # configuration - or removed together with its whole entry.
            ledger = dep_dir / ".ollivander_patched"
            ever = {l for l in ledger.read_text(encoding="utf-8").split("\n") if l.strip()} \
                if ledger.is_file() else set()
            ever |= {patch.get("file", "").replace("{bender_work}", str(bender_work))
                     for patch in dep_info["patches"]}
            ledger.write_text("\n".join(sorted(ever)) + "\n", encoding="utf-8")

            for patch in dep_info.get("patches", []):
                file_path = Path(patch.get("file", "").replace("{bender_work}", str(bender_work)))
                search_str = patch.get("search", "")
                replace_str = patch.get("replace", "").replace("\\n", "\n")

                if file_path.is_file():
                    content = file_path.read_text(encoding='utf-8')
                    if search_str in content:
                        print(f"  -> Patching {file_path.name} in {dep_name}")
                        content = content.replace(search_str, replace_str)
                        file_path.write_text(content, encoding='utf-8')
                    else:
                        # The file was just restored, so a search string that does not match cannot
                        # mean "already applied": it means the IP no longer contains what the patch
                        # was written against, and the patch has quietly become a no-op. Saying so
                        # is only possible thanks to the restore; before it, absence was ambiguous.
                        print(f"  [WARNING] Stale patch for {dep_name}: '{search_str[:60]}' no longer"
                              f" occurs in {file_path.name}. It has no effect and should be revised.")
                        
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
    print("[*] Starting Phase 5: Generating NoC RTL with FlooGen...\n")
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

def _pack_regblock_storage(regs_sv: Path):
    """Turn the PeakRDL 'field_storage_t' typedef into a packed struct, in place.

    peakrdl-regblock deliberately emits its internal register storage as an unpacked struct
    (unpacked members prevent accidental whole-struct assignments), and version 1.3.1 offers
    no option to change that. Verilator's V3Force, however, cannot build force infrastructure
    through unpacked composites ("Unsupported: opaque force path selector ARRAYSEL", an
    internal error): the generated testbench forces the bring-up and boot-scratch registers
    through exactly this struct, so an unpacked storage stops the whole verilator simulation
    flow. The packed layout is bit-identical, the struct is internal to the regblock (the
    hwif contract is untouched), and both simulators accept it - validated with identical
    UART/EOT runs on QuestaSim and Verilator. The transform rewrites 'typedef struct' into
    'typedef struct packed' inside the field_storage_t block only, and moves the unpacked
    array dimension of each member ('} name[N];') to a packed one ('} [N-1:0] name;').
    The same repair is applied to cheshire's checked-in copy by a catalogue patch.
    """
    import re
    if not regs_sv.is_file():
        return
    text = regs_sv.read_text(encoding="utf-8")
    # Isolate the field_storage_t typedef alone: the negative lookahead pins the match to
    # the 'typedef struct {' nearest to the closing '} field_storage_t;', so the other
    # regblock typedefs (decoded_reg_strb_t, field_combo_t) are left untouched - the strobe
    # struct in particular holds unpacked scalar arrays that must not become packed members.
    m = re.search(r"(  typedef struct \{(?:(?!typedef struct \{).)*?\} field_storage_t;)",
                  text, flags=re.DOTALL)
    if not m:
        return
    block = m.group(1)
    packed = block.replace("typedef struct {", "typedef struct packed {")
    packed = packed.replace("struct {", "struct packed {")
    # '} name[N];' -> '} [N-1:0] name;' (unpacked member array becomes packed).
    packed = re.sub(r"\} (\w+)\[(\d+)\];",
                    lambda mm: "} [%d:0] %s;" % (int(mm.group(2)) - 1, mm.group(1)),
                    packed)
    if packed != block:
        text = text.replace(block, packed)
        regs_sv.write_text(text, encoding="utf-8")
        print("  -> Packed the field_storage_t struct (verilator force compatibility).")


def _pack_hwif_pkg(pkg_sv: Path):
    """Turn every hwif typedef of the PeakRDL package into a packed struct, in place.

    The companion of _pack_regblock_storage, one Verilator pass further down: the hwif
    in/out structs cross the register block's boundary and, on a NoC, leave the manager
    tile as a port. When that tile is a hierarchical block, V3ProtectLib must build the
    DPI marshalling of every port of the child library, and on an unpacked struct port
    it segfaults instead of erroring (Verilator 5.050, SIGSEGV in
    V3Task::assignInternalToDpi via ProtectVisitor::handleOutput, met 2026-08-17 on
    mesh_manager_tile). The hwif package contains hardware-only members (logic vectors
    and nested structs of them), so the packed layout is bit-identical and every
    consumer keeps accessing fields by name; unlike the storage transform, ALL typedefs
    here are safe to pack, which is why this rewrites the whole package rather than one
    isolated block. Member arrays ('} name[N];') move to a packed dimension like in the
    storage transform.
    """
    import re
    if not pkg_sv.is_file():
        return
    text = pkg_sv.read_text(encoding="utf-8")
    packed = text.replace("typedef struct {", "typedef struct packed {")
    # Unpacked member arrays are illegal inside a packed struct and must move to a
    # packed dimension. Two shapes occur: '} name[N];' closing an anonymous nested
    # struct (as in the storage transform), and 'some_t name[N];' on a typed member
    # (the hwif packages declare repeated registers this way, e.g. 'version[1]').
    # The whole file is this package's typedefs, so no other '[N];' shape exists.
    packed = re.sub(r"\} (\w+)\[(\d+)\];",
                    lambda mm: "} [%d:0] %s;" % (int(mm.group(2)) - 1, mm.group(1)),
                    packed)
    packed = re.sub(r"(\w+)\s+(\w+)\[(\d+)\];",
                    lambda mm: "%s [%d:0] %s;" % (mm.group(1), int(mm.group(3)) - 1, mm.group(2)),
                    packed)
    if packed != text:
        pkg_sv.write_text(packed, encoding="utf-8")
        print("  -> Packed the hwif package structs (verilator protect-lib compatibility).")


def run_peakrdl_sysregs(top_level_module_name, reg_dir: Path, hw_dir: Path):
    """
    Early, minimal regblock pass on the System Controller's OWN RDL - the one
    file of the register flow that is self-contained (generated from the
    configuration, no third-party includes, unlike the memory map that keeps
    the full run in Phase 6 behind the Bender fetch). It exists so the
    top-level render can read the REAL s_apb_paddr width from the artifact
    instead of assuming 8: the assumption held on every fleet project by
    coincidence and broke on crux_mini's 16-byte register file (2026-08-23).
    Phase 6 regenerates the same file identically (and applies the Verilator
    packing passes); this pass deliberately skips them.
    """
    rdl_file = reg_dir / f"{top_level_module_name}_regs.rdl"
    if not rdl_file.is_file():
        return
    peakrdl_exe = shutil.which("peakrdl")
    if not peakrdl_exe:
        venv_peakrdl = Path(sys.executable).parent / "peakrdl"
        if venv_peakrdl.is_file() and os.access(venv_peakrdl, os.X_OK):
            peakrdl_exe = str(venv_peakrdl)
    if not peakrdl_exe:
        return
    cmd_sv = [peakrdl_exe, "regblock", str(rdl_file), "--cpuif", "apb4-flat",
              "--default-reset", "arst_n", "-o", str(hw_dir)]
    subprocess.run(cmd_sv, check=True, capture_output=True, text=True)


def run_peakrdl(soc_config, reg_dir: Path, hw_dir: Path, sw_dir: Path, registry_dependencies: dict = None, bender_dir: Path = None, custom_rdl_paths: list = None):
    """
    Invokes PeakRDL to generate RTL and C headers from SystemRDL specifications.
    This automatically bridges the gap between hardware registers (System Controller)
    and the software stack (drivers). It intelligently resolves include paths
    based on the environment registry to support complex third-party IP registers.
    """
    if not soc_config.system_controller:
        return
        
    top_level_module_name = soc_config.project.top_level_module_name
            
    rdl_file = reg_dir / f"{top_level_module_name}_regs.rdl"
    if not rdl_file.is_file():
        return
        
    print("=" * 70)
    print("[*] Starting Phase 6: Generating Register RTL with PeakRDL...\n")
    
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
            # The regblock file is named after the RDL addrmap (e.g. <name>_sys_regs.sv),
            # so pick up whatever *_regs.sv the export just produced.
            for regblock_sv in hw_dir.glob("*_regs.sv"):
                _pack_regblock_storage(regblock_sv)
            for regblock_pkg in hw_dir.glob("*_regs_pkg.sv"):
                _pack_hwif_pkg(regblock_pkg)
            print("  [SUCCESS] System Controller register RTL generated.")

            memory_map_file = reg_dir / f"{top_level_module_name}_memory_map.rdl"
            if memory_map_file.is_file():
                rdl_source = memory_map_file
            else:
                rdl_source = rdl_file

            # Generate the C Defines Header for software driver development
            c_header_file = sw_dir / f"{top_level_module_name}_regs.h"
            cmd_c = [peakrdl_exe, "c-header", str(rdl_source)] + include_args + ["-o", str(c_header_file), "-i", "-b", "ltoh"]
            subprocess.run(cmd_c, check=True, capture_output=True, text=True)
            print(f"  [SUCCESS] System Controller C header generated ({c_header_file.name}).")
            
            # Generate the SV Raw Header for Testbench usage (macros for register addresses)
            sv_header_file = hw_dir / f"{top_level_module_name}_regs.svh"
            cmd_svh = [peakrdl_exe, "raw-header", str(rdl_source)] + include_args + ["-o", str(sv_header_file), "--format", "svh", "--no-prefix"]
            # We don't enforce check=True here because 'peakrdl-rawheader' is a third-party plugin 
            # that might not be installed in all environments.
            subprocess.run(cmd_svh, capture_output=True, text=True)

            # Generate the C Raw Header for alternative firmware usage
            c_raw_header_file = sw_dir / f"{top_level_module_name}_raw_regs.h"
            cmd_c_raw = [peakrdl_exe, "raw-header", str(rdl_source)] + include_args + ["-o", str(c_raw_header_file), "--base_name", f"{top_level_module_name}_raw_regs", "--format", "c"]
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
    print("[*] Starting Phase 9: Formatting RTL with Verible...\n")
    
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

def run_padrick(env, soc_config, project_dir: Path):
    """
    Invokes Padrick to generate the Padframe RTL, CSRs, and Padlist CSV.
    """
    if not soc_config.padframe:
        return
        
    print("=" * 70)
    print("[*] Starting Phase 7: Generating Padframe with Padrick...\n")
    
    padrick_exe = shutil.which("padrick")
    venv_padrick = Path(sys.executable).parent / "padrick"
    
    padrick_base_cmd = None
    
    # If padrick is in the current virtual environment, we must monkey-patch Pydantic
    # because Padrick strictly requires Pydantic v1, while Ollivander requires Pydantic v2.
    if venv_padrick.is_file() and os.access(venv_padrick, os.X_OK):
        padrick_wrapper = (
            "import sys\n"
            "try:\n"
            "    import pydantic.v1 as pydantic\n"
            "    sys.modules['pydantic'] = pydantic\n"
            "except ImportError:\n"
            "    pass\n"
            "sys.argv = sys.argv[1:]\n"
            "from padrick.CLIEntryPoint import cli\n"
            "sys.exit(cli())\n"
        )
        padrick_base_cmd = [sys.executable, "-c", padrick_wrapper, "padrick"]
    elif padrick_exe:
        padrick_base_cmd = [padrick_exe]
    else:
        print("  [WARNING] Padrick executable not found. Skipping Padframe generation.")
        print("  [HINT] Install Padrick via: pip install padrick")
        return

    hw_dir = env.outdir_path / env.hw_sub
    doc_dir = env.outdir_path / env.doc_sub
    cfg_dir = env.outdir_path / env.cfg_sub

    if soc_config.padframe.padrick_cfg:
        top_cfg = project_dir / soc_config.padframe.padrick_cfg
        if not top_cfg.is_file():
            print(f"\n[ERROR] Padrick configuration not found: {top_cfg}")
            sys.exit(1)
    else:
        top_cfg = cfg_dir / f"{soc_config.project.name}_padrick_top.yml"
        port_groups_file = cfg_dir / f"{soc_config.project.name}_soc_port_groups.yml"
        
        top_dict = {
            "name": soc_config.padframe.name,
            "manifest_version": 3,
            "pad_domains": []
        }
        
        domains_config = soc_config.padframe.domains or []
        
        for dom in domains_config:
            tech_file = None
            search_dirs = env.component_paths + [env.base_dir / "components"]
            for d in search_dirs:
                candidate = d / "padframes" / dom.tech / f"{dom.tech}.yml"
                if candidate.is_file():
                    tech_file = candidate
                    break
                candidate = d / "padframes" / "tech" / f"{dom.tech}.yml"
                if candidate.is_file():
                    tech_file = candidate
                    break
            if not tech_file:
                print(f"\n[ERROR] Padframe technology catalog '{dom.tech}' not found.")
                sys.exit(1)
                
            pad_list_data = soc_config.padframe.get_pad_list_data(dom.name, project_dir)
                
            top_dict["pad_domains"].append({
                "name": dom.name,
                "pad_types": yaml.safe_load(tech_file.read_text(encoding='utf-8')),
                "pad_list": pad_list_data
            })
            
            # Save the intermediate domain-specific padlist YAML for debugging
            if soc_config.padframe.pad_csv or soc_config.padframe.pad_py:
                domain_list_file = cfg_dir / f"{soc_config.project.name}_pad_list_{dom.name}.yml"
                with open(domain_list_file, 'w', encoding='utf-8') as f:
                    f.write(get_generation_comment("#", soc_config.padframe.header_file))
                    yaml.dump(pad_list_data, f, sort_keys=False, default_flow_style=False)
            
        if port_groups_file.is_file():
            pg_dict = yaml.safe_load(port_groups_file.read_text(encoding='utf-8'))
            if "port_groups" in pg_dict:
                for dom in top_dict["pad_domains"]:
                    if any(not pad.get("is_static", False) for pad in dom.get("pad_list", [])):
                        dom["port_groups"] = pg_dict["port_groups"]
                        break # Padrick typically allows the port_group on the first dynamic domain
                
        # Check for unmapped logical ports to warn the user
        pg_dict_val = yaml.safe_load(port_groups_file.read_text(encoding='utf-8')) if port_groups_file.is_file() else {}
        soc_exports = next((pg for pg in pg_dict_val.get("port_groups", []) if pg["name"] == "soc_exports"), None)
        if soc_exports:
                    mapped_logical_ports = set()
                    statically_routed_wires = set()
                    for dom in top_dict["pad_domains"]:
                        for pad in dom.get("pad_list", []):
                            if "default_port" in pad:
                                p_val = pad["default_port"].split(".")[-1]
                                if "_{i}" in p_val and pad.get("multiple", 1) > 1:
                                    base_p = p_val.replace("_{i}", "")
                                    for i in range(pad.get("multiple", 1)):
                                        mapped_logical_ports.add(f"{base_p}_{i}")
                                else:
                                    mapped_logical_ports.add(p_val)
                            if "connections" in pad:
                                for pad_sig, soc_sig in pad["connections"].items():
                                    if "_{i}" in soc_sig and pad.get("multiple", 1) > 1:
                                        base_s = soc_sig.replace("_{i}", "")
                                        for i in range(pad.get("multiple", 1)):
                                            statically_routed_wires.add(f"{base_s}_{i}")
                                    else:
                                        statically_routed_wires.add(soc_sig)
                                
                    unmapped_ports = []
                    for port in soc_exports.get("ports", []):
                        p_name = port["name"]
                        if p_name in mapped_logical_ports:
                            continue
                            
                        # Check if all its connections are statically routed
                        conns = port.get("connections", {})
                        if conns:
                            is_fully_static = True
                            for k, v in conns.items():
                                soc_sig = k if v in ["pad2chip", "paden2chip", "chip2pad"] else v
                                if soc_sig not in statically_routed_wires:
                                    is_fully_static = False
                                    break
                            if is_fully_static:
                                continue
                                
                        unmapped_ports.append(p_name)
            
        with open(top_cfg, 'w', encoding='utf-8') as f:
            f.write(get_generation_comment("#", Path(top_cfg).parent))
            yaml.dump(top_dict, f, sort_keys=False, default_flow_style=False)

    # Output directories
    padframe_rtl_dir = hw_dir / "padframe"
    padframe_rtl_dir.mkdir(parents=True, exist_ok=True)

    # Handle RTL header generation
    header_path = None
    if soc_config.padframe.header_file:
        user_header = project_dir / soc_config.padframe.header_file
        if user_header.is_file():
            header_path = user_header
        else:
            print(f"  [WARNING] Custom header file not found: {user_header}")

    if not header_path:
        # Auto-generate a default header matching license_header.mako
        header_path = padframe_rtl_dir / "padrick_header.txt"
        header_content = (
            "// Copyright 2026 Fondazione Chips-IT.\n"
            "// Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.\n"
            "// SPDX-License-Identifier: SHL-0.51\n"
            + get_generation_comment("//", Path(padframe_rtl_dir).parent)
        )
        header_path.write_text(header_content, encoding='utf-8')

    print(f"  -> Generating RTL from {top_cfg.name}...")
    cmd_rtl = padrick_base_cmd + ["generate", "rtl", str(top_cfg), "-o", str(padframe_rtl_dir)]
    if header_path:
        cmd_rtl.extend(["--header", str(header_path)])

    try:
        subprocess.run(cmd_rtl, check=True, capture_output=True, text=True)
        print("  [SUCCESS] Padframe RTL successfully generated.")
    except subprocess.CalledProcessError as e:
        print(f"\n[WARNING] Padrick RTL generation failed (possibly due to empty padlist). Skipping.")
        print(f"  -> {e.stderr if e.stderr else ''}\n{e.stdout if e.stdout else ''}")

    print(f"  -> Generating Padlist CSV...")
    cmd_csv = padrick_base_cmd + ["generate", "padlist", str(top_cfg), "-o", str(doc_dir)]
    try:
        subprocess.run(cmd_csv, check=True, capture_output=True, text=True)
        print("  [SUCCESS] Padlist CSV successfully generated.")
    except subprocess.CalledProcessError as e:
        print(f"\n[WARNING] Padrick Padlist CSV generation failed. Skipping.")

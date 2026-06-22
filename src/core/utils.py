# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import re
from pathlib import Path

# =========================================================================
# Mako Template Helper Functions
# =========================================================================
# These functions are passed to the Mako rendering engine and can be called
# directly from within the .mako template files.
def fmt_dom(name): return name.replace('_clk', '').lower() if name else ""
def fmt_reg(name): return name.replace('_clk', '').lower() if name else ""
def fmt_rst(name): return name.replace('_rst', '').lower() if name else ""
def camel_case(name): return ''.join(word.title() for word in name.split('_'))

def strip_comments(content: str) -> str:
    """
    Removes single-line (//) and block (/* ... */) comments from SystemVerilog code,
    safely ignoring comment-like patterns inside string literals.
    """
    return re.sub(
        r'("[^"\\]*(?:\\.[^"\\]*)*")|(//[^\n]*)|(/\*.*?\*/)',
        lambda m: m.group(1) if m.group(1) else '',
        content,
        flags=re.DOTALL
    )

def is_external(comp):
    """
    Checks if a component is marked as 'external' in the YAML. External components
    have their interface ports (e.g., RegBus) exported to the top-level I/O
    instead of being instantiated inside the SoC.
    """
    if not comp.interfaces:
        return False
    slaves = comp.interfaces.get('regbus_slave', [])
    if isinstance(slaves, dict):
        slaves = [slaves]
    return any(slv.get('external', False) for slv in slaves)

def auto_import_sv_packages(code: str) -> str:
    """
    Post-processes rendered SystemVerilog code to automatically add missing
    `import` statements. It scans the code for package-scoped identifiers
    (e.g., `my_pkg::my_type`) and ensures `import my_pkg::*;` is present.
    
    This significantly reduces the burden on Mako templates, as developers
    don't need to manually track and emit import statements for every data type.
    """
    # Find all unique package names used with the '::' scope resolution operator.
    pkgs = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)::', code))
    # Find all packages that are already explicitly imported in the code.
    existing_imports = set(re.findall(r'\bimport\s+([a-zA-Z_][a-zA-Z0-9_]*)::\*;', code))
    
    # Determine which packages are missing.
    new_imports = pkgs - existing_imports
    if new_imports:
        # Create the new 'import' statements.
        import_statements = "".join([f"  import {p}::*;\n" for p in sorted(list(new_imports))])
        insert_pos = -1
        
        # Try to find the optimal insertion point: preferably right after existing imports.
        last_import_match = list(re.finditer(r'\bimport\s+[a-zA-Z_][a-zA-Z0-9_]*::\*;', code))
        if last_import_match:
            line_end = code.find('\n', last_import_match[-1].end())
            insert_pos = line_end + 1 if line_end != -1 else last_import_match[-1].end()
        else:
            # If no imports exist, insert them right after the 'module' declaration.
            module_match = re.search(r'\bmodule\s+[a-zA-Z_][a-zA-Z0-9_]*\s*(?:#\(|\(|;|\n)', code)
            if module_match:
                line_end = code.find('\n', module_match.start())
                insert_pos = line_end + 1 if line_end != -1 else module_match.end()
                
        if insert_pos != -1:
            return code[:insert_pos] + import_statements + code[insert_pos:]
    return code

def write_if_changed(file_path: Path, content: str):
    """
    Writes content to a file only if it differs from the existing content.
    This is extremely important for build systems like Make: by preserving the 
    modification timestamp of unchanged files, we avoid triggering unnecessary 
    recompilations of the RTL in downstream tools.
    """
    if file_path.is_file() and file_path.read_text(encoding="utf-8", errors="ignore") == content:
        return
    file_path.write_text(content, encoding="utf-8", newline="\n")
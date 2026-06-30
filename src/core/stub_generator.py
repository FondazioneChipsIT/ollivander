# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import sys
import re
from pathlib import Path
from core.utils import strip_comments, get_generation_comment


def resolve_active_dependencies(files, seeds, outdir_path, global_options, fast_check_tool="questa"):
    """
    Traces SystemVerilog dependencies transitively starting from seed modules.
    Returns a set of files that are actually referenced (imported or instantiated)
    by the active hierarchy, filtering out unused files/packages from dependencies.
    """
    def get_expanded_content(file_path, visited_includes=None):
        if visited_includes is None:
            visited_includes = set()
        file_path_abs = str(Path(file_path).resolve())
        if file_path_abs in visited_includes:
            return ""
        visited_includes.add(file_path_abs)

        try:
            content = Path(file_path_abs).read_text(encoding='utf-8', errors='ignore')
            content_clean = strip_comments(content)

            # Find all includes and expand them inline using the active include directories
            expanded_parts = []
            last_end = 0
            for match in re.finditer(r'`include\s+"([^"]+)"', content_clean):
                expanded_parts.append(content_clean[last_end:match.start()])
                inc_match = match.group(1)
                # Resolve inc_match using the include search paths
                for opt in global_options:
                    opt_str = opt.strip('\"\'')
                    if opt_str.startswith('+incdir+'):
                        inc_dir = Path(opt_str[8:].replace('$ROOT', '.')).resolve()
                        resolved = inc_dir / inc_match
                        if resolved.exists():
                            expanded_parts.append(get_expanded_content(resolved, visited_includes))
                            break
                last_end = match.end()
            expanded_parts.append(content_clean[last_end:])
            return "".join(expanded_parts)
        except Exception:
            return ""

    module_to_file = {}
    package_to_file = {}

    total_files = len(files)
    from core.utils import draw_progress_bar
    for idx, f in enumerate(files):
        f_clean = f.strip('\"\'').replace('$ROOT', '.')
        f_path = Path(f_clean).resolve()
        if not f_path.is_file():
            continue
        draw_progress_bar(idx + 1, total_files, prefix="  -> Mapping active hierarchy        ", suffix=f"({idx+1}/{total_files})")
        try:
            content_clean = get_expanded_content(f_path)
            for m in re.findall(r'\b(?:module|interface)\s+([a-zA-Z_0-9]+)\b', content_clean):
                if fast_check_tool == "verilator":
                    module_to_file[m] = [str(f_path)]
                else:
                    if m not in module_to_file:
                        module_to_file[m] = []
                    module_to_file[m].append(str(f_path))
            for p in re.findall(r'\bpackage\s+([a-zA-Z_0-9]+)\b', content_clean):
                if fast_check_tool == "verilator":
                    package_to_file[p] = [str(f_path)]
                else:
                    if p not in package_to_file:
                        package_to_file[p] = []
                    package_to_file[p].append(str(f_path))
        except Exception:
            pass

    # 2. Trace transitively starting from top-level seeds
    needed_files = set()
    visited = set()
    queue = list(seeds)

    # Add modules/interfaces used, instantiated, or imported in generated stubs directly to the queue
    stubs_dir = outdir_path / ".stubs"
    if stubs_dir.is_dir():
        for stub_path in stubs_dir.glob("*.sv"):
            try:
                content_clean = get_expanded_content(stub_path)

                # Find defined modules/interfaces in stubs
                for m in re.findall(r'\b(?:module|interface)\s+([a-zA-Z_0-9]+)\b', content_clean):
                    queue.append(m)

                # Find instantiations in stubs
                insts = re.findall(r'\b([a-zA-Z_0-9]+)\s*#\s*\(', content_clean)
                insts.extend(re.findall(r'\b([a-zA-Z_0-9]+)\s+[a-zA-Z_0-9]+\s*\(', content_clean))
                # Find interface port declarations
                insts.extend(re.findall(r'\b([a-zA-Z_0-9]+)\.[a-zA-Z_0-9]+\s+[a-zA-Z_0-9]+\b', content_clean))
                # Find virtual interfaces (e.g., virtual AXI_BUS_DV)
                insts.extend(re.findall(r'\bvirtual\s+([a-zA-Z_0-9]+)\b', content_clean))

                # Find package imports and scope references (my_pkg::...)
                imports = re.findall(r'\bimport\s+([a-zA-Z_0-9]+)::', content_clean)
                imports.extend(re.findall(r'\b([a-zA-Z_0-9]+)::', content_clean))

                keywords = {'if', 'case', 'for', 'while', 'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'logic', 'wire', 'reg', 'bit', 'int', 'struct', 'typedef', 'enum', 'return', 'else', 'begin', 'end'}
                for item in insts + imports:
                    if item not in visited and item not in keywords:
                        queue.append(item)
            except Exception:
                pass

    while queue:
        sys.stdout.write(f"\r  -> Tracing active dependencies: {len(needed_files)} files resolved ({len(queue)} in queue) ...")
        sys.stdout.flush()
        item = queue.pop(0)
        if item in visited:
            continue
        visited.add(item)

        defining_files = module_to_file.get(item, []) + package_to_file.get(item, [])
        for defining_file in defining_files:
            if not defining_file:
                continue
            needed_files.add(defining_file)

            # Parse dependencies of the resolved file
            f_path = Path(defining_file).resolve()
            try:
                content_clean = get_expanded_content(f_path)

                # Find instantiations (handling both parameterized with '#' and unparameterized)
                insts = re.findall(r'\b([a-zA-Z_0-9]+)\s*#\s*\(', content_clean)
                insts.extend(re.findall(r'\b([a-zA-Z_0-9]+)\s+[a-zA-Z_0-9]+\s*\(', content_clean))
                # Find interface port declarations like REG_BUS.out reg_o
                insts.extend(re.findall(r'\b([a-zA-Z_0-9]+)\.[a-zA-Z_0-9]+\s+[a-zA-Z_0-9]+\b', content_clean))

                keywords = {'if', 'case', 'for', 'while', 'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'logic', 'wire', 'reg', 'bit', 'int', 'struct', 'typedef', 'enum', 'return', 'else', 'begin', 'end'}
                for inst in insts:
                    if inst not in visited and inst not in keywords:
                        queue.append(inst)

                # Find package imports and scope references (my_pkg::...)
                imports = re.findall(r'\bimport\s+([a-zA-Z_0-9]+)::', content_clean)
                imports.extend(re.findall(r'\b([a-zA-Z_0-9]+)::', content_clean))
                for imp in imports:
                    if imp not in visited:
                        queue.append(imp)
            except Exception:
                pass

    sys.stdout.write(f"\r  -> Tracing active dependencies: Done! ({len(needed_files)} active files resolved)     \n")
    sys.stdout.flush()
    return needed_files


def generate_stubs(outdir_path: Path, soc_config, env_dependencies, base_dir: Path, fast_check_tool: str = "questa"):
    """
    Generates 'faithful' black-box stubs for external IPs for fast compilation.
    It extracts the exact module signature (parameters and ports) to validate
    the connectivity without compiling the full implementation.

    This approach drastically reduces structural verification time (from minutes
    to seconds) because it avoids analyzing/elaborating complex internal logic,
    allowing developers to quickly check if the Top-Level wiring generated by
    Ollivander is syntactically and dimensionally correct.
    """


    def is_fast_compile_target(p_clean, outdir_path, bld_dir=None):
        """
        Evaluates whether a given source file should be kept intact during a fast compile,
        or if its contents should be replaced by a stub.
        We want to compile ONLY the top-level structure, while dropping the RTL
        implementation of all leaves to maximize speed.
        """
        # Always keep generated files (like packages or top-level) and headers intact
        if outdir_path.name in p_clean or p_clean.endswith('.svh'):
            return True

        # Compile infrastructure primitives completely to avoid stubbing issues
        if 'infrastructure' in p_clean:
            return True

        # Compile pad reference/behavioral models completely (unless using Verilator)
        if ('components/padframe' in p_clean or 'components/padframes' in p_clean) and fast_check_tool != 'verilator':
            return True

        # External testbench files are not required for structural SoC elaboration.
        if 'bender_work' in p_clean and re.search(r'/(?:test|tests|tb)/', p_clean, re.IGNORECASE):
            return False

        # Resolve the actual file path
        if p_clean.startswith('$ROOT'):
            p_path = Path(p_clean.replace('$ROOT', '.')).resolve()
        else:
            p_path = Path(p_clean).resolve()
            if not p_path.exists() and bld_dir and (bld_dir / p_path).exists():
                p_path = (bld_dir / p_path).resolve()

        try:
            # Read and sanitize file content
            c = p_path.read_text(encoding='utf-8', errors='ignore')
            c_clean = strip_comments(c)

            c_clean = re.sub(r'"[^"]*"', '', c_clean) # Ignore string literals

            # Verilator cannot elaborate constant unpacked structs, so we stub any files defining them
            if fast_check_tool == 'verilator' and re.search(r'\blocalparam\s+[a-zA-Z_0-9]+\s+[a-zA-Z_0-9]+\s*=\s*\'{', c_clean):
                return False

            # If the file contains a module/interface wrapper/etc. that we want to stub, we do not compile it completely.
            # (We will extract any packages/interfaces defined inside it during stub generation).
            if re.search(r'\b(?:module|macromodule|program)\b', c_clean):
                return False

            # If the file only defines a package or an interface (no module), keep it completely.
            if re.search(r'\b(?:package|interface)\s+[a-zA-Z_0-9]+', c_clean):
                return True

            # If the file does not contain any module, macromodule, or program, keep it intact
            if not re.search(r'\b(?:module|macromodule|program)\b', c_clean):
                return True
        except Exception:
            # If we cannot read or resolve the file (e.g., due to env vars in the path),
            # keep it intact and let QuestaSim handle it.
            return True

        # Default behavior: replace with a stub
        return False

    def parse_struct_literal(body):
        fields = {}
        brace_depth = 0
        current_token = []
        tokens = []
        for c in body:
            if c == '{':
                brace_depth += 1
            elif c == '}':
                brace_depth -= 1

            if c == ',' and brace_depth == 0:
                tokens.append("".join(current_token).strip())
                current_token = []
            else:
                current_token.append(c)
        if current_token:
            tokens.append("".join(current_token).strip())

        for token in tokens:
            if not token:
                continue
            parts = token.split(':', 1)
            if len(parts) == 2:
                field = parts[0].strip()
                val = parts[1].strip()
                fields[field] = val
        return fields

    def decompose_struct_params(stubs_content):
        # Split stubs_content into blocks of package/module/interface
        blocks = []
        pos = 0
        pattern = r'\b(?P<block_type>package|module|interface)\s+(?P<block_name>[a-zA-Z_0-9]+)\b.*?\b(endpackage|endmodule|endinterface)\b'
        for match in re.finditer(pattern, stubs_content, re.DOTALL):
            start, end = match.start(), match.end()
            if start > pos:
                blocks.append((stubs_content[pos:start], None, None))
            blocks.append((stubs_content[start:end], match.group('block_type'), match.group('block_name')))
            pos = end
        if pos < len(stubs_content):
            blocks.append((stubs_content[pos:], None, None))

        # Global phase 1: Identify all localparam names and their parent packages
        name_to_pkg = dict(global_name_to_pkg)
        decl_names = set()
        for block_text, b_type, b_name in blocks:
            if b_type == 'package':
                for match in re.finditer(r'\blocalparam\s+[a-zA-Z_0-9_:]+\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*\'\{', block_text):
                    name = match.group('name')
                    name_to_pkg[name] = b_name
                    decl_names.add(name)
                for match in re.finditer(r'\blocalparam\s+[a-zA-Z_0-9_:]+\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*[a-zA-Z_0-9_:]+\s*;', block_text):
                    name = match.group('name')
                    name_to_pkg[name] = b_name
                    decl_names.add(name)

        # Identify which names are accessed via .field anywhere in the file
        decomposed_names = set()
        for name in decl_names:
            if fast_check_tool == "verilator":
                decomposed_names.add(name)
            else:
                pkg = name_to_pkg.get(name)
                if pkg:
                    pattern_access = r'\b(?:' + re.escape(pkg) + r'\s*::\s*)?' + re.escape(name) + r'\s*\.\s*[a-zA-Z_0-9]+\b'
                    if re.search(pattern_access, stubs_content):
                        decomposed_names.add(name)

        # Propagate backwards globally
        added = True
        while added:
            added = False
            for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<parent>[a-zA-Z_0-9_:]+)\s*;', stubs_content):
                name = match.group('name')
                parent = match.group('parent')
                parent_base = parent.split('::')[-1]
                if name in decomposed_names and parent_base not in decomposed_names:
                    if parent_base in decl_names:
                        decomposed_names.add(parent_base)
                        added = True

        # Global phase 2: Collect struct fields and decompose per block
        # global_struct_fields is pre-populated at the generate_stubs level
        commented_out_names = set()
        new_blocks = []
        for block_text, b_type, b_name in blocks:
            if b_type == 'package':
                decomposed_block = decompose_block_struct_params(block_text, global_struct_fields, decomposed_names, b_name, name_to_pkg, commented_out_names)
                new_blocks.append(decomposed_block)
            else:
                new_blocks.append(block_text)

        # Assemble stubs_content back
        stubs_content = "".join(new_blocks)

        # Global phase 3: Replace all member accesses globally using the unique names!
        for name in decomposed_names:
            pkg = name_to_pkg[name]
            unique_name = f"{pkg}_{name}"
            # Match pkg::name.field
            stubs_content = re.sub(
                re.escape(pkg) + r'\s*::\s*' + re.escape(name) + r'\s*\.\s*([a-zA-Z_0-9]+)\b',
                rf'{pkg}::{unique_name}_\1',
                stubs_content
            )

        # Now replace name.field inside their respective packages
        blocks_phase3 = []
        pos = 0
        for match in re.finditer(pattern, stubs_content, re.DOTALL):
            start, end = match.start(), match.end()
            if start > pos:
                blocks_phase3.append((stubs_content[pos:start], None, None))
            blocks_phase3.append((stubs_content[start:end], match.group('block_type'), match.group('block_name')))
            pos = end
        if pos < len(stubs_content):
            blocks_phase3.append((stubs_content[pos:], None, None))

        new_blocks_phase3 = []
        for block_text, b_type, b_name in blocks_phase3:
            if b_type == 'package':
                for name in decomposed_names:
                    if name_to_pkg[name] == b_name:
                        unique_name = f"{b_name}_{name}"
                        # Match name.field without package prefix
                        block_text = re.sub(
                            r'\b' + re.escape(name) + r'\s*\.\s*([a-zA-Z_0-9]+)\b',
                            rf'{unique_name}_\1',
                            block_text
                        )
            new_blocks_phase3.append(block_text)

        stubs_content = "".join(new_blocks_phase3)

        # Global phase 4: Under Verilator, replace any module/interface parameters of struct types
        if fast_check_tool == "verilator":
            decl_replacements = []
            for match in re.finditer(r'\bparameter\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<default>[a-zA-Z_0-9_:]+)', stubs_content):
                p_name = match.group('name')
                p_default = match.group('default').split('::')[-1]
                if p_default in global_struct_fields:
                    decl_replacements.append((match.start(), match.end(), p_name, p_default))

            # Apply parameter declaration replacements from back to front
            decl_replacements.sort(key=lambda x: x[0], reverse=True)
            for start, end, p_name, p_default in decl_replacements:
                stubs_content = stubs_content[:start] + f"parameter int {p_name} = 0" + stubs_content[end:]
                
                # Replace accesses for this specific parameter
                fields = global_struct_fields[p_default]
                for field, val in fields.items():
                    stubs_content = re.sub(
                        r'\b' + re.escape(p_name) + r'\s*\.\s*' + re.escape(field) + r'\b',
                        val,
                        stubs_content
                    )

        return stubs_content

    def decompose_block_struct_params(block_text, global_struct_fields, decomposed_names, b_name, name_to_pkg, commented_out_names):
        decl_names_in_block = {n for n, p in name_to_pkg.items() if p == b_name}
        block_decomposed = decomposed_names & decl_names_in_block

        struct_decls = []
        for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*\'\{', block_text):
            name = match.group('name')
            if name in block_decomposed:
                start_idx = match.start()
                brace_depth = 0
                idx = match.end() - 1
                end_idx = -1
                while idx < len(block_text):
                    c = block_text[idx]
                    if c == '{':
                        brace_depth += 1
                    elif c == '}':
                        brace_depth -= 1
                    elif c == ';' and brace_depth == 0:
                        end_idx = idx + 1
                        break
                    idx += 1
                if end_idx != -1:
                    full_match = block_text[start_idx:end_idx]
                    struct_decls.append((start_idx, end_idx, match.group('type'), name, full_match))

        assign_decls = []
        for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<parent>[a-zA-Z_0-9_:]+)\s*;', block_text):
            name = match.group('name')
            if name in block_decomposed:
                assign_decls.append((match.start(), match.end(), match.group('type'), name, match.group('parent'), match.group(0)))

        struct_fields = {}
        replacements = []

        for start, end, type_name, name, full_text in struct_decls:
            body_match = re.search(r'=\s*\'\{(.*)\}\s*;', full_text, re.DOTALL)
            if body_match:
                body = body_match.group(1)
                fields = parse_struct_literal(body)
                struct_fields[name] = fields
                global_struct_fields[name] = fields

                # Check if the struct has nested struct/array literals '{
                has_nested = "'{" in body
                is_packed = type_name.split('::')[-1] in packed_types
                if has_nested or (fast_check_tool == "verilator" and not is_packed):
                    decomposed = [f"// {line}" for line in full_text.splitlines()]
                    commented_out_names.add(name)
                else:
                    decomposed = [full_text]

                unique_name = f"{b_name}_{name}"
                for field, val in fields.items():
                    # Skip decomposing fields that contain '{ to avoid LOGIC_IMPLICIT errors
                    if "'{" not in val:
                        decomposed.append(f"  localparam {unique_name}_{field} = {val};")
                new_text = "\n".join(decomposed)
                replacements.append((start, end, new_text))

        for start, end, type_name, name, parent, full_text in assign_decls:
            parent_base = parent.split('::')[-1]
            if parent_base in global_struct_fields:
                fields = global_struct_fields[parent_base]
                struct_fields[name] = fields
                global_struct_fields[name] = fields

                # If the parent was commented out, we must comment out the child
                parent_commented = parent_base in commented_out_names
                is_packed = type_name.split('::')[-1] in packed_types
                if parent_commented or (fast_check_tool == "verilator" and not is_packed):
                    decomposed = [f"// {line}" for line in full_text.splitlines()]
                    commented_out_names.add(name)
                else:
                    decomposed = [full_text]

                parent_pkg = name_to_pkg.get(parent_base)
                unique_name = f"{b_name}_{name}"
                for field in fields:
                    parent_val = fields[field]
                    if "'{" not in parent_val:
                        # Use parent_val directly if the parent package is external (not b_name)
                        # otherwise use the local decomposed parameter name
                        if parent_pkg and parent_pkg != b_name:
                            val_str = parent_val
                            if parent_pkg and not val_str.startswith(f"{parent_pkg}::") and re.match(r'^[a-zA-Z_][a-zA-Z_0-9]*$', val_str):
                                val_str = f"{parent_pkg}::{val_str}"
                            decomposed.append(f"  localparam {unique_name}_{field} = {val_str};")
                        else:
                            parent_pkg_prefix = f"{parent_pkg}::" if parent_pkg else ""
                            parent_unique = f"{parent_pkg}_{parent_base}" if parent_pkg else parent_base
                            decomposed.append(f"  localparam {unique_name}_{field} = {parent_pkg_prefix}{parent_unique}_{field};")
                new_text = "\n".join(decomposed)
                replacements.append((start, end, new_text))
        # Phase 3: Comment out any other localparam declarations that reference commented out names
        # under Verilator
        if fast_check_tool == "verilator":
            added = True
            while added:
                added = False
                for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<expr>[^;]+);', block_text):
                    name = match.group('name')
                    expr = match.group('expr')
                    if name not in commented_out_names:
                        for c_name in commented_out_names:
                            if re.search(r'\b' + re.escape(c_name) + r'\b', expr):
                                start, end = match.start(), match.end()
                                overlap = False
                                for r_start, r_end, _ in replacements:
                                    if not (end <= r_start or start >= r_end):
                                        overlap = True
                                        break
                                if not overlap:
                                    full_text = match.group(0)
                                    new_text = "\n".join(f"// {line}" for line in full_text.splitlines())
                                    replacements.append((start, end, new_text))
                                commented_out_names.add(name)
                                added = True
                                break

        replacements.sort(key=lambda x: x[0], reverse=True)
        for start, end, new_text in replacements:
            block_text = block_text[:start] + new_text + block_text[end:]

        return block_text

    project_name = soc_config.project.name
    hw_dir = outdir_path / "hw"
    stubs_dir = outdir_path / ".stubs"
    if stubs_dir.exists():
        import shutil
        for child in stubs_dir.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except Exception as e:
                print(f"[WARNING] Could not clean stale stub '{child.name}': {e}")
    stubs_dir.mkdir(exist_ok=True)

    # 1. Discover target boundary modules from our generated files
    # We consider all files generated by Ollivander and the basic infrastructure
    # to figure out which modules are missing (i.e. instantiated but not defined).
    our_files = list(hw_dir.rglob("*.sv"))

    infra_dir = base_dir / "components" / "infrastructure"
    if infra_dir.exists():
        our_files.extend(list(infra_dir.glob("*.sv")))

    defined_modules = set()
    inst_modules = set()

    # Scan generated code to build a list of all instantiated modules
    for f in our_files:
        if 'stubs.sv' in f.name: continue
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            # Strip strings and comments to avoid false positive matches
            clean = strip_comments(content)


            # Track declared modules
            for m in re.finditer(r'\bmodule\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', clean):
                defined_modules.add(m.group(1))

            # Track instantiated modules (handling both parameterized with '#' and unparameterized)
            for m in re.finditer(r'\b([a-zA-Z_0-9]+)\s*#\s*\(', clean):
                inst_modules.add(m.group(1))
            for m in re.finditer(r'\b([a-zA-Z_0-9]+)\s+[a-zA-Z_0-9]+\s*\(', clean):
                inst_modules.add(m.group(1))
            # Track interface port declarations like REG_BUS.out reg_o
            for m in re.finditer(r'\b([a-zA-Z_0-9]+)\.[a-zA-Z_0-9]+\s+[a-zA-Z_0-9]+\b', clean):
                inst_modules.add(m.group(1))
        except Exception:
            pass

    # 2. Extract paths from the Bender-generated compile script
    # We use the standard QuestaSim compile script generated by Bender to locate
    # the actual source files of the external dependencies in the workspace.
    tcl_path = outdir_path / "compile_vsim.tcl"
    if not tcl_path.exists():
        print(f"[ERROR] {tcl_path} not found. Ensure 'make prep-sim' ran successfully.")
        sys.exit(1)

    # Read and clean the TCL script, merging lines broken by the continuation character '\'
    tcl_code = tcl_path.read_text(encoding='utf-8')
    tcl_code_clean = re.sub(r'\\\s*\n', ' ', tcl_code)

    sv_files = []
    global_options = []
    seen_defines = set()
    for line in tcl_code_clean.split('\n'):
        if 'vlog ' in line: # Process only QuestaSim compilation commands
            for p in line.split():
                p_raw = p.strip('\"\'')

                # Extract and store include directories to pass them to the fast-compile
                if p_raw.startswith('+incdir+'):
                    if p not in global_options:
                        global_options.append(p)
                # Extract and store macro definitions, ensuring no duplicates by name
                elif p_raw.startswith('+define+'):
                    def_name = p_raw.split('+')[2].split('=')[0]
                    if def_name not in seen_defines:
                        seen_defines.add(def_name)
                        global_options.append(p)

                # Resolve paths containing the $ROOT environment variable (used by Bender)
                p_clean = p_raw.replace('$ROOT', '.')
                p_path = Path(p_clean).resolve()
                # Collect standalone SystemVerilog/Verilog source files
                if (p_clean.endswith('.sv') or p_clean.endswith('.v')) and p_path.exists():
                    sv_files.append(str(p_path))
                # Parse file lists (.bld, .f, .F) and collect the source files listed inside
                elif p_clean.endswith('.bld') or p_clean.endswith('.f') or p_clean.endswith('.F'):
                    try:
                        bld_path = Path(p_clean.replace('$ROOT', '.'))
                        bld_content = bld_path.read_text(encoding='utf-8')
                        for bp in bld_content.split():
                            bp_clean = bp.strip('\"\'')
                            if (bp_clean.endswith('.sv') or bp_clean.endswith('.v')) and not bp_clean.startswith('+'):
                                if bp_clean.startswith('$ROOT'):
                                    bp_path = Path(bp_clean.replace('$ROOT', '.'))
                                else:
                                    bp_path = Path(bp_clean)
                                    # Fallback: check if the path is relative to the file list's directory
                                    if not bp_path.exists() and (bld_path.parent / bp_path).exists():
                                        bp_path = bld_path.parent / bp_path
                                if bp_path.exists():
                                    sv_files.append(str(bp_path))
                    except Exception:
                        pass
    # Pre-scan all SystemVerilog files in the compile list to discover struct fields, package definitions, and packed types
    global_struct_fields = {}
    global_name_to_pkg = {}
    packed_types = set()

    total_scan = len(sv_files)
    from core.utils import draw_progress_bar
    for idx, path in enumerate(sv_files):
        try:
            p_clean = path.strip('\"\'').replace('$ROOT', '.')
            draw_progress_bar(idx + 1, total_scan, prefix="  -> Pre-scanning SystemVerilog files", suffix=f"({idx+1}/{total_scan})")
            p_path = Path(p_clean)
            if not p_path.is_file():
                continue
            content = p_path.read_text(encoding='utf-8', errors='ignore')
            content_clean = strip_comments(content)
            
            # Parse packed typedefs
            for match in re.finditer(r'\btypedef\s+struct\s+packed\b.*?\b\s*;', content_clean, re.DOTALL):
                full_text = match.group(0)
                brace_depth = 0
                idx = match.start()
                end_idx = -1
                while idx < len(content_clean):
                    c = content_clean[idx]
                    if c == '{': brace_depth += 1
                    elif c == '}': brace_depth -= 1
                    elif c == ';' and brace_depth == 0:
                        end_idx = idx + 1
                        break
                    idx += 1
                if end_idx != -1:
                    typedef_text = content_clean[match.start():end_idx]
                    parts = typedef_text.split('}')
                    if len(parts) > 1:
                        type_name = parts[-1].strip().replace(';', '').strip().split()[-1].strip()
                        packed_types.add(type_name)
            
            # 1. Parse package definitions and their localparams
            for pkg_match in re.finditer(r'\bpackage\s+(?P<pkg_name>[a-zA-Z_0-9]+)\b.*?\bendpackage\b', content_clean, re.DOTALL):
                pkg_name = pkg_match.group('pkg_name')
                pkg_text = pkg_match.group(0)
                
                for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*\'\{', pkg_text):
                    name = match.group('name')
                    start_idx = match.start()
                    brace_depth = 0
                    idx = match.end() - 1
                    end_idx = -1
                    while idx < len(pkg_text):
                        c = pkg_text[idx]
                        if c == '{': brace_depth += 1
                        elif c == '}': brace_depth -= 1
                        elif c == ';' and brace_depth == 0:
                            end_idx = idx + 1
                            break
                        idx += 1
                    if end_idx != -1:
                        full_match = pkg_text[start_idx:end_idx]
                        body_match = re.search(r'=\s*\'\{(.*)\}\s*;', full_match, re.DOTALL)
                        if body_match:
                            fields = parse_struct_literal(body_match.group(1))
                            global_struct_fields[name] = fields
                            global_name_to_pkg[name] = pkg_name

                for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<parent>[a-zA-Z_0-9_:]+)\s*;', pkg_text):
                    name = match.group('name')
                    parent = match.group('parent')
                    global_name_to_pkg[name] = pkg_name

            # 2. Parse global/module scope struct literals
            for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*\'\{', content_clean):
                name = match.group('name')
                start_idx = match.start()
                brace_depth = 0
                idx = match.end() - 1
                end_idx = -1
                while idx < len(content_clean):
                    c = content_clean[idx]
                    if c == '{': brace_depth += 1
                    elif c == '}': brace_depth -= 1
                    elif c == ';' and brace_depth == 0:
                        end_idx = idx + 1
                        break
                    idx += 1
                if end_idx != -1:
                    full_match = content_clean[start_idx:end_idx]
                    body_match = re.search(r'=\s*\'\{(.*)\}\s*;', full_match, re.DOTALL)
                    if body_match:
                        fields = parse_struct_literal(body_match.group(1))
                        if name not in global_struct_fields or len(fields) > len(global_struct_fields[name]):
                            global_struct_fields[name] = fields
        except Exception:
            pass

    # Transitive propagation of struct fields across assignments
    propagated = True
    pass_idx = 1
    while propagated:
        propagated = False
        total_prop = len(sv_files)
        for idx, path in enumerate(sv_files):
            draw_progress_bar(idx + 1, total_prop, prefix=f"  -> Propagating structs (Pass {pass_idx})    ", suffix=f"({idx+1}/{total_prop})")
            try:
                p_clean = path.strip('\"\'').replace('$ROOT', '.')
                p_path = Path(p_clean)
                if not p_path.is_file():
                    continue
                content = p_path.read_text(encoding='utf-8', errors='ignore')
                content_clean = strip_comments(content)
                for match in re.finditer(r'\blocalparam\s+(?P<type>[a-zA-Z_0-9_:]+)\s+(?P<name>[a-zA-Z_0-9]+)\s*=\s*(?P<parent>[a-zA-Z_0-9_:]+)\s*;', content_clean):
                    name = match.group('name')
                    parent = match.group('parent')
                    parent_base = parent.split('::')[-1]
                    if parent_base in global_struct_fields and name not in global_struct_fields:
                        global_struct_fields[name] = global_struct_fields[parent_base]
                        propagated = True
            except Exception:
                pass
        pass_idx += 1

    # 2b. Also include modules/interfaces defined and instantiated in files that are compiled completely (fast compile targets)
    # This prevents us from generating stubs for modules that we are already compiling completely,
    # AND ensures we stub any modules instantiated inside these compiled files!
    total_hier = len(sv_files)
    for idx, f in enumerate(sv_files):
        f_clean = f.strip('\"\'')
        draw_progress_bar(idx + 1, total_hier, prefix="  -> Analyzing module hierarchies    ", suffix=f"({idx+1}/{total_hier})")
        if is_fast_compile_target(f_clean, outdir_path):
            f_path = Path(f_clean.replace('$ROOT', '.'))
            if f_path.is_file():
                try:
                    content = f_path.read_text(encoding='utf-8', errors='ignore')
                    content_clean = strip_comments(content)

                    # Track declared modules
                    for m in re.findall(r'\bmodule\s+([a-zA-Z_0-9]+)\b', content_clean):
                        defined_modules.add(m)
                    for i in re.findall(r'\binterface\s+([a-zA-Z_0-9]+)\b', content_clean):
                        defined_modules.add(i)

                    # Track instantiated modules (handling both parameterized with '#' and unparameterized)
                    for m in re.finditer(r'\b([a-zA-Z_0-9]+)\s*#\s*\(', content_clean):
                        inst_modules.add(m.group(1))
                    for m in re.finditer(r'\b([a-zA-Z_0-9]+)\s+[a-zA-Z_0-9]+\s*\(', content_clean):
                        inst_modules.add(m.group(1))
                    # Track interface port declarations like REG_BUS.out reg_o
                    for m in re.finditer(r'\b([a-zA-Z_0-9]+)\.[a-zA-Z_0-9]+\s+[a-zA-Z_0-9]+\b', content_clean):
                        inst_modules.add(m.group(1))
                except Exception:
                    pass

    # Filter out SystemVerilog keywords that might have triggered the instantiation regex
    keywords = {'if', 'case', 'for', 'while', 'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'logic', 'wire', 'reg', 'bit', 'int', 'struct', 'typedef', 'enum', 'return', 'else', 'begin', 'end'}
    # The missing modules are those instantiated but not defined in our outputs or fast compile targets
    targets = (inst_modules - defined_modules) - keywords

    # Handle excludes and predefined stubs from the environment config
    # Some IPs (like complex memory macros or analog blocks) might need custom
    # predefined stubs or should be completely excluded from fast-check.
    excludes = set()
    fast_check_stubs = []
    for dep_info in env_dependencies.values():
        if "fast_check_exclude" in dep_info:
            excludes.update(dep_info["fast_check_exclude"])
        if "fast_check_stubs" in dep_info:
            fast_check_stubs.extend(dep_info["fast_check_stubs"])

    targets -= excludes

    # Resolve transitively active dependencies starting from top-level seeds early
    seeds = [project_name, f'{project_name}_chip']
    if fast_check_tool != 'verilator':
        seeds.append(f'tb_{project_name}')
    active_files = resolve_active_dependencies(sv_files, seeds, outdir_path, global_options, fast_check_tool)

    completely_compiled_names = set()
    total_active = len(active_files)
    for idx, f in enumerate(active_files):
        draw_progress_bar(idx + 1, total_active, prefix="  -> Pre-scanning active files       ", suffix=f"({idx+1}/{total_active})")
        try:
            if is_fast_compile_target(f, outdir_path):
                content_clean = strip_comments(Path(f).read_text(encoding='utf-8', errors='ignore'))
                for m in re.findall(r'\b(?:module|interface)\s+([a-zA-Z_0-9]+)\b', content_clean):
                    completely_compiled_names.add(m)
        except Exception:
            pass

    # 3. Extract exact signatures
    stubs_out = []
    stub_file_mapping = {}

    def filter_existing_includes(raw_includes, global_options):
        unique_includes = []
        for inc in sorted(list(set(raw_includes))):
            match = re.search(r'"([^"]+)"', inc)
            if not match:
                continue
            inc_match = match.group(1)
            # Exclude assertion headers as they cause macro redefinition conflicts
            if 'assert' in inc_match.lower():
                continue
            # Check if the included file actually exists in any of the search paths
            exists = False
            for opt in global_options:
                opt_str = opt.strip('\"\'')
                if opt_str.startswith('+incdir+'):
                    inc_dir = Path(opt_str[8:].replace('$ROOT', '.')).resolve()
                    if (inc_dir / inc_match).exists():
                        exists = True
                        break
            if exists:
                unique_includes.append(f'`include "{inc_match}"')
        return unique_includes

    def extract_from_path(path):
        """
        Scans a SystemVerilog source file for specific module definitions (targets).
        If found, it extracts the module signature (ports and parameters), relevant
        includes, and imports to generate a faithful black-box stub.
        """
        try:
            content = Path(path).read_text(encoding='utf-8', errors='ignore')
            clean_content = strip_comments(content)

            # Mask semicolons in import statements to prevent premature signature termination
            masked_content = re.sub(r'\bimport\s+[^;]+;', lambda m: m.group(0).replace(';', ' '), clean_content)
        except Exception:
            return ""

        # For every missing target module, check if it's defined in this file
        extracted = []
        for t in list(targets):
            if t in completely_compiled_names:
                continue
            pattern = r'\bmodule\s+' + re.escape(t) + r'\b'
            match = re.search(pattern, clean_content)
            if match:
                start_idx = match.start()
                paren_count = 0
                idx = start_idx
                in_string = False
                # Walk through the character array to find the closing semicolon of the module signature
                while idx < len(masked_content):
                    c = masked_content[idx]
                    if c == '"':
                        in_string = not in_string
                    elif not in_string:
                        # Keep track of parenthesis nesting to not mistake a semicolon inside parameters for the end
                        if c == '(': paren_count += 1
                        elif c == ')': paren_count -= 1
                        # If we find a semicolon at the root parenthesis level, the signature is complete
                        elif c == ';' and paren_count == 0:
                            sig = clean_content[start_idx:idx+1]

                            # Preserve type definitions by importing wildcards from preceding packages
                            head = clean_content[:start_idx]
                            imports = re.findall(r'\bimport\s+[^;]+;', head)
                            # Also grab imports inside the module signature
                            imports.extend(re.findall(r'\bimport\s+[^;]+;', sig))
                            wild_imports = {re.sub(r'::\s*[a-zA-Z_0-9]+', '::*', imp) for imp in imports}

                            # Preserve `include directives required by the signature, verifying they exist
                            raw_includes = re.findall(r'`include\s+"[^"]+"', head)
                            raw_includes.extend(re.findall(r'`include\s+"[^"]+"', sig))
                            unique_includes = filter_existing_includes(raw_includes, global_options)

                            # Assemble the final stub: Includes + Imports + Signature + endmodule
                            stub = "\n".join(unique_includes) + "\n" + "\n".join(sorted(list(wild_imports))) + "\n" + sig + "\nendmodule"
                            extracted.append(stub)
                            targets.remove(t)
                            break
                    idx += 1
        return "\n\n".join(extracted)

    def extract_packages_and_interfaces(path):
        extracted = []
        try:
            content = Path(path).read_text(encoding='utf-8', errors='ignore')
            clean_content = strip_comments(content)
            # Extract and preserve any packages defined in this file
            for pkg_match in re.finditer(r'\bpackage\s+[a-zA-Z_0-9]+\b.*?\bendpackage\b', clean_content, re.DOTALL):
                start_idx = pkg_match.start()
                head = clean_content[:start_idx]
                includes = re.findall(r'`include\s+"[^"]+"', head)
                unique_includes = filter_existing_includes(includes, global_options)
                imports = re.findall(r'\bimport\s+[^;]+;', head)

                pkg_code = ""
                if unique_includes:
                    pkg_code += "\n".join(unique_includes) + "\n"
                if imports:
                    pkg_code += "\n".join(imports) + "\n"
                pkg_code += pkg_match.group(0)
                extracted.append(pkg_code)

            # Extract and preserve any interfaces defined in this file
            for intf_match in re.finditer(r'\binterface\s+(?P<intf_name>[a-zA-Z_0-9]+)\b.*?\bendinterface\b', clean_content, re.DOTALL):
                intf_name = intf_match.group('intf_name')
                if intf_name in completely_compiled_names:
                    continue
                start_idx = intf_match.start()
                head = clean_content[:start_idx]
                includes = re.findall(r'`include\s+"[^"]+"', head)
                unique_includes = filter_existing_includes(includes, global_options)
                imports = re.findall(r'\bimport\s+[^;]+;', head)

                intf_code = ""
                if unique_includes:
                    intf_code += "\n".join(unique_includes) + "\n"
                if imports:
                    intf_code += "\n".join(imports) + "\n"
                intf_code += intf_match.group(0)
                extracted.append(intf_code)
        except Exception:
            pass
        return "\n\n".join(extracted)

    # Generate in-place stubs for each skipped file
    import hashlib
    total_stubs = len(sv_files)
    stubs_generated_count = 0
    for idx, path in enumerate(sv_files):
        f_clean = path.strip('\"\'').replace('$ROOT', '.')
        draw_progress_bar(idx + 1, total_stubs, prefix="  -> Extracting stubs                ", suffix=f"({idx+1}/{total_stubs})")
        p_path = Path(f_clean)
        p_abs = str(p_path.resolve())
        # Only generate stubs for active files
        if p_abs not in active_files:
            continue
        if not is_fast_compile_target(f_clean, outdir_path):
            p_abs = str(p_path.resolve())

            pkg_stub = extract_packages_and_interfaces(p_abs)
            mod_stub = extract_from_path(p_abs)

            combined_stub = ""
            if pkg_stub:
                combined_stub += pkg_stub + "\n\n"
            if mod_stub:
                combined_stub += mod_stub + "\n\n"

            if combined_stub.strip():
                path_hash = hashlib.md5(p_abs.encode('utf-8')).hexdigest()[:8]
                safe_name = f"{p_path.stem}_{path_hash}.sv"
                stub_file_path = stubs_dir / safe_name

                if fast_check_tool == "verilator":
                    combined_stub = decompose_struct_params(combined_stub)

                stub_file_path.write_text("// AUTO-GENERATED STUB FILE\n\n" + combined_stub, encoding='utf-8')
                stub_file_mapping[p_abs] = safe_name
                stubs_generated_count += 1

    # Fallback search for any remaining missing target stubs
    total_fallback = len(sv_files)
    for idx, path in enumerate(sv_files):
        if not targets: break
        draw_progress_bar(idx + 1, total_fallback, prefix="  -> Running fallback stub search    ", suffix=f"({idx+1}/{total_fallback})")
        mod_stub = extract_from_path(path)
        if mod_stub:
            stubs_out.append(mod_stub)

    if targets:
        # Fallback: if some targets are still missing (e.g. Bender didn't include them
        # in the main target), aggressively search all .sv files in the workspace.
        print(f"  [INFO] Fallback search in bender_work for missing stubs: {', '.join(targets)}")
        for path in Path('bender_work').rglob("*.sv"):
            if not targets: break
            if str(path) in sv_files: continue
            mod_stub = extract_from_path(path)
            if mod_stub:
                stubs_out.append(mod_stub)

    if "tc_pad_bidir" in targets:
        fast_check_stubs.append({
            "name": "padframe_stubs.sv",
            "content": """// Copyright 2026 Fondazione Chips-IT.
// SPDX-License-Identifier: Apache-2.0

package tc_pad_pkg;
  localparam V = 1;
  localparam H = 0;
  typedef struct packed {
    logic dummy;
  } tc_pad_config_t;
  localparam tc_pad_config_t gf22_invecas_tc_pad_config = '{dummy: 1'b0};
endpackage

`ifndef io_pad_internals
`define io_pad_internals dummy_int_io
`endif

module tc_pad_bidir #(
  parameter int tc_pad_orientation = 0,
  parameter tc_pad_config = 0
) (
  inout wire pad_io,
  output logic pad2chip_o,
  input logic input_en_i,
  input logic pu_en_i,
  input logic pd_en_i,
  input logic schmitt_en_i,
  input logic nand_in_i,
  output logic nand_out_o,
  input logic chip2pad_i,
  input logic output_en_i,
  input logic slew_en_i,
  input logic [1:0] drive_strength_i,
  inout wire int_io
);
  wire dummy_int_io;
endmodule
"""
        })
        if "tc_pad_bidir" in targets:
            targets.remove("tc_pad_bidir")

    if "can_top_apb" in targets:
        fast_check_stubs.append({
            "name": "can_top_apb_stub.sv",
            "content": """// Copyright 2026 Fondazione Chips-IT.
// SPDX-License-Identifier: Apache-2.0

module can_top_apb #(
  parameter int rx_buffer_size = 128,
  parameter int txt_buffer_count = 4,
  parameter bit sup_filtA = 0,
  parameter bit sup_filtB = 0,
  parameter bit sup_filtC = 0,
  parameter bit sup_range = 0,
  parameter bit sup_traffic_ctrs = 0,
  parameter bit sup_test_registers = 0,
  parameter int target_technology = 1
) (
  input  logic aclk,
  input  logic arstn,
  input  logic scan_enable,
  output logic res_n_out,
  output logic irq,
  output logic CAN_tx,
  input  logic CAN_rx,
  input  logic [63:0] timestamp,
  input  logic [31:0] s_apb_paddr,
  input  logic s_apb_penable,
  input  logic [2:0] s_apb_pprot,
  output logic [31:0] s_apb_prdata,
  output logic s_apb_pready,
  input  logic s_apb_psel,
  output logic s_apb_pslverr,
  input  logic [3:0] s_apb_pstrb,
  input  logic [31:0] s_apb_pwdata,
  input  logic s_apb_pwrite
);
endmodule
"""
        })
        targets.remove("can_top_apb")


    comment = get_generation_comment("//", base_dir)
    with open(stubs_dir / f"{project_name}_stubs.sv", "w") as f:
        stubs_content = "// AUTO-GENERATED STUBS FOR FAST-CHECK\n" + comment + "\n" + "\n\n".join(stubs_out)
        if fast_check_tool == "verilator":
            stubs_content = decompose_struct_params(stubs_content)
        f.write(stubs_content)

    for stub in fast_check_stubs:
        stub_content = stub["content"]
        if fast_check_tool == "verilator":
            stub_content = decompose_struct_params(stub_content)
        with open(stubs_dir / stub["name"], "w") as f:
            f.write("// AUTO-GENERATED STUB FILE\n" + comment + "\n" + stub_content)


    # (Active files were resolved early at the start of generate_stubs)

    # 4. Create compile_vsim_fast.tcl
    # Prepare the initial TCL commands for creating the work library
    # This new TCL script will be a clone of the Bender one, but it will omit
    # the compilation of all "stubbed" files, compiling our auto-generated
    # stubs file instead.
    fast_tcl = ['onerror {quit -code 1}', 'if {[file exists work]} { file delete -force work }', 'vlib work']
    tcl_code_clean = tcl_code_clean.replace('return 1', 'quit -code 1')
    verilator_files = []

    for line in tcl_code_clean.split('\n'):
        if 'vlog ' in line:
            new_tokens = []
            for p in line.split():
                p_clean = p.strip('\"\'')
                # Process standalone Verilog/SystemVerilog sources
                if (p_clean.endswith('.sv') or p_clean.endswith('.v')) and not p.startswith('+'):
                    p_resolved_abs = str(Path(p_clean.replace('$ROOT', '.')).resolve())
                    if is_fast_compile_target(p_clean, outdir_path):
                        if p_resolved_abs in active_files or 'generated/' in p_clean or 'components/infrastructure/' in p_clean:
                            new_tokens.append(p)
                            verilator_files.append(p_clean)
                    else:
                        if p_resolved_abs in stub_file_mapping:
                            if p_resolved_abs in active_files or 'generated/' in p_clean or 'components/infrastructure/' in p_clean:
                                stub_rel = f'"$ROOT/generated/.stubs/{stub_file_mapping[p_resolved_abs]}"'
                                new_tokens.append(stub_rel)
                                verilator_files.append(f'generated/.stubs/{stub_file_mapping[p_resolved_abs]}')
                # Process file lists and filter their contents to create '.fast' versions
                elif p_clean.endswith('.bld') or p_clean.endswith('.f') or p_clean.endswith('.F'):
                    try:
                        bld_path = Path(p_clean.replace('$ROOT', '.'))
                        bld_content = bld_path.read_text(encoding='utf-8')
                        bld_tokens = []
                        for bp in bld_content.split():
                            bp_clean = bp.strip('\"\'')
                            if (bp_clean.endswith('.sv') or bp_clean.endswith('.v')) and not bp.startswith('+'):
                                bp_resolved = bp_clean.replace('$ROOT', '.') if bp_clean.startswith('$ROOT') else bp_clean
                                if not Path(bp_resolved).exists() and (bld_path.parent / bp_resolved).exists():
                                    bp_resolved = str((bld_path.parent / bp_resolved).resolve())
                                bp_resolved_abs = str(Path(bp_resolved).resolve())

                                if is_fast_compile_target(bp_clean, outdir_path, bld_path.parent):
                                    if bp_resolved_abs in active_files or 'generated/' in bp_resolved or 'components/infrastructure/' in bp_resolved:
                                        bld_tokens.append(bp)
                                        verilator_files.append(bp_resolved)
                                else:
                                    if bp_resolved_abs in stub_file_mapping:
                                        if bp_resolved_abs in active_files or 'generated/' in bp_resolved or 'components/infrastructure/' in bp_resolved:
                                            stub_abs = stubs_dir / stub_file_mapping[bp_resolved_abs]
                                            try:
                                                rel_path = os.path.relpath(stub_abs, bld_path.parent).replace('\\', '/')
                                                bld_tokens.append(rel_path)
                                                verilator_files.append(f'generated/.stubs/{stub_file_mapping[bp_resolved_abs]}')
                                            except Exception:
                                                pass
                            else:
                                bld_tokens.append(bp)

                        if bld_tokens:
                            fast_bld_name = bld_path.stem + "_fast" + bld_path.suffix
                            fast_bld_path = bld_path.with_name(fast_bld_name)
                            fast_bld_path.write_text("\n".join(bld_tokens), encoding='utf-8')
                            new_tokens.append(p.replace(bld_path.name, fast_bld_name))
                    except Exception:
                        new_tokens.append(p)
                else:
                    new_tokens.append(p)

            # Check if there are still any sources left to compile in this line
            has_sources = False
            for t in new_tokens:
                tc = t.strip('\"\'')
                if (tc.endswith('.sv') or tc.endswith('.v') or tc.endswith('.bld') or tc.endswith('.f') or tc.endswith('.F')) and not tc.startswith('+'):
                    has_sources = True

            if has_sources:
                # Ensure the floo_noc package is compiled BEFORE the soc package if both are present
                noc_idx, soc_idx = -1, -1
                for i, t in enumerate(new_tokens):
                    if '_noc_pkg.sv' in t: noc_idx = i
                    elif '_soc_pkg.sv' in t: soc_idx = i
                if noc_idx != -1 and soc_idx != -1 and soc_idx < noc_idx:
                    new_tokens[soc_idx], new_tokens[noc_idx] = new_tokens[noc_idx], new_tokens[soc_idx]

                # Add the -suppress flag to suppress unnecessary warnings during the fast compile
                fast_line = ' '.join(new_tokens).replace('vlog ', 'vlog -suppress 13314,13233 ')
                fast_tcl.append(fast_line)
        else:
            fast_tcl.append(line)

    # Finally, append the compilation command for the generated stubs
    opts_str = " ".join(global_options)
    fast_tcl.append(f'vlog -suppress 13314,13233 {opts_str} -sv {outdir_path}/.stubs/{project_name}_stubs.sv')
    for stub in fast_check_stubs:
        fast_tcl.append(f'vlog -suppress 13314,13233 {opts_str} -sv {outdir_path}/.stubs/{stub["name"]}')

    comment_hash = get_generation_comment("#", base_dir)
    with open(outdir_path / "compile_vsim_fast.tcl", "w") as f:
        f.write(comment_hash + "\n" + '\n'.join(fast_tcl))

    # 5. Create compile_verilator_fast.f
    # We compile a Verilator argument file (.f) containing include paths,
    # macro definitions, and the subset of source files and stubs required
    # for a fast linting-only check.
    verilator_f = [
        '-sv',
        '--lint-only', # Only lint the design without generating C++ compilation targets
        '-Wall',
        '-Wno-fatal',  # Prevent stylistic lint warnings from breaking the fast-check build

        # Suppress specific non-critical warnings to avoid false-positive build failures:
        # - DECLFILENAME: Verilator warning when module name does not match filename.
        '-Wno-DECLFILENAME',
        # - PINCONNECTEMPTY: Warns on empty pin connections, which are acceptable for optional ports.
        '-Wno-PINCONNECTEMPTY',
        # - UNDRIVEN / UNUSED: Suppressed because stubs naturally leave ports undriven or unused.
        '-Wno-UNDRIVEN',
        '-Wno-UNUSED',
        # - VARHIDDEN: Warns when a variable hides another, which is common in third-party package imports.
        '-Wno-VARHIDDEN',
        # - IMPORTSTAR: Warns on wildcard package imports, which are standard in SystemVerilog.
        '-Wno-IMPORTSTAR',
        # - WIDTH: Verilator is very strict on width mismatches for constants or parameters, which are
        #   already checked dynamically by Ollivander's IR verify engine.
        '-Wno-WIDTH',
        # - PINMISSING: Suppressed because the IR verification engine already formally validates port existence
        #   and completeness. Verilator does not need to duplicate this check.
        '-Wno-PINMISSING',

        # - REDEFMACRO / DEFOVERRIDE: Suppressed because third-party IP dependencies (e.g., Pulpissimo, OpenTitan)
        #   sometimes define conflicting global macros. This is a pre-existing condition of the external IPs
        #   and not a bug in the generated SoC top-level.
        '-Wno-REDEFMACRO',
        '-Wno-DEFOVERRIDE',
        # - EOFNEWLINE: A purely cosmetic warning about missing newline at the end of files.
        '-Wno-EOFNEWLINE'
    ]

    # Prioritize the parent directories of all compiled files to ensure local relative includes
    # take precedence (e.g. resolving prim_assert.sv locally within opentitan/ip/prim/rtl instead of falling back to ibex)
    local_incdirs = []
    for f_path in verilator_files:
        f_clean = f_path.strip('\"\'').replace('$ROOT', '.')
        parent_dir = Path(f_clean).parent
        inc_str = f'+incdir+{parent_dir.resolve()}'
        if inc_str not in local_incdirs:
            local_incdirs.append(inc_str)
    verilator_f.extend(local_incdirs)

    # Add generated output directories to include paths to resolve relative include paths
    # inside generated files (e.g., referencing crux_regs.svh from testbenches)
    verilator_f.append(f'+incdir+{outdir_path.resolve()}/hw')
    verilator_f.append(f'+incdir+{outdir_path.resolve()}/tb')

    # Add global include directories and defines (resolving relative incdirs to absolute paths)
    for opt in global_options:
        opt_clean = opt.strip('\"\'').replace('$ROOT', '.')
        if opt_clean.startswith('+incdir+'):
            inc_path = opt_clean[8:]
            abs_inc = Path(inc_path).resolve()
            verilator_f.append(f'+incdir+{abs_inc}')
        else:
            verilator_f.append(opt_clean)

    # Add source files
    for f_path in verilator_files:
        f_clean = f_path.strip('\"\'').replace('$ROOT', '.')
        verilator_f.append(f_clean)

    # Add stubs
    verilator_f.append(f'{outdir_path.resolve()}/.stubs/{project_name}_stubs.sv')
    for stub in fast_check_stubs:
        verilator_f.append(f'{outdir_path.resolve()}/.stubs/{stub["name"]}')

    with open(outdir_path / "compile_verilator_fast.f", "w") as f:
        f.write(comment_hash + "\n" + '\n'.join(verilator_f))
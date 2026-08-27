# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import re
import sys
from pathlib import Path

import yaml


class UniqueKeySafeLoader(yaml.SafeLoader):
    """yaml.SafeLoader that refuses duplicate mapping keys.

    Plain safe_load silently keeps the LAST value of a duplicated key, which is never
    what the file means and disables the earlier entry without a trace: the spatz
    registry entry carried two 'pre_build_cmds' keys and one of its patch scripts
    stopped running the day the second was added. Used for every
    YAML file Ollivander owns - the dependency registry, the environment overlays and
    the SoC descriptions; files produced by other tools (Bender manifests and locks)
    keep the permissive loader, since their content is not ours to police.
    """

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key '{key}': the loader would silently keep only "
                    f"the last value, dropping every earlier one", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


def yaml_load_strict(stream):
    """yaml.safe_load with duplicate mapping keys refused (UniqueKeySafeLoader)."""
    return yaml.load(stream, Loader=UniqueKeySafeLoader)

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

def parse_addr_value(value):
    """One base address or size from the SoC description, as an int, honouring its notation.

    The guide documents these fields as 'Int/Hex', and YAML already turns 0x60000000 into an
    int, so a string arrives here only when the user quoted it - and then base 0 reads the
    prefix that was written. UNIFIED DELIBERATELY: the two places that used to resolve windows
    disagreed on a string of bare digits, one reading it as hexadecimal and the other as
    decimal, so 'base_addr: "60000000"' denoted two different addresses within one build. No
    project description writes one (checked across every example '*.yml' and '*.py'), which is
    what makes unifying on the user's own notation free rather than a behavioural change.
    """
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def instance_count(comp):
    """How many instances a component expands into, from its own placement declaration.

    Derived from the declaration rather than from the placement grid, so that the callers who
    only need the COUNT do not have to rebuild the grid first - four places used to compute it
    by walking that grid, each with its own copy of the arithmetic. A component with no
    placement is one instance, which is every crossbar component and the reason a list is
    meaningless there.
    """
    placement = getattr(comp, 'placement', None) or {}
    logical = placement.get('logical')
    if not logical:
        return 1
    items = logical if isinstance(logical, list) else [logical]
    total = 0
    for item in items:
        if 'box' in item:
            box = item['box']
            total += ((box['x_end'] - box['x_start'] + 1)
                      * (box['y_end'] - box['y_start'] + 1))
        else:
            total += 1
    return max(1, total)


def instance_coords(comp):
    """The mesh coordinates of a component's instances, in INSTANCE-INDEX order.

    The canonical enumeration of the whole generator: placement items in declaration order,
    and within a box x outer / y inner. FlooGen's own address map agrees with it - the eight
    L2 instances of the reference mesh land at (0,0)..(0,3) then (8,0)..(8,3), which is this
    order and not the other one - as do the control-group bit selects that index instances.

    Needed wherever an array has to be UNROLLED into individually addressed instances, since
    an unrolled endpoint must state the coordinate that the array form derived from a range.
    """
    placement = getattr(comp, 'placement', None) or {}
    logical = placement.get('logical')
    if not logical:
        return []
    items = logical if isinstance(logical, list) else [logical]
    coords = []
    for item in items:
        if 'box' in item:
            box = item['box']
            for x in range(box['x_start'], box['x_end'] + 1):
                for y in range(box['y_start'], box['y_end'] + 1):
                    coords.append((x, y))
        else:
            coords.append((item['x'], item['y']))
    return coords


def resolve_instance_windows(entry, num_instances):
    """Every instance's (base, size) window for one address range, resolved in ONE place.

    'base_addr' and 'size_per_instance' each accept a scalar or a list of per-instance values,
    and all four combinations mean something a design needs:

        base     size     layout
        scalar   scalar   contiguous, stride equal to the size - the original behaviour
        scalar   list     contiguous and PACKED: the stride varies, no holes
        list     scalar   placement given, depth uniform: holes allowed
        list     list     placement and depth independent - the reference design's map, whose
                          small tiles leave the upper half of their uniform slot unmapped

    Resolving here instead of at each of the fourteen consumers IS the safety argument of the
    feature: a consumer that kept recomputing 'base + i * size' would be silently wrong for
    every layout but the first, and silently wrong address maps are what this generator exists
    to prevent. Consumers ask for the window of an instance; they never derive it.

    A length that disagrees with the instance count raises rather than truncating. The schema
    refuses that case first, with a message that explains why (soc_schema.py); this is the
    backstop for the paths that bypass it, a hand-built Python description above all.
    """
    # Normalised entries carry their resolved windows and are returned verbatim: the
    # normalisation pass (soc_schema.normalize_address_ranges) collapses the declared lists so
    # that the many consumers wanting simply "the component's base" keep reading an integer,
    # and re-deriving from that collapsed scalar here would silently reinstate the uniform
    # layout it replaced.
    stored = entry.get('_windows')
    if stored:
        return [tuple(window) for window in stored]

    raw_base = entry.get('base_addr', 0)
    raw_size = entry.get('size_per_instance', entry.get('size', 0))
    count = max(1, int(num_instances))

    def as_list(raw, field):
        if not isinstance(raw, (list, tuple)):
            return None
        values = [parse_addr_value(v) for v in raw]
        if len(values) != count:
            raise ValueError(
                f"'{field}' declares {len(values)} values but the component expands into "
                f"{count} instance(s); a list must carry exactly one value per instance.")
        return values

    bases = as_list(raw_base, 'base_addr')
    sizes = as_list(raw_size, 'size_per_instance')
    if sizes is None:
        sizes = [parse_addr_value(raw_size)] * count

    if bases is not None:
        return list(zip(bases, sizes))

    # Scalar base: each instance starts where the previous one ended. With a scalar size that
    # is exactly 'base + i * size'; with a list of sizes it packs them, which is the case a
    # reader of the feature summary tends to mistake for the reference map.
    windows, addr = [], parse_addr_value(raw_base)
    for size in sizes:
        windows.append((addr, size))
        addr += size
    return windows


def component_span(entry, num_instances):
    """The single (base, size) rule that covers EVERY instance of one address range.

    What a decoder placed UPSTREAM of the component needs - Cheshire's external-region table
    above all, which decides whether an address leaves the host at all. One instance's size is
    the wrong answer there and used to be the answer given: accesses beyond instance 0 were
    swallowed by the host's internal DECERR slave, B response and all, leaving 15 of the 16
    mesh clusters unreachable.

    THE ARRAY'S FOOTPRINT, NOT THE LAST MAPPED BYTE. When the pitch between instances is
    uniform, the span runs to the end of the LAST INSTANCE'S SLOT even if that instance maps
    only part of it: the rule a decoder upstream needs is "this array lives here", and the
    holes are the component's own decode to answer. Ending the region at the last mapped byte
    instead produced a region of 0x780000 where the array occupies 0x800000 - a size that is
    not a power of two, describing hardware whose footprint is - and the host then stalled on
    traffic that had nothing to do with the memory (the symptom was the UART's
    transmitter-empty bit never setting, with the firmware spinning inside a print).

    Without a uniform pitch there is no slot to round up to, and the span is simply the extent
    of what is mapped.
    """
    windows = resolve_instance_windows(entry, num_instances)
    low = min(base for base, _ in windows)
    high = max(base + size for base, size in windows)

    bases = [base for base, _ in windows]
    strides = {bases[i + 1] - bases[i] for i in range(len(bases) - 1)}
    if len(strides) == 1:
        pitch = strides.pop()
        high = max(high, max(bases) + pitch)
    return low, high - low


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

# Tool keywords that turn a comment into a DIRECTIVE when they are its first
# word, mapped to the directives each tool actually recognises. Prose that starts
# with one of these is silently reinterpreted: a comment reading
# "// Verilator accepts it anyway, but ..." is read by Verilator as an unknown
# metacomment and stops the build - a failure whose message ("Unknown verilator
# comment") points at the sentence rather than at the mistake, which is why this
# has bitten repeatedly.
#
# The whitelist is deliberately the failure-loud direction: a NEW legitimate
# directive not listed here trips the guard immediately and is a one-line fix,
# whereas guessing that unknown words are directives would let prose through.
COMMENT_DIRECTIVE_WORDS = {
    "verilator": {
        "lint_off", "lint_on", "lint_save", "lint_restore", "tracing_off", "tracing_on",
        "coverage_off", "coverage_on", "coverage_block_off", "public", "public_flat",
        "public_flat_rd", "public_flat_rw", "public_on", "public_off", "isolate_assignments",
        "inline_module", "no_inline_module", "no_inline_task", "hier_block", "split_var",
        "sc_bv", "sformat", "systemc_clock", "timing_on", "timing_off", "forceable",
        "clocker", "no_clocker", "clock_enable",
    },
    "synopsys": {"translate_off", "translate_on", "full_case", "parallel_case",
                 "dc_script_begin", "dc_script_end", "async_set_reset", "template"},
    "synthesis": {"translate_off", "translate_on", "full_case", "parallel_case"},
    "pragma": {"translate_off", "translate_on", "protect", "reset", "coverage_off",
               "coverage_on", "synthesis_off", "synthesis_on"},
}

_COMMENT_HEAD = re.compile(
    r"(?://|/\*)\s*(" + "|".join(COMMENT_DIRECTIVE_WORDS) + r")\b[ \t]*([A-Za-z_0-9]*)",
    re.IGNORECASE)


def find_fake_tool_pragmas(content: str):
    """Comment lines that open with a tool keyword but are prose, not a directive.

    Returns [(line_number, tool, offending_text)]. Applied to every SystemVerilog
    file Ollivander writes or links, so a sentence that happens to begin with
    'Verilator' is refused at generation time - where the fix is obvious - rather
    than surfacing as a pragma error from a tool three phases later.
    """
    hits = []
    for number, line in enumerate(content.split("\n"), start=1):
        match = _COMMENT_HEAD.search(line)
        if not match:
            continue
        tool = match.group(1).lower()
        following = (match.group(2) or "").lower()
        if following in COMMENT_DIRECTIVE_WORDS[tool]:
            continue        # a genuine directive
        hits.append((number, tool, line.strip()))
    return hits


def assert_no_fake_tool_pragmas(file_path: Path, content: str):
    """Refuse to write SystemVerilog whose comments would be read as directives."""
    if file_path.suffix not in (".sv", ".svh", ".v", ".vh"):
        return
    hits = find_fake_tool_pragmas(content)
    if not hits:
        return
    print(f"\n[ERROR] {file_path}: comment(s) that a tool would read as a directive:")
    for number, tool, text in hits:
        print(f"    line {number}: {text}")
        print(f"      -> '{tool}' as the first word of a comment is a {tool} pragma. "
              f"Reword so the sentence does not start with it.")
    sys.exit(1)


def write_if_changed(file_path: Path, content: str):
    """
    Writes content to a file only if it differs from the existing content.
    This is extremely important for build systems like Make: by preserving the 
    modification timestamp of unchanged files, we avoid triggering unnecessary 
    recompilations of the RTL in downstream tools.
    """
    assert_no_fake_tool_pragmas(file_path, content)
    if file_path.is_file() and file_path.read_text(encoding="utf-8", errors="ignore") == content:
        return
    # Nested output targets (e.g. sim/sim.mk) are legitimate: create the
    # destination directory instead of requiring every caller to remember it.
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8", newline="\n")

def simplify_port_ranges(decl: str) -> str:
    """
    Simplifies arithmetic expressions inside square brackets in a port declaration string.
    E.g. '[2-1:0][1-1:0]' -> '[1:0][0:0]'
    """
    def evaluate_simple_arithmetic(expr: str) -> str:
        expr_clean = expr.strip()
        if not expr_clean:
            return expr
        # Allow only digits, basic arithmetic/bitwise operators, parentheses, and whitespace
        if re.match(r'^[0-9+\-*/%&|^~<>()\s]+$', expr_clean):
            try:
                val = eval(expr_clean)
                if isinstance(val, (int, float)):
                    return str(int(val))
            except Exception:
                # Returning the expression untouched IS this function's contract - it simplifies
                # what it can and leaves the rest alone - so the failure is not swallowed
                # information. The regex above already rejects anything holding an identifier, so
                # what reaches here is malformed arithmetic, which the caller must keep verbatim.
                pass
        return expr

    def replace_bracket(match):
        content = match.group(1)
        if ':' in content:
            parts = content.split(':', 1)
            p1 = evaluate_simple_arithmetic(parts[0])
            p2 = evaluate_simple_arithmetic(parts[1])
            return f"[{p1}:{p2}]"
        else:
            return f"[{evaluate_simple_arithmetic(content)}]"
            
    return re.sub(r'\[([^\]]+)\]', replace_bracket, decl)


class Spinner:
    """
    A lightweight, thread-based CLI spinner context manager to provide
    visual feedback for long-running operations.
    """
    def __init__(self, message="  -> Processing..."):
        self.message = message
        self.spinner_chars = ["|", "/", "-", "\\"]
        import threading
        self.stop_running = threading.Event()
        self.thread = None

    def _spin(self):
        import sys
        import time
        idx = 0
        while not self.stop_running.is_set():
            char = self.spinner_chars[idx]
            sys.stdout.write(f"\r{self.message} {char}")
            sys.stdout.flush()
            idx = (idx + 1) % len(self.spinner_chars)
            time.sleep(1.0)
        # Clear the spinner line
        import sys
        sys.stdout.write("\r" + " " * (len(self.message) + 4) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        import threading
        self.stop_running.clear()
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_running.set()
        if self.thread:
            self.thread.join()


def draw_progress_bar(iteration, total, prefix='', suffix='', length=30, fill='█'):
    """
    Draws a single-line progress bar with percentage and custom messages.
    """
    if total <= 0:
        return
    import sys
    
    # Throttle printing to avoid blocking stdout over high-latency SSH
    last_pct = getattr(draw_progress_bar, "_last_pct", -1)
    current_pct = int(100 * iteration // total)
    if iteration != 1 and iteration < total and current_pct == last_pct:
        return
    draw_progress_bar._last_pct = current_pct

    percent = f"{100 * (iteration / float(total)):.1f}"
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration >= total:
        draw_progress_bar._last_pct = -1
        sys.stdout.write('\n')
        sys.stdout.flush()


def get_ollivander_version():
    """
    Returns the centralized version string of the Ollivander generator.
    """
    try:
        from core.version import __version__
        return __version__
    except ImportError:
        return "0.0.1"


def get_ollivander_git_hash(base_dir=None):
    """
    Dynamically retrieves the Git hash of the Ollivander repository using git describe.
    Falls back to 'unknown' if git command is not available or errors out.
    """
    import subprocess
    import shutil
    from pathlib import Path
    
    if not shutil.which("git"):
        return "no-git"
        
    cwd = Path(__file__).parent.parent.parent
    if base_dir:
        cwd = Path(base_dir)
        
    try:
        res = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return res.stdout.strip()
        except Exception:
            return "unknown"


def get_generation_comment(prefix="//", base_dir=None):
    """
    Returns a blank line followed by a generation comment line:
    
    <prefix> Generated by Ollivander vX.Y.Z (git_hash)
    """
    version = get_ollivander_version()
    git_hash = get_ollivander_git_hash(base_dir)
    return f"\n{prefix} Generated by Ollivander v{version} ({git_hash})\n"

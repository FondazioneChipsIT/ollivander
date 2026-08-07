#!/usr/bin/env python
# Copyright 2026 Fondazione Chips-IT.
# Licensed under the Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""Emit SystemVerilog stubs for the VHDL entities of a Bender source list.

Invoked by the generated Makefile.sim (prep-sim-verilator) as:

    gen_vhdl_stubs.py <vhdl_list_file> <output_dir>

where <vhdl_list_file> holds one .vhd/.vhdl path per line (the .vhd lines of
`bender script flist`) and <output_dir> receives one <entity>.sv stub per
mappable entity.

Rationale: the tool behind the license-free flow has no VHDL front-end, and
bender's verilator script silently drops VHDL sources, so any VHDL entity
instantiated from SystemVerilog surfaces as MODMISSING. QuestaSim keeps
simulating the real mixed-language sources; the license-free leg links these
stubs instead - its one declared coverage loss (docs/getting_started.md,
section 8.3). A firmware that actually drives a stubbed block must run under
QuestaSim; stub outputs are tied low precisely so that such traffic hangs or
reads zero loudly instead of half-working.

Only the entity declaration is parsed - generics and ports - with the
conservative type mapping below, and deliberately with regular expressions
rather than a full VHDL parser: the only entities that matter are the roots a
SystemVerilog file instantiates, i.e. mixed-language boundaries, which can only
expose the scalar/vector types the SV<->VHDL boundary supports in the first
place (QuestaSim enforces the same restriction on the real sources). The
grammar this script accepts therefore coincides with the grammar the problem
admits; the limiting factor is the type MAPPING, which no parser removes.
Should a full front-end ever be warranted, pyGHDL (libghdl bindings) is the
mature choice - it arrives with the same GHDL provisioning that the
ghdl-yosys-plugin route of future_evolution_tasks.md section 5.1 needs anyway.

An entity using anything outside the mapping (custom package types,
unconstrained arrays) is skipped with a warning, and the downstream MODMISSING
keeps pointing at it; extend the mapping or write a manual stub in that case.
Ranges may reference generics textually (std_logic_vector(G-1 downto 0)
becomes logic [G-1:0], the generic being a parameter of the stub).

The output directory must stay outside every Bender-visible source tree: these
stubs exist only for the file list that names them explicitly.
"""

import re
import sys
from pathlib import Path

# VHDL scalar/vector types a stub can represent faithfully.
SCALAR_TYPES = {"std_logic", "std_ulogic", "bit"}
VECTOR_TYPES = {"std_logic_vector", "std_ulogic_vector", "unsigned", "signed", "bit_vector"}
GENERIC_TYPES = {
    "natural": "int unsigned",
    "positive": "int unsigned",
    "integer": "int",
    "boolean": "bit",
    "std_logic": "logic",
}
BOOL_LITERALS = {"true": "1'b1", "false": "1'b0", "'0'": "1'b0", "'1'": "1'b1"}

# A VHDL declaration may open with an object class keyword ('constant g : natural',
# 'signal p : in std_logic'); it is noise for the stub and must not end up in the name.
OBJECT_CLASS = re.compile(r"^\s*(?:constant|signal|variable)\s+", re.I)

# VHDL has no reserved-word clash with these, SystemVerilog does: an entity whose port
# or generic is named after one of them cannot be transcribed at all, and is skipped.
SV_KEYWORDS = {
    "input", "output", "inout", "wire", "logic", "reg", "module", "endmodule", "parameter",
    "localparam", "begin", "end", "assign", "always", "initial", "function", "task", "generate",
    "genvar", "if", "else", "case", "endcase", "default", "signed", "unsigned", "bit", "byte",
    "int", "integer", "real", "time", "type", "class", "package", "interface", "program",
    "return", "break", "continue", "force", "release", "disable", "event", "wait", "posedge",
    "negedge", "edge", "and", "or", "not", "xor", "nand", "nor", "xnor", "buf", "supply0",
    "supply1", "tri", "wand", "wor", "config", "cell", "instance", "library", "use", "do",
    "while", "for", "forever", "repeat", "static", "automatic", "const", "ref", "var",
}


def _strip_comments(text):
    return re.sub(r"--[^\n]*", "", text)


def _balanced(text, start):
    """Return the span of the parenthesized block opening at text[start] == '('."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i
    return None, None


def _map_range(rng):
    """'63 downto 0' -> '[63:0]', 'G-1 downto 0' -> '[G-1:0]', 'M to N' -> '[M:N]'."""
    m = re.match(r"^(.*?)\s+(downto|to)\s+(.*?)$", rng.strip(), re.I | re.S)
    if not m:
        return None
    left, _, right = (s.strip() for s in m.groups())
    return f"[{left}:{right}]"


def _split_decls(block):
    """Split a generic/port block into individual declarations, ';' at depth 0."""
    decls, depth, cur = [], 0, []
    for ch in block:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            decls.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        decls.append("".join(cur))
    return decls


def _parse_generic(decl):
    """'name : natural range 32 to 4098 := 128' -> ('int unsigned', 'name', '128')."""
    decl = OBJECT_CLASS.sub("", decl)
    m = re.match(r"^\s*([\w\s,]+?)\s*:\s*(\w+)(?:\s+range\b[^:=]*)?\s*(?::=\s*(.+?))?\s*$",
                 decl, re.S)
    if not m:
        return None
    names, vtype, default = m.group(1), m.group(2).lower(), m.group(3)
    if vtype not in GENERIC_TYPES:
        return None
    sv_type = GENERIC_TYPES[vtype]
    default = (default or "0").strip()
    default = BOOL_LITERALS.get(default.lower(), default)
    return [(sv_type, n.strip(), default) for n in names.split(",")]


def _parse_port(decl):
    """'a, b : in std_logic_vector(7 downto 0)' -> [('input', 'logic [7:0]', name)...]."""
    decl = OBJECT_CLASS.sub("", decl)
    m = re.match(r"^\s*([\w\s,]+?)\s*:\s*(in|out|inout)\s+(\w+)\s*(\(.*\))?\s*$",
                 decl, re.I | re.S)
    if not m:
        return None
    names, direction, vtype, rng = m.group(1), m.group(2).lower(), m.group(3).lower(), m.group(4)
    direction = {"in": "input", "out": "output", "inout": "inout"}[direction]
    if vtype in SCALAR_TYPES and not rng:
        sv_type = "logic"
    elif vtype in VECTOR_TYPES and rng:
        mapped = _map_range(rng.strip()[1:-1])
        if mapped is None:
            return None
        sv_type = f"logic {mapped}"
    else:
        return None
    return [(direction, sv_type, n.strip()) for n in names.split(",")]


def stub_for_entity(name, body, src):
    """Render the SV stub for one parsed entity, or None with a reason."""
    generics, ports = [], []
    gm = re.search(r"\bgeneric\s*\(", body, re.I)
    if gm:
        block, _ = _balanced(body, gm.end() - 1)
        if block is None:
            return None, "unbalanced generic block"
        for decl in _split_decls(block):
            parsed = _parse_generic(decl)
            if parsed is None:
                return None, f"unmappable generic '{decl.strip()[:50]}'"
            generics.extend(parsed)
    pm = re.search(r"\bport\s*\(", body, re.I)
    if pm:
        block, _ = _balanced(body, pm.end() - 1)
        if block is None:
            return None, "unbalanced port block"
        for decl in _split_decls(block):
            parsed = _parse_port(decl)
            if parsed is None:
                return None, f"unmappable port '{decl.strip()[:50]}'"
            ports.extend(parsed)

    clash = sorted({n for _, n, _ in generics} | {n for _, _, n in ports}
                   if generics or ports else set())
    clash = [n for n in clash if n.lower() in SV_KEYWORDS]
    if clash:
        return None, f"port/generic named after a SystemVerilog keyword ({', '.join(clash)})"

    lines = [
        f"// AUTO-GENERATED STUB - do not edit, do not compile under QuestaSim.",
        f"// Stands in for the VHDL entity '{name}' ({src}), which the license-free",
        f"// flow cannot compile (no VHDL front-end). Outputs are tied low so that any",
        f"// real traffic into this block fails loudly instead of half-working; the",
        f"// mixed-language QuestaSim flows keep simulating the true sources.",
        f"module {name}",
    ]
    if generics:
        lines.append("#(")
        lines.append(",\n".join(f"  parameter {t} {n} = {d}" for t, n, d in generics))
        lines.append(")")
    lines.append("(")
    lines.append(",\n".join(f"  {d} {t} {n}" for d, t, n in ports))
    lines.append(");")
    for d, _, n in ports:
        if d == "output":
            lines.append(f"  assign {n} = '0;")
    lines.append(f"endmodule : {name}")
    return "\n".join(lines) + "\n", None


def main():
    if len(sys.argv) != 3:
        print("usage: gen_vhdl_stubs.py <vhdl_list_file> <output_dir>")
        sys.exit(1)
    list_file, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    # Regenerate the whole set every run: a stale stub for an entity that left
    # the graph must not survive in the file list.
    for old in out_dir.glob("*.sv"):
        old.unlink()

    # Pass 1: collect every entity declaration, and every entity name the VHDL
    # side itself references (direct instantiation or component declaration).
    # Only the ROOTS - entities no other VHDL instantiates - are the boundary
    # SystemVerilog can see, and only they get a stub: the internals of a VHDL
    # subtree are unreachable once its root is stubbed, and emitting them would
    # only risk name collisions with same-named SV modules of the graph.
    entities, referenced = {}, set()
    for line in list_file.read_text(encoding="utf-8").splitlines():
        src = Path(line.strip())
        if not line.strip() or not src.is_file():
            continue
        text = _strip_comments(src.read_text(encoding="utf-8", errors="ignore"))
        for m in re.finditer(r"\bentity\s+(\w+)\s+is\b(.*?)\bend\b", text, re.I | re.S):
            entities.setdefault(m.group(1).lower(), (m.group(1), m.group(2), src.name))
        for m in re.finditer(r"\bentity\s+\w+\.(\w+)", text, re.I):
            referenced.add(m.group(1).lower())
        for m in re.finditer(r"\bcomponent\s+(\w+)", text, re.I):
            referenced.add(m.group(1).lower())

    emitted, skipped = [], 0
    for key in sorted(set(entities) - referenced):
        name, body, src_name = entities[key]
        stub, reason = stub_for_entity(name, body, src_name)
        if stub is None:
            print(f"  [WARNING] gen_vhdl_stubs: no stub for root entity '{name}' "
                  f"({src_name}): {reason}. If it is instantiated from SystemVerilog "
                  f"it will surface as MODMISSING; write a manual stub or extend the mapping.")
            skipped += 1
            continue
        (out_dir / f"{name}.sv").write_text(stub, encoding="utf-8")
        emitted.append(name)
    print(f"  -> gen_vhdl_stubs: {len(entities)} entities, "
          f"{len(entities) - len(set(entities) - referenced)} internal to the VHDL side, "
          f"{len(emitted)} root stubs emitted"
          + (f", {skipped} roots skipped" if skipped else "")
          + (f" ({', '.join(emitted)})" if emitted else ""))


if __name__ == "__main__":
    main()

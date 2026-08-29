# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
"""
SystemVerilog Intermediate Representation (IR) for top-level architectures.
Allows structured modeling and verification of module instances, signals, and port connections.
"""

import re

def eval_dim_size(dim_str: str) -> int:
    """
    Given a SystemVerilog dimension string (e.g. '[1:0]' or '[3:0][7:0]'),
    returns the total resolved bit-width. Returns -1 if it cannot be statically resolved.
    """
    total_width = 1
    dims = re.findall(r'\[([^\]]+)\]', dim_str)
    if not dims:
        return 1
    for d in dims:
        if ':' in d:
            parts = d.split(':', 1)
            try:
                val1 = int(eval(parts[0], {"__builtins__": {}}))
                val2 = int(eval(parts[1], {"__builtins__": {}}))
                total_width *= (abs(val1 - val2) + 1)
            except Exception:
                return -1
        else:
            try:
                val = int(eval(d, {"__builtins__": {}}))
                total_width *= val
            except Exception:
                return -1
    return total_width

def get_type_width(type_str: str) -> int:
    """
    Extracts the total bit-width of a SystemVerilog type string like 'logic [1:0]'.
    """
    type_str = type_str.strip()
    if not type_str:
        return 1
    type_clean = re.sub(r'\b(input|output|inout|logic|reg|wire|var)\b', '', type_str).strip()
    if not type_clean:
        return 1
    return eval_dim_size(type_clean)

def get_expr_width(expr: str, ir_signals: dict) -> int:
    """
    Estimates the bit-width of a connected expression, matching against registered TopSignals.
    Returns -2 for unsized constants ('0, '1), -1 for unresolved, or the positive width.
    """
    expr = expr.strip()
    if not expr:
        return 0
    if expr in ["'0", "'1", "0", "1"]:
        return -2  # Unsized constant

    # Handle concatenation e.g., {sig_a, sig_b}
    if expr.startswith('{') and expr.endswith('}'):
        parts = []
        depth = 0
        current = []
        for char in expr[1:-1]:
            if char in ['[', '{', '(']:
                depth += 1
            elif char in [']', '}', ')']:
                depth -= 1
            if char == ',' and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())

        total = 0
        for p in parts:
            p_w = get_expr_width(p, ir_signals)
            if p_w < 0:
                return -1
            total += p_w
        return total

    # Handle slice e.g., sig[3] or sig[1:0]
    m_slice = re.match(r'^([a-zA-Z0-9_]+)\s*\[([^\]]+)\]$', expr)
    if m_slice:
        sig_name = m_slice.group(1)
        slice_content = m_slice.group(2)
        if sig_name in ir_signals:
            if ':' in slice_content:
                parts = slice_content.split(':', 1)
                try:
                    val1 = int(eval(parts[0], {"__builtins__": {}}))
                    val2 = int(eval(parts[1], {"__builtins__": {}}))
                    return abs(val1 - val2) + 1
                except Exception:
                    return -1
            else:
                return 1
        return -1

    if expr in ir_signals:
        return ir_signals[expr].width

    return -1


class TopSignal:
    def __init__(self, name: str, sig_type: str = "logic", dimensions: str = ""):
        self.name = name
        self.sig_type = sig_type
        self.dimensions = dimensions
        self.width = get_type_width(f"{sig_type} {dimensions}")


class PortConnection:
    def __init__(self, port_name: str, expression: str):
        self.port_name = port_name
        self.expression = expression


class ModuleInstance:
    def __init__(self, inst_name: str, module_name: str):
        self.inst_name = inst_name
        self.module_name = module_name
        self.parameters = {}  # parameter_name -> value_string
        self.connections = []  # List of PortConnection


class SVArchitectureIR:
    def __init__(self):
        self.signals = {}  # signal_name -> TopSignal
        self.instances = {}  # instance_name -> ModuleInstance
        self.assignments = []  # List of tuple (lhs_string, rhs_string)

    def add_signal(self, name: str, sig_type: str = "logic", dimensions: str = ""):
        self.signals[name] = TopSignal(name, sig_type, dimensions)

    def add_instance(self, inst_name: str, module_name: str) -> ModuleInstance:
        inst = ModuleInstance(inst_name, module_name)
        self.instances[inst_name] = inst
        return inst

    def add_assignment(self, lhs: str, rhs: str):
        # Idempotent: a dual-role port can legitimately be discovered by BOTH the wiring
        # matrix and the exported-interface list, and two continuous assignments to one
        # logic are illegal even when identical.
        if (lhs, rhs) not in self.assignments:
            self.assignments.append((lhs, rhs))

    def verify(self, comp_info: dict) -> list:
        """
        Performs structural verification.
        Returns a list of error/warning strings.
        """
        messages = []

        # ------------------------------------------------------------------
        # 0. Every consumed interrupt wire must have a driver (SafeConnect
        #    class guard, 2026-08-29). An 'intr_*' wire read by a vector or an
        #    input port but never driven elaborates perfectly and reads X (or 0
        #    under two-state) forever: the CAN event spent months routed to a
        #    PLIC bit that could not fire, invisible to every simulator and to
        #    slang alike, because nothing here says a wire OUGHT to be driven -
        #    that knowledge lives in the description, so it is enforced here.
        # ------------------------------------------------------------------
        intr_driven, intr_consumed = set(), set()
        _IDENT = re.compile(r"\bintr_[a-zA-Z0-9_]+\b")
        for lhs, rhs in self.assignments:
            intr_driven.update(_IDENT.findall(lhs))
            intr_consumed.update(_IDENT.findall(rhs))
        for inst_name, inst in self.instances.items():
            comp_name = inst_name[2:] if inst_name.startswith("i_") else inst_name
            c_ports = comp_info.get(comp_name, {}).get("ports", {})
            for conn in inst.connections:
                names = _IDENT.findall(conn.expression)
                if not names:
                    continue
                direction = (c_ports.get(conn.port_name) or {}).get("dir", "")
                (intr_driven if direction == "output" else intr_consumed).update(names)
        # Only SOURCE wires ('intr_<comp>_<port>_o') are judged here: destination vectors
        # ('..._i', '..._sync') are driven by the top template's own combinational block and
        # its sync cells, which the IR cannot see - including them produced five false
        # positives on the first run. The orphan class this guard exists for is precisely a
        # source wire (the CAN event was 'intr_apb_subsystem_can_bus_event_o').
        for w in sorted(intr_consumed - intr_driven):
            if not w.endswith("_o"):
                continue
            messages.append(f"[ERROR] Interrupt wire '{w}' is consumed but never driven: "
                            f"the routed line can never fire. The source port is either "
                            f"missing, misnamed, or claimed by another connection.")

        for inst_name, inst in self.instances.items():
            comp_name = inst_name[2:] if inst_name.startswith("i_") else inst_name
            # Fallback for tiled name mappings
            if comp_name.endswith("_tile") and comp_name not in comp_info:
                comp_name = comp_name[:-5]
            if comp_name.startswith("tile_") and comp_name not in comp_info:
                comp_name = comp_name[5:]
                
            c_ports = comp_info.get(comp_name, {}).get("ports", {})
            if not c_ports:
                continue

            connected_ports = {c.port_name for c in inst.connections}

            # 1. Connection Completeness Check
            for port_name in c_ports.keys():
                if port_name not in connected_ports:
                    messages.append(f"[WARNING] Port '{port_name}' on instance '{inst_name}' is not connected.")

            # 2. Bit-Width Match Check
            for conn in inst.connections:
                port_name = conn.port_name
                if port_name not in c_ports:
                    messages.append(f"[ERROR] Port '{port_name}' connected on instance '{inst_name}' does not exist in module definition.")
                    continue

                p_info = c_ports[port_name]
                p_type = p_info.get("type_dim", "logic")

                # Evaluate parameters in port type to get absolute width
                known_params = {}
                known_params.update(comp_info.get(comp_name, {}).get("supported_params", {}))
                known_params.update(comp_info.get(comp_name, {}).get("fixed_params", {}))
                known_params.update(inst.parameters)

                p_type_eval = p_type
                for param_name, param_val in known_params.items():
                    p_type_eval = re.sub(rf'\b{param_name}\b', str(param_val), p_type_eval)

                # Simplify math in the evaluated port type range
                from core.utils import simplify_port_ranges
                p_type_eval = simplify_port_ranges(p_type_eval)

                port_width = get_type_width(p_type_eval)
                expr_width = get_expr_width(conn.expression, self.signals)

                if port_width > 0 and expr_width > 0:
                    if port_width != expr_width:
                        messages.append(
                            f"[ERROR] Width mismatch on '{inst_name}.{port_name}': "
                            f"port expects width {port_width} ({p_type_eval}), "
                            f"but connected expression '{conn.expression}' has width {expr_width}."
                        )
                elif expr_width == -2:
                    # Unsized constants are compatible with any width
                    pass

        return messages

"""
Interrupt routing shared by the two top-level templates.

The crossbar top used to carry, in its Mako header, everything needed to turn the
'interrupts' declarations into RTL: dimension resolution from the parsed headers, the
list of output interrupts that need a wire, the sparse aliases, the dictionary-mapped
vectors and the clock-domain synchronizers. The NoC top had none of it, so a mesh
component's 'interrupts' produced registers and helpers but no wires. Moving the
Python half here and the SystemVerilog half into hw/infrastructure/interrupt_routing.mako
gives both tops one implementation; the crossbar output stayed byte-identical through
the move, which is the check that the refactoring changed nothing there.

One addition for the mesh: an OUTPUT interrupt of a component that expands into several
tile instances is one wire per instance - 'intr_<comp>_<port>' becomes an array over the
instances and every tile drives its own slice (rtl_ir_builder.build_noc_ir), so a source
written as 'comp.port' in the description names the whole array.
"""
import re

from core.utils import instance_count


def resolve_dim(c, c_info, dim_str):
    """Substitute a component's parameter names into an SV dimension string and fold the
    resulting arithmetic, so '[NumMailboxes-1:0]' becomes '[15:0]'."""
    params = {}
    if c_info:
        params.update(c_info.get('fixed_params', {}))
        supported = c_info.get('supported_params', {})
        if isinstance(supported, dict):
            params.update(supported)
    if getattr(c, 'parameters', None):
        params.update(c.parameters)

    for pk, pv in params.items():
        dim_str = re.sub(r'\b' + re.escape(pk) + r'\b', str(pv), dim_str)

    def eval_math(m):
        parts = m.group(1).split(':')
        eval_parts = []
        for p in parts:
            try:
                val = eval(p, {"__builtins__": {}})
                eval_parts.append(str(val))
            except Exception:
                eval_parts.append(p.strip())
        return '[' + ':'.join(eval_parts) + ']'

    return re.sub(r'\[(.*?)\]', eval_math, dim_str)


def get_port_dim(config, comp_info, c_name, port_name, is_input):
    """The packed dimension ('[31:0]', or '' for a scalar) of a component port, from the
    header parsed in Phase 2; a name without its direction suffix is tried as well."""
    c_info = comp_info.get(c_name, {})
    ports = c_info.get("ports", {})
    p_info = ports.get(port_name)
    if not p_info:
        base_port = port_name[:-2] if (is_input and port_name.endswith('_i')) or (not is_input and port_name.endswith('_o')) else port_name
        p_info = ports.get(base_port)

    if p_info:
        dims = re.findall(r'\[.*?\]', p_info["type_dim"])
        if dims:
            c_obj = next((x for x in [config.host] + config.components if x.name == c_name), None)
            return resolve_dim(c_obj, c_info, "".join(dims))
    return ""


def get_rep_factor(dim_str):
    """How many times a scalar source must be replicated to fill a vector destination."""
    if not dim_str:
        return ""
    m = re.match(r'\[(.*?):(.*?)\s*\]', dim_str)
    if m:
        try:
            val = int(m.group(1)) - int(m.group(2)) + 1
            return str(val) if val > 1 else ""
        except Exception:
            u = m.group(1).strip()
            l = m.group(2).strip()
            if l == '0':
                if u.endswith('-1'):
                    return u[:-2].strip()
                if u.endswith('- 1'):
                    return u[:-3].strip()
            return f"({u})-({l})+1"
    return ""


def check_src_valid(config, src_expr):
    """Whether every component named in an interrupt source expression exists (sub-components
    of an APB subsystem included). A missing one is tied off with a comment, not an error,
    so a partial description still generates."""
    src_comp_names = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', src_expr))
    for sc in src_comp_names:
        found = False
        if sc == config.host.name:
            found = True
        else:
            for c in config.components:
                if c.name == sc:
                    found = True
                    break
                if c.components:
                    for sub in c.components:
                        if sub.name == sc:
                            found = True
                            break
        if not found:
            return False, sc
    return True, None


def get_all_irqs(comps, parent_clk=None, parent_rst=None):
    """Every 'interrupts' entry of every component as (component, name, cfg, clk, rst)."""
    irqs = []
    for c in comps:
        c_clk = c.clock_domain or parent_clk or "host_clk"
        c_rst = c.reset_domain or parent_rst or "host_rst"
        if c.interrupts:
            for irq_name, irq_cfg in c.interrupts.items():
                irqs.append((c, irq_name, irq_cfg, c_clk, c_rst))
    return irqs


def get_clk_by_comp_name(config, name):
    """The clock domain a (sub-)component runs in, for the CDC decision."""
    if name == config.host.name:
        return config.host.clock_domain or 'host_clk'
    c = next((c for c in config.components if c.name == name), None)
    if c:
        return c.clock_domain or 'host_clk'
    for c in config.components:
        if c.components:
            sub = next((s for s in c.components if s.name == name), None)
            if sub:
                return sub.clock_domain or c.clock_domain or 'host_clk'
    return 'host_clk'


def irq_plan(config, comp_info):
    """Everything the interrupt_routing.mako defs render, computed once per top."""
    all_irqs = get_all_irqs([config.host] + config.components)
    on_mesh = config.topology.type == "noc"

    # Output interrupt ports that need a top-level wire, with their dimension.
    out_ports = {}
    for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
        if not irq_cfg.get('source'):
            port_name = irq_cfg.get('port', irq_name)
            if (c.name, port_name) not in out_ports:
                fallback = irq_cfg.get('width', 1)
                c_info = comp_info.get(c.name, {})
                parse_dim = irq_cfg.get('parse_sv_dim', True)
                dim = ""
                if parse_dim:
                    ports = c_info.get("ports", {})
                    base_port = port_name[:-2] if port_name.endswith('_o') else port_name
                    p_info = ports.get(port_name) or ports.get(base_port)
                    if p_info:
                        dims = re.findall(r'\[.*?\]', p_info["type_dim"])
                        if dims:
                            dim = resolve_dim(c, c_info, "".join(dims))
                if not dim and fallback > 1:
                    dim = f"[{fallback-1}:0]"
                # One slice per tile instance on a mesh (see the module docstring).
                if on_mesh and instance_count(c) > 1:
                    dim = f"[{instance_count(c)-1}:0]" + dim
                out_ports[(c.name, port_name)] = dim

    # Dictionary-mapped destinations, assembled bit by bit in an always_comb.
    complex_irqs = []
    for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
        source_str = str(irq_cfg.get('source', '')).strip()
        if source_str.startswith('{') and source_str.endswith('}'):
            complex_irqs.append((c, irq_name, irq_cfg, source_str))

    # Destinations whose source sits in another clock domain (unless 'cdc: false').
    sync_irqs = []
    for c, irq_name, irq_cfg, c_clk, c_rst in all_irqs:
        if irq_cfg.get('source') and str(irq_cfg.get('source')) != 'none':
            source_str = str(irq_cfg.get('source')).strip()
            is_valid, missing = check_src_valid(config, source_str)
            if not is_valid:
                continue

            src_comp_names = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', source_str))
            needs_sync = False
            for src_comp_name in src_comp_names:
                src_clk = get_clk_by_comp_name(config, src_comp_name)
                if src_clk != c_clk:
                    needs_sync = True
                    break
            if irq_cfg.get('cdc') is False:
                needs_sync = False
            if needs_sync:
                sync_irqs.append((c, irq_name, irq_cfg, c_clk, c_rst, source_str))

    return {
        "all_irqs": all_irqs,
        "out_ports": out_ports,
        "complex_irqs": complex_irqs,
        "sync_irqs": sync_irqs,
        "port_dim": lambda c_name, port_name, is_input: get_port_dim(config, comp_info, c_name, port_name, is_input),
        "src_valid": lambda src: check_src_valid(config, src),
        "rep_factor": get_rep_factor,
    }

# Copyright 2026 Fondazione Chips-IT.
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51

import sys
import yaml
from pathlib import Path

from core.utils import yaml_load_strict


def load_env_yaml(path, what="environment configuration"):
    """Read one environment YAML file, or stop with the parser's own diagnostic.

    An environment file that cannot be parsed used to be skipped: the paths and the forced
    resolutions it declared simply vanished, and generation carried on with the base
    configuration alone, reporting nothing. The failure then surfaced much later as a wrong
    output directory or a package resolved to an unexpected revision, with nothing pointing
    back at the real cause. A syntax error in a file the user just edited is not a condition
    to recover from, so it is fatal here, where yaml reports the exact line and column.

    A missing file is a different matter and is not this function's business: every
    environment file is optional, and its absence is handled by the callers.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            # Strict loader: a duplicated key in a file we own is always a bug
            # (see UniqueKeySafeLoader), and yaml reports its exact position.
            return yaml_load_strict(f) or {}
    except yaml.YAMLError as e:
        print(f"\n[ERROR] Cannot parse the {what} '{path}':\n{e}")
        sys.exit(1)
    except OSError as e:
        print(f"\n[ERROR] Cannot read the {what} '{path}': {e}")
        sys.exit(1)


class OllivanderEnv:
    """
    Data class that holds the resolved environment configuration for the current run.
    It stores all absolute paths (outputs, templates, components, tools) and the 
    merged registry of external Bender dependencies.
    """
    def __init__(self):
        self.registry_dependencies = {}
        self.outdir_path = None
        self.hw_sub = "hw"
        self.sw_sub = "sw"
        self.doc_sub = "doc"
        self.cfg_sub = "cfg"
        self.reg_sub = "reg"
        self.tb_sub = "tb"
        self.bender_manifest_path = None
        self.bender_dir = None
        self.template_paths = []
        self.component_paths = []
        self.search_paths = []
        self.exclude_dir = ""
        self.base_dir = None
        # Resolved path of the base environment configuration actually loaded, which is
        # ollivander_config.yml unless -e/--env-config replaced it. Exposed because the caller
        # needs to read its 'overrides' section, and cannot infer the default from the CLI
        # arguments alone.
        self.env_config_path = None
        self.fast_check_tool = "questa"
        self.ecc_schemes_dir = None

def setup_environment(args, base_dir: Path) -> OllivanderEnv:
    """
    Parses environment configuration files and command-line arguments to establish
    the execution context. It handles path resolutions, precedence rules, and 
    merges multiple environment configurations if provided.
    """
    env = OllivanderEnv()
    
    env.base_dir = base_dir
    # 1. Load the base environment configuration (usually ollivander_config.yml).
    # This provides the default paths and the base dependency registry.
    env_config_path = Path(args.env_config) if args.env_config else base_dir / "ollivander_config.yml"
    env_cfg = {}
    if env_config_path.is_file():
        env_cfg = load_env_yaml(env_config_path, "base environment configuration")
    elif args.env_config:
        print(f"[ERROR] Specified environment config not found: {env_config_path}")
        sys.exit(1)
        
    env.env_config_path = env_config_path
    env_base = env_config_path.parent
    paths_cfg = env_cfg.get('paths', {})
    
    # 2. Load an optional secondary environment file to be merged.
    # This allows users to override paths or add project-specific dependencies
    # without modifying the global ollivander_config.yml.
    append_env_cfg = {}
    append_env_base = None
    if args.append_env:
        append_env_path = Path(args.append_env)
        if append_env_path.is_file():
            append_env_cfg = load_env_yaml(append_env_path, "project environment configuration")
            append_env_base = append_env_path.parent
        else:
            print(f"[ERROR] Specified append environment config not found: {append_env_path}")
            sys.exit(1)
            
    app_paths_cfg = append_env_cfg.get('paths', {})

    # 3. Merge dependency registries from both environment files.
    # If a dependency exists in both, the appended environment takes precedence.
    # A registry entry written with no properties at all - a name followed by nothing, or by
    # comments only - parses as None, and every consumer that calls .get() on it fails with an
    # opaque "'NoneType' object has no attribute 'get'" raised from inside a Mako template. Normalise
    # it to an empty mapping so that such an entry is simply inert.
    #
    # "inherit_default_dependencies: false" declines the base registry as a whole, the twin of
    # "inherit_default_overrides" for projects that want a fully self-contained, auditable
    # dependency description: with it, a package required by pragma but absent from the project's
    # own registry becomes a hard error instead of silently resolving to the catalogue's source.
    # An unused base entry is inert for *resolution* either way (the registry is pragma-gated);
    # this flag exists for *control*. Note what is declined along with the sources: the base
    # entries also carry the patches and pre-build repairs, which the project then owns.
    inherit_deps = True
    if append_env_cfg and 'inherit_default_dependencies' in append_env_cfg:
        inherit_deps = bool(append_env_cfg['inherit_default_dependencies'])
    base_deps = {k: (v or {}) for k, v in (env_cfg.get('dependencies') or {}).items()}
    if not inherit_deps:
        print(f"  [INFO] inherit_default_dependencies is false: dropping the {len(base_deps)} "
              f"dependencies of {env_config_path.name}; only the project's own remain.")
        base_deps = {}
    env.registry_dependencies = base_deps
    if append_env_cfg:
        for dep_name, dep_info in append_env_cfg.get('dependencies', {}).items():
            if dep_name in env.registry_dependencies:
                env.registry_dependencies[dep_name].update(dep_info)
            else:
                env.registry_dependencies[dep_name] = dep_info or {}

    # 4. Determine the final output directory path with the following precedence:
    #    1. Command Line (`-o`)
    #    2. Appended Environment YAML
    #    3. Base Environment YAML
    #    4. Default ('./generated')
    if args.outdir is not None:
        env.outdir_path = Path(args.outdir).resolve()
    elif 'outdir' in app_paths_cfg:
        env.outdir_path = (append_env_base / app_paths_cfg['outdir']).resolve()
    elif 'outdir' in paths_cfg:
        env.outdir_path = (env_base / paths_cfg['outdir']).resolve()
    else:
        env.outdir_path = Path("generated").resolve()

    # Helper to get subdirectory configurations, giving precedence to the appended environment.
    def get_path_cfg(key, default):
        if key in app_paths_cfg:
            return app_paths_cfg[key]
        if key in paths_cfg:
            return paths_cfg[key]
        return default

    env.hw_sub = get_path_cfg('sub_hw', 'hw')
    env.sw_sub = get_path_cfg('sub_sw', 'sw')
    env.doc_sub = get_path_cfg('sub_doc', 'doc')
    env.cfg_sub = get_path_cfg('sub_cfg', 'cfg')
    env.reg_sub = get_path_cfg('sub_reg', 'reg')
    env.tb_sub = get_path_cfg('sub_tb', 'tb')
    
    if 'ecc_schemes_dir' in app_paths_cfg:
        env.ecc_schemes_dir = (append_env_base / app_paths_cfg['ecc_schemes_dir']).resolve()
    elif 'ecc_schemes_dir' in paths_cfg:
        env.ecc_schemes_dir = (env_base / paths_cfg['ecc_schemes_dir']).resolve()
    else:
        env.ecc_schemes_dir = (base_dir / "src/core/ecc_schemes").resolve()
    
    # Helper to resolve the path for the Bender manifest file.
    # It dynamically replaces the '{outdir}' placeholder with the actual resolved output path.
    def resolve_manifest_path(raw_path, base_path):
        replaced = raw_path.replace('{outdir}', str(env.outdir_path))
        p = Path(replaced)
        return p.resolve() if p.is_absolute() else (base_path / p).resolve()

    if args.bender is not None:
        env.bender_manifest_path = resolve_manifest_path(args.bender, Path.cwd())
    elif 'bender_manifest' in app_paths_cfg:
        env.bender_manifest_path = resolve_manifest_path(app_paths_cfg['bender_manifest'], append_env_base)
    elif 'bender_manifest' in paths_cfg:
        env.bender_manifest_path = resolve_manifest_path(paths_cfg['bender_manifest'], env_base)
    else:
        env.bender_manifest_path = env.outdir_path / "Bender.yml"
        
    env.bender_dir = env.bender_manifest_path.parent

    # Helper to resolve a list of paths relative to a base directory.
    # Used to build absolute search paths for templates, components, and tools.
    def resolve_paths(cfg_val, base, default):
        if not cfg_val:
            cfg_val = default
        if isinstance(cfg_val, str):
            cfg_val = [cfg_val]
        return [(base / p).resolve() for p in cfg_val]
        
    # Handle legacy path keys for backwards compatibility (e.g., 'templates_dir').
    tpl_cfg = paths_cfg.get('templates', paths_cfg.get('templates_dir', ['src/templates']))
    cmp_cfg = paths_cfg.get('components', paths_cfg.get('components_dir', ['components']))
    
    base_template_paths = resolve_paths(tpl_cfg, env_base, ['src/templates'])
    base_component_paths = resolve_paths(cmp_cfg, env_base, ['components'])

    # Paths declared in the appended project environment take PRECEDENCE over the ones of
    # the base environment, so they are prepended rather than appended.
    #
    # Every lookup built on these lists stops at the first match: get_isle_info() in
    # sv_parser.py breaks out as soon as it finds "<type>.sv", and Mako's TemplateLookup
    # resolves against the first directory that holds the file. Prepending therefore turns
    # "-a/--append-env" into a way to *override* a component or a template shipped with
    # Ollivander, and not merely to add new ones: a downstream project that needs a variant
    # of, say, l2_isle.sv only has to place a file of the same name in its own components
    # directory. With the previous order the default always won, and overriding required
    # replacing the whole environment with "-e/--env-config" and re-declaring every path.
    #
    # This mirrors the precedence already applied to dependencies, where the revisions in
    # a project's "*_env.yml" override those of the central registry.
    if append_env_base:
        env.template_paths = resolve_paths(app_paths_cfg.get('templates', app_paths_cfg.get('templates_dir', [])), append_env_base, []) + base_template_paths
        env.component_paths = resolve_paths(app_paths_cfg.get('components', app_paths_cfg.get('components_dir', [])), append_env_base, []) + base_component_paths
    else:
        env.template_paths = base_template_paths
        env.component_paths = base_component_paths
    
    # The complete list of paths where Ollivander will search for SV component wrappers
    # during the AST validation and hardware extraction phases.
    env.search_paths = [env.outdir_path] + env.component_paths + [base_dir]
    env.exclude_dir = env.outdir_path.name
    
    # Load fast_check_tool from config files. We only respect the environment variable 
    # FAST_CHECK_TOOL during stub generation (--generate-stubs) to prevent circular 
    # lock-in issues from a pre-existing generated sim makefile.
    import os
    env.fast_check_tool = ""
    if getattr(args, "generate_stubs", False):
        env.fast_check_tool = os.environ.get("FAST_CHECK_TOOL", "")
        
    if not env.fast_check_tool:
        if "fast_check_tool" in append_env_cfg:
            env.fast_check_tool = append_env_cfg["fast_check_tool"]
        elif "fast_check_tool" in env_cfg:
            env.fast_check_tool = env_cfg["fast_check_tool"]
        else:
            env.fast_check_tool = "questa"

    return env

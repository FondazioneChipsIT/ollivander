package:
  name: ${config.project.name}_soc
  authors:
    - "${config.project.author}"

dependencies:
% if project_dependencies:
% for dep_name, dep_info in project_dependencies.items():
% if dep_info.get('version'):
  ${dep_name}: { git: "${dep_info['git']}", version: "${dep_info['version']}" }
% else:
  ${dep_name}: { git: "${dep_info['git']}", rev: "${dep_info['rev']}" }
% endif
% endfor
% endif

workspace:
  checkout_dir: bender_work

sources:
  # --- System Packages ---
  - ${rel_hw_dir}/${config.project.name}_soc_pkg.sv
  - ${rel_hw_dir}/${config.project.name}_reg_pkg.sv
% if config.topology.type == "noc":
  - ${rel_hw_dir}/floo_${config.project.name}_noc_pkg.sv
% endif

  # --- Infrastructure & Primitives ---
% if external_local_files:
% for f in external_local_files:
  - ${f}
% endfor
% endif
  - ${rel_hw_dir}/${config.project.name}_rstgen.sv
% if config.system_controller:
  - ${rel_hw_dir}/${config.project.name}_reg_top.sv
% endif

  # --- Component Wrappers ---
% if generated_module_files:
% for f in generated_module_files:
  - ${f}
% endfor
% endif
% if config.topology.type == "noc":
  - ${rel_hw_dir}/${config.project.name}_dummy_tile.sv
% endif

  # --- Top-Level ---
  - ${rel_hw_dir}/${config.project.name}.sv

  # --- Testbench ---
  - target: simulation
    files:
      - ${rel_tb_dir}/tb_${config.project.name}.sv
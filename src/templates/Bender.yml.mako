<%
  # ============================================================================
  # MAKO TEMPLATE FOR THE BENDER MANIFEST (Bender.yml)
  # ============================================================================
  # This template generates the final Bender manifest for the entire SoC project.
  # It acts as the definitive source of truth for dependency management and 
  # SystemVerilog compilation ordering.
%>
package:
  name: ${config.project.name}_soc
  authors:
    - "${config.project.author}"

# ==============================================================================
# DYNAMIC DEPENDENCIES
# ==============================================================================
# Extracted automatically during Phase 3 by parsing `// BENDER:` pragmas inside
# the generated SystemVerilog wrappers and matching them with the central registry.
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

# Target directory where Bender will clone all external IPs.
workspace:
  checkout_dir: bender_work

# ==============================================================================
# SYSTEMVERILOG COMPILATION ORDER
# ==============================================================================
sources:
  # --- System Packages ---
  # Global parameters and types must be compiled first to be visible everywhere.
  - ${rel_hw_dir}/${config.project.name}_soc_pkg.sv
  - ${rel_hw_dir}/${config.project.name}_sys_regs_pkg.sv
% if config.topology.type == "noc":
  - ${rel_hw_dir}/floo_${config.project.name}_noc_pkg.sv
% endif

  # --- Infrastructure & Primitives ---
  # Low-level blocks (Clock dividers, CDC, Multiplexers) required by the wrappers.
  # These are staged locally by Ollivander based on `// OLLIVANDER: require` pragmas.
% if external_local_files:
% for f in external_local_files:
  - ${f}
% endfor
% endif
  - ${rel_hw_dir}/${config.project.name}_rstgen.sv
% if config.system_controller:
  - ${rel_hw_dir}/${config.project.name}_sys_regs.sv
% endif

  # --- Component Wrappers ---
  # The intermediate Isle/Tile SystemVerilog wrappers bridging the IPs to the SoC.
% if generated_module_files:
% for f in generated_module_files:
  - ${f}
% endfor
% endif
% if config.topology.type == "noc":
  - ${rel_hw_dir}/${config.project.name}_dummy_tile.sv
% endif

  # --- Top-Level ---
  # The final SoC module instantiating all the wrappers and matrices.
  - ${rel_hw_dir}/${config.project.name}.sv

  # --- Testbench ---
  # Target-specific files for simulation (e.g. QuestaSim).
  - target: simulation
    files:
      - ${rel_tb_dir}/tb_${config.project.name}.sv
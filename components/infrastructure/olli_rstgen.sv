// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// OLLIVANDER PLACEHOLDER MODULE
//
// This is a placeholder for the Standard Reset Generator.
// The user is required to implement the logic to synchronize an asynchronous
// reset into a specific clock domain, ensuring a synchronous de-assertion.
//
// BENDER: name="common_cells"

module olli_rstgen (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic test_mode_i,
  output logic rst_no,
  output logic init_no
);

`ifndef TARGET_SYNTHESIS
  // Simulation: use common_cells behavioral model
  rstgen i_sim_rstgen (
    .clk_i       ( clk_i ),
    .rst_ni      ( rst_ni ),
    .test_mode_i ( test_mode_i ),
    .rst_no      ( rst_no ),
    .init_no     ( init_no )
  );
`else
  // Synthesis: instantiate foundry-specific standard cell here
  // (e.g., tsmc_reset_sync)
`endif

endmodule
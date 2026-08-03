// Copyright 2026 Fondazione Chips-IT.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Standardized shell for the Security Island
//
// BENDER: name="opentitan"
// BENDER: name="axi"

`include "axi/typedef.svh"

module security_island_isle
  import axi_pkg::*;
#(
  // Geometry of the SoC this isle is attached to, driven by the generator at
  // instantiation (rtl_ir_builder.py): AxiOutIdWidth receives the crossbar's
  // manager-side AxiIdWidth. Previously localparams, which froze the values this
  // shell was extracted with; the wrapped security_island takes them all as
  // parameters (astral drives them the same way, carfield.sv), so nothing is fixed.
  parameter int unsigned AxiAddrWidth       = 48,
  parameter int unsigned AxiDataWidth       = 64,
  parameter int unsigned AxiUserWidth       = 10,
  parameter int unsigned AxiOutIdWidth      = 2,
  parameter int unsigned LogDepth           = 3,

  // Async AXI OUT (Master Port)
  localparam int unsigned AsyncAxiOutAwWidth = (2**LogDepth)*axi_pkg::aw_width(AxiAddrWidth, AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutWWidth  = (2**LogDepth)*axi_pkg::w_width(AxiDataWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutBWidth  = (2**LogDepth)*axi_pkg::b_width(AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutArWidth = (2**LogDepth)*axi_pkg::ar_width(AxiAddrWidth, AxiOutIdWidth, AxiUserWidth),
  localparam int unsigned AsyncAxiOutRWidth  = (2**LogDepth)*axi_pkg::r_width(AxiDataWidth, AxiOutIdWidth, AxiUserWidth)
) (
  input  logic clk_i,
  input  logic ref_clk_i,
  input  logic rst_ni,
  input  logic pwr_on_rst_ni,
  input  logic test_mode_i,

  // Control and Status
  input  logic [1:0]  bootmode_i,
  input  logic        fetch_en_i,
  input  logic        axi_isolate_i,
  output logic        axi_isolated_o,

  // Interrupts
  input  logic irq_ibex_i,
  input  logic cfi_req_irq_i,
  input  logic cfi_watermark_irq_i,

  // JTAG
  input  logic jtag_tck_i,
  input  logic jtag_trst_ni,
  input  logic jtag_tms_i,
  input  logic jtag_tdi_i,
  output logic jtag_tdo_o,
  output logic jtag_tdo_oe_o,

  // UART
  input  logic uart_rx_i,
  output logic uart_tx_o,

  // SPI Host
  output logic       spi_host_sck_o,
  output logic       spi_host_sck_en_o,
  output logic       spi_host_csb_o,
  output logic       spi_host_csb_en_o,
  output logic [3:0] spi_host_sd_o,
  input  logic [3:0] spi_host_sd_i,
  output logic [3:0] spi_host_sd_en_o,

  // GPIO
  input  logic gpio_0_i,
  output logic gpio_0_o,
  output logic gpio_0_oe_o,
  input  logic gpio_1_i,
  output logic gpio_1_o,
  output logic gpio_1_oe_o,

  // Standard AXI OUT (Master)
  output logic [AsyncAxiOutAwWidth-1:0] async_axi_out_aw_data_o,
  output logic             [LogDepth:0] async_axi_out_aw_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_aw_rptr_i,
  output logic [ AsyncAxiOutWWidth-1:0] async_axi_out_w_data_o,
  output logic             [LogDepth:0] async_axi_out_w_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_w_rptr_i,
  input  logic [ AsyncAxiOutBWidth-1:0] async_axi_out_b_data_i,
  input  logic             [LogDepth:0] async_axi_out_b_wptr_i,
  output logic             [LogDepth:0] async_axi_out_b_rptr_o,
  output logic [AsyncAxiOutArWidth-1:0] async_axi_out_ar_data_o,
  output logic             [LogDepth:0] async_axi_out_ar_wptr_o,
  input  logic             [LogDepth:0] async_axi_out_ar_rptr_i,
  input  logic [ AsyncAxiOutRWidth-1:0] async_axi_out_r_data_i,
  input  logic             [LogDepth:0] async_axi_out_r_wptr_i,
  output logic             [LogDepth:0] async_axi_out_r_rptr_o
);

  // AXI channel types built from the isle's own parameters, for the same reason as in
  // safety_island_isle: the wrapped module's type parameters default to synth-package
  // types frozen at the synth geometry, so the structs would not follow the widths.
  typedef logic [AxiAddrWidth-1:0]   isle_addr_t;
  typedef logic [AxiDataWidth-1:0]   isle_data_t;
  typedef logic [AxiDataWidth/8-1:0] isle_strb_t;
  typedef logic [AxiUserWidth-1:0]   isle_user_t;
  typedef logic [AxiOutIdWidth-1:0]  isle_out_id_t;
  `AXI_TYPEDEF_ALL(isle_axi_out, isle_addr_t, isle_out_id_t, isle_data_t, isle_strb_t, isle_user_t)

  security_island #(
    .AxiAddrWidth   ( AxiAddrWidth  ),
    .AxiDataWidth   ( AxiDataWidth  ),
    .AxiUserWidth   ( AxiUserWidth  ),
    .AxiExtIdWidth  ( AxiOutIdWidth ),
    .axi_ext_aw_chan_t ( isle_axi_out_aw_chan_t ),
    .axi_ext_w_chan_t  ( isle_axi_out_w_chan_t  ),
    .axi_ext_b_chan_t  ( isle_axi_out_b_chan_t  ),
    .axi_ext_ar_chan_t ( isle_axi_out_ar_chan_t ),
    .axi_ext_r_chan_t  ( isle_axi_out_r_chan_t  ),
    .axi_ext_req_t     ( isle_axi_out_req_t     ),
    .axi_ext_resp_t    ( isle_axi_out_resp_t    )
  ) i_security_island (
    .clk_i               ( clk_i               ),
    .clk_ref_i           ( ref_clk_i           ),
    .rst_ni              ( rst_ni              ),
    .pwr_on_rst_ni       ( pwr_on_rst_ni       ),
    .fetch_en_i          ( fetch_en_i          ),
    .bootmode_i          ( bootmode_i          ),
    .test_enable_i       ( test_mode_i         ),
    .irq_ibex_i          ( irq_ibex_i          ),
    .cfi_req_irq_i       ( cfi_req_irq_i       ),
    .cfi_watermark_irq_i ( cfi_watermark_irq_i ),
    .jtag_tck_i          ( jtag_tck_i          ),
    .jtag_tms_i          ( jtag_tms_i          ),
    .jtag_trst_n_i       ( jtag_trst_ni        ),
    .jtag_tdi_i          ( jtag_tdi_i          ),
    .jtag_tdo_o          ( jtag_tdo_o          ),
    .jtag_tdo_oe_o       ( jtag_tdo_oe_o       ),
    // Asynch axi port (mapped to standard Ollivander OUT)
    .async_axi_ext_aw_data_o ( async_axi_out_aw_data_o ),
    .async_axi_ext_aw_wptr_o ( async_axi_out_aw_wptr_o ),
    .async_axi_ext_aw_rptr_i ( async_axi_out_aw_rptr_i ),
    .async_axi_ext_w_data_o  ( async_axi_out_w_data_o  ),
    .async_axi_ext_w_wptr_o  ( async_axi_out_w_wptr_o  ),
    .async_axi_ext_w_rptr_i  ( async_axi_out_w_rptr_i  ),
    .async_axi_ext_b_data_i  ( async_axi_out_b_data_i  ),
    .async_axi_ext_b_wptr_i  ( async_axi_out_b_wptr_i  ),
    .async_axi_ext_b_rptr_o  ( async_axi_out_b_rptr_o  ),
    .async_axi_ext_ar_data_o ( async_axi_out_ar_data_o ),
    .async_axi_ext_ar_wptr_o ( async_axi_out_ar_wptr_o ),
    .async_axi_ext_ar_rptr_i ( async_axi_out_ar_rptr_i ),
    .async_axi_ext_r_data_i  ( async_axi_out_r_data_i  ),
    .async_axi_ext_r_wptr_i  ( async_axi_out_r_wptr_i  ),
    .async_axi_ext_r_rptr_o  ( async_axi_out_r_rptr_o  ),
    .axi_isolate_i       ( axi_isolate_i       ),
    .axi_isolated_o      ( axi_isolated_o      ),
    .ibex_uart_rx_i      ( uart_rx_i           ),
    .ibex_uart_tx_o      ( uart_tx_o           ),
    .spi_host_SCK_o      ( spi_host_sck_o      ),
    .spi_host_SCK_en_o   ( spi_host_sck_en_o   ),
    .spi_host_CSB_o      ( spi_host_csb_o      ),
    .spi_host_CSB_en_o   ( spi_host_csb_en_o   ),
    .spi_host_SD_o       ( spi_host_sd_o       ),
    .spi_host_SD_i       ( spi_host_sd_i       ),
    .spi_host_SD_en_o    ( spi_host_sd_en_o    ),
    .gpio_0_i            ( gpio_0_i            ),
    .gpio_0_o            ( gpio_0_o            ),
    .gpio_0_oe_o         ( gpio_0_oe_o         ),
    .gpio_1_i            ( gpio_1_i            ),
    .gpio_1_o            ( gpio_1_o            ),
    .gpio_1_oe_o         ( gpio_1_oe_o         )
  );

endmodule : security_island_isle

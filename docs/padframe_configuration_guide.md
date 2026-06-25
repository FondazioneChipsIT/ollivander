# Ollivander Padframe Configuration Guide

This guide explains how to define, structure, and generate physical Padframes and I/O Pin multiplexing (Pinmux) using the **Padrick** integration in Ollivander.

In Ollivander, you can define the pad list for each voltage domain using three alternative formats:
1. **CSV Flat File (`*.csv`)**: Recommended for most designs. Simple, tabular, and easy to edit in spreadsheet tools.
2. **Python Script (`*.py`)**: Recommended for large or complex designs. Allows procedural generation (e.g. loops, conditional configurations).
3. **Native Padrick YAML (`*.yml`)**: Recommended for low-level control. Maps directly to Padrick's native format.

---

## 1. Directory Structure and Technology Libraries

Every padframe is associated with a physical technology target (e.g., `behavioral`, `gf22`, etc.). Ollivander structures these targets under the `components/padframes/` directory.

### Structure of `components/padframes/`
```text
components/
└── padframes/
    ├── behavioral/
    │   ├── behavioral.yml   <-- Padrick Technology Catalog
    │   ├── tc_pad_pkg.sv    <-- SystemVerilog helper package
    │   └── tc_pad.sv        <-- SystemVerilog cell wrappers
    └── <other_tech>/
        ├── <other_tech>.yml
        └── ...
```

### File Responsibilities
1. **`<tech_name>.yml` (Technology Catalog)**: 
   This file is a Padrick-native technology declaration. It specifies:
   - Available pad types (e.g., inputs, outputs, bidirectionals, power pads).
   - Pad signals (e.g., data input, data output, pullup/pulldown enables).
   - Core-facing and pad-facing port names.
   - Output templates generating the physical instantiation blocks of the pads.

2. **SystemVerilog Source Files (`*.sv`)**:
   Any `.sv` files present inside the `components/padframes/<tech_name>/` folder provide the actual SystemVerilog module implementations for the pads declared in the technology catalog.
   - **Dynamic Discovery**: Ollivander automatically searches the selected technology's directory, globs all `*.sv` files, and appends them to the compilation manifest (`Bender.yml` / compilation flow).
   - **Custom Technologies**: Users can place custom technology folders under `hw_ips/padframes/<tech_name>/` in their own repository, provided `hw_ips` is listed in the environment bridge file under `paths.components`.

---

## 2. Defining the Padframe in the SoC Configuration

In your main SoC configuration YAML, declare the padframe base settings under the `padframe` key:

```yaml
padframe:
  name: "crux_padframe"
  base_addr: 0x200A0000       # Memory mapped base address for pinmux CSRs
  sync_domain: false          # Generates an async RegBus CDC adapter

  # Choose ONE of the three alternatives below to define the pad lists:

  # --- Alternative 1: CSV Padlist (Default) ---
  pad_csv: "crux_pads.csv"
  domains:
    - name: "domain_1v8"
      tech: "behavioral"
    - name: "domain_3v3"
      tech: "behavioral"

  # --- Alternative 2: Python Dynamic Padlist ---
  # pad_py: "crux_pads.py"
  # domains:
  #   - name: "domain_1v8"
  #     tech: "behavioral"
  #   - name: "domain_3v3"
  #     tech: "behavioral"

  # --- Alternative 3: YAML Padlists ---
  # domains:
  #   - name: "domain_1v8"
  #     tech: "behavioral"
  #     pad_list: "crux_pad_list_1v8.yml"
  #   - name: "domain_3v3"
  #     tech: "behavioral"
  #     pad_list: "crux_pad_list_3v3.yml"
```

---

## 3. Option 1: CSV-Based Padframe (`pad_csv`)

The CSV format allows you to list all pads for all domains in a single spreadsheet. 

### Columns in the CSV File
Your CSV must contain the following core columns:
- **`Domain`**: The target voltage domain (e.g. `domain_1v8`, `domain_3v3`). Must match the name of a domain defined under `padframe.domains` in the SoC YAML.
- **`Pad Name`**: The unique physical name of the pad. If it is a group, you can use `{i}` as a placeholder to be expanded dynamically.
- **`Type`**: The cell type of the pad (must match one of the pad types defined in the technology catalog YAML, e.g., `PAD_INPUT_H`, `PAD_BIDIR_V`).
- **`Multiple`**: Integer specifying how many pads to instantiate (expands `{i}` from `0` to `Multiple-1`). Use `1` for single pads.
- **`Is Static`**: Boolean (`true` or `false`).
  - **`true`**: The pad is static (e.g., clocks, power supply, JTAG pins). It connects directly to specific chip-level signals.
  - **`false`**: The pad is multiplexed (e.g. GPIOs). Its connections are managed dynamically through the pinmux CSRs.
- **`Default Port`**: Only valid for **multiplexed** pads (`Is Static = false`). Specifies which core-facing port is routed to the pad by default (e.g. `soc_exports.gpio_{i}`).
- **`Description`**: An optional text description.

### Static Connection Columns
Any additional column header in the CSV is treated as a **static connection signal** matching the pad signals defined in the technology catalog (e.g. `pad2chip`, `chip2pad`, `input_en`, `pu_en`, `pd_en`, `schmitt_en`, `output_en`, `drive_strength`, `slew_en`).
- **Rules**:
  1. Multiplexed pads (`Is Static = false`) **must have these columns left empty**.
  2. Static pads (`Is Static = true`) can populate these columns to map the pad's internal signals directly to core/wrapper signals or tie-offs (e.g., `1'b1`, `1'b0`, `uart_tx_o`, `ref_clk_i`).

### Example CSV (`crux_pads.csv`)
```csv
Domain,Pad Name,Type,Multiple,Is Static,Default Port,Description,pad2chip,chip2pad,input_en,pu_en,pd_en,schmitt_en,output_en
domain_1v8,config_tc_pad,CONFIG_TC_PAD_DEF,1,true,,Config pad definition,,,,,,,,
domain_1v8,PAD_CLK,PAD_INPUT_H,1,true,,Global Clock,ref_clk_i,,1'b1,1'b0,1'b0,1'b1,,
domain_1v8,PAD_ETH_MDIO,PAD_BIDIR_H,1,true,,Ethernet MDIO,ethernet_phy_mdio_i,ethernet_phy_mdio_o,1'b1,1'b0,1'b0,1'b1,ethernet_phy_mdio_oe
domain_3v3,PAD_UART_TX,PAD_OUTPUT_V,1,true,,Dedicated UART TX Pad,,uart_tx_o,,,,,1'b1
domain_3v3,pad_muxed_gpio_{i},PAD_BIDIR_V,8,false,soc_exports.gpio_{i},GPIO Bus (muxed),,,,,,,,
```

---

## 4. Option 2: Python-Based Padframe (`pad_py`)

The Python script format allows you to dynamically build your pad list using scripting. This is useful for large chips where pads can be automatically numbered, grouped, or conditional.

### Requirements
- The Python script must define a global dictionary named **`pad_domains`**.
- The keys of `pad_domains` must match the domain names.
- The value for each key must be a **list of dictionaries**, where each dictionary represents a pad.

### Pad Dictionary Fields
Each dictionary inside the lists represents a pad and must contain:
- `"name"`: (string) Name of the pad.
- `"pad_type"`: (string) Type of pad cell.
- `"is_static"`: (boolean) Whether the pad is static.
- `"multiple"`: (integer, optional) Multiplicity factor.
- `"description"`: (string, optional) Description.
- `"default_port"`: (string, optional) Default port for multiplexed pads.
- `"connections"`: (dictionary, optional) Static signal connections mapping.

### Example Python Script (`crux_pads.py`)
```python
domain_1v8 = [
    {
        "name": "config_tc_pad",
        "pad_type": "CONFIG_TC_PAD_DEF",
        "multiple": 1,
        "is_static": True,
        "description": "Config pad definition"
    },
    {
        "name": "PAD_CLK",
        "pad_type": "PAD_INPUT_H",
        "multiple": 1,
        "is_static": True,
        "description": "Global Clock",
        "connections": {
            "pad2chip": "ref_clk_i",
            "input_en": "1'b1",
            "pu_en": "1'b0",
            "pd_en": "1'b0",
            "schmitt_en": "1'b1"
        }
    }
]

domain_3v3 = [
    {
        "name": "PAD_UART_TX",
        "pad_type": "PAD_OUTPUT_V",
        "multiple": 1,
        "is_static": True,
        "description": "Dedicated UART TX Pad",
        "connections": {
            "chip2pad": "uart_tx_o",
            "output_en": "1'b1"
        }
    },
    # Loop to procedurally add multiple pads
    *[
        {
            "name": f"pad_muxed_gpio_{i}",
            "pad_type": "PAD_BIDIR_V",
            "multiple": 1,
            "is_static": False,
            "default_port": f"soc_exports.gpio_{i}",
            "description": f"Muxed GPIO pin {i}"
        }
        for i in range(8)
    ]
]

pad_domains = {
    "domain_1v8": domain_1v8,
    "domain_3v3": domain_3v3
}
```

---

## 5. Option 3: Native Padrick YAML (`pad_list`)

The native Padrick format maps directly to the standard Padrick YAML structure. You define a separate YAML file for each domain.

### Structure
Each YAML file is a flat list of pad definition objects. Each object can have the following keys:
- `name`: (string) Pad name. Can contain `{i}`.
- `pad_type`: (string) Pad cell type.
- `is_static`: (boolean) Whether the pad is static.
- `multiple`: (integer, optional) Multiplicity factor.
- `description`: (string, optional) Description.
- `default_port`: (string, optional) Default port for multiplexed pads.
- `connections`: (map, optional) Mappings for static connections.

### Example Native YAML (`crux_pad_list_1v8.yml`)
```yaml
- name: config_tc_pad
  pad_type: CONFIG_TC_PAD_DEF
  is_static: true
  description: Config pad definition

- name: PAD_CLK
  pad_type: PAD_INPUT_H
  is_static: true
  description: Global Clock
  connections:
    pad2chip: ref_clk_i
    input_en: 1'b1
    pu_en: 1'b0
    pd_en: 1'b0
    schmitt_en: 1'b1

- name: pad_muxed_gpio_{i}
  pad_type: PAD_BIDIR_V
  multiple: 8
  is_static: false
  default_port: soc_exports.gpio_{i}
  description: GPIO Bus (muxed)
```

---

## Comparison of Formats

| Feature | CSV Option (`pad_csv`) | Python Option (`pad_py`) | Native YAML Option (`pad_list`) |
| :--- | :--- | :--- | :--- |
| **Readability** | Tabular, very high | Moderate (code-like) | Structured, clean |
| **Complexity** | Best for standard pinouts | Best for algorithmic layouts | Best for explicit definitions |
| **Tooling** | LibreOffice, Excel | Python IDEs | Any Text Editor |
| **Logic/Loops** | Not supported | Fully supported | Not supported |
| **File Count** | Single file for all domains | Single file for all domains | One file per domain |

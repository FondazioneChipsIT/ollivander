import sys
import os
import argparse
import yaml

def load_ecc_scheme(scheme_name, ecc_dir):
    scheme_file = os.path.join(ecc_dir, f"{scheme_name}.yml") if ecc_dir else ""
    if not scheme_file or not os.path.isfile(scheme_file):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        scheme_file = os.path.join(script_dir, "ecc_schemes", f"{scheme_name}.yml")
        
    if not os.path.isfile(scheme_file):
        raise FileNotFoundError(f"ECC scheme file '{scheme_name}.yml' not found in '{ecc_dir}' or default search paths.")
        
    with open(scheme_file, "r", encoding="utf-8") as f:
        scheme_data = yaml.safe_load(f)
        
    matrix_raw = scheme_data.get("matrix", [])
    matrix = []
    for row in matrix_raw:
        if isinstance(row, str):
            matrix.append(int(row, 0))
        else:
            matrix.append(int(row))
    return matrix

def calculate_ecc(val, matrix):
    parity = 0
    for i, row in enumerate(matrix):
        p_bit = bin(val & row).count('1') % 2
        parity |= (p_bit << i)
    return parity

def main():
    parser = argparse.ArgumentParser(description="Split flat hex file into interleaved SRAM bank files.")
    parser.add_argument("input_hex", help="Input hex file path")
    parser.add_argument("output_dir", help="Output directory path")
    parser.add_argument("--base-addr", required=True, help="Base address of memory (e.g. 0x78000000)")
    parser.add_argument("--num-groups", type=int, default=2, help="Number of bank groups")
    parser.add_argument("--data-width", type=int, default=64, help="AXI data width in bits")
    parser.add_argument("--bank-width", type=int, default=32, help="SRAM bank width in bits")
    parser.add_argument("--mem-size", required=True, help="Memory size in bytes (e.g. 0x200000)")
    parser.add_argument("--num-banks-per-group", type=int, help="Total number of physical banks per group")
    parser.add_argument("--ecc-scheme", help="ECC scheme to use (e.g. secded_39_32)")
    parser.add_argument("--ecc-dir", help="Directory containing custom ECC scheme files")
    
    args = parser.parse_args()
    
    if args.ecc_scheme:
        ecc_matrix = load_ecc_scheme(args.ecc_scheme, args.ecc_dir)
    else:
        ecc_matrix = None

    def parse_int(val):
        if val.lower().startswith('0x'):
            return int(val, 16)
        return int(val)
        
    base_addr = parse_int(args.base_addr)
    mem_size = parse_int(args.mem_size)
    num_groups = args.num_groups
    data_width = args.data_width
    bank_width = args.bank_width
    
    if data_width % bank_width != 0:
        print(f"Error: data-width ({data_width}) must be a multiple of bank-width ({bank_width})")
        sys.exit(1)
        
    num_lanes = data_width // bank_width
    if args.num_banks_per_group:
        num_banks_per_group = args.num_banks_per_group
    else:
        num_banks_per_group = num_lanes
        
    depth = num_banks_per_group // num_lanes
    sram_num_words = (mem_size // (num_groups * num_banks_per_group)) // (bank_width // 8) if depth > 1 else 0
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        
    byte_memory = {}
    current_addr = 0
    
    with open(args.input_hex, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('@'):
                current_addr = int(line[1:], 16)
            else:
                bytes_list = line.split()
                for b in bytes_list:
                    byte_memory[current_addr] = int(b, 16)
                    current_addr += 1
                    
    if not byte_memory:
        print("Empty hex file!")
        sys.exit(0)
        
    banks = {g: {b: {} for b in range(num_banks_per_group)} for g in range(num_groups)}
    
    step = data_width // 8
    num_axi_words = mem_size // step
    
    for w in range(num_axi_words):
        rel_addr = w * step
        addr = base_addr + rel_addr
        
        axi_word_val = 0
        has_data = False
        for byte_idx in range(step):
            b_addr = addr + byte_idx
            if b_addr in byte_memory:
                axi_word_val |= (byte_memory[b_addr] << (byte_idx * 8))
                has_data = True
                
        if not has_data:
            continue
            
        g = (rel_addr // step) % num_groups
        row_idx = rel_addr // (num_groups * step)
        
        if depth > 1:
            d = row_idx // sram_num_words
            bank_word_idx = row_idx % sram_num_words
        else:
            d = 0
            bank_word_idx = row_idx
            
        for l in range(num_lanes):
            slice_val = (axi_word_val >> (l * bank_width)) & ((1 << bank_width) - 1)
            b = d * num_lanes + l
            banks[g][b][bank_word_idx] = slice_val
            
    input_basename = os.path.basename(args.input_hex)
    name_parts = os.path.splitext(input_basename)
    
    for g in range(num_groups):
        for b in range(num_banks_per_group):
            filename = f"{name_parts[0]}_g{g}_b{b}{name_parts[1]}"
            filepath = os.path.join(args.output_dir, filename)
            
            with open(filepath, 'w') as f:
                bank_data = banks[g][b]
                if bank_data:
                    for idx in sorted(bank_data.keys()):
                        f.write(f"@{idx:08x}\n")
                        if args.ecc_scheme:
                            word_val = bank_data[idx]
                            ecc_val = calculate_ecc(word_val, ecc_matrix)
                            ecc_bits = len(ecc_matrix)
                            out_val = (ecc_val << bank_width) | word_val
                            out_width = bank_width + ecc_bits
                            num_chars = (out_width + 3) // 4
                            f.write(f"{out_val:0{num_chars}x}\n")
                        else:
                            num_chars = bank_width // 4
                            f.write(f"{bank_data[idx]:0{num_chars}x}\n")
                else:
                    if args.ecc_scheme:
                        ecc_bits = len(ecc_matrix)
                        num_chars = (bank_width + ecc_bits + 3) // 4
                        f.write(f"@00000000\n{'0'*num_chars}\n")
                    else:
                        num_chars = bank_width // 4
                        f.write(f"@00000000\n{'0'*num_chars}\n")
                        
    print("Split completed successfully.")

if __name__ == '__main__':
    main()

<%namespace file="/license_header.mako" import="license"/>\
${license(prefix='#')}\
# ==============================================================================
# OLLIVANDER AUTO-GENERATED SOFTWARE MAKEFILE
# ==============================================================================

<%
import struct
sw_cfg = config.get("software_stack", {})
toolchain = sw_cfg.get("toolchain", "riscv64-unknown-elf-")
app_name = sw_cfg.get("test_app", {}).get("name", "hello_world")
%>
CC      = ${toolchain}gcc
OBJCOPY = ${toolchain}objcopy
OBJDUMP = ${toolchain}objdump

<%
  # simulation.firmware knobs (soc_schema.py): raw flag lists. cflags REPLACES the
  # optimization/debug tail of the host line (the ISA/ABI/cmodel triplet stays
  # derived from the host component - it describes hardware, not preference);
  # ldflags APPENDS to the link line; cluster_cflags REPLACES the offload
  # payload's -O2 -g. Absent section = today's text, byte for byte.
  def _fw(key, default):
      s = getattr(config, "simulation", None)
      f = getattr(s, "firmware", None) if s else None
      v = getattr(f, key, None) if f else None
      return " ".join(v) if v else default
  fw_cflags  = _fw("cflags", "-g -O0")
  fw_ldflags = _fw("ldflags", "")
  fw_cluster = _fw("cluster_cflags", "-O2 -g")
%>\
# Default compilation flags for Host (dynamic based on ISA/ABI/cmodel)
CFLAGS  = -march=${config.host.isa or "rv64imafdc"} -mabi=${config.host.abi or "lp64d"} -mcmodel=${config.host.cmodel or "medany"} -ffunction-sections -fdata-sections ${fw_cflags}
LDFLAGS = -T linker.ld -nostartfiles -Wl,--gc-sections${" " + fw_ldflags if fw_ldflags else ""}

.PHONY: all clean
<%
_boot_mode = (config.get("testbench", {}) or {}).get("boot_mode", "force")
_autonomous = _boot_mode in ("spi_flash", "i2c_eeprom")
_hf = comp_info.get(config.host.name, {}).get("fixed_params", {}) if _autonomous else {}
_zsl_guid = str(_hf.get("BootZslTypeGuid", "")).strip('"\'')
_img_lba  = int(str(_hf.get("BootImgPayloadLba", "42")).strip('"\'')) if _autonomous else 42
_img_pad  = int(str(_hf.get("BootImgPadLbas", "85")).strip('"\'')) if _autonomous else 85
%>\
% if _autonomous:
all: ${app_name}.hex ${app_name}.gpt.memh
% else:
all: ${app_name}.hex
% endif

% if app_name == "offload":
# ------------------------------------------------------------------------------
# Offload payloads - one leg per target, all from the same generic source.
# ------------------------------------------------------------------------------
# Each target's payload is cross-compiled for the ISA/ABI its Offload* contract
# declares (the host toolchain provides them as multilibs - a documented
# prerequisite of the offload app), linked at the shared payload region, then
# flattened and embedded into the host firmware as a C header by bin2header.py,
# which the generator drops next to this Makefile: the whole flow is contained
# in the generated tree. bin2header.py is stdlib-only, any python3 works.
PYTHON ?= python3

% for t_name, t in offload_targets.items():
<%
# The contract kind selects both the payload's code path (-DOFFLOAD_MM) and where
# its results travel: through the control unit's registers (control_wire) or
# through a return-slot array in the cluster-local memory (memory_mapped).
ctrl_base = t["base_addr"] + t["ctrl_offs"]
# The PAYLOAD's view of its own cluster: multi-instance targets declare an alias
# base (OffloadLocalBase) at which every instance sees ITSELF, so one image serves
# the whole array; targets without one decode their own global base internally.
local_base = t.get("local_base", t["base_addr"])
common = [
    f'-DOFFLOAD_STACK_TOP={hex(local_base + t["stack_offs"])}',
    f'-DOFFLOAD_CHECK_N={offload_check_n}',
    f'-DOFFLOAD_CHECK_XOR={hex(offload_check_xor)}',
]
if t["contract"] == "control_wire":
    specific = [
        f'-DOFFLOAD_RETURN_ADDR={hex(ctrl_base + t["return_offs"])}',
        f'-DOFFLOAD_EOC_ADDR={hex(ctrl_base + t["eoc_offs"])}',
    ]
else:
    specific = [
        '-DOFFLOAD_MM=1',
        f'-DOFFLOAD_RETURN_ADDR={hex(local_base + t["return_offs"])}',
        f'-DOFFLOAD_HART_BASE={hex(t.get("hart_base", 0))}',
        # Secondary cores return this distinctive code (see rtl_generator's
        # single-source comment); the host firmware checks it per-core, exactly.
        f'-DOFFLOAD_SECONDARY_CODE={hex(offload_secondary_code)}',
    ]
    if t.get("collective_test"):
        # Global addresses of instance 0's stamped windows: writing them makes
        # the network reduce (IntAdd) or barrier (LsbAnd) across the group.
        specific += [
            # One switch the payload keys the whole collective section on: the
            # phases inside it are then selected by their own defines.
            '-DOFFLOAD_COLLECTIVE_PHASE=1',
            f'-DOFFLOAD_BARRIER_ADDR={hex(t["coll_alias_base"] + t["barrier_offs"])}',
            # Local (own-range) view of the meta word: every core0 reads its
            # role without touching the network.
            f'-DOFFLOAD_COLL_META_LOCAL={hex(local_base + t["coll_meta_offs"])}',
        ]
        if t.get("collective_reduce"):
            specific += [
                f'-DOFFLOAD_COLLECT_ADDR={hex(t["coll_alias_base"] + t["collect_offs"])}',
                f'-DOFFLOAD_COLL_COL_LOCAL={hex(local_base + t["collect_col_offs"])}',
                # REAL global address of the final slot, for the pre-barrier read
                # poll: reads must NOT travel through the alias (the stamper only
                # rewrites AW hits, and an aliased AR would reach the SAM undecoded).
                f'-DOFFLOAD_COLLECT_READ_ADDR={hex(t["base_addr"] + t["collect_offs"])}',
            ]
            if t.get("two_phase"):
                # Only a real 2D grid gets the column window; a degenerate (1D)
                # group reduces straight onto the final slot.
                specific += [
                    f'-DOFFLOAD_COLLECT_COL_ADDR={hex(t["coll_alias_base"] + t["collect_col_offs"])}',
                ]
        if t.get("collective_wide"):
            # The wide reduction, in TWO dimension-ordered phases like the narrow
            # one (a sequential reduction merges at most two contributions per
            # router): every member sends its lanes to its column head's landing
            # with the COLUMN mask, then the heads send the column sums to
            # instance 0 with the ROW mask, a barrier in between. No alias on this
            # channel: a write whose user carries a non-zero mask leaves the
            # cluster through the SoC port whatever its address, so the DMA
            # targets REAL landings and instance 0's own contribution enters the
            # network too. The column head's address comes from a host-written
            # mailbox, the payload knowing neither its base nor its column.
            _two = t.get("two_phase") and t.get("y_mask")
            _user_col = ((t["y_mask"] if _two else t["group_mask"]) << 4) | 0x3   # {mask, FpAdd}
            _user_row = (t["x_mask"] << 4) | 0x3
            _lane_hi = [struct.unpack('<II', struct.pack('<d', float(k + 1)))[1] for k in range(8)]
            _ydim = t.get("y_dim") or 1
            _exp_col0_hi = struct.unpack('<II', struct.pack('<d', float(_ydim if _two else t["num_instances"])))[1]
            _exp0_hi = struct.unpack('<II', struct.pack('<d', float(t["num_instances"])))[1]
            specific += [
                '-DOFFLOAD_WIDE_RED=1',
                f'-DOFFLOAD_DMA_HART={t["dma_hart"]}',
                f'-DOFFLOAD_WIDE_SRC_LOCAL={hex(local_base + t["wide_src_offs"])}',
                f'-DOFFLOAD_WIDE_LANDING_LOCAL={hex(local_base + t["wide_offs"])}',
                f'-DOFFLOAD_WIDE_COLDST_LOCAL={hex(local_base + t["wide_col_dst_offs"])}',
                f'-DOFFLOAD_WIDE_DST_ADDR={hex(t["base_addr"] + t["wide_offs"])}',
                '-DOFFLOAD_WIDE_BYTES=64',
                f'-DOFFLOAD_WIDE_USER_COL_LO={hex(_user_col & 0xFFFFFFFF)}',
                f'-DOFFLOAD_WIDE_USER_COL_HI={hex(_user_col >> 32)}',
                f'-DOFFLOAD_WIDE_USER_ROW_LO={hex(_user_row & 0xFFFFFFFF)}',
                f'-DOFFLOAD_WIDE_USER_ROW_HI={hex(_user_row >> 32)}',
                # Handshake words: the upper halves of the meta and multicast beats,
                # otherwise unwritten (they were the source of the dcache X reads).
                f'-DOFFLOAD_WIDE_GO_LOCAL={hex(local_base + t["coll_meta_offs"] + 4)}',
                f'-DOFFLOAD_WIDE_DONE_LOCAL={hex(local_base + t["mcast_offs"] + 4)}',
                f'-DOFFLOAD_WIDE_EXP_COL0_HI={hex(_exp_col0_hi)}',
                f'-DOFFLOAD_WIDE_EXP0_HI={hex(_exp0_hi)}',
            ] + [f'-DOFFLOAD_WIDE_LANE_HI_{k}={hex(v)}' for k, v in enumerate(_lane_hi)]
            if _two:
                specific += ['-DOFFLOAD_WIDE_TWO_PHASE=1']
        elif t.get("dma_hart") is not None:
            # B1 probe: a bare 512-bit burst, no collective. Both ends are the
            # contract's wide slot - the cluster's own copy through the alias
            # (every instance sees itself there) and instance 0's through its
            # window - so the transfer stays inside memory the contract owns and
            # both ends are 64-byte aligned, which is what makes iDMA emit one
            # full wide beat instead of strobed narrow ones.
            specific += [
                f'-DOFFLOAD_WIDE_PROBE=1',
                f'-DOFFLOAD_DMA_HART={t["dma_hart"]}',
                f'-DOFFLOAD_WIDE_SRC_LOCAL={hex(local_base + t["wide_offs"])}',
                f'-DOFFLOAD_WIDE_DST_ADDR={hex(t["base_addr"] + t["wide_offs"])}',
                '-DOFFLOAD_WIDE_BYTES=64',
            ]
        if t.get("collective_mcast"):
            specific += [
                f'-DOFFLOAD_MCAST_ADDR={hex(t["coll_alias_base"] + t["mcast_offs"])}',
                f'-DOFFLOAD_MCAST_LOCAL={hex(local_base + t["mcast_offs"])}',
                '-DOFFLOAD_MCAST_VALUE=0x5A11ED00',
            ]
payload_defines = " ".join(common + specific)
%>\
# Target '${t_name}': ${t["isa"]}/${t["abi"]}, registers via the '${t["contract"]}' contract.
payload_${t_name}.elf: payload_main.c payload.ld
	$(CC) -march=${t["isa"]} -mabi=${t["abi"]} -mcmodel=medlow ${fw_cluster} -ffreestanding -nostartfiles -nostdlib -T payload.ld ${payload_defines} -o $@ payload_main.c

payload_${t_name}.bin: payload_${t_name}.elf
	$(OBJCOPY) -O binary $< $@

payload_${t_name}.h: payload_${t_name}.bin
	$(PYTHON) bin2header.py --binary $< --output $@ --symbol payload_${t_name} --base ${hex(offload_payload_base)}

% endfor
# The host firmware embeds every payload header.
${app_name}.elf: main.c ${" ".join(f"payload_{t}.h" for t in offload_targets)}
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ main.c
% else:
${app_name}.elf: main.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
% endif

# The flat hex must be ONE contiguous span: the generated testbench's SBA
# preload packs it with a num()-based word count, which silently truncates
# the tail if the @-blocks have a gap. objcopy emits one block per section,
# and section ALIGNMENT leaves real slivers between them (on crux, 6 bytes
# between two adjacent section blocks), so --gap-fill closes them with zeros -
# the same bytes a debugger-side loader would write. The awk check stays as
# the contract's enforcer: it fails the BUILD on any residual gap, instead
# of a runtime check in the testbench, where the robust SV constructs crash
# Verilator 5.050's threaded scheduler (see tb_soc.sv.mako, image load).
% if _autonomous:
# The autonomous boot image: a GPT whose second partition carries
# the firmware under the type GUID the bootrom scans for (the host contract's
# BootZslTypeGuid) - upstream cheshire's own test-image recipe, dummy
# partitions included, so the GPT parsing is exercised and not just humored.
# sgdisk lives in /usr/sbin on this host class, often outside make's PATH.
SGDISK ?= $(shell command -v sgdisk || echo /usr/sbin/sgdisk)

${app_name}.gpt.bin: ${app_name}.elf
	$(OBJCOPY) -O binary $< ${app_name}.flash.raw
	rm -f $@
	truncate -s $$(( ($$(stat --printf="%s" ${app_name}.flash.raw)/512 + ${_img_pad})*512 )) $@
	$(SGDISK) -Z --clear -g --set-alignment=1 --new=1:37:$$((${_img_lba}-2)) --new=2:${_img_lba}:-9 --typecode=2:${_zsl_guid} --new=3:-5:-2 $@ > /dev/null
	dd if=${app_name}.flash.raw of=$@ bs=512 seek=${_img_lba} conv=notrunc 2> /dev/null

${app_name}.gpt.memh: ${app_name}.gpt.bin
	$(OBJCOPY) -I binary -O verilog $< $@

% endif
${app_name}.hex: ${app_name}.elf
	$(OBJCOPY) -O verilog --gap-fill 0x00 $< $@
	@awk '/^@/ { a = strtonum("0x" substr($$1, 2)); \
	             if (expect && a != expect) { \
	               printf "ERROR: %s: @%x does not continue @%x - the image has a gap or overlap, the SBA preload would truncate it\n", \
	                      FILENAME, a, expect > "/dev/stderr"; exit 1; } \
	             expect = a; next } \
	           { expect += NF }' $@

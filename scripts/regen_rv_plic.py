#!/usr/bin/env python3
"""
Regenerate the Cheshire host's PLIC with Cheshire's own recipe, sized for THIS host.

WHY. The rv_plic that reaches the compile list is opentitan_peripherals' checked-in default:
32 sources, 1 target. Cheshire's own build (cheshire.mk, target `.generated`) replaces it by
copying its `hw/rv_plic.cfg.hjson` into opentitan_peripherals and running `make otp` - ipgen
plus OpenTitan's regtool - and cheshire_soc feeds the PLIC with `intr_routed[NumSrc-1:0]` of
its `{external, internal}` interrupt vector. With the default 32 the PLIC saw the first 32
INTERNAL sources only: no `intr_ext_i` line ever reached it, in any generated SoC, and the
S-mode target did not exist. Astral (carfield.mk, `update_plic`) fixes it exactly this way:
two `sed` on Cheshire's configuration, then Cheshire's regeneration. This script is that,
run from the registry as a pre-build command of the cheshire dependency.

WHAT IT KNOWS, AND FROM WHERE. Everything Cheshire-specific comes from Cheshire's own
configuration file AS FETCHED (`git show HEAD:` in the Bender checkout, so a previous run's
edit is never mistaken for the original - the side-copy first tried was made after such an
edit and doubled the count): its `src` is Cheshire's internal source count (the PLIC
upstream is sized to exactly the internal interrupts) and its `target` is the number of
contexts per hart (two, M and S). The generator hands over the
host's side through the generic `{host.<Parameter>}` substitution: the external interrupt
count (NumIntrsIn, the capacity cheshire_isle.sv declares), the core count and the external
interruptible harts. Sources = internal + external; targets = contexts x (cores + external
harts). No number is repeated anywhere else.

Idempotent: when the generated package already carries the requested counts nothing runs, so
a repeated `make generate` stays fast and offline.

Usage: regen_rv_plic.py <bender_work> --num-ext-irqs N --num-cores C --num-ext-irq-harts H
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _cfg_value(text: str, key: str) -> int:
    m = re.search(rf"^\s*{key}:\s*(\d+)", text, re.M)
    if not m:
        raise ValueError(f"'{key}:' not found in cheshire's rv_plic.cfg.hjson - its layout changed")
    return int(m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate cheshire's PLIC for this host")
    ap.add_argument("bender_work")
    ap.add_argument("--num-ext-irqs", type=int, required=True, help="external interrupt lines of the host (NumIntrsIn)")
    ap.add_argument("--num-cores", type=int, required=True, help="cores of the host (NumCores)")
    ap.add_argument("--num-ext-irq-harts", type=int, required=True, help="external interruptible harts (NumIrqHarts)")
    a = ap.parse_args()

    bw = Path(a.bender_work)
    chs_cfg = bw / "cheshire" / "hw" / "rv_plic.cfg.hjson"
    otp = bw / "opentitan_peripherals"
    regtool_dir = bw / "register_interface" / "vendor" / "lowrisc_opentitan" / "util"
    ipgen = otp / "util" / "ipgen.py"
    for p in (chs_cfg, ipgen, regtool_dir / "regtool.py"):
        if not p.exists():
            print(f"  [ERROR] regen_rv_plic: {p} is missing - the fetched trees do not match the recipe")
            return 1

    # Cheshire's own numbers, from the file AS FETCHED: the checkout's committed copy, which no
    # earlier run of this script can have touched.
    try:
        orig = subprocess.run(["git", "-C", str(bw / "cheshire"), "show", "HEAD:hw/rv_plic.cfg.hjson"],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  [ERROR] regen_rv_plic: cannot read cheshire's committed rv_plic.cfg.hjson ({e})")
        return 1
    try:
        internal = _cfg_value(orig, "src")
        ctx_per_hart = _cfg_value(orig, "target")
    except ValueError as e:
        print(f"  [ERROR] regen_rv_plic: {e}")
        return 1
    num_src = internal + a.num_ext_irqs
    num_target = ctx_per_hart * (a.num_cores + a.num_ext_irq_harts)

    pkg = otp / "src" / "rv_plic" / "rtl" / "rv_plic_reg_pkg.sv"

    def counts(text: str):
        s = re.search(r"parameter int NumSrc\s*=\s*(\d+)", text)
        t = re.search(r"parameter int NumTarget\s*=\s*(\d+)", text)
        return (int(s.group(1)) if s else None, int(t.group(1)) if t else None)

    if pkg.exists() and counts(pkg.read_text()) == (num_src, num_target):
        print(f"  -> regen_rv_plic: rv_plic already generated for {num_src} sources and {num_target} targets")
        return 0

    # 1. Cheshire's configuration with this host's counts (Astral's two sed lines).
    new = re.sub(r"^(\s*src:\s*)\d+", rf"\g<1>{num_src}", orig, count=1, flags=re.M)
    new = re.sub(r"^(\s*target:\s*)\d+", rf"\g<1>{num_target}", new, count=1, flags=re.M)
    chs_cfg.write_text(new)

    # 2. The IP's own recipe (opentitan_peripherals/otp.mk, target otp_rv_plic), verbatim.
    dst_cfg = otp / "src" / "rv_plic" / "rv_plic.cfg.hjson"
    shutil.copyfile(chs_cfg, dst_cfg)
    gen = otp / "src" / "rv_plic" / "gen"
    shutil.rmtree(gen, ignore_errors=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{regtool_dir}:{env.get('PYTHONPATH', '')}"
    cmd = [sys.executable, str(ipgen), "generate",
           "-C", str(otp / "src" / "rv_plic" / "tpl" / "rv_plic"),
           "-o", str(gen), "-c", str(dst_cfg)]
    try:
        subprocess.run(cmd, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] regen_rv_plic: ipgen failed\n{e.stdout}")
        return 1
    for item in gen.iterdir():
        target = otp / "src" / "rv_plic" / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(item, target)
    shutil.rmtree(gen, ignore_errors=True)

    got = counts(pkg.read_text()) if pkg.exists() else (None, None)
    if got != (num_src, num_target):
        print(f"  [ERROR] regen_rv_plic: the regenerated package reports {got}, not ({num_src}, {num_target})")
        return 1
    print(f"  -> regen_rv_plic: rv_plic regenerated for {num_src} sources ({internal} internal + "
          f"{a.num_ext_irqs} external) and {num_target} targets ({ctx_per_hart} contexts x "
          f"{a.num_cores + a.num_ext_irq_harts} harts); the fetched default was 32 and 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())

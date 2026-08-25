#!/usr/bin/env python3
"""
Check that a HOST-PROVIDED tool an IP's own generation flow needs is present.

Some IPs are not consumed as plain RTL: they generate part of themselves with
their own toolchain (spatz compiles its cluster bootrom for rv32, snitch_cluster
generates RTL with a specific LLVM). Those compilers are host prerequisites -
Ollivander deliberately does not fetch them, because toolchain provisioning on
shared machines belongs to whoever administers them - so the only thing this
flow owes the user is a CLEAR failure: which tool, where it was looked for, why
it is needed, and how to point somewhere else.

Without that, the failure surfaces as the IP's own Makefile reporting a missing
binary several commands deep, with nothing naming the tool or the override.

Each tool declares one entry below: the environment variable that relocates it,
the site default, the binary that must be executable, and the reason it exists.
Used from the dependency registry as

    $(PYTHON) {ollivander_dir}/scripts/host_tools.py <name>

and importable, so a script that already knows whether a flow will run at all
can perform the same check at exactly the right moment:

    from host_tools import require, resolve
"""

import os
import sys
from pathlib import Path

TOOLS = {
    "spatz-gcc": {
        "env": "SPATZ_GCC_DIR",
        "default": "/opt/riscv/spatz-gcc-7.1.1",
        "binary": "bin/riscv32-unknown-elf-gcc",
        "why": "spatz compiles its cluster bootrom for rv32, which the host's "
               "riscv64 toolchain (software_stack.toolchain) does not provide",
    },
    "snitch-llvm": {
        "env": "SNITCH_LLVM_DIR",
        "default": "/opt/riscv/snitch-llvm-15.0.0-snitch-0.2.0",
        "binary": "bin/clang",
        "why": "snitch_cluster generates its RTL with its own LLVM, whose clang "
               "the generator invokes as riscv32-unknown-elf-clang",
    },
}


def resolve(name):
    """The directory this tool should live in: the override, else the default."""
    spec = TOOLS[name]
    return Path(os.environ.get(spec["env"]) or spec["default"])


def require(name):
    """Return the tool's directory, or exit(1) naming what is missing and why."""
    if name not in TOOLS:
        print(f"[ERROR] host_tools: unknown tool '{name}'. Declared: "
              f"{', '.join(sorted(TOOLS))}", file=sys.stderr)
        sys.exit(1)
    spec = TOOLS[name]
    root = resolve(name)
    binary = root / spec["binary"]
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        print(f"[ERROR] Host tool '{name}' is missing: no executable "
              f"'{spec['binary']}' under {root}.", file=sys.stderr)
        print(f"        It is needed because {spec['why']}.", file=sys.stderr)
        print(f"        Install it (it is provisioned outside this repository) or set "
              f"{spec['env']} to a directory that has it.", file=sys.stderr)
        sys.exit(1)
    return root


def main():
    """`<name>` checks and reports; `--path <name>` checks and prints the bare
    directory, so a command that must PASS the path to a Makefile can substitute
    it instead of repeating the default - one definition, here."""
    args = sys.argv[1:]
    if args[:1] == ["--path"] and len(args) == 2:
        print(require(args[1]))
        return
    if len(args) != 1:
        print(f"usage: host_tools.py [--path] <{'|'.join(sorted(TOOLS))}>", file=sys.stderr)
        sys.exit(1)
    root = require(args[0])
    print(f"  -> host tool '{args[0]}': {root}")


if __name__ == "__main__":
    main()

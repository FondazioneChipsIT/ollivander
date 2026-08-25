#!/usr/bin/env python3
"""
Prepare the LLVM snitch_cluster's RTL generator expects to find on PATH.

Invoked from the dependency registry as a pre-build command, before `make rtl`:

    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/prep_snitch_llvm.py"

The IP generates part of its own RTL and calls the compiler as
`riscv32-unknown-elf-clang`, a name the snitch LLVM distribution does not ship:
it provides plain `clang`. So a directory of symlinks is built next to the
project and prepended to PATH by the command that follows, with the expected
name pointing at the real binary.

Two reasons this is a script rather than a line of shell in the registry: the
compiler is a HOST PREREQUISITE whose absence must be reported clearly (which
tool, where it was looked for, why, and how to relocate it - scripts/host_tools.py
owns all four), and a diagnostic like that does not fit in a YAML string without
becoming unreadable and untestable. Checking BEFORE creating the links also
matters: a symlink farm built from a missing directory succeeds quietly and the
failure resurfaces later as a compiler that cannot be found.
"""

import os
import sys
from pathlib import Path

from host_tools import require

LINK_DIR = Path(".tmp_llvm_bin")
EXPECTED_NAME = "riscv32-unknown-elf-clang"


def main():
    llvm_bin = require("snitch-llvm") / "bin"
    LINK_DIR.mkdir(parents=True, exist_ok=True)
    for entry in sorted(llvm_bin.iterdir()):
        link = LINK_DIR / entry.name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(entry)
    # The name the generator actually invokes, aliased onto plain clang.
    alias = LINK_DIR / EXPECTED_NAME
    if alias.is_symlink() or alias.exists():
        alias.unlink()
    alias.symlink_to(llvm_bin / "clang")
    print(f"  -> snitch LLVM ready in {LINK_DIR}/ ({EXPECTED_NAME} -> clang), "
          f"from {llvm_bin}")


if __name__ == "__main__":
    main()

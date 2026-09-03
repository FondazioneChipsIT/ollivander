# Debugging a failing generation or simulation

Which log answers which question. Everything below lives under `<project>/logs/`, created by `build-sim` / `run-sim`; `logs/generated` is a symlink to `../generated`, so the testbench's relative paths (the hex preload files) resolve while the simulator runs from `logs/`.

| file | what it answers |
| --- | --- |
| `compile.log` | `vlog` output of `build-sim` — the first place to look for an elaboration error |
| `fast_compile.log`, `fast_check.log` | stub compilation and blackbox elaboration of `fast-check` |
| `transcript` | full `run-sim` transcript: UART output, `[TB_*]` monitors, where `$finish` happened |
| `verilator_transcript` | the same for `run-sim-verilator`, with the same pass criterion |
| `trace_core_*.log`, `trace_hart_*.log` | RISC-V commit traces emitted by the core IPs. **They append across runs** — check the timestamps before reading them as the current run's |
| `test_generate.log`, `test_fastcheck_<tool>.log`, `test_build_sim.log`, `test_run_sim.log` | per-step logs written by `make test-all` |
| `soc_cfg_examples/test_summary.log` | PASS/FAIL summary of the last `make test-all`, with the scope of the run in its header |
| `logs/debug/debug_vsim.txt`, `logs/debug/debug_testbench.txt` | dumped by `sim.mk.mako` at *generation* time: how preload memories and their parameters were resolved |

**Suite runs overwrite these in place** (`make test-all` removes `logs/` per project at startup), so anything worth comparing against must be copied out before the next run.

**Batch runs dump no waveform.** For waveforms use `make gui`, then log signals interactively (`log -r /*` before `run -all`); `*.wlf` / `*.vcd` / `*.fst` are git-ignored.

## The pass criterion

A simulation passes when the run log contains `[UART]:` output **and** the testbench prints `[TB] EOT received. Simulation finished.` Both are required: a run that reaches EOT without UART output has booted nothing, and one with UART output but no EOT has not finished.

## Reading a failure

**A crash before the first display line is almost never the design.** In a Verilator model it is the object cache: `ccache` older than 4 poisons precompiled-header builds and returns objects compiled against a stale layout, so the model is allocated smaller than the class that constructs it and the binary segfaults inside a constructor. The tells are a crash with no output, a backtrace in innocent generated code, determinism across rebuilds that wipe the work directory, and healing under `CCACHE_DISABLE=1`. Check which `ccache` is on `PATH` before touching the RTL (`docs/developer/wip/future_evolution_tasks.md` section 5.2.3 has the full history).

**Silence is not a stall.** Before concluding that a run is stuck, measure progress: the transcript's modification time, the `[TB_TIME]` heartbeat, the simulated time advancing. Firmware phases have long quiet stretches, and healthy runs have been killed on the assumption that quiet meant hung. Two instruments narrow the question on an offload run (testbench guide): the last `[PROGRESS]` phase code says which phase a quiet run is in, and the `+progress` link-activity grid says what the mesh is doing there - a tile beating high while its neighbours sit at zero is a poll that will not end (something it waits for is not coming), a grid at zero is a real stall. A wrong reduction result no longer looks like either: since the payload waits for a landing to leave its sentinel rather than for an exact value, the host reports `[COLLECTIVE] <target> collect=<value> (expected <value>) ...` as soon as it lands, instead of running to the watchdog.

**A hung AXI read has nothing to time out against.** When the firmware addresses a block whose clock is gated, the transaction never completes and no software poll limit can fire: the symptom is total silence until the testbench's own `sim_timeout_ns`. If a run goes quiet right after a power-management step, suspect an access to a parked block rather than a logic error.

**Compare the two simulators before blaming the design.** QuestaSim and Verilator legitimately differ in the ordering of zero-time events. A defect visible in one and not the other is usually a testbench that depends on that ordering — for instance a `$readmemh` serialized on a DUT reset that takes several transitions within the same instant.

**A testbench agent's liveness check fails OPEN under X.** `if (idcode != expected)` with an all-X read compares X against a constant and does not fire, so the agent sails on into an unpowered or unexported interface (the 2026-08-16 jtag bring-up debug: all-X DMI reads from a host that did not export `"jtag"` — now refused at generation time). If an agent "checked" something and the run still walks into X-land, suspect the check's polarity under X before suspecting the DUT.

**A compilation unit without a `timescale` gets the simulator's resolution as its time unit under Questa** — the suppressed warning-3009 class. The VIP's TCK once ran at 20 ps and riscv-dbg's driver sampled TDO one cycle early because of it; `sim.mk.mako` now passes `-timescale 1ns/1ps` to every `vlog` as the default. When agent timing looks impossibly wrong, check which timescale the unit actually received before reading waveforms.

**The riscv-dbg DTM silently drops a DMI request issued while the previous one is still crossing its CDC**, and a fire-and-forget `write_dmi` never sees the sticky busy error — the VIP's `write_dmi_safe` parks in Run-Test/Idle after every write for exactly this reason. If JTAG writes vanish without any error, suspect request pacing, not the register.

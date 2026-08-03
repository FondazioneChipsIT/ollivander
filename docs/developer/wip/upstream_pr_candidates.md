# Upstream Pull-Request Candidates

Every defect found in an external IP that deserves fixing at its source, in one place. The registry patches in `ollivander_config.yml` and the pre-build scripts are *our* remedies and keep working regardless; this list tracks the half of the work that belongs upstream, so it survives the session that discovered it. When a PR is filed or merged, update the status; when the fix lands in a revision we pin, drop the corresponding patch and the entry together.

A lesson recorded with the list, learned on 2026-08-03: **verify a defect at the repository's HEAD before calling it a PR candidate.** A defect upstream has already fixed calls for a pin bump, not a PR; and one upstream never had — because its requirement matrix differs from ours — is not theirs to fix. Both cases looked identical to the session that found them.

## Candidates toward pulp-platform (and neighbours)

| Repository | Defect | Our remedy today | Verified at HEAD | Status |
| :--- | :--- | :--- | :--- | :--- |
| `cva6` | The scalar-cryptography sources are missing from the Bender manifest, so the aes unit does not compile from a clean checkout | `scripts/patch_cva6_aes.py` compiles them, renaming to `cva6_aes_*` where opentitan also declares an `aes` | 2026-07-29 (found) | candidate |
| `cheshire` | `cheshire_pkg.sv` assigns `ret.slink` only under `if (cfg.SerialLink)` yet sets `ret.apb_mask[ret.slink]` unconditionally: with the link disabled the mask of an unrelated peripheral is raised and `reg_out_rsp[0]` is driven twice (vopt-7045) | registry patch guarding the assignment | 2026-07-29 (found) | candidate |
| `axi_obi` | `axi_to_obi.sv` slices `rsp_ruser[IdRuserWidth-1:ObiCfg.IdWidth]`, degenerate (reversed range) whenever `RUserWidth == 0` | registry patch guarding the two assigns | 2026-07-30 (found) | candidate |
| `obi` | `obi_to_apb.sv` uses the assertion macros without the `OBI_ASSERTS_OFF` guard its twin `apb_to_obi.sv` has | registry patch adding the guard | 2026-08-03, `main` (17 commits past our pin) still unguarded | candidate |
| `hier-icache` | The SVA property block in `share_icache.sv` is guarded by `ifndef SYNTHESIS` alone; the `##[0:1]` cycle-delay range is unparsable by Verilator | registry patch nesting an `ifndef VERILATOR` guard | 2026-08-03, our pin **is** HEAD (last activity 2025-02) | candidate |
| `neureka` | `neureka_ctrl.sv` uses `9'h0ffffffff`, a 36-bit literal in a 9-bit case item; simulators that do not truncate silently refuse it | registry patch replacing it with the equivalent `9'h1ff` | 2026-08-03, still present at HEAD | candidate |
| `floo_noc` | `floo_nw_join` derives its internal ID-converter ports from the numeric `AxiCfg*` structs while its own ports carry the handed-in channel types; nothing enforces their agreement (module hygiene — see `future_evolution_tasks.md`, section 3.4) | none needed: everything Ollivander emits keeps the two consistent | 2026-07-30 (analysis) | candidate |
| `floo_noc` | With collectives enabled the `collect_op_e` enum is assigned from a raw 4-bit vector without a cast (~250 messages per run, the reason message 8386 is suppressed); no check that a flit carries a legal opcode | suppression of message 8386, volume only | 2026-07-28 (found) | candidate |

## Alignments toward the CHIPS-IT forks (not upstream defects)

| Repository | Change | Why it is ours |
| :--- | :--- | :--- |
| `FondazioneChipsIT/pulp_cluster` | Remove the seven dead geometry overrides (`AWC`, `DW_LIC`, `DW_SIC`, `AWH`, `DWH`, `OWH`, `AWM`) and the four `boffs`/`lrdy` interface ties in `cluster_interconnect_wrap.sv` / `idma_wrap.sv` | pulp-platform's master still carries these lines, consistently with the older hci *it* requires; the mismatch is created by our hci forcing, so the fix belongs next to it |
| `cva6` (vendor refresh, not a patch-PR) | The two vendored copies of `common_cells/assertions.svh` predate the modern macro signatures and carry the old `PRIM_ASSERT_SV` include guard, so both macro sets parse in a single compilation unit and the last include wins | a vendored-copy staleness: the remedy is refreshing the vendor directory upstream or bumping our cva6 pin (constrained by cheshire), not patching the copies |

# Ollivander Environment Configuration Guide

Ollivander enforces a strict **Separation of Concerns**. While your main SoC YAML file describes *what* hardware to build (the topology, the components, the memory map), the **Environment Configuration YAML** describes *how* and *where* to build it.

The environment configuration tells Ollivander:
* Where to output the generated files.
* Where to search for custom templates and component wrappers.
* How to resolve, fetch, patch, and compile external IP dependencies (via Bender).

---

## 1. File Precedence

Ollivander uses a base configuration file, usually named `ollivander_config.yml`, located in the generator's root directory. **You should never modify this file directly.**

Instead, when integrating Ollivander into your project, you should create a project-specific environment file (e.g., `my_project_env.yaml`) and pass it to the generator using the `-a` (`--append-env`) flag:

```bash
make generate SOC_YAML=my_project.yaml ENV_YAML=my_project_env.yaml
```

Ollivander will automatically merge your custom environment file with the base one. If a path or a dependency is defined in both, **your custom file takes precedence**.

Both files are optional to *exist*, but neither is optional to *parse*: a YAML syntax error in either one stops the generator, naming the file and the position the parser reports. Skipping an unreadable file would be worse than stopping, because its paths and its forced resolutions would silently vanish and generation would continue with the defaults — surfacing much later as an output written to the wrong directory, or a package resolved to an unexpected revision.

---

## 2. Paths Configuration (`paths`)

The `paths` section defines directories for inputs and outputs. All relative paths are resolved relative to the location of the YAML file that defines them.

### Output Directories
| Field             | Type   | Default                 | Description                                            |
| :---------------- | :----- | :---------------------- | :----------------------------------------------------- |
| `outdir`          | String | `"generated"`           | The base directory where all output files will be      |
|                   |        |                         | written.                                               |
| `sub_hw`          | String | `"hw"`                  | Subdirectory for SystemVerilog RTL files.              |
| `sub_sw`          | String | `"sw"`                  | Subdirectory for C headers, linker scripts, and        |
|                   |        |                         | firmware binaries.                                     |
| `sub_doc`         | String | `"doc"`                 | Subdirectory for documentation and mapping CSVs.       |
| `sub_cfg`         | String | `"cfg"`                 | Subdirectory for tool configs (e.g., FlooGen YAMLs).   |
| `sub_reg`         | String | `"reg"`                 | Subdirectory for register specifications (HJSON).      |
| `sub_tb`          | String | `"tb"`                  | Subdirectory for generated testbenches.                |
| `bender_manifest` | String | `"{outdir}/Bender.yml"` | Path where the final Bender manifest will be generated.|
|                   |        |                         | The `{outdir}` placeholder is resolved dynamically.    |

### Input Search Paths
These define where Ollivander looks when you declare a component `type` or a `require` pragma.

| Field         | Type            | Default                       | Description                                  |
| :------------ | :-------------- | :---------------------------- | :------------------------------------------- |
| `templates`   | List of Strings | `["src/templates"]`           | Directories containing `.mako` templates.    |
| `components`  | List of Strings | `["components"]`              | Directories containing SystemVerilog IP      |
|               |                 |                               | wrappers (`*_isle.sv` or `*_tile.sv`). To    |
|               |                 |                               | inject your custom IPs, add your project's   |
|               |                 |                               | hardware folder here. Ollivander also looks  |
|               |                 |                               | in these paths for custom Padframe           |
|               |                 |                               | technology catalogs (`padframes/tech/`).     |
| `rdl_includes`| List of Strings | `[]`                          | Directories where PeakRDL should search for  |
|               |                 |                               | custom `.rdl` files. Files found here have   |
|               |                 |                               | absolute priority and will override external |
|               |                 |                               | IP registers with the same name.             |

**Example of appending custom paths:**
```yaml
paths:
  components:
    - "../hw_ips" # Search for custom wrappers in my project's hw_ips folder
  rdl_includes:
    - "custom_rdls" # Highest priority for PeakRDL includes
```

---

## 3. Dependency Registry (`dependencies`)

This section is the **Centralized Dependency Registry**. When an IP wrapper or a template requires an external repository (via the `// BENDER: name="my_ip"` pragma), Ollivander looks up `"my_ip"` in this dictionary to know where to fetch it and how to compile it.

Each key in the `dependencies` dictionary represents the name of the IP.

### 3.1 Git Resolution
| Field     | Type   | Description                                                                              |
| :-------- | :----- | :--------------------------------------------------------------------------------------- |
| `git`     | String | **Required**. The Git repository URL of the dependency.                                  |
| `version` | String | Specifies a semantic version to checkout (e.g., `"1.0.4"`).                              |
| `rev`     | String | Specifies a commit hash or tag to checkout (e.g., `"0ec0bf8"`).                          |

*(Note: You must specify either `version` or `rev`, but not both).*

Do not point `rev` at a branch name. A branch moves, so the build stops being reproducible; and a branch cannot satisfy the semantic-version ranges other IPs may express against the same package, which pushes the project into a forced resolution (section 4) for no reason. The catalogue shipped with Ollivander contains no branch references, deliberately: every entry is a released version where the IP publishes one, an explicit commit otherwise.

**Changing a pinned `rev` takes effect on the next plain `make generate` — including for patched packages.** Bender never overwrites a checkout that carries local modifications, and a patched checkout is modified by construction, so a revision bump used to leave the old tree silently in place until a full clean. The generator now detects the mismatch per package (against the lock's recorded revision, or against the checkout's own git HEAD where the lock has degraded the package to a path dependency) and deletes exactly that checkout before re-resolving, announcing it: `[INFO] Re-materializing '<name>': declared rev changed (<old> -> <new>)`. The fresh checkout is fetched at the declared revision and the patches and pre-build commands re-apply on the pristine tree. Anything a developer parked by hand inside that `bender_work/<name>` goes with it — which is why the log line exists, and why experiments belong outside `bender_work/`. Unchanged declarations cost nothing: the fast `bender checkout` path is taken and no checkout is touched.

### 3.2 Compilation Targets (`bender_targets`)
Some IPs contain multiple implementations (e.g., FPGA vs ASIC) or optional sub-modules. Bender uses targets (`-t`) to select the right source files.

| Field            | Type            | Description                                                              |
| :--------------- | :-------------- | :----------------------------------------------------------------------- |
| `bender_targets` | List of Strings | A list of targets that will be automatically passed to `bender script    |
|                  |                 | vsim` when compiling the SoC (e.g., `["cva6", "fpga_synth"]`).           |

*Note: If you define `bender_targets` for an existing IP in your custom project environment file, it will **completely replace** the default targets defined in the base `ollivander_config.yml`. If you want to add a target while keeping the default ones, you must list both the default targets and your new target in your custom file.*

### 3.3 Pre-Build Tooling and Scripts
Sometimes an IP needs to generate some files, download models, or install python libraries *before* the RTL can be compiled or simulated. Ollivander handles this automatically in Python immediately after fetching the IPs via Bender.

| Field             | Type            | Description                                                             |
| :---------------- | :-------------- | :---------------------------------------------------------------------- |
| `pre_build_cmds`  | List of Strings | Shell commands executed once the IP is on disk, in the order given.     |

The following substitutions are applied to each command:

| Placeholder        | Meaning                                                                |
| :----------------- | :--------------------------------------------------------------------- |
| `{bender_work}`    | The directory the IPs were fetched into.                               |
| `{ollivander_dir}` | The generator root, for scripts shipped alongside Ollivander.          |
| `$(PYTHON)`        | The interpreter of the active virtual environment.                     |
| `$(MAKE)`          | `make`.                                                                |
| `$(BENDER)`        | `bender`.                                                              |

The virtual environment's `bin/` is prepended to `PATH`, so a script whose shebang says `python` picks up the right interpreter. Any other tool must simply be reachable on `PATH`; there is no macro for it. An external script of any language is therefore invoked as an ordinary command:

```yaml
dependencies:
  idma:
    git: "https://github.com/FondazioneChipsIT/iDMA.git"
    rev: "2e637216e0455d77706a50d0639b86891e2a83aa"
    bender_targets:
      - "idma"
    pre_build_cmds:
      - "$(PYTHON) -m pip install -q flatdict mako"
      - "$(MAKE) -C {bender_work}/idma idma_hw_all BENDER=\"$(BENDER)\""

  my_custom_ip:
    git: "https://github.com/my-org/custom_ip.git"
    rev: "9a1c4f8e2b7d05c3a6e8f014b29d7c3518aa6b42"
    pre_build_cmds:
      - "$(PYTHON) {ollivander_dir}/scripts/setup_custom_ip.py {bender_work}/my_custom_ip"
      - "vsim -c -do {ollivander_dir}/scripts/gen_mem_models.tcl -quit"
```

Unlike `patches`, these commands are **not** undone between runs, so a command that modifies the checkout must take care of its own idempotency. Two strategies are in use: restore what you are about to touch before editing it, the way `scripts/patch_cva6_aes.py` does with a fixed target list; or record every edited file in the checkout's `.ollivander_patched` ledger, the way `scripts/patch_spatz_snitch.py` does when the target set is discovered at run time - the generator restores every ledger entry to its fetched state before each run, which also means deleting the command undoes its edits on the next generation. Use `pre_build_cmds` when the repair needs logic a text substitution cannot express: generating RTL, or deciding *whether* to modify something.

### 3.4 On-the-fly Code Patching (`patches`)
If an external IP contains a bug, a missing import, or requires a small tweak to compile within your specific environment, you can instruct Ollivander to patch the source code automatically using simple text replacement.

| Field     | Type            | Description                                                              |
| :-------- | :-------------- | :----------------------------------------------------------------------- |
| `patches` | List of Objects | A list of text replacements to perform inside the fetched IP repository. |

**Patch Object:**
* `file`: The path to the file to modify (supports `{bender_work}` placeholder).
* `search`: The exact string to look for. Every occurrence is replaced, not just the first.
* `replace`: The string to insert in its place. A literal `\n` becomes a newline.

Three properties of the mechanism are worth knowing, because they decide how you use it:

* **Every target file is restored to its fetched state before the patches are applied.** The result therefore does not depend on how many times the generator has run, nor on what a previous configuration did. Editing a fetched file by hand is pointless, since the next generation reverts it: to work on a dependency, use `bender clone`.
* **Removing a patch undoes it.** Ollivander records, inside each checkout, the files it has ever patched, so deleting a patch - or the whole entry that carried it - restores the original on the next run rather than leaving the last edit in place.
* **A patch that no longer matches is reported.** Since the file was just restored, a `search` string that does not occur can only mean the IP has changed and the patch has become a no-op, so Ollivander prints a warning naming it. Take it seriously: a silent no-op patch is how a repair survives long after the defect it addressed has been fixed upstream.

**Example of patching a file:**
```yaml
dependencies:
  opentitan:
    git: "https://github.com/AlSaqr-platform/opentitan.git"
    rev: "chips-it"
    patches:
      - file: "{bender_work}/opentitan/Bender.yml"
        search: "prim_flop_macros.svh"
        replace: "prim_flop_macros.sv"
```

### 3.5 Overriding one entry: the project's declaration replaces the catalogue's, whole

A dependency declared in a project's `*_env.yml` **replaces the catalogue's entry entirely**, in every part. It is not a per-key merge: what the project writes is what Bender and the pre-build steps see, and everything the catalogue said about that dependency — sources, patches, pre-build commands, targets — is gone unless the project restates it.

```yaml
dependencies:
  spatz:
    rev: "a-newer-revision"      # the catalogue's patches and pre-build commands
                                 # are NOT inherited
```

One rule, sayable in a sentence, and it buys three things a merge cannot express:

*   **Order** — the project's `pre_build_cmds` list *is* the sequence. Nothing is appended after it.
*   **Substitution** — a repair replaced by the project's own variant, rather than both running.
*   **Exclusion** — dropping a fleet repair that is wrong for the revision being pinned, by simply not restating it. This is the case that matters most in practice: a patch written against the catalogue's revision is suspect by construction against a newer one.

The cost is explicit: to change a revision **and** keep the repairs, copy the repairs into the project's entry too. That is deliberate — changing a revision is exactly the moment to re-read the patches rather than inherit them by default.

The replacement is **announced**, once per overridden entry, so a project that only meant to bump a revision cannot lose the repairs silently:

```
[INFO] project overrides dependency 'spatz': the catalogue's 1 patch and 3 pre-build
       commands are NOT inherited. Restate them in the project's dependency entry to
       keep them.
```

A copied patch does age: it keeps applying against sources the catalogue has since moved past. The stale-patch warning is the detector, and it works because every patch is applied to a freshly restored file — so a repair that has stopped matching says so instead of passing quietly.

### 3.6 Taking over the whole dependencies set (`inherit_default_dependencies`)

A project that wants a fully self-contained, auditable dependency description can decline the entire `dependencies` set shipped with Ollivander:

```yaml
inherit_default_dependencies: false
dependencies:
  # the project's own entries, and nothing else
```

The flag defaults to `true` and governs only what the base configuration contributes: the project's own `dependencies` block is kept either way. With it set to `false`, a package required by a `// BENDER:` pragma but absent from the project's own `dependencies` **stops the generation with an error naming the package**, instead of silently resolving to the catalogue's source. That is the point: an unused base entry never reaches Bender anyway (the registry is gated by the pragmas), so the flag buys no resolution change — it buys *control*, the guarantee that no source enters the build that the project did not write. Ollivander prints how many entries it dropped, and from which file.

Be aware of what is given up. The base entries carry more than sources: the patches and the pre-build repairs documented through this section live in them, so declining the catalogue means owning every one of those repairs. Like its twin `inherit_default_overrides` (section 4.3), the flag suits a project bringing its own complete IP catalogue rather than one starting from the examples.

---

## 4. Forced Resolutions (`overrides`)

`dependencies` declares *requirements*, which Bender must reconcile with the requirements every other package brings. `overrides` declares *forcings*, which bypass that reconciliation: Bender applies them to the whole dependency graph, transitive dependencies included, and never reports an override it honours. They silence the resolver rather than satisfying it, so the list should stay as short as the IP set allows.

```yaml
overrides:
  axi: { git: "https://github.com/colluca/axi.git", rev: "06410c36819924e32db2afa428d244dbdbcd5d4e" }
```

Two consequences of that difference matter in practice. An override on a package that never enters your graph is **inert**, which is why the catalogue shipped with Ollivander can list entries that only some topologies need. And an override must carry a `git` plus a `rev`: a `version` is still a constraint, so it participates in resolution instead of replacing it, and forces nothing.

Ollivander collects the entries and writes them into the project's `Bender.local`, a file it owns: it is rewritten on every generation, and removed once no forcing is left. It is therefore not a place to record anything by hand - a hand-written forcing would survive exactly until the next `make generate`.

More generally, **`Bender.yml`, `Bender.lock` and `Bender.local` are local build state** — git-ignored, and never to be copied between machines or working copies. The lock in particular may record a patched checkout as a *path* dependency, and that path is only meaningful next to the `bender_work/` it was created with: carried elsewhere, Bender will not re-fetch the package, and the generator refuses to proceed, naming the missing packages and the remedy (`make clean` and regenerate).

Because Bender says nothing about a forcing it honours, every generation reports the set that is in effect, and where each entry came from:

```
  [INFO] Forced resolutions in effect: 17, of which 2 declared by the project (*), the rest by ollivander_config.yml.
         axi, axi_riscv_atomics, cluster_interconnect, common_cells, cv32e40p, fpnew, hwpe-ctrl,
         hwpe-stream, idma, my_own_ip*, obi*, pulp_cluster, redundancy_cells, register_interface,
         riscv-dbg, scm, tech_cells_generic
```

Read it when a package behaves as if it were at a revision nobody asked for: a name in that list is pinned graph-wide, whatever the requirements around it say. Entries the project replaced count as its own, since from Bender's point of view that is what they are.

### 4.1 When you need one

Bender refuses to resolve when the requirements it collects admit no common solution, and stops with a report naming every package involved. That happens more often than one would like in this ecosystem: one package required from two different repositories, a requirement expressed as a branch name, an untagged commit set against a semantic version range, two exact pins to different versions, or a package that one IP vendors as a `path:` dependency inside its own tree while the rest of the graph requires it from git - Bender demands that a package be a path dependency everywhere or nowhere, and refuses the mixed graph outright. None of these can be repaired by choosing better revisions - only by forcing one.

The report is also the recipe. It names the revision each requirement asks for, including the one your own SoC asks for:

```
Error: Dependency requirements conflict with each other on dependency axi.

- package mesh_soc   requires  06410c36819924e32db2afa428d244dbdbcd5d4e  at colluca/axi.git
- package cheshire   requires  ^0.39.8 (0.39.8 <= x < 0.40.0)            at pulp-platform/axi.git
```

Copy the source and revision you intend to win into the `overrides` block of your own environment file. Entries there take precedence over the ones shipped with Ollivander, key by key, so you can also disagree with a forced resolution from the catalogue without touching it.

Record *why*, next to each entry. A forcing whose reason is lost is indistinguishable from a superstition, and the only way to re-derive it is to remove every override and let Bender report the conflicts again, one run at a time.

### 4.2 Disabling one, instead of replacing it

Replacing a forced resolution is not always enough. A project that adds an IP of its own may find that no single revision satisfies both that IP and the forcing it inherits - which is precisely the kind of contradiction the catalogue exists to describe. Give the key a **null** value to drop the forcing altogether:

```yaml
overrides:
  common_cells: null    # 'false' works too: hand this package back to Bender's own resolution
```

The package then takes part in normal resolution again, so Bender either resolves it or stops with the report of section 4.1 - which is the input you need in order to choose a revision, and which a silently honoured forcing would have hidden.

A removal that removes nothing is reported as having no effect, for the same reason a stale patch is: it outlives the update that made it pointless. Any value that is neither a mapping nor null is refused with an error naming the file and the key, since it would otherwise be copied verbatim into the generated `Bender.local` and fail there, inside a file the project never wrote.

### 4.3 Taking over the whole set

A project that re-pins many IPs is better served by owning the entire set than by disabling inherited forcings one at a time:

```yaml
inherit_default_overrides: false
overrides:
  # the project's own forcings, and nothing else
```

The flag defaults to `true`, and governs only what the base configuration contributes: your own `overrides` block is kept either way. With it set to `false` no forcing reaches Bender that you did not write, which is worth having precisely because an honoured override is never reported - the inherited set is otherwise invisible from inside the project. Ollivander prints how many forcings it dropped, and from which file.

Be aware of what is given up. The forcings shipped with Ollivander are what makes its example topologies resolvable at all: most of them exist because external IPs contradict *each other*, in ways no choice of revisions can repair. Declining them means taking that whole conflict set upon yourself, so the flag suits a project bringing its own IP catalogue rather than one starting from the examples.

The `dependencies` registry has its own version of this flag, `inherit_default_dependencies` (section 3.6), but the two exist for different reasons, and the asymmetry this section opened with explains why. A forcing applies to the whole graph unconditionally, so declining it changes what Bender *resolves*; a registry entry only reaches Bender when a pragma requires it, so an unused one is already inert and declining it changes nothing about resolution — what that flag buys is *control*, the guarantee that a required package cannot silently source from a catalogue the project never wrote.

---

## 5. Fast-Check Simulator Configuration (`fast_check_tool`)

Ollivander supports multiple verification backends for structural fast-check compilation validation. You can declare the simulator of choice directly in your environment configuration YAML file.

### 5.1 Configuration YAML Field
You can add `fast_check_tool` at the root level of your environment YAML file:

```yaml
# my_project_env.yaml
fast_check_tool: "verilator"  # Options: "questa" (default) or "verilator"
```

### 5.2 Configuration Precedence & Command-Line Override
1. **YAML Files**: Ollivander evaluates the base `ollivander_config.yml` first, and overrides it with your custom appended environment file (passed via `-a`). The resulting simulator is used when you run `make generate` to write the compilation script targets inside the output `sim/sim.mk`.
2. **Command Line**: You can override the tool selection at run-time without re-generating the codebase by passing `FAST_CHECK_TOOL` directly to the `make` command:
   ```bash
   make fast-check FAST_CHECK_TOOL=verilator
   ```

---

## 6. Self-Elaboration of the Generated RTL (`generated_rtl_check`)

Ollivander parses the external IPs with `pyslang` to learn their signatures, and since the ninth wave it also re-reads **what it writes**. Phase 11, the last of the generation run, elaborates the design with the **slang** front-end and refuses errors found inside the generated output or the component directories.

```yaml
# my_project_env.yml
generated_rtl_check: "strict"   # "strict" (default) | "warn" | "off"
```

| value | behaviour |
| --- | --- |
| `strict` | errors in what Ollivander generated **stop the generation**. The default: a check that does not stop is a check whose green result means nothing. |
| `warn` | the same errors are reported and the generation continues. |
| `off` | the phase is skipped entirely. |

### 6.1 What it reports, and what it does not

The reported set is **derived, not fixed**: it is the output directory plus every entry of `paths.components`, including the directories a project adds in its own environment YAML. Vendor sources are *parsed* — their packages are needed to elaborate anything at all — but never *reported*, or the check would drown in third-party diagnostics that are not yours to fix.

That inclusion of your own components is deliberate. They are, in any project, the least reviewed SystemVerilog in the tree: nobody upstream reviewed them, they have no other consumer, and no example exercises them. A fixed pair of paths would have under-covered exactly the code that most needs a second reader.

`warn` exists for that same reason seen from the other side. Ollivander is entitled to impose its front-end's severity on **its own** output; imposing it on a component you wrote, which your simulator accepts, would be presumptuous. Set `warn`, read the diagnostics, and decide for yourself.

### 6.2 It is an elaboration check, not a lint

Worth being explicit, because the two are easy to conflate and the expectation matters. This check answers *is this legal, self-consistent SystemVerilog?* — does every instantiated module exist, do its ports exist and match, do types resolve, do parameters elaborate, is a member access valid on the type it is applied to. A lint answers a different question: *is this legal code unwise?* — latches, incomplete cases, width truncation, undriven signals.

Three consequences follow:

*   **The severity is not a matter of taste.** An elaboration error means the RTL is not valid to a conforming front-end, so someone downstream will hit it; that is why `strict` is a defensible default. A lint finding is an opinion, and a lint gate needs a warning set argued rule by rule before it can block anything.
*   **It will never report a latch, or a truncated width.** Those elaborate perfectly. Expecting lint findings here and receiving none would read as a broken check rather than as a check doing its job.
*   **It is a third front-end, not a third opinion.** The value comes from front-end diversity: QuestaSim and Verilator are lenient in different places, `slang` is strict. Same class of tool, different tolerance — which is exactly how it finds what two simulators pass over.

The boundary is not metaphysical: `slang` has a warning set of its own, and this check deliberately reports **errors only**. Turning its warnings on would move it towards linting, and that would be a decision requiring the curated set above, not a drift.

### 6.3 Why a third front-end, when fast-check already elaborates

Because `fast-check` and the simulators cannot see one whole class of defect:

* `vlog` does not check port existence across a module boundary, so a wrapper connecting ports its submodule never declared compiles clean;
* nothing in any flow elaborates the **chip wrapper** — the generated testbench instantiates the SoC, not the chip — so that file is compiled and never checked.

Those two together let a wrapper carrying fourteen connections to non-existent padframe ports pass every gate the project had. Phase 11 is the flow that would have caught it, and it costs two to four seconds per project.

### 6.4 The two passes

| pass | file list | what only it can see |
| --- | --- | --- |
| phase 11, end of generation | the whole design; dependencies are already fetched, so the **real** IPs elaborate | self-consistency of the generated RTL, and our wrappers against the IPs' true signatures |
| `fast-check`, after stub generation | the fast-check list, with stubs standing in for the IPs | whether a **stub faithfully represents** the IP it replaces |

Both obey `generated_rtl_check`. The stub pass is the cheaper of the two and exists for the narrower reason: a malformed stub makes the fast-check green mean less than it appears to.

> **The error limit is lifted deliberately, and until 2026-08-28 it was not — which made the full-flist pass largely blind.** Vendor sources are parsed but never reported: `slang` still *emits* their diagnostics, and the ownership filter drops them afterwards. With the default limit, that budget was spent entirely before our own files were reached — measured on `noc`, 86 errors, every one of them in `axi_demux`, `cv32e40p_tracer`, the `*_reg_top` blocks and `floo_nw_chimney` — so the pass printed "no errors in what we generate" without having looked. The defect that exposed it was a declaration-order error in a generated tile: the full pass reported nothing, the stubbed pass (where there is almost no vendor code to spend the budget) rejected it immediately, and with the limit lifted the same tree yields 2063 errors of which 96 are the real one. The limit is now an explicit large number rather than `0`: `slang` documents `0` as "no limit", and a version reading it as "print none" would disable the check in silence.
>
> Lifting it surfaced exactly one latent defect in the fleet — `reqrsp_pkg::AMONone` in `components/tiles/snitch_hwpe_subsystem.sv`, a member selected through a package that only wildcard-imports it, accepted by both simulators — and one construct that is not a defect: the generated testbench preloads interleaved memories through paths crossing an *unnamed* generate block inside the IP (`genblk1[0]`), which `slang` gates behind `--allow-genblk-reference`. That flag is passed, because both simulators resolve those paths and the whole fleet boots through them.

### 6.5 Running it by hand

From a project directory, `make check-rtl` re-runs the check over the tree as it stands, without regenerating it — useful while working through a list of findings — and `make check-rtl CHECK_RTL_MODE=stubs` selects the stubbed variant. Both are the generator's own `--check-rtl` flag, and both read only: the report-only path returns before anything touches the output directory. The full-design mode needs `bender` on `PATH`, since the file list comes from `bender script flist-plus`.

### 6.6 It degrades loudly

There is no path in which a missing check looks like a passing one. If `pyslang` is absent, if Bender cannot produce a file list, or if the checker fails its own self-test — an input known to be invalid that it must reject before its clean verdicts are believed — the phase says so and leaves the generation alone.

## 7. Regenerating an IP to the Host's Configuration (`{host.<Parameter>}`)

A pre-build command of a dependency may substitute **any resolved parameter of the host** as `{host.<Parameter>}`: the isle's own defaults, the values the description sets under `parameters`, and the ones the generator derives (`NumIntrsIn`, `NumIrqHarts`, `NumDbgHarts`, the bus counts). It is the generic hook for an IP that must be regenerated to the host it serves, and the generator knows nothing of what the command does with the numbers.

Its user today is the Cheshire host's PLIC. The `rv_plic` that reaches the compile list is `opentitan_peripherals`' checked-in default - 32 sources, one target - which sees only the first 32 internal sources: no `intr_ext_i` line reaches it and the S-mode target does not exist. Cheshire's own build regenerates it (`cheshire.mk`, target `.generated`: its `hw/rv_plic.cfg.hjson` copied into `opentitan_peripherals`, then `ipgen` + `regtool`), a step a Bender fetch never runs; Astral's `update_plic` edits that configuration with two `sed` before letting Cheshire regenerate. `scripts/regen_rv_plic.py`, a pre-build command of the `cheshire` dependency, does the same with the host's numbers:

```yaml
- "$(PYTHON) {ollivander_dir}/scripts/regen_rv_plic.py {bender_work} --num-ext-irqs {host.NumIntrsIn} --num-cores {host.NumCores} --num-ext-irq-harts {host.NumIrqHarts}"
```

Everything Cheshire-specific stays in Cheshire's files: the script reads the internal source count and the contexts per hart from Cheshire's own configuration (kept pristine in a side copy), so sources are internal + external and targets are contexts x harts. The external width is not the routed count but the **capacity the host isle is built for**, which is simply the default of its `NumIntrsIn` parameter (32 in `cheshire_isle.sv`; standardization document, section 5.1): a per-project count could not serve a project and the pre-generated macro it nests from one Bender tree, while a header default is the same for every host built from that isle. The generator keeps the default and refuses a description routing a bit beyond it; `parameters.NumIntrsIn` in the host's description overrides it, and the regeneration follows, since it reads the resolved value. The regeneration is idempotent and offline.

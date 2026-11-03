# Novanode Studio — progress, execution roadmap, and backlog

Snapshot: **2026-11-02** · Primary target: **Unreal / Linux** · Prepared engine family: **5.8**

**Current position:** source preparation is implemented; native Unreal execution and model-profile
qualification have not begun. The review identified additional activation/hardening gates below.
**Next action:** step **01**, a read-only storage/GPU/toolchain readiness check.
**First milestone:** a playable Linux lab with native test evidence and an inspected visual baseline.

Review update, **2026-11-02**: command behavior, task prerequisites, public model availability,
and exact HF pins were checked again. See [AI_CODING_RESEARCH.md](AI_CODING_RESEARCH.md) for the
current architecture/technique review, sources, and open findings **H1–H7**. Those findings are
not runtime fixes or proof that an inactive profile is ready for unattended use.

## How to use this document

- Work through the numbered steps in ascending order. Stop at a failed prerequisite; do not
  skip a required gate just to reach a later command. Optional steps may be explicitly deferred.
- Run shell commands from the project root:
  `/home/d/Desktop/proyects/nn-proyects/novanode-studio`. Replace example paths before execution.
- Execute one command block at a time and inspect its outcome. This is a human runbook, not a
  script to paste and run unattended, and it does not itself authorize downloads or account changes.
- Mark a checkbox only after its completion gate is satisfied. Record evidence and blockers in
  the checkpoint template at the end. Only a human can grant `human_approved` status.
- Status progression is `implemented` → `machine_verified` → `human_approved`, with a stated
  scope. A source check, engine test, screenshot review, and model benchmark prove different things.
- For an AI work session, provide only the active step, its relevant reference, and a bounded
  task contract. Do not load this whole roadmap and every linked document into every task.
- The current runner requires nonempty `steps` and `verification`, deadlines/timeouts no greater
  than 3,600 seconds, 1–3 attempts, and a context handoff within 20,000 characters including the
  contract. This roadmap alone exceeds that cap: select small explicit task inputs instead.

## Progress already made

The results below are recorded preparation results, not a claim that future execution has passed.

| Area | Completed work | Verification boundary |
|---|---|---|
| Project direction | Separate Novanode studio project; Unreal/Linux selected; Godot preserved; macOS deferred | The original `hackrf-webui` project was not part of this implementation |
| Production CLI | Dependency-free Python CLI, bounded contracts, compact handoffs, source-write auditing, resource ownership | Runner audits writes after commands; it is not an OS/network sandbox |
| Cost/usage foundation | Transactional reservations, persistent job identity, reconciliation, immutable receipts | External OpenCode requests are not automatically imported into the ledger |
| Asset pilot | Repeatable background Blender bench, geometry/scale/provenance checks | Pilot checks passed; Blender → Unreal import remains unverified |
| Legacy Godot pilot | Interaction, movement/collision, save/load, imported asset, Linux packaged smoke | 14 gameplay checks passed after migration; none proves Unreal behavior |
| Unreal source | Project descriptor/config, first-person C++, modular lab, airlock, power/reference interactions, HUD | Implemented; actors/UHT, native rendering, input, and packaging have not been verified |
| Unreal preparation tools | Generator-owned material/map preparation; Linux build, play, automation, package, and smoke commands | Prepared plans/fixtures, not completed native gates |
| Regression checks | 70 tests passed, including compilation/execution of the exact portable `LabState.h`; Ruff and clean source-only checks passed | Portable C++ is not an Unreal module build |
| CI | Linux source checks and a manual licensed self-hosted Unreal workflow | Native workflow has not run; no remote publication is implied |
| Model research | Live HF cards/GGUF metadata and OpenRouter catalog checked on 2026-11-02; revisions/sizes/hashes pinned | Metadata only; actual coding quality, compatibility, and speed remain unbenchmarked |
| Model tools | Opt-in downloads, VRAM plans, localhost single-slot serving, two-request synthetic tool probe | No new weights downloaded and no candidate inference performed |
| OpenCode profiles | Inactive free/local V2 profiles generated under `.studio/opencode/` | No active/global configuration or provider credentials changed |

At the latest preparation check, this machine had an **RTX 3090 / 24 GiB VRAM**, approximately
**64 GiB RAM**, and approximately **75 GiB free disk space**. These are historical observations;
remeasure before installation. Existing Ollama models were preserved, not unloaded or deleted.
Git inspection during roadmap preparation showed `main`, an initial staged implementation,
and no commits yet. Preserve that staging and review it before making a checkpoint.

The read-only review remeasured **73.43 GiB free disk**, **62.09 GiB RAM**, and approximately
**1.16 GiB GPU memory in use**. Installed version strings were OpenCode **2.2.5**, Ollama
**0.31.2**, and llama-server **0.8.0 / `8642541`**; these are not model/CUDA compatibility passes.
`UE_ROOT` remains unset. Host **Fedora 44 / Clang 22.1.8** must not be mistaken for Epic's
reviewed engine toolchain. Recheck all values when resuming; no resources have been reserved.

### Prepared model shortlist — not a ranking proven on this workstation

Weight sizes are decimal GB, **not total runtime VRAM**. Exact revisions/hashes live in
[`models.lock.json`](../models.lock.json); research and caveats live in [MODELS.md](MODELS.md).

| Local profile | Candidate | Weight file | Intended evaluation |
|---|---|---:|---|
| `qwen38-main` | Qwen3.8-27B UD-Q4_K_M | 16.46 GB | First solo-quality candidate, Unreal closed |
| `qwen35-small` | Qwen3.5-9B Q4_K_M | 5.68 GB | Small tasks with measured editor headroom |
| `north-code` | North Mini Code 1.0 UD-Q4_K_M | 19.20 GB | Coding specialist; tight memory/runtime gate |
| `nanbeige-experiment` | Nanbeige4.3-33B Q3_K_M | 15.92 GB | Recent challenger; quantization/speed tradeoff |
| `qwen3-coder` | Qwen3-Coder-30B-A3B Instruct Q4_K_M | 18.56 GB | Older coding-specialist baseline |

Prepared free cloud references, subject to renewed availability checks:

- Coding: `openrouter/cohere/north-mini-code:free`.
- Coding alternative: `openrouter/recursive/flint-v1.0:free`.
- Image-review candidate: `openrouter/nvidia/nemotron-3.5-super-vl:free`.

The sensible starting policy is free cloud coding while Unreal uses the GPU, a smaller local
model only if measured headroom permits, and larger local candidates with Unreal closed.
Do not download the entire shortlist or treat an advertised context size as an affordable setting.
All five pinned revision/filename/size/advertised-hash combinations were reconfirmed. New research
candidates such as **GSQ-RCO Qwen3.8** and **ternary Bonsai 2** are documented separately, not
silently added to the lock file or accepted as working models. LFM3's own card advises against
agentic coding; small size/popularity alone is not a selection criterion.

## Execution order — required native milestone

### 01 — Check storage, GPU, and toolchain readiness

- [ ] **Complete step 01.** No installation or model invocation is needed.

```sh
df -h .
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
nvidia-smi
python3 --version
clang++ --version
python3 studio.py doctor
```

Inspect available mounted drives and separately check free space on any proposed engine drive.
An unavailable host compiler is a setup finding, not permission to install arbitrary packages.
Confirm the chosen editor's supported Linux distribution, Vulkan/driver, and bundled toolchain
requirements against Epic's current documentation linked in [UNREAL.md](UNREAL.md).
UE 5.8's release notes specify Clang 20.1.8 and reference Ubuntu/Rocky/RHEL configurations;
validate the installed engine's toolchain on this Fedora host rather than replacing system
packages or assuming host Clang 22 is the engine compiler.

**Completion gate:** choose an engine location and allow room for the download/extraction,
installed editor, shader/derived caches, project intermediates, packages, and future models.
The old 75 GiB reading is not a sufficient installation-space guarantee. Do not delete models,
stop existing services, upgrade drivers, or move the project without the owner's approval.

### 02 — Recheck the source baseline and protect the current work

- [ ] **Complete step 02.** Requires step 01; engine installation is not required.

```sh
git status --short --branch
git diff --stat
git diff --cached --stat
python3 studio.py task validate tasks/unreal-source.json
python3 studio.py task context tasks/unreal-source.json
python3 studio.py task run tasks/unreal-source.json --execute
```

Review the existing staged and unstaged work. Arrange a human-approved local commit or independent
backup before substantial native integration. Do not reset the index, discard files, or use blanket
staging to hide unrelated changes. A local checkpoint does not authorize a remote or a push.
`.studio/` evidence, receipts, tools, and weights are ignored; preserve important evidence separately
without including credentials. Source Git history alone will not back up those ignored files.

**Completion gate:** source validation and regressions pass again, and there is an agreed recovery
point. The recorded count is 70 tests; investigate unexpected failures/skips rather than forcing
that historical count or weakening checks.

### 03 — Authorize and install the Linux Unreal editor

- [ ] **Complete step 03.** Requires the storage decision and recovery point from steps 01–02.

This is an explicit **human approval gate**, not an automated `studio.py` download:

1. Review Epic's current license/EULA and its applicability to games versus non-game studio work.
2. Use your authorized Epic account and official Linux distribution channel.
3. Approve the installation drive, payload size, and any required system/toolchain changes.
4. Install the engine, preserving existing projects, models, services, and editor sessions.

**Completion gate:** an authorized Linux installation exists with `Engine/Build/Build.version`,
`Engine/Binaries/Linux/UnrealEditor`, and the Linux build/UAT scripts. The prepared project targets
**5.8**; this does not mean 5.8 must still be the newest version when you resume. If using another
family, plan and review a version migration instead of bypassing the existing version check.

### 04 — Connect the installed engine to the project

- [ ] **Complete step 04.** Requires step 03.

Replace the example root with the actual folder containing `Engine/`:

```sh
export UE_ROOT=/your/installed/UE_5.8
python3 studio.py unreal doctor
python3 studio.py unreal validate
```

`UE_ROOT` is an installation root, not the `UnrealEditor` executable path. Set it again in new
terminals or arrange an approved persistent environment later; do not silently edit shell settings.

**Completion gate:** doctor reports the expected installation as ready and source validation
passes. Doctor checks installation/source readiness; it does not establish a successful native
compile or a working Vulkan graphical session. See [UNREAL.md](UNREAL.md) for setup details.

### 05 — Compile the Unreal editor module

- [ ] **Complete step 05.** Requires step 04.

Preview first, then explicitly execute:

```sh
python3 studio.py unreal build
python3 studio.py unreal build --execute
```

**Completion gate:** the actual Linux editor-module build, including Unreal Header Tool processing,
completes successfully. Inspect `.studio/evidence/unreal-build-0.log` and resolve real API,
compiler, or toolchain errors with small reviewed changes. This is the first native compilation
gate; the portable state test does not predict that it will pass unchanged.
Current wrapper timeouts use generic “failed” wording too. On timeout, inspect logs and owned
process/build state, checkpoint the outcome as unknown until reconciled, and do not blindly retry
or change a running task/runner to extend its budget. See review finding H5.

If blocked, save the error and checkpoint. Optional step 11 may be brought forward deliberately
for approved cloud assistance; installing local weights is not a prerequisite to fixing the build.

### 06 — Generate the owned map and material assets

- [ ] **Complete step 06.** Requires step 05; no other owner may be using the project editor.

```sh
python3 studio.py unreal prepare
python3 studio.py unreal prepare --execute
```

**Completion gate:** fresh `.studio/evidence/unreal-prepare.json` reports `assets_prepared`, with
the generated map and material present under `projects/NovanodeLab/Content/Generated/`.
The generator refuses unmarked existing assets; investigate such a conflict rather than deleting
or overwriting someone else's files. Generated Unreal content is ignored and must be reproducible.
Already marked assets are currently **reused, not rebuilt**. A later material/map recipe change
needs a reviewed versioned regeneration/migration plan; a successful `prepare` alone does not
prove those existing assets changed. See H6 before visual/material iteration.

The saved map starts blank: `StudioGameMode` constructs the lab at runtime. An empty editor view
before pressing Play is expected, not evidence that the runtime room failed to generate.

### 07 — Launch the first playable lab and check real input

- [ ] **Complete step 07.** Requires step 06 and a graphical Linux session.

```sh
python3 studio.py unreal run --execute
```

For editor inspection instead, close the game and use:

```sh
python3 studio.py unreal editor --execute
```

In the editor, press Play. Check the intended gold path using real controls:

1. Spawn in the lab; verify mouse look and WASD movement/collision.
2. Look at the airlock and use **E** to open it; physically walk through.
3. Find the power console, look at it, and use **E** to enable power.
4. Find the reference instrument and use **E** to run the analytical reference.
5. Verify contextual prompts, status/result feedback, and **Esc** cursor behavior.
6. Record any blocked route, unreliable interaction, or unreadable UI before adding features.

**Completion gate:** a human has observed a usable launch-to-result path. Do not mark a broader
visual/art acceptance yet. The formula result is an **analytical reference, not a validated physics
simulation**. Close the game/editor normally before exclusive test/preparation/package operations;
do not kill someone else's editor or service to acquire ownership.

### 08 — Run the native Unreal automation tests

- [ ] **Complete step 08.** Requires steps 05–07; preserve the playable gold path.

```sh
python3 studio.py unreal test --execute
```

**Completion gate:** the fresh report at `.studio/evidence/unreal-automation/index.json` includes
successful `Novanode.State.Prerequisites`, `Novanode.State.Period`, and
`Novanode.State.InvalidInputs`. Missing, duplicate, skipped, failed, or unfinished tests do not pass.
These are native state tests, not automated proof of physical keyboard input or visual quality.

### 09 — Package Linux and verify the packaged runtime

- [ ] **Complete step 09.** Requires step 08 and sufficient package/build space.

```sh
python3 studio.py unreal package
python3 studio.py unreal package --execute
python3 studio.py unreal smoke --execute
```

Then run the combined bounded native regression gate:

```sh
python3 studio.py task context tasks/unreal-smoke.json
python3 studio.py task run tasks/unreal-smoke.json --execute
```

**Completion gate:** the Linux launcher exists under `.studio/builds/unreal/Linux/`, and fresh
`.studio/evidence/unreal-startup.json` passes the five named checks: authored material loaded,
prerequisite rejection, closed-door ray blocking, open-door ray clearance, and correct reference
outcome. Inspect build/test/smoke logs on failure; an old report is not evidence for a new build.
Also manually launch the packaged application graphically and repeat step 07's gold path.
Record the source checkpoint, engine version, build time, and inspected artifact identity as well:
the current package check only verifies that a launcher exists, not a source-to-build manifest (H5).

NullRHI smoke does not verify rendering, real input, or game feel. Packaging is an internal build,
not approval to distribute, upload, sign, or publish it.

### 10 — Inspect visuals and measure a baseline

- [ ] **Complete step 10.** Requires the runnable native/package path from steps 07–09.

Capture fresh screenshots of the entrance, main room, equipment bays, reference station, and HUD.
Inspect them at actual player height and gameplay resolution. Store captures and review notes
under `.studio/evidence/unreal-visual-review/`; there is no implemented `unreal capture` command
to assume here. Do not reuse Godot screenshots as Unreal evidence.

Review layout/readability, lighting/exposure, material scale, collision, navigation, interaction
reach, HUD/accessibility, and whether the lab feels coherent rather than like disconnected cubes.
Record representative frame times/FPS, VRAM, RAM, startup/shader time, resolution, and settings.
Agree human performance/quality targets rather than inventing a pass threshold after measuring.

**Completion gate:** an inspected visual baseline, measured performance baseline, and a short
prioritized defect list exist. Humans decide acceptance; screenshots and measurements may reveal
that the current primitive-based scene needs substantial improvement.

**Milestone A reached:** there is a playable Unreal/Linux build with scoped machine evidence
and a real visual review. Model research alone cannot satisfy this milestone.

## Execution order — improve the experience and select coding models

### 11 — Activate an approved free-cloud coding profile, if wanted

- [ ] **Complete or explicitly defer step 11.** Normally follows step 10; it may be pulled forward
  for an earlier blocker after separate account/privacy approval. It is not required for native execution.

Refresh public metadata and generate an inactive draft; preserve any manually edited draft first:

```sh
python3 studio.py models refresh-free
python3 studio.py models config --profile free
```

1. Review `.studio/opencode/free.json` and [MODELS.md](MODELS.md). Confirm explicit `:free` routes,
   zero-price ceilings, privacy-compatible routing, scoped permissions, and no paid fallback.
   `data_collection: deny` is not ZDR; the generated draft does not set `provider.zdr`. Decide
   what retention policy studio IP requires, and defer cloud use if no acceptable route exists.
2. Review existing project/inherited OpenCode configuration. Manually merge or activate the draft
   as appropriate; do not blindly overwrite `opencode.json`, `opencode.jsonc`, or `.opencode/` settings.
   Check inherited plugins, warming/background summaries, and maintenance model routing. Keep
   warming and background summaries off for the free-request budget; review a small agent-step
   allowance. Provider restrictions do not form an allowlist of only the three declared model IDs.
3. In OpenCode, use `/connect` → OpenRouter to enter credentials directly in its interface,
   never in chat, source files, screenshots, or logs. Do not purchase credits as an implicit setup step.
4. Use `/models` to select an available intended free route. An existing session selection can
   override the new-work default. Configuration reloads automatically; no restart is normally needed.
5. Authorize one small non-sensitive tool-using task and inspect its actual result/usage before
   sending studio IP. Respect current request quotas and stop/checkpoint on exhausted capacity.
   Qualify request-body price/privacy behavior with a credential-free mock or approved redacted
   observation; unit-tested config dictionaries alone are not end-to-end enforcement. Record
   actual model/provider identifiers, requests, retries, and summary calls without credentials.

**Completion gate:** an approved free route demonstrably works in this project, without paid
fallback or permission bypass. Catalog metadata and authentication alone are not inference QA.
If no privacy/parameter-compatible free route exists, defer it rather than relaxing protections.
Use a small **single-session** plan → edit → test → review loop with targeted file/symbol retrieval.
The runner does not automatically cap or record OpenCode requests. Review H3/H4/H7 and the
research note's quota-conscious settings before granting broad tools. Watcher ignores are not
security/context exclusions, and read-deny rules do not sandbox shell/search/plugin execution.

### 12 — Fix the highest-value visual and interaction defects

- [ ] **Complete step 12.** Requires step 10's defect list; step 11 is optional.

Choose one small change at a time: architectural rhythm, instrument placement, lighting,
materials, prompt clarity, player feel, or interaction/collision reliability. Keep one owner per
editor/scene/settings/integration operation. Divide human responsibilities explicitly; do not
start helper-agent swarms without human authorization.

For each change, define its permitted files, context inputs, attempts/deadline, and acceptance
criteria in a bounded contract before execution. Do not edit a running contract/runner/fixture.
Run `python3 studio.py test` plus the relevant native/asset checks, rebuild affected code/content,
and repeat visual/input review where applicable. Repackage/smoke the resulting delivery candidate.
Turn repeated failures into regression tests instead of adding more operating prose.

**Completion gate:** the prioritized usability/visual problems are resolved or explicitly accepted
by a human, evidence is fresh, and the original gold path still works. More primitives or Lumen
settings in source are not proof of better art.

### 13 — Prove the Blender → Unreal asset path

- [ ] **Complete or explicitly defer step 13.** Requires the native baseline and an approved asset task.

1. Choose one small useful prop; use background Blender for reproducible authoring/export.
2. Validate its manifest with `python3 studio.py assets validate <manifest>` after replacing
   `<manifest>` with the actual approved file path. Retain provenance/license and inspect geometry.
3. Import into the actual Unreal project under an explicit write allowance; verify meter/Y-up
   interchange against Unreal's centimeter/Z-up convention, orientation, pivot, and scale.
4. Verify materials, collision, lighting, placement, and cooking in the real gameplay camera.
5. Rebuild/repackage as needed and rerun the gold path and packaged smoke.

**Completion gate:** one traceable Blender prop looks and behaves correctly in both the native
application and packaged build. The old Godot bench import does not satisfy this gate. Keep authored
assets separate from generator-owned content unless ownership and regeneration are explicitly designed.

### 14 — Set up one local candidate and prove tool transport

- [ ] **Complete or explicitly defer step 14.** Requires measured editor GPU usage from step 10,
  renewed disk checks, and explicit approval for any runtime installation or large weight download.

Start with planning only:

```sh
python3 studio.py models list
python3 studio.py models plan qwen35-small --mode editor
python3 studio.py models plan qwen38-main --mode solo
```

Choose **one** candidate, not every row in the shortlist. Existing Ollama models can be a separately
approved baseline, but the pinned GGUF commands below do not reuse an Ollama alias automatically.
Confirm that a reviewed CUDA llama.cpp build supports the chosen architecture/template; this
pipeline does not install or upgrade that runtime. Preserve existing services and model files.
Before activating the local draft, qualify **H1/H2**: real OpenCode streaming, automatic tool
selection, repeated tool/result turns, error handling, and a session near its context limit.
The current 16K server/profile combination has not been tested with V2 compaction's documented
reserve behavior or the full instruction/tool overhead. Review a supported reserve/context/output
configuration rather than assuming that the synthetic probe establishes a usable coding context.

After approving the size/location, this example downloads the smaller pinned candidate:

```sh
python3 studio.py models fetch qwen35-small
python3 studio.py models fetch qwen35-small --execute
```

Terminal A, after reviewing the current memory plan:

```sh
python3 studio.py models serve qwen35-small --mode editor
python3 studio.py models serve qwen35-small --mode editor --execute
```

While that foreground server is running, use terminal B:

```sh
python3 studio.py models probe qwen35-small --execute
python3 studio.py models config --profile local --local-model qwen35-small
```

The prepared server binds `127.0.0.1:8091`, uses one inference slot and 16K context. Planning
adds a heuristic 3 GiB runtime allowance and, in editor mode, an extra 8 GiB reserve; neither is
a measured no-OOM guarantee. If it rejects the plan, do not bypass it or stop user services to fit.
For an approved `qwen38-main` trial, substitute that profile and use `--mode solo` with Unreal
closed by its owner. Weight/context/model labels do not establish actual memory consumption.

**Completion gate:** the pinned model loads, actual memory/speed are recorded, and a fresh
`.studio/evidence/model-probe-<profile>.json` verifies the synthetic tool/result round trip.
Accept only the **current invocation's** successful result and verify the owned server/model/hash.
The current probe has no timestamp/run ID, does not establish serving identity, and leaves an old
success file behind if a later probe fails: do not accept that old file as a new pass. A short
thinking/output budget can also truncate a capable model; distinguish that from wrong code (H1/H2).
The probe executes no generated tool and does not prove coding quality. Then review/merge the
inactive local profile without overwriting existing configuration and select it through `/models`.
Keep local routing explicit, text-only, and without automatic cloud fallback; vision is not tested.
Only promote it after the actual OpenCode transport/context qualification above passes. The later
hardening task must add provenance/failure-invalidation regressions before unattended reliance.

### 15 — Benchmark approved models on the same real tasks

- [ ] **Complete step 15 for each candidate being considered.** Requires actual access to that
  candidate from step 11 or 14 and the native baseline. A cloud-only comparison is valid if local
  evaluation is deferred; do not claim an untested local/cloud winner.

Use the same starting files, task boundaries, acceptance tests, context/output budgets, and
allowed tools. Use separate reviewable copies/checkpoints so one candidate's edits do not become
another candidate's starting advantage. Run candidates sequentially unless delegation is authorized.
Keep the small tool surface and model-specific reasoning/template settings explicit. Record the
cloud endpoint/provider when exposed; a hosted slug does not pin an exact deployed quant/revision.

Suggested bounded tasks, in increasing complexity:

1. Fix a portable-state bug and add a regression test.
2. Repair a real Unreal compile failure without weakening checks.
3. Add one contextual interaction with native and packaged verification.
4. Make one small Blender/Python asset-pipeline change with geometry/import checks.

Record success, attempts, tool-call failures, compile/test outcomes, latency, prompt/output
tokens, actual VRAM, and human correction/review time. Record exact model/quant, runtime version,
context, reasoning/output settings, and route. Separate truncation/rate-limit/transport failures
from wrong code; retry only within the approved attempt/request budget.
Compare ordinary Q4 versus any approved GSQ-RCO/ternary experiment on the **same tool/coding tasks**,
not just a card's perplexity or coding average. Speculative decoding/MTP, aggressive KV quantization,
extra retrieval infrastructure, and multi-agent review come later only if measurements justify them.

**Completion gate:** a small reproducible scorecard under `.studio/evidence/model-benchmarks/`
supports choices by task type. Model-card scores, popularity, one happy-path probe, and aggressive
quant file size are not substitutes for this evidence.

### 16 — Freeze measured defaults and close accounting/documentation gaps

- [ ] **Complete step 16.** Requires the scorecard and an explicit list of deferred candidates.

Select defaults for editor-open coding, editor-closed local coding, and image review only where
tested. Retain explicit manual fallback and permission boundaries. Set practical context/output
and request budgets from observed tasks rather than advertising maximum model context.

Document request usage honestly: use inspected receipts/manual records first, or add tested
OpenCode accounting instrumentation before claiming automatic per-feature cost coverage. Do not
mistake free inference for unlimited requests or include separate agent usage in a zero-cost claim.
Update this roadmap, [MODELS.md](MODELS.md), [UNREAL.md](UNREAL.md), and the verification record
with scoped results, exact versions, evidence locations, approvals, and unresolved defects.

**Completion gate:** the team knows which tested route to use, when to switch, what it costs in
requests/time/review, and which measurements remain missing.

**Milestone B reached:** a reviewed lab slice and an evidence-based coding workflow exist.
This is still not proof of a production-proven studio template or validated scientific simulation.

## Ordered backlog — execute only when its prerequisites and scope are approved

These are follow-up work packages, not hidden requirements to begin steps 01–10. The ordering is
the recommended progression; explicitly deferred optional integrations do not block later product work.

### 17 — Verify the authorized native CI lane

- [ ] After step 09, configure an approved self-hosted Linux runner with a licensed engine and
  `UE_ROOT`, and run `.github/workflows/unreal-linux.yml` manually.
- [ ] Verify fresh build/prepare/test/package/smoke evidence and allowlisted artifact retention.
- [ ] Keep ordinary source CI separate. Never execute arbitrary fork/PR code on the licensed runner.
- [ ] Close the timeout/build-identity gaps in H5 before relying on unattended native outcomes.

**Done when:** one reviewed revision has a native CI pass. Remote creation, publication, and runner
access require separate approval; the prepared workflow alone is not a CI result.

### 18 — Add visual/performance regression baselines

- [ ] After steps 10–13, define human-approved camera/resolution/lighting/settings baselines.
- [ ] Add a reproducible native capture/review workflow and measured performance budgets.
- [ ] Preserve source, asset provenance, generator/runtime versions, and generated-output recipes.
- [ ] Test tolerances and failure reporting; do not treat headless state tests as visual regression.

**Done when:** an intentional visual/performance regression is detected without noisy false passes.

### 19 — Prove reuse with a real second deliverable

- [ ] After the first slice and step 16, choose one small game, interactive lab, simulation
  visualization, or 3D-branding deliverable with its own brief, budget, and acceptance gates.
- [ ] Reuse only proven pipeline parts; measure setup cost, review/rework time, and portability.
- [ ] Add domain/scientific validation separately if required. For branding, validate camera,
  materials, motion/render output, and brand approval rather than only gameplay checks.

**Done when:** the second deliverable is accepted on its own criteria without unbounded control-plane
growth. Do not resume parallel Godot/Mac product development just to claim multi-engine coverage.

### 20 — Complete product hardening and release readiness

- [ ] After a chosen deliverable's scope is stable, prioritize input/accessibility, audio, failure
  recovery, save/reset/persistence, packaging reliability, and target-machine compatibility as needed.
  Godot save/load behavior has not automatically been ported into Unreal.
- [ ] Review asset/model/engine licenses, source/IP privacy, distribution ownership, signing,
  security, and support/update plans for the intended game or non-game use.
- [ ] Obtain human playtest/art/product acceptance and explicit approval for any distribution,
  remote, push, purchase, credentials, or release signing operation.

**Done when:** the particular product's release gates pass. An internal package or source-test pass
does not grant permission to publish it.

### 21 — Evaluate optional editor MCP only if it solves a measured problem

- [ ] After native stability, evaluate the experimental official Unreal MCP plugin
  `ModelContextProtocol` before adopting an additional community bridge.
- [ ] Verify Linux behavior, localhost binding/authentication, project identity, ownership,
  scoped tools, and discovery/context cost. Generated OpenCode profiles currently deny MCP.
- [ ] Any enablement or policy change needs explicit review; never expose public editor ports or
  remove permissions wholesale. Do not attach to someone else's live Blender file.

**Done when:** a small demonstrable workflow benefit exceeds the security/context/maintenance cost.
Otherwise leave MCP disabled; the CLI/native automation path remains the default.

### 22 — Add paid generation/SDK integrations only with explicit justification

- [ ] Only if a real asset/workflow need cannot be met reasonably by existing tools, choose one
  approved provider and agree the budget, scoped credentials, licenses, and provider-side caps.
- [ ] Add reservation/persisted-job identity, usage receipts, timeout/reconciliation tests, and
  a reproducible evaluation before production use.
- [ ] Treat timeout as unknown; reconcile the original job instead of blindly resubmitting or
  clearing a hold. Do not start warming, autonomous loops, or paid fallback by default.

**Done when:** correctness, spend limits, recovery, and accounting are machine-verified and a
human authorizes use. The existing ledger balance is not purchase authorization.

### 23 — Revisit macOS or additional platforms only on demand

- [ ] Keep macOS deferred until a real delivery requirement and approved native host exist.
- [ ] Then review engine/toolchain compatibility, native input/render/runtime tests, packaging,
  and any signing/notarization requirements on that actual platform.

**Done when:** native evidence and human approval exist for the requested platform. The archived
Godot cross-export and old Mac CI notes are historical, not active Unreal acceptance or next steps.

## Stop/checkpoint rules

Stop when blocked, a required approval is missing, or the active task's attempts/time/budget is
exhausted. Preserve logs and user changes; never clear a failure by weakening checks or reverting
unrelated files. For a process/request timeout, inspect its identity/state before deciding to retry.
Never stop existing services to free GPU memory. Keep one owner per interactive editor, scene,
settings file, and integration operation. Source-check evidence does not establish rendering,
physical input, scientific accuracy, or human acceptance.

Use this template at the end of each work session:

```text
Date / owner:
Last completed step:
Active step and scope:
Status: implemented | machine_verified | human_approved (human only)
Files changed / checkpoint reference:
Commands actually executed and results:
Evidence paths / screenshots inspected:
Engine/model/runtime versions and settings, if relevant:
Human approvals granted / still needed:
Known defects / deferred optional steps:
Next single action:
```

Record important decisions in source-controlled notes when approved; raw evidence, builds,
receipts, and weights stay under ignored `.studio/` paths and need their own safe backup policy.
Never include credentials or authorization headers in handoffs, screenshots, or shared logs.

## Reference map

- [README](../README.md): project entry points and current command families.
- [UNREAL.md](UNREAL.md): Linux installation boundary, native gates, and Epic references.
- [MODELS.md](MODELS.md) and [model pins](../models.lock.json): research, memory policy, profiles, probes.
- [AI_CODING_RESEARCH.md](AI_CODING_RESEARCH.md): current primary sources, architecture/quantization
  alternatives, qualification findings H1–H7, and what remains unimplemented.
- [VERIFICATION.md](VERIFICATION.md): recorded checks and their limits.
- [PLAN.md](PLAN.md): short delivery plan plus clearly marked legacy history.
- [WORKFLOW.md](WORKFLOW.md), [ASSETS.md](ASSETS.md), [SECURITY.md](SECURITY.md): consult only for the active task.
- [OpenCode V2 providers](https://opencode.ai/v2/docs/providers),
  [model selection](https://opencode.ai/v2/docs/models), and
  [configuration](https://opencode.ai/v2/docs/config): activation references checked for this roadmap.

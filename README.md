# Novanode Studio — Unreal / Linux

Linux-first studio pipeline with an **Unreal C++ lab project**, Blender asset tools, bounded work
packages, cost/usage receipts, and opt-in OpenCode V2 profiles for free cloud and local models.
macOS is deferred. The Godot pilot is preserved as a legacy reference, not the primary engine.

## Current status

**Historical checkpoint, 2026-11-03:** Unreal 5.8.4 was installed and the lab editor launched. The owner confirmed
the window is visible. Actual native compilation, owned map/material preparation, all three native
state tests, and 77 Python/portable C++ tests passed. Real gameplay input, visual/performance quality,
packaged startup, and model coding quality remain separate unverified gates. This setup reused an
existing installation; it did not download an engine/model or accept Epic's license.

**2026-11-04:** official Lyra 5.8 is installed separately on this workstation, with the opt-in
`NovanodeHeroes` extension and versioned Hero Lab v2. Prior native build, standalone combat and
rendered-body probes passed; human visual/controls approval, retargeting, multiplayer, FPS and
packaging remain separate pending gates. See [Hero Lab usage and evidence](docs/HERO_SANDBOX.md).
These are historical receipts, not a claim that an old build verifies today's source/engine/content.

## Start here

For completed progress, numbered execution steps, approval gates, and the ordered backlog, use
the [execution roadmap](docs/EXECUTION_ROADMAP.md). Resume at its first unfinished required step.

Requires Python **3.11.8+**. A C++ compiler is needed for the portable state test.

On this workstation, `.studio/unreal.env` selects the discovered engine and
`python3 .studio/launch_unreal.py` opens the lab editor. Check existing ownership before launching;
do not start another instance. These helpers are ignored, machine-local files. See
[the exact installation and verification evidence](docs/UNREAL.md) for a fresh checkout.

```sh
python3 studio.py doctor
python3 studio.py task run tasks/unreal-source.json --execute
python3 studio.py unreal build
```

### Explicit project profiles — read-only first

```sh
python3 studio.py projects list
python3 studio.py projects status                     # matches studio.project: NovanodeLab
python3 studio.py projects status --profile hero-sandbox
python3 studio.py doctor --profile hero-sandbox       # same metadata-only diagnostic
python3 studio.py run --profile lab                   # existing lab preview
python3 studio.py run --profile hero-sandbox          # guarded play-v2 wrapper preview, no launch
```

`studio.project` remains unchanged; project profiles in `studio.toml` are distinct from the
coding-model profiles below. Status/explicit-profile doctors do not run tools, create `.studio`,
read engine logs, import local launch helpers or approve native/visual gates. They inspect bounded
metadata and owned source/module hashes. Missing `UE_ROOT`, engine mismatches, unknown jobs and
stale/unbound journals are reported without clearing holds or changing configuration.

Hero profile routing is **preview-only** for `run`/`unreal run`/`unreal editor`; `--execute` and other
native Hero routes are rejected, never redirected to NovanodeLab. Keep using the existing guarded
`projects/hero-sandbox/manage.py` launcher for authorized native work. Its fixed engine path and
ignored helper chain have **not** been migrated; a clean checkout can diagnose missing prerequisites,
not reconstruct/download Lyra automatically. Legacy commands without `--profile` retain their behavior.

Unreal actions **preview by default**. Install the Linux editor through your authorized Epic
account, review licensing/storage needs, and point `UE_ROOT` at the folder containing `Engine/`.
The prepared project targets the **5.8 version family**; another version needs an explicit review.
Close the editor normally before exclusive build, prepare, native-test, package, or smoke operations.

```sh
export UE_ROOT=/your/installed/UE_5.8
python3 studio.py unreal build --execute
python3 studio.py unreal prepare --execute
python3 studio.py unreal run --execute
```

Intended experience: a first-person modular Novanode research lab with an airlock, instrument
bays, emissive accents, Lumen lighting, contextual **E** interaction, and a compact HUD.
**WASD** moves; mouse looks; **Esc** toggles the cursor. Visual quality is not yet verified.
The pendulum display is an analytical reference, **not a validated physics simulation**.

See [Unreal setup and native gates](docs/UNREAL.md) before building.

## Free cloud and local coding models

Model cards and public API metadata were checked **2026-11-02**, not guessed from older names.

```sh
python3 studio.py models list
python3 studio.py models refresh-free
python3 studio.py models plan qwen38-main --mode solo
python3 studio.py models plan qwen35-small --mode editor
python3 studio.py models config --profile free
python3 studio.py models config --profile local --local-model qwen35-small
```

Profiles are written under `.studio/opencode/` and remain **inactive** until you review/copy
one to the project config. No global OpenCode settings are modified. Cloud profiles use explicit
`:free` routes with zero-price ceilings; local profiles allow only a localhost provider.
Neither activates an account, invokes a model, installs a server, or starts helper agents.

The RTX 3090 has **24 GiB VRAM shared with Unreal**. A ~16–19 GB weight file does not leave that
much VRAM available to the editor. Use free cloud coding while editing, a smaller local model for
bounded tasks, and larger local candidates with Unreal closed. Memory plans are estimates, not benchmarks.

[Model research, exact sizes, and setup](docs/MODELS.md) · [Pins and hashes](models.lock.json)

The [current AI coding architecture/tooling review](docs/AI_CODING_RESEARCH.md) adds new
mixed-precision/ternary research candidates and documents open qualification gates: real OpenCode
tool transport/compaction, probe freshness, request accounting, and spend/privacy enforcement.
These are not silently fixed or proven by metadata and source tests; profiles remain inactive.

## Native verification after setup

```sh
python3 studio.py unreal test --execute
python3 studio.py unreal package --execute
python3 studio.py unreal smoke --execute
```

Default CI runs Linux source/Python/portable C++ checks only. Native Unreal CI is manual on
an authorized self-hosted Linux runner. No Mac jobs, engine downloads, model requests, or paid
fallbacks are launched by CI. Art/feel, real keyboard input, performance, and external release
approval remain human gates.

## Project map

- `projects/NovanodeLab/`: primary Unreal descriptor, C++, and Linux settings.
- `scripts/unreal/`: generator-owned material/map preparation; refuses unmarked existing assets.
- `pipeline/`: task runner, ledger, asset inspection, Unreal adapter, model/profile tools.
- `tasks/unreal-source.json`: runnable checks without an engine install.
- `tasks/unreal-smoke.json`: native engine/package gates once configured.
- `.studio/`: ignored tools, models, logs, profiles, receipts, and build artifacts.
- `projects/lab/`: preserved Godot pilot; use explicit `godot` commands only for legacy work.

[Workflow](docs/WORKFLOW.md) · [Security](docs/SECURITY.md) · [Plan](docs/PLAN.md)
· [Verification record](docs/VERIFICATION.md) · [Legacy pilot](docs/LEGACY_GODOT.md)

The runner audits source writes after commands; it is **not an OS/network sandbox**. The ledger
tracks recorded jobs, not arbitrary OpenCode requests. No redistribution license, developer signing,
or automatic release acceptance is configured. Pushes and release publication require approval.

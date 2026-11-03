# Novanode Studio — Unreal / Linux

Linux-first studio pipeline with an **Unreal C++ lab project**, Blender asset tools, bounded work
packages, cost/usage receipts, and opt-in OpenCode V2 profiles for free cloud and local models.
macOS is deferred. The Godot pilot is preserved as a legacy reference, not the primary engine.

## Current status

**Prepared source, not a running Unreal build yet.** No licensed Unreal editor is installed here.
Python tools and portable C++ state logic can be tested now; engine compilation, rendering,
packaged startup, and actual model coding quality still need their respective runtime gates.
No Epic license was accepted, no engine/model weights downloaded, and no credentials changed.

## Start here

For completed progress, numbered execution steps, approval gates, and the ordered backlog, use
the [execution roadmap](docs/EXECUTION_ROADMAP.md). Resume at its first unfinished required step.

Requires Python **3.11.8+**. A C++ compiler is needed for the portable state test.

```sh
python3 studio.py doctor
python3 studio.py task run tasks/unreal-source.json --execute
python3 studio.py unreal build
```

Unreal actions **preview by default**. Install the Linux editor through your authorized Epic
account, review licensing/storage needs, and point `UE_ROOT` at the folder containing `Engine/`.
The prepared project targets the **5.8 version family**; another version needs an explicit review.

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
tracks recorded jobs, not arbitrary OpenCode requests. No redistribution license, remote,
publication credentials, developer signing, or automatic acceptance is configured.

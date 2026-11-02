# Legacy Godot pilot — archived README

Historical implementation, superseded by the Linux Unreal direction on 2026-11-02.
Source and local binaries were preserved. Current setup: `../README.md`.

A runnable, local-first foundation for a three-engineer AI-assisted studio on **Linux and macOS**.
It combines a small Godot lab, procedural Blender assets, bounded work packages, cost/token
receipts, and native build verification. No always-running agents or paid services are required.

**Status:** initial vertical slice. Linux execution has been tested locally. Native macOS
jobs are configured in CI but must run before macOS support is considered verified.
This is not yet a complete production studio, scientific simulator, or autonomous agent service.

## Quick start

Requires Python **3.11.8+** and a graphical session to play. The Python pipeline has no third-party
dependencies. Commands below run from this directory.

```sh
python3 studio.py test
python3 studio.py tools fetch godot
```

On Linux x86-64, fetch the pinned portable Blender:

```sh
python3 studio.py tools fetch blender
```

On macOS, install Blender **4.5.15 LTS** from the official download linked by the same command;
set `BLENDER_BIN` if it is not at `/Applications/Blender.app/Contents/MacOS/Blender`.
The Godot download is universal; Linux ARM64 does not have a bundled tool pin yet.

```sh
python3 studio.py doctor
python3 studio.py task run tasks/asset-bench.json --execute
python3 studio.py task run tasks/lab-smoke.json --execute
python3 studio.py godot run
```

In the lab: **WASD** move, **E** door, **P** power, **R** run. The buttons also work.
The pendulum readout is an analytical small-angle reference, not measured simulation output.

### Internal native builds

Export templates are optional and download approximately **1.3 GB**; tools stay under `.studio/`.

```sh
python3 studio.py tools fetch godot --templates
python3 studio.py godot export --platform linux --smoke
```

On a Mac, use `--platform macos --smoke`. Output: `.studio/builds/<platform>/`.
Linux builds are unsigned; macOS uses a local ad-hoc signature, not a developer identity or
notarization. Both are internal and are **not** approval to distribute. No remote or paid
provider is created, configured, or contacted by the demo pipeline.

### Evidence and context

```sh
python3 studio.py godot capture
python3 studio.py task context tasks/lab-smoke.json
python3 studio.py jobs report
```

- `.studio/evidence/lab.png`: fresh gameplay screenshot; requires a display.
- `.studio/runs/<run-id>/`: frozen contract, command logs, and atomic run report.
- `.studio/ledger.sqlite3`: settled costs and outstanding reservations.
- `.studio/receipts/`: content-addressed billing evidence; never commit credentials.

`task run` is a **dry run by default**. `--execute` runs trusted argv with your user's
privileges. Deadlines/retries are bounded and source writes are audited afterward; this is
**not a filesystem/network sandbox**. Ledger caps govern recorded reservations, not arbitrary
subprocess purchases. See [security boundaries](SECURITY.md).

## Repository map

| Path | Purpose |
|---|---|
| `pipeline/`, `studio.py` | Dependency-free automation and CLI |
| `projects/lab/` | Interactive Godot starter and 14-check gold path |
| `scripts/blender/` | Factory-startup, background procedural exports |
| `tasks/` | Executable contracts and a fail-closed feature template |
| `.cursor/skills/`, `AGENTS.md` | On-demand agent procedures and shared boundaries |
| `mcp.example.json` | Optional pinned Blender bridge; not activated |
| `.github/workflows/verify.yml` | Python matrix and native Blender → Godot → export checks |
| `tools.lock.json` | Reviewed tool versions, URLs, and SHA-256 pins |

## How the team uses it

1. A human approves a small brief and acceptance criteria.
2. An implementer receives only the task's bounded context.
3. Repeatable work runs as scripts; no helper swarm by default.
4. A reviewer checks diffs and fresh evidence, not the implementer's narrative.
5. A human plays/reviews the build before acceptance or distribution.

Start with [the workflow](WORKFLOW.md), [tooling](TOOLING.md), and
[the current plan](PLAN.md). See [verification results](VERIFICATION.md) for measured
coverage and gaps, and [asset conventions](ASSETS.md) before adding art.

## What is deliberately not enabled

- Paid image/3D/model adapters, account access, or automated purchases.
- A custom agent SDK framework or a hosted control plane.
- Automatic human approval, external publishing, developer-identity signing, or notarization.
- Complete glTF validation, rigging/animation gates, visual regression baselines,
  performance budgets on representative hardware, or scientific validation.

These are explicit follow-up gates, not implied capabilities. No redistribution license
has been selected for this project; obtain approval before publishing source or assets.

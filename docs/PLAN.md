# Delivery plan

## Active direction — Unreal / Linux, 2026-11-02

- User chose Unreal as the primary 3D engine; macOS is deferred.
- User chose project preparation first. No editor is installed; approximately 75 GiB was free.
- Prepared Unreal module, first-person lab layout, material/map generator, Linux command plans,
  state automation fixtures, and a manual licensed-runner workflow.
- Prepared OpenCode V2 free/local profiles, exact HF GGUF pins, memory-aware serving plans,
  and a local synthetic tool-transport probe. No weights were downloaded or models invoked.
- Python/portable C++ checks can run now; Unreal actors/UHT/rendering and deployed models cannot
  be called verified until their runtimes are installed and tested.

Next: install/configure authorized Linux editor → compile/prepare → native smoke → inspect visuals
and iterate on actual art/feel → benchmark free/local models on the same small Unreal tasks.
Keep existing local models intact. Use cloud/small local profiles while Unreal occupies the GPU.

The sections below describe the initial legacy foundation; superseded engine/Mac decisions
are preserved for history, not instructions to resume work on three engines.

## Implemented foundation

- Dependency-free Python CLI and bounded deterministic task runner.
- Compact explicit context handoffs; no agent swarm or unbounded stop hooks.
- Transactional SQLite reservations, resumable job identity, immutable cost/usage receipts.
- Background procedural Blender bench and independent static-prop checks.
- Godot interactive lab, input/collision/movement/save-load checks, and packaged-startup smoke.
- Optional inactive Blender MCP example and focused project skills.
- Linux/macOS CI configuration and a documented human release gate.

## Next gates (not yet complete)

1. Run the native macOS CI jobs on an approved private remote/runner.
2. Human playtest and art/interaction feedback on this small slice.
3. Choose a real second deliverable and prove template reuse without growing the control plane.
4. Benchmark feature cost, review time, rework, and frame-time/memory on representative machines.
5. If paid generation is justified, choose one provider; add an explicitly approved SDK adapter
   with provider-side caps, scoped credentials, timeout/reconciliation tests, and usage receipts.
6. Add visual regression baselines and specialist asset/domain gates only when needed.
7. Establish publishing licenses, signing/notarization, security review, and distribution ownership
   before an external product release.

## Decisions

- Godot + Blender was the initial pilot stack; Unreal/Linux supersedes it. Do not maintain three engines.
- This project is separate from `hackrf-webui`; that repository remains unchanged.
- Project-local tools rather than system installs; no remote, purchases, or account changes.
- Engine-native files/CLI first; optional MCP for interactive Blender only.
- Task argv are trusted local automation, not a claim of isolated or billable agent execution.
- Prototype scope: a lab reference calculation, not a home-grown physics engine.

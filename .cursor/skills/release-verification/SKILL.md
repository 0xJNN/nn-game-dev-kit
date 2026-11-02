---
name: release-verification
description: Verifies an internal Novanode build using functional, packaged-startup, and visual evidence. Use when explicitly asked to prepare a build or verify a release candidate.
disable-model-invocation: true
---

# Release verification

Read the release gate in `docs/WORKFLOW.md`.

1. Run Python/portable C++ tests and relevant asset validation. Source checks are not engine passes.
2. On the licensed Linux host, run `unreal build`, `prepare`, `test`, `package`, and `smoke` with `--execute`.
3. Inspect fresh native Unreal visuals and real E/WASD/mouse behavior. Do not reuse the Godot capture as Unreal evidence.
4. Record test/build hashes, hardware, known issues, and untested platforms.
5. Ask a human to play the build and approve visuals, feel, licensing, and scope.
6. An internal artifact is NOT an externally approved release. Do not publish, notarize, or use developer signing credentials.

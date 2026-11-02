---
name: asset-production
description: Produces and validates Novanode static props with Blender and provenance manifests. Use when explicitly assigned a modeling, GLB export, or asset integration task.
disable-model-invocation: true
---

# Asset production

Read `docs/ASSETS.md` and the approved style/asset brief only.

1. Prefer an existing licensed asset or a procedural construction before paid generation.
2. For this pilot, run `python3 studio.py task run tasks/asset-bench.json --execute`.
3. For a new asset, use a separate background Blender process and a unique output directory.
4. Export meters / glTF Y-up, bottom-center origin, embedded resources.
5. Record provenance and checksum; never label generated content as hand-authored.
6. Run `python3 studio.py assets validate <manifest>`. Unreal import is a separate native gate;
   do not claim the preserved Godot bench test proves Unreal integration.
7. Capture and inspect the result. Validation does not establish visual quality or rights ownership.
8. Leave human approval pending. Rig/animation assets need additional gates; do not bypass the static-prop validator.

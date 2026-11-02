# Shared static-prop production contract

Unreal/Linux is now primary. The runnable bench pipeline below belongs to the preserved Godot
pilot and independently validates GLB geometry/provenance. It is **not yet an Unreal import test**.
Native Unreal uses centimeters/Z-up; the meter/Y-up interchange must be verified at the import
boundary before integration. Current Unreal room primitives/materials are authored separately.

## Current route

Approved brief → reuse/procedural construction → background Blender → self-contained GLB →
checksum/provenance + independent binary inspection → Godot import → game-camera review → human acceptance.

```sh
python3 studio.py task run tasks/asset-bench.json --execute
python3 studio.py assets validate projects/lab/assets/generated/bench.manifest.json
```

The procedural bench is 1.6 m wide × 0.9 m high × 0.7 m deep, with 60 triangles. The Blender
exporter converts Z-up construction into glTF's Y-up. Generated outputs are reproducible and
ignored; the source script is versioned. The Godot fallback remains playable without them,
but packaged export requires the validated bench.

## Manifest fields

`schema_version`, `id`, checkout-relative `file`, `sha256`, `units: meters`, `up_axis: Y`,
and provenance (`kind`, `author`, `source`, `license`). CC-BY also requires `attribution`.
Generated assets additionally require `provider`, `model`, `job_id`, and `receipt`.

`LicenseRef-Novanode-Internal` is an internal workflow marker, **not** a legal license grant
or proof of ownership. An allowlisted identifier does not establish that the source had rights.
Do not download raw animation archives or marketplace content without verifying authorization.

## Enforced checks

- GLB 2.0 header/chunk boundaries and a single embedded binary buffer.
- Actual vertex/index data, scene transforms, triangle count, finite coordinates, world bounds.
- Bottom-center origin within 1 mm; meters/Y-up declaration.
- Embedded texture references (no silent dependence on external source directories).
- File size, triangle, dimension, checksum, and provenance budgets from `studio.toml`.

This small inspector is **not a complete Khronos validator**. It only accepts uncompressed
static triangle props. Sparse accessors, required extensions, morphs, skins, and animations
are refused; do not remove those guards to pass an incompatible asset.

Not checked: image resolution/quality, topology quality, UV quality, licensing ownership,
animation quality, rig weights, or physical correctness. Add specialist gates when those
asset types become real requirements. Never call a technical pass a visual approval.

## Future paid route

Approve one concept before 3D. Prefer a modular kit over one generation per prop. Reserve
the maximum expected cost, save the provider job ID, and reconcile timeouts. Allow a small
human-approved attempt count, then simplify/reuse rather than generating indefinitely.
Providers need an explicit, tested adapter before unattended submission is permitted.

"""Run only in an isolated background Blender process; never attach to a live file."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import bpy


def cube(name, location, dimensions, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    material = bpy.data.materials.new(name + "Material")
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = 0.65
    obj.data.materials.append(material)
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    root = args.root.resolve()
    target = root / "projects/lab/assets/generated"
    target.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    cube("BenchTop", (0, 0, 0.85), (1.6, 0.7, 0.1), (0.08, 0.5, 0.55))
    for x in (-0.65, 0.65):
        for y in (-0.23, 0.23):
            cube("BenchLeg", (x, y, 0.4), (0.1, 0.1, 0.8), (0.15, 0.2, 0.27))
    # Blender Z-up -> glTF Y-up is handled by the official exporter.
    temporary = target / "bench.pending.glb"
    output = target / "bench.glb"
    result = bpy.ops.export_scene.gltf(
        filepath=str(temporary), export_format="GLB", export_animations=False,
        export_cameras=False, export_lights=False, export_extras=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError("glTF export failed")
    os.replace(temporary, output)
    manifest = {
        "schema_version": 1, "id": "lab-bench-001",
        "file": output.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "units": "meters", "up_axis": "Y",
        "provenance": {
            "kind": "procedural", "author": "Novanode Studio",
            "source": "scripts/blender/build_bench.py",
            "license": "LicenseRef-Novanode-Internal",
        },
        "review": {"human_approval": "pending"},
    }
    pending = target / "bench.manifest.pending.json"
    pending.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(pending, target / "bench.manifest.json")
    print("NOVANODE_ASSET_EXPORTED " + str(output))


if __name__ == "__main__":
    main()

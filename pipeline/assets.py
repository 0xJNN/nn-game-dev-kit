from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

from .common import ROOT, StudioError, config, load_json, project_path

IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def multiply(a, b):
    return [sum(a[k * 4 + row] * b[column * 4 + k] for k in range(4))
            for column in range(4) for row in range(4)]


def node_matrix(node):
    if "matrix" in node:
        matrix = node["matrix"]
        if len(matrix) != 16 or not all(math.isfinite(v) for v in matrix):
            raise StudioError("Invalid node transform")
        return matrix
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    tx, ty, tz = node.get("translation", [0, 0, 0])
    return [
        (1 - 2*y*y - 2*z*z)*sx, (2*x*y + 2*z*w)*sx, (2*x*z - 2*y*w)*sx, 0,
        (2*x*y - 2*z*w)*sy, (1 - 2*x*x - 2*z*z)*sy, (2*y*z + 2*x*w)*sy, 0,
        (2*x*z + 2*y*w)*sz, (2*y*z - 2*x*w)*sz, (1 - 2*x*x - 2*y*y)*sz, 0,
        tx, ty, tz, 1,
    ]


def inspect_glb(path: Path) -> dict:
    """Small, strict static-prop inspector, NOT a complete Khronos glTF validator."""
    data = path.read_bytes()
    if len(data) < 20:
        raise StudioError("Truncated GLB")
    magic, version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise StudioError("Invalid GLB 2.0 header or length")
    offset, chunks = 12, []
    while offset < length:
        if offset + 8 > length:
            raise StudioError("Truncated GLB chunk")
        size, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if size % 4 or offset + size > length:
            raise StudioError("Invalid GLB chunk length")
        chunks.append((kind, data[offset:offset+size]))
        offset += size
    if not chunks or chunks[0][0] != 0x4E4F534A:
        raise StudioError("GLB must start with JSON")
    document = json.loads(chunks[0][1])
    if document.get("asset", {}).get("version") != "2.0":
        raise StudioError("Expected glTF 2.0")
    if document.get("extensionsRequired") or document.get("skins") or document.get("animations"):
        raise StudioError("Pilot validator supports uncompressed static props only")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or buffers[0].get("uri"):
        raise StudioError("Only one embedded GLB buffer is supported; external files refused")
    binary = next((chunk for kind, chunk in chunks if kind == 0x004E4942), b"")
    if buffers[0]["byteLength"] > len(binary):
        raise StudioError("Truncated embedded buffer")
    for image in document.get("images", []):
        if "uri" in image or "bufferView" not in image:
            raise StudioError("Textures must be embedded, not resolved from the source directory")

    def accessor(index):
        item = document["accessors"][index]
        if "sparse" in item or "bufferView" not in item:
            raise StudioError("Sparse/implicit accessors are not supported in the static-prop gate")
        view = document["bufferViews"][item["bufferView"]]
        if view.get("buffer", 0) != 0:
            raise StudioError("Unexpected buffer index")
        formats = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}
        sizes = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
        if item["componentType"] not in formats or item["type"] not in sizes:
            raise StudioError("Unsupported accessor format")
        pattern = "<" + formats[item["componentType"]] * sizes[item["type"]]
        packed_size = struct.calcsize(pattern)
        stride = view.get("byteStride", packed_size)
        count = item["count"]
        start = view.get("byteOffset", 0) + item.get("byteOffset", 0)
        end = start + (count - 1) * stride + packed_size
        view_end = view.get("byteOffset", 0) + view["byteLength"]
        if count <= 0 or stride < packed_size or start < 0 or end > min(view_end, len(binary)):
            raise StudioError("Accessor exceeds embedded data")
        return [struct.unpack_from(pattern, binary, start + i * stride) for i in range(count)]

    points, triangles = [], 0

    def visit(index, parent, ancestors):
        nonlocal triangles
        if index in ancestors:
            raise StudioError("Cycle in scene hierarchy")
        node = document["nodes"][index]
        world = multiply(parent, node_matrix(node))
        if "mesh" in node:
            mesh = document["meshes"][node["mesh"]]
            for primitive in mesh["primitives"]:
                if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                    raise StudioError("Only static triangle primitives are supported")
                positions = accessor(primitive["attributes"]["POSITION"])
                if any(len(point) != 3 for point in positions):
                    raise StudioError("Expected VEC3 positions")
                count = len(positions)
                if "indices" in primitive:
                    indices = accessor(primitive["indices"])
                    if any(len(i) != 1 or type(i[0]) is not int or not 0 <= i[0] < count
                           for i in indices):
                        raise StudioError("Invalid mesh index")
                    count = len(indices)
                if count % 3:
                    raise StudioError("Incomplete triangle")
                triangles += count // 3
                for point in positions:
                    transformed = [sum(world[k*4+axis] * point[k] for k in range(3))
                                   + world[12+axis] for axis in range(3)]
                    if not all(math.isfinite(v) for v in transformed):
                        raise StudioError("Non-finite mesh coordinate")
                    points.append(transformed)
        for child in node.get("children", []):
            visit(child, world, ancestors | {index})

    scene = document["scenes"][document.get("scene", 0)]
    for index in scene.get("nodes", []):
        visit(index, IDENTITY, set())
    if not points or not triangles:
        raise StudioError("Asset contains no visible triangle mesh")
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    return {"triangles": triangles, "bounds_min_m": minimum, "bounds_max_m": maximum,
            "dimensions_m": [maximum[i] - minimum[i] for i in range(3)],
            "embedded_images": len(document.get("images", []))}


def validate_asset(manifest_path: Path, root: Path = ROOT) -> dict:
    manifest = load_json(manifest_path)
    rules = config(root)["assets"]
    if manifest.get("schema_version") != 1:
        raise StudioError("Unsupported asset manifest version")
    for key in ("id", "file", "sha256", "units", "up_axis", "provenance"):
        if not manifest.get(key):
            raise StudioError(f"Missing asset manifest field: {key}")
    if manifest["units"] != "meters" or manifest["up_axis"] != "Y":
        raise StudioError("Engine interchange assets must use meters and Y-up")
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict) or provenance.get("kind") not in {"procedural", "library", "generated"}:
        raise StudioError("Asset provenance kind must be procedural, library, or generated")
    for key in ("kind", "author", "source", "license"):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            raise StudioError(f"Missing provenance field: {key}")
    if provenance["license"] not in rules["allowed_licenses"]:
        raise StudioError("License requires explicit review before integration")
    if provenance["license"] == "CC-BY-4.0" and not provenance.get("attribution"):
        raise StudioError("CC-BY asset requires attribution text")
    if provenance["kind"] == "generated" and not all(
        provenance.get(key) for key in ("provider", "model", "job_id", "receipt")
    ):
        raise StudioError("Generated assets require provider, model, job_id, receipt")
    asset = project_path(manifest["file"], root)
    if asset.suffix.lower() != ".glb" or not asset.is_file():
        raise StudioError("Expected an existing self-contained GLB")
    if asset.stat().st_size > rules["max_file_bytes"]:
        raise StudioError("Asset exceeds file size budget")
    with asset.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        raise StudioError("Asset checksum differs from its manifest")
    try:
        metrics = inspect_glb(asset)
    except (KeyError, IndexError, TypeError, ValueError, struct.error, RecursionError) as exc:
        raise StudioError(f"Malformed or unsupported GLB: {exc}") from exc
    if metrics["triangles"] > rules["max_triangles"]:
        raise StudioError("Asset exceeds triangle budget")
    if max(metrics["dimensions_m"]) > rules["max_dimension_m"]:
        raise StudioError("Asset exceeds world-space dimension budget")
    low, high = metrics["bounds_min_m"], metrics["bounds_max_m"]
    if abs(low[1]) > 0.001 or abs(low[0] + high[0]) > 0.002 or abs(low[2] + high[2]) > 0.002:
        raise StudioError("Static props must have a bottom-center origin within 1 mm")
    return {"asset_id": manifest["id"], "status": "machine_verified",
            "human_approval": "pending", "sha256": digest, "metrics": metrics,
            "not_checked": ["visual quality", "topology quality", "texture resolution",
                            "license ownership", "rigging and animation"]}

import hashlib
import json
import struct

from helpers import ProjectTest
from pipeline.assets import validate_asset
from pipeline.common import StudioError, atomic_json


class AssetTests(ProjectTest):
    def asset(self, translate_y=0, external=False, points=None, provenance=None):
        points = points or [(-0.5, 0, 0), (0.5, 0, 0), (0, 1, 0)]
        binary = b"".join(struct.pack("<fff", *point) for point in points)
        doc = {
            "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "translation": [0, translate_y, 0]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [{"buffer": 0, "byteLength": len(binary)}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": len(points)}],
        }
        if external:
            doc["buffers"][0]["uri"] = "../secret.bin"
        encoded = json.dumps(doc).encode()
        encoded += b" " * (-len(encoded) % 4)
        size = 12 + 8 + len(encoded) + 8 + len(binary)
        data = struct.pack("<4sII", b"glTF", 2, size)
        data += struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
        data += struct.pack("<II", len(binary), 0x004E4942) + binary
        (self.root / "asset.glb").write_bytes(data)
        manifest = {
            "schema_version": 1, "id": "test-prop", "file": "asset.glb",
            "sha256": hashlib.sha256(data).hexdigest(), "units": "meters", "up_axis": "Y",
            "provenance": provenance or {"kind": "procedural", "author": "Novanode",
                "source": "tests", "license": "LicenseRef-Novanode-Internal"},
        }
        path = self.root / "manifest.json"
        atomic_json(path, manifest)
        return path

    def test_valid_static_prop_uses_actual_binary_coordinates(self):
        result = validate_asset(self.asset(), self.root)
        self.assertEqual(result["metrics"]["triangles"], 1)
        self.assertEqual(result["metrics"]["dimensions_m"], [1.0, 1.0, 0.0])
        self.assertEqual(result["human_approval"], "pending")

    def test_checksum_mismatch_is_refused(self):
        manifest = self.asset()
        with (self.root / "asset.glb").open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaises(StudioError):
            validate_asset(manifest, self.root)

    def test_world_space_pivot_is_checked(self):
        with self.assertRaises(StudioError):
            validate_asset(self.asset(translate_y=0.5), self.root)

    def test_external_buffers_are_refused(self):
        with self.assertRaises(StudioError):
            validate_asset(self.asset(external=True), self.root)

    def test_large_dimensions_are_refused(self):
        with self.assertRaises(StudioError):
            validate_asset(self.asset(points=[(-20, 0, 0), (20, 0, 0), (0, 1, 0)]), self.root)

    def test_nonfinite_positions_are_refused(self):
        with self.assertRaises(StudioError):
            validate_asset(self.asset(points=[(float("nan"), 0, 0), (1, 0, 0), (0, 1, 0)]), self.root)

    def test_unknown_license_is_not_silently_accepted(self):
        provenance = {"kind": "library", "author": "Someone", "source": "somewhere", "license": "free"}
        with self.assertRaises(StudioError):
            validate_asset(self.asset(provenance=provenance), self.root)

    def test_attribution_required_for_cc_by(self):
        provenance = {"kind": "library", "author": "Someone", "source": "somewhere", "license": "CC-BY-4.0"}
        with self.assertRaises(StudioError):
            validate_asset(self.asset(provenance=provenance), self.root)
        provenance["attribution"] = "Asset by Someone, CC BY 4.0, source link"
        self.assertEqual(validate_asset(self.asset(provenance=provenance), self.root)["status"], "machine_verified")

    def test_generated_assets_need_job_provenance(self):
        provenance = {"kind": "generated", "author": "Novanode", "source": "provider",
                      "license": "LicenseRef-Novanode-Internal"}
        with self.assertRaises(StudioError):
            validate_asset(self.asset(provenance=provenance), self.root)

import copy
import ast
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

from pipeline.common import ROOT, StudioError
from pipeline.resources import (
    approved_download_url, eligible, fetch_item, safe_extract, safe_url, validate_catalog,
)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".studio" / "resource-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = json.loads((ROOT / "resources/hero-sandbox/catalog.json").read_text())
        self.item = copy.deepcopy(self.catalog["items"][0])

    def archive(self, items):
        path = self.root / "media.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name, content in items:
                output.writestr(name, content)
        return path

    def test_real_catalog_has_item_level_license_and_explicit_ai_status(self):
        self.assertEqual(validate_catalog(self.catalog), self.catalog)
        self.assertTrue(all(i["license_evidence"] for i in self.catalog["items"]))

    def test_duplicate_ids_and_missing_license_evidence_are_refused(self):
        self.catalog["items"].append(copy.deepcopy(self.catalog["items"][0]))
        with self.assertRaises(StudioError): validate_catalog(self.catalog)
        self.catalog["items"].pop()
        self.catalog["items"][0]["license_evidence"] = ""
        with self.assertRaises(StudioError): validate_catalog(self.catalog)

    def test_free_price_does_not_clear_candidate_or_account_requirement(self):
        for field, value in (("review", "candidate"), ("account_required", True), ("price_usd", "1.00")):
            item = copy.deepcopy(self.item)
            item[field] = value
            with self.assertRaises(StudioError): eligible(item)

    def test_engine_use_is_separate_from_restricted_or_unknown_ai_input(self):
        for policy in ("restricted", "unknown"):
            self.item["ai_input"] = policy
            self.assertTrue(eligible(self.item, "engine"))
            with self.assertRaises(StudioError): eligible(self.item, "ai")

    def test_attribution_required_for_cc_by(self):
        self.item["license_id"] = "CC-BY-4.0"
        with self.assertRaises(StudioError): eligible(self.item)
        self.item["attribution"] = "Example by Original Author, CC BY 4.0, source URL"
        self.assertTrue(eligible(self.item))

    def test_unknown_license_and_unknown_purpose_are_not_inferred(self):
        self.item["license_id"] = "free"
        with self.assertRaises(StudioError): eligible(self.item)
        with self.assertRaises(StudioError): eligible(self.item, "publish")

    def test_non_https_credentials_local_and_unreviewed_redirects_are_refused(self):
        for url in ("http://example.org/a", "https://user:password@example.org/a", "https://127.0.0.1/a", "https://localhost/a"):
            with self.assertRaises(StudioError): safe_url(url)
        with self.assertRaises(StudioError): approved_download_url("https://unreviewed.example/a.glb")

    def test_zip_traversal_absolute_windows_and_symlinks_fail_before_writes(self):
        for bad in ("../escape.glb", "/absolute.glb", "a\\..\\escape.glb", "C:/escape.glb"):
            archive = self.archive([("safe.glb", b"glTF"), (bad, b"x")])
            with self.assertRaises(StudioError): safe_extract(archive, self.root / "out")
            self.assertFalse((self.root / "out").exists())
        link = zipfile.ZipInfo("evil.glb")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.archive([(link, b"/outside")])
        with self.assertRaises(StudioError): safe_extract(archive, self.root / "out")

    def test_case_collisions_and_compression_bombs_are_refused(self):
        for items in ([("a.glb", b"x"), ("A.glb", b"y")], [("bomb.txt", b"0" * 500000)]):
            archive = self.archive(items)
            with self.assertRaises(StudioError): safe_extract(archive, self.root / "out")
            self.assertFalse((self.root / "out").exists())

    def test_archive_extracts_only_media_and_preserves_existing_destination(self):
        archive = self.archive([("clips/a.glb", b"glTF"), ("run.py", b"danger"), ("rig.blend", b"embedded_scripts")])
        entries = safe_extract(archive, self.root / "out")
        self.assertEqual([e["file"] for e in entries], ["clips/a.glb"])
        self.assertEqual(entries[0]["sha256"], hashlib.sha256(b"glTF").hexdigest())
        with self.assertRaises(StudioError): safe_extract(archive, self.root / "out")

    def test_wrong_media_type_and_checksum_mismatch_do_not_get_imported(self):
        self.item["download"] = {"kind": "direct", "url": "https://static.poly.pizza/example.glb", "filename": "mesh.glb"}
        with patch("pipeline.resources.request", return_value=io.BytesIO(b"<html>login</html>")):
            with self.assertRaises(StudioError): fetch_item(self.item, self.root)
        with patch("pipeline.resources.request", return_value=io.BytesIO(b"glTFchanged")):
            with self.assertRaises(StudioError): fetch_item(self.item, self.root)
        self.assertFalse((self.root / ".studio/downloads").exists())

    def test_live_combat_rules_compile_and_cover_cooldowns_combo_and_deduplication(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "The repository's portable native checks require a C++ compiler")
        include = ROOT / "projects/hero-sandbox/NovanodeHeroes/Source/NovanodeHeroes/Public"
        source = self.root / "rules.cpp"
        source.write_text('''#include "HeroCombatRules.h"
#include <cassert>
#include <limits>
int main() {
  using namespace NovanodeHeroes;
  CombatRules r;
  assert(!r.TryPrimary(-1.));
  assert(!r.TryPrimary(std::numeric_limits<double>::quiet_NaN()));
  assert(!r.TryPrimary(std::numeric_limits<double>::infinity()));
  assert(r.TryPrimary(1.));
  assert(!r.TryPrimary(1.1));
  assert(!r.TryDash(1.));
  r.Select(Kit::Sword);
  assert(!r.TryPrimary(1.2));
  assert(r.TryPrimary(1.8) && r.Combo == 1);
  assert(r.FirstHit(7) && !r.FirstHit(7));
  assert(r.TryPrimary(2.3) && r.Combo == 2 && r.FirstHit(7));
  assert(r.TryPrimary(2.8) && r.Combo == 3 && r.Damage() == 30.f);
  assert(!r.TryPrimary(3.));
  assert(r.TryPrimary(5.) && r.Combo == 1);
  assert(r.TryDash(5.) && !r.TryDash(5.1));
  r.Select(Kit::Mage); r.Select(Kit::Sword);
  assert(!r.TryDash(6.) && r.TryDash(7.5));
}''')
        binary = self.root / "rules"
        result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I", str(include), str(source), "-o", str(binary)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(subprocess.run([str(binary)], timeout=10).returncode, 0)

    def test_replication_macro_regression_uses_required_argument_name(self):
        cpp = (ROOT / "projects/hero-sandbox/NovanodeHeroes/Source/NovanodeHeroes/Private/HeroSandbox.cpp").read_text()
        # DOREPLIFETIME macros reference OutLifetimeProps by name internally.
        self.assertEqual(cpp.count("GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps)"), 2)
        self.assertIn('StartsWith(TEXT("/NovanodeHeroes/Maps/"))', cpp)
        self.assertIn('StartsWith(TEXT("/NovanodeHeroes/Experiences/"))', cpp)

    def test_partial_map_is_not_misreported_as_a_complete_reused_map(self):
        recipe = ast.parse((ROOT / "projects/hero-sandbox/prepare_unreal.py").read_text())
        function = next(n for n in recipe.body if isinstance(n, ast.FunctionDef) and n.name == "level")
        module = ast.Module(body=[function], type_ignores=[])
        levels = SimpleNamespace(load_level=lambda _: True, save_current_level=lambda: True)
        settings = SimpleNamespace(get_editor_property=lambda _: [], set_editor_property=lambda *_: None)
        world = SimpleNamespace(get_world_settings=lambda: settings)
        calls = []
        actor_subsystem = SimpleNamespace(get_all_level_actors=lambda: [])
        fake = SimpleNamespace(
            LevelEditorSubsystem="levels", UnrealEditorSubsystem="world", EditorActorSubsystem="actors",
            get_editor_subsystem=lambda name: {"levels": levels, "world": SimpleNamespace(get_editor_world=lambda: world), "actors": actor_subsystem}[name],
            Name=lambda name: name, load_class=lambda *_: object(),
            HeroSandboxEditorTools=SimpleNamespace(configure_owned_map=lambda *_: calls.append("configure") or False),
            StaticMeshActor=type("Mesh", (), {}), SkeletalMeshActor=type("Skeletal", (), {}), TextRenderActor=type("Text", (), {}),
        )
        namespace = {"PREFIX": "/NovanodeHeroes", "LIB": SimpleNamespace(does_asset_exist=lambda _: True),
                     "unreal": fake, "record": lambda *_, **__: None}
        exec(compile(module, "owned-level-recipe", "exec"), namespace)
        with self.assertRaisesRegex(AssertionError, "experience assignment"):
            namespace["level"](object(), [], [])
        self.assertEqual(calls, ["configure"])
        settings.get_editor_property = lambda _: ["NN_HERO_RECIPE_V1_COMPLETE"]
        namespace["level"](object(), [], [])
        self.assertEqual(calls, ["configure"], "Only an explicitly completed owned map may be reused")

    def test_stale_binary_or_failed_build_cannot_qualify_current_source(self):
        spec = importlib.util.spec_from_file_location("hero_manager_test", ROOT / "projects/hero-sandbox/manage.py")
        manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager)
        binary = self.root / "plugin.so"
        binary.write_bytes(b"\x7fELFsynthetic-owned-test")
        hashes = {"own.cpp": "a" * 64}
        row = {"operation": "build", "state": "completed", "exit_code": 0, "source_sha256": hashes,
               "native_module_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "job_id": "build-owned-test"}
        self.assertEqual(manager.verify_build_identity(hashes, binary, [row]), "build-owned-test")
        for field, value in (("state", "blocked"), ("source_sha256", {"own.cpp": "b" * 64}), ("native_module_sha256", "0" * 64)):
            failed = {**row, field: value}
            with self.assertRaises(StudioError): manager.verify_build_identity(hashes, binary, [failed])

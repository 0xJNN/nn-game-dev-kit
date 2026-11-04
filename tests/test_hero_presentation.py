import ast
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pipeline.common import ROOT, StudioError


class HeroPresentationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".studio/presentation-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        path = ROOT / "projects/hero-sandbox/manage.py"
        spec = importlib.util.spec_from_file_location("hero_presentation_manager", path)
        self.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.manager)

    def test_exact_live_text_facing_and_body_rules_compile(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler)
        source = self.root / "presentation.cpp"
        source.write_text('''#include "HeroPresentationRules.h"
#include <cassert>
#include <cmath>
#include <limits>
int main() {
  using namespace NovanodeHeroes;
  constexpr double Pi = 3.14159265358979323846;
  // Every quadrant: the readable local -X face must point toward the viewer.
  for (int degree = -180; degree <= 180; degree += 15) {
    const double x = 600. * std::cos(degree * Pi / 180.);
    const double y = 600. * std::sin(degree * Pi / 180.);
    const double yaw = TextFacingYaw(0., 0., x, y) * Pi / 180.;
    const double dot = (-std::cos(yaw) * x - std::sin(yaw) * y) / 600.;
    assert(dot > .999999);
  }
  assert(std::abs(TextFacingYaw(1300., 0., 0., 0.)) < .00001);
  assert(TextFacingYaw(0., 0., 0., 0., 45.) == 45.);
  assert(TextFacingYaw(0., 0., std::numeric_limits<double>::quiet_NaN(), 0., 25.) == 25.);
  assert(!HasUsableBody(0, 0, 1, 0)); // The observed four-vertex proxy is NOT a body.
  assert(!HasUsableBody(1, 0, 1, 1));
  assert(!HasUsableBody(1, 1, 0, 1));
  assert(!HasUsableBody(1, 1, 1, 0));
  assert(HasUsableBody(1, 1, 1, 1));
}''')
        binary = self.root / "presentation"
        include = ROOT / "projects/hero-sandbox/NovanodeHeroes/Source/NovanodeHeroes/Public"
        result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
                                 "-I", str(include), str(source), "-o", str(binary)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(subprocess.run([str(binary)], timeout=10).returncode, 0)

    def test_unrecognized_staged_cpp_is_not_silently_compiled(self):
        stage = self.root / "plugin"
        code = stage / "Source/Module/Owned.cpp"
        code.parent.mkdir(parents=True)
        code.write_text("// Original test file\n")
        hashes = {"Source/Module/Owned.cpp": hashlib.sha256(code.read_bytes()).hexdigest()}
        with patch.object(self.manager, "STAGE", stage):
            self.manager.verify_staged_code_paths(hashes)
            (code.parent / "Unrecognized.cpp").write_text("// Preserve, do not execute\n")
            with self.assertRaises(StudioError):
                self.manager.verify_staged_code_paths(hashes)
        self.assertTrue((code.parent / "Unrecognized.cpp").exists())

    def test_v2_requires_its_own_prepared_map_not_just_v1(self):
        stage = self.root / "plugin"
        content = stage / "Content/Maps"
        content.mkdir(parents=True)
        (content / "L_HeroSandbox_v1.umap").write_bytes(b"synthetic-owned-v1")
        hashes = {"Maps/L_HeroSandbox_v1.umap": hashlib.sha256(b"synthetic-owned-v1").hexdigest()}
        row = {"job_id": "prepare-owned-test", "operation": "prepare", "state": "completed",
               "preparation": {"state": "prepared", "generated_sha256": hashes}}
        with patch.object(self.manager, "STAGE", stage):
            self.assertEqual(self.manager.verify_prepared_assets([row]), "prepare-owned-test")
            with self.assertRaises(StudioError):
                self.manager.verify_prepared_assets([row], "Maps/L_HeroSandbox_v2.umap")
            (content / "L_HeroSandbox_v2.umap").write_bytes(b"synthetic-owned-v2")
            hashes["Maps/L_HeroSandbox_v2.umap"] = hashlib.sha256(b"synthetic-owned-v2").hexdigest()
            row["operation"] = "prepare-v2"
            self.assertEqual(self.manager.verify_prepared_assets([row], "Maps/L_HeroSandbox_v2.umap"), "prepare-owned-test")
            (content / "L_HeroSandbox_v1.umap").write_bytes(b"unrecognized-edit")
            with self.assertRaises(StudioError):
                self.manager.verify_prepared_assets([row], "Maps/L_HeroSandbox_v2.umap")

    def test_blocked_creation_is_not_a_play_approval_without_fresh_strict_validation(self):
        stage = self.root / "plugin"
        content = stage / "Content/Maps"
        content.mkdir(parents=True)
        (content / "L_HeroSandbox_v2.umap").write_bytes(b"owned-v2")
        hashes = {"Maps/L_HeroSandbox_v2.umap": hashlib.sha256(b"owned-v2").hexdigest()}
        blocked = {"operation": "prepare-v2", "state": "blocked", "job_id": "blocked-creation",
                   "preparation": {"state": "prepared", "generated_sha256": hashes}}
        with patch.object(self.manager, "STAGE", stage):
            with self.assertRaises(StudioError):
                self.manager.verify_prepared_assets([blocked], "Maps/L_HeroSandbox_v2.umap")
            checked = {**blocked, "operation": "validate-v2", "state": "completed", "job_id": "fresh-readonly-validation"}
            self.assertEqual(self.manager.verify_prepared_assets([blocked, checked], "Maps/L_HeroSandbox_v2.umap"),
                             "fresh-readonly-validation")

    def test_validation_uses_native_type_check_for_nonexported_engine_action(self):
        code = (ROOT / "projects/hero-sandbox/validate_presentation.py").read_text()
        self.assertIn("validate_owned_cosmetic_assembly_action(cls)", code)
        self.assertNotIn("unreal.GameFeatureAction_AddComponents", code)

    def test_cosmetics_adapter_is_narrow_and_does_not_copy_match_action_sets(self):
        path = ROOT / "projects/hero-sandbox/NovanodeHeroes/Source/NovanodeHeroes/Private/HeroPresentation.cpp"
        code = path.read_text()
        self.assertIn("Component->IsChildOf(ControllerParts)", code)
        self.assertIn("Selected.Num() != 1", code)
        self.assertIn('StartsWith(TEXT("/NovanodeHeroes/Experiences/B_HeroSandbox_v2."))', code)
        self.assertIn("Vertices >= 256", code)
        self.assertIn("GetAnimInstance() || Component->LeaderPoseComponent.IsValid()", code)

    def test_calibration_refuses_foreign_visuals_before_requesting_screenshot(self):
        path = ROOT / "projects/hero-sandbox/NovanodeHeroes/Source/NovanodeHeroes/Private/HeroPresentation.cpp"
        code = path.read_text()
        self.assertIn('TEXT("/NovanodeHeroes/Maps/L_TextCalibration_v2")', code)
        self.assertIn("if (Mesh->GetSkeletalMeshAsset()) bAllowed = false", code)
        self.assertIn('StartsWith(TEXT("/Engine/BasicShapes/"))', code)
        self.assertLess(code.index("if (!bAllowed || Texts != 2)"), code.index("FScreenshotRequest::RequestScreenshot"))

    def test_v2_recipe_has_pre_and_post_preservation_checks_and_no_v1_asset_writes(self):
        path = ROOT / "projects/hero-sandbox/prepare_presentation.py"
        tree = ast.parse(path.read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        calls = [node for node in ast.walk(main) if isinstance(node, ast.Call) and
                 isinstance(node.func, ast.Name) and node.func.id == "old_content_unchanged"]
        self.assertEqual(len(calls), 2)
        code = path.read_text()
        self.assertIn('"/Maps/L_HeroSandbox_v2"', code)
        self.assertIn('"/Experiences/B_HeroSandbox_v2"', code)
        self.assertNotIn("duplicate_asset", code)
        self.assertNotIn("delete_asset", code)
        self.assertNotIn("rename_asset", code)

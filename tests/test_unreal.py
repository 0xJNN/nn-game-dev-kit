import os
import shutil
import subprocess
from unittest.mock import patch

from helpers import ProjectTest
from pipeline.common import ROOT, StudioError, atomic_json
from pipeline.unreal import commands, doctor, engine_root, run, validate_source, verify_automation, verify_smoke


class UnrealTests(ProjectTest):
    def setUp(self):
        super().setUp()
        shutil.copytree(ROOT / "projects/NovanodeLab", self.root / "projects/NovanodeLab",
                        ignore=shutil.ignore_patterns("Binaries", "Intermediate", "Saved", "Content"))

    def test_source_validation_does_not_claim_native_verification(self):
        result = validate_source(self.root)
        self.assertEqual(result["status"], "source_validated")
        self.assertFalse(result["native_build_verified"])

    def test_missing_engine_is_actionable_not_an_auto_download(self):
        with patch.dict(os.environ, {"UE_ROOT": ""}):
            result = doctor(self.root)
            self.assertFalse(result["ready"])
            self.assertIn("UE_ROOT", result["setup_required"])

    def test_preview_never_runs_unreal(self):
        with patch("pipeline.unreal.run_process") as process:
            result = run("build", root=self.root)
            process.assert_not_called()
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("NovanodeLabEditor", result["commands"][0])

    def test_version_mismatch_is_refused(self):
        engine = self.root / "engine"
        atomic_json(engine / "Engine/Build/Build.version", {"MajorVersion": 5, "MinorVersion": 7})
        with patch.dict(os.environ, {"UE_ROOT": str(engine)}), self.assertRaises(StudioError):
            engine_root(self.root)

    def test_linux_package_uses_native_uat_without_shell_expansion(self):
        argv = commands("package", self.root / "engine", self.root)[0]
        self.assertIn("-platform=Linux", argv)
        self.assertIn("-clientconfig=Development", argv)
        self.assertNotIn("-platform=Mac", argv)

    def report(self):
        names = ["Novanode.State.Prerequisites", "Novanode.State.Period", "Novanode.State.InvalidInputs"]
        return {"failed": 0, "notRun": 0, "inProcess": 0, "tests": [
            {"fullTestPath": name, "state": "Success", "errors": 0} for name in names
        ]}

    def test_native_report_requires_all_named_tests(self):
        path = self.root / "index.json"
        atomic_json(path, self.report())
        result = verify_automation(path)
        self.assertEqual(result["status"], "machine_verified")
        self.assertEqual(result["human_approval"], "pending")

    def test_skipped_failed_duplicate_or_missing_tests_do_not_pass(self):
        for variant in ("skip", "failed", "duplicate", "missing"):
            report = self.report()
            if variant == "skip":
                report["tests"][0]["state"] = "Skipped"
            elif variant == "failed":
                report["failed"] = 1
            elif variant == "duplicate":
                report["tests"][0] = report["tests"][1]
            else:
                report["tests"].pop()
            path = self.root / "index.json"
            atomic_json(path, report)
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                verify_automation(path)

    def test_portable_cpp_state_compiles_and_runs_without_unreal(self):
        compiler = shutil.which("clang++") or shutil.which("c++")
        if not compiler:
            self.skipTest("C++ compiler unavailable; native state logic not exercised")
        output = self.root / "lab-state-test"
        include = ROOT / "projects/NovanodeLab/Source/NovanodeLab/Public"
        result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                 "-I", str(include), str(ROOT / "tests/cpp/lab_state_test.cpp"),
                                  "-o", str(output)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def smoke_report(self):
        names = ["authored material loaded", "reference rejects missing prerequisites",
                 "closed door blocks world-space ray", "open door clears collision ray",
                 "reference completes with correct period"]
        return {"status": "passed", "human_approval": "pending",
                "checks": [{"name": name, "passed": True} for name in names]}

    def test_smoke_requires_the_actual_named_outcomes(self):
        path = self.root / "startup.json"
        atomic_json(path, self.smoke_report())
        result = verify_smoke(path)
        self.assertEqual(result["status"], "machine_verified")
        self.assertIn("not physical keyboard", result["scope"])

    def test_smoke_rejects_duplicate_and_invented_passes(self):
        report = self.smoke_report()
        report["checks"][0] = report["checks"][1]
        path = self.root / "startup.json"
        atomic_json(path, report)
        with self.assertRaises(StudioError):
            verify_smoke(path)

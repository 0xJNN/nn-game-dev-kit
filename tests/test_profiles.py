import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch

from helpers import ProjectTest
from pipeline import cli, profiles
from pipeline.common import StudioError, atomic_json, load_json


class ProfileTests(ProjectTest):
    def setUp(self):
        super().setUp()
        self.lab = profiles.resolve("lab", self.root)
        self.hero = profiles.resolve("hero-sandbox", self.root)
        atomic_json(self.root / self.lab["project"], {
            "EngineAssociation": "5.8", "Modules": [{"Name": "NovanodeLab"}],
        })
        self.env = patch.dict(os.environ, {"UE_ROOT": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def hero_project(self):
        atomic_json(self.root / self.hero["project"], {
            "EngineAssociation": "5.8", "Modules": [{"Name": "LyraGame"}, {"Name": "LyraEditor"}],
        })

    def engine(self, minor=8, patch_version=4):
        engine = self.root / "engine"
        atomic_json(engine / "Engine/Build/Build.version", {
            "MajorVersion": 5, "MinorVersion": minor, "PatchVersion": patch_version,
        })
        for name in ("Engine/Binaries/Linux/UnrealEditor", "Engine/Build/BatchFiles/Linux/Build.sh",
                     "Engine/Build/BatchFiles/RunUAT.sh"):
            path = engine / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture, never executed")
            path.chmod(0o700)
        os.environ["UE_ROOT"] = str(engine)
        return engine

    def journal(self, job="build-111111111111", **overrides):
        row = {
            "job_id": job, "operation": "build", "state": "completed", "exit_code": 0,
            "finished_at": "2026-11-03T12:00:00+00:00", "human_approval": "pending",
            "summary": {"fatal_count": 0, "error_severity_count": 0, "normal_exit_marker": True},
        }
        row.update(overrides)
        path = self.root / ".studio/evidence" / f"hero-sandbox-job-{job}.json"
        atomic_json(path, row)
        return path

    def build(self):
        self.hero_project()
        source = self.root / profiles.HERO_SOURCE / "Source/Owned.cpp"
        source.parent.mkdir(parents=True)
        source.write_text("// original owned fixture\n")
        stage = (self.root / self.hero["project"]).parent / "Plugins/NovanodeHeroes"
        staged_source = stage / "Source/Owned.cpp"
        staged_source.parent.mkdir(parents=True)
        shutil.copy(source, staged_source)
        module = stage / "Binaries/Linux/libUnrealEditor-NovanodeHeroes.so"
        module.parent.mkdir(parents=True)
        module.write_bytes(b"\x7fELFowned-fixture-not-executable")
        self.journal(source_sha256={"Source/Owned.cpp": hashlib.sha256(source.read_bytes()).hexdigest()},
                     native_module_sha256=hashlib.sha256(module.read_bytes()).hexdigest())
        return source, staged_source, module

    def tree(self):
        return {path.relative_to(self.root).as_posix():
                ("directory" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest())
                for path in self.root.rglob("*")}

    def change_config(self, old, new):
        path = self.root / "studio.toml"
        path.write_text(path.read_text().replace(old, new, 1))

    def test_default_is_still_studio_project_and_profiles_are_distinct(self):
        listing = profiles.list_profiles(self.root)
        self.assertEqual(listing["default_profile"], "lab")
        self.assertEqual(listing["default_project"], "projects/NovanodeLab/NovanodeLab.uproject")
        self.assertEqual(profiles.resolve(root=self.root)["id"], "lab")
        self.assertNotEqual(self.lab["project"], self.hero["project"])
        self.assertNotEqual(self.lab["map"], self.hero["map"])
        self.assertEqual(self.hero["experience"], "/NovanodeHeroes/Experiences/B_HeroSandbox_v2")

    def test_unknown_or_unmapped_default_never_silently_selects_a_project(self):
        with self.assertRaises(StudioError):
            profiles.resolve("invented", self.root)
        self.change_config('project = "projects/NovanodeLab/NovanodeLab.uproject"',
                           'project = "projects/Other/Other.uproject"')
        self.assertIsNone(profiles.list_profiles(self.root)["default_profile"])
        with self.assertRaises(StudioError):
            profiles.resolve(root=self.root)
        self.assertEqual(profiles.resolve("lab", self.root)["id"], "lab")
        with self.assertRaises(StudioError):
            profiles.require_lab_adapter(profiles.resolve("lab", self.root), self.root)

    def test_missing_profile_configuration_is_actionable(self):
        path = self.root / "studio.toml"
        text = path.read_text()
        path.write_text(text[:text.index("# Selection is explicit")] + text[text.index("[budgets]"):])
        with self.assertRaisesRegex(StudioError, "profiles.lab"):
            profiles.status(root=self.root)

    def test_hero_previews_use_the_guarded_wrapper_and_correct_project_map(self):
        for action, operation in (("run", "play-v2"), ("editor", "editor-v2")):
            with self.subTest(action=action), patch("subprocess.Popen") as process:
                result = profiles.preview_hero(action, self.root)
            process.assert_not_called()
            self.assertEqual(result["project"], str(self.root / self.hero["project"]))
            self.assertEqual(result["map"], self.hero["map"])
            self.assertEqual(result["experience"], self.hero["experience"])
            self.assertEqual(result["commands"][0][-1], operation)
            self.assertIn("manage.py", result["commands"][0][-2])
            self.assertFalse(result["execution_supported"])
            self.assertFalse((self.root / ".studio").exists())

    def test_modified_profile_cannot_misrepresent_the_fixed_hero_launcher(self):
        self.change_config(self.hero["map"], "/NovanodeHeroes/Maps/Other")
        with self.assertRaisesRegex(StudioError, "fixed manage.py"):
            profiles.preview_hero("run", self.root)
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["coverage"], "profile_identity_mismatch")
        self.assertIsNone(result["history"]["last_successful_build"])

    def test_missing_installation_and_helpers_work_without_creating_studio(self):
        before = self.tree()
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["engine"]["status"], "not_configured")
        self.assertIn("UE_ROOT", result["engine"]["action"])
        self.assertEqual(result["project"]["status"], "missing_or_invalid")
        self.assertFalse(result["launcher"]["local_entry_helper_present"])
        self.assertEqual(result["gates"]["native_build"]["status"], "unknown")
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / ".studio").exists())

    def test_metadata_compatibility_is_not_native_or_human_approval(self):
        self.hero_project()
        self.engine()
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["project"]["status"], "metadata_compatible")
        self.assertEqual(result["engine"]["status"], "metadata_compatible")
        self.assertEqual(result["engine"]["observed_version"], "5.8.4")
        self.assertFalse(result["engine"]["native_verified"])
        self.assertEqual(result["status"], "diagnostic_only")
        self.assertEqual(result["execution_readiness"], "not_assessed")
        self.assertEqual(result["human_approval"], "pending")
        for gate in ("multiplayer", "performance", "package"):
            self.assertEqual(result["gates"][gate]["status"], "not_verified")

    def test_engine_patch_and_family_mismatches_are_actionable(self):
        self.engine(patch_version=3)
        self.assertEqual(profiles.status("hero-sandbox", self.root)["engine"]["status"], "incompatible")
        self.assertEqual(profiles.status("lab", self.root)["engine"]["status"], "metadata_compatible")
        self.engine(minor=7)
        result = profiles.status("lab", self.root)
        self.assertEqual(result["engine"]["status"], "incompatible")
        self.assertIn("Review", result["engine"]["action"])

    def test_incomplete_or_malformed_engine_metadata_never_looks_ready(self):
        engine = self.engine()
        (engine / "Engine/Binaries/Linux/UnrealEditor").chmod(0o600)
        self.assertEqual(profiles.status("lab", self.root)["engine"]["status"], "incomplete_installation")
        atomic_json(engine / "Engine/Build/Build.version", {"MajorVersion": 5, "MinorVersion": 8})
        self.assertEqual(profiles.status("lab", self.root)["engine"]["status"], "missing_or_invalid")

    def test_wrong_module_or_project_association_is_not_compatible(self):
        self.hero_project()
        path = self.root / self.hero["project"]
        for data in ({"EngineAssociation": "5.7", "Modules": [{"Name": "LyraGame"}]},
                     {"EngineAssociation": "5.8", "Modules": [{"Name": "NovanodeLab"}]},
                     {"EngineAssociation": "5.8", "Modules": None}):
            with self.subTest(data=data):
                atomic_json(path, data)
                self.assertEqual(profiles.status("hero-sandbox", self.root)["project"]["status"], "incompatible")

    def test_resource_review_pin_and_ai_holds_are_distinct_from_import(self):
        atomic_json(self.root / "resources/hero-sandbox/catalog.json", {"schema_version": 1, "items": [
            {"id": "reviewed-mesh", "review": "reviewed_item", "sha256": "a" * 64, "ai_input": "restricted",
             "native_status": "machine_imported_DO_NOT_TRUST_THIS_LABEL"},
            {"id": "candidate", "review": "candidate", "sha256": None, "ai_input": "unknown"},
        ]})
        result = profiles.status("hero-sandbox", self.root)["resources"]
        self.assertFalse(result["items"][0]["pin_hold"])
        self.assertFalse(result["items"][0]["review_hold"])
        self.assertTrue(result["items"][0]["ai_input_hold"])
        self.assertTrue(result["items"][1]["pin_hold"])
        self.assertFalse(result["native_import_verified"])
        self.assertNotIn("DO_NOT_TRUST", json.dumps(result))

    def test_matching_build_is_still_historical_without_engine_content_binding(self):
        self.build()
        self.engine()
        result = profiles.status("hero-sandbox", self.root)
        build = result["history"]["last_successful_build"]
        self.assertEqual(build["status"], "historical_unbound")
        for field in ("source_matches", "staged_source_matches", "binary_matches"):
            self.assertTrue(build[field])
        self.assertFalse(build["current_verified"])
        self.assertEqual(build["engine_binding"], "unrecorded")
        self.assertEqual(result["gates"]["native_build"]["status"], "historical_unbound")

    def test_changed_sources_staging_or_binary_make_build_stale(self):
        paths = self.build()
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                result = profiles.status("hero-sandbox", self.root)
                self.assertEqual(result["history"]["last_successful_build"]["status"], "stale")
                path.write_bytes(original)

    def test_pending_unknown_and_unrecognized_jobs_are_never_reconciled_implicitly(self):
        for index, state in enumerate(("reserved", "running_unknown", "unknown", "future_state", {"bad": True})):
            self.journal(job=f"build-pending-{index}", state=state)
        before = self.tree()
        with patch("os.killpg") as kill:
            result = profiles.status("hero-sandbox", self.root)
        kill.assert_not_called()
        pending = result["history"]["unresolved_jobs"]
        self.assertEqual(len(pending), 5)
        self.assertTrue(all(row["reconciliation_required"] for row in pending))
        self.assertEqual(self.tree(), before)

    def test_invalid_undated_or_contradictory_journals_cannot_create_a_pass(self):
        for job, changes in (("build-no-date", {"finished_at": None}),
                             ("build-contradictory", {"exit_code": 1}),
                             ("build-no-hashes", {}),
                             ("build-errors", {"summary": {"fatal_count": 1, "error_severity_count": 0}})):
            self.journal(job=job, **changes)
        path = self.journal(job="build-malformed")
        path.write_text("{not-json")
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["coverage"], "invalid_metadata")
        self.assertEqual(len(result["history"]["invalid_journals"]), 3)
        self.assertEqual(len(result["history"]["unqualified_completions"]), 2)
        self.assertIsNone(result["history"]["last_successful_build"])

    def test_journal_scan_limits_are_explicit_and_do_not_promote_partial_results(self):
        self.build()
        self.journal(job="build-pending", state="running_unknown")
        with patch.object(profiles, "MAX_JOURNALS", 1):
            result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["coverage"], "limit_exceeded")
        self.assertFalse(result["history"]["unresolved_job_scan_complete"])
        self.assertIsNone(result["history"]["last_successful_build"])

    def test_failed_attempts_remain_visible_beside_historical_success(self):
        self.build()
        self.journal(job="build-later-failed", state="blocked", exit_code=1)
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["last_successful_build"]["status"], "historical_unbound")
        self.assertEqual(result["history"]["blocked_jobs"], [{"job_id": "build-later-failed", "exit_code": 1}])
        self.assertTrue(result["history"]["unresolved_job_scan_complete"])

    def test_unrecognized_source_files_or_binary_symlinks_leave_identity_unavailable(self):
        source, _, module = self.build()
        extra = source.parent / ".env.fixture"
        extra.write_text("FAKE_FIXTURE_NOT_A_CREDENTIAL")
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["last_successful_build"]["status"], "identity_unavailable")
        extra.unlink()
        target = self.root / "owned-module-fixture"
        target.write_bytes(module.read_bytes())
        module.unlink()
        module.symlink_to(target)
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["history"]["last_successful_build"]["status"], "identity_unavailable")

    def test_fake_success_fields_cannot_override_gameplay_or_human_gates(self):
        self.journal(job="smoke-v2-fake", operation="smoke-v2", smoke={"passed": False}, human_approval="approved")
        self.journal(job="smoke-v2-historical", operation="smoke-v2", smoke={"passed": True}, human_approval="approved")
        result = profiles.status("hero-sandbox", self.root)
        self.assertEqual(result["gates"]["standalone_gameplay"]["status"], "historical_unbound")
        self.assertEqual(result["gates"]["standalone_gameplay"]["job_id"], "smoke-v2-historical")
        self.assertIn({"job_id": "smoke-v2-fake", "reason": "completion_checks_not_met"},
                      result["history"]["unqualified_completions"])
        self.assertEqual(result["human_approval"], "pending")
        self.assertEqual(result["gates"]["visual_controls"]["status"], "human_review_pending")

    def test_symlink_metadata_and_oversized_json_are_not_followed_or_loaded(self):
        target = self.root / "owned-fixture.json"
        atomic_json(target, {"schema_version": 1, "items": []})
        catalog = self.root / "resources/hero-sandbox/catalog.json"
        catalog.parent.mkdir(parents=True)
        catalog.symlink_to(target)
        self.assertEqual(profiles.status("hero-sandbox", self.root)["resources"]["status"], "missing_or_invalid")
        catalog.unlink()
        catalog.write_text("x" * 65)
        with patch.object(profiles, "MAX_METADATA_BYTES", 64):
            self.assertEqual(profiles.status("hero-sandbox", self.root)["resources"]["status"], "missing_or_invalid")

    def test_project_escape_is_rejected_before_metadata_access(self):
        self.change_config(self.hero["project"], "../escape/Lyra.uproject")
        with self.assertRaises(StudioError):
            profiles.status("hero-sandbox", self.root)

    def test_status_is_read_only_and_never_imports_helpers_or_returns_log_payloads(self):
        self.build()
        helper = self.root / profiles.HERO_HELPER
        helper.parent.mkdir(parents=True)
        helper.write_text("raise AssertionError('must not import this helper')")
        job = self.root / ".studio/evidence/hero-sandbox-job-build-111111111111.json"
        row = load_json(job)
        row.update(command=["DO_NOT_EMIT_COMMAND_PAYLOAD"], owned_diagnostics=["DO_NOT_EMIT_LOG_PAYLOAD"],
                   raw_logs_local_only=["DO_NOT_EMIT_RAW_LOG_PATH"])
        atomic_json(job, row)
        before = self.tree()
        with (patch("subprocess.Popen") as process, patch("urllib.request.urlopen") as network,
              patch.object(Path, "mkdir", side_effect=AssertionError("unexpected write")),
              patch.object(Path, "write_text", side_effect=AssertionError("unexpected write"))):
            result = profiles.status("hero-sandbox", self.root)
        process.assert_not_called()
        network.assert_not_called()
        self.assertEqual(before, self.tree())
        self.assertNotIn("DO_NOT_EMIT", json.dumps(result))
        self.assertTrue(result["launcher"]["local_entry_helper_present"])


class ProfileCliTests(ProjectTest):
    def test_default_run_and_unreal_validation_keep_the_legacy_routes(self):
        with patch("pipeline.cli.unreal.run", return_value={"status": "dry_run"}) as run:
            cli.dispatch(cli.parser().parse_args(["run"]))
        run.assert_called_once_with("run", False)
        with patch("pipeline.cli.unreal.validate_source", return_value={"status": "source_validated"}) as validate:
            cli.dispatch(cli.parser().parse_args(["unreal", "validate"]))
        validate.assert_called_once_with()

    def test_project_doctors_use_only_readonly_status_not_legacy_tool_probes(self):
        for argv in (["doctor", "--profile", "hero-sandbox"], ["unreal", "doctor", "--profile", "hero-sandbox"],
                     ["projects", "status", "--profile", "hero-sandbox"]):
            with (self.subTest(argv=argv), patch("pipeline.cli.profiles.status", return_value={"read_only": True}) as status,
                  patch("pipeline.cli.engines.checked_binary") as binary, patch("pipeline.cli.unreal.doctor") as doctor):
                self.assertEqual(cli.dispatch(cli.parser().parse_args(argv)), {"read_only": True})
            status.assert_called_once_with("hero-sandbox")
            binary.assert_not_called()
            doctor.assert_not_called()

    def test_hero_execution_or_unsupported_actions_never_reach_the_lab_adapter(self):
        cases = [["run", "--profile", "hero-sandbox", "--execute"],
                 ["unreal", "editor", "--profile", "hero-sandbox", "--execute"],
                 ["unreal", "validate", "--profile", "hero-sandbox"],
                 ["unreal", "package", "--profile", "hero-sandbox"]]
        for argv in cases:
            with (self.subTest(argv=argv), patch("pipeline.cli.unreal.run") as run,
                  patch("pipeline.cli.unreal.validate_source") as validate):
                with self.assertRaises(StudioError):
                    cli.dispatch(cli.parser().parse_args(argv))
            run.assert_not_called()
            validate.assert_not_called()

    def test_explicit_lab_preview_uses_validated_legacy_adapter(self):
        with (patch("pipeline.cli.unreal.run", return_value={"status": "dry_run"}) as run,
              patch("pipeline.cli.profiles.require_lab_adapter") as require):
            result = cli.dispatch(cli.parser().parse_args(["unreal", "run", "--profile", "lab"]))
        self.assertEqual(result["profile"], "lab")
        self.assertEqual(require.call_args.args[0]["id"], "lab")
        run.assert_called_once_with("run", False)

    def test_model_profiles_are_not_project_profiles_and_unknown_profiles_fail(self):
        args = cli.parser().parse_args(["models", "config", "--profile", "free"])
        self.assertEqual(args.profile, "free")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parser().parse_args(["run", "--profile", "free"])

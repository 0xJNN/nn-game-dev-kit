"""Training v3 source/identity regressions; never starts Unreal or signals a game."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects/hero-sandbox"
SCRATCH = ROOT / ".studio/runs/hero-training-v3-implementation-2026-11-05-fixtures"
PUBLIC = PROJECT / "NovanodeHeroes/Source/NovanodeHeroes/Public"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


training = module("owned_training_under_test", PROJECT / "hero_training.py")
manager = module("owned_training_base_manager_under_test", PROJECT / "manage.py")
recipe = module("owned_training_recipe_under_test", PROJECT / "prepare_training.py")
from pipeline.common import StudioError, atomic_json


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)

    def test_real_cpp_flow_header(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler, "A C++ compiler is required; do not silently skip the live flow rules")
        source = r'''
#include "HeroTrainingFlow.h"
#include <cassert>
using namespace NovanodeHeroes;
int main() {
    for (TrainingHero hero : {TrainingHero::Melee, TrainingHero::Mage}) {
        TrainingFlow f;
        assert(!f.Start(true)); assert(!f.Choose(hero)); assert(!f.Pause());
        assert(f.OpenTraining()); assert(!f.Start(true));
        assert(!f.Choose(static_cast<TrainingHero>(99)));
        assert(f.Choose(hero)); assert(f.Hero == hero);
        assert(!f.Start(false)); assert(f.Start(true)); assert(!f.Start(true));
        for (int bots : {0, 1, 2, 4, 5}) assert(!f.MatchReady(true, bots));
        assert(!f.MatchReady(false, 3)); assert(f.MatchReady(true, 3));
        assert(!f.OpenTraining()); assert(f.Pause()); assert(!f.Pause());
        assert(f.Resume()); assert(!f.Resume()); assert(f.Pause());
        assert(f.Return()); assert(!f.Pause()); assert(!f.Return());
        assert(f.ArriveAtLobby()); assert(!f.HasSelection);
        assert(f.OpenTraining()); assert(f.Choose(hero));
        assert(f.BackFromSelection()); assert(!f.HasSelection);
    }
    TrainingFlow loading;
    assert(loading.OpenTraining()); assert(loading.Choose(TrainingHero::Mage));
    assert(loading.Start(true)); assert(loading.Return()); assert(loading.ArriveAtLobby());
}
'''
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            path = Path(temp)
            (path / "flow.cpp").write_text("#include <initializer_list>\n" + source)
            built = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(PUBLIC),
                                    str(path / "flow.cpp"), "-o", str(path / "flow")], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(subprocess.run([str(path / "flow")], capture_output=True).returncode, 0)

    def test_every_operation_defaults_to_no_engine_preview(self):
        for operation in ("build", "prepare-v3", "validate-v3", "play-v3"):
            with patch.object(training, "load_manager", side_effect=AssertionError("native helper imported")):
                result = training.run(operation)
            self.assertEqual(result["state"], "preview")
            self.assertFalse(result["engine_started"])

    def test_cli_play_is_preview_without_execute(self):
        result = subprocess.run([sys.executable, str(PROJECT / "hero_training.py"), "play-v3"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["engine_started"])

    def test_unknown_or_repeated_native_work_is_not_resubmitted(self):
        for state in training.PENDING:
            with self.assertRaises(StudioError): training.eligible([(None, {"state": state})], "build")
        for state in ("completed", "blocked"):
            with self.assertRaises(StudioError):
                training.eligible([(None, {"state": state, "task": training.TASK, "operation": "build"})], "build")

    def test_three_operation_cap(self):
        rows = [(None, {"state": "completed", "task": training.TASK, "operation": op}) for op in ("build", "prepare-v3", "validate-v3")]
        with self.assertRaises(StudioError): training.eligible(rows, "another-operation")

    def test_only_new_training_assets_may_be_added(self):
        recipe.require_preserved({"Maps/v2.umap": "a"}, {"Maps/v2.umap": "a", "TrainingV3/new.uasset": "b"})
        for current in ({"Maps/v2.umap": "changed"}, {}, {"Maps/v2.umap": "a", "Unrelated/new.uasset": "b"}):
            with self.assertRaises(RuntimeError): recipe.require_preserved({"Maps/v2.umap": "a"}, current)

    def promotion_fixture(self, folder):
        content = folder / "Content"
        (content / "Maps").mkdir(parents=True)
        (content / "TrainingV3").mkdir()
        (content / "Maps/L_HeroSandbox_v1.umap").write_bytes(b"old v1")
        (content / "Maps/L_HeroSandbox_v2.umap").write_bytes(b"old v2")
        (content / "TrainingV3/new.uasset").write_bytes(b"new v3")
        current = training.inventory(content)
        base = {name: value for name, value in current.items() if not name.startswith("TrainingV3/")}
        summary = {"fatal_count": 0, "error_severity_count": 0, "normal_exit_marker": True}
        parent = {"job_id": "old", "operation": "validate-v2", "state": "completed", "exit_code": 0,
                  "summary": summary.copy(), "preparation": {"state": "prepared", "generated_sha256": base}}
        promotion = {"job_id": "new", "operation": "validate-v3", "state": "completed", "exit_code": 0,
                     "summary": summary.copy(), "preparation": {"state": "prepared", "generated_sha256": current,
                         "pre_existing_sha256": base, "pre_existing_content_unchanged": True, "baseline_job_id": "old"}}
        return parent, promotion

    def test_additive_promotion_keeps_both_old_maps_eligible(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            folder = Path(temp)
            parent, promotion = self.promotion_fixture(folder)
            with patch.object(manager, "STAGE", folder):
                for name in ("Maps/L_HeroSandbox_v1.umap", "Maps/L_HeroSandbox_v2.umap"):
                    self.assertEqual(manager.verify_prepared_assets([parent, promotion], name), "new")

    def test_promotion_requires_parent_identity_and_zero_error_exit(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            folder = Path(temp)
            parent, promotion = self.promotion_fixture(folder)
            variants = []
            for key, value in (("exit_code", 1), ("exit_code", False), ("state", "blocked")):
                row = copy.deepcopy(promotion); row[key] = value; variants.append((parent, row))
            for key, value in (("error_severity_count", 1), ("fatal_count", 1), ("normal_exit_marker", False)):
                row = copy.deepcopy(promotion); row["summary"][key] = value; variants.append((parent, row))
            row = copy.deepcopy(promotion); row["preparation"]["baseline_job_id"] = "absent"; variants.append((parent, row))
            for key, value in (("exit_code", 1), ("exit_code", False)):
                old = copy.deepcopy(parent); old[key] = value; variants.append((old, promotion))
            with patch.object(manager, "STAGE", folder):
                for old, new in variants:
                    with self.subTest(old=old["exit_code"], new=new["exit_code"]), self.assertRaises(StudioError):
                        manager.verify_prepared_assets([old, new])

    def test_promotion_refuses_changed_old_asset_or_unrelated_addition(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            folder = Path(temp)
            parent, promotion = self.promotion_fixture(folder)
            (folder / "Content/Maps/L_HeroSandbox_v2.umap").write_bytes(b"changed")
            promotion["preparation"]["generated_sha256"] = training.inventory(folder / "Content")
            with patch.object(manager, "STAGE", folder), self.assertRaises(StudioError): manager.verify_prepared_assets([parent, promotion])
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            folder = Path(temp)
            parent, promotion = self.promotion_fixture(folder)
            (folder / "Content/unrelated.uasset").write_bytes(b"unexpected")
            promotion["preparation"]["generated_sha256"] = training.inventory(folder / "Content")
            with patch.object(manager, "STAGE", folder), self.assertRaises(StudioError): manager.verify_prepared_assets([parent, promotion])

    def test_runtime_source_is_opt_in_and_uses_native_combat(self):
        private = PROJECT / "NovanodeHeroes/Source/NovanodeHeroes/Private"
        ui = (private / "HeroTrainingUI.cpp").read_text()
        combat = (private / "HeroTrainingCombat.cpp").read_text()
        self.assertIn('FParse::Param(FCommandLine::Get(), TEXT("HeroTrainingV3"))', ui)
        self.assertIn("NM_Standalone", ui)
        self.assertIn("ULyraDamageExecution::StaticClass()", combat)
        self.assertIn("Manager->EquipItem", combat)
        self.assertIn("Manager->UnequipItem", combat)
        self.assertIn("AbilityInputTagPressed", combat)
        self.assertIn("Montage_Play", combat)
        self.assertNotIn("AHeroTargetDummy", combat)
        self.assertNotIn("SetNumericAttributeBase", combat)
        self.assertIn("RemoveMappingContext", combat)
        self.assertIn("ClearTimer(CastTimer)", combat)

    def test_mage_animation_is_not_misrepresented_as_a_dedicated_cast_asset(self):
        self.assertEqual(recipe.CLIPS["Mage_Cast"], "UAL2_StandardOverhandThrow")
        self.assertIn("provisional_overhand_throw", (PROJECT / "prepare_training.py").read_text())


class StopV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)

    def test_stop_never_selects_v2_or_a_build(self):
        for job in ("play-v2-0123456789ab", "build-0123456789ab", "play-v3-../../x", "play-v3-XYZ"):
            with self.assertRaises(StudioError): training.stop_v3(job, dry_run=True)

    def test_no_pending_v3_is_a_read_only_noop(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            root = Path(temp)
            evidence = root / ".studio/evidence"
            evidence.mkdir(parents=True)
            with patch.object(training, "ROOT", root), patch.object(training, "EVIDENCE", evidence):
                self.assertEqual(training.stop_v3(), {"state": "not_running", "signal_sent": False})
            self.assertEqual(list(evidence.iterdir()), [])

    def test_stop_timeout_validation(self):
        for value in (0, 61, True, -1):
            with self.assertRaises(StudioError): training.stop_v3(timeout=value)

    def fixture(self, root):
        evidence = root / ".studio/evidence"
        evidence.mkdir(parents=True)
        engine = root / "engine"
        work = root / "project"
        command = [str(engine / "Engine/Binaries/Linux/UnrealEditor"), str(work / "Lyra.uproject"), training.FRONTEND,
                   "-game", "-DisablePython", "-HeroTrainingV3"]
        import os
        boot = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
        started = datetime.fromtimestamp(boot + 200 / os.sysconf('SC_CLK_TCK'), timezone.utc).isoformat()
        row = {"job_id": "play-v3-0123456789ab", "operation": "play-v3", "state": "running_unknown", "pid": 4242,
               "process_start_ticks": "200", "command": command, "started_at": started}
        path = evidence / ("hero-sandbox-job-" + row["job_id"] + ".json")
        atomic_json(path, row)
        current = {"argv": command, "lifecycle": "S", "uid": os.getuid(), "parent_pid": 3131,
                   "caught": 1 << (signal.SIGINT - 1), "ignored": 0}
        parent = {"uid": os.getuid(), "lifecycle": "S", "ticks": "100",
                  "argv": [sys.executable, str(root / "projects/hero-sandbox/hero_training.py"), "play-v3", "--execute"]}
        return evidence, path, row, current, parent, SimpleNamespace(ENGINE=engine, WORK=work)

    def test_v3_stop_pins_game_and_does_not_edit_native_journal(self):
        from pipeline import hero_stop as transport
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            root = Path(temp)
            evidence, path, row, current, parent, fake_manager = self.fixture(root)
            before = path.read_bytes()
            process = SimpleNamespace(exited=lambda: False, request_exit=lambda: None, close=lambda: None)
            with patch.object(training, "ROOT", root), patch.object(training, "EVIDENCE", evidence), \
                 patch.object(training, "load_manager", return_value=fake_manager), \
                 patch.object(transport, "_proc", side_effect=[current, parent, current, parent]), \
                 patch.object(transport, "PidfdProcess", return_value=process) as bind, \
                 patch.object(transport, "_wait", return_value={"state": "stopped"}):
                result = training.stop_v3(row["job_id"])
            self.assertEqual(result["state"], "stopped")
            bind.assert_called_once_with(4242)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list(evidence.glob("hero-training-v3-stop-*.json"))), 1)

    def test_stop_refuses_foreign_supervisor_or_missing_handler(self):
        from pipeline import hero_stop as transport
        for bad_parent, no_handler in ((True, False), (False, True)):
            with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
                root = Path(temp)
                evidence, _, row, current, parent, fake_manager = self.fixture(root)
                if bad_parent: parent["argv"] = ["python", "manage.py", "play-v2"]
                if no_handler: current["caught"] = 0
                signals = []
                process = SimpleNamespace(exited=lambda: False, request_exit=lambda: signals.append(True), close=lambda: None)
                with patch.object(training, "ROOT", root), patch.object(training, "EVIDENCE", evidence), \
                     patch.object(training, "load_manager", return_value=fake_manager), \
                     patch.object(transport, "_proc", side_effect=[current, parent]), \
                     patch.object(transport, "PidfdProcess", return_value=process), self.assertRaises(StudioError):
                    training.stop_v3(row["job_id"])
                self.assertEqual(signals, [])
                self.assertEqual(list(evidence.glob("hero-training-v3-stop-*.json")), [])

    def test_unresolved_stop_blocks_another_signal(self):
        from pipeline import hero_stop as transport
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            root = Path(temp)
            evidence, _, row, _, _, _ = self.fixture(root)
            atomic_json(evidence / "hero-training-v3-stop-old.json", {"job_id": row["job_id"], "state": "outcome_unknown"})
            with patch.object(training, "ROOT", root), patch.object(training, "EVIDENCE", evidence), \
                 patch.object(transport, "PidfdProcess", side_effect=AssertionError("must not bind/signal")), self.assertRaises(StudioError):
                training.stop_v3(row["job_id"])


if __name__ == "__main__":
    unittest.main()

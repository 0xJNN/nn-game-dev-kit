"""Native lobby guard/transition regressions. No engine launch, network or signals."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects/hero-sandbox"
PLUGIN = PROJECT / "NovanodeTraining"
PUBLIC = PLUGIN / "Source/NovanodeTraining/Public"
PRIVATE = PLUGIN / "Source/NovanodeTraining/Private"
spec = importlib.util.spec_from_file_location("native_training_under_test", PROJECT / "native_training.py")
training = importlib.util.module_from_spec(spec)
spec.loader.exec_module(training)


class NativeTrainingTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".studio/runs/native-training-fixtures"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_actual_cpp_transition_policy_and_second_match(self):
        source = self.folder / "flow.cpp"
        source.write_text(r'''
#include "TrainingFlow.h"
#include <cassert>
int main() {
    using namespace NovanodeTraining;
    Flow f;
    assert(!f.BeginHosting() && !f.Choose(Hero::Melee));
    for (unsigned n = 1; n <= 2; ++n) {
        assert(f.ArriveAtLobby());
        assert(!f.ArriveAtLobby());
        assert(f.OpenSelection() && !f.OpenSelection());
        assert(!f.BeginHosting() && !f.Choose(Hero::None));
        assert(f.Choose(n == 1 ? Hero::Melee : Hero::Mage));
        assert(f.BeginHosting() && !f.BeginHosting());
        assert(f.MatchGeneration == n);
        assert(!f.MatchReady(false, 3) && !f.MatchReady(true, 2));
        assert(!f.MatchReady(true, 4));
        assert(f.MatchReady(true, 3) && !f.MatchReady(true, 3));
        assert(f.Return() && !f.Return());
    }
    assert(f.ArriveAtLobby() && f.Selected == Hero::None);
    assert(f.OpenSelection() && f.Choose(Hero::Mage));
    assert(f.BeginHosting()); f.HostFailed();
    assert(f.State == Screen::Selection && f.Back());
    assert(f.Selected == Hero::None && !f.Return());
}
''')
        binary = self.folder / "flow"
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(PUBLIC), str(source), "-o", str(binary)],
                       check=True, capture_output=True, timeout=20)
        subprocess.run([str(binary)], check=True, timeout=5)

    def test_component_adapter_checks_native_struct_and_field_types(self):
        source = (PRIVATE / "TrainingReflectionAdapter.cpp").read_text()
        for token in ("FGameFeatureComponentEntry::StaticStruct()", "sizeof(FGameFeatureComponentEntry)",
                      "FSoftClassProperty", "FBoolProperty", "FByteProperty", 'TEXT("ComponentList")'):
            self.assertIn(token, source)
        recipe = (PROJECT / "prepare_native_training.py").read_text()
        self.assertNotIn("unreal.GameFeatureComponentEntry", recipe)
        self.assertIn('unreal.load_module("NovanodeTraining")', recipe)

    def test_reflected_host_bridge_is_narrow_and_schema_checked(self):
        source = (PRIVATE / "TrainingReflectionAdapter.cpp").read_text()
        for token in ("Function->NumParms != 2", "FUNC_Const", "CPF_OutParm | CPF_ReferenceParm",
                      "UCommonSession_HostSessionRequest::StaticClass()", "FStructOnScope", "HasHostingSignature(Definition)"):
            self.assertIn(token, source)
        self.assertIn("ECommonSessionOnlineMode::Offline", source)
        self.assertIn("Request->bUseLobbies = false", source)

    def test_no_polling_or_direct_travel_in_new_feature(self):
        source = "\n".join(p.read_text() for p in (PLUGIN / "Source").rglob("*") if p.suffix in (".cpp", ".h"))
        for token in ("FTickableGameObject", "NativeTick(", "::Tick(", "OpenLevel(", "ServerTravel(", "ClientTravel(", "AddToViewport("):
            self.assertNotIn(token, source)
        for token in ("HostSession(Player, Request)", "CleanUpSessions()", "ReturnToMainMenu()",
                      "CallOrRegister_OnExperienceLoaded_LowPriority", "RegisterAndCallForClassInitState",
                      "UnregisterClassInitStateDelegate"):
            self.assertIn(token, source)

    def test_action_sets_are_referenced_and_not_flattened(self):
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn('Sets.Add(Set)', source)
        self.assertNotIn("Reference.Num() != 8", source)
        self.assertNotIn("BasicShooterAccolades", source)
        self.assertIn('TEXT("LAS_ShooterGame_StandardComponents")', source)

    def test_menu_blocks_gas_and_uses_commonui_menu_input(self):
        source = (PRIVATE / "TrainingLobby.cpp").read_text()
        for token in ("ECommonInputMode::Menu", "EMouseCaptureMode::NoCapture", "ClearAbilityInput()",
                      "CancelInputActivatedAbilities(false)", "RemoveLooseGameplayTag(Tag)", "AddLooseGameplayTag(Tag)"):
            self.assertIn(token, source)

    def test_plugin_has_explicit_dependencies_and_registered_discovery(self):
        plugin = json.loads((PLUGIN / "NovanodeTraining.uplugin").read_text())
        self.assertTrue(plugin["ExplicitlyLoaded"])
        self.assertEqual(plugin["BuiltInInitialFeatureState"], "Registered")
        dependencies = {p["Name"] for p in plugin["Plugins"]}
        self.assertTrue({"GameFeatures", "ModularGameplay", "CommonUser", "CommonGame", "ShooterCore"} <= dependencies)
        self.assertNotIn("NovanodeHeroes", dependencies)

    def test_commands_never_launch_interactive_windows(self):
        for operation in ("schema", "prepare", "verify"):
            args = training.command(operation, self.folder)
            self.assertIn("-unattended", args)
            self.assertIn("-NullRHI", args)
            self.assertIn("UnrealEditor-Cmd", args[0])
            self.assertFalse(any(a.startswith("-HeroTrainingV3") for a in args))
        build = training.command("build", self.folder)
        self.assertIn("-Module=NovanodeTraining", build)

    def test_execution_requires_bounded_task(self):
        with patch.dict(training.os.environ, {"NOVANODE_TASK_ID": "other-task"}):
            with self.assertRaisesRegex(training.StudioError, "bounded task"):
                training.run("build")

    def test_manifest_rejects_symlinks_and_ignores_generated_not_source(self):
        (self.folder / "owned.cpp").write_text("owned")
        (self.folder / "Binaries").mkdir()
        (self.folder / "Binaries/generated").write_text("generated")
        self.assertEqual(set(training.manifest(self.folder)), {"owned.cpp"})
        (self.folder / "foreign.h").symlink_to(self.folder / "owned.cpp")
        with self.assertRaisesRegex(training.StudioError, "Symlink"):
            training.manifest(self.folder)

    def test_unfinished_native_job_blocks_even_without_pid(self):
        path = self.folder / "hero-other-job-fixture.json"
        for state in ("reserved", "running_unknown", "outcome_unknown"):
            path.write_text(json.dumps({"state": state, "pid": 999999999}))
            with patch.object(training, "EVIDENCE", self.folder):
                with self.assertRaisesRegex(training.StudioError, "Unfinished native"):
                    training.ensure_no_pending()

    def test_only_completed_exact_source_and_module_satisfy_prerequisite(self):
        source = {"Source/owned.cpp": "a" * 64}
        module_hash = "b" * 64
        base = {"operation": "build", "state": "completed", "exit_code": 0,
                "source_sha256": source, "module_sha256": module_hash}
        with patch.object(training, "digest", return_value=module_hash):
            for change in ({"exit_code": None}, {"exit_code": False}, {"state": "blocked"},
                           {"module_sha256": "c" * 64}, {"source_sha256": {}}):
                with patch.object(training, "journals", return_value=[{**base, **change}]):
                    with self.assertRaisesRegex(training.StudioError, "source-exact"):
                        training.require_phase("schema", source, {})
            with patch.object(training, "journals", return_value=[base]):
                training.require_phase("schema", source, {})

    def test_unknown_installed_source_is_not_overwritten_or_removed(self):
        source, stage = self.folder / "source", self.folder / "stage"
        source.mkdir(); stage.mkdir()
        (source / "owned.h").write_text("owned")
        (stage / "owned.h").write_text("owned")
        (stage / "parallel.cpp").write_text("preserve")
        receipt = {"sha256": training.manifest(source)}
        with patch.object(training, "SOURCE", source), patch.object(training, "STAGE", stage):
            with self.assertRaisesRegex(training.StudioError, "Unrecognized"):
                training.verify_install(receipt)
        self.assertEqual((stage / "parallel.cpp").read_text(), "preserve")

    def test_project_inventory_uses_exact_authored_file_keys(self):
        authored = {"NovanodeTraining.uplugin": "a" * 64, "Source/owned.cpp": "b" * 64}
        expected = {"Plugins/GameFeatures/NovanodeTraining/" + k: v for k, v in authored.items()}
        self.assertEqual(training.plugin_inventory(authored), expected)
        source = (PROJECT / "native_training.py").read_text()
        self.assertNotIn("source_inventory(STAGE)", source)
        self.assertIn("helper.source_inventory(WORK) != expected", source)

    def test_partial_adoption_requires_both_exact_checkpoint_and_authored_bytes(self):
        authored = {"Source/owned.cpp": "a" * 64}
        checkpoint = {"partial_installed_sha256": dict(authored)}
        training.verify_partial_adoption(authored, dict(authored), checkpoint)
        for installed in ({}, {**authored, "Content/partial.uasset": "b" * 64}, {"Source/owned.cpp": "c" * 64}):
            with self.assertRaisesRegex(training.StudioError, "Partial installation differs"):
                training.verify_partial_adoption(authored, installed, checkpoint)

    def test_changed_authored_source_cannot_adopt_checkpointed_copy(self):
        with self.assertRaisesRegex(training.StudioError, "Partial installation differs"):
            training.verify_partial_adoption({"owned.cpp": "new"}, {"owned.cpp": "old"},
                                            {"partial_installed_sha256": {"owned.cpp": "old"}})

    def test_compile_fix_uses_public_lyra_override_and_complete_asset_types(self):
        source = (PRIVATE / "TrainingMatchComponent.cpp").read_text()
        self.assertIn('"GameModes/LyraGameMode.h"', source)
        self.assertIn("ALyraGameMode* Mode", source)
        self.assertIn("GetAuthGameMode<ALyraGameMode>()", source)
        self.assertIn('"Engine/AssetManagerTypes.h"', (PRIVATE / "TrainingAssets.cpp").read_text())

    def test_compile_correction_scope_is_exact_not_a_blanket_sync(self):
        first = "Source/NovanodeTraining/Private/TrainingMatchComponent.cpp"
        second = "Source/NovanodeTraining/Private/TrainingAssets.cpp"
        old = {first: "old", second: "old", "unrelated.h": "keep"}
        new = {**old, first: "new", second: "new"}
        self.assertEqual(training.compile_correction_updates(old, new), {first, second})
        for candidate in ({**new, "unrelated.h": "changed"}, {**new, "new.h": "new"}, {**old, first: "new"}):
            with self.assertRaisesRegex(training.StudioError, "exactly the two"):
                training.compile_correction_updates(old, candidate)

    def test_asset_type_config_uses_public_mutators_not_private_members(self):
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn("Info.SetAssetBaseClass(TSoftClassPtr<UObject>(Base))", source)
        self.assertIn("Info.GetDirectories().Add(Path)", source)
        self.assertNotIn("Info.AssetBaseClass =", source)
        self.assertNotIn("Info.Directories.Add", source)

    def test_asset_type_sync_only_accepts_the_one_measured_file(self):
        name = "Source/NovanodeTraining/Private/TrainingAssets.cpp"
        old = {name: "old", "keep.h": "keep"}
        new = {**old, name: "new"}
        self.assertEqual(training.asset_types_correction_updates(old, new), {name})
        for candidate in (old, {**new, "keep.h": "changed"}, {name: "new"}):
            with self.assertRaisesRegex(training.StudioError, "exactly the measured"):
                training.asset_types_correction_updates(old, candidate)


if __name__ == "__main__":
    unittest.main(verbosity=2)

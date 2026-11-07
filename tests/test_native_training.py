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
                "source_sha256": source, "module_sha256": module_hash, "loader_manifest_sha256": module_hash}
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

    def test_repository_change_requires_an_explicit_exact_checkpoint(self):
        checkpoint = {"revision": "audited_revision", "index_sha256": "audited_index"}
        self.assertTrue(training.repository_matches_checkpoint("audited_revision", "audited_index", checkpoint))
        self.assertFalse(training.repository_matches_checkpoint("arbitrary_descendant", "audited_index", checkpoint))
        self.assertFalse(training.repository_matches_checkpoint("audited_revision", "parallel_staging", checkpoint))

    def test_loader_metadata_requires_observed_build_matching_ids_and_actual_elf(self):
        binary = self.folder / "owned.so"
        binary.write_bytes(b"\x7fELFowned_fixture_not_executed")
        engine = {"BuildId": "observed_engine"}
        expected = {"BuildId": "observed_engine", "Modules": {"NovanodeTraining": "libUnrealEditor-NovanodeTraining.so"}}
        self.assertEqual(training.loader_inventory(engine, engine, binary, 0), expected)
        for code in (None, False, 6):
            with self.assertRaises(training.StudioError):
                training.loader_inventory(engine, engine, binary, code)
        with self.assertRaises(training.StudioError):
            training.loader_inventory(engine, {"BuildId": "other_engine"}, binary, 0)
        binary.write_bytes(b"not_elf")
        with self.assertRaises(training.StudioError):
            training.loader_inventory(engine, engine, binary, 0)

    def test_bootstrap_is_scoped_to_schema_and_preparation_not_runtime(self):
        for operation in ("schema", "prepare"):
            self.assertIn("-DPCVars=GameFeaturePlugin.SkipBuiltInGameFeatures=1", training.command(operation, self.folder))
        self.assertFalse(any("SkipBuiltInGameFeatures" in x for x in training.command("verify", self.folder)))
        self.assertFalse(any("SkipBuiltInGameFeatures" in x for x in training.command("validate-assets", self.folder)))
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn("MountExplicitlyLoadedPlugin(Name)", source)

    def test_loader_publication_refuses_existing_metadata_without_overwrite(self):
        stage = self.folder / "plugin"
        existing = stage / training.LOADER
        existing.parent.mkdir(parents=True)
        existing.write_text("preserve")
        with patch.object(training, "STAGE", stage), patch.object(training, "loader_inventory", return_value={}), \
                patch.object(training, "load_json", return_value={}):
            with self.assertRaisesRegex(training.StudioError, "already exists"):
                training.publish_loader_inventory({"exit_code": 0})
        self.assertEqual(existing.read_text(), "preserve")

    def test_regular_plugin_is_not_sent_to_explicit_mount_operation(self):
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn('MountPointExists(TEXT("/LyraExampleContent/"))', source)
        self.assertIn('{ TEXT("ShooterCore"), TEXT("NovanodeTraining") }', source)
        self.assertNotIn('{ TEXT("LyraExampleContent"), TEXT("ShooterCore")', source)

    def test_loader_reuse_requires_observed_build_and_exact_previous_binary(self):
        row = {"operation": "build", "state": "completed", "exit_code": 0,
               "module_sha256": "previous_elf", "loader_manifest_sha256": "loader"}
        self.assertTrue(training.proven_loader_reuse([row], "loader", "previous_elf"))
        for changed in ({"state": "blocked"}, {"exit_code": None}, {"exit_code": False}, {"module_sha256": "foreign"}):
            self.assertFalse(training.proven_loader_reuse([{**row, **changed}], "loader", "previous_elf"))
        self.assertFalse(training.proven_loader_reuse([row], "different_loader", "previous_elf"))

    def test_authoring_objects_have_scoped_gc_roots_not_raw_temporary_owners(self):
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn("TStrongObjectPtr<UGameFeatureAction_AddComponents> Teams", source)
        self.assertIn("TArray<TStrongObjectPtr<UObject>> Created", source)
        self.assertIn("TStrongObjectPtr<UClass> ControllerPin", source)
        self.assertNotIn("auto* Teams = NewObject", source)
        self.assertNotIn("AddToRoot", source)

    def test_native_schema_actually_forces_gc_and_requires_survival(self):
        source = (PRIVATE / "TrainingReflectionAdapter.cpp").read_text()
        self.assertIn("CollectGarbage(RF_NoFlags)", source)
        self.assertIn("scoped_uobject_survives_forced_gc", source)
        self.assertIn("Components && Hosting && Editable && ScopedLifetime", source)

    def test_map_recipe_uses_actual_world_primary_id_not_short_name_guess(self):
        source = (PRIVATE / "TrainingAssets.cpp").read_text()
        self.assertIn("= TrainingMap->GetPrimaryAssetId()", source)
        self.assertIn("const FPrimaryAssetId Actual = Map->GetPrimaryAssetId()", source)
        self.assertIn('Value->ToString() != TEXT("Map:L_HeroTraining")', source)

    def test_mapid_migration_cannot_modify_maps_or_add_remove_assets(self):
        before = {"Experiences/DA_HeroTraining.uasset": "old", "Maps/L_HeroTraining.umap": "preserve"}
        after = {**before, "Experiences/DA_HeroTraining.uasset": "new"}
        training.validate_mapid_migration(before, after)
        for wrong in (before, {**after, "Maps/L_HeroTraining.umap": "changed"},
                      {**after, "extra.uasset": "new"}, {"Experiences/DA_HeroTraining.uasset": "new"}):
            with self.assertRaises(training.StudioError):
                training.validate_mapid_migration(before, wrong)

    def test_match_binds_exported_hero_feature_not_rejected_none(self):
        source = (PRIVATE / "TrainingMatchComponent.cpp").read_text()
        self.assertIn('"Character/LyraHeroComponent.h"', source)
        self.assertIn("RegisterAndCallForClassInitState(APawn::StaticClass(), ULyraHeroComponent::NAME_ActorFeatureName", source)
        self.assertNotIn("RegisterAndCallForClassInitState(APawn::StaticClass(), NAME_None", source)

    def test_initstate_fix_cannot_sync_unrelated_sources(self):
        name = "Source/NovanodeTraining/Private/TrainingMatchComponent.cpp"
        old = {name: "old", "keep.h": "keep"}
        self.assertEqual(training.initstate_source_updates(old, {**old, name: "new"}), {name})
        with self.assertRaises(training.StudioError):
            training.initstate_source_updates(old, {**old, name: "new", "keep.h": "changed"})

    def test_automatic_probe_actions_are_deferred_out_of_initialization_stack(self):
        source = (PRIVATE / "TrainingLobby.cpp").read_text()
        begin = source.index("void UTrainingLobbySubsystem::MatchReady")
        end = source.index("void UTrainingLobbySubsystem::ReturnToLobby", begin)
        branch = source[begin:end]
        self.assertIn("SetTimerForNextTick(FTimerDelegate::CreateWeakLambda", branch)
        self.assertLess(branch.index("SetTimerForNextTick"), branch.index("ReturnToLobby()"))
        self.assertIn("match_ready_pending_next_frame", branch)

    def test_probe_deferral_scope_cannot_alter_combat_or_match_initialization(self):
        name = "Source/NovanodeTraining/Private/TrainingLobby.cpp"
        old = {name: "old", "Source/NovanodeTraining/Private/TrainingMatchComponent.cpp": "keep"}
        self.assertEqual(training.probe_deferral_source_updates(old, {**old, name: "new"}), {name})
        with self.assertRaises(training.StudioError):
            training.probe_deferral_source_updates(old, {name: "new"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

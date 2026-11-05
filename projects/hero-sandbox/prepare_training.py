"""One-shot, additive TrainingV3 assets. Execute only through hero_training.py.

All sample references remain engine-local. No sample source, graphs, images or
asset serialization is returned by this recipe. Existing assets are never saved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "/NovanodeHeroes/TrainingV3"
CONTENT = ROOT / ".studio/lyra/projects/LyraStarterGame/Plugins/NovanodeHeroes/Content"
CHECKPOINT = ROOT / ".studio/evidence/hero-training-v3-implementation-2026-11-05.json"
CLIPS = {
    "Sword_A": "UAL2_StandardSword_Regular_A",
    "Sword_B": "UAL2_StandardSword_Regular_B",
    "Sword_C": "UAL2_StandardSword_Regular_C",
    "Sword_Dash": "UAL2_StandardSword_Dash",
    "Mage_Cast": "UAL2_StandardOverhandThrow",
}
# Source pack naming varies between exporters. Resolution is exact after case,
# punctuation and namespace normalization; absent required bones block the recipe.
CHAINS = {
    "Spine": (["spine_01", "Spine", "spine"], ["spine_05", "Chest", "Spine2", "chest"]),
    "Head": (["neck_01", "Neck", "neck"], ["head", "Head"]),
    "LeftArm": (["upperarm_l", "upper_arm.L", "LeftArm", "arm.L"], ["hand_l", "hand.L", "LeftHand"]),
    "RightArm": (["upperarm_r", "upper_arm.R", "RightArm", "arm.R"], ["hand_r", "hand.R", "RightHand"]),
    "LeftLeg": (["thigh_l", "thigh.L", "LeftUpLeg", "upper_leg.L"], ["foot_l", "foot.L", "LeftFoot"]),
    "RightLeg": (["thigh_r", "thigh.R", "RightUpLeg", "upper_leg.R"], ["foot_r", "foot.R", "RightFoot"]),
}


def hashes():
    return {p.relative_to(CONTENT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in CONTENT.rglob("*") if p.is_file()}


def require_preserved(before, current):
    if any(current.get(name) != value for name, value in before.items()):
        raise RuntimeError("pre_existing_content_changed_preserve_and_review")
    if any(not name.startswith("TrainingV3/") for name in set(current) - set(before)):
        raise RuntimeError("unexpected_additive_asset_namespace")


def main():
    import unreal
    folder = Path(os.environ["NN_HERO_TRAINING_DIR"])
    report = {"state": "preparing", "recipe": "hero-training-v3", "visual_verified": False,
              "runtime_verified": False, "sample_content_exported": False, "phase": "preflight"}
    def record(phase):
        report["phase"] = phase
        (folder / "prepare.json").write_text(json.dumps(report, indent=2) + "\n")
    try:
        before = json.loads(CHECKPOINT.read_text())["content_before_sha256"]
        require_preserved(before, hashes())
        lib = unreal.EditorAssetLibrary
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous(["/NovanodeHeroes", "/ShooterCore/Experiences"], force_rescan=True)
        registry.wait_for_completion()
        assert not any(name.startswith("TrainingV3/") for name in hashes()), "training_namespace_already_exists"
        reference = unreal.load_class(None, "/ShooterCore/Experiences/B_ShooterGame_Elimination.B_ShooterGame_Elimination_C")
        assert reference, "baseline_experience_missing"
        adapter = unreal.HeroTrainingEditorTools
        target = adapter.get_player_retarget_mesh(reference)
        bot_parent = adapter.get_stock_bot_component_class(reference)
        assert target and bot_parent, "baseline_target_or_bot_component_missing"
        attack_slot = adapter.get_attack_slot(target)
        assert str(attack_slot) != "None", "existing_player_montage_slot_missing"
        rows = registry.get_assets_by_path("/NovanodeHeroes/AnimationLibrary", recursive=True, include_only_on_disk_assets=True)
        own = [row.get_asset() for row in rows]
        meshes = [obj for obj in own if isinstance(obj, unreal.SkeletalMesh)]
        sequences = {obj.get_name(): obj for obj in own if isinstance(obj, unreal.AnimSequence)}
        assert len(meshes) == 1 and len(sequences) == 43, "owned_import_counts_differ"
        assert all(name in sequences for name in CLIPS.values()), "required_owned_animation_missing"
        source = meshes[0]

        def blueprint(name, parent):
            assert not lib.does_asset_exist(PREFIX + "/" + name), "owned_destination_exists"
            factory = unreal.BlueprintFactory()
            factory.set_editor_property("parent_class", parent)
            asset = tools.create_asset(name, PREFIX, unreal.Blueprint, factory)
            assert asset, "owned_blueprint_creation_failed"
            return asset

        def data_asset(name, cls):
            factory = unreal.DataAssetFactory()
            factory.set_editor_property("data_asset_class", cls)
            obj = tools.create_asset(name, PREFIX, cls, factory)
            assert obj, "owned_data_asset_creation_failed"
            return obj

        def rig(name, mesh):
            asset = tools.create_asset(name, PREFIX + "/Retarget", unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
            assert asset, "owned_ik_rig_creation_failed"
            controller = unreal.IKRigController.get_controller(asset)
            assert controller.set_skeletal_mesh(mesh), "ik_mesh_assignment_failed"
            pelvis = adapter.resolve_bone(mesh, ["pelvis", "Hips", "hips"])
            assert str(pelvis) != "None", "required_pelvis_bone_missing"
            assert controller.set_retarget_root(pelvis), "retarget_root_assignment_failed"
            for chain, (starts, ends) in CHAINS.items():
                start, end = adapter.resolve_bone(mesh, starts), adapter.resolve_bone(mesh, ends)
                assert str(start) != "None" and str(end) != "None", "required_chain_bone_missing"
                actual = controller.add_retarget_chain(chain, start, end, "None")
                assert str(actual) == chain, "retarget_chain_creation_failed"
            assert lib.save_loaded_asset(asset), "owned_ik_rig_save_failed"
            return asset

        # Resolve every mandatory chain before writing any assets, so an unsupported
        # source rig is a clean blocker rather than a half-created guessed retarget.
        for mesh in (source, target):
            for starts, ends in CHAINS.values():
                assert str(adapter.resolve_bone(mesh, starts)) != "None" and str(adapter.resolve_bone(mesh, ends)) != "None", "required_chain_bone_missing"

        record("retarget_owned_player_attacks")
        source_rig, target_rig = rig("IK_HeroTraining_Source_v3", source), rig("IK_HeroTraining_Player_v3", target)
        retargeter = tools.create_asset("RTG_HeroTraining_v3", PREFIX + "/Retarget", unreal.IKRetargeter, unreal.IKRetargetFactory())
        assert retargeter, "owned_retargeter_creation_failed"
        controller = unreal.IKRetargeterController.get_controller(retargeter)
        controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
        controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
        controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source)
        controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target)
        controller.add_default_ops()
        controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
        controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.SOURCE)
        assert lib.save_loaded_asset(retargeter), "owned_retargeter_save_failed"
        inputs = unreal.IKRetargetBatchOperationInputs(
            assets_to_retarget=[lib.find_asset_data(sequences[name].get_path_name()) for name in CLIPS.values()],
            source_mesh=source, target_mesh=target, ik_retarget_asset=retargeter,
            target_path=PREFIX + "/Animations", prefix="HT3_", include_referenced_assets=False,
            overwrite_existing_files=False, use_source_path=False)
        outputs = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
        assert len(outputs) == 5, "retarget_output_count_differ"
        retargeted = {obj.get_name(): obj for obj in (row.get_asset() for row in outputs)}
        montages = {}
        for key, original in CLIPS.items():
            sequence = retargeted.get("HT3_" + original)
            assert isinstance(sequence, unreal.AnimSequence), "owned_retargeted_sequence_missing"
            assert sequence.get_editor_property("skeleton") == target.get_editor_property("skeleton"), "player_skeleton_mismatch"
            assert lib.save_loaded_asset(sequence), "owned_sequence_save_failed"
            montage = adapter.create_owned_montage(sequence, "AM_HeroTraining_" + key + "_v3", attack_slot)
            assert montage and lib.save_loaded_asset(montage), "owned_montage_save_failed"
            montages[key] = montage

        record("native_ability_sets_and_equipment")
        ability_set = data_asset("AbilitySet_HeroTraining_v3", unreal.LyraAbilitySet)
        assert adapter.configure_ability_set(ability_set), "native_ability_set_configuration_failed"
        assert lib.save_loaded_asset(ability_set), "owned_ability_set_save_failed"
        equipment = {}
        for key, mage in (("Sword", False), ("Mage", True)):
            asset = blueprint("B_HeroTraining" + key + "Equipment_v3", unreal.LyraEquipmentDefinition)
            assert adapter.configure_equipment(asset.generated_class(), ability_set, mage, target), "native_equipment_configuration_failed"
            unreal.BlueprintEditorLibrary.compile_blueprint(asset)
            assert lib.save_loaded_asset(asset), "owned_equipment_save_failed"
            equipment[key] = asset.generated_class()

        record("three_bot_training_experience")
        bots = blueprint("B_HeroTrainingBots_v3", bot_parent)
        unreal.get_default_object(bots.generated_class()).set_editor_property("num_bots_to_create", 3)
        unreal.BlueprintEditorLibrary.compile_blueprint(bots)
        assert lib.save_loaded_asset(bots), "owned_bot_configuration_save_failed"
        exp = blueprint("B_HeroTraining_v3", unreal.LyraExperienceDefinition)
        default = unreal.get_default_object(exp.generated_class())
        default.set_editor_property("default_pawn_data", unreal.get_default_object(reference).get_editor_property("default_pawn_data"))
        default.set_editor_property("game_features_to_enable", ["ShooterCore"])
        assert adapter.configure_experience(exp.generated_class(), reference, bots.generated_class()), "native_experience_configuration_failed"
        unreal.BlueprintEditorLibrary.compile_blueprint(exp)
        assert lib.save_loaded_asset(exp), "owned_experience_save_failed"
        data = data_asset("DA_HeroTraining_v3", unreal.HeroTrainingData)
        for key, value in {
            "sword_montages": [montages[name] for name in ("Sword_A", "Sword_B", "Sword_C")],
            "cast_montage": montages["Mage_Cast"], "dash_montage": montages["Sword_Dash"],
            "sword_equipment": equipment["Sword"], "mage_equipment": equipment["Mage"],
            "target_mesh": target, "attack_slot": attack_slot, "sword_length_cm": 120.0,
        }.items():
            data.set_editor_property(key, value)
        assert lib.save_loaded_asset(data), "owned_training_data_save_failed"
        current = hashes()
        require_preserved(before, current)
        report.update(state="prepared", phase="complete", generated_sha256=current,
                      pre_existing_content_unchanged=True, added_assets=len(set(current) - set(before)),
                      player_attack_montages=5, bot_count=3, mage_cast_animation="provisional_overhand_throw",
                      grip_alignment="structural_only_human_review_pending")
        record("complete")
    except Exception as exc:
        report.update(state="blocked", error_type=type(exc).__name__)
        (folder / "prepare.json").write_text(json.dumps(report, indent=2) + "\n")
        # Raw native exceptions remain in the engine-local console only.
        raise


if __name__ == "__main__":
    main()

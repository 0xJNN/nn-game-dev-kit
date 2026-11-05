"""Read-only load/schema verification, not a rendered or full gameplay approval."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_training import CLIPS, PREFIX, CHECKPOINT, hashes, require_preserved


def main():
    import unreal
    folder = Path(os.environ["NN_HERO_TRAINING_DIR"])
    report = {"state": "validating", "runtime_verified": False, "visual_verified": False,
              "sample_content_exported": False}
    try:
        before = json.loads(CHECKPOINT.read_text())["content_before_sha256"]
        initial = hashes()
        require_preserved(before, initial)
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous(["/NovanodeHeroes"], force_rescan=True)
        registry.wait_for_completion()
        lib = unreal.EditorAssetLibrary
        data = lib.load_asset(PREFIX + "/DA_HeroTraining_v3")
        assert isinstance(data, unreal.HeroTrainingData), "training_data_missing"
        target = data.get_editor_property("target_mesh")
        assert target, "target_mesh_missing"
        assert len(data.get_editor_property("sword_montages")) == 3, "sword_combo_montage_count_differ"
        assert data.get_editor_property("cast_montage") and data.get_editor_property("dash_montage"), "skill_montage_missing"
        assert data.get_editor_property("sword_equipment") and data.get_editor_property("mage_equipment"), "equipment_missing"
        assert str(data.get_editor_property("attack_slot")) != "None", "attack_slot_missing"
        assert 80.0 <= data.get_editor_property("sword_length_cm") <= 160.0, "weapon_scale_outside_bounds"
        montage_count = 0
        for key in CLIPS:
            montage = lib.load_asset(PREFIX + "/Montages/AM_HeroTraining_" + key + "_v3")
            assert isinstance(montage, unreal.AnimMontage), "body_montage_missing"
            assert montage.get_editor_property("skeleton") == target.get_editor_property("skeleton"), "body_montage_skeleton_mismatch"
            assert montage.get_play_length() > 0, "body_montage_empty"
            montage_count += 1
        for name in ("B_HeroTraining_v3", "B_HeroTrainingBots_v3", "B_HeroTrainingSwordEquipment_v3", "B_HeroTrainingMageEquipment_v3"):
            assert lib.does_asset_exist(PREFIX + "/" + name), "owned_blueprint_missing"
            assert unreal.load_class(None, PREFIX + "/" + name + "." + name + "_C"), "owned_generated_class_missing"
        bots = unreal.load_class(None, PREFIX + "/B_HeroTrainingBots_v3.B_HeroTrainingBots_v3_C")
        assert unreal.get_default_object(bots).get_editor_property("num_bots_to_create") == 3, "bot_count_configuration_differ"
        assert hashes() == initial, "validation_changed_assets"
        report.update(state="prepared", generated_sha256=initial, pre_existing_content_unchanged=True,
                      player_attack_montages=montage_count, bot_count=3,
                      scope="asset_load_and_schema_only_not_gameplay")
    except Exception as exc:
        report.update(state="blocked", error_type=type(exc).__name__)
    (folder / "validation.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

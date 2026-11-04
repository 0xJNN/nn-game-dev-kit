"""Fresh read-only reconciliation of exactly hashed v2 preparation outputs.

This never recreates actions/materials, overwrites a partial map, saves packages,
or ignores a prior failed engine lifecycle. The wrapper must separately accept
this fresh operation with zero errors and a normal exit before enabling play.
"""
import hashlib
import json
import os
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(os.environ["NN_HERO_BUILD_DIR"])
REPORT = FOLDER / "prepare.json"
SOURCE_REPORT = Path(os.environ["NN_HERO_RECONCILE_JOURNAL"])
PREFIX = "/NovanodeHeroes"
MAP = PREFIX + "/Maps/L_HeroSandbox_v2"
LIB = unreal.EditorAssetLibrary
RESULT = {"state": "validating", "recipe": "presentation-v2-readonly-reconciliation",
          "source_journal": SOURCE_REPORT.relative_to(ROOT).as_posix(), "read_only": True,
          "visual_verified": False, "sample_content_exported": False}


def content_hashes():
    folder = ROOT / ".studio/lyra/projects/LyraStarterGame/Plugins/NovanodeHeroes/Content"
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file()}


try:
    source = json.loads(SOURCE_REPORT.read_text())
    expected = source["preparation"]["generated_sha256"]
    assert source["preparation"]["state"] == "prepared" and content_hashes() == expected, "No exact prepared artifact identity"
    base = json.loads((ROOT / ".studio/checkpoints/hero-sandbox-presentation-v2/before.json").read_text())
    assert all(expected.get(name) == value for name, value in base["pre_existing_content_sha256"].items()), "V1 preservation mismatch"
    cls = unreal.load_class(None, PREFIX + "/Experiences/B_HeroSandbox_v2.B_HeroSandbox_v2_C")
    assert cls, "Own v2 experience class unavailable"
    default = unreal.get_default_object(cls)
    assert default.get_editor_property("default_pawn_data"), "Pawn data missing"
    assert list(default.get_editor_property("game_features_to_enable")) == ["ShooterCore"], "Feature wiring changed"
    # This engine-native action has no exported Python wrapper in this install.
    # Validate its exact class/entry/receiver/server flag via our read-only native adapter.
    assert unreal.HeroSandboxEditorTools.validate_owned_cosmetic_assembly_action(cls), "Invalid server-side character assembly action"
    assert not list(default.get_editor_property("action_sets")), "Do not inherit match/bot/UI action sets"
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assert levels.load_level(MAP), "Own v2 map load failed"
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    settings = world.get_world_settings()
    assert "B_HeroSandbox_v2" in str(settings.get_editor_property("default_gameplay_experience")), "Wrong default experience"
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    directors = sum(isinstance(actor, unreal.HeroSandboxDirector) for actor in actors)
    texts = sum(isinstance(actor, unreal.HeroFacingTextActor) for actor in actors)
    previews = sum(isinstance(actor, unreal.SkeletalMeshActor) for actor in actors)
    assert directors == 1 and texts >= 7 and previews >= 3, "Incomplete map assembly"
    for name in ("Floor", "Wall", "Mage", "Sword", "Trim", "Target"):
        assert LIB.does_asset_exist(PREFIX + "/PresentationV2/M_" + name + "_v2"), "Original palette asset missing"
    assert content_hashes() == expected, "Read-only validation changed package bytes"
    RESULT.update(state="prepared", map=MAP, controller_cosmetic_action_entries=1,
                  editor_preview_mesh_actors=previews, facing_text_actors=texts,
                  pre_existing_content_unchanged=True, generated_sha256=expected)
except Exception as exc:
    RESULT.update(state="blocked", error_type=type(exc).__name__)
    if isinstance(exc, AssertionError):
        RESULT["detail"] = str(exc)
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")
    raise
REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")

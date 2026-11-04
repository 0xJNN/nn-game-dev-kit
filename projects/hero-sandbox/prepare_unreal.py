"""Run ONLY through manage.py prepare, with exclusive editor ownership.

Creates assets in /NovanodeHeroes only. Restricted Lyra assets are referenced
locally by the engine, never serialized/exported to a model or a public file.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import wave

import unreal

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(os.environ["NN_HERO_BUILD_DIR"])
REPORT = FOLDER / "prepare.json"
PREFIX = "/NovanodeHeroes"
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.EditorAssetLibrary
PHASE = "initialization"
RESULT = {"state": "preparing", "visual_verified": False, "multiplayer_verified": False,
          "sample_content_exported": False, "phases": []}


def record(phase, **values):
    global PHASE
    PHASE = phase
    RESULT["phases"].append({"phase": phase, **values})
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")


def own_assets(path):
    assert path.startswith(PREFIX + "/")
    return [LIB.load_asset(p) for p in LIB.list_assets(path, recursive=True, include_folder=False)]


def receipt(asset_id):
    folder = ROOT / ".studio/downloads/hero-sandbox" / asset_id
    data = json.loads((folder / "receipt.json").read_text())
    path = ROOT / data["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == data["sha256"], "Acquired artifact hash differs"
    return folder, data


def import_glb(path, destination, animation=False):
    if own_assets(destination):
        record("reuse_owned_import", destination=destination)
        return own_assets(destination)
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.animation_pipeline.set_editor_property("import_animations", animation)
    pipeline.animation_pipeline.set_editor_property("use30_hz_to_bake_bone_animation", True)
    pipeline.common_skeletal_meshes_and_animations_properties.set_editor_property("try_auto_select_skeleton", False)
    pipeline.common_skeletal_meshes_and_animations_properties.set_editor_property("skeleton", None)
    parameters = unreal.ImportAssetParameters()
    parameters.set_editor_property("is_automated", True)
    parameters.set_editor_property("replace_existing", False)
    parameters.set_editor_property("override_pipelines", [unreal.SoftObjectPath(pipeline.get_path_name())])
    source = unreal.InterchangeManager.create_source_data(str(path))
    record("import_glb", destination=destination, animated=animation)
    result = manager.import_asset(destination, source, parameters)
    if isinstance(result, tuple): result = result[0]
    assert result, "Reviewed GLB import failed"
    objects = own_assets(destination)
    assert objects, "Import produced no native assets"
    for obj in objects: LIB.save_loaded_asset(obj)
    return objects


def audio():
    record("original_audio")
    directory = FOLDER / "authored-audio"
    directory.mkdir()
    for name, frequency in (("S_Cast", 660.), ("S_Slash", 160.), ("S_Impact", 90.)):
        if LIB.does_asset_exist(PREFIX + "/Audio/" + name): continue
        path = directory / (name + ".wav")
        rate, length = 44100, .22
        samples = []
        for i in range(int(rate * length)):
            t = i / rate
            envelope = min(1., t * 200.) * (1. - t / length) ** 2
            chirp = frequency * t + frequency * t * t * (2. if name == "S_Cast" else -1.)
            value = .35 * envelope * (math.sin(2. * math.pi * chirp) + .2 * math.sin(2. * math.pi * chirp * 2.31))
            samples.append(struct.pack("<h", int(max(-1., min(1., value)) * 32767)))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
            output.writeframes(b"".join(samples))
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(path))
        task.set_editor_property("destination_path", PREFIX + "/Audio")
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        TOOLS.import_asset_tasks([task])
        assert LIB.does_asset_exist(PREFIX + "/Audio/" + name), "Authored audio import missing"


def experience():
    record("experience")
    path = PREFIX + "/Experiences/B_HeroSandbox"
    if LIB.does_asset_exist(path):
        return unreal.load_class(None, path + ".B_HeroSandbox_C")
    # Public Lyra class and sample experience identities. This local reference
    # copies only the pawn-data pointer, not code/graphs/content into AI context.
    base = unreal.load_class(None, "/Script/LyraGame.LyraExperienceDefinition")
    source = unreal.load_class(None, "/ShooterCore/Experiences/B_ShooterGame_Elimination.B_ShooterGame_Elimination_C")
    assert base and source, "Documented Lyra experience prerequisite unavailable"
    pawn_data = unreal.get_default_object(source).get_editor_property("default_pawn_data")
    assert pawn_data, "Baseline pawn-data reference unavailable"
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", base)
    asset = TOOLS.create_asset("B_HeroSandbox", PREFIX + "/Experiences", unreal.Blueprint, factory)
    assert asset, "Could not create isolated experience"
    generated = asset.generated_class()
    default = unreal.get_default_object(generated)
    default.set_editor_property("default_pawn_data", pawn_data)
    default.set_editor_property("game_features_to_enable", ["ShooterCore"])
    # No shooter match/bot/UI action sets: this is a small mechanics laboratory.
    unreal.BlueprintEditorLibrary.compile_blueprint(asset)
    LIB.save_loaded_asset(asset)
    return generated


def spawn(cls, xyz, rotation=(0., 0., 0.)):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return actors.spawn_actor_from_class(cls, unreal.Vector(*xyz), unreal.Rotator(*rotation))


def box(location, scale):
    actor = spawn(unreal.StaticMeshActor, location)
    actor.static_mesh_component.set_static_mesh(LIB.load_asset("/Engine/BasicShapes/Cube"))
    actor.set_actor_scale3d(unreal.Vector(*scale))
    return actor


def label(text, location, size=28.):
    actor = spawn(unreal.TextRenderActor, location, (0., 180., 0.))
    component = actor.get_component_by_class(unreal.TextRenderComponent)
    component.set_text(text)
    component.set_world_size(size)
    component.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    return actor


def level(exp, external_meshes, clips):
    record("map")
    path = PREFIX + "/Maps/L_HeroSandbox_v1"
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if LIB.does_asset_exist(path):
        assert levels.load_level(path), "Existing owned map failed to load"
    else:
        assert levels.new_level(path), "Map creation failed"
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    settings = world.get_world_settings()
    complete_tag = unreal.Name("NN_HERO_RECIPE_V1_COMPLETE")
    if complete_tag in settings.get_editor_property("tags"):
        record("reuse_owned_complete_map")
        return
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    assert not any(isinstance(a, (unreal.StaticMeshActor, unreal.SkeletalMeshActor, unreal.TextRenderActor)) for a in actors), "Partial map contains work: checkpoint/migrate instead of duplicating or replacing it"
    assert levels.save_current_level(), "Initial owned map identity must be saved before assignment"
    settings.set_editor_property("default_game_mode", unreal.load_class(None, "/Script/LyraGame.LyraGameMode"))
    assert unreal.HeroSandboxEditorTools.configure_owned_map(world, exp), "Owned map experience assignment failed"
    box((400., 0., -25.), (30., 24., .5))
    box((1900., 0., 125.), (.3, 24., 3.))
    box((-1100., 0., 125.), (.3, 24., 3.))
    box((400., 1200., 125.), (30., .3, 3.))
    box((400., -1200., 125.), (30., .3, 3.))
    # Cover lane is away from the clear projectile/sword lane.
    box((700., 650., 90.), (.4, 3., 1.8))
    light = spawn(unreal.DirectionalLight, (0., 0., 600.), (-45., -30., 0.))
    light.light_component.set_editor_property("intensity", 5.)
    sky = spawn(unreal.SkyLight, (0., 0., 400.))
    sky.light_component.set_editor_property("intensity", .8)
    start_class = unreal.load_class(None, "/Script/LyraGame.LyraPlayerStart")
    assert start_class, "Lyra player start class unavailable"
    for y in (-250., 250.): spawn(start_class, (0., y, 105.))
    spawn(unreal.HeroSandboxDirector, (0., 0., 0.))
    label("NOVANODE | HERO LAB", (1300., 0., 330.), 60.)
    label("1 MAGE   2 SWORD   |   J ATTACK   K DASH", (1300., 0., 250.), 35.)
    label("100 HP targets | reset after defeat | WASD + mouse (Lyra)", (1300., 0., 185.), 24.)
    label("CC0 RESOURCE PREVIEW | Quaternius | not Lyra-retargeted", (600., 850., 240.), 22.)
    # Three external animation demonstrations on the pack's own original rig.
    # These are NOT misleadingly presented as retargeted Lyra player montages.
    if external_meshes:
        chosen = [a for a in clips if "Sword_Regular_A" in a.get_name() and "Rec" not in a.get_name()][:2]
        chosen += [a for a in clips if "Sword_Dash" in a.get_name()][:1]
        for index, clip in enumerate(chosen):
            actor = spawn(unreal.SkeletalMeshActor, (400. + index * 240., 850., 0.), (0., 180., 0.))
            component = actor.skeletal_mesh_component
            component.set_skeletal_mesh_asset(external_meshes[0])
            component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            # Serialized animation_data plays in PIE, unlike a transient editor preview call.
            data = unreal.SingleAnimationPlayData()
            data.set_editor_property("anim_to_play", clip)
            data.set_editor_property("saved_looping", True)
            data.set_editor_property("saved_playing", True)
            component.set_editor_property("animation_data", data)
            label(clip.get_name().replace("UAL2_Standard_", ""), (400. + index * 240., 850., 210.), 15.)
    settings.set_editor_property("tags", list(settings.get_editor_property("tags")) + [complete_tag])
    assert levels.save_current_level(), "Map save failed"


def main():
    record("validate_downloads")
    folder, data = receipt("quaternius-ual2-standard")
    entries = [p for p in data["extracted"] if p["file"].endswith("Unreal-Godot/UAL2_Standard.glb")]
    assert len(entries) == 1, "Expected one reviewed in-place Unreal GLB"
    path = folder / "media" / entries[0]["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entries[0]["sha256"], "Extracted GLB changed"
    objects = import_glb(path, PREFIX + "/AnimationLibrary", True)
    clips = [a for a in objects if isinstance(a, unreal.AnimSequence)]
    meshes = [a for a in objects if isinstance(a, unreal.SkeletalMesh)]
    assert meshes and clips, "Animation import must contain a rig and real animation clips"
    RESULT["animation_count"] = len(clips)
    RESULT["sword_clip_count"] = sum("Sword" in a.get_name() for a in clips)
    RESULT["external_mesh_count"] = len(meshes)
    folder, data = receipt("quaternius-claymore-poly-pizza")
    alias = PREFIX + "/Imported/SM_Claymore"
    objects = [LIB.load_asset(alias)] if LIB.does_asset_exist(alias) else import_glb(ROOT / data["file"], PREFIX + "/Imported/Claymore")
    swords = [a for a in objects if isinstance(a, unreal.StaticMesh)]
    assert len(swords) == 1, "Expected one reviewed static weapon mesh"
    if not LIB.does_asset_exist(PREFIX + "/Imported/SM_Claymore"):
        assert LIB.rename_asset(swords[0].get_path_name(), PREFIX + "/Imported/SM_Claymore"), "Weapon alias failed"
    audio()
    exp = experience()
    level(exp, meshes, clips)
    RESULT.update(state="prepared", mage_staff="original_primitive_placeholder", player_combat_animation="procedural_weapon_only",
                  retargeted_lyra_player_animation=False, audio="3_original_synthesized_waves", map=PREFIX + "/Maps/L_HeroSandbox_v1")
    record("complete")
    # Record only authored/imported plugin assets, never sample content metadata.
    stage = ROOT / ".studio/lyra/projects/LyraStarterGame/Plugins/NovanodeHeroes/Content"
    RESULT["generated_sha256"] = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in stage.rglob("*") if p.is_file()}
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")


try:
    main()
except Exception as exc:
    RESULT.update(state="blocked", blocked_phase=PHASE, error_type=type(exc).__name__, detail=str(exc))
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")
    raise

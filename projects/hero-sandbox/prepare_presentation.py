"""Versioned presentation recipe. Never overwrite v1 or sample content.

Only the controller character-assembly action is wired from the baseline by a
narrow local native adapter. No sample graphs/source/assets are exported to AI.
"""
import hashlib
import json
import os
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(os.environ["NN_HERO_BUILD_DIR"])
REPORT = FOLDER / "prepare.json"
PREFIX = "/NovanodeHeroes"
MAP = PREFIX + "/Maps/L_HeroSandbox_v2"
EXPERIENCE = PREFIX + "/Experiences/B_HeroSandbox_v2"
MATERIALS = PREFIX + "/PresentationV2"
LIB = unreal.EditorAssetLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
RESULT = {"state": "preparing", "recipe": "presentation-v2", "phases": [],
          "visual_verified": False, "sample_content_exported": False}
PHASE = "initialization"


def record(phase, **values):
    global PHASE
    PHASE = phase
    RESULT["phases"].append({"phase": phase, **values})
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")


def old_content_unchanged():
    before = json.loads((ROOT / ".studio/checkpoints/hero-sandbox-presentation-v2/before.json").read_text())
    content = ROOT / ".studio/lyra/projects/LyraStarterGame/Plugins/NovanodeHeroes/Content"
    changed = [name for name, expected in before["pre_existing_content_sha256"].items()
               if not (content / name).is_file() or hashlib.sha256((content / name).read_bytes()).hexdigest() != expected]
    assert not changed, "Pre-existing content changed: preserve and review instead of overwriting"
    return content


def material(name, rgb):
    path = MATERIALS + "/" + name
    assert not LIB.does_asset_exist(path), "New presentation material already exists: checkpoint before resuming"
    asset = TOOLS.create_asset(name, MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    assert asset, "Original material creation failed"
    color = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector)
    color.set_editor_property("constant", unreal.LinearColor(*rgb, 1.))
    assert unreal.MaterialEditingLibrary.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    roughness = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant)
    roughness.set_editor_property("r", .8)
    assert unreal.MaterialEditingLibrary.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    assert LIB.save_loaded_asset(asset)
    return asset


def spawn(cls, location, rotation=(0., 0., 0.)):
    actor = ACTORS.spawn_actor_from_class(cls, unreal.Vector(*location), unreal.Rotator(*rotation))
    assert actor, "Owned scene actor creation failed"
    return actor


def box(location, scale, surface, collision=True):
    actor = spawn(unreal.StaticMeshActor, location)
    actor.static_mesh_component.set_static_mesh(LIB.load_asset("/Engine/BasicShapes/Cube"))
    actor.static_mesh_component.set_material(0, surface)
    if not collision:
        actor.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        actor.static_mesh_component.set_cast_shadow(False)
    actor.set_actor_scale3d(unreal.Vector(*scale))
    return actor


def label(text, location, size=28., viewer=(0., 0., 150.)):
    actor = spawn(unreal.HeroFacingTextActor, location)
    component = actor.get_component_by_class(unreal.TextRenderComponent)
    component.set_text(text)
    component.set_world_size(size)
    component.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    component.set_text_render_color(unreal.Color(235, 245, 255, 255))
    actor.face_entry(unreal.Vector(*viewer))
    return actor


def create_experience():
    record("isolated_experience_with_character_assembly")
    assert not LIB.does_asset_exist(EXPERIENCE), "V2 experience exists: checkpoint instead of replacing it"
    base = unreal.load_class(None, "/Script/LyraGame.LyraExperienceDefinition")
    reference = unreal.load_class(None, "/ShooterCore/Experiences/B_ShooterGame_Elimination.B_ShooterGame_Elimination_C")
    assert base and reference, "Baseline experience API unavailable"
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", base)
    asset = TOOLS.create_asset("B_HeroSandbox_v2", PREFIX + "/Experiences", unreal.Blueprint, factory)
    assert asset, "V2 experience creation failed"
    generated = asset.generated_class()
    default = unreal.get_default_object(generated)
    default.set_editor_property("default_pawn_data", unreal.get_default_object(reference).get_editor_property("default_pawn_data"))
    default.set_editor_property("game_features_to_enable", ["ShooterCore"])
    count = unreal.HeroSandboxEditorTools.add_owned_cosmetic_assembly_action(generated, reference)
    assert count == 1, "Expected exactly one documented controller character-assembly entry"
    unreal.BlueprintEditorLibrary.compile_blueprint(asset)
    assert LIB.save_loaded_asset(asset)
    RESULT["controller_cosmetic_action_entries"] = count
    RESULT["copied_match_bot_ui_or_weapon_grant_actions"] = 0
    return generated


def own_animation_assets():
    objects = [LIB.load_asset(path) for path in LIB.list_assets(PREFIX + "/AnimationLibrary", recursive=True, include_folder=False)]
    meshes = [obj for obj in objects if isinstance(obj, unreal.SkeletalMesh)]
    clips = [obj for obj in objects if isinstance(obj, unreal.AnimSequence)]
    assert len(meshes) == 1 and clips, "Verified CC0 animation imports missing"
    return meshes[0], clips


def preview(mesh, clip, location):
    actor = spawn(unreal.SkeletalMeshActor, location, (0., 180., 0.))
    component = actor.skeletal_mesh_component
    component.set_skeletal_mesh_asset(mesh)
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    data = unreal.SingleAnimationPlayData()
    data.set_editor_property("anim_to_play", clip)
    data.set_editor_property("saved_looping", True)
    data.set_editor_property("saved_playing", True)
    component.set_editor_property("animation_data", data)
    return actor


def calibration():
    record("isolated_original_text_calibration_map")
    path = PREFIX + "/Maps/L_TextCalibration_v2"
    assert not LIB.does_asset_exist(path), "Calibration map exists: preserve it"
    assert LEVELS.new_level(path)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
    for text, z, yaw in (("YAW ZERO   ABC 123", 180., 0.), ("YAW 180   ABC 123", 85., 180.)):
        actor = spawn(unreal.TextRenderActor, (0., 0., z), (0., yaw, 0.))
        component = actor.get_component_by_class(unreal.TextRenderComponent)
        component.set_text(text)
        component.set_world_size(38.)
        component.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    camera = spawn(unreal.CameraActor, (-600., 0., 135.))
    camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    camera.camera_component.set_field_of_view(65.)
    spawn(unreal.PlayerStart, (-900., -500., 120.))
    spawn(unreal.HeroTextCalibrationActor, (0., 0., 0.))
    assert LEVELS.save_current_level()


def create_map(exp, surfaces):
    record("versioned_lab_with_explicit_editor_previews")
    assert not LIB.does_asset_exist(MAP), "V2 map exists: preserve and inspect rather than overwrite"
    assert LEVELS.new_level(MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    settings = world.get_world_settings()
    assert LEVELS.save_current_level()
    settings.set_editor_property("default_game_mode", unreal.load_class(None, "/Script/LyraGame.LyraGameMode"))
    assert unreal.HeroSandboxEditorTools.configure_owned_map(world, exp)
    box((400., 0., -25.), (30., 24., .5), surfaces["floor"])
    for location, scale in (((1900., 0., 125.), (.3, 24., 3.)), ((-1100., 0., 125.), (.3, 24., 3.)),
                            ((400., 1200., 125.), (30., .3, 3.)), ((400., -1200., 125.), (30., .3, 3.))):
        box(location, scale, surfaces["wall"])
    box((700., 650., 90.), (.4, 3., 1.8), surfaces["wall"])
    for y, surface in ((-450., surfaces["mage"]), (450., surfaces["sword"])):
        box((400., y, 1.), (23., .06, .02), surface, False)
    for x in (350., 650., 950.):
        box((x, 0., 1.), (.03, 9., .02), surfaces["trim"], False)
    light = spawn(unreal.DirectionalLight, (0., 0., 600.), (-45., -30., 0.))
    light.light_component.set_editor_property("intensity", 5.)
    sky = spawn(unreal.SkyLight, (0., 0., 400.))
    sky.light_component.set_editor_property("intensity", .8)
    spawn(unreal.SkyAtmosphere, (0., 0., 0.))
    start_class = unreal.load_class(None, "/Script/LyraGame.LyraPlayerStart")
    for y in (-250., 250.): spawn(start_class, (0., y, 105.))
    director = spawn(unreal.HeroSandboxDirector, (0., 0., 0.))
    director.set_editor_property("target_material", surfaces["target"])
    label("NOVANODE | HERO LAB v2", (1300., 0., 330.), 55.)
    label("PRESS PLAY | experience loads automatically", (1300., 0., 255.), 30.)
    label("1 MAGE   2 SWORD  |  J ATTACK  K DASH", (1300., 0., 190.), 28.)
    label("EDITOR PREVIEWS - NOT THE POSSESSED PLAYER", (-400., -820., 260.), 22.)
    mesh, clips = own_animation_assets()
    idle = next((clip for clip in clips if "Idle" in clip.get_name()), clips[0])
    preview(mesh, idle, (-400., -650., 20.))
    box((-400., -650., 10.), (2., 2., .2), surfaces["mage"])
    label("CC0 body preview | player spawns on Play", (-400., -650., 220.), 16.)
    chosen = [clip for clip in clips if "Sword_Regular_A" in clip.get_name() and "Rec" not in clip.get_name()][:2]
    chosen += [clip for clip in clips if "Sword_Dash" in clip.get_name()][:1]
    for index, clip in enumerate(chosen):
        x = 400. + index * 240.
        box((x, 850., 10.), (1.8, 1.8, .2), surfaces["sword"])
        preview(mesh, clip, (x, 850., 20.))
        label("CC0 SWORD CLIP | original rig", (x, 850., 230.), 15.)
    label("Character body: Lyra assembly | attack retarget still pending", (600., 1050., 270.), 19.)
    settings.set_editor_property("tags", list(settings.get_editor_property("tags")) + [unreal.Name("NN_HERO_RECIPE_V2_COMPLETE")])
    assert LEVELS.save_current_level()
    RESULT["editor_preview_mesh_actors"] = len(chosen) + 1
    RESULT["fixed_negative_text_scale_used"] = False


def main():
    record("preserve_v1_and_imported_resources")
    content = old_content_unchanged()
    surfaces = {name: material("M_" + name.capitalize() + "_v2", rgb) for name, rgb in {
        "floor": (.025, .04, .065), "wall": (.07, .095, .14), "mage": (.02, .55, .8),
        "sword": (.9, .22, .045), "trim": (.32, .42, .5), "target": (.8, .7, .42)}.items()}
    exp = create_experience()
    calibration()
    create_map(exp, surfaces)
    old_content_unchanged()
    RESULT.update(state="prepared", map=MAP, experience=EXPERIENCE,
                  pre_existing_content_unchanged=True, persistent_graphics_settings_changed=False,
                  player_combat_animation="procedural_weapon_only_retarget_pending")
    RESULT["generated_sha256"] = {path.relative_to(content).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in content.rglob("*") if path.is_file()}
    record("complete")


try:
    main()
except Exception as exc:
    RESULT.update(state="blocked", blocked_phase=PHASE, error_type=type(exc).__name__)
    if isinstance(exc, AssertionError): RESULT["detail"] = str(exc)
    REPORT.write_text(json.dumps(RESULT, indent=2) + "\n")
    raise

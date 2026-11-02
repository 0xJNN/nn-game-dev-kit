"""Run via the installed Unreal Editor Python commandlet, never a normal Python interpreter.

Creates only generator-owned assets. Existing unmarked assets are never overwritten.
"""
import json
import os
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
MARKER = "novanode-source-v1"
MATERIAL = "/Game/Generated/Materials/M_StudioSurface"
MAP = "/Game/Generated/Maps/NovanodeLab"


def existing_owned(path):
    if not unreal.EditorAssetLibrary.does_asset_exist(path):
        return None
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if unreal.EditorAssetLibrary.get_metadata_tag(asset, "NovanodeGenerator") != MARKER:
        raise RuntimeError(f"Refusing to overwrite an existing unmarked asset: {path}")
    return asset


def make_material():
    if existing_owned(MATERIAL):
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    material = tools.create_asset("M_StudioSurface", "/Game/Generated/Materials",
                                  unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError("Material asset creation failed")
    for index, (name, expression_type, default, prop) in enumerate([
        ("BaseColor", unreal.MaterialExpressionVectorParameter, unreal.LinearColor(0.08, 0.12, 0.16, 1), unreal.MaterialProperty.MP_BASE_COLOR),
        ("Emissive", unreal.MaterialExpressionVectorParameter, unreal.LinearColor(0, 0, 0, 1), unreal.MaterialProperty.MP_EMISSIVE_COLOR),
        ("Roughness", unreal.MaterialExpressionScalarParameter, 0.65, unreal.MaterialProperty.MP_ROUGHNESS),
        ("Metallic", unreal.MaterialExpressionScalarParameter, 0.25, unreal.MaterialProperty.MP_METALLIC),
    ]):
        expression = unreal.MaterialEditingLibrary.create_material_expression(material, expression_type, -350, index * 180)
        expression.set_editor_property("parameter_name", name)
        expression.set_editor_property("default_value", default)
        if not unreal.MaterialEditingLibrary.connect_material_property(expression, "", prop):
            raise RuntimeError(f"Cannot connect material property {name}")
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "NovanodeGenerator", MARKER)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError("Cannot save material")


def make_map():
    if existing_owned(MAP):
        return
    unreal.EditorAssetLibrary.make_directory("/Game/Generated/Maps")
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    if world is None:
        raise RuntimeError("Cannot create blank map")
    unreal.EditorAssetLibrary.set_metadata_tag(world, "NovanodeGenerator", MARKER)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, MAP):
        raise RuntimeError("Cannot save generated map")


def main():
    output = ROOT / ".studio/evidence/unreal-prepare.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    unreal.EditorAssetLibrary.make_directory("/Game/Generated/Materials")
    make_material()
    make_map()
    pending = output.with_suffix(".pending.json")
    pending.write_text(json.dumps({
        "status": "assets_prepared", "human_approval": "pending",
        "assets": [MATERIAL, MAP], "generator": MARKER,
        "note": "Runtime room is built by StudioGameMode; press Play after opening the map.",
    }, indent=2) + "\n", encoding="utf-8")
    os.replace(pending, output)
    unreal.log("NOVANODE_PREPARE_COMPLETE")


if __name__ == "__main__":
    main()

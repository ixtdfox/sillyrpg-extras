from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bpy

from . import atlas_manifest, textures, utils
from .furniture_catalog import FURNITURE_BY_ID, FurnitureDef


FURNITURE_MANIFEST = {
    "atlas": "furniture_atlas.png",
    "version": 1,
    "tileSize": 128,
    "atlas_width": 512,
    "atlas_height": 512,
    "materials": {
        "painted_metal_white": {"x": 0, "y": 0, "w": 128, "h": 128},
        "painted_metal_gray": {"x": 128, "y": 0, "w": 128, "h": 128},
        "dark_plastic": {"x": 256, "y": 0, "w": 128, "h": 128},
        "rubber_black": {"x": 384, "y": 0, "w": 128, "h": 128},
        "wood_light": {"x": 0, "y": 128, "w": 128, "h": 128},
        "wood_dark": {"x": 128, "y": 128, "w": 128, "h": 128},
        "fabric_blue": {"x": 256, "y": 128, "w": 128, "h": 128},
        "fabric_brown": {"x": 384, "y": 128, "w": 128, "h": 128},
        "glass_blue": {"x": 0, "y": 256, "w": 128, "h": 128},
        "screen_dark": {"x": 128, "y": 256, "w": 128, "h": 128},
        "screen_green": {"x": 256, "y": 256, "w": 128, "h": 128},
        "ceramic_white": {"x": 384, "y": 256, "w": 128, "h": 128},
        "warning_yellow": {"x": 0, "y": 384, "w": 128, "h": 128},
        "medical_red": {"x": 128, "y": 384, "w": 128, "h": 128},
        "label_panel": {"x": 256, "y": 384, "w": 128, "h": 128},
        "vent_grille": {"x": 384, "y": 384, "w": 128, "h": 128},
    },
}

WALL_OBJECTS = {
    "tv_screen", "wall_shelf", "wall_mirror", "mirror_cabinet", "towel_rack",
    "wall_lamp", "wall_terminal", "notice_board", "wall_pipe", "first_aid_box",
    "note_board", "emergency_button", "wall_screen", "map_board",
}


class FurnitureBuildContext:
    def __init__(self, scene, collection, settings, atlas_runtime, rng):
        self.scene = scene
        self.collection = collection
        self.settings = settings
        self.atlas_runtime = atlas_runtime
        self.rng = rng
        self.created_objects: list[bpy.types.Object] = []


def furniture_asset_path(filename: str) -> str:
    return atlas_manifest.addon_asset_path(filename)


def default_furniture_manifest() -> dict:
    manifest = json.loads(json.dumps(FURNITURE_MANIFEST))
    manifest["regions"] = dict(manifest["materials"])
    return manifest


def ensure_furniture_manifest(path_str: str) -> dict:
    path = Path(atlas_manifest._abs_path(path_str))
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    else:
        manifest = default_furniture_manifest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if "regions" not in manifest and "materials" in manifest:
        manifest["regions"] = dict(manifest["materials"])
    valid, message = atlas_manifest.validate_manifest(manifest)
    if not valid:
        raise RuntimeError(message)
    return manifest


def build_furniture_runtime(settings) -> dict:
    manifest_path = getattr(settings, "furniture_manifest_path", furniture_asset_path("furniture_atlas_manifest.json"))
    manifest = ensure_furniture_manifest(manifest_path)
    image_path = getattr(settings, "furniture_atlas_image_path", furniture_asset_path("furniture_atlas.png"))
    if not getattr(settings, "furniture_use_atlas", True):
        image_path = ""
    return {
        "manifest": manifest,
        "atlas_width": int(manifest.get("atlas_width", 512)),
        "atlas_height": int(manifest.get("atlas_height", 512)),
        "image_path": image_path,
        "regions": manifest.get("regions", manifest.get("materials", {})),
    }


def _part(obj: bpy.types.Object, context: FurnitureBuildContext, material_key: str, object_id: str, room_type: str) -> bpy.types.Object:
    textures.apply_material_and_uv(obj, context.atlas_runtime, material_key)
    utils.set_generated_metadata(obj, object_id, f"furniture/{room_type}", [material_key])
    obj["furniture_room_type"] = room_type
    return obj


def _root(definition: FurnitureDef, collection: bpy.types.Collection) -> bpy.types.Object:
    return utils.create_empty_root(utils.next_object_name(f"FURN_{definition.room_type}_{definition.object_id}"), collection, (0.0, 0.0, 0.0))


def _finalize(root: bpy.types.Object, parts: list[bpy.types.Object], definition: FurnitureDef, context: FurnitureBuildContext, location, rotation_z) -> bpy.types.Object:
    for part in parts:
        if part.type == "MESH":
            _maybe_bevel(part, context)
    utils.parent_parts(root, parts)
    root.location = location
    root.rotation_euler = utils.Euler((0.0, 0.0, rotation_z))
    utils.set_generated_metadata(root, definition.object_id, f"furniture/{definition.room_type}", utils.list_unique_region_names(parts))
    root["furniture_room_type"] = definition.room_type
    root["furniture_label"] = definition.label
    root["footprint_width"] = definition.footprint[0]
    root["footprint_depth"] = definition.footprint[1]
    context.created_objects.append(root)
    context.created_objects.extend(parts)
    return root


def _maybe_bevel(obj: bpy.types.Object, context: FurnitureBuildContext) -> None:
    if not getattr(context.settings, "apply_bevels", True) or obj.type != "MESH":
        return
    detail = getattr(context.settings, "detail_level", "MEDIUM")
    amount = {"LOW": 0.008, "MEDIUM": 0.014, "HIGH": 0.02}.get(detail, 0.014)
    segments = {"LOW": 1, "MEDIUM": 1, "HIGH": 2}.get(detail, 1)
    utils.add_bevel_modifier(obj, amount, segments)


def _box(context, name, size, loc, mat, definition, rot=(0.0, 0.0, 0.0)):
    return _part(utils.create_box(name, context.collection, size, loc, rot), context, mat, definition.object_id, definition.room_type)


def _cyl(context, name, radius, depth, loc, mat, definition, vertices=10, rot=(0.0, 0.0, 0.0)):
    obj = _part(utils.create_cylinder(name, context.collection, radius, depth, vertices, loc, rot), context, mat, definition.object_id, definition.room_type)
    utils.shade_smooth_safe(obj)
    return obj


def _cone(context, name, r1, r2, depth, loc, mat, definition, vertices=10, rot=(0.0, 0.0, 0.0)):
    obj = _part(utils.create_cone(name, context.collection, r1, r2, depth, vertices, loc, rot), context, mat, definition.object_id, definition.room_type)
    utils.shade_smooth_safe(obj)
    return obj


def _panel(context, name, size, loc, mat, definition, rot=(0.0, 0.0, 0.0)):
    return _part(utils.create_panel_plane(name, context.collection, size, loc, rot), context, mat, definition.object_id, definition.room_type)


def _pipe(context, name, start, end, radius, mat, definition, vertices=8):
    obj = _part(utils.create_pipe_between_points(name, context.collection, start, end, radius, vertices), context, mat, definition.object_id, definition.room_type)
    utils.shade_smooth_safe(obj)
    return obj


def _cabinet_parts(context, root, definition, size=(1.0, 0.45, 1.0), body="wood_dark", top="wood_light", glass=False):
    sx, sy, sz = size
    parts = [
        _box(context, f"{root.name}_body", size, (0, 0, sz * 0.5), body, definition),
        _box(context, f"{root.name}_top", (sx * 1.03, sy * 1.03, 0.05), (0, 0, sz + 0.025), top, definition),
    ]
    door_mat = "glass_blue" if glass else "wood_light"
    for x in (-sx * 0.25, sx * 0.25):
        parts.append(_box(context, f"{root.name}_door_{x:.1f}", (sx * 0.42, 0.025, sz * 0.75), (x, sy * 0.515, sz * 0.52), door_mat, definition))
        parts.append(_box(context, f"{root.name}_handle_{x:.1f}", (0.035, 0.03, sz * 0.28), (x + sx * 0.14, sy * 0.545, sz * 0.55), "painted_metal_gray", definition))
    return parts


def _table_parts(context, root, definition, size=(1.2, 0.75, 0.72), mat="wood_light"):
    sx, sy, sz = size
    parts = [_box(context, f"{root.name}_top", (sx, sy, 0.08), (0, 0, sz), mat, definition)]
    for x in (-sx * 0.38, sx * 0.38):
        for y in (-sy * 0.34, sy * 0.34):
            parts.append(_box(context, f"{root.name}_leg_{x:.1f}_{y:.1f}", (0.07, 0.07, sz), (x, y, sz * 0.5), "wood_dark", definition))
    return parts


def _chair_parts(context, root, definition, prefix="chair"):
    parts = [
        _box(context, f"{root.name}_{prefix}_seat", (0.46, 0.44, 0.08), (0, 0, 0.46), "wood_light", definition),
        _box(context, f"{root.name}_{prefix}_back", (0.48, 0.08, 0.62), (0, -0.22, 0.76), "wood_dark", definition),
    ]
    for x in (-0.18, 0.18):
        for y in (-0.16, 0.16):
            parts.append(_box(context, f"{root.name}_{prefix}_leg_{x:.1f}_{y:.1f}", (0.045, 0.045, 0.46), (x, y, 0.23), "wood_dark", definition))
    return parts


def _screen_parts(context, root, definition, size=(1.1, 0.08, 0.68), stand=True):
    sx, sy, sz = size
    parts = [
        _box(context, f"{root.name}_frame", (sx, sy, sz), (0, 0, sz * 0.5 + 0.55), "dark_plastic", definition),
        _box(context, f"{root.name}_screen", (sx * 0.88, sy * 1.15, sz * 0.78), (0, sy * 0.08, sz * 0.5 + 0.55), "screen_dark", definition),
    ]
    if stand:
        parts.extend([
            _box(context, f"{root.name}_neck", (0.08, 0.08, 0.38), (0, 0, 0.35), "dark_plastic", definition),
            _box(context, f"{root.name}_base", (0.45, 0.28, 0.06), (0, 0, 0.03), "dark_plastic", definition),
        ])
    return parts


def _shelf_contents(context, root, definition, shelf_w, y, z_values, books=True):
    parts = []
    for shelf_index, z in enumerate(z_values):
        x = -shelf_w * 0.38
        item = 0
        while x < shelf_w * 0.38:
            width = context.rng.uniform(0.08, 0.16)
            height = context.rng.uniform(0.18, 0.36) if books else context.rng.uniform(0.16, 0.28)
            mat = context.rng.choice(["fabric_blue", "fabric_brown", "wood_light", "painted_metal_gray"])
            parts.append(_box(context, f"{root.name}_item_{shelf_index}_{item}", (width, 0.08, height), (x, y, z + height * 0.5), mat, definition))
            x += width + 0.035
            item += 1
    return parts


def _build_sofa_like(context, root, definition, wide=2.0, chair=False):
    fabric = context.rng.choice(["fabric_blue", "fabric_brown"])
    parts = [
        _box(context, f"{root.name}_base", (wide, 0.78, 0.28), (0, 0, 0.32), fabric, definition),
        _box(context, f"{root.name}_back", (wide, 0.18, 0.72), (0, -0.34, 0.62), fabric, definition),
        _box(context, f"{root.name}_arm_l", (0.18, 0.82, 0.55), (-wide * 0.5 + 0.09, 0, 0.48), fabric, definition),
        _box(context, f"{root.name}_arm_r", (0.18, 0.82, 0.55), (wide * 0.5 - 0.09, 0, 0.48), fabric, definition),
        _box(context, f"{root.name}_front_strip", (wide * 0.86, 0.035, 0.06), (0, 0.41, 0.46), "dark_plastic", definition),
    ]
    for x in (-wide * 0.36, wide * 0.36):
        parts.append(_box(context, f"{root.name}_pillow_{x:.1f}", (0.36, 0.14, 0.28), (x, -0.2, 0.72), "fabric_brown" if fabric == "fabric_blue" else "fabric_blue", definition))
    for x in (-wide * 0.38, wide * 0.38):
        for y in (-0.25, 0.25):
            parts.append(_box(context, f"{root.name}_leg_{x:.1f}_{y:.1f}", (0.07, 0.07, 0.16), (x, y, 0.08), "wood_dark", definition))
    if chair:
        parts.append(_box(context, f"{root.name}_single_cushion", (wide * 0.62, 0.62, 0.08), (0, 0.08, 0.5), "fabric_brown", definition))
    return parts


def _build_bed(context, root, definition):
    parts = [
        _box(context, f"{root.name}_frame", (2.05, 1.32, 0.22), (0, 0, 0.22), "wood_dark", definition),
        _box(context, f"{root.name}_mattress", (1.92, 1.18, 0.22), (0, 0.02, 0.44), "ceramic_white", definition),
        _box(context, f"{root.name}_blanket", (1.35, 1.12, 0.08), (0.18, 0.05, 0.61), "fabric_blue", definition),
        _box(context, f"{root.name}_pillow_l", (0.42, 0.42, 0.12), (-0.45, -0.36, 0.66), "ceramic_white", definition),
        _box(context, f"{root.name}_pillow_r", (0.42, 0.42, 0.12), (0.45, -0.36, 0.66), "ceramic_white", definition),
        _box(context, f"{root.name}_headboard", (2.1, 0.14, 0.8), (0, -0.7, 0.52), "wood_dark", definition),
    ]
    return parts


def _build_fridge(context, root, definition, medical=False):
    parts = [
        _box(context, f"{root.name}_body", (0.68, 0.62, 1.82), (0, 0, 0.91), "painted_metal_white", definition),
        _box(context, f"{root.name}_top_door", (0.62, 0.035, 0.62), (0, 0.33, 1.46), "painted_metal_white", definition),
        _box(context, f"{root.name}_bottom_door", (0.62, 0.035, 1.02), (0, 0.33, 0.72), "painted_metal_white", definition),
        _box(context, f"{root.name}_handle_top", (0.035, 0.05, 0.42), (0.26, 0.36, 1.42), "painted_metal_gray", definition),
        _box(context, f"{root.name}_handle_bottom", (0.035, 0.05, 0.62), (0.26, 0.36, 0.72), "painted_metal_gray", definition),
        _box(context, f"{root.name}_label", (0.22, 0.04, 0.16), (-0.17, 0.36, 1.55), "medical_red" if medical else "label_panel", definition),
    ]
    return parts


def _build_sink(context, root, definition):
    return [
        _box(context, f"{root.name}_cabinet", (0.82, 0.52, 0.72), (0, 0, 0.36), "painted_metal_white", definition),
        _box(context, f"{root.name}_counter", (0.88, 0.58, 0.08), (0, 0, 0.76), "painted_metal_gray", definition),
        _box(context, f"{root.name}_basin", (0.44, 0.34, 0.055), (0, 0.02, 0.82), "glass_blue", definition),
        _pipe(context, f"{root.name}_faucet_v", (0.22, -0.08, 0.82), (0.22, -0.08, 1.05), 0.018, "painted_metal_gray", definition),
        _pipe(context, f"{root.name}_faucet_h", (0.22, -0.08, 1.05), (0.05, 0.05, 1.05), 0.016, "painted_metal_gray", definition),
    ]


def _build_shelf(context, root, definition, size=(1.2, 0.36, 1.65), books=True):
    sx, sy, sz = size
    parts = [
        _box(context, f"{root.name}_left", (0.06, sy, sz), (-sx * 0.5, 0, sz * 0.5), "wood_dark", definition),
        _box(context, f"{root.name}_right", (0.06, sy, sz), (sx * 0.5, 0, sz * 0.5), "wood_dark", definition),
        _box(context, f"{root.name}_back", (sx, 0.04, sz), (0, -sy * 0.48, sz * 0.5), "wood_dark", definition),
    ]
    z_values = [0.28, 0.68, 1.08, 1.48]
    for idx, z in enumerate(z_values):
        parts.append(_box(context, f"{root.name}_shelf_{idx}", (sx, sy, 0.045), (0, 0, z), "wood_light", definition))
    parts.extend(_shelf_contents(context, root, definition, sx, sy * 0.08, z_values[:-1], books))
    return parts


def _build_stove(context, root, definition):
    parts = [
        _box(context, f"{root.name}_body", (0.68, 0.58, 0.74), (0, 0, 0.37), "painted_metal_gray", definition),
        _box(context, f"{root.name}_oven", (0.5, 0.035, 0.36), (0, 0.31, 0.36), "screen_dark", definition),
    ]
    for x in (-0.18, 0.18):
        for y in (-0.15, 0.14):
            parts.append(_cyl(context, f"{root.name}_burner_{x:.1f}_{y:.1f}", 0.085, 0.025, (x, y, 0.77), "dark_plastic", definition, 12))
    for x in (-0.2, 0.0, 0.2):
        parts.append(_cyl(context, f"{root.name}_knob_{x:.1f}", 0.035, 0.035, (x, 0.33, 0.62), "dark_plastic", definition, 8, (math.radians(90), 0, 0)))
    return parts


def _build_toilet(context, root, definition):
    return [
        _box(context, f"{root.name}_base", (0.36, 0.42, 0.36), (0, 0.08, 0.18), "ceramic_white", definition),
        _cyl(context, f"{root.name}_bowl", 0.28, 0.22, (0, 0.1, 0.43), "ceramic_white", definition, 14, (math.radians(90), 0, 0)),
        _box(context, f"{root.name}_seat", (0.42, 0.34, 0.045), (0, 0.14, 0.56), "ceramic_white", definition),
        _box(context, f"{root.name}_tank", (0.52, 0.18, 0.42), (0, -0.28, 0.66), "ceramic_white", definition),
        _box(context, f"{root.name}_flush", (0.12, 0.025, 0.04), (0.16, -0.38, 0.86), "painted_metal_gray", definition),
    ]


def _build_barrel_group(context, root, definition):
    parts = []
    for index, x in enumerate((-0.24, 0.24)):
        parts.append(_cyl(context, f"{root.name}_barrel_{index}", 0.22, 0.72, (x, 0, 0.36), "painted_metal_gray", definition, 12))
        parts.append(_cyl(context, f"{root.name}_ring_{index}_a", 0.225, 0.035, (x, 0, 0.18), "dark_plastic", definition, 12))
        parts.append(_cyl(context, f"{root.name}_ring_{index}_b", 0.225, 0.035, (x, 0, 0.56), "dark_plastic", definition, 12))
    return parts


def _build_ladder(context, root, definition):
    parts = [
        _pipe(context, f"{root.name}_rail_l", (-0.22, 0, 0), (-0.22, 0, 1.65), 0.022, "painted_metal_gray", definition),
        _pipe(context, f"{root.name}_rail_r", (0.22, 0, 0), (0.22, 0, 1.65), 0.022, "painted_metal_gray", definition),
    ]
    for index in range(7):
        z = 0.18 + index * 0.22
        parts.append(_pipe(context, f"{root.name}_rung_{index}", (-0.2, 0, z), (0.2, 0, z), 0.018, "painted_metal_gray", definition))
    return parts


def _build_cable_spool(context, root, definition):
    return [
        _cyl(context, f"{root.name}_left_disc", 0.3, 0.06, (-0.22, 0, 0.36), "wood_dark", definition, 14, (0, math.radians(90), 0)),
        _cyl(context, f"{root.name}_right_disc", 0.3, 0.06, (0.22, 0, 0.36), "wood_dark", definition, 14, (0, math.radians(90), 0)),
        _cyl(context, f"{root.name}_core", 0.16, 0.48, (0, 0, 0.36), "rubber_black", definition, 14, (0, math.radians(90), 0)),
        _cyl(context, f"{root.name}_hub", 0.07, 0.54, (0, 0, 0.36), "painted_metal_gray", definition, 10, (0, math.radians(90), 0)),
    ]


def _build_generic(context, root, definition):
    oid = definition.object_id
    if oid in {"sofa", "canteen_sofa"}:
        return _build_sofa_like(context, root, definition, 2.0)
    if oid == "armchair":
        return _build_sofa_like(context, root, definition, 0.95, True)
    if oid in {"coffee_table", "dining_table", "large_table"}:
        return _table_parts(context, root, definition, (1.1 if oid == "coffee_table" else 1.55, 0.62 if oid == "coffee_table" else 0.85, 0.46 if oid == "coffee_table" else 0.74))
    if oid in {"tv_screen", "wall_screen"}:
        return _screen_parts(context, root, definition, (1.28, 0.06, 0.72), stand=oid == "tv_screen")
    if oid in {"bookshelf", "archive_shelf", "sample_shelf", "metal_shelving"}:
        return _build_shelf(context, root, definition, (1.2, 0.38, 1.65), books=oid != "metal_shelving")
    if oid in {"small_cabinet", "dresser", "shoe_cabinet", "utility_cabinet", "file_cabinet", "tool_cabinet", "cleaning_cabinet", "material_safe"}:
        return _cabinet_parts(context, root, definition, (definition.footprint[0], definition.footprint[1], 0.85 if oid not in {"utility_cabinet", "tool_cabinet", "cleaning_cabinet"} else 1.45), "wood_dark" if oid != "material_safe" else "painted_metal_gray")
    if oid in {"floor_lamp", "desk_lamp", "table_lamp", "wall_lamp", "exam_lamp"}:
        h = 1.6 if oid == "floor_lamp" else 0.72
        parts = [_cyl(context, f"{root.name}_base", 0.12, 0.04, (0, 0, 0.02), "dark_plastic", definition), _pipe(context, f"{root.name}_pole", (0, 0, 0.04), (0, 0, h), 0.018, "painted_metal_gray", definition)]
        parts.append(_cone(context, f"{root.name}_shade", 0.16, 0.09, 0.18, (0, 0, h + 0.05), "warning_yellow", definition, 10))
        return parts
    if oid in {"wall_shelf", "towel_rack", "wall_pipe"}:
        parts = [_box(context, f"{root.name}_bar", (definition.footprint[0], 0.06, 0.06), (0, 0, 1.2), "painted_metal_gray", definition)]
        if oid == "wall_shelf":
            parts.extend(_shelf_contents(context, root, definition, definition.footprint[0], 0.04, [1.25], books=True))
        return parts
    if oid in {"rug", "small_rug"}:
        return [_box(context, f"{root.name}_rug", (definition.footprint[0], definition.footprint[1], 0.025), (0, 0, 0.012), "fabric_brown", definition)]
    if oid in {"decor_crate", "storage_trunk", "cardboard_boxes", "plastic_crates"}:
        parts = []
        count = 4 if oid in {"cardboard_boxes", "plastic_crates"} else 1
        for index in range(count):
            x = (index % 2) * 0.42 - 0.21 if count > 1 else 0
            y = (index // 2) * 0.34 - 0.17 if count > 1 else 0
            z = 0.18 + (index // 2) * 0.26 if count > 1 else 0.22
            mat = "wood_light" if oid != "plastic_crates" else "fabric_blue"
            parts.append(_box(context, f"{root.name}_box_{index}", (0.38, 0.3, 0.32), (x, y, z), mat, definition))
        return parts
    if oid == "bed":
        return _build_bed(context, root, definition)
    if oid == "bedside_table":
        parts = _cabinet_parts(context, root, definition, (0.46, 0.4, 0.52), "wood_dark")
        parts.extend(_build_generic(context, root, FurnitureDef("desk_lamp", definition.room_type, definition.label, definition.footprint)))
        return parts
    if oid == "wardrobe":
        return _cabinet_parts(context, root, definition, (1.3, 0.52, 1.85), "wood_dark")
    if oid in {"wall_mirror", "mirror_cabinet"}:
        return [_box(context, f"{root.name}_frame", (0.64, 0.04, 0.82), (0, 0, 1.25), "painted_metal_gray", definition), _box(context, f"{root.name}_mirror", (0.52, 0.045, 0.68), (0, 0.02, 1.25), "glass_blue", definition)]
    if oid in {"fridge", "canteen_fridge", "medicine_fridge"}:
        return _build_fridge(context, root, definition, medical=oid == "medicine_fridge")
    if oid in {"kitchen_counter", "sink_cabinet", "medical_sink", "bath_sink", "tea_station", "utility_workbench", "lab_workbench"}:
        parts = _cabinet_parts(context, root, definition, (definition.footprint[0], definition.footprint[1], 0.78), "painted_metal_white", "painted_metal_gray")
        if "sink" in oid:
            parts.extend(_build_sink(context, root, definition)[2:])
        if oid in {"lab_workbench", "utility_workbench", "tea_station"}:
            parts.append(_box(context, f"{root.name}_toolbox", (0.35, 0.22, 0.2), (-0.35, 0.05, 0.95), "warning_yellow" if oid == "lab_workbench" else "dark_plastic", definition))
        return parts
    if oid == "stove":
        return _build_stove(context, root, definition)
    if oid in {"microwave", "canteen_microwave", "coffee_machine", "radio_unit", "analyzer_device", "generator_box"}:
        sx, sy = definition.footprint
        parts = [_box(context, f"{root.name}_body", (sx, sy, 0.45 if oid != "generator_box" else 0.75), (0, 0, 0.42), "painted_metal_gray", definition)]
        parts.append(_box(context, f"{root.name}_screen", (sx * 0.42, 0.035, 0.22), (-sx * 0.14, sy * 0.52, 0.46), "screen_dark" if oid != "analyzer_device" else "screen_green", definition))
        parts.append(_box(context, f"{root.name}_buttons", (sx * 0.22, 0.04, 0.28), (sx * 0.28, sy * 0.53, 0.46), "label_panel", definition))
        parts.append(_box(context, f"{root.name}_slot", (sx * 0.55, 0.035, 0.06), (0, sy * 0.54, 0.22), "dark_plastic", definition))
        return parts
    if oid in {"simple_chair", "medical_chair", "office_chair"}:
        parts = _chair_parts(context, root, definition)
        if oid == "office_chair":
            parts.append(_cyl(context, f"{root.name}_center_pole", 0.035, 0.42, (0, 0, 0.25), "painted_metal_gray", definition))
        return parts
    if oid in {"water_machine", "water_dispenser"}:
        return [_box(context, f"{root.name}_body", (0.42, 0.36, 1.1), (0, 0, 0.55), "painted_metal_white", definition), _cyl(context, f"{root.name}_bottle", 0.18, 0.38, (0, 0, 1.28), "glass_blue", definition, 12), _box(context, f"{root.name}_taps", (0.2, 0.04, 0.08), (0, 0.2, 0.8), "screen_dark", definition)]
    if oid in {"trash_bin", "bath_trash_bin"}:
        return [_cyl(context, f"{root.name}_body", 0.19, 0.45, (0, 0, 0.225), "dark_plastic", definition, 10), _cyl(context, f"{root.name}_lid", 0.2, 0.04, (0, 0, 0.47), "painted_metal_gray", definition, 10)]
    if oid == "toilet":
        return _build_toilet(context, root, definition)
    if oid == "shower_cabin":
        return [_box(context, f"{root.name}_tray", (0.9, 0.9, 0.08), (0, 0, 0.04), "ceramic_white", definition), _box(context, f"{root.name}_glass_l", (0.04, 0.86, 1.55), (-0.43, 0, 0.82), "glass_blue", definition), _box(context, f"{root.name}_glass_b", (0.86, 0.04, 1.55), (0, -0.43, 0.82), "glass_blue", definition), _pipe(context, f"{root.name}_pipe", (0.32, -0.38, 0.25), (0.32, -0.38, 1.45), 0.018, "painted_metal_gray", definition), _cyl(context, f"{root.name}_head", 0.08, 0.05, (0.25, -0.38, 1.42), "painted_metal_gray", definition, 10, (0, math.radians(90), 0))]
    if oid == "bathtub":
        return [_box(context, f"{root.name}_tub", (1.6, 0.72, 0.48), (0, 0, 0.24), "ceramic_white", definition), _box(context, f"{root.name}_inner", (1.25, 0.46, 0.05), (0, 0, 0.5), "glass_blue", definition), _pipe(context, f"{root.name}_faucet", (0.62, -0.2, 0.48), (0.62, 0.05, 0.62), 0.018, "painted_metal_gray", definition)]
    if oid == "washing_machine":
        return [_box(context, f"{root.name}_body", (0.62, 0.58, 0.82), (0, 0, 0.41), "painted_metal_white", definition), _cyl(context, f"{root.name}_door", 0.18, 0.04, (0, 0.31, 0.45), "glass_blue", definition, 14, (math.radians(90), 0, 0)), _box(context, f"{root.name}_panel", (0.5, 0.04, 0.12), (0, 0.31, 0.74), "label_panel", definition)]
    if oid == "coat_rack":
        parts = [_box(context, f"{root.name}_rail", (0.75, 0.05, 0.06), (0, 0, 1.35), "wood_dark", definition)]
        for x in (-0.25, 0, 0.25):
            parts.append(_pipe(context, f"{root.name}_hook_{x:.1f}", (x, 0, 1.34), (x + 0.06, 0.14, 1.25), 0.012, "painted_metal_gray", definition))
            parts.append(_box(context, f"{root.name}_coat_{x:.1f}", (0.18, 0.035, 0.42), (x, 0.07, 1.03), "fabric_brown", definition))
        return parts
    if oid == "bench":
        return _table_parts(context, root, definition, (1.2, 0.34, 0.45), "wood_light")
    if oid in {"wall_terminal", "notice_board", "note_board", "first_aid_box", "emergency_button", "map_board"}:
        mat = "medical_red" if oid in {"first_aid_box", "emergency_button"} else "label_panel"
        parts = [_box(context, f"{root.name}_panel", (definition.footprint[0], 0.04, 0.58 if definition.footprint[0] > 0.5 else 0.32), (0, 0, 1.25), mat, definition)]
        if oid in {"notice_board", "note_board", "map_board"}:
            for i, x in enumerate((-0.22, 0.0, 0.22)):
                parts.append(_box(context, f"{root.name}_paper_{i}", (0.16, 0.045, 0.18), (x, 0.03, 1.28), "ceramic_white", definition))
        return parts
    if oid == "medical_couch":
        return [_box(context, f"{root.name}_pad", (1.65, 0.58, 0.16), (0.08, 0, 0.68), "fabric_blue", definition), _box(context, f"{root.name}_head_angled", (0.55, 0.58, 0.12), (-0.72, 0, 0.78), "fabric_blue", definition, (0, math.radians(12), 0)), _box(context, f"{root.name}_frame", (1.8, 0.62, 0.08), (0, 0, 0.52), "painted_metal_gray", definition)] + [_box(context, f"{root.name}_leg_{i}", (0.05, 0.05, 0.52), (x, y, 0.26), "painted_metal_gray", definition) for i, (x, y) in enumerate([(-0.7, -0.22), (-0.7, 0.22), (0.7, -0.22), (0.7, 0.22)])]
    if oid == "medical_cabinet":
        return _cabinet_parts(context, root, definition, (0.85, 0.42, 1.65), "painted_metal_white", "painted_metal_gray", glass=True)
    if oid == "doctor_desk" or oid == "office_desk":
        parts = _table_parts(context, root, definition, (1.25, 0.68, 0.74), "wood_light")
        parts.append(_box(context, f"{root.name}_papers", (0.34, 0.24, 0.025), (-0.32, 0.12, 0.8), "ceramic_white", definition))
        parts.extend(_screen_parts(context, root, definition, (0.45, 0.04, 0.28), True))
        return parts
    if oid == "privacy_screen":
        parts = []
        for index, x in enumerate((-0.48, 0, 0.48)):
            parts.append(_box(context, f"{root.name}_panel_{index}", (0.45, 0.035, 1.25), (x, 0, 0.7), "fabric_blue", definition, (0, 0, math.radians((index - 1) * 10))))
        return parts
    if oid == "oxygen_cylinder":
        return [_cyl(context, f"{root.name}_body", 0.16, 1.0, (0, 0, 0.5), "glass_blue", definition, 12), _cone(context, f"{root.name}_cap", 0.16, 0.08, 0.14, (0, 0, 1.07), "painted_metal_gray", definition, 12), _box(context, f"{root.name}_valve", (0.16, 0.08, 0.08), (0, 0, 1.18), "dark_plastic", definition)]
    if oid == "health_monitor":
        return _screen_parts(context, root, definition, (0.42, 0.06, 0.32), True) + [_box(context, f"{root.name}_wave", (0.22, 0.04, 0.035), (0, 0.04, 0.73), "screen_green", definition)]
    if oid == "lab_terminal":
        return _screen_parts(context, root, definition, (0.6, 0.06, 0.42), True) + [_box(context, f"{root.name}_keyboard", (0.48, 0.22, 0.035), (0, 0.28, 0.08), "dark_plastic", definition)]
    if oid == "sealed_container":
        return [_cyl(context, f"{root.name}_jar", 0.2, 0.42, (0, 0, 0.21), "glass_blue", definition, 12), _cyl(context, f"{root.name}_cap", 0.21, 0.05, (0, 0, 0.45), "warning_yellow", definition, 12), _box(context, f"{root.name}_label", (0.18, 0.03, 0.12), (0, 0.2, 0.25), "label_panel", definition)]
    if oid == "air_sensor":
        return [_pipe(context, f"{root.name}_pole", (0, 0, 0), (0, 0, 1.15), 0.018, "painted_metal_gray", definition), _box(context, f"{root.name}_sensor", (0.22, 0.16, 0.16), (0, 0, 1.22), "painted_metal_white", definition)]
    if oid == "glove_box":
        return [_box(context, f"{root.name}_chamber", (1.05, 0.55, 0.55), (0, 0, 0.65), "glass_blue", definition), _cyl(context, f"{root.name}_port_l", 0.09, 0.05, (-0.22, 0.3, 0.62), "dark_plastic", definition, 10, (math.radians(90), 0, 0)), _cyl(context, f"{root.name}_port_r", 0.09, 0.05, (0.22, 0.3, 0.62), "dark_plastic", definition, 10, (math.radians(90), 0, 0)), _box(context, f"{root.name}_base", (1.1, 0.62, 0.34), (0, 0, 0.17), "painted_metal_white", definition)]
    if oid == "exhaust_hood":
        return [_box(context, f"{root.name}_base", (1.1, 0.62, 0.8), (0, 0, 0.4), "painted_metal_white", definition), _cone(context, f"{root.name}_hood", 0.55, 0.26, 0.38, (0, 0, 1.05), "painted_metal_gray", definition, 4), _cyl(context, f"{root.name}_pipe", 0.13, 0.65, (0, 0, 1.55), "painted_metal_gray", definition, 10), _box(context, f"{root.name}_grille", (0.6, 0.035, 0.18), (0, 0.33, 0.78), "vent_grille", definition)]
    if oid == "chair_set":
        parts = _table_parts(context, root, definition, (1.0, 0.7, 0.72), "wood_light")
        for i, (x, y) in enumerate([(-0.75, 0), (0.75, 0), (0, -0.65), (0, 0.65)]):
            sub = FurnitureDef("simple_chair", definition.room_type, definition.label, definition.footprint)
            for p in _chair_parts(context, root, sub, f"chairset_{i}"):
                p.location.x += x
                p.location.y += y
                parts.append(p)
        return parts
    if oid == "vending_machine":
        parts = [_box(context, f"{root.name}_body", (0.75, 0.55, 1.8), (0, 0, 0.9), "painted_metal_gray", definition), _box(context, f"{root.name}_glass", (0.46, 0.04, 1.1), (-0.12, 0.3, 1.05), "glass_blue", definition), _box(context, f"{root.name}_buttons", (0.16, 0.045, 0.62), (0.26, 0.31, 1.0), "label_panel", definition), _box(context, f"{root.name}_slot", (0.35, 0.045, 0.1), (0, 0.31, 0.28), "dark_plastic", definition)]
        for i in range(6):
            parts.append(_box(context, f"{root.name}_product_{i}", (0.11, 0.04, 0.12), (-0.27 + (i % 3) * 0.15, 0.27, 0.8 + (i // 3) * 0.24), context.rng.choice(["fabric_blue", "fabric_brown", "warning_yellow"]), definition))
        return parts
    if oid == "communication_terminal" or oid == "control_console":
        return [_box(context, f"{root.name}_base", (definition.footprint[0], definition.footprint[1], 0.55), (0, 0, 0.28), "painted_metal_gray", definition), _box(context, f"{root.name}_panel", (definition.footprint[0] * 0.82, 0.08, 0.42), (0, 0.22, 0.68), "dark_plastic", definition, (math.radians(-18), 0, 0)), _box(context, f"{root.name}_screen", (0.36, 0.04, 0.2), (-0.2, 0.25, 0.72), "screen_green", definition), _box(context, f"{root.name}_buttons", (0.42, 0.04, 0.16), (0.25, 0.25, 0.66), "label_panel", definition)]
    if oid == "music_speaker":
        return [_box(context, f"{root.name}_cabinet", (0.34, 0.3, 0.78), (0, 0, 0.39), "dark_plastic", definition), _cyl(context, f"{root.name}_woofer", 0.11, 0.035, (0, 0.17, 0.28), "vent_grille", definition, 12, (math.radians(90), 0, 0)), _cyl(context, f"{root.name}_tweeter", 0.07, 0.035, (0, 0.17, 0.58), "vent_grille", definition, 10, (math.radians(90), 0, 0))]
    if oid == "barrels":
        return _build_barrel_group(context, root, definition)
    if oid == "ladder":
        return _build_ladder(context, root, definition)
    if oid == "spare_pipes":
        parts = []
        for i, z in enumerate((0.08, 0.18, 0.28)):
            parts.append(_pipe(context, f"{root.name}_pipe_{i}", (-0.62, 0, z), (0.62, 0, z), 0.045, "painted_metal_gray", definition, 10))
        return parts
    if oid == "cable_spool":
        return _build_cable_spool(context, root, definition)
    if oid == "document_stack":
        return [_box(context, f"{root.name}_paper_{i}", (0.38, 0.28, 0.018), (0, 0, 0.018 + i * 0.02), "ceramic_white", definition, (0, 0, math.radians(i * 3))) for i in range(5)]
    return _cabinet_parts(context, root, definition, (definition.footprint[0], definition.footprint[1], 0.85), "painted_metal_gray")


def build_furniture_object(context: FurnitureBuildContext, object_id: str, location=(0.0, 0.0, 0.0), rotation_z=0.0, scale=1.0) -> bpy.types.Object:
    definition = FURNITURE_BY_ID[object_id]
    root = _root(definition, context.collection)
    parts = _build_generic(context, root, definition)
    if abs(scale - 1.0) > 1e-6:
        for part in parts:
            part.scale = (scale, scale, scale)
    return _finalize(root, parts, definition, context, location, rotation_z)


def weighted_choice(rng: random.Random, definitions: list[FurnitureDef]) -> FurnitureDef:
    total = sum(max(0.01, definition.weight) for definition in definitions)
    threshold = rng.uniform(0.0, total)
    running = 0.0
    for definition in definitions:
        running += max(0.01, definition.weight)
        if running >= threshold:
            return definition
    return definitions[-1]


def register():
    pass


def unregister():
    pass

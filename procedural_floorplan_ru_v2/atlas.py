from __future__ import annotations

import json
from pathlib import Path

import bpy


ATLAS_CATEGORIES = [
    ("walls", "walls", "Обычные стены"),
    ("windows", "windows", "Оконные рамы"),
    ("glass", "glass", "Стекло"),
    ("wall_doors", "wall_doors", "Стены с дверями"),
    ("outside_doors", "outside_doors", "Внешние двери"),
    ("inside_doors", "inside_doors", "Межкомнатные двери"),
    ("floors", "floors", "Полы"),
    ("roofs", "roofs", "Крыши"),
    ("roof_borders", "roof_borders", "Бортики крыши"),
    ("floor_bands", "floor_bands", "Межэтажные балки"),
    ("railings", "railings", "Перила"),
    ("stairs", "stairs", "Ступени"),
    ("stair_landings", "stair_landings", "Лестничные площадки"),
]


def _abs_path(path_str: str) -> str:
    if not path_str:
        return ""
    try:
        return bpy.path.abspath(path_str)
    except Exception:
        return path_str


def default_manifest() -> dict:
    return {
        "meta": {
            "atlas_width": 1024,
            "atlas_height": 1024,
            "source_image": "//house_atlas.png",
            "style": "anime_modern_house",
            "random_pick": True,
            "version": 1,
        },
        "walls": [
            {"id": "wall_01", "x": 0, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_02", "x": 256, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
        ],
        "windows": [
            {"id": "window_01", "x": 512, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 1.25},
        ],
        "glass": [
            {"id": "glass_01", "x": 512, "y": 256, "w": 512, "h": 256, "tile_width_m": 2.0, "tile_height_m": 3.0},
        ],
        "wall_doors": [
            {"id": "wall_door_01", "x": 0, "y": 512, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
        ],
        "outside_doors": [
            {"id": "outside_door_01", "x": 0, "y": 512, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 2.0},
        ],
        "inside_doors": [
            {"id": "inside_door_01", "x": 256, "y": 512, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 2.0},
        ],
        "floors": [
            {"id": "floor_01", "x": 0, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0},
            {"id": "floor_02", "x": 256, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0},
        ],
        "roofs": [
            {"id": "roof_01", "x": 512, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0},
        ],
        "roof_borders": [
            {"id": "roof_border_01", "x": 0, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 0.2},
        ],
        "floor_bands": [
            {"id": "floor_band_01", "x": 256, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 0.1},
        ],
        "railings": [
            {"id": "railing_01", "x": 512, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 1.0},
        ],
        "stairs": [
            {"id": "stair_01", "x": 768, "y": 512, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0},
        ],
        "stair_landings": [
            {"id": "landing_01", "x": 768, "y": 640, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0},
        ],
        "placement": {
            "glass": {"offset_x": 0.0, "offset_y": 0.0, "width_scale": 1.0, "height_scale": 1.0},
            "wall_doors": {"offset_x": 0.0, "offset_y": 0.0, "width_scale": 1.0, "height_scale": 1.0},
            "outside_doors": {"offset_x": 0.0, "offset_y": 0.0, "width_scale": 1.0, "height_scale": 1.0},
            "inside_doors": {"offset_x": 0.0, "offset_y": 0.0, "width_scale": 1.0, "height_scale": 1.0},
        },
    }


def write_default_manifest(path_str: str) -> dict:
    path = Path(_abs_path(path_str))
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = default_manifest()
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def load_manifest_from_props(props):
    path = Path(_abs_path(props.atlas_manifest_path))
    if not path.exists():
        return None, path
    return json.loads(path.read_text(encoding="utf-8")), path


def save_manifest_to_props(props, manifest: dict):
    path = Path(_abs_path(props.atlas_manifest_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def manifest_from_settings(settings, persist_default_manifest: bool = True) -> dict | None:
    if not settings.atlas_enabled:
        return None
    path = Path(_abs_path(settings.atlas_manifest_path))
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if persist_default_manifest:
        return write_default_manifest(settings.atlas_manifest_path)
    return default_manifest()


def _ensure_placement(manifest: dict):
    placement = manifest.setdefault("placement", {})
    for key in ("glass", "wall_windows", "wall_doors", "outside_doors", "inside_doors"):
        cfg = placement.setdefault(key, {})
        cfg.setdefault("offset_x", 0.0)
        cfg.setdefault("offset_y", 0.0)
        cfg.setdefault("width_scale", 1.0)
        cfg.setdefault("height_scale", 1.0)
    return placement


def category_items(_self=None, _context=None):
    return ATLAS_CATEGORIES


def tile_items(self, _context):
    manifest_json = getattr(self, "atlas_manifest_json", "")
    if not manifest_json:
        return [("", "Нет данных", "Сначала загрузите manifest.json")]
    try:
        manifest = json.loads(manifest_json)
    except Exception:
        return [("", "Ошибка JSON", "Не удалось разобрать manifest")]
    category = getattr(self, "atlas_category", "walls")
    entries = manifest.get(category, [])
    if not entries:
        return [("", "Нет тайлов", f"В категории {category} нет тайлов")]
    return [
        (str(index), f"{index}: {entry.get('id', f'tile_{index}')}", str(entry.get("id", f"tile_{index}")))
        for index, entry in enumerate(entries)
    ]


def sync_editor_from_manifest(props):
    manifest_json = getattr(props, "atlas_manifest_json", "")
    if not manifest_json:
        return
    props.atlas_sync_lock = True
    try:
        manifest = json.loads(manifest_json)
        category = props.atlas_category
        entries = manifest.get(category, [])
        if not entries:
            props.atlas_tile = ""
            props.atlas_tile_id = ""
            props.atlas_x = props.atlas_y = props.atlas_w = props.atlas_h = 0
            props.atlas_tile_width_m = 1.0
            props.atlas_tile_height_m = 1.0
        else:
            idx = max(0, min(int(props.atlas_tile or 0), len(entries) - 1))
            entry = entries[idx]
            props.atlas_tile = str(idx)
            props.atlas_tile_id = str(entry.get("id", f"tile_{idx}"))
            props.atlas_x = int(entry.get("x", 0))
            props.atlas_y = int(entry.get("y", 0))
            props.atlas_w = int(entry.get("w", 0))
            props.atlas_h = int(entry.get("h", 0))
            props.atlas_tile_width_m = float(entry.get("tile_width_m", 1.0))
            props.atlas_tile_height_m = float(entry.get("tile_height_m", 1.0))

        placement = _ensure_placement(manifest)
        window_cfg = placement.get("glass") or placement.get("wall_windows") or {}
        door_cfg = placement.get("outside_doors") or placement.get("inside_doors") or placement.get("wall_doors") or {}
        props.atlas_window_offset_x = float(window_cfg.get("offset_x", 0.0))
        props.atlas_window_offset_y = float(window_cfg.get("offset_y", 0.0))
        props.atlas_window_width_scale = float(window_cfg.get("width_scale", 1.0))
        props.atlas_window_height_scale = float(window_cfg.get("height_scale", 1.0))
        props.atlas_door_offset_x = float(door_cfg.get("offset_x", 0.0))
        props.atlas_door_offset_y = float(door_cfg.get("offset_y", 0.0))
        props.atlas_door_width_scale = float(door_cfg.get("width_scale", 1.0))
        props.atlas_door_height_scale = float(door_cfg.get("height_scale", 1.0))
    finally:
        props.atlas_sync_lock = False


def apply_editor_to_manifest(props):
    manifest_json = getattr(props, "atlas_manifest_json", "")
    if not manifest_json:
        raise RuntimeError("Manifest не загружен")
    manifest = json.loads(manifest_json)
    category = props.atlas_category
    entries = manifest.setdefault(category, [])
    if not entries:
        entries.append({"id": props.atlas_tile_id or f"{category}_0"})
        props.atlas_tile = "0"
    idx = max(0, min(int(props.atlas_tile or 0), len(entries) - 1))
    entry = entries[idx]
    entry["id"] = props.atlas_tile_id or entry.get("id") or f"{category}_{idx}"
    entry["x"] = int(props.atlas_x)
    entry["y"] = int(props.atlas_y)
    entry["w"] = int(props.atlas_w)
    entry["h"] = int(props.atlas_h)
    entry["tile_width_m"] = float(props.atlas_tile_width_m)
    entry["tile_height_m"] = float(props.atlas_tile_height_m)

    placement = _ensure_placement(manifest)
    placement["glass"] = {
        "offset_x": float(props.atlas_window_offset_x),
        "offset_y": float(props.atlas_window_offset_y),
        "width_scale": float(props.atlas_window_width_scale),
        "height_scale": float(props.atlas_window_height_scale),
    }
    placement["wall_doors"] = {
        "offset_x": float(props.atlas_door_offset_x),
        "offset_y": float(props.atlas_door_offset_y),
        "width_scale": float(props.atlas_door_width_scale),
        "height_scale": float(props.atlas_door_height_scale),
    }
    placement["outside_doors"] = dict(placement["wall_doors"])
    placement["inside_doors"] = dict(placement["wall_doors"])
    props.atlas_manifest_json = json.dumps(manifest, ensure_ascii=False)
    return manifest


def build_atlas_runtime(settings, manifest: dict | None) -> dict:
    if not manifest:
        return {}
    meta = manifest.get("meta", {})
    return {
        "manifest": manifest,
        "atlas_width": int(meta.get("atlas_width", 1024)),
        "atlas_height": int(meta.get("atlas_height", 1024)),
        "image_path": settings.atlas_image_path or meta.get("source_image", ""),
        "random_pick": bool(meta.get("random_pick", settings.atlas_random_pick)),
        "categories": {
            "walls": manifest.get("walls", []),
            "windows": manifest.get("windows", manifest.get("walls", [])),
            "glass": manifest.get("glass", manifest.get("wall_windows", [])),
            "wall_doors": manifest.get("wall_doors", []),
            "outside_doors": manifest.get("outside_doors", manifest.get("wall_doors", [])),
            "inside_doors": manifest.get("inside_doors", manifest.get("wall_doors", [])),
            "floors": manifest.get("floors", []),
            "roofs": manifest.get("roofs", []),
            "roof_borders": manifest.get("roof_borders", manifest.get("walls", [])),
            "floor_bands": manifest.get("floor_bands", manifest.get("walls", [])),
            "railings": manifest.get("railings", manifest.get("walls", [])),
            "stairs": manifest.get("stairs", []),
            "stair_landings": manifest.get("stair_landings", []),
        },
    }


def _load_atlas_image(image_path: str):
    abs_path = _abs_path(image_path)
    if not abs_path or not Path(abs_path).exists():
        return None
    for img in bpy.data.images:
        if bpy.path.abspath(img.filepath) == abs_path:
            return img
    try:
        return bpy.data.images.load(abs_path)
    except Exception:
        return None


def _ensure_atlas_material(mat_name: str, image):
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    node_tree = mat.node_tree
    for node in list(node_tree.nodes):
        node_tree.nodes.remove(node)
    out = node_tree.nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (80, 0)
    tex = node_tree.nodes.new(type="ShaderNodeTexImage")
    tex.location = (-260, 0)
    tex.image = image
    node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.blend_method = "CLIP"
    return mat


def _assign_uv_to_bbox(obj, region, atlas_w, atlas_h):
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="AtlasUV")
    uv_layer = mesh.uv_layers.active.data

    min_u = region["x"] / atlas_w
    max_u = (region["x"] + region["w"]) / atlas_w
    min_v = 1.0 - (region["y"] + region["h"]) / atlas_h
    max_v = 1.0 - region["y"] / atlas_h

    def remap(value, source_min, source_max, target_min, target_max):
        if abs(source_max - source_min) < 1e-8:
            return (target_min + target_max) * 0.5
        factor = (value - source_min) / (source_max - source_min)
        return target_min + (target_max - target_min) * factor

    def polygon_axes(polygon):
        nx = abs(polygon.normal.x)
        ny = abs(polygon.normal.y)
        nz = abs(polygon.normal.z)
        if nz >= nx and nz >= ny:
            return "x", "y"
        if nx >= ny:
            return "y", "z"
        return "x", "z"

    for polygon in mesh.polygons:
        primary_axis, secondary_axis = polygon_axes(polygon)
        polygon_vertices = [mesh.vertices[mesh.loops[loop_index].vertex_index].co for loop_index in polygon.loop_indices]
        primary_values = [getattr(vertex, primary_axis) for vertex in polygon_vertices]
        secondary_values = [getattr(vertex, secondary_axis) for vertex in polygon_vertices]
        min_primary, max_primary = min(primary_values), max(primary_values)
        min_secondary, max_secondary = min(secondary_values), max(secondary_values)
        for loop_index in polygon.loop_indices:
            vert = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            u = remap(getattr(vert, primary_axis), min_primary, max_primary, min_u, max_u)
            v = remap(getattr(vert, secondary_axis), min_secondary, max_secondary, min_v, max_v)
            uv_layer[loop_index].uv = (u, v)


def _pick_region(entries: list[dict], *, random_pick: bool, seed_value: int, salt: str):
    if not entries:
        return None
    if len(entries) == 1 or not random_pick:
        return entries[0]
    index = abs(hash(f"{seed_value}:{salt}")) % len(entries)
    return entries[index]


def resolve_floor_tile_id(context) -> str:
    manifest = context.atlas_manifest or {}
    floor_entries = manifest.get("floors", [])
    props = context.scene.floorplan_ru_v2_settings
    if props.atlas_category == "floors" and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if floor_entries:
        return str(floor_entries[0].get("id", ""))
    return ""


def resolve_wall_tile_id(context) -> str:
    """Подбирает id тайла стен для новых wall-объектов.

    Как это работает:
    если пользователь сейчас редактирует категорию `walls` и явно выбрал
    конкретный тайл, берётся именно он. Иначе используется первый тайл
    из категории `walls` в manifest, чтобы новый builder оставался совместимым
    с atlas pipeline даже без отдельной сложной логики выбора.
    """
    manifest = context.atlas_manifest or {}
    wall_entries = manifest.get("walls", [])
    props = context.scene.floorplan_ru_v2_settings
    if props.atlas_category == "walls" and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if wall_entries:
        return str(wall_entries[0].get("id", ""))
    return ""


def resolve_window_tile_id(context) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    window_entries = manifest.get("windows", manifest.get("walls", []))
    if props.atlas_category == "windows" and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if window_entries:
        return str(window_entries[0].get("id", ""))
    return ""


def resolve_door_tile_id(context, door_type: str) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    category = "outside_doors" if door_type in {"entry", "external_stair"} else "inside_doors"
    entries = manifest.get(category, manifest.get("wall_doors", []))
    if props.atlas_category == category and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if entries:
        return str(entries[0].get("id", ""))
    return ""


def resolve_border_tile_id(context, border_type: str) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    category = "floor_bands" if border_type == "floor_band" else "roof_borders"
    entries = manifest.get(category, manifest.get("walls", []))
    if props.atlas_category == category and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if entries:
        return str(entries[0].get("id", ""))
    return ""


def resolve_roof_tile_id(context) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    entries = manifest.get("roofs", [])
    if props.atlas_category == "roofs" and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if entries:
        return str(entries[0].get("id", ""))
    return ""


def resolve_railing_tile_id(context) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    entries = manifest.get("railings", manifest.get("walls", []))
    if props.atlas_category == "railings" and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if entries:
        return str(entries[0].get("id", ""))
    return ""


def resolve_stair_tile_id(context, part: str) -> str:
    manifest = context.atlas_manifest or {}
    props = context.scene.floorplan_ru_v2_settings
    category = "stair_landings" if part == "landing" else "stairs"
    entries = manifest.get(category, [])
    if props.atlas_category == category and props.atlas_tile_id:
        return str(props.atlas_tile_id)
    if entries:
        return str(entries[0].get("id", ""))
    return ""


def _resolve_region_for_object(obj, atlas_data: dict, seed_value: int):
    category = str(obj.get("atlas_category", ""))
    if not category:
        return None, None
    entries = atlas_data.get("categories", {}).get(category, [])
    if not entries:
        return category, None
    tile_id = str(obj.get("atlas_tile_id", ""))
    if tile_id:
        for entry in entries:
            if str(entry.get("id", "")) == tile_id:
                return category, entry
    random_pick = atlas_data.get("random_pick", True)
    return category, _pick_region(entries, random_pick=random_pick, seed_value=seed_value, salt=obj.name)


def apply_atlas_to_collection(context) -> None:
    atlas_data = context.atlas_data
    if not atlas_data:
        return
    image = _load_atlas_image(atlas_data.get("image_path", ""))
    if image is None:
        return
    atlas_w = atlas_data["atlas_width"]
    atlas_h = atlas_data["atlas_height"]
    mat_cache = {}

    def material_for(category: str):
        if category not in mat_cache:
            mat_cache[category] = _ensure_atlas_material(f"Atlas_{category}", image)
        return mat_cache[category]

    from .common.utils import iter_collection_objects_recursive

    for obj in iter_collection_objects_recursive(context.collection):
        if obj.type != "MESH":
            continue
        category, region = _resolve_region_for_object(obj, atlas_data, context.settings.seed)
        if not category or not region:
            continue
        if obj.get("uv_baked") or obj.get("atlas_baked"):
            if not obj.data.materials:
                obj.data.materials.append(material_for(category))
            continue
        obj.data.materials.clear()
        obj.data.materials.append(material_for(category))
        _assign_uv_to_bbox(obj, region, atlas_w, atlas_h)


classes = ()


def register():
    pass


def unregister():
    pass

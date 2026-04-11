import json
from pathlib import Path

import bpy

from . import core

ATLAS_CATEGORIES = [
    ("walls", "walls", "Обычные стены"),
    ("glass", "glass", "Стекло"),
    ("wall_doors", "wall_doors", "Стены с дверями"),
    ("floors", "floors", "Полы"),
    ("roofs", "roofs", "Крыши"),
    ("roof_borders", "roof_borders", "Бортики крыши"),
    ("floor_bands", "floor_bands", "Межэтажные балки"),
    ("stairs", "stairs", "Ступени"),
    ("stair_landings", "stair_landings", "Лестничные площадки"),
]

CATEGORY_IDS = [c[0] for c in ATLAS_CATEGORIES]


def _abs_path(path_str: str) -> Path:
    return Path(core._atlas_abs(path_str))


def load_manifest_from_props(props):
    path = _abs_path(props.atlas_manifest_path)
    if not path.exists():
        return None, path
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, path


def save_manifest_to_props(props, manifest: dict):
    path = _abs_path(props.atlas_manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _ensure_placement(manifest: dict):
    placement = manifest.setdefault("placement", {})
    for key in ("glass", "wall_windows", "wall_doors"):
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
    items = []
    for idx, entry in enumerate(entries):
        tile_id = str(entry.get("id", f"tile_{idx}"))
        label = f"{idx}: {tile_id}"
        items.append((str(idx), label, tile_id))
    return items


def sync_editor_from_manifest(props):
    manifest_json = getattr(props, "atlas_manifest_json", "")
    if not manifest_json:
        return
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
        try:
            idx = int(props.atlas_tile)
        except Exception:
            idx = 0
        idx = max(0, min(idx, len(entries) - 1))
        props.atlas_tile = str(idx)
        entry = entries[idx]
        props.atlas_tile_id = str(entry.get("id", f"tile_{idx}"))
        props.atlas_x = int(entry.get("x", 0))
        props.atlas_y = int(entry.get("y", 0))
        props.atlas_w = int(entry.get("w", 0))
        props.atlas_h = int(entry.get("h", 0))
        props.atlas_tile_width_m = float(entry.get("tile_width_m", 1.0))
        props.atlas_tile_height_m = float(entry.get("tile_height_m", 1.0))

    placement = _ensure_placement(manifest)
    ww = placement.get("glass") or placement.get("wall_windows") or {"offset_x": 0.0, "offset_y": 0.0, "width_scale": 1.0, "height_scale": 1.0}
    wd = placement["wall_doors"]
    props.atlas_window_offset_x = float(ww.get("offset_x", 0.0))
    props.atlas_window_offset_y = float(ww.get("offset_y", 0.0))
    props.atlas_window_width_scale = float(ww.get("width_scale", 1.0))
    props.atlas_window_height_scale = float(ww.get("height_scale", 1.0))
    props.atlas_door_offset_x = float(wd.get("offset_x", 0.0))
    props.atlas_door_offset_y = float(wd.get("offset_y", 0.0))
    props.atlas_door_width_scale = float(wd.get("width_scale", 1.0))
    props.atlas_door_height_scale = float(wd.get("height_scale", 1.0))


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
    idx = int(props.atlas_tile or 0)
    idx = max(0, min(idx, len(entries) - 1))
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

    props.atlas_manifest_json = json.dumps(manifest, ensure_ascii=False)
    return manifest

from __future__ import annotations

import json
from pathlib import Path

import bpy

from . import utils


DEFAULT_MANIFEST = {
    "atlas": "rooftop_yard_atlas.png",
    "version": 1,
    "tileSize": 128,
    "atlas_width": 1024,
    "atlas_height": 1024,
    "regions": {
        "metal_light": {"x": 0, "y": 0, "w": 128, "h": 128},
        "metal_dark": {"x": 128, "y": 0, "w": 128, "h": 128},
        "paint_white": {"x": 256, "y": 0, "w": 128, "h": 128},
        "paint_red": {"x": 384, "y": 0, "w": 128, "h": 128},
        "rubber_black": {"x": 512, "y": 0, "w": 128, "h": 128},
        "solar_panel": {"x": 0, "y": 128, "w": 256, "h": 128},
        "fan_grille": {"x": 256, "y": 128, "w": 128, "h": 128},
        "vent_louver": {"x": 384, "y": 128, "w": 128, "h": 128},
        "warning_label": {"x": 512, "y": 128, "w": 64, "h": 64},
        "hazard_stripes": {"x": 576, "y": 128, "w": 128, "h": 64},
        "chainlink": {"x": 0, "y": 256, "w": 128, "h": 128},
        "glass_light": {"x": 128, "y": 256, "w": 128, "h": 128},
        "lamp_glow": {"x": 256, "y": 256, "w": 128, "h": 128},
        "speaker_dark": {"x": 384, "y": 256, "w": 128, "h": 128},
        "concrete_base": {"x": 512, "y": 256, "w": 128, "h": 128},
    },
}


def _abs_path(path_str: str) -> str:
    if not path_str:
        return ""
    try:
        return bpy.path.abspath(path_str)
    except Exception:
        return path_str


def addon_asset_path(filename: str) -> str:
    return str(utils.addon_dir() / "assets" / filename)


def default_manifest() -> dict:
    return json.loads(json.dumps(DEFAULT_MANIFEST))


def write_default_manifest(path_str: str) -> dict:
    path = Path(_abs_path(path_str))
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = default_manifest()
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def validate_manifest(manifest: dict) -> tuple[bool, str]:
    if not isinstance(manifest, dict):
        return False, "Manifest должен быть объектом JSON"
    if "regions" not in manifest or not isinstance(manifest["regions"], dict):
        return False, "Manifest должен содержать regions"
    atlas_width = int(manifest.get("atlas_width", 0))
    atlas_height = int(manifest.get("atlas_height", 0))
    if atlas_width <= 0 or atlas_height <= 0:
        return False, "atlas_width и atlas_height должны быть больше нуля"
    for name, region in manifest["regions"].items():
        if not isinstance(region, dict):
            return False, f"Регион {name} должен быть объектом"
        for key in ("x", "y", "w", "h"):
            if key not in region:
                return False, f"Регион {name} не содержит {key}"
            if int(region[key]) < 0:
                return False, f"Регион {name} содержит отрицательный {key}"
        if int(region["w"]) <= 0 or int(region["h"]) <= 0:
            return False, f"Регион {name} должен иметь положительные размеры"
    return True, ""


def load_manifest_from_props(props):
    path = Path(_abs_path(props.manifest_path))
    if not path.exists():
        return None, path
    manifest = json.loads(path.read_text(encoding="utf-8"))
    valid, message = validate_manifest(manifest)
    if not valid:
        raise RuntimeError(message)
    return manifest, path


def save_manifest_to_props(props, manifest: dict):
    valid, message = validate_manifest(manifest)
    if not valid:
        raise RuntimeError(message)
    path = Path(_abs_path(props.manifest_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def region_items(self, _context):
    manifest_json = getattr(self, "manifest_json", "")
    if not manifest_json:
        return [("", "Нет данных", "Сначала загрузите manifest")]
    try:
        manifest = json.loads(manifest_json)
    except Exception:
        return [("", "Ошибка JSON", "Не удалось прочитать manifest")]
    regions = manifest.get("regions", {})
    if not regions:
        return [("", "Пусто", "В manifest нет regions")]
    return [(name, name, f"Регион {name}") for name in sorted(regions.keys())]


def sync_editor_from_manifest(props):
    if not getattr(props, "manifest_json", ""):
        return
    props.manifest_sync_lock = True
    try:
        manifest = json.loads(props.manifest_json)
        regions = manifest.get("regions", {})
        names = sorted(regions.keys())
        if not names:
            props.manifest_region = ""
            props.region_x = props.region_y = props.region_w = props.region_h = 0
            return
        if props.manifest_region not in regions:
            props.manifest_region = names[0]
        region = regions[props.manifest_region]
        props.region_x = int(region.get("x", 0))
        props.region_y = int(region.get("y", 0))
        props.region_w = int(region.get("w", 0))
        props.region_h = int(region.get("h", 0))
        props.atlas_width = int(manifest.get("atlas_width", 1024))
        props.atlas_height = int(manifest.get("atlas_height", 1024))
    finally:
        props.manifest_sync_lock = False


def apply_editor_to_manifest(props):
    manifest_json = getattr(props, "manifest_json", "")
    if not manifest_json:
        raise RuntimeError("Manifest не загружен")
    manifest = json.loads(manifest_json)
    manifest["atlas_width"] = int(props.atlas_width)
    manifest["atlas_height"] = int(props.atlas_height)
    regions = manifest.setdefault("regions", {})
    region_name = props.manifest_region or "metal_light"
    regions.setdefault(region_name, {})
    regions[region_name]["x"] = int(props.region_x)
    regions[region_name]["y"] = int(props.region_y)
    regions[region_name]["w"] = int(props.region_w)
    regions[region_name]["h"] = int(props.region_h)
    valid, message = validate_manifest(manifest)
    if not valid:
        raise RuntimeError(message)
    props.manifest_json = json.dumps(manifest, ensure_ascii=False)
    return manifest


def manifest_from_settings(settings, persist_default_manifest: bool = True) -> dict:
    path = Path(_abs_path(settings.manifest_path))
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        valid, message = validate_manifest(manifest)
        if not valid:
            raise RuntimeError(message)
        return manifest
    if persist_default_manifest:
        return write_default_manifest(settings.manifest_path)
    return default_manifest()


def get_region(manifest: dict, region_name: str) -> dict | None:
    return (manifest or {}).get("regions", {}).get(region_name)


def build_runtime(settings, manifest: dict) -> dict:
    atlas_path = settings.atlas_image_path
    if not atlas_path:
        atlas_path = str(Path(_abs_path(settings.manifest_path)).with_name(manifest.get("atlas", "rooftop_yard_atlas.png")))
    return {
        "manifest": manifest,
        "atlas_width": int(manifest.get("atlas_width", 1024)),
        "atlas_height": int(manifest.get("atlas_height", 1024)),
        "image_path": atlas_path,
        "regions": manifest.get("regions", {}),
    }


classes = ()


def register():
    pass


def unregister():
    pass

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import bpy


@dataclass(frozen=True)
class DecalEntry:
    id: str
    x: int
    y: int
    w: int
    h: int
    tile_width_m: float
    tile_height_m: float
    kind: str


@dataclass(frozen=True)
class DecalRuntime:
    manifest_path: str
    image_path: str
    atlas_width: int
    atlas_height: int
    streak_entries: tuple[DecalEntry, ...]


def load_decal_runtime(settings) -> DecalRuntime | None:
    manifest_path = str(getattr(settings, "decal_manifest_path", "") or "").strip()
    if not manifest_path:
        print("[Decal] Empty decal manifest path, skipping decal generation.")
        return None

    resolved_manifest_path = _resolve_path(manifest_path, base_dir=None)
    if resolved_manifest_path is None or not resolved_manifest_path.exists():
        print(f"[Decal] Manifest not found: {manifest_path}")
        return None

    try:
        manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[Decal] Failed to read manifest '{resolved_manifest_path}': {exc}")
        return None

    if not isinstance(manifest, dict):
        print(f"[Decal] Manifest '{resolved_manifest_path}' is not a JSON object.")
        return None

    meta = manifest.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    atlas_width = _int_or_default(meta.get("atlas_width"), default=0)
    atlas_height = _int_or_default(meta.get("atlas_height"), default=0)
    if atlas_width <= 0 or atlas_height <= 0:
        print(f"[Decal] Manifest '{resolved_manifest_path}' has invalid atlas size.")
        return None

    source_image = str(meta.get("source_image", "") or "").strip()
    image_value = str(getattr(settings, "decal_image_path", "") or "").strip() or source_image
    resolved_image_path = _resolve_path(image_value, base_dir=resolved_manifest_path.parent)
    if resolved_image_path is None or not resolved_image_path.exists():
        print(f"[Decal] Image not found: {image_value or source_image}")
        return None

    streak_entries = _load_entries(manifest, meta)
    if not streak_entries:
        print(f"[Decal] Manifest '{resolved_manifest_path}' has no valid streak entries.")
        return None

    return DecalRuntime(
        manifest_path=str(resolved_manifest_path),
        image_path=str(resolved_image_path),
        atlas_width=atlas_width,
        atlas_height=atlas_height,
        streak_entries=tuple(streak_entries),
    )


def ensure_decal_image(runtime: DecalRuntime):
    try:
        return bpy.data.images.load(runtime.image_path, check_existing=True)
    except Exception as exc:
        print(f"[Decal] Failed to load image '{runtime.image_path}': {exc}")
        return None


def ensure_decal_material(image, *, material_name: str = "DecalMaterial") -> bpy.types.Material:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)

    material.use_nodes = True
    node_tree = material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (600, 0)

    mix = nodes.new(type="ShaderNodeMixShader")
    mix.location = (360, 0)

    transparent = nodes.new(type="ShaderNodeBsdfTransparent")
    transparent.location = (120, 120)

    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (120, -40)
    principled.inputs["Roughness"].default_value = 0.95
    principled.inputs["Metallic"].default_value = 0.0

    texture = nodes.new(type="ShaderNodeTexImage")
    texture.location = (-140, 0)
    texture.image = image

    links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    links.new(texture.outputs["Alpha"], mix.inputs["Fac"])
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(principled.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])

    material.blend_method = "BLEND"
    material.shadow_method = "NONE"
    material.use_backface_culling = False
    material.show_transparent_back = True
    return material


def _load_entries(manifest: dict, meta: dict) -> list[DecalEntry]:
    raw_entries = manifest.get("under_roof_drips", manifest.get("streaks", []))
    if not isinstance(raw_entries, list):
        return []

    default_height_m = _float_from_candidates(
        (
            meta.get("under_roof_decal_height_m"),
            meta.get("decal_height_m"),
            manifest.get("under_roof_decal_height_m"),
            manifest.get("decal_height_m"),
        ),
        default=0.25,
    )

    entries: list[DecalEntry] = []
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            continue
        x = _int_or_default(raw_entry.get("x"), default=-1)
        y = _int_or_default(raw_entry.get("y"), default=-1)
        w = _int_or_default(
            raw_entry.get("w", raw_entry.get("width", raw_entry.get("tile_px_w"))),
            default=0,
        )
        h = _int_or_default(
            raw_entry.get("h", raw_entry.get("height", raw_entry.get("tile_px_h"))),
            default=0,
        )
        if min(x, y, w, h) < 0 or w <= 0 or h <= 0:
            continue
        tile_width_m = max(
            0.05,
            _float_from_candidates((raw_entry.get("tile_width_m"),), default=1.0),
        )
        tile_height_m = max(
            0.05,
            _float_from_candidates(
                (
                    raw_entry.get("tile_height_m"),
                    raw_entry.get("decal_height_m"),
                    raw_entry.get("height_m"),
                ),
                default=default_height_m,
            ),
        )
        entries.append(
            DecalEntry(
                id=str(raw_entry.get("id", f"under_roof_{index + 1:02d}")),
                x=x,
                y=y,
                w=w,
                h=h,
                tile_width_m=tile_width_m,
                tile_height_m=tile_height_m,
                kind="under_roof_streak",
            )
        )
    return entries


def _resolve_path(path_value: str, *, base_dir: Path | None) -> Path | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    if raw.startswith("//"):
        return Path(bpy.path.abspath(raw)).expanduser()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if base_dir is not None:
        return (base_dir / path).resolve()
    return path.resolve()


def _int_or_default(value, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _float_from_candidates(candidates, *, default: float) -> float:
    for value in candidates:
        try:
            if value is None:
                continue
            converted = float(value)
            if converted > 0.0:
                return converted
        except Exception:
            continue
    return default

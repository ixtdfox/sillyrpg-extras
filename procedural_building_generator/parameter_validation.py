from __future__ import annotations

import math
from dataclasses import dataclass

from .utils import clamp


MIN_WINDOW_CLEARANCE = 0.5
WINDOW_HEAD_TOP_MARGIN = 0.1
WINDOW_MAX_SILL_MARGIN = 0.8
MIN_FOOTPRINT_M = 8.0
MIN_TILE_SIZE = 0.25
MIN_WALL_THICKNESS = 0.02
MIN_FLOOR_HEIGHT = 1.2
WINDOW_FALLBACK_MIN_HEIGHT = 0.7
SUPPORTED_FLOORS = (1, 3)


@dataclass(frozen=True)
class SanitizedSettings:
    values: dict[str, object]
    warnings: tuple[str, ...]

    def __getattr__(self, item):
        try:
            return self.values[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def sanitize_parameters(settings, fast_mode: bool = False) -> SanitizedSettings:
    values = {}
    warnings: list[str] = []

    def set_default(name: str):
        values[name] = getattr(settings, name)

    passthrough = (
        "facade_module_mode",
        "seed",
        "detail_amount",
        "style_preset",
        "material_palette",
        "wall_tint_variation",
        "dirt_amount",
        "glass_tint_strength",
        "accent_color_strength",
        "balcony_chance",
        "facade_variation",
        "accent_strength",
        "entrance_style",
        "band_density",
        "vertical_fins",
        "roof_style",
        "roof_profile",
        "roof_detail_density",
        "rooftop_equipment_amount",
        "skylight_chance",
        "solar_panel_chance",
        "stair_opening_margin",
        "lot_padding",
        "parapet_thickness",
        "canopy_depth",
        "canopy_width",
        "canopy_height",
        "interactive_preview",
        "preview_detail_scale",
        "rebuild_interval_ms",
        "idle_full_rebuild_ms",
        "auto_rebuild",
        "window_asset",
        "entrance_asset",
        "corner_asset",
        "balcony_asset",
        "rooftop_utility_asset",
        "pb_last_rebuild_quality",
        "pb_timer_pause_reason",
    )
    for name in passthrough:
        set_default(name)

    tile_size = max(float(settings.tile_size), MIN_TILE_SIZE)
    if tile_size != float(settings.tile_size):
        warnings.append(f"tile_size was clamped from {float(settings.tile_size):.3f} to {tile_size:.3f} (must be > 0).")
    values["tile_size"] = tile_size

    min_footprint = max(MIN_FOOTPRINT_M, tile_size * 4.0)
    width_raw = max(float(settings.width_m), min_footprint)
    depth_raw = max(float(settings.depth_m), min_footprint)
    width_tiles = max(4, int(math.ceil(width_raw / tile_size)))
    depth_tiles = max(4, int(math.ceil(depth_raw / tile_size)))
    width = width_tiles * tile_size
    depth = depth_tiles * tile_size
    if width != float(settings.width_m):
        warnings.append(f"width_m was clamped from {float(settings.width_m):.3f} to {width:.3f} (minimum supported footprint / tile aligned).")
    if depth != float(settings.depth_m):
        warnings.append(f"depth_m was clamped from {float(settings.depth_m):.3f} to {depth:.3f} (minimum supported footprint / tile aligned).")
    values["width_m"] = width
    values["depth_m"] = depth

    floors = int(clamp(int(settings.floors), SUPPORTED_FLOORS[0], SUPPORTED_FLOORS[1]))
    if floors != int(settings.floors):
        warnings.append(f"floors was clamped from {int(settings.floors)} to {floors} (supported range {SUPPORTED_FLOORS[0]}-{SUPPORTED_FLOORS[1]}).")
    values["floors"] = floors

    room_count = max(1, int(settings.room_count))
    if room_count != int(settings.room_count):
        warnings.append(f"room_count was clamped from {int(settings.room_count)} to {room_count} (must be >= 1).")
    if fast_mode:
        room_count = max(1, int(round(room_count * 0.5)))
    values["room_count"] = room_count

    floor_height = max(float(settings.floor_height), MIN_FLOOR_HEIGHT)
    if floor_height != float(settings.floor_height):
        warnings.append(f"floor_height was clamped from {float(settings.floor_height):.3f} to {floor_height:.3f} (must be > 0).")
    values["floor_height"] = floor_height

    wall_thickness = max(float(settings.wall_thickness), MIN_WALL_THICKNESS)
    if wall_thickness != float(settings.wall_thickness):
        warnings.append(f"wall_thickness was clamped from {float(settings.wall_thickness):.3f} to {wall_thickness:.3f} (must be > 0).")
    values["wall_thickness"] = wall_thickness

    slab_thickness = min(max(float(settings.slab_thickness), 0.01), max(0.01, floor_height - 0.05))
    if slab_thickness != float(settings.slab_thickness):
        warnings.append(f"slab_thickness was clamped from {float(settings.slab_thickness):.3f} to {slab_thickness:.3f} (must be < floor_height).")
    values["slab_thickness"] = slab_thickness

    door_width = max(float(settings.door_width), 0.1)
    if door_width != float(settings.door_width):
        warnings.append(f"door_width was clamped from {float(settings.door_width):.3f} to {door_width:.3f} (must be > 0).")
    values["door_width"] = door_width

    door_height = min(max(float(settings.door_height), 0.3), floor_height - 0.05)
    if door_height != float(settings.door_height):
        warnings.append(f"door_height was clamped from {float(settings.door_height):.3f} to {door_height:.3f} (must be < floor_height).")
    values["door_height"] = door_height

    values["stairs_rise_step"] = max(float(settings.stairs_rise_step), 0.01)
    if values["stairs_rise_step"] != float(settings.stairs_rise_step):
        warnings.append(f"stairs_rise_step was clamped from {float(settings.stairs_rise_step):.3f} to {values['stairs_rise_step']:.3f} (must be > 0).")
    values["stairs_run_step"] = max(float(settings.stairs_run_step), 0.01)
    if values["stairs_run_step"] != float(settings.stairs_run_step):
        warnings.append(f"stairs_run_step was clamped from {float(settings.stairs_run_step):.3f} to {values['stairs_run_step']:.3f} (must be > 0).")
    values["stairs_width"] = max(float(settings.stairs_width), 0.1)
    if values["stairs_width"] != float(settings.stairs_width):
        warnings.append(f"stairs_width was clamped from {float(settings.stairs_width):.3f} to {values['stairs_width']:.3f} (must be > 0).")

    parapet_height = max(float(settings.parapet_height), 0.0)
    if parapet_height != float(settings.parapet_height):
        warnings.append(f"parapet_height was clamped from {float(settings.parapet_height):.3f} to {parapet_height:.3f} (must be >= 0).")
    values["parapet_height"] = parapet_height

    max_sill = max(0.0, floor_height - WINDOW_MAX_SILL_MARGIN)
    sill = clamp(float(settings.window_sill_h), 0.0, max_sill)
    if sill != float(settings.window_sill_h):
        warnings.append(f"window_sill_h was clamped from {float(settings.window_sill_h):.3f} to {sill:.3f} (must be between 0 and floor_height-{WINDOW_MAX_SILL_MARGIN:.1f}).")

    max_head = max(0.0, floor_height - WINDOW_HEAD_TOP_MARGIN)
    head = clamp(float(settings.window_head_h), 0.0, max_head)
    if head != float(settings.window_head_h):
        warnings.append(f"window_head_h was clamped from {float(settings.window_head_h):.3f} to {head:.3f} (must be <= floor_height-{WINDOW_HEAD_TOP_MARGIN:.1f}).")

    minimum_head = sill + MIN_WINDOW_CLEARANCE
    if head < minimum_head:
        original = head
        head = min(max_head, minimum_head)
        if abs(head - original) > 1e-9:
            warnings.append(f"window_head_h was clamped from {original:.3f} to {head:.3f} (must be > window_sill_h + {MIN_WINDOW_CLEARANCE:.1f}).")
    if sill > max(0.0, head - MIN_WINDOW_CLEARANCE):
        original = sill
        sill = max(0.0, head - MIN_WINDOW_CLEARANCE)
        if abs(sill - original) > 1e-9:
            warnings.append(f"window_sill_h was clamped from {original:.3f} to {sill:.3f} (must keep minimum window clearance).")

    values["window_sill_h"] = sill
    values["window_head_h"] = head
    values["minimum_window_clearance"] = MIN_WINDOW_CLEARANCE
    values["window_overlap"] = 0.015
    values["module_overlap"] = 0.004

    window_valid = (head - sill) >= WINDOW_FALLBACK_MIN_HEIGHT and (head <= max_head + 1e-6)
    values["window_is_valid"] = window_valid
    if not window_valid:
        warnings.append("Window parameters are impossible after clamping; falling back to solid wall modules.")

    for message in warnings:
        print(f"[proc_building][sanitize] {message}")
    return SanitizedSettings(values=values, warnings=tuple(warnings))

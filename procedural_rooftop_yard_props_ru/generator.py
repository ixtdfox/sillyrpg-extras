from __future__ import annotations

import math
import random
from dataclasses import dataclass

import bpy

from . import atlas_manifest, textures, utils


CATEGORY_ITEMS = [
    ("roof_power", "Солнечные панели"),
    ("roof_utilities", "Баки/ёмкости"),
    ("roof_hvac", "HVAC/кондиционеры"),
    ("roof_vents", "Вентиляция"),
    ("communications", "Антенны/связь"),
    ("warning_systems", "Сирены/маяки"),
    ("lighting", "Освещение"),
    ("power_equipment", "Электрооборудование"),
    ("fences", "Заборы/ограждения"),
    ("access", "Лестницы/доступ"),
    ("storage", "Ящики/контейнеры"),
    ("surveillance", "Камеры/датчики"),
    ("special", "Спец-объекты"),
]

CATEGORY_LABELS = dict(CATEGORY_ITEMS)
CATEGORY_ENUM_ITEMS = tuple((key, label, label) for key, label in CATEGORY_ITEMS)


@dataclass(frozen=True)
class PropDef:
    prop_type: str
    category: str
    footprint: tuple[float, float]
    height: float
    allowed_surfaces: tuple[str, ...]
    weight: float = 1.0
    label: str = ""


PROP_DEFS: dict[str, PropDef] = {
    "solar_panel_array": PropDef("solar_panel_array", "roof_power", (2.6, 1.8), 1.2, ("roof",), 1.0, "Solar Array"),
    "water_tank_vertical": PropDef("water_tank_vertical", "roof_utilities", (1.4, 1.4), 2.4, ("roof", "yard"), 0.9, "Water Tank Vertical"),
    "water_tank_horizontal": PropDef("water_tank_horizontal", "roof_utilities", (2.2, 1.2), 1.6, ("roof", "yard"), 0.8, "Water Tank Horizontal"),
    "barrel_small": PropDef("barrel_small", "roof_utilities", (0.7, 0.7), 1.0, ("roof", "yard"), 0.8, "Barrel Small"),
    "hvac_small": PropDef("hvac_small", "roof_hvac", (1.0, 0.6), 0.8, ("roof", "yard"), 1.1, "HVAC Small"),
    "hvac_medium": PropDef("hvac_medium", "roof_hvac", (1.6, 1.0), 1.0, ("roof", "yard"), 1.1, "HVAC Medium"),
    "hvac_large": PropDef("hvac_large", "roof_hvac", (2.4, 1.6), 1.4, ("roof", "yard"), 1.2, "HVAC Large"),
    "vent_box": PropDef("vent_box", "roof_hvac", (1.8, 1.2), 1.4, ("roof",), 0.9, "Vent Box"),
    "air_conditioner": PropDef("air_conditioner", "roof_hvac", (1.0, 0.7), 0.9, ("roof", "yard"), 0.9, "Air Conditioner"),
    "vent_mushroom": PropDef("vent_mushroom", "roof_vents", (0.8, 0.8), 1.0, ("roof",), 1.0, "Vent Mushroom"),
    "vent_pipe": PropDef("vent_pipe", "roof_vents", (0.6, 0.6), 1.2, ("roof",), 1.0, "Vent Pipe"),
    "vent_box_small": PropDef("vent_box_small", "roof_vents", (1.0, 0.8), 0.9, ("roof",), 0.9, "Vent Box Small"),
    "exhaust_cap": PropDef("exhaust_cap", "roof_vents", (0.9, 0.9), 1.1, ("roof",), 0.9, "Exhaust Cap"),
    "radio_tower": PropDef("radio_tower", "communications", (1.6, 1.6), 4.8, ("roof", "yard"), 0.6, "Radio Tower"),
    "antenna_tripod": PropDef("antenna_tripod", "communications", (1.2, 1.2), 2.8, ("roof",), 0.9, "Antenna Tripod"),
    "antenna_cluster": PropDef("antenna_cluster", "communications", (1.0, 1.0), 2.6, ("roof", "yard"), 0.9, "Antenna Cluster"),
    "comm_box_tower": PropDef("comm_box_tower", "communications", (1.3, 1.3), 2.6, ("roof", "yard"), 0.8, "Comm Box Tower"),
    "loudspeaker": PropDef("loudspeaker", "warning_systems", (0.8, 0.8), 1.6, ("roof", "yard"), 0.8, "Loudspeaker"),
    "warning_beacon": PropDef("warning_beacon", "warning_systems", (0.5, 0.5), 1.8, ("roof", "yard"), 0.8, "Warning Beacon"),
    "siren_light": PropDef("siren_light", "warning_systems", (0.8, 0.8), 1.8, ("roof", "yard"), 0.7, "Siren Light"),
    "flood_alarm_unit": PropDef("flood_alarm_unit", "warning_systems", (1.0, 0.8), 1.7, ("roof", "yard"), 0.7, "Flood Alarm Unit"),
    "pole_floodlight": PropDef("pole_floodlight", "lighting", (0.6, 0.6), 2.8, ("roof", "yard"), 0.9, "Pole Floodlight"),
    "portable_floodlight": PropDef("portable_floodlight", "lighting", (0.9, 0.8), 1.0, ("roof", "yard"), 0.8, "Portable Floodlight"),
    "work_light": PropDef("work_light", "lighting", (0.8, 0.8), 1.3, ("roof", "yard"), 0.8, "Work Light"),
    "portable_generator": PropDef("portable_generator", "power_equipment", (1.4, 0.9), 1.0, ("roof", "yard"), 1.0, "Portable Generator"),
    "electrical_cabinet": PropDef("electrical_cabinet", "power_equipment", (1.4, 0.8), 1.7, ("roof", "yard"), 1.0, "Electrical Cabinet"),
    "battery_box": PropDef("battery_box", "power_equipment", (1.0, 0.7), 1.0, ("roof", "yard"), 0.8, "Battery Box"),
    "inverter_box": PropDef("inverter_box", "power_equipment", (0.9, 0.6), 1.0, ("roof", "yard"), 0.8, "Inverter Box"),
    "chainlink_fence": PropDef("chainlink_fence", "fences", (2.4, 0.2), 1.8, ("roof", "yard"), 0.7, "Chainlink Fence"),
    "equipment_cage": PropDef("equipment_cage", "fences", (2.4, 1.8), 2.2, ("roof", "yard"), 0.7, "Equipment Cage"),
    "low_railing": PropDef("low_railing", "fences", (2.0, 0.2), 1.1, ("roof", "yard"), 0.7, "Low Railing"),
    "safety_barrier": PropDef("safety_barrier", "fences", (1.6, 0.4), 1.0, ("roof", "yard"), 0.6, "Safety Barrier"),
    "step_ladder": PropDef("step_ladder", "access", (1.0, 1.2), 1.8, ("roof", "yard"), 0.8, "Step Ladder"),
    "vertical_ladder": PropDef("vertical_ladder", "access", (0.8, 0.2), 3.2, ("roof", "yard"), 0.8, "Vertical Ladder"),
    "service_platform": PropDef("service_platform", "access", (1.8, 1.4), 1.6, ("roof", "yard"), 0.7, "Service Platform"),
    "service_box": PropDef("service_box", "storage", (0.9, 0.7), 0.8, ("roof", "yard"), 0.8, "Service Box"),
    "utility_crate": PropDef("utility_crate", "storage", (1.0, 0.8), 0.9, ("roof", "yard"), 0.8, "Utility Crate"),
    "barrel": PropDef("barrel", "storage", (0.8, 0.8), 1.0, ("roof", "yard"), 0.8, "Barrel"),
    "bin": PropDef("bin", "storage", (0.9, 0.9), 1.1, ("roof", "yard"), 0.8, "Bin"),
    "dome_sensor": PropDef("dome_sensor", "surveillance", (0.6, 0.6), 0.7, ("roof", "yard"), 0.8, "Dome Sensor"),
    "security_camera": PropDef("security_camera", "surveillance", (0.7, 0.4), 0.7, ("roof", "yard"), 0.8, "Security Camera"),
    "sensor_pole": PropDef("sensor_pole", "surveillance", (0.6, 0.6), 1.8, ("roof", "yard"), 0.7, "Sensor Pole"),
    "hazard_sphere_module": PropDef("hazard_sphere_module", "special", (1.4, 1.4), 1.7, ("roof", "yard"), 0.5, "Hazard Sphere Module"),
    "research_beacon": PropDef("research_beacon", "special", (1.0, 1.0), 2.2, ("roof", "yard"), 0.5, "Research Beacon"),
    "sealed_core_container": PropDef("sealed_core_container", "special", (1.5, 1.2), 1.4, ("roof", "yard"), 0.5, "Sealed Core Container"),
}

PROP_TYPE_ENUM_ITEMS = tuple(
    (prop_type, definition.label or prop_type, definition.prop_type)
    for prop_type, definition in PROP_DEFS.items()
)
PROP_TYPE_ENUM_ITEMS_BY_CATEGORY = {
    category: tuple(
        (prop_type, definition.label or prop_type, definition.prop_type)
        for prop_type, definition in PROP_DEFS.items()
        if definition.category == category
    )
    for category, _label in CATEGORY_ITEMS
}


def category_enum_items(_self=None, _context=None):
    return CATEGORY_ENUM_ITEMS


def prop_type_items(self, _context):
    category = getattr(self, "single_category", "")
    items = PROP_TYPE_ENUM_ITEMS_BY_CATEGORY.get(category)
    if items:
        return items
    return PROP_TYPE_ENUM_ITEMS


def enabled_categories_from_props(props) -> list[str]:
    mapping = {
        "roof_power": props.enable_solar_panels,
        "roof_utilities": props.enable_tanks,
        "roof_hvac": props.enable_hvac,
        "roof_vents": props.enable_vents,
        "communications": props.enable_communications,
        "warning_systems": props.enable_warning_systems,
        "lighting": props.enable_lighting,
        "power_equipment": props.enable_power_equipment,
        "fences": props.enable_fences,
        "access": props.enable_access,
        "storage": props.enable_storage,
        "surveillance": props.enable_surveillance,
        "special": props.enable_special,
    }
    return [key for key, enabled in mapping.items() if enabled]


def surface_filtered_props(surface: str, categories: list[str]) -> list[PropDef]:
    return [definition for definition in PROP_DEFS.values() if definition.category in categories and surface in definition.allowed_surfaces]


class PropBuilder:
    prop_type = "base"
    category = "misc"
    footprint = (1.0, 1.0)

    def build(self, context, params):
        raise NotImplementedError


class BuildContext:
    def __init__(self, scene, collection, settings, atlas_runtime, rng):
        self.scene = scene
        self.collection = collection
        self.settings = settings
        self.atlas_runtime = atlas_runtime
        self.rng = rng
        self.created_objects: list[bpy.types.Object] = []


def _part(obj: bpy.types.Object, runtime: dict, region_name: str, prop_type: str, category: str) -> bpy.types.Object:
    textures.apply_material_and_uv(obj, runtime, region_name)
    utils.set_generated_metadata(obj, prop_type, category, [region_name])
    return obj


def _root(prefix: str, collection: bpy.types.Collection, _location: tuple[float, float, float]) -> bpy.types.Object:
    return utils.create_empty_root(utils.next_object_name(prefix), collection, (0.0, 0.0, 0.0))


def _finalize_root(root: bpy.types.Object, parts: list[bpy.types.Object], prop_type: str, category: str, created_objects: list[bpy.types.Object]) -> bpy.types.Object:
    utils.parent_parts(root, parts)
    utils.set_generated_metadata(root, prop_type, category, utils.list_unique_region_names(parts))
    created_objects.append(root)
    created_objects.extend(parts)
    return root


def _maybe_bevel(obj: bpy.types.Object, detail: str, apply_bevels: bool) -> None:
    if not apply_bevels or obj.type != "MESH":
        return
    amount = {"LOW": 0.01, "MEDIUM": 0.02, "HIGH": 0.03}.get(detail, 0.02)
    segments = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(detail, 2)
    utils.add_bevel_modifier(obj, amount=amount, segments=segments)


def _common_panel_label(
    name: str,
    collection: bpy.types.Collection,
    runtime: dict,
    prop_type: str,
    category: str,
    size: tuple[float, float],
    location: tuple[float, float, float],
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    region_name: str = "warning_label",
) -> bpy.types.Object:
    return _part(utils.create_panel_plane(name, collection, size=size, location=location, rotation=rotation), runtime, region_name, prop_type, category)


def build_solar_array(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Solar_Array", context.collection, location)
    parts = []
    panel_count = context.rng.randint(1, 4)
    row_count = context.rng.randint(1, 2)
    tilt_deg = context.rng.uniform(15.0, 28.0)
    spacing = 0.12 * scale
    panel_w = 0.9 * scale
    panel_d = 1.5 * scale
    leg_h = 0.28 * scale
    for row in range(row_count):
        for col in range(panel_count):
            offset_x = (col - (panel_count - 1) * 0.5) * (panel_w + spacing)
            offset_y = (row - (row_count - 1) * 0.5) * (panel_d * 0.95)
            frame = _part(utils.create_box(f"{root.name}_frame_{row}_{col}", context.collection, (panel_w, panel_d, 0.04 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
            frame.location = (offset_x, offset_y, leg_h + 0.45 * scale)
            frame.rotation_euler = utils.Euler((math.radians(tilt_deg), 0.0, rotation_z))
            panel = _part(utils.create_panel_plane(f"{root.name}_panel_{row}_{col}", context.collection, (panel_w * 0.94, panel_d * 0.94)), context.atlas_runtime, "solar_panel", definition.prop_type, definition.category)
            panel.location = (offset_x, offset_y, leg_h + 0.47 * scale)
            panel.rotation_euler = utils.Euler((math.radians(tilt_deg), 0.0, rotation_z))
            parts.extend([frame, panel])
            for side in (-1.0, 1.0):
                leg = _part(utils.create_pipe_between_points(
                    f"{root.name}_leg_{row}_{col}_{int(side)}",
                    context.collection,
                    (offset_x + side * panel_w * 0.38, offset_y - panel_d * 0.32, 0.0),
                    (offset_x + side * panel_w * 0.38, offset_y, leg_h + 0.1 * scale),
                    radius=0.025 * scale,
                ), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
                brace = _part(utils.create_pipe_between_points(
                    f"{root.name}_brace_{row}_{col}_{int(side)}",
                    context.collection,
                    (offset_x + side * panel_w * 0.38, offset_y + panel_d * 0.30, 0.0),
                    (offset_x + side * panel_w * 0.15, offset_y, leg_h + 0.18 * scale),
                    radius=0.02 * scale,
                ), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
                parts.extend([leg, brace])
    box = _part(utils.create_box(f"{root.name}_inverter", context.collection, (0.35 * scale, 0.2 * scale, 0.4 * scale), location=(panel_count * 0.55 * scale, 0.0, 0.2 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
    label = _common_panel_label(f"{root.name}_label", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.12 * scale, 0.08 * scale), (panel_count * 0.55 * scale + 0.18 * scale, 0.0, 0.25 * scale))
    parts.extend([box, label])
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_tank(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Water_Tank", context.collection, location)
    parts = []
    if definition.prop_type == "water_tank_horizontal":
        body = _part(utils.create_cylinder(f"{root.name}_body", context.collection, 0.45 * scale, 1.8 * scale, 14, rotation=(0.0, math.radians(90.0), rotation_z), location=(0.0, 0.0, 0.8 * scale)), context.atlas_runtime, "paint_white", definition.prop_type, definition.category)
        for sign in (-1.0, 1.0):
            support = _part(utils.create_box(f"{root.name}_support_{int(sign)}", context.collection, (0.24 * scale, 0.4 * scale, 0.6 * scale), location=(sign * 0.45 * scale, 0.0, 0.3 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
            parts.append(support)
        hatch = _part(utils.create_cylinder(f"{root.name}_hatch", context.collection, 0.09 * scale, 0.08 * scale, 10, location=(0.0, 0.0, 1.26 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        pipe = _part(utils.create_pipe_between_points(f"{root.name}_pipe", context.collection, (0.65 * scale, 0.0, 0.75 * scale), (1.0 * scale, 0.0, 0.3 * scale), 0.05 * scale), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.extend([body, hatch, pipe])
    else:
        radius = 0.45 * scale if definition.prop_type == "water_tank_vertical" else 0.22 * scale
        depth = 1.8 * scale if definition.prop_type == "water_tank_vertical" else 0.9 * scale
        body_region = "paint_white" if context.rng.random() > 0.35 else "metal_dark"
        body = _part(utils.create_cylinder(f"{root.name}_body", context.collection, radius, depth, 14, location=(0.0, 0.0, depth * 0.5)), context.atlas_runtime, body_region, definition.prop_type, definition.category)
        base = _part(utils.create_cylinder(f"{root.name}_base", context.collection, radius * 1.05, 0.12 * scale, 14, location=(0.0, 0.0, 0.06 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        cap = _part(utils.create_cylinder(f"{root.name}_cap", context.collection, radius * 0.92, 0.08 * scale, 14, location=(0.0, 0.0, depth + 0.04 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        pipe = _part(utils.create_pipe_between_points(f"{root.name}_pipe", context.collection, (radius, 0.0, depth * 0.45), (radius + 0.35 * scale, 0.0, 0.25 * scale), 0.04 * scale), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        cap_small = _part(utils.create_cylinder(f"{root.name}_valve", context.collection, 0.06 * scale, 0.1 * scale, 8, location=(0.0, 0.0, depth + 0.12 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.extend([body, base, cap, pipe, cap_small])
        if definition.prop_type == "water_tank_vertical":
            ladder_left = _part(utils.create_pipe_between_points(f"{root.name}_ladder_l", context.collection, (-radius * 0.45, radius, 0.15 * scale), (-radius * 0.45, radius, depth * 0.9), 0.018 * scale), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
            ladder_right = _part(utils.create_pipe_between_points(f"{root.name}_ladder_r", context.collection, (radius * 0.45, radius, 0.15 * scale), (radius * 0.45, radius, depth * 0.9), 0.018 * scale), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
            parts.extend([ladder_left, ladder_right])
            for index in range(5):
                rung = _part(utils.create_pipe_between_points(
                    f"{root.name}_rung_{index}",
                    context.collection,
                    (-radius * 0.4, radius, 0.3 * scale + index * 0.25 * scale),
                    (radius * 0.4, radius, 0.3 * scale + index * 0.25 * scale),
                    0.015 * scale,
                ), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
                parts.append(rung)
    parts.append(_common_panel_label(f"{root.name}_warning", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.16 * scale, 0.12 * scale), (0.0, 0.46 * scale, 0.75 * scale)))
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_hvac(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_HVAC_Large" if definition.prop_type == "hvac_large" else "RY_HVAC", context.collection, location)
    parts = []
    base_size = {
        "hvac_small": (0.9, 0.55, 0.55),
        "air_conditioner": (0.8, 0.5, 0.55),
        "hvac_medium": (1.4, 0.9, 0.85),
        "vent_box": (1.6, 1.0, 1.2),
        "hvac_large": (2.1, 1.4, 1.1),
    }[definition.prop_type]
    body = _part(utils.create_box(f"{root.name}_body", context.collection, tuple(value * scale for value in base_size), rotation=utils.make_rotation(rotation_z), location=(0.0, 0.0, base_size[2] * 0.5 * scale + 0.15 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
    parts.append(body)
    for sign in (-1.0, 1.0):
        foot = _part(utils.create_box(f"{root.name}_foot_{int(sign)}", context.collection, (0.2 * scale, base_size[1] * 0.85 * scale, 0.18 * scale), rotation=utils.make_rotation(rotation_z), location=(sign * base_size[0] * 0.3 * scale, 0.0, 0.09 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        parts.append(foot)
    grille = _part(utils.create_panel_plane(f"{root.name}_fan_grille", context.collection, (base_size[1] * 0.42 * scale, base_size[1] * 0.42 * scale), location=(base_size[0] * 0.51 * scale, 0.0, base_size[2] * 0.5 * scale + 0.15 * scale), rotation=(0.0, math.radians(90.0), rotation_z)), context.atlas_runtime, "fan_grille", definition.prop_type, definition.category)
    parts.append(grille)
    louver = _part(utils.create_panel_plane(f"{root.name}_louvers", context.collection, (base_size[0] * 0.55 * scale, base_size[2] * 0.45 * scale), location=(0.0, -base_size[1] * 0.51 * scale, base_size[2] * 0.52 * scale + 0.15 * scale), rotation=(math.radians(90.0), 0.0, rotation_z)), context.atlas_runtime, "vent_louver", definition.prop_type, definition.category)
    parts.append(louver)
    panel = _part(utils.create_box(f"{root.name}_service_panel", context.collection, (base_size[0] * 0.25 * scale, 0.04 * scale, base_size[2] * 0.36 * scale), location=(-base_size[0] * 0.15 * scale, base_size[1] * 0.52 * scale, base_size[2] * 0.53 * scale + 0.15 * scale), rotation=utils.make_rotation(rotation_z)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
    parts.append(panel)
    label = _common_panel_label(f"{root.name}_warning", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.14 * scale, 0.1 * scale), (base_size[0] * 0.3 * scale, base_size[1] * 0.53 * scale, base_size[2] * 0.62 * scale + 0.15 * scale))
    parts.append(label)
    if definition.prop_type in {"hvac_large", "vent_box"}:
        for sign in (-1.0, 1.0):
            top_fan = _part(utils.create_panel_plane(f"{root.name}_top_fan_{int(sign)}", context.collection, (0.42 * scale, 0.42 * scale), location=(sign * 0.45 * scale, 0.0, base_size[2] * scale + 0.17 * scale), rotation=(0.0, 0.0, rotation_z)), context.atlas_runtime, "fan_grille", definition.prop_type, definition.category)
            parts.append(top_fan)
        conduit = _part(utils.create_pipe_between_points(f"{root.name}_conduit", context.collection, (-base_size[0] * 0.55 * scale, -base_size[1] * 0.2 * scale, 0.2 * scale), (-base_size[0] * 0.9 * scale, -base_size[1] * 0.2 * scale, 0.2 * scale), 0.04 * scale), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.append(conduit)
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_vent(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Vent", context.collection, location)
    parts = []
    if definition.prop_type == "vent_mushroom":
        stem = _part(utils.create_cylinder(f"{root.name}_stem", context.collection, 0.16 * scale, 0.6 * scale, 12, location=(0.0, 0.0, 0.3 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        cap = _part(utils.create_cone(f"{root.name}_cap", context.collection, 0.36 * scale, 0.24 * scale, 0.22 * scale, 12, location=(0.0, 0.0, 0.72 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        base = _part(utils.create_cylinder(f"{root.name}_base", context.collection, 0.26 * scale, 0.08 * scale, 12, location=(0.0, 0.0, 0.04 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        parts.extend([stem, cap, base])
    elif definition.prop_type == "vent_box_small":
        body = _part(utils.create_box(f"{root.name}_body", context.collection, (0.75 * scale, 0.6 * scale, 0.55 * scale), rotation=utils.make_rotation(rotation_z), location=(0.0, 0.0, 0.28 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        louver = _part(utils.create_panel_plane(f"{root.name}_louvers", context.collection, (0.5 * scale, 0.25 * scale), location=(0.0, 0.31 * scale, 0.3 * scale), rotation=(math.radians(90.0), 0.0, rotation_z)), context.atlas_runtime, "vent_louver", definition.prop_type, definition.category)
        top = _part(utils.create_box(f"{root.name}_top", context.collection, (0.82 * scale, 0.66 * scale, 0.06 * scale), location=(0.0, 0.0, 0.58 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.extend([body, louver, top])
    else:
        pipe = _part(utils.create_cylinder(f"{root.name}_pipe", context.collection, 0.14 * scale, 0.8 * scale, 10, location=(0.0, 0.0, 0.4 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        tip = _part(utils.create_cone(f"{root.name}_tip", context.collection, 0.18 * scale, 0.08 * scale, 0.22 * scale, 10, location=(0.0, 0.0, 0.92 * scale), rotation=(math.radians(25.0) if definition.prop_type == "exhaust_cap" else 0.0, 0.0, rotation_z)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        base = _part(utils.create_cylinder(f"{root.name}_base", context.collection, 0.24 * scale, 0.08 * scale, 10, location=(0.0, 0.0, 0.04 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        parts.extend([pipe, tip, base])
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_antenna(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Antenna_Tower" if definition.prop_type == "radio_tower" else "RY_Antenna", context.collection, location)
    parts = []
    if definition.prop_type == "radio_tower":
        height = 4.6 * scale
        leg_positions = [(-0.45, -0.45), (0.45, -0.45), (-0.45, 0.45), (0.45, 0.45)]
        for x, y in leg_positions:
            leg = _part(utils.create_pipe_between_points(f"{root.name}_leg_{x}_{y}", context.collection, (x * scale, y * scale, 0.0), (x * 0.5 * scale, y * 0.5 * scale, height), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
            parts.append(leg)
        for level in range(1, 6):
            z = level * (height / 6.0)
            braces = [
                ((-0.45, -0.45, z - 0.5 * scale), (0.45, 0.45, z)),
                ((0.45, -0.45, z - 0.5 * scale), (-0.45, 0.45, z)),
            ]
            for start, end in braces:
                brace = _part(utils.create_pipe_between_points(f"{root.name}_brace_{level}", context.collection, tuple(value * scale for value in start), tuple(value * scale for value in end), 0.018 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
                parts.append(brace)
        tip = _part(utils.create_pipe_between_points(f"{root.name}_tip", context.collection, (0.0, 0.0, height), (0.0, 0.0, height + 0.7 * scale), 0.02 * scale, 6), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        light = _part(utils.create_cylinder(f"{root.name}_light", context.collection, 0.05 * scale, 0.09 * scale, 8, location=(0.0, 0.0, height + 0.35 * scale)), context.atlas_runtime, "lamp_glow", definition.prop_type, definition.category)
        parts.extend([tip, light])
    elif definition.prop_type == "comm_box_tower":
        for index in range(3):
            angle = rotation_z + (math.tau / 3.0) * index
            start = (math.cos(angle) * 0.45 * scale, math.sin(angle) * 0.45 * scale, 0.0)
            end = (0.0, 0.0, 1.9 * scale)
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_leg_{index}", context.collection, start, end, 0.025 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        mast = _part(utils.create_pipe_between_points(f"{root.name}_mast", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 2.3 * scale), 0.028 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        box = _part(utils.create_box(f"{root.name}_box", context.collection, (0.6 * scale, 0.45 * scale, 0.55 * scale), location=(0.0, 0.0, 1.6 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        panel = _common_panel_label(f"{root.name}_panel", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.16 * scale, 0.1 * scale), (0.0, 0.24 * scale, 1.65 * scale))
        cable = _part(utils.create_pipe_between_points(f"{root.name}_cable", context.collection, (0.0, 0.0, 1.35 * scale), (0.0, 0.0, 0.1 * scale), 0.012 * scale, 6), context.atlas_runtime, "rubber_black", definition.prop_type, definition.category)
        parts.extend([mast, box, panel, cable])
    else:
        leg_count = 3 if definition.prop_type == "antenna_tripod" else 1
        for index in range(leg_count):
            angle = rotation_z + (math.tau / max(leg_count, 1)) * index
            start = (math.cos(angle) * 0.5 * scale, math.sin(angle) * 0.5 * scale, 0.0)
            end = (0.0, 0.0, 1.9 * scale)
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_leg_{index}", context.collection, start, end, 0.025 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        mast = _part(utils.create_pipe_between_points(f"{root.name}_mast", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 2.4 * scale), 0.028 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.append(mast)
        antenna_count = 4 if definition.prop_type == "antenna_cluster" else 2
        for index in range(antenna_count):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_antenna_{index}", context.collection, (0.0, 0.0, 1.0 * scale + index * 0.25 * scale), (0.0, 0.0, 1.35 * scale + index * 0.25 * scale), 0.012 * scale, 6), context.atlas_runtime, "metal_light", definition.prop_type, definition.category))
    for part in parts:
        if part.type == "MESH":
            utils.shade_smooth_safe(part)
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_warning(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Warning", context.collection, location)
    parts = []
    pole = _part(utils.create_pipe_between_points(f"{root.name}_pole", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 1.4 * scale), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
    parts.append(pole)
    if definition.prop_type == "loudspeaker":
        horn = _part(utils.create_cone(f"{root.name}_horn", context.collection, 0.05 * scale, 0.26 * scale, 0.4 * scale, 12, location=(0.0, 0.22 * scale, 1.2 * scale), rotation=(math.radians(90.0), 0.0, rotation_z)), context.atlas_runtime, "paint_red", definition.prop_type, definition.category)
        back = _part(utils.create_cylinder(f"{root.name}_back", context.collection, 0.08 * scale, 0.2 * scale, 10, location=(0.0, 0.0, 1.2 * scale), rotation=(math.radians(90.0), 0.0, rotation_z)), context.atlas_runtime, "speaker_dark", definition.prop_type, definition.category)
        bracket = _part(utils.create_pipe_between_points(f"{root.name}_bracket", context.collection, (0.0, 0.0, 1.0 * scale), (0.0, 0.08 * scale, 1.15 * scale), 0.015 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.extend([horn, back, bracket])
    elif definition.prop_type == "warning_beacon":
        light = _part(utils.create_cylinder(f"{root.name}_light", context.collection, 0.1 * scale, 0.22 * scale, 10, location=(0.0, 0.0, 1.5 * scale)), context.atlas_runtime, "lamp_glow", definition.prop_type, definition.category)
        ring = _part(utils.create_cylinder(f"{root.name}_ring", context.collection, 0.12 * scale, 0.05 * scale, 10, location=(0.0, 0.0, 1.38 * scale)), context.atlas_runtime, "rubber_black", definition.prop_type, definition.category)
        parts.extend([light, ring])
    else:
        head = _part(utils.create_box(f"{root.name}_head", context.collection, (0.32 * scale, 0.22 * scale, 0.28 * scale), location=(0.0, 0.14 * scale, 1.25 * scale)), context.atlas_runtime, "paint_red" if definition.prop_type == "siren_light" else "metal_dark", definition.prop_type, definition.category)
        lens = _common_panel_label(f"{root.name}_lens", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.18 * scale, 0.14 * scale), (0.0, 0.26 * scale, 1.25 * scale), rotation=(0.0, math.radians(90.0), 0.0), region_name="glass_light")
        bracket = _part(utils.create_pipe_between_points(f"{root.name}_u1", context.collection, (-0.16 * scale, 0.0, 1.05 * scale), (-0.16 * scale, 0.18 * scale, 1.25 * scale), 0.014 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        bracket2 = _part(utils.create_pipe_between_points(f"{root.name}_u2", context.collection, (0.16 * scale, 0.0, 1.05 * scale), (0.16 * scale, 0.18 * scale, 1.25 * scale), 0.014 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.extend([head, lens, bracket, bracket2])
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_light(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Floodlight", context.collection, location)
    parts = []
    if definition.prop_type == "pole_floodlight":
        pole = _part(utils.create_pipe_between_points(f"{root.name}_pole", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 2.3 * scale), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        head = _part(utils.create_box(f"{root.name}_head", context.collection, (0.32 * scale, 0.18 * scale, 0.28 * scale), location=(0.0, 0.18 * scale, 2.18 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        lens = _common_panel_label(f"{root.name}_lens", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.22 * scale, 0.14 * scale), (0.0, 0.28 * scale, 2.18 * scale), rotation=(0.0, math.radians(90.0), 0.0), region_name="lamp_glow")
        parts.extend([pole, head, lens])
    else:
        lamp = _part(utils.create_box(f"{root.name}_lamp", context.collection, (0.38 * scale, 0.16 * scale, 0.28 * scale), location=(0.0, 0.0, 0.5 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        lens = _common_panel_label(f"{root.name}_lens", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.26 * scale, 0.18 * scale), (0.0, 0.09 * scale, 0.5 * scale), rotation=(0.0, math.radians(90.0), 0.0), region_name="glass_light" if definition.prop_type == "portable_floodlight" else "lamp_glow")
        stand = _part(utils.create_pipe_between_points(f"{root.name}_stand", context.collection, (-0.18 * scale, 0.0, 0.15 * scale), (0.18 * scale, 0.0, 0.15 * scale), 0.015 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        legs = [
            _part(utils.create_pipe_between_points(f"{root.name}_leg_l", context.collection, (-0.18 * scale, 0.0, 0.15 * scale), (-0.32 * scale, 0.0, 0.0), 0.015 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category),
            _part(utils.create_pipe_between_points(f"{root.name}_leg_r", context.collection, (0.18 * scale, 0.0, 0.15 * scale), (0.32 * scale, 0.0, 0.0), 0.015 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category),
        ]
        parts.extend([lamp, lens, stand, *legs])
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_power(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Generator" if definition.prop_type == "portable_generator" else "RY_Power", context.collection, location)
    parts = []
    if definition.prop_type == "portable_generator":
        frame_pts = [(-0.55, -0.35, 0.1), (0.55, -0.35, 0.1), (-0.55, 0.35, 0.1), (0.55, 0.35, 0.1)]
        for x, y, z in frame_pts:
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_post_{x}_{y}", context.collection, (x * scale, y * scale, 0.0), (x * scale, y * scale, 0.55 * scale), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        for y in (-0.35, 0.35):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_top_{y}", context.collection, (-0.55 * scale, y * scale, 0.55 * scale), (0.55 * scale, y * scale, 0.55 * scale), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        body = _part(utils.create_box(f"{root.name}_body", context.collection, (0.82 * scale, 0.44 * scale, 0.44 * scale), location=(0.0, 0.0, 0.3 * scale)), context.atlas_runtime, "paint_red" if context.rng.random() > 0.5 else "metal_light", definition.prop_type, definition.category)
        panel = _common_panel_label(f"{root.name}_panel", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.24 * scale, 0.18 * scale), (0.42 * scale, 0.0, 0.3 * scale), rotation=(0.0, math.radians(90.0), 0.0), region_name="warning_label")
        parts.extend([body, panel])
    else:
        body = _part(utils.create_box(f"{root.name}_body", context.collection, (1.0 * scale, 0.65 * scale, 1.1 * scale) if definition.prop_type == "electrical_cabinet" else (0.72 * scale, 0.52 * scale, 0.76 * scale), location=(0.0, 0.0, 0.55 * scale if definition.prop_type == "electrical_cabinet" else 0.38 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.append(body)
        vent = _common_panel_label(f"{root.name}_vent", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.24 * scale, 0.16 * scale), (0.0, 0.33 * scale, body.location.z), rotation=(math.radians(90.0), 0.0, 0.0), region_name="vent_louver")
        label = _common_panel_label(f"{root.name}_label", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.14 * scale, 0.1 * scale), (0.22 * scale, 0.33 * scale, body.location.z + 0.12 * scale))
        parts.extend([vent, label])
        if definition.prop_type == "electrical_cabinet":
            for sign in (-1.0, 1.0):
                parts.append(_part(utils.create_box(f"{root.name}_foot_{int(sign)}", context.collection, (0.14 * scale, 0.55 * scale, 0.12 * scale), location=(sign * 0.3 * scale, 0.0, 0.06 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category))
        else:
            conduit = _part(utils.create_pipe_between_points(f"{root.name}_conduit", context.collection, (0.0, -0.2 * scale, body.location.z), (0.0, -0.5 * scale, 0.1 * scale), 0.025 * scale, 6), context.atlas_runtime, "rubber_black", definition.prop_type, definition.category)
            parts.append(conduit)
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_fence(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Fence_Cage" if definition.prop_type == "equipment_cage" else "RY_Fence", context.collection, location)
    parts = []
    if definition.prop_type == "equipment_cage":
        width, depth, height = 1.9 * scale, 1.4 * scale, 1.9 * scale
        post_points = [(-width * 0.5, -depth * 0.5), (width * 0.5, -depth * 0.5), (-width * 0.5, depth * 0.5), (width * 0.5, depth * 0.5)]
        for x, y in post_points:
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_post", context.collection, (x, y, 0.0), (x, y, height), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        panels = [
            ((0.0, -depth * 0.5, height * 0.5), (width, height), (math.radians(90.0), 0.0, 0.0)),
            ((0.0, depth * 0.5, height * 0.5), (width, height), (math.radians(90.0), 0.0, 0.0)),
            ((-width * 0.5, 0.0, height * 0.5), (depth, height), (0.0, math.radians(90.0), 0.0)),
            ((width * 0.5, 0.0, height * 0.5), (depth, height), (0.0, math.radians(90.0), 0.0)),
        ]
        for index, (loc, size, rot) in enumerate(panels):
            parts.append(_part(utils.create_panel_plane(f"{root.name}_panel_{index}", context.collection, size=size, location=loc, rotation=rot), context.atlas_runtime, "chainlink", definition.prop_type, definition.category))
    else:
        length = 2.2 * scale if definition.prop_type == "chainlink_fence" else 1.5 * scale
        height = 1.7 * scale if definition.prop_type == "chainlink_fence" else 0.95 * scale
        for sign in (-1.0, 1.0):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_post_{int(sign)}", context.collection, (sign * length * 0.5, 0.0, 0.0), (sign * length * 0.5, 0.0, height), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        parts.append(_part(utils.create_pipe_between_points(f"{root.name}_top", context.collection, (-length * 0.5, 0.0, height), (length * 0.5, 0.0, height), 0.02 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        parts.append(_part(utils.create_pipe_between_points(f"{root.name}_bottom", context.collection, (-length * 0.5, 0.0, 0.08 * scale), (length * 0.5, 0.0, 0.08 * scale), 0.02 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        if definition.prop_type == "chainlink_fence":
            parts.append(_part(utils.create_panel_plane(f"{root.name}_mesh", context.collection, (length, height * 0.9), location=(0.0, 0.0, height * 0.5), rotation=(math.radians(90.0), 0.0, 0.0)), context.atlas_runtime, "chainlink", definition.prop_type, definition.category))
        else:
            for offset in (-0.2, 0.2):
                parts.append(_part(utils.create_pipe_between_points(f"{root.name}_rail_{offset}", context.collection, (-length * 0.45, 0.0, height * (0.5 + offset)), (length * 0.45, 0.0, height * (0.5 + offset)), 0.02 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
            if definition.prop_type == "safety_barrier":
                parts.append(_common_panel_label(f"{root.name}_hazard", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (length * 0.5, 0.18 * scale), (0.0, 0.0, height * 0.55), rotation=(math.radians(90.0), 0.0, 0.0), region_name="hazard_stripes"))
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_access(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Access", context.collection, location)
    parts = []
    if definition.prop_type == "step_ladder":
        for sign in (-1.0, 1.0):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_front_{int(sign)}", context.collection, (sign * 0.25 * scale, -0.35 * scale, 0.0), (sign * 0.12 * scale, 0.0, 1.45 * scale), 0.025 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_back_{int(sign)}", context.collection, (sign * 0.22 * scale, 0.42 * scale, 0.0), (sign * 0.12 * scale, 0.05 * scale, 1.35 * scale), 0.022 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        for step in range(5):
            z = 0.28 * scale + step * 0.22 * scale
            y = -0.25 * scale + step * 0.07 * scale
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_step_{step}", context.collection, (-0.18 * scale, y, z), (0.18 * scale, y, z), 0.018 * scale, 8), context.atlas_runtime, "metal_light", definition.prop_type, definition.category))
        top = _part(utils.create_box(f"{root.name}_top", context.collection, (0.35 * scale, 0.18 * scale, 0.05 * scale), location=(0.0, 0.08 * scale, 1.45 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.append(top)
    elif definition.prop_type == "vertical_ladder":
        for sign in (-1.0, 1.0):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_rail_{int(sign)}", context.collection, (sign * 0.18 * scale, 0.0, 0.0), (sign * 0.18 * scale, 0.0, 2.9 * scale), 0.022 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        for step in range(11):
            z = 0.25 * scale + step * 0.24 * scale
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_rung_{step}", context.collection, (-0.16 * scale, 0.0, z), (0.16 * scale, 0.0, z), 0.016 * scale, 8), context.atlas_runtime, "metal_light", definition.prop_type, definition.category))
    else:
        deck = _part(utils.create_box(f"{root.name}_deck", context.collection, (1.2 * scale, 0.9 * scale, 0.08 * scale), location=(0.0, 0.0, 0.9 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        parts.append(deck)
        for x in (-0.45, 0.45):
            for y in (-0.32, 0.32):
                parts.append(_part(utils.create_pipe_between_points(f"{root.name}_leg_{x}_{y}", context.collection, (x * scale, y * scale, 0.0), (x * scale, y * scale, 0.9 * scale), 0.03 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
        for sign in (-1.0, 1.0):
            parts.append(_part(utils.create_pipe_between_points(f"{root.name}_rail_{int(sign)}", context.collection, (sign * 0.55 * scale, -0.45 * scale, 0.9 * scale), (sign * 0.55 * scale, 0.45 * scale, 1.35 * scale), 0.02 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category))
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_storage(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Storage", context.collection, location)
    parts = []
    if definition.prop_type in {"barrel", "bin"}:
        radius = 0.26 * scale if definition.prop_type == "barrel" else 0.32 * scale
        depth = 0.82 * scale if definition.prop_type == "barrel" else 0.95 * scale
        body = _part(utils.create_cylinder(f"{root.name}_body", context.collection, radius, depth, 12, location=(0.0, 0.0, depth * 0.5)), context.atlas_runtime, "metal_dark" if definition.prop_type == "barrel" else "paint_white", definition.prop_type, definition.category)
        lid = _part(utils.create_cylinder(f"{root.name}_lid", context.collection, radius * 1.03, 0.06 * scale, 12, location=(0.0, 0.0, depth + 0.03 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.extend([body, lid])
    else:
        size = (0.75 * scale, 0.55 * scale, 0.45 * scale) if definition.prop_type == "service_box" else (0.95 * scale, 0.72 * scale, 0.62 * scale)
        body = _part(utils.create_box(f"{root.name}_body", context.collection, size, location=(0.0, 0.0, size[2] * 0.5)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        lid = _part(utils.create_box(f"{root.name}_lid", context.collection, (size[0] * 1.02, size[1] * 1.02, 0.06 * scale), location=(0.0, 0.0, size[2] + 0.03 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        handle = _part(utils.create_pipe_between_points(f"{root.name}_handle", context.collection, (-0.12 * scale, size[1] * 0.52, size[2] * 0.6), (0.12 * scale, size[1] * 0.52, size[2] * 0.6), 0.012 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        label = _common_panel_label(f"{root.name}_label", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.14 * scale, 0.1 * scale), (size[0] * 0.22, size[1] * 0.53, size[2] * 0.62))
        parts.extend([body, lid, handle, label])
    for part in parts:
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_surveillance(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Surveillance", context.collection, location)
    parts = []
    if definition.prop_type == "dome_sensor":
        base = _part(utils.create_cylinder(f"{root.name}_base", context.collection, 0.22 * scale, 0.08 * scale, 12, location=(0.0, 0.0, 0.04 * scale)), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        dome = _part(utils.create_sphere(f"{root.name}_dome", context.collection, 0.2 * scale, 12, 8, location=(0.0, 0.0, 0.2 * scale)), context.atlas_runtime, "glass_light", definition.prop_type, definition.category)
        core = _part(utils.create_box(f"{root.name}_core", context.collection, (0.12 * scale, 0.12 * scale, 0.08 * scale), location=(0.0, 0.0, 0.18 * scale)), context.atlas_runtime, "speaker_dark", definition.prop_type, definition.category)
        parts.extend([base, dome, core])
    elif definition.prop_type == "security_camera":
        body = _part(utils.create_box(f"{root.name}_body", context.collection, (0.32 * scale, 0.18 * scale, 0.16 * scale), location=(0.0, 0.18 * scale, 0.36 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        lens = _part(utils.create_cylinder(f"{root.name}_lens", context.collection, 0.05 * scale, 0.06 * scale, 10, location=(0.0, 0.29 * scale, 0.36 * scale), rotation=(math.radians(90.0), 0.0, 0.0)), context.atlas_runtime, "glass_light", definition.prop_type, definition.category)
        bracket = _part(utils.create_pipe_between_points(f"{root.name}_bracket", context.collection, (0.0, 0.0, 0.24 * scale), (0.0, 0.12 * scale, 0.34 * scale), 0.015 * scale, 6), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        parts.extend([body, lens, bracket])
    else:
        pole = _part(utils.create_pipe_between_points(f"{root.name}_pole", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 1.55 * scale), 0.025 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        box = _part(utils.create_box(f"{root.name}_sensor", context.collection, (0.2 * scale, 0.15 * scale, 0.14 * scale), location=(0.0, 0.0, 1.62 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.extend([pole, box])
    for part in parts:
        if part.type == "MESH":
            utils.shade_smooth_safe(part)
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


def build_special(context: BuildContext, definition: PropDef, location, rotation_z, scale) -> bpy.types.Object:
    root = _root("RY_Special", context.collection, location)
    parts = []
    if definition.prop_type == "hazard_sphere_module":
        sphere = _part(utils.create_sphere(f"{root.name}_sphere", context.collection, 0.42 * scale, 14, 10, location=(0.0, 0.0, 0.62 * scale)), context.atlas_runtime, "speaker_dark", definition.prop_type, definition.category)
        band = _part(utils.create_cylinder(f"{root.name}_band", context.collection, 0.46 * scale, 0.12 * scale, 14, location=(0.0, 0.0, 0.62 * scale)), context.atlas_runtime, "hazard_stripes", definition.prop_type, definition.category)
        base = _part(utils.create_cylinder(f"{root.name}_base", context.collection, 0.55 * scale, 0.22 * scale, 14, location=(0.0, 0.0, 0.11 * scale)), context.atlas_runtime, "concrete_base", definition.prop_type, definition.category)
        panel = _common_panel_label(f"{root.name}_panel", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.18 * scale, 0.12 * scale), (0.0, 0.45 * scale, 0.62 * scale))
        parts.extend([sphere, band, base, panel])
    elif definition.prop_type == "research_beacon":
        shaft = _part(utils.create_pipe_between_points(f"{root.name}_shaft", context.collection, (0.0, 0.0, 0.0), (0.0, 0.0, 1.8 * scale), 0.035 * scale, 8), context.atlas_runtime, "metal_dark", definition.prop_type, definition.category)
        core = _part(utils.create_cylinder(f"{root.name}_core", context.collection, 0.16 * scale, 0.38 * scale, 10, location=(0.0, 0.0, 1.55 * scale)), context.atlas_runtime, "lamp_glow", definition.prop_type, definition.category)
        fins = _part(utils.create_panel_plane(f"{root.name}_fin", context.collection, (0.44 * scale, 0.18 * scale), location=(0.0, 0.0, 1.3 * scale), rotation=(math.radians(90.0), 0.0, 0.0)), context.atlas_runtime, "hazard_stripes", definition.prop_type, definition.category)
        parts.extend([shaft, core, fins])
    else:
        body = _part(utils.create_box(f"{root.name}_body", context.collection, (1.1 * scale, 0.85 * scale, 0.9 * scale), location=(0.0, 0.0, 0.45 * scale)), context.atlas_runtime, "speaker_dark", definition.prop_type, definition.category)
        stripe = _common_panel_label(f"{root.name}_stripe", context.collection, context.atlas_runtime, definition.prop_type, definition.category, (0.74 * scale, 0.18 * scale), (0.0, 0.43 * scale, 0.45 * scale), rotation=(math.radians(90.0), 0.0, 0.0), region_name="hazard_stripes")
        hatch = _part(utils.create_box(f"{root.name}_hatch", context.collection, (0.28 * scale, 0.04 * scale, 0.32 * scale), location=(0.0, 0.44 * scale, 0.45 * scale)), context.atlas_runtime, "metal_light", definition.prop_type, definition.category)
        parts.extend([body, stripe, hatch])
    for part in parts:
        if part.type == "MESH":
            utils.shade_smooth_safe(part)
        _maybe_bevel(part, context.settings.detail_level, context.settings.apply_bevels)
    return _finalize_root(root, parts, definition.prop_type, definition.category, context.created_objects)


BUILDERS = {
    "roof_power": build_solar_array,
    "roof_utilities": build_tank,
    "roof_hvac": build_hvac,
    "roof_vents": build_vent,
    "communications": build_antenna,
    "warning_systems": build_warning,
    "lighting": build_light,
    "power_equipment": build_power,
    "fences": build_fence,
    "access": build_access,
    "storage": build_storage,
    "surveillance": build_surveillance,
    "special": build_special,
}


def build_prop(context: BuildContext, prop_type: str, location=(0.0, 0.0, 0.0), rotation_z=0.0, scale=1.0) -> bpy.types.Object:
    definition = PROP_DEFS[prop_type]
    builder = BUILDERS[definition.category]
    obj = builder(context, definition, location, rotation_z, scale)
    obj.location = location
    return obj


def weighted_choice(rng: random.Random, defs: list[PropDef]) -> PropDef:
    total = sum(definition.weight for definition in defs)
    threshold = rng.uniform(0.0, total)
    running = 0.0
    for definition in defs:
        running += definition.weight
        if running >= threshold:
            return definition
    return defs[-1]


def try_place_prop(rng, definition: PropDef, placed_rects: list[tuple[float, float, float, float]], width: float, depth: float, margin: float, avoid_overlaps: bool, blocked_rects: list[tuple[float, float, float, float]], attempts: int = 50):
    rotations = [0.0, math.radians(90.0), math.radians(180.0), math.radians(270.0)]
    for _ in range(attempts):
        rotation_z = rng.choice(rotations)
        footprint = utils.compute_rotated_footprint(definition.footprint, rotation_z)
        center = utils.sample_position_in_rect(rng, width, depth, margin, footprint)
        rect = utils.rect_from_center(center, footprint)
        if any(utils.rects_overlap(rect, blocked, 0.0) for blocked in blocked_rects):
            continue
        if avoid_overlaps and any(utils.rects_overlap(rect, other, 0.18) for other in placed_rects):
            continue
        return center, rect, rotation_z
    return None, None, None


def _roof_service_paths(props) -> list[tuple[float, float, float, float]]:
    if not props.keep_service_paths:
        return []
    width = props.roof_width
    depth = props.roof_depth
    path = props.service_path_width
    return [
        (-path * 0.5, -depth * 0.5, path * 0.5, depth * 0.5),
        (-width * 0.5, -path * 0.5, width * 0.5, path * 0.5),
    ]


def _build_guide_plane(collection, name, size, z, region_name, context: BuildContext):
    plane = utils.create_panel_plane(name, collection, size=size, location=(0.0, 0.0, z))
    textures.apply_material_and_uv(plane, context.atlas_runtime, region_name)
    utils.set_generated_metadata(plane, "guide_plane", "guides", [region_name])
    context.created_objects.append(plane)
    return plane


def generate_single(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    manifest = atlas_manifest.manifest_from_settings(props, persist_default_manifest=True)
    runtime = atlas_manifest.build_runtime(props, manifest)
    collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    target_collection = utils.ensure_child_collection(collection, "Single")
    rng = random.Random(props.seed)
    build_context = BuildContext(context.scene, target_collection, props, runtime, rng)
    build_prop(build_context, props.single_prop_type, location=(0.0, 0.0, 0.0), rotation_z=0.0, scale=props.scale_multiplier)
    return build_context.created_objects


def generate_preview(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    manifest = atlas_manifest.manifest_from_settings(props, persist_default_manifest=True)
    runtime = atlas_manifest.build_runtime(props, manifest)
    collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    preview_collection = utils.ensure_child_collection(collection, "Preview")
    rng = random.Random(props.seed)
    build_context = BuildContext(context.scene, preview_collection, props, runtime, rng)
    if props.include_ground_plane:
        _build_guide_plane(preview_collection, "RY_Preview_Ground", (props.preview_columns * props.preview_spacing, props.preview_spacing * 6.0), -0.001, "concrete_base", build_context)
    defs = [definition for definition in PROP_DEFS.values() if definition.category in enabled_categories_from_props(props)]
    if not defs:
        defs = list(PROP_DEFS.values())
    columns = max(1, props.preview_columns)
    spacing = max(1.0, props.preview_spacing)
    for index, definition in enumerate(defs):
        row = index // columns
        col = index % columns
        base_x = col * spacing
        base_y = -row * spacing
        variant_count = max(1, props.preview_variants_per_type)
        for variant in range(variant_count):
            build_prop(
                build_context,
                definition.prop_type,
                location=(base_x + variant * 0.6, base_y - variant * 0.2, 0.0),
                rotation_z=(math.pi * 0.5) if variant % 2 else 0.0,
                scale=props.scale_multiplier,
            )
        if props.include_preview_labels:
            label = utils.create_text_label(definition.prop_type, preview_collection, (base_x - 0.9, base_y - 0.3, 0.02), size=0.22)
            build_context.created_objects.append(label)
    return build_context.created_objects


def generate_roof(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    manifest = atlas_manifest.manifest_from_settings(props, persist_default_manifest=True)
    runtime = atlas_manifest.build_runtime(props, manifest)
    root_collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    roof_collection = utils.ensure_child_collection(root_collection, "Roof")
    rng = random.Random(props.seed)
    build_context = BuildContext(context.scene, roof_collection, props, runtime, rng)
    _build_guide_plane(roof_collection, "RY_Roof_Area", (props.roof_width, props.roof_depth), 0.0, "concrete_base", build_context)

    placed_rects: list[tuple[float, float, float, float]] = []
    blocked_rects = _roof_service_paths(props)
    categories = enabled_categories_from_props(props)
    candidates = surface_filtered_props("roof", categories)
    target_count = max(4, int(props.roof_width * props.roof_depth * props.density * 0.12))

    if props.enable_solar_panels:
        rows = max(1, int(props.density * 2))
        for row in range(rows):
            center = (0.0, -props.roof_depth * 0.2 + row * 2.0 * props.scale_multiplier)
            rect = utils.rect_from_center(center, PROP_DEFS["solar_panel_array"].footprint)
            if any(utils.rects_overlap(rect, other, 0.25) for other in blocked_rects):
                continue
            build_prop(build_context, "solar_panel_array", location=(center[0], center[1], 0.0), rotation_z=0.0, scale=props.scale_multiplier)
            placed_rects.append(rect)

    priority = [definition for definition in candidates if definition.prop_type in {"hvac_large", "hvac_medium", "antenna_tripod", "vent_mushroom", "electrical_cabinet"}]
    fill = [definition for definition in candidates if definition not in priority]
    for definition in priority:
        result = try_place_prop(rng, definition, placed_rects, props.roof_width, props.roof_depth, props.margin_from_edge, props.avoid_overlaps, blocked_rects)
        center, rect, rotation_z = result
        if center is None:
            continue
        build_prop(build_context, definition.prop_type, location=(center[0], center[1], 0.0), rotation_z=rotation_z, scale=props.scale_multiplier)
        placed_rects.append(rect)

    while len(placed_rects) < target_count and fill:
        definition = weighted_choice(rng, fill)
        center, rect, rotation_z = try_place_prop(rng, definition, placed_rects, props.roof_width, props.roof_depth, props.margin_from_edge, props.avoid_overlaps, blocked_rects)
        if center is None:
            break
        build_prop(build_context, definition.prop_type, location=(center[0], center[1], 0.0), rotation_z=rotation_z, scale=props.scale_multiplier)
        placed_rects.append(rect)
        if props.cluster_mode and definition.category in {"roof_vents", "roof_hvac"} and rng.random() > 0.55:
            offset = (center[0] + rng.uniform(-0.8, 0.8), center[1] + rng.uniform(-0.8, 0.8))
            rect2 = utils.rect_from_center(offset, definition.footprint)
            if not any(utils.rects_overlap(rect2, other, 0.15) for other in placed_rects):
                build_prop(build_context, definition.prop_type, location=(offset[0], offset[1], 0.0), rotation_z=rotation_z, scale=props.scale_multiplier * rng.uniform(0.9, 1.05))
                placed_rects.append(rect2)
    return build_context.created_objects


def generate_yard(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    manifest = atlas_manifest.manifest_from_settings(props, persist_default_manifest=True)
    runtime = atlas_manifest.build_runtime(props, manifest)
    root_collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    yard_collection = utils.ensure_child_collection(root_collection, "Yard")
    rng = random.Random(props.seed)
    build_context = BuildContext(context.scene, yard_collection, props, runtime, rng)
    _build_guide_plane(yard_collection, "RY_Yard_Area", (props.yard_width, props.yard_depth), 0.0, "concrete_base", build_context)
    building_plane = _build_guide_plane(yard_collection, "RY_Building_Footprint", (props.building_width, props.building_depth), 0.01, "metal_dark", build_context)
    building_plane["procedural_rooftop_yard"] = False

    placed_rects: list[tuple[float, float, float, float]] = [utils.rect_from_center((0.0, 0.0), (props.building_width + props.margin_from_edge * 2.0, props.building_depth + props.margin_from_edge * 2.0))]
    categories = enabled_categories_from_props(props)
    candidates = surface_filtered_props("yard", categories)
    target_count = max(5, int(props.yard_width * props.yard_depth * props.density * 0.08))

    if props.fence_around_yard:
        perimeter_defs = ["chainlink_fence", "chainlink_fence", "chainlink_fence", "chainlink_fence"]
        offsets = [
            (0.0, -props.yard_depth * 0.48, 0.0),
            (0.0, props.yard_depth * 0.48, math.pi),
            (-props.yard_width * 0.48, 0.0, math.pi * 0.5),
            (props.yard_width * 0.48, 0.0, math.pi * 0.5),
        ]
        for prop_type, (x, y, rot) in zip(perimeter_defs, offsets):
            build_prop(build_context, prop_type, location=(x, y, 0.0), rotation_z=rot, scale=props.scale_multiplier)

    cluster_types = []
    if props.equipment_zone:
        cluster_types.extend(["electrical_cabinet", "equipment_cage", "battery_box"])
    if props.generator_zone:
        cluster_types.extend(["portable_generator", "inverter_box"])
    if props.enable_tanks:
        cluster_types.extend(["water_tank_vertical", "barrel"])
    if props.enable_lighting and props.lighting_zone:
        cluster_types.extend(["pole_floodlight", "work_light"])

    cluster_anchor = (-props.building_width * 0.5 - 1.8, -props.building_depth * 0.5 - 1.2)
    for index, prop_type in enumerate(cluster_types):
        offset = (cluster_anchor[0] + (index % 3) * 1.6, cluster_anchor[1] - (index // 3) * 1.4)
        build_prop(build_context, prop_type, location=(offset[0], offset[1], 0.0), rotation_z=0.0, scale=props.scale_multiplier)
        placed_rects.append(utils.rect_from_center(offset, PROP_DEFS[prop_type].footprint))

    while len(placed_rects) < target_count and candidates:
        definition = weighted_choice(rng, candidates)
        footprint = definition.footprint
        rotation_z = rng.choice([0.0, math.pi * 0.5, math.pi, math.pi * 1.5])
        footprint = utils.compute_rotated_footprint(footprint, rotation_z)
        center = utils.sample_position_around_building(rng, props.yard_width, props.yard_depth, props.building_width, props.building_depth, props.margin_from_edge, footprint)
        rect = utils.rect_from_center(center, footprint)
        if props.avoid_overlaps and any(utils.rects_overlap(rect, other, 0.16) for other in placed_rects):
            continue
        build_prop(build_context, definition.prop_type, location=(center[0], center[1], 0.0), rotation_z=rotation_z, scale=props.scale_multiplier)
        placed_rects.append(rect)
    return build_context.created_objects


def clear_generated(context: bpy.types.Context, props) -> None:
    collection = bpy.data.collections.get(props.target_collection_name)
    if collection is not None:
        utils.clear_collection(collection)

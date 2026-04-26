from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from . import utils
from .furniture_catalog import (
    FURNITURE_BY_ID,
    FURNITURE_CATALOG,
    ROOM_COLLECTIONS,
    definitions_for_room,
    normalize_room_type,
)
from .furniture_generator import FurnitureBuildContext, build_furniture_object, build_furniture_runtime, weighted_choice


def _selected_room_bounds(context: bpy.types.Context, fallback_width: float, fallback_depth: float) -> tuple[float, float, float, float, str]:
    obj = context.active_object
    if obj is None or not getattr(obj, "bound_box", None):
        return 0.0, 0.0, fallback_width, fallback_depth, "all"
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [corner.x for corner in corners]
    ys = [corner.y for corner in corners]
    zs = [corner.z for corner in corners]
    width = max(max(xs) - min(xs), 1.0)
    depth = max(max(ys) - min(ys), 1.0)
    center_x = (min(xs) + max(xs)) * 0.5
    center_y = (min(ys) + max(ys)) * 0.5
    z = min(zs)
    room = "all"
    for key in ("room_type", "room_purpose", "purpose"):
        value = obj.get(key)
        if value:
            room = normalize_room_type(str(value), "all")
            break
    return center_x, center_y, width, depth, room, z


def _room_collection(root_collection: bpy.types.Collection, room_type: str) -> bpy.types.Collection:
    furniture_collection = utils.ensure_child_collection(root_collection, "Furniture")
    if room_type == "all":
        return furniture_collection
    return utils.ensure_child_collection(furniture_collection, ROOM_COLLECTIONS.get(room_type, room_type.title()))


def _guide_plane(context: FurnitureBuildContext, collection, name: str, size: tuple[float, float], z: float):
    plane = utils.create_panel_plane(name, collection, size=size, location=(0.0, 0.0, z - 0.002))
    from . import textures

    textures.apply_material_and_uv(plane, context.atlas_runtime, "painted_metal_gray")
    utils.set_generated_metadata(plane, "furniture_area", "furniture/guides", ["painted_metal_gray"])
    context.created_objects.append(plane)
    return plane


def generate_furniture_catalog_preview(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    runtime = build_furniture_runtime(props)
    root_collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    furniture_collection = utils.ensure_child_collection(root_collection, "Furniture")
    preview_collection = utils.ensure_child_collection(furniture_collection, "CatalogPreview")
    rng = random.Random(props.furniture_seed)
    build_context = FurnitureBuildContext(context.scene, preview_collection, props, runtime, rng)

    room_types = list(FURNITURE_CATALOG.keys()) if props.room_type == "all" else [props.room_type]
    spacing = max(1.5, props.preview_spacing)
    columns = max(1, props.preview_columns)
    row_offset = 0
    for room_type in room_types:
        definitions = definitions_for_room(room_type)
        if props.furniture_object_type != "all":
            definitions = [FURNITURE_BY_ID[props.furniture_object_type]]
        room_collection = utils.ensure_child_collection(preview_collection, ROOM_COLLECTIONS.get(room_type, room_type.title()))
        build_context.collection = room_collection
        for index, definition in enumerate(definitions):
            row = (index // columns) + row_offset
            col = index % columns
            x = col * spacing
            y = -row * spacing
            build_furniture_object(build_context, definition.object_id, (x, y, 0.0), rotation_z=(index % 4) * math.pi * 0.5, scale=props.scale_multiplier)
            if props.include_preview_labels:
                label = utils.create_text_label(f"{definition.room_type}/{definition.object_id}", room_collection, (x - 0.8, y - 0.55, 0.02), size=0.18)
                build_context.created_objects.append(label)
        row_offset += math.ceil(max(1, len(definitions)) / columns) + 1
    return build_context.created_objects


def _wall_aligned_candidate(rng, definition, width: float, depth: float, margin: float, footprint: tuple[float, float]):
    side = rng.choice(("north", "south", "east", "west"))
    if side in {"north", "south"}:
        x = rng.uniform(-width * 0.5 + margin + footprint[0] * 0.5, width * 0.5 - margin - footprint[0] * 0.5)
        y = (depth * 0.5 - margin - footprint[1] * 0.5) * (1 if side == "north" else -1)
        rot = 0.0 if side == "north" else math.pi
    else:
        x = (width * 0.5 - margin - footprint[1] * 0.5) * (1 if side == "east" else -1)
        y = rng.uniform(-depth * 0.5 + margin + footprint[0] * 0.5, depth * 0.5 - margin - footprint[0] * 0.5)
        rot = math.pi * 0.5 if side == "east" else math.pi * 1.5
    return (x, y), rot


def _center_candidate(rng, width: float, depth: float, margin: float, footprint: tuple[float, float]):
    x_span = max(0.1, width * 0.18)
    y_span = max(0.1, depth * 0.18)
    return (rng.uniform(-x_span, x_span), rng.uniform(-y_span, y_span)), rng.choice([0.0, math.pi * 0.5, math.pi, math.pi * 1.5])


def _try_place(rng, definition, placed_rects, width, depth, margin, padding, avoid_overlaps, attempts=80):
    for _attempt in range(attempts):
        rotation_z = rng.choice([0.0, math.pi * 0.5, math.pi, math.pi * 1.5])
        footprint = utils.compute_rotated_footprint(definition.footprint, rotation_z)
        if definition.placement in {"wall", "corner"}:
            center, rotation_z = _wall_aligned_candidate(rng, definition, width, depth, margin, definition.footprint)
            footprint = utils.compute_rotated_footprint(definition.footprint, rotation_z)
        elif definition.placement == "center":
            center, rotation_z = _center_candidate(rng, width, depth, margin, footprint)
            footprint = utils.compute_rotated_footprint(definition.footprint, rotation_z)
        else:
            center = utils.sample_position_in_rect(rng, width, depth, margin, footprint)
        rect = utils.rect_from_center(center, footprint)
        bounds = (-width * 0.5 + margin, -depth * 0.5 + margin, width * 0.5 - margin, depth * 0.5 - margin)
        if rect[0] < bounds[0] or rect[1] < bounds[1] or rect[2] > bounds[2] or rect[3] > bounds[3]:
            continue
        if avoid_overlaps and any(utils.rects_overlap(rect, other, padding) for other in placed_rects):
            continue
        return center, rect, rotation_z
    return None, None, None


def generate_furniture_in_rectangle(context: bpy.types.Context, props, *, use_selected_bounds: bool = False) -> list[bpy.types.Object]:
    runtime = build_furniture_runtime(props)
    root_collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    rng = random.Random(props.furniture_seed)

    room_type = props.room_type
    origin_x = origin_y = 0.0
    origin_z = 0.0
    width = props.furniture_area_width
    depth = props.furniture_area_depth
    if use_selected_bounds:
        selected = _selected_room_bounds(context, width, depth)
        origin_x, origin_y, width, depth, selected_room, origin_z = selected
        if room_type == "all" and selected_room != "all":
            room_type = selected_room

    target_collection = _room_collection(root_collection, room_type if room_type != "all" else "all")
    build_context = FurnitureBuildContext(context.scene, target_collection, props, runtime, rng)
    if getattr(props, "include_ground_plane", True):
        guide = _guide_plane(build_context, target_collection, f"FURN_{room_type}_Area", (width, depth), origin_z)
        guide.location.x += origin_x
        guide.location.y += origin_y

    candidates = definitions_for_room(room_type)
    if props.furniture_object_type != "all":
        candidates = [FURNITURE_BY_ID[props.furniture_object_type]]
    if not candidates:
        return build_context.created_objects

    placed_rects: list[tuple[float, float, float, float]] = []
    target_count = max(1, int(props.furniture_density))
    priority = [definition for definition in candidates if definition.placement in {"wall", "corner"}]
    fill = list(candidates)

    for definition in priority[: min(len(priority), target_count)]:
        center, rect, rotation_z = _try_place(rng, definition, placed_rects, width, depth, props.furniture_margin, props.furniture_collision_padding, props.avoid_overlaps)
        if center is None:
            continue
        build_furniture_object(build_context, definition.object_id, (origin_x + center[0], origin_y + center[1], origin_z), rotation_z, props.scale_multiplier)
        placed_rects.append(rect)

    failures = 0
    while len(placed_rects) < target_count and failures < target_count * 30:
        definition = weighted_choice(rng, fill)
        center, rect, rotation_z = _try_place(rng, definition, placed_rects, width, depth, props.furniture_margin, props.furniture_collision_padding, props.avoid_overlaps)
        if center is None:
            failures += 1
            continue
        build_furniture_object(build_context, definition.object_id, (origin_x + center[0], origin_y + center[1], origin_z), rotation_z, props.scale_multiplier)
        placed_rects.append(rect)
    return build_context.created_objects


def generate_single_furniture(context: bpy.types.Context, props) -> list[bpy.types.Object]:
    runtime = build_furniture_runtime(props)
    root_collection = utils.ensure_collection(context.scene, props.target_collection_name, props.clear_previous_before_generate)
    room_type = props.room_type
    if props.furniture_object_type != "all":
        room_type = FURNITURE_BY_ID[props.furniture_object_type].room_type
    target_collection = _room_collection(root_collection, room_type if room_type != "all" else "all")
    rng = random.Random(props.furniture_seed)
    build_context = FurnitureBuildContext(context.scene, target_collection, props, runtime, rng)
    object_id = props.furniture_object_type
    if object_id == "all":
        candidates = definitions_for_room(room_type)
        object_id = weighted_choice(rng, candidates).object_id
    build_furniture_object(build_context, object_id, (0.0, 0.0, 0.0), 0.0, props.scale_multiplier)
    return build_context.created_objects


def register():
    pass


def unregister():
    pass

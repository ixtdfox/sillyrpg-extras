from __future__ import annotations

import bpy
from mathutils import Vector

from ...common.utils import ADDON_ID
from ..terrain_materials import ensure_terrain_material
from .metrics import tiles_to_meters


def create_city_surface_materials() -> dict[str, bpy.types.Material]:
    return {
        "ground": ensure_terrain_material("Terrain_Ground_Grass", (0.18, 0.35, 0.14, 1.0)),
        "road": ensure_terrain_material("Terrain_Road_Asphalt", (0.09, 0.09, 0.09, 1.0)),
        "intersection": ensure_terrain_material("Terrain_Road_Intersection", (0.11, 0.11, 0.11, 1.0)),
        "sidewalk": ensure_terrain_material("Terrain_Sidewalk_Concrete", (0.63, 0.63, 0.63, 1.0)),
        "curb": ensure_terrain_material("Terrain_Curb_Concrete", (0.78, 0.78, 0.78, 1.0)),
        "crosswalk": ensure_terrain_material("Terrain_Crosswalk_White", (0.96, 0.96, 0.96, 1.0)),
        "lane_mark": ensure_terrain_material("Terrain_LaneMark_Yellow", (0.95, 0.78, 0.15, 1.0)),
        "debug_road": ensure_terrain_material("Terrain_Debug_Road", (0.12, 0.62, 0.95, 0.25)),
        "debug_block": ensure_terrain_material("Terrain_Debug_Block", (0.25, 0.95, 0.45, 0.25)),
        "debug_parcel": ensure_terrain_material("Terrain_Debug_Parcel", (0.95, 0.65, 0.15, 0.25)),
        "debug_building": ensure_terrain_material("Terrain_Debug_Building", (0.95, 0.2, 0.25, 0.25)),
    }


def create_prism_object(
    *,
    collection: bpy.types.Collection,
    name: str,
    x: float,
    y: float,
    width: float,
    depth: float,
    z_min: float,
    z_max: float,
    material: bpy.types.Material,
    building_part: str,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    x_min = x
    y_min = y
    x_max = x + width
    y_max = y + depth
    vertices = [
        Vector((x_min, y_min, z_min)),
        Vector((x_max, y_min, z_min)),
        Vector((x_max, y_max, z_min)),
        Vector((x_min, y_max, z_min)),
        Vector((x_min, y_min, z_max)),
        Vector((x_max, y_min, z_max)),
        Vector((x_max, y_max, z_max)),
        Vector((x_min, y_max, z_max)),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata([tuple(item) for item in vertices], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj["generated_by"] = ADDON_ID
    obj["building_part"] = building_part
    collection.objects.link(obj)
    return obj


def generate_city_surfaces(*, collections: dict[str, bpy.types.Collection], layout, settings, scene_id: str) -> dict[str, int]:
    materials = create_city_surface_materials()
    counts = {
        "ground": 0,
        "roads": 0,
        "intersections": 0,
        "sidewalks": 0,
        "curbs": 0,
        "crosswalks": 0,
        "lane_marks": 0,
    }
    if settings.include_ground:
        obj = create_prism_object(
            collection=collections["ground"],
            name="Ground_000",
            x=tiles_to_meters(layout.origin_x_tiles),
            y=tiles_to_meters(layout.origin_y_tiles),
            width=layout.total_width,
            depth=layout.total_depth,
            z_min=-0.04,
            z_max=-0.02,
            material=materials["ground"],
            building_part="ground",
        )
        obj["terrain_scene_id"] = scene_id
        counts["ground"] += 1

    for index, road in enumerate(layout.roads):
        obj = create_prism_object(
            collection=collections["roads"],
            name=f"Road_{index:03d}",
            x=road.x,
            y=road.y,
            width=road.width,
            depth=road.depth,
            z_min=0.0,
            z_max=0.002,
            material=materials["road"],
            building_part="road",
        )
        obj["terrain_scene_id"] = scene_id
        counts["roads"] += 1
        counts["lane_marks"] += _create_lane_marks(collections["lane_marks"], road, materials["lane_mark"], scene_id)

    for index, patch in enumerate(layout.intersections):
        obj = create_prism_object(
            collection=collections["intersections"],
            name=f"Intersection_{index:03d}",
            x=patch.x,
            y=patch.y,
            width=patch.width,
            depth=patch.depth,
            z_min=0.002,
            z_max=0.004,
            material=materials["intersection"],
            building_part="intersection",
        )
        obj["terrain_scene_id"] = scene_id
        counts["intersections"] += 1
        counts["crosswalks"] += _create_crosswalks(collections["crosswalks"], patch, materials["crosswalk"], scene_id)

    for block_index, block in enumerate(layout.blocks):
        outer_x = tiles_to_meters(block.outer_x_tiles)
        outer_y = tiles_to_meters(block.outer_y_tiles)
        outer_w = tiles_to_meters(block.outer_width_tiles)
        outer_d = tiles_to_meters(block.outer_depth_tiles)
        for side_index, bounds in enumerate(_sidewalk_bounds(outer_x, outer_y, outer_w, outer_d, block.x, block.y, block.width, block.depth)):
            if bounds[2] <= 0.0 or bounds[3] <= 0.0:
                continue
            obj = create_prism_object(
                collection=collections["sidewalks"],
                name=f"Sidewalk_{block_index:03d}_{side_index}",
                x=bounds[0],
                y=bounds[1],
                width=bounds[2],
                depth=bounds[3],
                z_min=0.0,
                z_max=0.035,
                material=materials["sidewalk"],
                building_part="sidewalk",
            )
            obj["terrain_scene_id"] = scene_id
            counts["sidewalks"] += 1
        for curb_index, bounds in enumerate(_curb_bounds(block)):
            obj = create_prism_object(
                collection=collections["curbs"],
                name=f"Curb_{block_index:03d}_{curb_index}",
                x=bounds[0],
                y=bounds[1],
                width=bounds[2],
                depth=bounds[3],
                z_min=0.0,
                z_max=0.08,
                material=materials["curb"],
                building_part="curb",
            )
            obj["terrain_scene_id"] = scene_id
            counts["curbs"] += 1
    return counts


def create_debug_bounds(*, collection: bpy.types.Collection, name: str, x: float, y: float, width: float, depth: float, z: float, material: bpy.types.Material, role: str, scene_id: str) -> bpy.types.Object:
    obj = create_prism_object(
        collection=collection,
        name=name,
        x=x,
        y=y,
        width=width,
        depth=depth,
        z_min=z,
        z_max=z + 0.01,
        material=material,
        building_part="debug",
    )
    obj["floorplan_debug"] = True
    obj["terrain_role"] = role
    obj["terrain_scene_id"] = scene_id
    obj.display_type = "WIRE"
    obj.hide_render = True
    return obj


def _sidewalk_bounds(outer_x: float, outer_y: float, outer_w: float, outer_d: float, inner_x: float, inner_y: float, inner_w: float, inner_d: float) -> list[tuple[float, float, float, float]]:
    return [
        (outer_x, outer_y, outer_w, inner_y - outer_y),
        (outer_x, inner_y + inner_d, outer_w, outer_y + outer_d - (inner_y + inner_d)),
        (outer_x, inner_y, inner_x - outer_x, inner_d),
        (inner_x + inner_w, inner_y, outer_x + outer_w - (inner_x + inner_w), inner_d),
    ]


def _curb_bounds(block) -> list[tuple[float, float, float, float]]:
    outer_x = tiles_to_meters(block.outer_x_tiles)
    outer_y = tiles_to_meters(block.outer_y_tiles)
    outer_w = tiles_to_meters(block.outer_width_tiles)
    outer_d = tiles_to_meters(block.outer_depth_tiles)
    curb_depth = min(0.18, max(0.08, tiles_to_meters(0.18)))
    return [
        (outer_x, outer_y, outer_w, curb_depth),
        (outer_x, outer_y + outer_d - curb_depth, outer_w, curb_depth),
        (outer_x, outer_y, curb_depth, outer_d),
        (outer_x + outer_w - curb_depth, outer_y, curb_depth, outer_d),
    ]


def _create_crosswalks(collection: bpy.types.Collection, patch, material: bpy.types.Material, scene_id: str) -> int:
    stripe_width = 0.35
    gap = 0.25
    count = 0
    for orientation in ("horizontal", "vertical"):
        span = patch.width if orientation == "horizontal" else patch.depth
        stripe_count = max(2, int(span // (stripe_width + gap)))
        for index in range(stripe_count):
            if orientation == "horizontal":
                x = patch.x + patch.width * 0.2 + index * (stripe_width + gap)
                y = patch.y + patch.depth * 0.5 - 0.18
                width = min(stripe_width, patch.x + patch.width - x)
                depth = 0.36
            else:
                x = patch.x + patch.width * 0.5 - 0.18
                y = patch.y + patch.depth * 0.2 + index * (stripe_width + gap)
                width = 0.36
                depth = min(stripe_width, patch.y + patch.depth - y)
            if width <= 0.0 or depth <= 0.0:
                continue
            obj = create_prism_object(
                collection=collection,
                name=f"Crosswalk_{patch.patch_id}_{orientation}_{index:02d}",
                x=x,
                y=y,
                width=width,
                depth=depth,
                z_min=0.0055,
                z_max=0.006,
                material=material,
                building_part="crosswalk",
            )
            obj["terrain_scene_id"] = scene_id
            count += 1
    return count


def _create_lane_marks(collection: bpy.types.Collection, road, material: bpy.types.Material, scene_id: str) -> int:
    count = 0
    dash_length = 1.4
    gap = 1.1
    if road.orientation == "horizontal":
        y = road.y + road.depth * 0.5 - 0.05
        cursor = road.x + 0.9
        end = road.x + road.width - 0.9
        while cursor < end:
            width = min(dash_length, end - cursor)
            obj = create_prism_object(
                collection=collection,
                name=f"LaneMark_{road.segment_id}_{count:03d}",
                x=cursor,
                y=y,
                width=width,
                depth=0.1,
                z_min=0.0057,
                z_max=0.006,
                material=material,
                building_part="lane_mark",
            )
            obj["terrain_scene_id"] = scene_id
            count += 1
            cursor += dash_length + gap
        return count
    x = road.x + road.width * 0.5 - 0.05
    cursor = road.y + 0.9
    end = road.y + road.depth - 0.9
    while cursor < end:
        depth = min(dash_length, end - cursor)
        obj = create_prism_object(
            collection=collection,
            name=f"LaneMark_{road.segment_id}_{count:03d}",
            x=x,
            y=cursor,
            width=0.1,
            depth=depth,
            z_min=0.0057,
            z_max=0.006,
            material=material,
            building_part="lane_mark",
        )
        obj["terrain_scene_id"] = scene_id
        count += 1
        cursor += dash_length + gap
    return count

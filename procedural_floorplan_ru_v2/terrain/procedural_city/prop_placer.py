from __future__ import annotations

import math
import random

import bpy

from ...game_grid import GAME_TILE_SIZE_M, snap_value_to_game_grid
from .layout import plan_prop_points


def place_city_props(*, layout, settings, asset_library, collections: dict[str, bpy.types.Collection], scene_id: str, building_bounds: list[tuple[float, float, float, float]], prop_plan=None) -> dict[str, int]:
    rng = random.Random(int(settings.seed) + 404)
    counts = {
        "cars": 0,
        "trees": 0,
        "street_furniture": 0,
        "traffic_lights": 0,
    }
    if not asset_library.has_assets():
        return counts

    if settings.include_cars:
        for road in layout.roads:
            if rng.random() > settings.car_density:
                continue
            margin = GAME_TILE_SIZE_M * 2.0
            if road.orientation == "horizontal":
                if road.width <= margin * 2.0:
                    continue
                x = snap_value_to_game_grid(rng.uniform(road.x + margin, road.x + road.width - margin))
                y = snap_value_to_game_grid(road.y + road.depth * (0.35 if rng.random() < 0.5 else 0.65))
                rotation = 0.0 if rng.random() < 0.5 else math.pi
            else:
                if road.depth <= margin * 2.0:
                    continue
                x = snap_value_to_game_grid(road.x + road.width * (0.35 if rng.random() < 0.5 else 0.65))
                y = snap_value_to_game_grid(rng.uniform(road.y + margin, road.y + road.depth - margin))
                rotation = math.pi * 0.5 if rng.random() < 0.5 else math.pi * 1.5
            filepath = asset_library.choose_asset(("cars", "trucks", "special_vehicles"), rng)
            if filepath is None:
                continue
            obj = asset_library.create_instance(
                filepath=filepath,
                collection=collections["cars"],
                location=(x, y, 0.0),
                rotation_z=rotation,
                scale=rng.uniform(0.9, 1.1),
                prop_type="car",
            )
            if obj is None:
                continue
            _tag_prop(obj, scene_id, "car")
            counts["cars"] += 1

    if settings.include_trees:
        spacing_radius = GAME_TILE_SIZE_M * 2.0
        placed_points: list[tuple[float, float]] = []
        tree_assets_available = bool(asset_library.catalog.get("trees") or asset_library.catalog.get("trees_tropical"))
        tree_candidates = list((prop_plan or plan_prop_points(layout, settings)).get("trees", []))
        for block in layout.blocks:
            candidates = [point for point in tree_candidates if _point_in_rect(point[0], point[1], (block.x, block.y, block.x + block.width, block.y + block.depth))]
            rng.shuffle(candidates)
            target_count = 0
            if tree_assets_available and settings.tree_density > 0.0:
                target_count = max(1, int(round(settings.tree_density * 6.0)))
            placed_in_block = 0
            for x, y in candidates:
                if placed_in_block >= target_count:
                    break
                if any(_point_in_rect(x, y, rect, padding=GAME_TILE_SIZE_M * 0.8) for rect in building_bounds):
                    continue
                if any(_point_in_rect(x, y, (road.x, road.y, road.x + road.width, road.y + road.depth), padding=0.05) for road in layout.roads):
                    continue
                if any(_point_in_rect(x, y, (patch.x, patch.y, patch.x + patch.width, patch.y + patch.depth), padding=0.05) for patch in layout.intersections):
                    continue
                if any(math.dist((x, y), point) < spacing_radius for point in placed_points):
                    continue
                filepath = asset_library.choose_asset(("trees", "trees_tropical"), rng)
                if filepath is None:
                    break
                obj = asset_library.create_instance(
                    filepath=filepath,
                    collection=collections["trees"],
                    location=(snap_value_to_game_grid(x), snap_value_to_game_grid(y), 0.0),
                    rotation_z=rng.uniform(0.0, math.tau),
                    scale=rng.uniform(0.85, 1.2),
                    prop_type="tree",
                )
                if obj is None:
                    continue
                _tag_prop(obj, scene_id, "tree")
                placed_points.append((x, y))
                placed_in_block += 1
                counts["trees"] += 1

    if settings.include_street_furniture:
        for parcel in layout.parcels:
            if rng.random() > 0.25:
                continue
            filepath = asset_library.choose_asset(("benches", "street_furniture", "road_props"), rng)
            if filepath is None:
                continue
            x, y = _frontage_point(parcel)
            if any(_point_in_rect(x, y, rect, padding=GAME_TILE_SIZE_M * 0.5) for rect in building_bounds):
                continue
            obj = asset_library.create_instance(
                filepath=filepath,
                collection=collections["street_furniture"],
                location=(x, y, 0.0),
                rotation_z=rng.uniform(0.0, math.tau),
                scale=rng.uniform(0.9, 1.05),
                prop_type="street_furniture",
            )
            if obj is None:
                continue
            _tag_prop(obj, scene_id, "street_furniture")
            counts["street_furniture"] += 1

    if settings.include_traffic_lights:
        for patch in layout.intersections:
            filepath = asset_library.choose_asset(("traffic_lights",), rng)
            if filepath is None:
                break
            margin = min(GAME_TILE_SIZE_M * 0.5, patch.width * 0.2, patch.depth * 0.2)
            corners = [
                (patch.x + margin, patch.y + margin, 0.0),
                (patch.x + patch.width - margin, patch.y + margin, math.pi * 0.5),
                (patch.x + margin, patch.y + patch.depth - margin, math.pi * 1.5),
                (patch.x + patch.width - margin, patch.y + patch.depth - margin, math.pi),
            ]
            for x, y, rotation in corners[: rng.randint(2, 4)]:
                obj = asset_library.create_instance(
                    filepath=filepath,
                    collection=collections["traffic_lights"],
                    location=(x, y, 0.0),
                    rotation_z=rotation,
                    scale=1.0,
                    prop_type="traffic_light",
                )
                if obj is None:
                    continue
                _tag_prop(obj, scene_id, "traffic_light")
                counts["traffic_lights"] += 1
    return counts


def _block_tree_candidates(block) -> list[tuple[float, float]]:
    candidates: list[tuple[float, float]] = []
    inset = GAME_TILE_SIZE_M * 1.5
    step = GAME_TILE_SIZE_M * 2.0
    x = block.x + inset
    while x <= block.x + block.width - inset + 1e-6:
        candidates.append((x, block.y + inset))
        candidates.append((x, block.y + block.depth - inset))
        x += step
    y = block.y + inset + step
    while y <= block.y + block.depth - inset - step + 1e-6:
        candidates.append((block.x + inset, y))
        candidates.append((block.x + block.width - inset, y))
        y += step
    center_x = block.x + block.width * 0.5
    center_y = block.y + block.depth * 0.5
    candidates.extend(
        [
            (center_x - step, center_y - step),
            (center_x + step, center_y - step),
            (center_x - step, center_y + step),
            (center_x + step, center_y + step),
        ]
    )
    return [(snap_value_to_game_grid(x), snap_value_to_game_grid(y)) for x, y in candidates]


def _frontage_point(parcel) -> tuple[float, float]:
    if parcel.frontage_direction == "south":
        return snap_value_to_game_grid(parcel.x + parcel.width * 0.5), snap_value_to_game_grid(parcel.y - GAME_TILE_SIZE_M)
    if parcel.frontage_direction == "north":
        return snap_value_to_game_grid(parcel.x + parcel.width * 0.5), snap_value_to_game_grid(parcel.y + parcel.depth + GAME_TILE_SIZE_M)
    if parcel.frontage_direction == "east":
        return snap_value_to_game_grid(parcel.x + parcel.width + GAME_TILE_SIZE_M), snap_value_to_game_grid(parcel.y + parcel.depth * 0.5)
    return snap_value_to_game_grid(parcel.x - GAME_TILE_SIZE_M), snap_value_to_game_grid(parcel.y + parcel.depth * 0.5)


def _point_in_rect(x: float, y: float, rect: tuple[float, float, float, float], padding: float = 0.0) -> bool:
    return (rect[0] - padding) <= x <= (rect[2] + padding) and (rect[1] - padding) <= y <= (rect[3] + padding)


def _tag_prop(obj: bpy.types.Object, scene_id: str, role: str) -> None:
    obj["terrain_scene_id"] = scene_id
    obj["terrain_role"] = role
    obj["generated_by"] = "procedural_city"
    obj["prop_type"] = role

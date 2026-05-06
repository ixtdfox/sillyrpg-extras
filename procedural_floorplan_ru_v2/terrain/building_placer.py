from __future__ import annotations

import random
from dataclasses import replace

import bpy
from mathutils import Matrix, Vector

from ..building_manager import settings_from_props
from ..building_stories_manager import BuildingStoriesManager
from ..config import GenerationSettings
from .collection_utils import iter_collection_objects_recursive, relink_collection
from .mask_schema import TerrainMask, TerrainZone
from .region_extractor import TerrainRegion, extract_regions


SHAPE_OPTIONS = ("rectangle", "l_shape", "u_shape", "h_shape", "t_shape", "courdoner", "offset")
PROFILE_OPTIONS = ("strict", "setback", "offset_stack", "pinwheel", "mixed")


def place_buildings_from_mask(
    *,
    scene: bpy.types.Scene,
    props,
    terrain_settings,
    terrain_mask: TerrainMask,
    buildings_collection: bpy.types.Collection,
    terrain_root_name: str,
    progress=None,
    progress_start: int = 70,
    progress_end: int = 92,
) -> list[bpy.types.Collection]:
    base_settings = settings_from_props(props)
    rng = random.Random(int(terrain_settings.seed))
    collections: list[bpy.types.Collection] = []
    regions = extract_regions(terrain_mask, TerrainZone.BUILDING, min_area_px=terrain_settings.min_building_area_px)

    total_regions = max(1, len(regions))
    for region_index, region in enumerate(regions):
        if progress is not None:
            percent = progress_start + int(round((progress_end - progress_start) * ((region_index + 1) / total_regions)))
            progress.update(percent, label=f"Generating buildings {region_index + 1}/{total_regions}", report=False)
        if rng.random() > terrain_settings.building_density:
            continue
        settings = _building_settings_for_region(
            base_settings=base_settings,
            region=region,
            region_index=region_index,
            rng=rng,
            terrain_root_name=terrain_root_name,
            terrain_settings=terrain_settings,
        )
        manager = BuildingStoriesManager(settings)
        building_context = manager.build(scene)
        collection = building_context.collection
        relink_collection(buildings_collection, collection, scene=scene)
        _place_collection_at_region(collection, region, terrain_mask)
        _tag_building_collection(collection, terrain_root_name, region_index)
        collections.append(collection)
    if progress is not None:
        progress.update(progress_end, label=f"Generated buildings: {len(collections)}/{total_regions}", report=False)
    return collections


def _building_settings_for_region(
    *,
    base_settings: GenerationSettings,
    region: TerrainRegion,
    region_index: int,
    rng: random.Random,
    terrain_root_name: str,
    terrain_settings,
) -> GenerationSettings:
    min_x, min_y, max_x, max_y = region.bounds_px
    width_px = max_x - min_x + 1
    height_px = max_y - min_y + 1
    bounds_area = max(1, width_px * height_px)
    scale_hint = max(0.75, min(3.0, (bounds_area ** 0.5) / 6.0))
    target_rooms = max(2, min(18, int(round(bounds_area / 10.0))))
    story_count = rng.randint(terrain_settings.building_min_stories, terrain_settings.building_max_stories)
    shape_mode = rng.choice(SHAPE_OPTIONS)
    profile_mode = rng.choice(PROFILE_OPTIONS if story_count > 2 else ("strict", "setback", "offset_stack"))
    profile_strength = rng.uniform(0.2, 0.9) if profile_mode != "strict" else 0.0
    seed = int(terrain_settings.seed) + (region_index * 9973)
    collection_name = f"{terrain_root_name}_Building_{region_index:03d}_{shape_mode}_{story_count}st"

    return replace(
        base_settings,
        general=replace(
            base_settings.general,
            collection_name=collection_name,
            delete_old=True,
            randomize_seed_each_build=False,
            seed=seed,
        ),
        shape=replace(
            base_settings.shape,
            shape_mode=shape_mode,
            house_scale=scale_hint,
            target_room_count=target_rooms,
        ),
        stories=replace(
            base_settings.stories,
            story_count=story_count,
            vertical_profile_mode=profile_mode,
            profile_strength=profile_strength,
        ),
    )


def _collection_bounds(collection: bpy.types.Collection) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []
    for obj in iter_collection_objects_recursive(collection):
        if getattr(obj, "bound_box", None) is None:
            continue
        if bool(obj.get("game_rect_grid_preview", False)) or bool(obj.get("floorplan_debug", False)):
            continue
        matrix = obj.matrix_world
        for corner in obj.bound_box:
            point = matrix @ Vector(corner)
            points.append((point.x, point.y))
    if not points:
        return None
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _top_level_objects(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    objects = list(iter_collection_objects_recursive(collection))
    own_keys = {obj.as_pointer() for obj in objects}
    return [obj for obj in objects if obj.parent is None or obj.parent.as_pointer() not in own_keys]


def _place_collection_at_region(collection: bpy.types.Collection, region: TerrainRegion, mask: TerrainMask) -> None:
    bounds = _collection_bounds(collection)
    if bounds is None:
        return
    target_x, target_y = mask.cell_center_world(region.centroid_px[0], region.centroid_px[1])
    current_x = (bounds[0] + bounds[2]) * 0.5
    current_y = (bounds[1] + bounds[3]) * 0.5
    shift = Matrix.Translation((target_x - current_x, target_y - current_y, 0.0))
    for obj in _top_level_objects(collection):
        obj.matrix_world = shift @ obj.matrix_world


def _tag_building_collection(collection: bpy.types.Collection, terrain_root_name: str, region_index: int) -> None:
    collection["terrain_scene_id"] = terrain_root_name
    collection["terrain_region_id"] = int(region_index)
    collection["terrain_zone"] = "building"
    collection["terrain_generated_by"] = "terrain_scene_generator"
    for obj in iter_collection_objects_recursive(collection):
        obj["terrain_scene_id"] = terrain_root_name
        obj["terrain_region_id"] = int(region_index)
        obj["terrain_zone"] = "building"
        obj["terrain_generated_by"] = "terrain_scene_generator"

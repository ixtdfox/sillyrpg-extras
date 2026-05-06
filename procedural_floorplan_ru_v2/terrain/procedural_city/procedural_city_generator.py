from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import bpy

from ..collection_utils import delete_collection_tree, ensure_terrain_scene_collections, validate_generated_buildings_parent
from .asset_library import ProceduralCityAssetLibrary
from .layout import generate_city_layout, plan_prop_points
from .parcel_to_building import collection_bbox, generate_buildings_for_parcels
from .prop_placer import place_city_props
from .road_generator import create_city_surface_materials, create_debug_bounds, generate_city_surfaces


class ProceduralCityGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProceduralCityGenerationStats:
    buildings_created: int = 0
    buildings_requested: int = 0
    building_reservations: int = 0
    buildings_preflight_rejected: int = 0
    buildings_relocated: int = 0
    buildings_rejected: int = 0
    blocks_created: int = 0
    parcels_created: int = 0
    road_objects: int = 0
    sidewalk_objects: int = 0
    curb_objects: int = 0
    crosswalk_objects: int = 0
    cars_created: int = 0
    trees_created: int = 0
    street_furniture_created: int = 0
    traffic_lights_created: int = 0
    asset_counts: dict[str, int] | None = None
    warnings: tuple[str, ...] = ()


class ProceduralCityGenerator:
    def generate(self, context, props, settings, progress=None) -> ProceduralCityGenerationStats:
        total_started = perf_counter()
        _progress_set(progress, 5, "Validating procedural city settings", report=True)
        self._validate(settings)

        prepare_started = perf_counter()
        _progress_set(progress, 10, "Preparing terrain scene collections", report=True)
        collections = ensure_terrain_scene_collections(context.scene, settings.collection_name, delete_old=settings.delete_old)
        collections["asset_library_hidden"].hide_viewport = True
        collections["asset_library_hidden"].hide_render = True
        print(f"[ProceduralCity][Perf] prepare_collections: {perf_counter() - prepare_started:.2f}s")

        _progress_set(progress, 20, "Generating city layout", report=True)
        planning_started = perf_counter()
        workers_used = 1
        planning_mode = "single"
        try:
            if settings.use_multiprocessing:
                planning_mode = "multiprocessing"
                workers_used = settings.worker_count if settings.worker_count > 0 else 0
                layout = generate_city_layout(settings, use_multiprocessing=True, worker_count=settings.worker_count)
                prop_plan = plan_prop_points(layout, settings, use_multiprocessing=True, worker_count=settings.worker_count)
            else:
                layout = generate_city_layout(settings, use_multiprocessing=False, worker_count=0)
                prop_plan = plan_prop_points(layout, settings, use_multiprocessing=False, worker_count=0)
        except Exception as exc:
            print(f"[ProceduralCity] multiprocessing planning failed, falling back to single process: {exc}")
            planning_mode = "fallback_single"
            workers_used = 1
            layout = generate_city_layout(settings, use_multiprocessing=False, worker_count=0)
            prop_plan = plan_prop_points(layout, settings, use_multiprocessing=False, worker_count=0)
        print(f"[ProceduralCity][Perf] planning: {perf_counter() - planning_started:.2f}s workers={workers_used} mode={planning_mode}")

        _progress_set(progress, 35, "Generating roads, sidewalks, curbs and crossings", report=True)
        terrain_started = perf_counter()
        surface_counts = generate_city_surfaces(collections=collections, layout=layout, settings=settings, scene_id=settings.collection_name)
        print(f"[ProceduralCity][Perf] terrain_meshes: {perf_counter() - terrain_started:.2f}s")

        _progress_set(progress, 35, f"Generating buildings 0/{len(layout.parcels)}", report=True)
        buildings_started = perf_counter()
        building_collections = generate_buildings_for_parcels(
            scene=context.scene,
            props=props,
            layout=layout,
            settings=settings,
            buildings_collection=collections["buildings"],
            debug_collection=collections["debug"],
            scene_id=settings.collection_name,
            progress=progress,
            progress_start=35,
            progress_end=80,
        )
        print(f"[ProceduralCity][Perf] buildings: {perf_counter() - buildings_started:.2f}s count={len(building_collections)} editable=True")
        building_stats = getattr(generate_buildings_for_parcels, "_last_stats", {})
        building_bounds = [bbox for collection in building_collections if (bbox := collection_bbox(collection)) is not None]

        asset_counts: dict[str, int] = {}
        warnings: list[str] = []
        prop_counts = {"cars": 0, "trees": 0, "street_furniture": 0, "traffic_lights": 0}
        _progress_set(progress, 84, "Loading city prop assets", report=True)
        asset_library = ProceduralCityAssetLibrary(settings.assets_root, collections["asset_library_hidden"])
        asset_counts = dict(asset_library.asset_counts)
        warnings.extend(asset_library.warnings)
        print(f"[TerrainProgress] Assets root: {asset_library.assets_root}")
        print(
            "[TerrainProgress] Found assets: "
            f"cars={asset_counts.get('cars', 0)} "
            f"trees={asset_counts.get('trees', 0)} "
            f"tropicalTrees={asset_counts.get('trees_tropical', 0)} "
            f"streetFurniture={asset_counts.get('street_furniture', 0)} "
            f"trafficLights={asset_counts.get('traffic_lights', 0)}"
        )
        if settings.include_trees and (asset_counts.get("trees", 0) + asset_counts.get("trees_tropical", 0) <= 0):
            warnings.append("Trees enabled but no tree assets found. Check terrain_bpy_city_assets_root. It can point either to bpy-city or bpy-city/assets.")
        if asset_library.has_assets():
            _progress_set(progress, 90, "Placing trees and props", report=True)
            props_started = perf_counter()
            prop_counts = place_city_props(
                layout=layout,
                settings=settings,
                asset_library=asset_library,
                collections=collections,
                scene_id=settings.collection_name,
                building_bounds=building_bounds,
                prop_plan=prop_plan,
            )
            print(
                f"[ProceduralCity][Perf] props: {perf_counter() - props_started:.2f}s "
                f"linked_duplicates=True count={sum(prop_counts.values())}"
            )
        if asset_library.import_failures:
            warnings.append(f"Asset import failures: {len(asset_library.import_failures)}")
        print(
            "[TerrainProgress] Placed props: "
            f"cars={prop_counts['cars']} trees={prop_counts['trees']} "
            f"streetFurniture={prop_counts['street_furniture']} trafficLights={prop_counts['traffic_lights']}"
        )

        if settings.generate_debug_markers:
            _progress_set(progress, 95, "Creating debug markers", report=True)
            self._create_debug_overlays(collections["debug"], layout, settings.collection_name, building_bounds)

        _progress_set(progress, 100, "Writing terrain metadata", report=True)
        root = collections["root"]
        root["terrain_environment_type"] = "city"
        root["terrain_generation_mode"] = "procedural_city"
        root["terrain_generated_by"] = "procedural_city_generator"
        root["terrain_seed"] = int(settings.seed)
        root["terrain_city_width_blocks"] = int(settings.width_blocks)
        root["terrain_city_depth_blocks"] = int(settings.depth_blocks)
        root["terrain_buildings_requested"] = int(building_stats.get("requested", len(building_collections)))
        root["terrain_building_reservations"] = int(building_stats.get("reservations", len(building_collections)))
        root["terrain_buildings_preflight_rejected"] = int(building_stats.get("preflight_rejected_no_fit", 0) + building_stats.get("preflight_rejected_overlap", 0))
        root["terrain_buildings_final_rejected"] = int(building_stats.get("final_rejected_after_mesh", 0))
        root["terrain_buildings_placed"] = int(building_stats.get("placed", len(building_collections)))
        root["terrain_buildings_relocated"] = int(building_stats.get("relocated", 0))
        root["terrain_buildings_rejected"] = int(
            building_stats.get("preflight_rejected_no_fit", 0)
            + building_stats.get("preflight_rejected_overlap", 0)
            + building_stats.get("final_rejected_after_mesh", 0)
        )
        validate_generated_buildings_parent(context.scene, root, collections["buildings"])
        print(f"[terrain] Generated buildings: {len(building_collections)} collections under {root.name}/{collections['buildings'].name}")
        print(f"[ProceduralCity][Perf] total: {perf_counter() - total_started:.2f}s")
        return ProceduralCityGenerationStats(
            buildings_created=len(building_collections),
            buildings_requested=int(building_stats.get("requested", len(building_collections))),
            building_reservations=int(building_stats.get("reservations", len(building_collections))),
            buildings_preflight_rejected=int(building_stats.get("preflight_rejected_no_fit", 0) + building_stats.get("preflight_rejected_overlap", 0)),
            buildings_relocated=int(building_stats.get("relocated", 0)),
            buildings_rejected=int(
                building_stats.get("preflight_rejected_no_fit", 0)
                + building_stats.get("preflight_rejected_overlap", 0)
                + building_stats.get("final_rejected_after_mesh", 0)
            ),
            blocks_created=len(layout.blocks),
            parcels_created=len(layout.parcels),
            road_objects=surface_counts["roads"] + surface_counts["intersections"] + surface_counts["lane_marks"],
            sidewalk_objects=surface_counts["sidewalks"],
            curb_objects=surface_counts["curbs"],
            crosswalk_objects=surface_counts["crosswalks"],
            cars_created=prop_counts["cars"],
            trees_created=prop_counts["trees"],
            street_furniture_created=prop_counts["street_furniture"],
            traffic_lights_created=prop_counts["traffic_lights"],
            asset_counts=asset_counts,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def clear(self, scene, collection_name: str) -> bool:
        root = bpy.data.collections.get(str(collection_name))
        if root is None:
            return False
        started = perf_counter()
        objects = list(_iter_collection_objects(root))
        collections = list(_iter_collection_tree(root))
        delete_collection_tree(root)
        print(f"[ProceduralCity][Perf] clear_scene: {perf_counter() - started:.2f}s objects={len(objects)} collections={len(collections)}")
        return True

    def _validate(self, settings) -> None:
        if settings.width_blocks < 1 or settings.depth_blocks < 1:
            raise ProceduralCityGenerationError("City width/depth blocks должны быть >= 1")
        if settings.block_size_tiles <= 0:
            raise ProceduralCityGenerationError("terrain_block_size_tiles должен быть больше нуля")
        if settings.road_width_tiles <= 0:
            raise ProceduralCityGenerationError("terrain_road_width_tiles должен быть больше нуля")
        if settings.sidewalk_width_tiles < 0:
            raise ProceduralCityGenerationError("terrain_sidewalk_width_tiles не может быть отрицательным")
        if settings.min_stories < 1:
            raise ProceduralCityGenerationError("terrain_building_min_stories должен быть >= 1")
        if settings.max_stories < settings.min_stories:
            raise ProceduralCityGenerationError("terrain_building_max_stories должен быть >= terrain_building_min_stories")

    def _create_debug_overlays(self, collection: bpy.types.Collection, layout, scene_id: str, building_bounds: list[tuple[float, float, float, float]]) -> None:
        materials = create_city_surface_materials()
        origin = bpy.data.objects.new("CityGridOrigin", None)
        origin.empty_display_type = "PLAIN_AXES"
        origin.location = (0.0, 0.0, 0.2)
        origin["floorplan_debug"] = True
        origin["terrain_role"] = "debug_origin"
        origin["terrain_scene_id"] = scene_id
        collection.objects.link(origin)
        for road in layout.roads:
            create_debug_bounds(
                collection=collection,
                name=f"DebugRoad_{road.segment_id}",
                x=road.x,
                y=road.y,
                width=road.width,
                depth=road.depth,
                z=0.01,
                material=materials["debug_road"],
                role="debug_road",
                scene_id=scene_id,
            )
        for block in layout.blocks:
            create_debug_bounds(
                collection=collection,
                name=f"DebugBlock_{block.block_id:03d}",
                x=block.x,
                y=block.y,
                width=block.width,
                depth=block.depth,
                z=0.025,
                material=materials["debug_block"],
                role="debug_block",
                scene_id=scene_id,
            )
        for parcel in layout.parcels:
            create_debug_bounds(
                collection=collection,
                name=f"DebugParcel_{parcel.parcel_id:03d}",
                x=parcel.x,
                y=parcel.y,
                width=parcel.width,
                depth=parcel.depth,
                z=0.04,
                material=materials["debug_parcel"],
                role="debug_parcel",
                scene_id=scene_id,
            )
        for index, bounds in enumerate(building_bounds):
            create_debug_bounds(
                collection=collection,
                name=f"DebugBuildingBBox_{index:03d}",
                x=bounds[0],
                y=bounds[1],
                width=bounds[2] - bounds[0],
                depth=bounds[3] - bounds[1],
                z=0.055,
                material=materials["debug_building"],
                role="debug_building_bbox",
                scene_id=scene_id,
            )


def _progress_set(progress, percent: int, label: str, report: bool = False) -> None:
    if progress is not None:
        progress.update(percent, label=label, report=report)


def _iter_collection_tree(collection: bpy.types.Collection):
    yield collection
    for child in collection.children:
        yield from _iter_collection_tree(child)


def _iter_collection_objects(collection: bpy.types.Collection):
    for obj in collection.objects:
        yield obj
    for child in collection.children:
        yield from _iter_collection_objects(child)

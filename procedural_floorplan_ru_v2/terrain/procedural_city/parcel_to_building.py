from __future__ import annotations

import math
import random
from dataclasses import replace

import bpy
from mathutils import Matrix, Vector

from ...building_manager import settings_from_props
from ...building_stories_manager import BuildingStoriesManager
from ...common.utils import ensure_child_collection
from ...config import GenerationSettings
from ...game_grid import GAME_TILE_SIZE_M, snap_value_to_game_grid
from ...planning.shape_footprint_generator import ShapeFootprintGenerator
from ..collection_utils import delete_collection_tree, iter_collection_objects_recursive, relink_collection
from .building_plan import BuildingCandidate, BuildingReservation
from .placement_validator import (
    PlacementRegistry,
    Rect,
    clamp_rect_translation_into,
    rect_contains,
    rect_depth,
    rect_from_intersection,
    rect_from_parcel,
    rect_from_road,
    rect_translate,
    rects_overlap,
    rect_width,
)


SHAPE_OPTIONS = ("rectangle", "l_shape", "u_shape", "h_shape", "t_shape", "courdoner", "offset")
PROFILE_OPTIONS = ("strict", "setback", "offset_stack", "pinwheel", "mixed")
COMPACT_PROFILE_OPTIONS = ("strict", "setback")
MAX_FINAL_ATTEMPTS = 4


def generate_buildings_for_parcels(
    *,
    scene: bpy.types.Scene,
    props,
    layout,
    settings,
    buildings_collection: bpy.types.Collection,
    debug_collection: bpy.types.Collection | None,
    scene_id: str,
    progress=None,
    progress_start: int = 35,
    progress_end: int = 80,
) -> list[bpy.types.Collection]:
    base_settings = settings_from_props(props)
    rng = random.Random(int(settings.seed) + 101)
    shape_footprint_generator = ShapeFootprintGenerator()
    total_parcels = max(1, len(layout.parcels))
    spacing_m = float(settings.building_spacing_tiles) * float(GAME_TILE_SIZE_M)
    forbidden = [rect_from_road(road) for road in layout.roads] + [rect_from_intersection(patch) for patch in layout.intersections]

    reservations, preflight_stats = _plan_building_reservations(
        base_settings=base_settings,
        layout=layout,
        settings=settings,
        scene_id=scene_id,
        rng=rng,
        shape_footprint_generator=shape_footprint_generator,
        forbidden=forbidden,
        spacing_m=spacing_m,
        progress=progress,
        progress_start=progress_start,
        progress_end=min(progress_end, progress_start + (progress_end - progress_start) // 2),
        total_parcels=total_parcels,
    )

    collections: list[bpy.types.Collection] = []
    final_registry = PlacementRegistry(placed_buildings=[], forbidden=forbidden, spacing_m=spacing_m)
    placed_parcel_ids: set[int] = set()
    final_stats = {
        "final_rejected_after_mesh": 0,
        "final_rejected_bbox_too_large": 0,
        "final_rejected_overlap": 0,
        "final_rejected_forbidden": 0,
        "final_rejected_no_bbox": 0,
        "final_retried_compact": 0,
        "final_salvaged_by_translate": 0,
        "final_salvaged_by_scale": 0,
        "final_relocated": 0,
        "placed": 0,
    }
    mesh_progress_start = min(progress_end, progress_start + (progress_end - progress_start) // 2)
    mesh_total = max(1, len(reservations))
    for reservation_index, reservation in enumerate(reservations, start=1):
        if progress is not None:
            percent = mesh_progress_start + int(round((progress_end - mesh_progress_start) * (reservation_index / mesh_total)))
            progress.update(percent, label=f"Generating accepted buildings {reservation_index}/{mesh_total}", report=False)

        placed = _place_building_from_reservation_plan(
            scene=scene,
            base_settings=base_settings,
            layout=layout,
            settings=settings,
            shape_footprint_generator=shape_footprint_generator,
            source_reservation=reservation,
            buildings_collection=buildings_collection,
            debug_collection=debug_collection,
            final_registry=final_registry,
            placed_parcel_ids=placed_parcel_ids,
            spacing_m=spacing_m,
            scene_id=scene_id,
            final_stats=final_stats,
        )
        if placed is None:
            continue
        collections.append(placed)

    if progress is not None:
        progress.update(progress_end, label=f"Buildings done {len(collections)}/{len(reservations)}", report=False)

    print(f"[ProceduralCity] building candidates requested: {preflight_stats['requested']}")
    print(f"[ProceduralCity] building reservations accepted: {len(reservations)}")
    print(f"[ProceduralCity] preflight rejected no_fit: {preflight_stats['preflight_rejected_no_fit']}")
    print(f"[ProceduralCity] preflight rejected overlap: {preflight_stats['preflight_rejected_overlap']}")
    print(f"[ProceduralCity] mesh generated: {len(reservations)}")
    print(f"[ProceduralCity] final rejected after mesh: {final_stats['final_rejected_after_mesh']}")
    print(f"[ProceduralCity] final rejected bbox too large: {final_stats['final_rejected_bbox_too_large']}")
    print(f"[ProceduralCity] final rejected overlap: {final_stats['final_rejected_overlap']}")
    print(f"[ProceduralCity] final rejected forbidden: {final_stats['final_rejected_forbidden']}")
    print(f"[ProceduralCity] final rejected no bbox: {final_stats['final_rejected_no_bbox']}")
    print(f"[ProceduralCity] final retried compact: {final_stats['final_retried_compact']}")
    print(f"[ProceduralCity] final salvaged by translate: {final_stats['final_salvaged_by_translate']}")
    print(f"[ProceduralCity] final salvaged by scale: {final_stats['final_salvaged_by_scale']}")
    print(f"[ProceduralCity] final relocated: {final_stats['final_relocated']}")
    print(f"[ProceduralCity] placed: {len(collections)}")
    setattr(
        generate_buildings_for_parcels,
        "_last_stats",
        {
            "requested": preflight_stats["requested"],
            "reservations": len(reservations),
            "preflight_rejected_no_fit": preflight_stats["preflight_rejected_no_fit"],
            "preflight_rejected_overlap": preflight_stats["preflight_rejected_overlap"],
            **final_stats,
            "relocated": final_stats["final_relocated"],
        },
    )
    return collections


def _place_building_from_reservation_plan(
    *,
    scene: bpy.types.Scene,
    base_settings: GenerationSettings,
    layout,
    settings,
    shape_footprint_generator: ShapeFootprintGenerator,
    source_reservation: BuildingReservation,
    buildings_collection: bpy.types.Collection,
    debug_collection: bpy.types.Collection | None,
    final_registry: PlacementRegistry,
    placed_parcel_ids: set[int],
    spacing_m: float,
    scene_id: str,
    final_stats: dict[str, int],
) -> bpy.types.Collection | None:
    source_parcel = _parcel_by_id(layout.parcels, source_reservation.candidate.source_parcel_id)
    attempts = _build_attempt_candidates(
        base_settings=base_settings,
        source_candidate=source_reservation.candidate,
        source_parcel=source_parcel,
        shape_footprint_generator=shape_footprint_generator,
        scene_id=scene_id,
        settings=settings,
    )
    for attempt_index, candidate in enumerate(attempts):
        if attempt_index > 0:
            final_stats["final_retried_compact"] += 1
        reservation, rejection_reason = _reserve_candidate(
            candidate=candidate,
            source_parcel=source_parcel,
            candidate_parcels=layout.parcels,
            registry=final_registry,
            used_parcel_ids=placed_parcel_ids,
            allow_move_to_other_parcel=bool(settings.allow_relocate_buildings and settings.avoid_building_overlaps),
            spacing_m=spacing_m,
        )
        if reservation is None:
            print(
                "[ProceduralCity][PlacementRetry]",
                f"parcel={source_parcel.parcel_id}",
                f"attempt={attempt_index}",
                f"policy={_attempt_policy_name(attempt_index)}",
                f"reason=preflight_{rejection_reason}",
            )
            continue

        generation_settings = _settings_from_candidate(base_settings=base_settings, candidate=reservation.candidate)
        manager = BuildingStoriesManager(generation_settings)
        building_context = manager.build(scene)
        collection = building_context.collection
        relink_collection(buildings_collection, collection, scene=scene)

        fit_result = _fit_collection_to_reservation(collection, reservation)
        if fit_result["scaled"]:
            final_stats["final_salvaged_by_scale"] += 1

        validation = _salvage_and_validate_collection(
            collection=collection,
            reservation=reservation,
            parcel=_parcel_by_id(layout.parcels, reservation.parcel_id),
            registry=final_registry,
            spacing_m=spacing_m,
        )
        if validation["translated"]:
            final_stats["final_salvaged_by_translate"] += 1

        actual_rect = validation["actual_rect"]
        reason = validation["reason"]
        if actual_rect is None or not validation["can_place"]:
            final_stats["final_rejected_after_mesh"] += 1
            if reason == "no_bbox":
                final_stats["final_rejected_no_bbox"] += 1
            elif reason == "bbox_too_large":
                final_stats["final_rejected_bbox_too_large"] += 1
            elif reason == "overlap":
                final_stats["final_rejected_overlap"] += 1
            else:
                final_stats["final_rejected_forbidden"] += 1
            print(
                "[ProceduralCity][BuildingReject]",
                f"collection={collection.name}",
                f"parcel={reservation.parcel_id}",
                f"attempt={attempt_index}",
                f"policy={_attempt_policy_name(attempt_index)}",
                f"reason={reason}",
                f"reservation={_format_rect(reservation.rect)}",
                f"allowed={_format_rect(validation['allowed_area'])}",
                f"actual={_format_rect(actual_rect) if actual_rect is not None else None}",
                f"containsAllowed={validation['contains_allowed']}",
                f"canPlaceFinal={validation['can_place']}",
            )
            _reject_building_collection(
                collection,
                reason=reason,
                debug_collection=debug_collection,
                scene=scene,
                keep_rejected=bool(settings.keep_rejected_buildings),
            )
            continue

        final_registry.reserve(actual_rect)
        placed_parcel_ids.add(int(reservation.parcel_id))
        _tag_collection(collection, _parcel_by_id(layout.parcels, reservation.parcel_id), scene_id)
        collection["terrain_placement_status"] = "placed"
        collection["terrain_preflight_reserved"] = True
        collection["terrain_original_parcel_id"] = int(source_reservation.candidate.source_parcel_id)
        collection["terrain_final_parcel_id"] = int(reservation.parcel_id)
        collection["terrain_relocated"] = bool(reservation.relocated)
        collection["terrain_estimated_width_tiles"] = int(reservation.candidate.footprint_width_tiles)
        collection["terrain_estimated_depth_tiles"] = int(reservation.candidate.footprint_depth_tiles)
        collection["terrain_actual_bbox_width_m"] = float(rect_width(actual_rect))
        collection["terrain_actual_bbox_depth_m"] = float(rect_depth(actual_rect))
        collection["terrain_fit_policy"] = _attempt_policy_name(attempt_index)
        collection["terrain_fit_margin_m"] = float(reservation.candidate.placement_margin_m)
        collection["terrain_fit_frontage_extra_m"] = float(reservation.candidate.frontage_extra_m)
        final_stats["placed"] += 1
        if reservation.relocated:
            final_stats["final_relocated"] += 1
        return collection

    return None


def _build_attempt_candidates(
    *,
    base_settings: GenerationSettings,
    source_candidate: BuildingCandidate,
    source_parcel,
    shape_footprint_generator: ShapeFootprintGenerator,
    scene_id: str,
    settings,
) -> list[BuildingCandidate]:
    candidates = [source_candidate]
    for attempt_index in range(1, MAX_FINAL_ATTEMPTS):
        compact = _candidate_for_parcel(
            base_settings=base_settings,
            parcel=source_parcel,
            building_index=source_candidate.building_index,
            rng=random.Random(int(settings.seed) + source_parcel.parcel_id * 9973 + attempt_index * 53),
            scene_id=scene_id,
            settings=settings,
            shape_footprint_generator=shape_footprint_generator,
            size_policy=_attempt_policy_name(attempt_index),
        )
        candidates.append(compact)
    return candidates


def _attempt_policy_name(attempt_index: int) -> str:
    return {
        0: "normal",
        1: "compact",
        2: "tiny",
        3: "relocate_compact",
    }.get(attempt_index, f"retry_{attempt_index}")


def _plan_building_reservations(
    *,
    base_settings: GenerationSettings,
    layout,
    settings,
    scene_id: str,
    rng: random.Random,
    shape_footprint_generator: ShapeFootprintGenerator,
    forbidden: list[Rect],
    spacing_m: float,
    progress,
    progress_start: int,
    progress_end: int,
    total_parcels: int,
) -> tuple[list[BuildingReservation], dict[str, int]]:
    registry = PlacementRegistry(placed_buildings=[], forbidden=forbidden, spacing_m=spacing_m)
    reservations: list[BuildingReservation] = []
    used_parcel_ids: set[int] = set()
    requested = 0
    rejected_no_fit = 0
    rejected_overlap = 0
    building_index = 0
    for parcel_index, parcel in enumerate(layout.parcels, start=1):
        if progress is not None:
            percent = progress_start + int(round((progress_end - progress_start) * (parcel_index / total_parcels)))
            progress.update(percent, label=f"Planning building reservations {parcel_index}/{total_parcels}", report=False)
        if rng.random() > settings.building_density:
            continue
        requested += 1
        building_index += 1
        candidate = _candidate_for_parcel(
            base_settings=base_settings,
            parcel=parcel,
            building_index=building_index,
            rng=rng,
            scene_id=scene_id,
            settings=settings,
            shape_footprint_generator=shape_footprint_generator,
            size_policy="normal",
        )
        reservation, rejection_reason = _reserve_candidate(
            candidate=candidate,
            source_parcel=parcel,
            candidate_parcels=layout.parcels,
            registry=registry,
            used_parcel_ids=used_parcel_ids,
            allow_move_to_other_parcel=bool(settings.allow_relocate_buildings and settings.avoid_building_overlaps),
            spacing_m=spacing_m,
        )
        if reservation is None:
            if rejection_reason == "overlap":
                rejected_overlap += 1
            else:
                rejected_no_fit += 1
            continue
        reservations.append(reservation)
        registry.reserve(reservation.rect)
        used_parcel_ids.add(int(reservation.parcel_id))
    return reservations, {
        "requested": requested,
        "preflight_rejected_no_fit": rejected_no_fit,
        "preflight_rejected_overlap": rejected_overlap,
    }


def _candidate_for_parcel(
    *,
    base_settings: GenerationSettings,
    parcel,
    building_index: int,
    rng: random.Random,
    scene_id: str,
    settings,
    shape_footprint_generator: ShapeFootprintGenerator,
    size_policy: str = "normal",
) -> BuildingCandidate:
    spacing_m = float(settings.building_spacing_tiles) * float(GAME_TILE_SIZE_M)
    allowed_width_m = max(GAME_TILE_SIZE_M * 3.0, float(parcel.width) - spacing_m * 2.0)
    allowed_depth_m = max(GAME_TILE_SIZE_M * 3.0, float(parcel.depth) - spacing_m * 2.0)
    allowed_width_tiles = max(3.0, allowed_width_m / float(GAME_TILE_SIZE_M))
    allowed_depth_tiles = max(3.0, allowed_depth_m / float(GAME_TILE_SIZE_M))
    target_area_tiles = max(1.0, allowed_width_tiles * allowed_depth_tiles)
    if size_policy == "normal":
        room_scale_options = (1.0, 0.85, 0.7, 0.55)
        house_scale_options = (1.0, 0.9, 0.8, 0.7)
        allowed_shapes = list(SHAPE_OPTIONS)
        profile_options = PROFILE_OPTIONS
    elif size_policy in {"compact", "relocate_compact"}:
        room_scale_options = (0.8, 0.65, 0.5)
        house_scale_options = (0.85, 0.75, 0.65)
        allowed_shapes = ["rectangle", "l_shape", "offset"]
        profile_options = COMPACT_PROFILE_OPTIONS
    else:
        room_scale_options = (0.6, 0.45)
        house_scale_options = (0.7, 0.6, 0.5)
        allowed_shapes = ["rectangle"]
        profile_options = ("strict",)

    target_rooms = max(1 if size_policy != "normal" else 2, min(10, int(round(target_area_tiles / (20.0 if size_policy == "normal" else 24.0)))))
    scale_hint = max(0.5 if size_policy != "normal" else 0.55, min(1.05, min(allowed_width_tiles, allowed_depth_tiles) / (6.8 if size_policy == "normal" else 7.4)))
    min_room_side = min(float(base_settings.shape.min_room_side_m), 2.0 if size_policy == "normal" else 1.75)
    if size_policy == "tiny":
        min_room_side = min(min_room_side, 1.5)
    story_low = max(settings.min_stories, parcel.min_stories)
    story_high = min(settings.max_stories, parcel.max_stories)
    if size_policy == "tiny":
        story_high = min(story_high, max(1, story_low))
    elif size_policy in {"compact", "relocate_compact"}:
        story_high = min(story_high, max(story_low, settings.max_stories - 1))
    story_count = rng.randint(story_low, max(story_low, story_high))
    profile_mode = rng.choice(profile_options if story_count > 2 else tuple(mode for mode in profile_options if mode != "mixed") or ("strict",))
    profile_strength = 0.0 if profile_mode == "strict" else rng.uniform(0.15, 0.65 if size_policy != "normal" else 0.85)
    seed = int(settings.seed) + parcel.parcel_id * 9973
    collection_name = f"{scene_id}_Building_{building_index:03d}_block_{parcel.block_id}_{parcel.parcel_id}"
    shape_order = list(allowed_shapes)
    rng.shuffle(shape_order)
    best_candidate: BuildingCandidate | None = None
    best_score: tuple[float, float, int] | None = None

    for shape_mode in shape_order:
        for room_scale in room_scale_options:
            for house_scale_factor in house_scale_options:
                candidate_rooms = max(1, int(round(target_rooms * room_scale)))
                candidate_scale = max(0.45, scale_hint * house_scale_factor)
                shape_settings = replace(
                    base_settings.shape,
                    shape_mode=shape_mode,
                    min_room_side_m=min_room_side,
                    house_scale=candidate_scale,
                    target_room_count=candidate_rooms,
                )
                footprint = shape_footprint_generator.build(shape_settings, seed=seed)
                min_x, min_y, max_x, max_y = footprint.bounds
                width_tiles = max_x - min_x + 1
                depth_tiles = max_y - min_y + 1
                candidate = _build_candidate(
                    base_settings=base_settings,
                    settings=settings,
                    building_index=building_index,
                    parcel_id=int(parcel.parcel_id),
                    seed=seed,
                    shape_mode=shape_mode,
                    story_count=story_count,
                    profile_mode=profile_mode,
                    profile_strength=profile_strength,
                    target_room_count=candidate_rooms,
                    house_scale=candidate_scale,
                    min_room_side_m=min_room_side,
                    collection_name=collection_name,
                    width_tiles=width_tiles,
                    depth_tiles=depth_tiles,
                )
                fits_direct = candidate.placement_width_m <= allowed_width_m and candidate.placement_depth_m <= allowed_depth_m
                fits_rotated = candidate.placement_depth_m <= allowed_width_m and candidate.placement_width_m <= allowed_depth_m
                if fits_direct or fits_rotated:
                    return candidate
                overflow = min(
                    max(0.0, candidate.placement_width_m - allowed_width_m) + max(0.0, candidate.placement_depth_m - allowed_depth_m),
                    max(0.0, candidate.placement_depth_m - allowed_width_m) + max(0.0, candidate.placement_width_m - allowed_depth_m),
                )
                area_delta = abs((candidate.placement_width_m * candidate.placement_depth_m) - (allowed_width_m * allowed_depth_m))
                score = (overflow, area_delta, candidate_rooms)
                if best_score is None or score < best_score:
                    best_score = score
                    best_candidate = candidate

    if best_candidate is not None:
        return best_candidate
    return _build_candidate(
        base_settings=base_settings,
        settings=settings,
        building_index=building_index,
        parcel_id=int(parcel.parcel_id),
        seed=seed,
        shape_mode="rectangle",
        story_count=story_count,
        profile_mode="strict",
        profile_strength=0.0,
        target_room_count=max(1, target_rooms),
        house_scale=scale_hint,
        min_room_side_m=min_room_side,
        collection_name=collection_name,
        width_tiles=max(1, int(round(allowed_width_tiles))),
        depth_tiles=max(1, int(round(allowed_depth_tiles))),
    )


def _build_candidate(
    *,
    base_settings: GenerationSettings,
    settings,
    building_index: int,
    parcel_id: int,
    seed: int,
    shape_mode: str,
    story_count: int,
    profile_mode: str,
    profile_strength: float,
    target_room_count: int,
    house_scale: float,
    min_room_side_m: float,
    collection_name: str,
    width_tiles: int,
    depth_tiles: int,
) -> BuildingCandidate:
    raw_width_m = float(width_tiles) * float(GAME_TILE_SIZE_M)
    raw_depth_m = float(depth_tiles) * float(GAME_TILE_SIZE_M)
    placement_margin_m, frontage_extra_m = _candidate_bbox_margin_m(
        base_settings=base_settings,
        story_count=story_count,
        profile_mode=profile_mode,
        profile_strength=profile_strength,
    )
    placement_width_m = raw_width_m + placement_margin_m * 2.0
    placement_depth_m = raw_depth_m + placement_margin_m * 2.0 + frontage_extra_m
    return BuildingCandidate(
        building_index=building_index,
        source_parcel_id=parcel_id,
        seed=seed,
        shape_mode=shape_mode,
        story_count=story_count,
        profile_mode=profile_mode,
        profile_strength=profile_strength,
        target_room_count=target_room_count,
        house_scale=house_scale,
        min_room_side_m=min_room_side_m,
        collection_name=collection_name,
        footprint_width_tiles=width_tiles,
        footprint_depth_tiles=depth_tiles,
        raw_width_m=raw_width_m,
        raw_depth_m=raw_depth_m,
        placement_width_m=placement_width_m,
        placement_depth_m=placement_depth_m,
        placement_margin_m=placement_margin_m,
        frontage_extra_m=frontage_extra_m,
        estimated_width_tiles=width_tiles,
        estimated_depth_tiles=depth_tiles,
        estimated_width_m=placement_width_m,
        estimated_depth_m=placement_depth_m,
    )


def _candidate_bbox_margin_m(
    *,
    base_settings: GenerationSettings,
    story_count: int,
    profile_mode: str,
    profile_strength: float,
) -> tuple[float, float]:
    wall_margin = max(0.2, float(base_settings.walls.wall_thickness) * 0.9)
    trim_margin = 0.18
    border_margin = float(base_settings.roof_border.depth) if base_settings.roof_border.enabled else 0.0
    railing_margin = float(base_settings.roof_railing.post_size) if base_settings.roof_railing.enabled else 0.0
    profile_margin = 0.0 if profile_mode == "strict" else 0.12 + (0.18 * float(profile_strength))
    terrace_margin = 0.15 if story_count > 1 and profile_mode != "strict" else 0.0
    placement_margin_m = round(wall_margin + trim_margin + border_margin + railing_margin + profile_margin + terrace_margin, 3)
    frontage_extra_m = 0.0
    if base_settings.stairs.enabled and base_settings.stairs.mode.value == "external" and story_count > 1:
        frontage_extra_m = round(
            max(
                0.75,
                min(1.75, float(base_settings.stairs.width) + float(base_settings.stairs.landing_size) * 0.35),
            ),
            3,
        )
    return placement_margin_m, frontage_extra_m


def _settings_from_candidate(*, base_settings: GenerationSettings, candidate: BuildingCandidate) -> GenerationSettings:
    return replace(
        base_settings,
        general=replace(
            base_settings.general,
            collection_name=candidate.collection_name,
            delete_old=True,
            randomize_seed_each_build=False,
            seed=candidate.seed,
        ),
        shape=replace(
            base_settings.shape,
            shape_mode=candidate.shape_mode,
            min_room_side_m=candidate.min_room_side_m,
            house_scale=candidate.house_scale,
            target_room_count=candidate.target_room_count,
        ),
        stories=replace(
            base_settings.stories,
            story_count=candidate.story_count,
            vertical_profile_mode=candidate.profile_mode,
            profile_strength=candidate.profile_strength,
        ),
    )


def collection_bbox(collection: bpy.types.Collection) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []
    for obj in iter_collection_objects_recursive(collection):
        if obj.type != "MESH":
            continue
        if getattr(obj, "bound_box", None) is None:
            continue
        if bool(obj.get("game_rect_grid_preview", False)) or bool(obj.get("floorplan_debug", False)):
            continue
        if bool(obj.get("building_root", False)) or bool(obj.get("nav_kind", "")) or bool(obj.get("nav_debug_kind", "")):
            continue
        if str(obj.get("building_part", obj.get("part", ""))).lower() in {"room_metadata", "visibility_volume"}:
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


def collection_rect(collection: bpy.types.Collection) -> Rect | None:
    bounds = collection_bbox(collection)
    if bounds is None:
        return None
    return Rect(bounds[0], bounds[1], bounds[2], bounds[3])


def _top_level_objects(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    objects = list(iter_collection_objects_recursive(collection))
    own = {obj.as_pointer() for obj in objects}
    return [obj for obj in objects if obj.parent is None or obj.parent.as_pointer() not in own]


def _fit_collection_to_reservation(collection: bpy.types.Collection, reservation: BuildingReservation) -> dict[str, float | bool]:
    bounds = collection_bbox(collection)
    if bounds is None:
        return {"scaled": False, "raw_scale": 1.0, "scale_factor": 1.0}
    target_width = max(GAME_TILE_SIZE_M, rect_width(reservation.rect))
    target_depth = max(GAME_TILE_SIZE_M, rect_depth(reservation.rect))
    current_width = max(0.01, bounds[2] - bounds[0])
    current_depth = max(0.01, bounds[3] - bounds[1])
    raw_scale = min(target_width / current_width, target_depth / current_depth)
    scale_factor = 1.0
    scaled = False
    if abs(raw_scale - 1.0) >= 0.03:
        scale_factor = max(0.75, min(1.35, round(raw_scale / 0.05) * 0.05))
        scaled = abs(scale_factor - 1.0) > 1e-6

    current_center_x = snap_value_to_game_grid((bounds[0] + bounds[2]) * 0.5)
    current_center_y = snap_value_to_game_grid((bounds[1] + bounds[3]) * 0.5)
    transform = Matrix.Translation((reservation.center_x, reservation.center_y, 0.0)) @ Matrix.Rotation(reservation.rotation_z, 4, "Z") @ Matrix.Scale(scale_factor, 4)
    inverse = Matrix.Translation((-current_center_x, -current_center_y, 0.0))
    matrix = transform @ inverse
    for obj in _top_level_objects(collection):
        obj.matrix_world = matrix @ obj.matrix_world
    _update_view_layer_for_bbox()
    rect = collection_rect(collection)
    collection["terrain_fit_raw_scale"] = float(raw_scale)
    collection["terrain_fit_scale"] = float(scale_factor)
    collection["terrain_fit_scaled"] = bool(scaled)
    collection["terrain_fit_shrunk"] = bool(scale_factor < 1.0 - 1e-6)
    if rect is not None:
        collection["terrain_actual_bbox_width_m"] = float(rect_width(rect))
        collection["terrain_actual_bbox_depth_m"] = float(rect_depth(rect))
    return {"scaled": scaled, "raw_scale": float(raw_scale), "scale_factor": float(scale_factor)}


def _salvage_and_validate_collection(
    *,
    collection: bpy.types.Collection,
    reservation: BuildingReservation,
    parcel,
    registry: PlacementRegistry,
    spacing_m: float,
) -> dict[str, object]:
    allowed_area = rect_from_parcel(parcel, inset_m=spacing_m)
    actual_rect = collection_rect(collection)
    translated = False
    contains_allowed = actual_rect is not None and rect_contains(allowed_area, actual_rect)
    if actual_rect is not None and not contains_allowed:
        translation = clamp_rect_translation_into(allowed_area, actual_rect)
        if translation is not None and (abs(translation[0]) > 1e-5 or abs(translation[1]) > 1e-5):
            _translate_collection(collection, translation[0], translation[1])
            _update_view_layer_for_bbox()
            actual_rect = collection_rect(collection)
            translated = True
            contains_allowed = actual_rect is not None and rect_contains(allowed_area, actual_rect)
            print(
                "[ProceduralCity][PlacementSalvage]",
                f"collection={collection.name}",
                "action=translate",
                f"dx={translation[0]:.2f}",
                f"dy={translation[1]:.2f}",
                f"actualAfter={_format_rect(actual_rect) if actual_rect is not None else None}",
            )
    can_place = actual_rect is not None and contains_allowed and registry.can_place(actual_rect, allowed_area=allowed_area)
    reason = "placed"
    if actual_rect is None:
        reason = "no_bbox"
    elif not contains_allowed:
        reason = "bbox_too_large"
    elif not can_place:
        if any(rects_overlap(actual_rect, forbidden) for forbidden in registry.forbidden):
            reason = "forbidden"
        else:
            reason = "overlap"
    return {
        "allowed_area": allowed_area,
        "actual_rect": actual_rect,
        "contains_allowed": contains_allowed,
        "can_place": can_place,
        "translated": translated,
        "reason": reason,
    }


def _translate_collection(collection: bpy.types.Collection, dx: float, dy: float) -> None:
    offset = Matrix.Translation((float(dx), float(dy), 0.0))
    for obj in _top_level_objects(collection):
        obj.matrix_world = offset @ obj.matrix_world


def _reserve_candidate(
    *,
    candidate: BuildingCandidate,
    source_parcel,
    candidate_parcels,
    registry: PlacementRegistry,
    used_parcel_ids: set[int],
    allow_move_to_other_parcel: bool,
    spacing_m: float,
) -> tuple[BuildingReservation | None, str]:
    ordered = _ordered_candidate_parcels(source_parcel, candidate_parcels, used_parcel_ids, allow_move_to_other_parcel)
    saw_fit = False
    for parcel in ordered:
        rotation_z = _frontage_rotation(parcel.frontage_direction)
        estimated_width_m, estimated_depth_m = _candidate_dimensions_for_rotation(candidate, rotation_z)
        allowed = rect_from_parcel(parcel, inset_m=spacing_m)
        if estimated_width_m > rect_width(allowed) or estimated_depth_m > rect_depth(allowed):
            continue
        saw_fit = True
        center_x, center_y = _allowed_center(allowed)
        rect = Rect(
            center_x - estimated_width_m * 0.5,
            center_y - estimated_depth_m * 0.5,
            center_x + estimated_width_m * 0.5,
            center_y + estimated_depth_m * 0.5,
        )
        translation = clamp_rect_translation_into(allowed, rect)
        if translation is not None and (abs(translation[0]) > 1e-5 or abs(translation[1]) > 1e-5):
            rect = rect_translate(rect, translation[0], translation[1])
            center_x += translation[0]
            center_y += translation[1]
        if registry.can_place(rect, allowed_area=allowed):
            return (
                BuildingReservation(
                    candidate=candidate,
                    parcel_id=int(parcel.parcel_id),
                    rect=rect,
                    center_x=center_x,
                    center_y=center_y,
                    rotation_z=rotation_z,
                    relocated=bool(int(parcel.parcel_id) != int(source_parcel.parcel_id)),
                ),
                "placed",
            )
    return None, "overlap" if saw_fit else "no_fit"


def _allowed_center(allowed: Rect) -> tuple[float, float]:
    return (
        snap_value_to_game_grid((allowed.min_x + allowed.max_x) * 0.5),
        snap_value_to_game_grid((allowed.min_y + allowed.max_y) * 0.5),
    )


def _ordered_candidate_parcels(source_parcel, candidate_parcels, used_parcel_ids: set[int], allow_move_to_other_parcel: bool):
    source_center_x = float(source_parcel.x + source_parcel.width * 0.5)
    source_center_y = float(source_parcel.y + source_parcel.depth * 0.5)
    free_parcels = [parcel for parcel in candidate_parcels if int(parcel.parcel_id) not in used_parcel_ids]
    free_parcels.sort(
        key=lambda parcel: (
            0 if int(parcel.parcel_id) == int(source_parcel.parcel_id) else 1,
            (float(parcel.x + parcel.width * 0.5) - source_center_x) ** 2 + (float(parcel.y + parcel.depth * 0.5) - source_center_y) ** 2,
            int(parcel.parcel_id),
        )
    )
    if allow_move_to_other_parcel:
        return free_parcels
    return [parcel for parcel in free_parcels if int(parcel.parcel_id) == int(source_parcel.parcel_id)]


def _candidate_dimensions_for_rotation(candidate: BuildingCandidate, rotation_z: float) -> tuple[float, float]:
    quarter_turn = abs(abs(rotation_z) % math.pi - (math.pi * 0.5)) < 1e-4
    if quarter_turn:
        return candidate.placement_depth_m, candidate.placement_width_m
    return candidate.placement_width_m, candidate.placement_depth_m


def _parcel_by_id(parcels, parcel_id: int):
    for parcel in parcels:
        if int(parcel.parcel_id) == int(parcel_id):
            return parcel
    raise KeyError(parcel_id)


def _frontage_rotation(frontage_direction: str) -> float:
    return {
        "south": 0.0,
        "north": math.pi,
        "east": math.pi * 0.5,
        "west": math.pi * 1.5,
    }.get(frontage_direction, 0.0)


def _tag_collection(collection: bpy.types.Collection, parcel, scene_id: str) -> None:
    collection["terrain_scene_id"] = scene_id
    collection["terrain_building_id"] = collection.name
    collection["terrain_block_id"] = int(parcel.block_id)
    collection["terrain_parcel_id"] = int(parcel.parcel_id)
    collection["terrain_generated_by"] = "procedural_city_generator"
    for obj in iter_collection_objects_recursive(collection):
        obj["terrain_scene_id"] = scene_id
        obj["terrain_building_id"] = collection.name
        obj["terrain_block_id"] = int(parcel.block_id)
        obj["terrain_parcel_id"] = int(parcel.parcel_id)
        obj["terrain_generated_by"] = "procedural_city_generator"


def _reject_building_collection(
    collection: bpy.types.Collection,
    *,
    reason: str,
    debug_collection: bpy.types.Collection | None,
    scene: bpy.types.Scene | None,
    keep_rejected: bool,
) -> None:
    collection["terrain_placement_status"] = "rejected"
    collection["terrain_rejection_reason"] = reason
    if keep_rejected and debug_collection is not None:
        rejected_parent = ensure_child_collection(debug_collection, "RejectedBuildings_Debug")
        relink_collection(rejected_parent, collection, scene=scene)
        collection.hide_viewport = True
        collection.hide_render = True
        for obj in iter_collection_objects_recursive(collection):
            obj.hide_viewport = True
            obj.hide_render = True
        return
    delete_collection_tree(collection)


def _update_view_layer_for_bbox() -> None:
    try:
        bpy.context.view_layer.update()
    except Exception as exc:
        print(f"[ProceduralCity] WARNING: failed to update depsgraph before bbox validation: {exc}")


def _format_rect(rect: Rect) -> str:
    return f"({rect.min_x:.2f},{rect.min_y:.2f})-({rect.max_x:.2f},{rect.max_y:.2f}) {rect_width(rect):.2f}x{rect_depth(rect):.2f}"

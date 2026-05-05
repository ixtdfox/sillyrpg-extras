from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable

import bpy

from .common.utils import ADDON_ID, ensure_child_collection, link_object
from .domain.stairs import ExternalStairPlacement, StairPlacement
from .game_grid import GAME_TILE_SIZE_M


NAV_COLLECTION_NAME = "Nav"
BUILDING_ROOT_NAME = "BuildingRoot"
CHECKPOINT_MATERIAL_NAME = "NAV_AcidGreen_Checkpoint"
PATH_PREVIEW_MATERIAL_NAME = "NAV_AcidGreen_PathPreview"
CHECKPOINT_RADIUS_M = 0.16
CHECKPOINT_THICKNESS_M = 0.025
SURFACE_OFFSET_M = 0.03
CENTERLINE_TOLERANCE_M = 0.45
VALID_CHECKPOINT_ROLES = {"floor_entry", "landing_center", "run_start", "run_mid", "run_end", "floor_exit"}
ROLE_ALIASES = {
    "entrance": "floor_entry",
    "exit": "floor_exit",
    "stair_entry": "run_start",
    "stair_exit": "run_end",
    "landing": "landing_center",
    "door_connector": "floor_exit",
}


@dataclass(frozen=True)
class StairNavPoint:
    location: tuple[float, float, float]
    role: str
    story_index: int
    vertical_phase: str


@dataclass(frozen=True)
class StairNavigationValidationResult:
    ok: bool
    warnings: tuple[str, ...]
    connector_count: int
    checkpoint_count: int


@dataclass(frozen=True)
class GameNavigationValidationResult:
    ok: bool
    warnings: tuple[str, ...]
    object_count: int
    blocker_count: int
    floor_count: int


def ensure_building_root(collection: bpy.types.Collection) -> bpy.types.Object:
    for obj in collection.objects:
        if bool(obj.get("building_root", False)) and obj.get("generated_by") == ADDON_ID:
            _tag_building_grid_anchor(obj)
            return obj

    obj = bpy.data.objects.new(BUILDING_ROOT_NAME, None)
    obj.empty_display_type = "CUBE"
    obj.empty_display_size = 1.0
    obj["generated_by"] = ADDON_ID
    obj["building_root"] = True
    obj["building_root_kind"] = "floorplan_building_root"
    _tag_building_grid_anchor(obj)
    link_object(collection, obj)
    return obj


def _tag_building_grid_anchor(obj: bpy.types.Object) -> None:
    if "generation_grid_mode" not in obj:
        obj["generation_grid_mode"] = "SQUARE_LEGACY"
    if "generation_pipeline" not in obj:
        obj["generation_pipeline"] = "square_legacy"
    obj["building_grid_anchor"] = True
    obj["game_grid_origin_contract"] = "world_origin"
    obj["game_grid_plane_contract"] = "blender_xy_maps_to_game_xz"
    obj["grid_contract"] = "sillyrpg.grid_navigation.v3"
    obj["grid_type"] = "rect"
    obj["game_grid_contract"] = "rect_meter_grid"
    obj["building_tile_size_m"] = float(GAME_TILE_SIZE_M)
    obj["tile_size_m"] = float(GAME_TILE_SIZE_M)
    obj["origin_policy"] = "world_origin_integer_meter_grid"


def parent_objects_to_building_root(collection: bpy.types.Collection, objects: Iterable[bpy.types.Object]) -> bpy.types.Object:
    root = ensure_building_root(collection)
    for obj in objects:
        if obj is root or obj.parent is not None:
            continue
        obj.parent = root
    return root


def ensure_nav_collection(collection: bpy.types.Collection) -> bpy.types.Collection:
    return ensure_child_collection(collection, NAV_COLLECTION_NAME)


def create_internal_stair_navigation(context, placement: StairPlacement, *, stair_index: int) -> list[bpy.types.Object]:
    if not bool(getattr(context.settings.stairs, "generate_nav_checkpoints", True)):
        return []
    building_collection = _building_collection(context)
    root = ensure_building_root(building_collection)
    nav_collection = ensure_nav_collection(building_collection)
    stair_id = _stair_id(placement.from_story, placement.to_story, stair_index)
    if _existing_checkpoints(stair_id):
        return []
    path = _internal_checkpoint_path(context, placement)
    existing_connector = _existing_connector(stair_id)
    if existing_connector is not None:
        return _rebuild_connector_children(existing_connector, path, outside=False)
    return _create_stair_navigation_objects(
        nav_collection,
        root,
        stair_id=stair_id,
        from_story=placement.from_story,
        to_story=placement.to_story,
        stair_kind="internal",
        cost=max(2, len(path) - 1),
        path=path,
        outside=False,
    )


def create_external_stair_navigation(context, placement: ExternalStairPlacement, *, stair_index: int) -> list[bpy.types.Object]:
    if not bool(getattr(context.settings.stairs, "generate_nav_checkpoints", True)):
        return []
    if placement.switchback_placement is None or not placement.has_upward_flight:
        return []
    switchback = placement.switchback_placement
    building_collection = _building_collection(context)
    root = ensure_building_root(building_collection)
    nav_collection = ensure_nav_collection(building_collection)
    stair_id = _stair_id(switchback.from_story, switchback.to_story, stair_index)
    if _existing_checkpoints(stair_id):
        return []
    path = _external_checkpoint_path(context, placement)
    existing_connector = _existing_connector(stair_id)
    if existing_connector is not None:
        return _rebuild_connector_children(existing_connector, path, outside=True)
    return _create_stair_navigation_objects(
        nav_collection,
        root,
        stair_id=stair_id,
        from_story=switchback.from_story,
        to_story=switchback.to_story,
        stair_kind="external",
        cost=max(3, len(path) - 1),
        path=path,
        outside=True,
    )


def regenerate_existing_stair_navigation(collection: bpy.types.Collection) -> int:
    regenerated = 0
    connectors = [obj for obj in _iter_collection_objects_recursive(collection) if obj.get("nav_kind") == "stair_connector"]
    for connector in connectors:
        path = _path_from_connector(connector)
        if not path:
            continue
        _rebuild_connector_children(connector, path, outside=bool(connector.get("outside", False)))
        regenerated += 1
    return regenerated


def set_stair_navigation_visibility(collection: bpy.types.Collection, *, visible: bool) -> int:
    count = 0
    for obj in _iter_collection_objects_recursive(collection):
        if str(obj.get("nav_kind", "")):
            obj.hide_viewport = not visible
            obj.hide_set(not visible)
            obj.hide_render = False
            count += 1
        elif str(obj.get("nav_debug_kind", "")) == "stair_path_preview":
            obj.hide_viewport = not visible
            obj.hide_set(not visible)
            obj.hide_render = False
            count += 1
    return count


def set_selected_stair_navigation_visibility(collection: bpy.types.Collection, selected_objects: Iterable[bpy.types.Object]) -> tuple[int, str | None]:
    selected_stair_id = _selected_stair_id(selected_objects)
    if not selected_stair_id:
        return 0, None
    count = 0
    for obj in _iter_collection_objects_recursive(collection):
        if str(obj.get("nav_kind", "")) or str(obj.get("nav_debug_kind", "")) == "stair_path_preview":
            visible = str(obj.get("stair_id", "")) == selected_stair_id
            obj.hide_viewport = not visible
            obj.hide_set(not visible)
            obj.hide_render = False
            count += 1
    return count, selected_stair_id


def validate_stair_navigation(collection: bpy.types.Collection) -> StairNavigationValidationResult:
    warnings: list[str] = []
    connectors = [obj for obj in _iter_collection_objects_recursive(collection) if obj.get("nav_kind") == "stair_connector"]
    checkpoints = [obj for obj in _iter_collection_objects_recursive(collection) if obj.get("nav_kind") == "stair_checkpoint"]
    checkpoints_by_stair: dict[str, list[bpy.types.Object]] = {}
    for checkpoint in checkpoints:
        stair_id = str(checkpoint.get("stair_id", ""))
        if not stair_id:
            warnings.append(f"{checkpoint.name}: missing stair_id")
            continue
        checkpoints_by_stair.setdefault(stair_id, []).append(checkpoint)
        if "checkpoint_index" not in checkpoint:
            warnings.append(f"{checkpoint.name}: missing checkpoint_index")
        _migrate_checkpoint_role(checkpoint)

    for connector in connectors:
        connector_warnings_before = len(warnings)
        stair_id = str(connector.get("stair_id", ""))
        if not stair_id:
            warnings.append(f"{connector.name}: missing stair_id")
            continue
        if connector.get("nav_kind") != "stair_connector":
            warnings.append(f"{connector.name}: nav_kind must be stair_connector")
        cps = checkpoints_by_stair.get(stair_id, [])
        minimum = 5 if str(connector.get("stair_kind", "")) == "external" or bool(connector.get("nav_switchback", False)) else 3
        if len(cps) < minimum:
            warnings.append(f"{connector.name}: expected at least {minimum} checkpoints, found {len(cps)}")
            continue
        raw_indices = [int(cp.get("checkpoint_index", -1)) for cp in cps]
        duplicate_indices = sorted(index for index in set(raw_indices) if raw_indices.count(index) > 1)
        if duplicate_indices:
            warnings.append(f"{connector.name}: duplicate checkpoint indices {duplicate_indices}")
        indices = sorted(raw_indices)
        expected = list(range(len(cps)))
        if indices != expected:
            warnings.append(f"{connector.name}: checkpoint indices must be contiguous from 0, found {indices}")
        from_story = int(connector.get("from_story", 0))
        to_story = int(connector.get("to_story", from_story + 1))
        _validate_story_endpoint(cps, from_story, to_story, warnings)
        _validate_required_roles(connector, cps, warnings)
        _validate_segment_lengths(connector, cps, warnings)
        for cp in cps:
            if cp.parent is None or cp.parent != connector:
                warnings.append(f"{cp.name}: checkpoint must be parented to its stair connector")
            if cp.get("nav_kind") != "stair_checkpoint":
                warnings.append(f"{cp.name}: nav_kind must be stair_checkpoint")
            if str(cp.get("stair_id", "")) != stair_id:
                warnings.append(f"{cp.name}: stair_id does not match connector {stair_id}")
            if not bool(cp.get("hide_in_game", False)):
                warnings.append(f"{cp.name}: hide_in_game must be True")
            if not str(cp.get("checkpoint_role", "")):
                warnings.append(f"{cp.name}: missing checkpoint_role")
            elif str(cp.get("checkpoint_role", "")) not in VALID_CHECKPOINT_ROLES:
                warnings.append(f"{cp.name}: unsupported checkpoint_role {cp.get('checkpoint_role')}")
            if "story_index" not in cp:
                warnings.append(f"{cp.name}: missing story_index")
            _validate_centerline_distance(cp, warnings)
        if len(warnings) == connector_warnings_before:
            print(f"[StairNavigationValidation] OK: {stair_id}, {len(cps)} checkpoints")

    connector_ids = {str(obj.get("stair_id", "")) for obj in connectors}
    for stair_id, cps in checkpoints_by_stair.items():
        if stair_id not in connector_ids:
            warnings.append(f"stair_id={stair_id}: checkpoints exist without stair_connector")

    _validate_external_stair_visibility_metadata(collection, warnings)

    ok = not warnings
    return StairNavigationValidationResult(
        ok=ok,
        warnings=tuple(warnings),
        connector_count=len(connectors),
        checkpoint_count=len(checkpoints),
    )


def validate_game_navigation_metadata(collection: bpy.types.Collection) -> GameNavigationValidationResult:
    warnings: list[str] = []
    nav_objects = 0
    blockers = 0
    floors = 0

    for obj in _iter_collection_objects_recursive(collection):
        part = str(obj.get("building_part", "")).lower()
        nav_kind = str(obj.get("nav_kind", ""))
        generated = obj.get("generated_by") == ADDON_ID
        if generated and part and not bool(obj.get("game_nav", False)):
            warnings.append(f"{obj.name}: generated {part} missing game_nav metadata")
            continue
        if not bool(obj.get("game_nav", False)):
            continue

        nav_objects += 1
        game_nav_kind = str(obj.get("game_nav_kind", ""))
        footprint = str(obj.get("game_nav_footprint", ""))
        blocks_movement = bool(obj.get("game_nav_blocks_movement", False))
        blocks_vision = bool(obj.get("game_nav_blocks_vision", False))

        if game_nav_kind == "floor":
            floors += 1
            if "game_nav_story_index" not in obj:
                warnings.append(f"{obj.name}: floor nav metadata missing game_nav_story_index")
            if footprint == "none":
                warnings.append(f"{obj.name}: floor nav metadata must use a non-none footprint")
            if blocks_movement:
                warnings.append(f"{obj.name}: floor must not block movement")
        if blocks_movement:
            blockers += 1
            if "game_nav_story_index" not in obj:
                warnings.append(f"{obj.name}: movement blocker missing game_nav_story_index")
        if nav_kind in {"stair_connector", "stair_checkpoint"} and blocks_movement:
            warnings.append(f"{obj.name}: {nav_kind} must not block movement")
        if part == "decal" and blocks_movement:
            warnings.append(f"{obj.name}: decal must not block movement")
        if part == "floor" and blocks_movement:
            warnings.append(f"{obj.name}: floor must not block movement")
        if part in {"outer_wall", "inner_wall"}:
            if game_nav_kind != "wall":
                warnings.append(f"{obj.name}: {part} must export game_nav_kind=wall")
            if not blocks_movement or not blocks_vision:
                warnings.append(f"{obj.name}: {part} must block movement and vision")
        if part == "stair":
            if game_nav_kind != "stairs":
                warnings.append(f"{obj.name}: stair mesh must export game_nav_kind=stairs")
            if blocks_movement or blocks_vision:
                warnings.append(f"{obj.name}: stair mesh must not block movement or vision")
            if footprint != "none":
                warnings.append(f"{obj.name}: stair mesh must use game_nav_footprint=none")

    ok = not warnings
    return GameNavigationValidationResult(
        ok=ok,
        warnings=tuple(warnings),
        object_count=nav_objects,
        blocker_count=blockers,
        floor_count=floors,
    )


def _create_stair_navigation_objects(
    nav_collection: bpy.types.Collection,
    building_root: bpy.types.Object,
    *,
    stair_id: str,
    from_story: int,
    to_story: int,
    stair_kind: str,
    cost: int,
    path: list[StairNavPoint],
    outside: bool,
) -> list[bpy.types.Object]:
    connector_name = f"Nav_Stair_{stair_id}"
    connector = bpy.data.objects.new(connector_name, None)
    connector.empty_display_type = "PLAIN_AXES"
    connector.empty_display_size = 0.4
    connector.parent = building_root
    connector["nav_kind"] = "stair_connector"
    connector["stair_id"] = stair_id
    connector["from_story"] = int(from_story)
    connector["to_story"] = int(to_story)
    connector["stair_kind"] = stair_kind
    connector["cost"] = int(cost)
    connector["bidirectional"] = True
    connector["generated_by"] = ADDON_ID
    connector["game_hidden_at_runtime"] = True
    connector["hide_in_game"] = True
    connector["nav_switchback"] = len(path) >= 5
    _apply_stair_nav_object_metadata(connector, from_story)
    _write_connector_path_metadata(connector, path)
    if outside:
        connector["outside"] = True
    link_object(nav_collection, connector)

    material = _ensure_checkpoint_material()
    objects = [connector]
    objects.extend(_create_checkpoint_objects_for_connector(connector, path, material, outside=outside))
    objects.append(_create_path_preview(connector, path))
    for obj in objects[1:]:
        link_object(nav_collection, obj)
    return objects


def _create_checkpoint_objects_for_connector(
    connector: bpy.types.Object,
    path: list[StairNavPoint],
    material: bpy.types.Material,
    *,
    outside: bool | None = None,
) -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []
    stair_id = str(connector.get("stair_id", ""))
    from_story = int(connector.get("from_story", 0))
    to_story = int(connector.get("to_story", 0))
    stair_kind = str(connector.get("stair_kind", "internal"))
    is_outside = bool(connector.get("outside", False) if outside is None else outside)
    for index, point in enumerate(path):
        checkpoint = _create_checkpoint_mesh(f"{connector.name}_CP_{index:02d}_{point.role}", point.location, _material_for_role(point.role), _radius_for_role(point.role))
        checkpoint.parent = connector
        checkpoint["nav_kind"] = "stair_checkpoint"
        checkpoint["stair_id"] = stair_id
        checkpoint["checkpoint_index"] = int(index)
        checkpoint["from_story"] = from_story
        checkpoint["to_story"] = to_story
        checkpoint["story_index"] = int(point.story_index)
        checkpoint["stair_kind"] = stair_kind
        checkpoint["checkpoint_role"] = point.role
        checkpoint["nav_role"] = point.role
        checkpoint["vertical_phase"] = point.vertical_phase
        checkpoint["generated_by"] = ADDON_ID
        checkpoint["game_hidden_at_runtime"] = True
        checkpoint["hide_in_game"] = True
        _apply_stair_nav_object_metadata(checkpoint, point.story_index)
        checkpoint["nav_centerline_x"] = float(point.location[0])
        checkpoint["nav_centerline_y"] = float(point.location[1])
        checkpoint["nav_centerline_z"] = float(point.location[2])
        checkpoint["nav_centerline_tolerance"] = CENTERLINE_TOLERANCE_M
        if is_outside:
            checkpoint["outside"] = True
        objects.append(checkpoint)
    return objects


def _apply_stair_nav_object_metadata(obj: bpy.types.Object, story_index: int) -> None:
    obj["game_nav"] = True
    obj["game_nav_kind"] = "stairs"
    obj["game_nav_story_index"] = int(story_index)
    obj["game_nav_footprint"] = "none"
    obj["game_nav_blocks_movement"] = False
    obj["game_nav_blocks_vision"] = False
    obj["game_nav_cover"] = "none"
    obj["game_nav_movement_cost"] = 1.0
    obj["game_nav_source_part"] = str(obj.get("nav_kind", "stair"))


def _rebuild_connector_children(connector: bpy.types.Object, path: list[StairNavPoint], *, outside: bool) -> list[bpy.types.Object]:
    for child in list(connector.children):
        if str(child.get("nav_kind", "")).startswith("stair_") or str(child.get("nav_debug_kind", "")):
            bpy.data.objects.remove(child, do_unlink=True)
    connector["nav_switchback"] = len(path) >= 5
    connector["checkpoint_count"] = len(path)
    _apply_stair_nav_object_metadata(connector, int(connector.get("from_story", 0)))
    _write_connector_path_metadata(connector, path)
    material = _ensure_checkpoint_material()
    objects = _create_checkpoint_objects_for_connector(connector, path, material, outside=outside)
    objects.append(_create_path_preview(connector, path))
    for obj in objects:
        _link_object_like(connector, obj)
    return objects


def _link_object_like(reference: bpy.types.Object, obj: bpy.types.Object) -> None:
    if reference.users_collection:
        link_object(reference.users_collection[0], obj)


def _create_checkpoint_mesh(name: str, location: tuple[float, float, float], material: bpy.types.Material, radius: float) -> bpy.types.Object:
    half_height = CHECKPOINT_THICKNESS_M * 0.5
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    segments = 24
    verts.append((0.0, 0.0, half_height))
    for z in (-half_height, half_height):
        for index in range(segments):
            angle = (math.tau * index) / segments
            verts.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
    faces.append(tuple(range(segments, 0, -1)))
    faces.append(tuple(range(segments + 1, (segments * 2) + 1)))
    for index in range(segments):
        next_index = (index + 1) % segments
        faces.append((index + 1, next_index + 1, next_index + segments + 1, index + segments + 1))
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.data.materials.append(material)
    obj.show_in_front = True
    return obj


def _ensure_checkpoint_material() -> bpy.types.Material:
    material = bpy.data.materials.get(CHECKPOINT_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(CHECKPOINT_MATERIAL_NAME)
    material.diffuse_color = (0.0, 1.0, 0.1, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (0.0, 1.0, 0.1, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (0.0, 1.0, 0.1, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 2.5
    return material


def _material_for_role(role: str) -> bpy.types.Material:
    if role == "floor_entry":
        return _ensure_role_material("NAV_Role_FloorEntry_Green", (0.0, 1.0, 0.1, 1.0), 2.8)
    if role == "floor_exit":
        return _ensure_role_material("NAV_Role_FloorExit_Blue", (0.0, 0.35, 1.0, 1.0), 2.8)
    if role == "landing_center":
        return _ensure_role_material("NAV_Role_Landing_Yellow", (1.0, 0.9, 0.0, 1.0), 2.5)
    if role == "run_start":
        return _ensure_role_material("NAV_Role_RunStart_White", (1.0, 1.0, 1.0, 1.0), 1.8)
    if role == "run_mid":
        return _ensure_role_material("NAV_Role_RunMid_Grey", (0.72, 0.78, 0.78, 1.0), 1.6)
    if role == "run_end":
        return _ensure_role_material("NAV_Role_RunEnd_Orange", (1.0, 0.45, 0.0, 1.0), 2.2)
    return _ensure_checkpoint_material()


def _ensure_role_material(name: str, color: tuple[float, float, float, float], emission_strength: float) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return material


def _radius_for_role(role: str) -> float:
    if role in {"floor_entry", "floor_exit"}:
        return 0.22
    if role in {"run_start", "run_end", "landing_center"}:
        return 0.18
    return CHECKPOINT_RADIUS_M


def _ensure_path_preview_material() -> bpy.types.Material:
    material = bpy.data.materials.get(PATH_PREVIEW_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(PATH_PREVIEW_MATERIAL_NAME)
    material.diffuse_color = (0.0, 1.0, 0.9, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (0.0, 1.0, 0.9, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (0.0, 1.0, 0.9, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 2.0
    return material


def _create_path_preview(connector: bpy.types.Object, path: list[StairNavPoint]) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{connector.name}_PathPreviewCurve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.025
    curve.bevel_resolution = 3
    polyline = curve.splines.new("POLY")
    polyline.points.add(max(0, len(path) - 1))
    for point, nav_point in zip(polyline.points, path):
        x, y, z = nav_point.location
        point.co = (x, y, z + 0.025, 1.0)
    obj = bpy.data.objects.new(f"{connector.name}_PathPreview", curve)
    obj.parent = connector
    obj.show_in_front = True
    obj["nav_debug_kind"] = "stair_path_preview"
    obj["nav_kind"] = "stair_path_preview"
    obj["stair_id"] = str(connector.get("stair_id", ""))
    obj["generated_by"] = ADDON_ID
    obj["hide_in_game"] = True
    obj["game_hidden_at_runtime"] = True
    obj.data.materials.append(_ensure_path_preview_material())
    return obj


def _write_connector_path_metadata(connector: bpy.types.Object, path: list[StairNavPoint]) -> None:
    serialized_path = [[round(x, 4), round(y, 4), round(z, 4)] for x, y, z in (point.location for point in path)]
    roles = [point.role for point in path]
    detailed = [
        {
            "index": index,
            "role": point.role,
            "storyIndex": int(point.story_index),
            "verticalPhase": point.vertical_phase,
            "position": [round(x, 4), round(y, 4), round(z, 4)],
        }
        for index, point in enumerate(path)
        for x, y, z in (point.location,)
    ]
    connector["traversal_path_local_json"] = json.dumps(serialized_path)
    connector["traversal_path_local_detailed_json"] = json.dumps(detailed)
    connector["traversal_path_points_local_json"] = json.dumps(detailed)
    connector["nav_expected_path_local_json"] = json.dumps(serialized_path)
    connector["nav_roles_json"] = json.dumps(roles)
    connector["nav_story_indices_json"] = json.dumps([int(point.story_index) for point in path])
    connector["nav_vertical_phases_json"] = json.dumps([point.vertical_phase for point in path])
    connector["checkpoint_count"] = len(path)


def _path_from_connector(connector: bpy.types.Object) -> list[StairNavPoint]:
    path_json = str(connector.get("nav_expected_path_local_json", "") or connector.get("traversal_path_local_json", ""))
    if not path_json:
        return []
    try:
        raw_points = json.loads(path_json)
    except Exception:
        return []
    roles_json = str(connector.get("nav_roles_json", ""))
    try:
        roles = json.loads(roles_json) if roles_json else []
    except Exception:
        roles = []
    story_indices_json = str(connector.get("nav_story_indices_json", ""))
    vertical_phases_json = str(connector.get("nav_vertical_phases_json", ""))
    try:
        story_indices = json.loads(story_indices_json) if story_indices_json else []
    except Exception:
        story_indices = []
    try:
        vertical_phases = json.loads(vertical_phases_json) if vertical_phases_json else []
    except Exception:
        vertical_phases = []
    from_story = int(connector.get("from_story", 0))
    path: list[StairNavPoint] = []
    for index, raw_point in enumerate(raw_points):
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 3:
            continue
        role = _canonical_role(str(roles[index]) if index < len(roles) else "run_mid")
        story_index = int(story_indices[index]) if index < len(story_indices) else from_story
        vertical_phase = str(vertical_phases[index]) if index < len(vertical_phases) else _vertical_phase_for_role(role)
        path.append(StairNavPoint((float(raw_point[0]), float(raw_point[1]), float(raw_point[2])), role, story_index, vertical_phase))
    return path


def _validate_centerline_distance(checkpoint: bpy.types.Object, warnings: list[str]) -> None:
    expected_x = checkpoint.get("nav_centerline_x")
    expected_y = checkpoint.get("nav_centerline_y")
    if expected_x is None or expected_y is None:
        warnings.append(f"{checkpoint.name}: missing stored centerline reference")
        return
    dx = float(checkpoint.location.x) - float(expected_x)
    dy = float(checkpoint.location.y) - float(expected_y)
    tolerance = float(checkpoint.get("nav_centerline_tolerance", CENTERLINE_TOLERANCE_M))
    if math.sqrt((dx * dx) + (dy * dy)) > tolerance:
        warnings.append(f"{checkpoint.name}: moved {math.sqrt((dx * dx) + (dy * dy)):.2f}m from generated stair centerline")


def _validate_external_stair_visibility_metadata(collection: bpy.types.Collection, warnings: list[str]) -> None:
    for obj in _iter_collection_objects_recursive(collection):
        if obj.type != "MESH":
            continue
        if str(obj.get("building_part", "")) != "stair":
            continue
        if str(obj.get("stair_kind", "")) != "external":
            continue
        if str(obj.get("game_visibility_role", "")) == "hide_above_player":
            warnings.append(f"{obj.name}: external stair mesh has hide_above_player role")
        if str(obj.get("game_visibility_behavior", "")) != "external_stair_connector":
            warnings.append(f"{obj.name}: external stair mesh missing external_stair_connector visibility behavior")
        if bool(obj.get("game_hide_when_above_player", False)):
            warnings.append(f"{obj.name}: external stair mesh must not hide_when_above_player")
        if "from_story" not in obj:
            warnings.append(f"{obj.name}: external stair mesh missing from_story")
        if "to_story" not in obj:
            warnings.append(f"{obj.name}: external stair mesh missing to_story")


def _migrate_checkpoint_role(checkpoint: bpy.types.Object) -> None:
    role = _canonical_role(str(checkpoint.get("checkpoint_role", "") or checkpoint.get("nav_role", "")))
    if not role:
        index = int(checkpoint.get("checkpoint_index", -1))
        role = "floor_entry" if index == 0 else "floor_exit" if index > 0 and index == int(checkpoint.parent.get("checkpoint_count", -1)) - 1 else "run_mid"
    checkpoint["checkpoint_role"] = role
    checkpoint["nav_role"] = role
    if "vertical_phase" not in checkpoint:
        checkpoint["vertical_phase"] = _vertical_phase_for_role(role)


def _validate_required_roles(connector: bpy.types.Object, checkpoints: list[bpy.types.Object], warnings: list[str]) -> None:
    stair_id = str(connector.get("stair_id", connector.name))
    ordered = sorted(checkpoints, key=lambda obj: int(obj.get("checkpoint_index", -1)))
    roles = [_canonical_role(str(cp.get("checkpoint_role", cp.get("nav_role", "")))) for cp in ordered]
    for role in ("floor_entry", "run_start", "run_end", "floor_exit"):
        if role not in roles:
            warnings.append(f"Stair {stair_id}: missing {role}")
    if bool(connector.get("nav_switchback", False)) and "landing_center" not in roles:
        warnings.append(f"Stair {stair_id}: missing landing_center for switchback stair")
    if roles and roles[0] != "floor_entry":
        warnings.append(f"Stair {stair_id}: first checkpoint is {roles[0]}, but floor_entry is required")
    if roles and roles[-1] != "floor_exit":
        warnings.append(f"Stair {stair_id}: last checkpoint is {roles[-1]}, but floor_exit is required")


def _validate_segment_lengths(connector: bpy.types.Object, checkpoints: list[bpy.types.Object], warnings: list[str]) -> None:
    stair_id = str(connector.get("stair_id", connector.name))
    ordered = sorted(checkpoints, key=lambda obj: int(obj.get("checkpoint_index", -1)))
    max_length = 4.5 if str(connector.get("stair_kind", "")) == "external" else 5.5
    for left, right in zip(ordered, ordered[1:]):
        dx = float(right.location.x - left.location.x)
        dy = float(right.location.y - left.location.y)
        dz = float(right.location.z - left.location.z)
        distance = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
        if distance > max_length:
            warnings.append(
                f"Stair {stair_id}: checkpoint CP_{int(left.get('checkpoint_index', -1)):02d} connects too far "
                f"to CP_{int(right.get('checkpoint_index', -1)):02d} ({distance:.2f}m)"
            )


def _vertical_phase_for_role(role: str) -> str:
    role = _canonical_role(role)
    if role in {"floor_entry", "floor_exit"}:
        return "floor"
    if role == "landing_center":
        return "landing_between_floors"
    return "stair"


def _canonical_role(role: str) -> str:
    normalized = str(role or "").strip()
    return ROLE_ALIASES.get(normalized, normalized if normalized in VALID_CHECKPOINT_ROLES else "run_mid")


def _bounds_center(bounds: tuple[float, float, float, float], z: float) -> tuple[float, float, float]:
    x0, y0, x1, y1 = bounds
    return ((float(x0) + float(x1)) * 0.5, (float(y0) + float(y1)) * 0.5, z)


def _selected_stair_id(selected_objects: Iterable[bpy.types.Object]) -> str | None:
    for obj in selected_objects:
        stair_id = str(obj.get("stair_id", ""))
        if stair_id:
            return stair_id
        parent = obj.parent
        while parent is not None:
            stair_id = str(parent.get("stair_id", ""))
            if stair_id:
                return stair_id
            parent = parent.parent
    return None


def _internal_checkpoint_path(context, placement: StairPlacement) -> list[StairNavPoint]:
    base_z = float(getattr(context.story_plan, "z_offset", 0.0))
    top_elevation = float(placement.top_elevation if placement.top_elevation is not None else context.settings.walls.wall_height)
    x0 = float(placement.x)
    y0 = float(placement.y)
    x1 = x0 + float(placement.length)
    y1 = y0 + float(placement.width)
    lower_total_rise = placement.lower_riser_count * float(placement.riser_height)
    lower_z = base_z + SURFACE_OFFSET_M
    landing_z = base_z + lower_total_rise + SURFACE_OFFSET_M
    upper_z = base_z + top_elevation + SURFACE_OFFSET_M
    margin = max(0.18, min(float(placement.stair_width) * 0.35, 0.45))
    from_story = int(placement.from_story)
    to_story = int(placement.to_story)
    if placement.orientation == "x":
        lane = min(float(placement.stair_width), max(0.6, (y1 - y0) * 0.45))
        bottom_y = y0 + (lane * 0.5)
        top_y = y1 - (lane * 0.5)
        mid_x = x1 - float(placement.mid_landing_size)
        upper_run_end = x0 + float(placement.landing_size)
        floor_entry_x = max(x0 - margin, x0 + (margin * 0.25))
        floor_exit_x = max(x0 + (float(placement.landing_size) * 0.5), upper_run_end - (margin * 0.25))
        return [
            StairNavPoint((floor_entry_x, bottom_y, lower_z), "floor_entry", from_story, "floor"),
            StairNavPoint((x0 + margin, bottom_y, lower_z), "run_start", from_story, "stair"),
            StairNavPoint(((x0 + mid_x) * 0.5, bottom_y, base_z + (lower_total_rise * 0.5) + SURFACE_OFFSET_M), "run_mid", from_story, "stair"),
            StairNavPoint((mid_x - margin, bottom_y, landing_z), "run_end", from_story, "stair"),
            StairNavPoint(((mid_x + x1) * 0.5, (y0 + y1) * 0.5, landing_z), "landing_center", from_story, "landing_between_floors"),
            StairNavPoint((mid_x - margin, top_y, landing_z), "run_start", from_story, "stair"),
            StairNavPoint(((mid_x + upper_run_end) * 0.5, top_y, landing_z + ((upper_z - landing_z) * 0.5)), "run_mid", from_story, "stair"),
            StairNavPoint((upper_run_end + margin, top_y, upper_z), "run_end", to_story, "stair"),
            StairNavPoint((floor_exit_x, top_y, upper_z), "floor_exit", to_story, "floor"),
        ]
    lane = min(float(placement.stair_width), max(0.6, (x1 - x0) * 0.45))
    left_x = x0 + (lane * 0.5)
    right_x = x1 - (lane * 0.5)
    mid_y = y1 - float(placement.mid_landing_size)
    upper_run_end = y0 + float(placement.landing_size)
    floor_entry_y = max(y0 - margin, y0 + (margin * 0.25))
    floor_exit_y = max(y0 + (float(placement.landing_size) * 0.5), upper_run_end - (margin * 0.25))
    return [
        StairNavPoint((left_x, floor_entry_y, lower_z), "floor_entry", from_story, "floor"),
        StairNavPoint((left_x, y0 + margin, lower_z), "run_start", from_story, "stair"),
        StairNavPoint((left_x, (y0 + mid_y) * 0.5, base_z + (lower_total_rise * 0.5) + SURFACE_OFFSET_M), "run_mid", from_story, "stair"),
        StairNavPoint((left_x, mid_y - margin, landing_z), "run_end", from_story, "stair"),
        StairNavPoint(((x0 + x1) * 0.5, (mid_y + y1) * 0.5, landing_z), "landing_center", from_story, "landing_between_floors"),
        StairNavPoint((right_x, mid_y - margin, landing_z), "run_start", from_story, "stair"),
        StairNavPoint((right_x, (mid_y + upper_run_end) * 0.5, landing_z + ((upper_z - landing_z) * 0.5)), "run_mid", from_story, "stair"),
        StairNavPoint((right_x, upper_run_end + margin, upper_z), "run_end", to_story, "stair"),
        StairNavPoint((right_x, floor_exit_y, upper_z), "floor_exit", to_story, "floor"),
    ]


def _external_checkpoint_path(context, placement: ExternalStairPlacement) -> list[StairNavPoint]:
    switchback = placement.switchback_placement
    if switchback is None:
        return []
    base_z = float(getattr(context.story_plan, "z_offset", 0.0))
    top_elevation = float(switchback.top_elevation or context.settings.walls.wall_height)
    lower_total_rise = switchback.lower_riser_count * float(switchback.riser_height)
    x0 = float(switchback.x)
    y0 = float(switchback.y)
    lower_z = base_z + SURFACE_OFFSET_M
    landing_z = base_z + lower_total_rise + SURFACE_OFFSET_M
    upper_z = base_z + top_elevation + SURFACE_OFFSET_M
    margin = max(0.18, min(float(switchback.stair_width) * 0.35, 0.45))
    from_story = int(switchback.from_story)
    to_story = int(switchback.to_story)
    door_center = _bounds_center(placement.door_access_bounds, upper_z)
    if switchback.orientation == "x":
        x1 = x0 + float(switchback.length)
        y1 = y0 + float(switchback.width)
        lane = min(float(switchback.stair_width), max(0.6, (y1 - y0) * 0.45))
        bottom_y = y0 + (lane * 0.5)
        top_y = y1 - (lane * 0.5)
        mid_x = x0 + float(switchback.mid_landing_size)
        lower_mid_z = base_z + (lower_total_rise * 0.5) + SURFACE_OFFSET_M
        upper_mid_z = landing_z + ((upper_z - landing_z) * 0.5)
        return [
            StairNavPoint((x1 - (margin * 0.25), bottom_y, lower_z), "floor_entry", from_story, "floor"),
            StairNavPoint((x1 - margin, bottom_y, lower_z), "run_start", from_story, "stair"),
            StairNavPoint(((x1 + mid_x) * 0.5, bottom_y, lower_mid_z), "run_mid", from_story, "stair"),
            StairNavPoint((mid_x + margin, bottom_y, landing_z), "run_end", from_story, "stair"),
            StairNavPoint(((x0 + mid_x) * 0.5, (y0 + y1) * 0.5, landing_z), "landing_center", from_story, "landing_between_floors"),
            StairNavPoint((mid_x + margin, top_y, landing_z), "run_start", from_story, "stair"),
            StairNavPoint(((x1 + mid_x) * 0.5, top_y, upper_mid_z), "run_mid", from_story, "stair"),
            StairNavPoint((x1 - margin, top_y, upper_z), "run_end", to_story, "stair"),
            StairNavPoint(door_center, "floor_exit", to_story, "floor"),
        ]
    x1 = x0 + float(switchback.width)
    y1 = y0 + float(switchback.length)
    lane = min(float(switchback.stair_width), max(0.6, (x1 - x0) * 0.45))
    left_x = x0 + (lane * 0.5)
    right_x = x1 - (lane * 0.5)
    mid_y = y0 + float(switchback.mid_landing_size)
    lower_mid_z = base_z + (lower_total_rise * 0.5) + SURFACE_OFFSET_M
    upper_mid_z = landing_z + ((upper_z - landing_z) * 0.5)
    return [
        StairNavPoint((left_x, y1 - (margin * 0.25), lower_z), "floor_entry", from_story, "floor"),
        StairNavPoint((left_x, y1 - margin, lower_z), "run_start", from_story, "stair"),
        StairNavPoint((left_x, (y1 + mid_y) * 0.5, lower_mid_z), "run_mid", from_story, "stair"),
        StairNavPoint((left_x, mid_y + margin, landing_z), "run_end", from_story, "stair"),
        StairNavPoint(((x0 + x1) * 0.5, (y0 + mid_y) * 0.5, landing_z), "landing_center", from_story, "landing_between_floors"),
        StairNavPoint((right_x, mid_y + margin, landing_z), "run_start", from_story, "stair"),
        StairNavPoint((right_x, (y1 + mid_y) * 0.5, upper_mid_z), "run_mid", from_story, "stair"),
        StairNavPoint((right_x, y1 - margin, upper_z), "run_end", to_story, "stair"),
        StairNavPoint(door_center, "floor_exit", to_story, "floor"),
    ]


def _building_collection(context) -> bpy.types.Collection:
    name = str(getattr(getattr(context, "settings", None), "collection_name", "") or "")
    collection = bpy.data.collections.get(name)
    if collection is not None:
        return collection
    return context.collection


def _stair_id(from_story: int, to_story: int, stair_index: int) -> str:
    return f"{int(from_story)}_{int(to_story)}_{int(stair_index):03d}"


def _existing_checkpoints(stair_id: str) -> list[bpy.types.Object]:
    return [
        obj
        for obj in bpy.data.objects
        if obj.get("nav_kind") == "stair_checkpoint" and str(obj.get("stair_id", "")) == stair_id
    ]


def _existing_connector(stair_id: str) -> bpy.types.Object | None:
    for obj in bpy.data.objects:
        if obj.get("nav_kind") == "stair_connector" and str(obj.get("stair_id", "")) == stair_id:
            return obj
    return None


def _iter_collection_objects_recursive(collection: bpy.types.Collection):
    yield from collection.objects
    for child in collection.children:
        yield from _iter_collection_objects_recursive(child)


def _validate_story_endpoint(cps: list[bpy.types.Object], from_story: int, to_story: int, warnings: list[str]) -> None:
    ordered = sorted(cps, key=lambda obj: int(obj.get("checkpoint_index", -1)))
    if not ordered:
        return
    first = ordered[0]
    last = ordered[-1]
    first_z = float(first.matrix_world.translation.z)
    last_z = float(last.matrix_world.translation.z)
    if last_z <= first_z:
        warnings.append(f"{first.name}/{last.name}: last checkpoint must be above first checkpoint")
    if int(first.get("from_story", -1)) != from_story or int(last.get("to_story", -1)) != to_story:
        warnings.append(f"{first.name}/{last.name}: endpoint story metadata does not match connector")
    if int(first.get("story_index", -1)) != from_story:
        warnings.append(f"{first.name}: floor_entry story_index must match from_story={from_story}")
    if int(last.get("story_index", -1)) != to_story:
        warnings.append(f"{last.name}: floor_exit story_index must match to_story={to_story}")

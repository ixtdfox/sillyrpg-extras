from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import bpy
from mathutils import Vector

from ..common.utils import ADDON_ID, link_object
from ..game_grid import GAME_GRID_ORIGIN_X_M, GAME_GRID_ORIGIN_Z_M, WORLD_TILE_SIZE_M
from ..grid import GRID_NAVIGATION_CONTRACT, GameGridCoordinateMapper, RectCell, RectEdge, create_game_rect_layout

DEFAULT_EXTERNAL_STAIR_COMBAT_COST = 2
DEFAULT_INTERNAL_STAIR_COMBAT_COST = 2
MAX_REASONABLE_ONE_STORY_STAIR_COMBAT_COST = 6


@dataclass
class _StoryNavigationData:
    walkable_cells: set[RectCell] = field(default_factory=set)
    blocked_edges: set[RectEdge] = field(default_factory=set)
    door_edges: set[RectEdge] = field(default_factory=set)
    stairs: list["_StairLink"] = field(default_factory=list)
    blocked_cells: set[RectCell] = field(default_factory=set)
    story_y_m: float = 0.0
    floor_object_count: int = 0
    wall_object_count: int = 0
    door_object_count: int = 0
    floor_bounds_min: Vector | None = None
    floor_bounds_max: Vector | None = None
    door_records: list["_DoorRecord"] = field(default_factory=list)


@dataclass(frozen=True)
class _StairPathPoint:
    x: float
    y: float
    z: float
    story_index: int | None = None
    role: str | None = None
    vertical_phase: str | None = None


@dataclass(frozen=True)
class _StairLink:
    stair_id: str
    from_story_index: int
    from_cell: RectCell
    to_story_index: int
    to_cell: RectCell
    kind: str
    cost: int
    bidirectional: bool
    traversal_path: tuple[_StairPathPoint, ...]


@dataclass(frozen=True)
class _DoorRecord:
    name: str
    story_index: int
    edge: RectEdge
    tile_x: int | None
    tile_y: int | None
    edge_side: str
    wall_orientation: str
    is_external: bool


class NavigationMetadataExporter:
    """Writes the rect grid navigation contract v3 as JSON on an exported mesh node."""

    def __init__(self) -> None:
        self._mapper = GameGridCoordinateMapper()
        self._debug_enabled = os.getenv("SILLYRPG_GRID_NAV_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

    def create_rect_contract_object(
        self,
        collection: bpy.types.Collection,
        *,
        building_id: str,
        stories: list[tuple[int, _StoryNavigationData]],
    ) -> bpy.types.Object:
        payload_stories: list[dict[str, object]] = []
        for story_index, story_data in stories:
            blocked_edges = {edge.canonical() for edge in story_data.blocked_edges}
            door_edges = {edge.canonical() for edge in story_data.door_edges}
            blocked_keys = {edge.key() for edge in blocked_edges}
            door_keys = {edge.key() for edge in door_edges}
            overlapping_edges = blocked_keys & door_keys
            if overlapping_edges:
                blocked_edges = {edge for edge in blocked_edges if edge.key() not in overlapping_edges}
                print(
                    f"[GridValidation] story={story_index} door edges override blocked edges: "
                    f"removed={len(overlapping_edges)}"
                )

            mapped_walkable = sorted(self._mapper.cell_to_game(cell) for cell in story_data.walkable_cells)
            mapped_blocked_cells = sorted(self._mapper.cell_to_game(cell) for cell in story_data.blocked_cells)
            mapped_blocked_edges = sorted(self._mapper.edge_to_game(edge) for edge in blocked_edges)
            mapped_door_edges = sorted(self._mapper.edge_to_game(edge) for edge in door_edges)
            mapped_stairs = [self._map_stair_link(stair) for stair in story_data.stairs]
            mapped_doors = [self._map_door_record(door) for door in story_data.door_records]

            self._validate_story(
                story_index,
                story_data,
                mapped_walkable,
                mapped_blocked_cells,
                mapped_blocked_edges,
                mapped_door_edges,
                mapped_stairs,
                mapped_doors,
            )

            payload_stories.append(
                {
                    "story_index": int(story_index),
                    "story_y_m": float(story_data.story_y_m),
                    "walkable_cells": [{"x": cell.x, "z": cell.y} for cell in mapped_walkable],
                    "blocked_cells": [
                        {"x": cell.x, "z": cell.y, "reason": "obstacle"}
                        for cell in mapped_blocked_cells
                    ],
                    "blocked_edges": [
                        {
                            "a": {"x": edge.a.x, "z": edge.a.y},
                            "b": {"x": edge.b.x, "z": edge.b.y},
                            "reason": "wall",
                        }
                        for edge in mapped_blocked_edges
                    ],
                    "door_edges": [
                        {
                            "a": {"x": door.edge.a.x, "z": door.edge.a.y},
                            "b": {"x": door.edge.b.x, "z": door.edge.b.y},
                            "door_id": door.name,
                            "is_external": door.is_external,
                            "is_open": True,
                        }
                        for door in sorted(mapped_doors, key=lambda item: (item.edge.key(), item.name))
                    ],
                    "stairs": mapped_stairs,
                }
            )

            self._log_story_debug(
                story_index,
                story_data,
                mapped_walkable,
                mapped_blocked_cells,
                mapped_blocked_edges,
                mapped_door_edges,
                mapped_stairs,
            )

        payload = {
            "contract": GRID_NAVIGATION_CONTRACT,
            "grid_type": "rect",
            "tile_size_m": float(WORLD_TILE_SIZE_M),
            "origin": {"x": float(GAME_GRID_ORIGIN_X_M), "z": float(GAME_GRID_ORIGIN_Z_M)},
            "coordinate_mapping": "blender_xy_to_game_xz",
            "coordinate_mapping_details": "game_x=tile_x, game_z=-(tile_y+1)",
            "building_id": str(building_id),
            "stories": payload_stories,
        }
        self._validate_payload(payload)
        obj = self._create_metadata_mesh_object()
        obj["generated_by"] = ADDON_ID
        obj["building_part"] = "metadata"
        obj["grid_contract"] = GRID_NAVIGATION_CONTRACT
        obj["grid_type"] = "rect"
        obj["tile_size_m"] = float(WORLD_TILE_SIZE_M)
        obj["game_hidden_at_runtime"] = True
        obj["hide_in_game"] = True
        obj["game_nav"] = False
        obj["game_visibility"] = False
        obj["game_navigation_json"] = json.dumps(payload, separators=(",", ":"))
        link_object(collection, obj)
        return obj

    def create_rect_contract_from_collection(self, collection: bpy.types.Collection, *, building_id: str) -> bpy.types.Object:
        stories: dict[int, _StoryNavigationData] = {}
        stair_connectors: dict[str, bpy.types.Object] = {}
        stair_checkpoints: dict[str, list[bpy.types.Object]] = {}

        for obj in self._iter_objects(collection):
            if obj.name.startswith("BuildingGridNavigationMetadata") or str(obj.get("building_part", "")).lower() == "metadata":
                bpy.data.objects.remove(obj, do_unlink=True)
                continue
            story_index = self._resolve_story_index(obj)
            story_data = stories.setdefault(story_index, _StoryNavigationData())
            story_data.story_y_m = self._resolve_story_y(obj, story_data.story_y_m)
            part = str(obj.get("building_part", obj.get("part", ""))).lower()
            nav_kind = str(obj.get("nav_kind", "")).lower()

            if nav_kind == "stair_connector":
                stair_id = str(obj.get("stair_id", "")).strip()
                if stair_id:
                    stair_connectors[stair_id] = obj
                continue

            if nav_kind == "stair_checkpoint":
                stair_id = str(obj.get("stair_id", "")).strip()
                if stair_id:
                    stair_checkpoints.setdefault(stair_id, []).append(obj)
                continue

            if part == "floor":
                story_data.floor_object_count += 1
                story_data.walkable_cells.update(self._read_cells(obj.get("grid_cells")))
                self._include_floor_bounds(story_data, obj)
            if self._is_external_landing_object(obj, part):
                landing_cells = self._object_bounds_to_rect_cells(obj)
                story_data.walkable_cells.update(landing_cells)
                if self._debug_enabled:
                    print(
                        f"[GridNavigationExport][debug] story={story_index} externalLanding={obj.name} "
                        f"cells={sorted(landing_cells)}"
                    )
            if part in {"outer_wall", "inner_wall"}:
                story_data.wall_object_count += 1
                story_data.blocked_edges.update(self._read_edges(obj.get("blocked_edges")))
            if part == "door":
                story_data.door_object_count += 1
                edge = self._read_edge(obj.get("door_edge"))
                if edge is not None:
                    self._validate_door_tile_alignment(obj, edge)
                    story_data.door_edges.add(edge)
                    door_record = self._door_record_from_object(obj, story_index, edge)
                    story_data.door_records.append(door_record)
                    if door_record.is_external:
                        story_data.walkable_cells.add(edge.a)
                        story_data.walkable_cells.add(edge.b)
                else:
                    print(f"[GridValidation] door '{obj.name}' is missing valid door_edge metadata")
            if self._is_blocked_cell_object(obj, part):
                story_data.blocked_cells.update(self._read_cells(obj.get("grid_cells")))

        for stair in self._collect_stair_links(stair_connectors, stair_checkpoints):
            from_story = stories.setdefault(stair.from_story_index, _StoryNavigationData())
            to_story = stories.setdefault(stair.to_story_index, _StoryNavigationData())
            from_story.stairs.append(stair)
            from_story.walkable_cells.add(stair.from_cell)
            to_story.walkable_cells.add(stair.to_cell)

        sorted_stories = sorted(stories.items(), key=lambda item: item[0])
        if not sorted_stories:
            sorted_stories = [(0, _StoryNavigationData())]

        return self.create_rect_contract_object(collection, building_id=building_id, stories=sorted_stories)

    def _create_metadata_mesh_object(self) -> bpy.types.Object:
        mesh = bpy.data.meshes.new("BuildingGridNavigationMetadataMesh")
        mesh.from_pydata(
            [(0.0, 0.0, -1000.0), (0.001, 0.0, -1000.0), (0.0, 0.001, -1000.0)],
            [],
            [(0, 1, 2)],
        )
        mesh.update()
        obj = bpy.data.objects.new("BuildingGridNavigationMetadata", mesh)
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)
        return obj

    def _iter_objects(self, collection: bpy.types.Collection):
        yield from collection.objects
        for child in collection.children:
            yield from self._iter_objects(child)

    def _read_cells(self, raw: object) -> set[RectCell]:
        if not raw:
            return set()
        try:
            values = json.loads(str(raw))
        except Exception:
            return set()
        cells: set[RectCell] = set()
        for value in values if isinstance(values, list) else []:
            if isinstance(value, dict) and "x" in value and "z" in value:
                cells.add(RectCell(int(value["x"]), int(value["z"])))
        return cells

    def _read_edges(self, raw: object) -> set[RectEdge]:
        if not raw:
            return set()
        try:
            values = json.loads(str(raw))
        except Exception:
            return set()
        edges: set[RectEdge] = set()
        for value in values if isinstance(values, list) else []:
            edge = self._edge_from_dict(value)
            if edge is not None:
                edges.add(edge)
        return edges

    def _read_edge(self, raw: object) -> RectEdge | None:
        if not raw:
            return None
        try:
            value = json.loads(str(raw))
        except Exception:
            return None
        return self._edge_from_dict(value)

    def _edge_from_dict(self, value: object) -> RectEdge | None:
        if not isinstance(value, dict):
            return None
        a = value.get("a")
        b = value.get("b")
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        try:
            return RectEdge(RectCell(int(a["x"]), int(a["z"])), RectCell(int(b["x"]), int(b["z"]))).canonical()
        except Exception as exc:
            print(f"[GridValidation] invalid edge metadata: {value}: {exc}")
            return None

    def _resolve_story_index(self, obj: bpy.types.Object) -> int:
        for key in ("story_index", "game_story_index", "game_nav_story_index"):
            value = obj.get(key)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    continue
        return 0

    def _resolve_story_y(self, obj: bpy.types.Object, fallback: float) -> float:
        for key in ("story_z_offset", "game_story_z_offset"):
            value = obj.get(key)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    continue
        return fallback

    def _include_floor_bounds(self, story_data: _StoryNavigationData, obj: bpy.types.Object) -> None:
        if not getattr(obj, "bound_box", None):
            return
        matrix = obj.matrix_world
        corners = [matrix @ Vector(corner) for corner in obj.bound_box]
        if not corners:
            return
        min_corner = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        max_corner = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        if story_data.floor_bounds_min is None:
            story_data.floor_bounds_min = min_corner
            story_data.floor_bounds_max = max_corner
            return
        story_data.floor_bounds_min = Vector(
            (
                min(story_data.floor_bounds_min.x, min_corner.x),
                min(story_data.floor_bounds_min.y, min_corner.y),
                min(story_data.floor_bounds_min.z, min_corner.z),
            )
        )
        story_data.floor_bounds_max = Vector(
            (
                max(story_data.floor_bounds_max.x, max_corner.x),
                max(story_data.floor_bounds_max.y, max_corner.y),
                max(story_data.floor_bounds_max.z, max_corner.z),
            )
        )

    def _log_story_debug(
        self,
        story_index: int,
        story_data: _StoryNavigationData,
        mapped_walkable: list[RectCell],
        mapped_blocked_cells: list[RectCell],
        mapped_blocked_edges: list[RectEdge],
        mapped_door_edges: list[RectEdge],
        mapped_stairs: list[dict[str, object]],
    ) -> None:
        floor_bounds = "n/a"
        if story_data.floor_bounds_min is not None and story_data.floor_bounds_max is not None:
            floor_bounds = (
                f"x=[{story_data.floor_bounds_min.x:.2f},{story_data.floor_bounds_max.x:.2f}] "
                f"z=[{story_data.floor_bounds_min.y:.2f},{story_data.floor_bounds_max.y:.2f}]"
            )
        cell_bounds = self._format_cell_bounds(mapped_walkable)
        print(
            "[GridNavigationExport]",
            f"story={story_index}",
            f"story_y_m={story_data.story_y_m:.2f}",
            f"walkable={len(mapped_walkable)}",
            f"blocked_cells={len(mapped_blocked_cells)}",
            f"blocked_edges={len(mapped_blocked_edges)}",
            f"door_edges={len(mapped_door_edges)}",
            f"stairs={len(mapped_stairs)}",
            f"floor_bounds={floor_bounds}",
            f"cell_bounds={cell_bounds}",
        )
        if not self._debug_enabled:
            return
        sample_count = min(5, len(story_data.walkable_cells))
        if sample_count == 0:
            return
        samples = sorted(story_data.walkable_cells)[:sample_count]
        mapping_preview = ", ".join(
            f"({cell.x},{cell.y})->({self._mapper.cell_to_game(cell).x},{self._mapper.cell_to_game(cell).y})"
            for cell in samples
        )
        print(f"[GridNavigationExport][debug] story={story_index} sample_cell_mapping={mapping_preview}")

    def _is_blocked_cell_object(self, obj: bpy.types.Object, part: str) -> bool:
        if part in {"outer_wall", "inner_wall", "floor", "door", "stair", "border", "roof_railing", "terrace_railing"}:
            return False
        if not bool(obj.get("game_nav", False)):
            return False
        if not bool(obj.get("game_nav_blocks_movement", False)):
            return False
        nav_kind = str(obj.get("game_nav_kind", "")).lower()
        return nav_kind in {"obstacle", "blocking", "cover"}

    def _is_external_landing_object(self, obj: bpy.types.Object, part: str) -> bool:
        if part != "stair":
            return False
        if str(obj.get("stair_kind", "")).lower() != "external":
            return False
        return str(obj.get("stair_part", "")).lower() == "landing"

    def _object_bounds_to_rect_cells(self, obj: bpy.types.Object) -> set[RectCell]:
        if not getattr(obj, "bound_box", None):
            return set()
        matrix = obj.matrix_world
        corners = [matrix @ Vector(corner) for corner in obj.bound_box]
        if not corners:
            return set()
        min_x = min(corner.x for corner in corners)
        max_x = max(corner.x for corner in corners)
        min_y = min(corner.y for corner in corners)
        max_y = max(corner.y for corner in corners)
        return {
            RectCell(tile_x, tile_y)
            for tile_x in range(math.floor(min_x), math.ceil(max_x))
            for tile_y in range(math.floor(min_y), math.ceil(max_y))
        }

    def _validate_story(
        self,
        story_index: int,
        story_data: _StoryNavigationData,
        mapped_walkable: list[RectCell],
        mapped_blocked_cells: list[RectCell],
        mapped_blocked_edges: list[RectEdge],
        mapped_door_edges: list[RectEdge],
        mapped_stairs: list[dict[str, object]],
        mapped_doors: list[_DoorRecord],
    ) -> None:
        if story_data.floor_object_count > 0 and len(mapped_walkable) == 0:
            print(f"[GridValidation] story={story_index} has floor meshes but walkable_cells is empty")
        if story_data.wall_object_count > 0 and len(mapped_blocked_edges) == 0:
            print(f"[GridValidation] story={story_index} has wall meshes but blocked_edges is empty")
        if story_data.door_object_count > 0 and len(mapped_door_edges) != story_data.door_object_count:
            print(
                f"[GridValidation] story={story_index} expected door_edges={story_data.door_object_count} "
                f"but exported {len(mapped_door_edges)} (missing or duplicate door_edge metadata)"
            )

        blocked_keys = {edge.key() for edge in mapped_blocked_edges}
        walkable_keys = {f"{cell.x}:{cell.y}" for cell in mapped_walkable}
        blocked_cell_by_key = {f"{cell.x}:{cell.y}": cell for cell in mapped_blocked_cells}
        for edge in mapped_door_edges:
            if not self._is_neighbor_edge(edge):
                print(f"[GridValidation] story={story_index} non-neighbor door edge: {edge.key()}")
            if edge.key() in blocked_keys:
                continue
            a_key = f"{edge.a.x}:{edge.a.y}"
            b_key = f"{edge.b.x}:{edge.b.y}"
            if a_key in walkable_keys and b_key in walkable_keys:
                continue
            print(
                f"[GridValidation] story={story_index} door edge {edge.key()} is not in blocked_edges "
                "and does not connect two walkable cells"
            )

        for edge in mapped_blocked_edges:
            if not self._is_neighbor_edge(edge):
                print(f"[GridValidation] story={story_index} non-neighbor blocked edge: {edge.key()}")

        mapped_open_door_endpoint_keys = {
            f"{endpoint.x}:{endpoint.y}"
            for edge in mapped_door_edges
            for endpoint in (edge.a, edge.b)
        }
        for endpoint_key in sorted(mapped_open_door_endpoint_keys):
            if endpoint_key in blocked_cell_by_key:
                print(
                    f"[GridValidation] story={story_index} open door endpoint is blocked cell: {endpoint_key} "
                    "reason=wall_or_perimeter_generated_obstacle"
                )

        for door in mapped_doors:
            a_key = f"{door.edge.a.x}:{door.edge.a.y}"
            b_key = f"{door.edge.b.x}:{door.edge.b.y}"
            a_inside = a_key in walkable_keys
            b_inside = b_key in walkable_keys
            if door.is_external:
                blocked_endpoint = a_key in blocked_cell_by_key or b_key in blocked_cell_by_key
                print(
                    f"[GridValidation] story={story_index} externalDoor={door.name} edge={door.edge.key()} "
                    f"outsideWalkable={a_inside or b_inside} insideWalkable={a_inside or b_inside} "
                    f"endpointBlocked={blocked_endpoint} ok={a_inside and b_inside and not blocked_endpoint}"
                )
                if a_inside == b_inside:
                    continue
            elif not (a_inside and b_inside):
                print(
                    f"[GridValidation] story={story_index} internal door '{door.name}' must connect two inside walkable cells "
                    f"tile=({door.tile_x},{door.tile_y}) side={door.edge_side} edge={door.edge.key()}"
                )

        self._validate_door_metadata_contract_consistency(story_index, mapped_door_edges, mapped_doors)

        if story_data.blocked_cells:
            blocked_not_walkable = [cell for cell in story_data.blocked_cells if cell not in story_data.walkable_cells]
            if blocked_not_walkable:
                print(
                    f"[GridValidation] story={story_index} blocked_cells_outside_walkable={len(blocked_not_walkable)} "
                    "(likely wall/perimeter export bug)"
                )

        for stair in mapped_stairs:
            from_payload = stair.get("from") if isinstance(stair, dict) else None
            to_payload = stair.get("to") if isinstance(stair, dict) else None
            if not isinstance(from_payload, dict) or not isinstance(to_payload, dict):
                continue
            from_cell = from_payload.get("cell")
            to_cell = to_payload.get("cell")
            if not isinstance(from_cell, dict) or not isinstance(to_cell, dict):
                continue
            from_key = f"{int(from_cell.get('x', 0))}:{int(from_cell.get('z', 0))}"
            to_key = f"{int(to_cell.get('x', 0))}:{int(to_cell.get('z', 0))}"
            if from_key not in walkable_keys:
                print(f"[GridValidation] story={story_index} stair {stair.get('id', 'stair')} from endpoint is not walkable: {from_key}")
            if int(to_payload.get("story_index", story_index)) == story_index and to_key not in walkable_keys:
                print(f"[GridValidation] story={story_index} stair {stair.get('id', 'stair')} to endpoint is not walkable: {to_key}")

    def _validate_payload(self, payload: dict[str, object]) -> None:
        stories_raw = payload.get("stories")
        if not isinstance(stories_raw, list):
            return
        walkable_by_story: dict[int, set[str]] = {}
        blocked_by_story: dict[int, set[str]] = {}
        for story in stories_raw:
            if not isinstance(story, dict):
                continue
            story_index = int(story.get("story_index", 0))
            walkable_by_story[story_index] = {
                f"{int(cell.get('x', 0))}:{int(cell.get('z', 0))}"
                for cell in story.get("walkable_cells", [])
                if isinstance(cell, dict)
            }
            blocked_by_story[story_index] = {
                f"{int(cell.get('x', 0))}:{int(cell.get('z', 0))}"
                for cell in story.get("blocked_cells", [])
                if isinstance(cell, dict)
            }

        for story in stories_raw:
            if not isinstance(story, dict):
                continue
            story_index = int(story.get("story_index", 0))
            walkable = walkable_by_story.get(story_index, set())
            blocked = blocked_by_story.get(story_index, set())
            print(
                f"[GridValidation] story={story_index} walkable={len(walkable)} "
                f"blocked_edges={len(story.get('blocked_edges', [])) if isinstance(story.get('blocked_edges'), list) else 0} "
                f"door_edges={len(story.get('door_edges', [])) if isinstance(story.get('door_edges'), list) else 0} "
                f"stairs={len(story.get('stairs', [])) if isinstance(story.get('stairs'), list) else 0}"
            )
            for stair in story.get("stairs", []) if isinstance(story.get("stairs"), list) else []:
                if not isinstance(stair, dict):
                    continue
                for endpoint_name in ("from", "to"):
                    endpoint = stair.get(endpoint_name)
                    if not isinstance(endpoint, dict):
                        continue
                    endpoint_story = int(endpoint.get("story_index", story_index))
                    endpoint_cell = endpoint.get("cell")
                    if not isinstance(endpoint_cell, dict):
                        continue
                    key = f"{int(endpoint_cell.get('x', 0))}:{int(endpoint_cell.get('z', 0))}"
                    endpoint_walkable = key in walkable_by_story.get(endpoint_story, set())
                    endpoint_blocked = key in blocked_by_story.get(endpoint_story, set())
                    print(
                        f"[GridValidation] stair={stair.get('id', 'stair')} {endpoint_name}="
                        f"{endpoint_story}:{key} walkable={endpoint_walkable} blocked={endpoint_blocked} "
                        f"ok={endpoint_walkable and not endpoint_blocked}"
                    )

    def _is_neighbor_edge(self, edge: RectEdge) -> bool:
        return abs(edge.a.x - edge.b.x) + abs(edge.a.y - edge.b.y) == 1

    def _collect_stair_links(
        self,
        connectors: dict[str, bpy.types.Object],
        checkpoints_by_stair: dict[str, list[bpy.types.Object]],
    ) -> list[_StairLink]:
        stairs: list[_StairLink] = []
        for stair_id, connector in sorted(connectors.items(), key=lambda item: item[0]):
            from_story = int(connector.get("from_story", 0))
            to_story = int(connector.get("to_story", from_story + 1))
            checkpoints = checkpoints_by_stair.get(stair_id, [])
            traversal_path = self._resolve_stair_path(connector, checkpoints, from_story, to_story)
            endpoints = self._resolve_stair_endpoints(connector, checkpoints, from_story, to_story, traversal_path)
            if endpoints is None:
                print(f"[GridValidation] stair '{stair_id}' has no checkpoint/path endpoints for contract export")
                continue
            kind = str(connector.get("stair_kind", "internal") or "internal").lower()
            if kind not in {"internal", "external"}:
                kind = "internal"
            stairs.append(
                _StairLink(
                    stair_id=stair_id,
                    from_story_index=from_story,
                    from_cell=endpoints[0],
                    to_story_index=to_story,
                    to_cell=endpoints[1],
                    kind=kind,
                    cost=self._resolve_stair_tactical_cost(connector, kind, from_story, to_story),
                    bidirectional=_as_bool(connector.get("bidirectional"), default=True),
                    traversal_path=tuple(traversal_path),
                )
            )
        return stairs

    def _resolve_stair_tactical_cost(
        self,
        connector: bpy.types.Object,
        kind: str,
        from_story: int,
        to_story: int,
    ) -> int:
        story_delta = max(1, abs(int(to_story) - int(from_story)))
        adjacent_story_cost = (
            DEFAULT_EXTERNAL_STAIR_COMBAT_COST
            if kind == "external"
            else DEFAULT_INTERNAL_STAIR_COMBAT_COST
        )
        default_cost = adjacent_story_cost * story_delta

        explicit_cost = connector.get("combat_cost", connector.get("movement_cost"))
        if explicit_cost is not None:
            try:
                cost = int(explicit_cost)
            except (TypeError, ValueError):
                cost = 0
            if cost > 0:
                return cost

        legacy_cost = connector.get("cost")
        if legacy_cost is not None:
            try:
                cost = int(legacy_cost)
            except (TypeError, ValueError):
                cost = 0
            max_reasonable_cost = MAX_REASONABLE_ONE_STORY_STAIR_COMBAT_COST * story_delta
            if 0 < cost <= max_reasonable_cost:
                return cost
            if cost > max_reasonable_cost:
                print(
                    f"[GridValidation] stair '{connector.name}' legacy cost={cost} exceeds tactical limit "
                    f"{max_reasonable_cost}; exporting default combat cost {default_cost}"
                )

        return default_cost

    def _resolve_stair_endpoints(
        self,
        connector: bpy.types.Object,
        checkpoints: list[bpy.types.Object],
        from_story: int,
        to_story: int,
        path_points: list[_StairPathPoint] | None = None,
    ) -> tuple[RectCell, RectCell] | None:
        if checkpoints:
            ordered = sorted(checkpoints, key=lambda cp: int(cp.get("checkpoint_index", 0)))
            from_checkpoint = self._pick_story_checkpoint(ordered, from_story, first=True)
            to_checkpoint = self._pick_story_checkpoint(ordered, to_story, first=False)
            if from_checkpoint is not None and to_checkpoint is not None:
                return self._object_to_rect_cell(from_checkpoint), self._object_to_rect_cell(to_checkpoint)

        path_points = path_points if path_points is not None else self._read_path_points(connector, from_story)
        if len(path_points) < 2:
            return None
        return (
            self._world_point_to_rect_cell((path_points[0].x, path_points[0].y, path_points[0].z)),
            self._world_point_to_rect_cell((path_points[-1].x, path_points[-1].y, path_points[-1].z)),
        )

    def _pick_story_checkpoint(self, checkpoints: list[bpy.types.Object], story_index: int, *, first: bool) -> bpy.types.Object | None:
        candidates = [cp for cp in checkpoints if int(cp.get("story_index", -10_000)) == story_index]
        if not candidates:
            return checkpoints[0] if first else checkpoints[-1]
        return candidates[0] if first else candidates[-1]

    def _resolve_stair_path(
        self,
        connector: bpy.types.Object,
        checkpoints: list[bpy.types.Object],
        from_story: int,
        to_story: int,
    ) -> list[_StairPathPoint]:
        path_points = self._read_path_points(connector, from_story)
        if path_points:
            return path_points
        ordered = sorted(checkpoints, key=lambda cp: int(cp.get("checkpoint_index", 0)))
        return [self._checkpoint_to_path_point(checkpoint, from_story, to_story) for checkpoint in ordered]

    def _read_path_points(self, connector: bpy.types.Object, from_story: int) -> list[_StairPathPoint]:
        detailed_json = str(connector.get("traversal_path_local_detailed_json", "") or connector.get("traversal_path_points_local_json", ""))
        if detailed_json:
            detailed_points = self._read_detailed_path_points(detailed_json)
            if detailed_points:
                return detailed_points

        path_json = str(connector.get("traversal_path_local_json", "") or connector.get("nav_expected_path_local_json", ""))
        if not path_json:
            return []
        try:
            values = json.loads(path_json)
        except Exception:
            return []
        roles = self._read_json_list(connector.get("nav_roles_json"))
        story_indices = self._read_json_list(connector.get("nav_story_indices_json"))
        vertical_phases = self._read_json_list(connector.get("nav_vertical_phases_json"))
        points: list[_StairPathPoint] = []
        for value in values if isinstance(values, list) else []:
            index = len(points)
            if isinstance(value, list) and len(value) == 3:
                story_index = int(story_indices[index]) if index < len(story_indices) and isinstance(story_indices[index], int) else from_story
                role = str(roles[index]) if index < len(roles) and roles[index] is not None else None
                vertical_phase = str(vertical_phases[index]) if index < len(vertical_phases) and vertical_phases[index] is not None else None
                points.append(_StairPathPoint(float(value[0]), float(value[1]), float(value[2]), story_index, role, vertical_phase))
        return points

    def _read_detailed_path_points(self, raw_json: str) -> list[_StairPathPoint]:
        try:
            values = json.loads(raw_json)
        except Exception:
            return []
        points: list[_StairPathPoint] = []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            position = value.get("position")
            if not isinstance(position, list) or len(position) != 3:
                continue
            story_index = value.get("storyIndex", value.get("story_index"))
            vertical_phase = value.get("verticalPhase", value.get("vertical_phase"))
            points.append(
                _StairPathPoint(
                    float(position[0]),
                    float(position[1]),
                    float(position[2]),
                    int(story_index) if isinstance(story_index, int) else None,
                    str(value.get("role")) if value.get("role") is not None else None,
                    str(vertical_phase) if vertical_phase is not None else None,
                )
            )
        return points

    def _read_json_list(self, raw: object) -> list[object]:
        if not raw:
            return []
        try:
            value = json.loads(str(raw))
        except Exception:
            return []
        return value if isinstance(value, list) else []

    def _checkpoint_to_path_point(self, checkpoint: bpy.types.Object, from_story: int, to_story: int) -> _StairPathPoint:
        story_index = int(checkpoint.get("story_index", from_story))
        role = str(checkpoint.get("checkpoint_role", checkpoint.get("nav_role", "")) or "")
        vertical_phase = str(checkpoint.get("vertical_phase", "") or "")
        return _StairPathPoint(
            float(checkpoint.location.x),
            float(checkpoint.location.y),
            float(checkpoint.location.z),
            story_index if story_index in {from_story, to_story} else story_index,
            role or None,
            vertical_phase or None,
        )

    def _object_to_rect_cell(self, obj: bpy.types.Object) -> RectCell:
        return self._world_point_to_rect_cell((float(obj.location.x), float(obj.location.y), float(obj.location.z)))

    def _world_point_to_rect_cell(self, point: tuple[float, float, float]) -> RectCell:
        return create_game_rect_layout().snap_point_to_cell(point[0], point[1])

    def _map_stair_link(self, stair: _StairLink) -> dict[str, object]:
        from_cell = self._mapper.cell_to_game(stair.from_cell)
        to_cell = self._mapper.cell_to_game(stair.to_cell)
        traversal_path_world = [self._map_stair_path_point(point) for point in stair.traversal_path]
        self._validate_mapped_stair_link(stair, from_cell, to_cell, traversal_path_world)
        return {
            "id": stair.stair_id,
            "kind": stair.kind,
            "bidirectional": stair.bidirectional,
            "cost": stair.cost,
            "movement_cost": stair.cost,
            "combat_cost": stair.cost,
            "from": {
                "story_index": int(stair.from_story_index),
                "cell": {"x": from_cell.x, "z": from_cell.y},
            },
            "to": {
                "story_index": int(stair.to_story_index),
                "cell": {"x": to_cell.x, "z": to_cell.y},
            },
            "traversal_path_world": traversal_path_world,
        }

    def _map_stair_path_point(self, point: _StairPathPoint) -> dict[str, object]:
        x, y, z = self._mapper.world_point_to_game((point.x, point.y, point.z))
        payload: dict[str, object] = {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}
        if point.story_index is not None:
            payload["story_index"] = int(point.story_index)
        if point.role:
            payload["role"] = point.role
        if point.vertical_phase:
            payload["vertical_phase"] = point.vertical_phase
        return payload

    def _validate_mapped_stair_link(
        self,
        stair: _StairLink,
        from_cell: RectCell,
        to_cell: RectCell,
        path: list[dict[str, object]],
    ) -> None:
        monotonic_story_ok = self._is_monotonic_story_path(path, stair.from_story_index, stair.to_story_index)
        print(
            f"[GridValidation] stair={stair.stair_id} "
            f"from={stair.from_story_index}:{from_cell.x}:{from_cell.y} "
            f"to={stair.to_story_index}:{to_cell.x}:{to_cell.y} "
            f"path_points={len(path)} path_bounds={self._format_point_bounds(path)} "
            f"monotonic_story_ok={str(monotonic_story_ok).lower()}"
        )
        if len(path) < 2:
            print(f"[GridValidation] stair={stair.stair_id} invalid path_points={len(path)} expected>=2")
            return
        first_distance = self._distance_to_cell_center(path[0], from_cell)
        last_distance = self._distance_to_cell_center(path[-1], to_cell)
        if first_distance > 2.0 or last_distance > 2.0:
            print(
                f"[GridValidation] stair={stair.stair_id} endpoint path distance high: "
                f"first_to_from_cell={first_distance:.2f}m last_to_to_cell={last_distance:.2f}m"
            )
        if stair.kind == "external" and len(path) <= 3:
            print(
                f"[GridValidation] stair={stair.stair_id} external stair has only {len(path)} path points; "
                "switchback stairs should export detailed traversal_path_world"
            )

    def _distance_to_cell_center(self, point: dict[str, object], cell: RectCell) -> float:
        point_x = float(point["x"])
        point_z = float(point["z"])
        center_x = float(cell.x) + 0.5
        center_z = float(cell.y) + 0.5
        return math.hypot(point_x - center_x, point_z - center_z)

    def _format_point_bounds(self, path: list[dict[str, object]]) -> str:
        if not path:
            return "n/a"
        xs = [float(point["x"]) for point in path]
        ys = [float(point["y"]) for point in path]
        zs = [float(point["z"]) for point in path]
        return (
            f"x=[{min(xs):.2f},{max(xs):.2f}] "
            f"y=[{min(ys):.2f},{max(ys):.2f}] "
            f"z=[{min(zs):.2f},{max(zs):.2f}]"
        )

    def _is_monotonic_story_path(self, path: list[dict[str, object]], from_story: int, to_story: int) -> bool:
        story_indices = [point.get("story_index") for point in path if isinstance(point.get("story_index"), int)]
        if len(story_indices) < 2:
            return True
        if to_story >= from_story:
            return all(int(story_indices[index]) <= int(story_indices[index + 1]) for index in range(len(story_indices) - 1))
        return all(int(story_indices[index]) >= int(story_indices[index + 1]) for index in range(len(story_indices) - 1))

    def _format_cell_bounds(self, cells: list[RectCell]) -> str:
        if not cells:
            return "n/a"
        min_x = min(cell.x for cell in cells)
        max_x = max(cell.x for cell in cells)
        min_z = min(cell.y for cell in cells)
        max_z = max(cell.y for cell in cells)
        return f"x=[{min_x},{max_x}] z=[{min_z},{max_z}]"

    def _validate_door_tile_alignment(self, door_obj: bpy.types.Object, edge: RectEdge) -> None:
        if "tile_x" not in door_obj or "tile_y" not in door_obj:
            return
        try:
            tile_cell = RectCell(int(door_obj.get("tile_x")), int(door_obj.get("tile_y")))
        except Exception:
            return
        if tile_cell != edge.a and tile_cell != edge.b:
            print(
                f"[GridValidation] door '{door_obj.name}' tile ({tile_cell.x},{tile_cell.y}) does not match door_edge {edge.key()}"
            )

    def _door_record_from_object(self, door_obj: bpy.types.Object, story_index: int, edge: RectEdge) -> _DoorRecord:
        tile_x = _as_optional_int(door_obj.get("tile_x"))
        tile_y = _as_optional_int(door_obj.get("tile_y"))
        edge_side = str(door_obj.get("edge_side", "") or "").lower()
        wall_orientation = str(door_obj.get("wall_orientation", "") or "").lower()
        door_type = str(door_obj.get("door_type", "") or "").lower()
        return _DoorRecord(
            name=door_obj.name,
            story_index=story_index,
            edge=edge.canonical(),
            tile_x=tile_x,
            tile_y=tile_y,
            edge_side=edge_side,
            wall_orientation=wall_orientation,
            is_external=door_type in {"entry", "external_stair"},
        )

    def _map_door_record(self, door: _DoorRecord) -> _DoorRecord:
        mapped_edge = self._mapper.edge_to_game(door.edge)
        return _DoorRecord(
            name=door.name,
            story_index=door.story_index,
            edge=mapped_edge,
            tile_x=door.tile_x,
            tile_y=door.tile_y,
            edge_side=door.edge_side,
            wall_orientation=door.wall_orientation,
            is_external=door.is_external,
        )

    def _validate_door_metadata_contract_consistency(
        self,
        story_index: int,
        mapped_door_edges: list[RectEdge],
        mapped_doors: list[_DoorRecord],
    ) -> None:
        contract_edges = {edge.key(): edge for edge in mapped_door_edges}
        for door in mapped_doors:
            edge_key = door.edge.key()
            if edge_key in contract_edges:
                continue
            contract_preview = ", ".join(sorted(contract_edges.keys())[:8]) if contract_edges else "none"
            print(
                f"[GridValidation] story={story_index} door metadata mismatch name='{door.name}' "
                f"tile=({door.tile_x},{door.tile_y}) side={door.edge_side} wall_orientation={door.wall_orientation} "
                f"metadata_edge={edge_key} contract_edges=[{contract_preview}]"
            )


def _as_optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default

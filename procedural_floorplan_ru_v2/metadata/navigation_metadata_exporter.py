from __future__ import annotations

import json

import bpy

from ..common.utils import ADDON_ID, link_object
from ..game_grid import GAME_GRID_ORIGIN_X_M, GAME_GRID_ORIGIN_Z_M, WORLD_TILE_SIZE_M
from ..grid import GRID_NAVIGATION_CONTRACT, RectCell, RectEdge


class NavigationMetadataExporter:
    """Writes the rect grid navigation contract v3 as JSON on a lightweight empty."""

    def create_rect_contract_object(
        self,
        collection: bpy.types.Collection,
        *,
        building_id: str,
        walkable_cells: set[RectCell],
        blocked_edges: set[RectEdge],
        door_edges: set[RectEdge],
        blocked_cells: set[RectCell] | None = None,
        story_index: int = 0,
        story_y_m: float = 0.0,
    ) -> bpy.types.Object:
        blocked_keys = {edge.canonical().key() for edge in blocked_edges}
        door_keys = {edge.canonical().key() for edge in door_edges}
        if blocked_keys & door_keys:
            print(f"[GridValidation] door edges override blocked edges: {sorted(blocked_keys & door_keys)}")

        payload = {
            "contract": GRID_NAVIGATION_CONTRACT,
            "grid_type": "rect",
            "tile_size_m": float(WORLD_TILE_SIZE_M),
            "origin": {"x": float(GAME_GRID_ORIGIN_X_M), "z": float(GAME_GRID_ORIGIN_Z_M)},
            "coordinate_mapping": "blender_xy_to_game_xz",
            "building_id": str(building_id),
            "stories": [
                {
                    "story_index": int(story_index),
                    "story_y_m": float(story_y_m),
                    "walkable_cells": [cell.to_game_dict() for cell in sorted(walkable_cells)],
                    "blocked_cells": [
                        {"x": cell.x, "z": cell.y, "reason": "wall_occupancy"}
                        for cell in sorted(blocked_cells or set())
                    ],
                    "blocked_edges": [edge.to_game_dict("wall") for edge in sorted(edge.canonical() for edge in blocked_edges)],
                    "door_edges": [
                        {
                            "a": edge.canonical().a.to_game_dict(),
                            "b": edge.canonical().b.to_game_dict(),
                            "door_id": f"Door_Story{story_index}_{index:03d}",
                            "is_open": True,
                        }
                        for index, edge in enumerate(sorted(edge.canonical() for edge in door_edges), start=1)
                    ],
                    "stairs": [],
                }
            ],
        }
        obj = bpy.data.objects.new("BuildingGridNavigationMetadata", None)
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.35
        obj["generated_by"] = ADDON_ID
        obj["building_part"] = "metadata"
        obj["grid_contract"] = GRID_NAVIGATION_CONTRACT
        obj["grid_type"] = "rect"
        obj["tile_size_m"] = float(WORLD_TILE_SIZE_M)
        obj["game_navigation_json"] = json.dumps(payload, separators=(",", ":"))
        link_object(collection, obj)
        return obj

    def create_rect_contract_from_collection(self, collection: bpy.types.Collection, *, building_id: str) -> bpy.types.Object:
        walkable_cells: set[RectCell] = set()
        blocked_edges: set[RectEdge] = set()
        door_edges: set[RectEdge] = set()

        for obj in self._iter_objects(collection):
            if obj.name.startswith("BuildingGridNavigationMetadata"):
                bpy.data.objects.remove(obj, do_unlink=True)
                continue
            part = str(obj.get("building_part", obj.get("part", ""))).lower()
            if part == "floor":
                walkable_cells.update(self._read_cells(obj.get("grid_cells")))
            if part in {"outer_wall", "inner_wall"}:
                blocked_edges.update(self._read_edges(obj.get("blocked_edges")))
            if part == "door":
                edge = self._read_edge(obj.get("door_edge"))
                if edge is not None:
                    door_edges.add(edge)

        return self.create_rect_contract_object(
            collection,
            building_id=building_id,
            walkable_cells=walkable_cells,
            blocked_edges=blocked_edges,
            door_edges=door_edges,
        )

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

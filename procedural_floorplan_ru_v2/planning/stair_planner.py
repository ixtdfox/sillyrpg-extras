from __future__ import annotations

import math
from collections import deque

from ..domain.rooms import Room
from ..domain.stairs import StairOpeningPlan, StairPlacement
from .stair_validator import StairPlacementValidator


ShapeTile = tuple[int, int]
TileEdge = frozenset[ShapeTile]


class StairPlanner:
    """Chooses a deterministic stair placement inside the already planned floor layout."""

    def __init__(self):
        self.validator = StairPlacementValidator()

    def plan(self, context) -> StairPlacement | None:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        if story_plan is None or building_plan is None or story_plan.story_index >= (building_plan.story_count - 1):
            return None

        footprint_tiles = set(context.footprint.tiles)
        if not footprint_tiles:
            return None

        opening_tiles = {
            tile
            for opening in story_plan.floor_openings
            for tile in opening.tiles
        }
        room_by_tile = self._room_by_tile(context.rooms, footprint_tiles)
        passage_edges = self._door_passage_edges(context.door_placements)
        forbidden_tiles = opening_tiles | self._collect_forbidden_tiles(context, footprint_tiles)
        walkable_seed_tiles = footprint_tiles - opening_tiles
        if not walkable_seed_tiles:
            return None

        geometry = self._stair_geometry(context)
        candidates: list[StairPlacement] = []
        building_center = self._tile_centroid(footprint_tiles)
        rooms = context.rooms or [Room(id=1, tiles=frozenset(footprint_tiles))]
        rooms_by_id = {room.id: room for room in rooms}
        room_tile_sets = {room.id: set(room.tiles) for room in rooms}
        room_scores = {room.id: self._room_score(room, room_tile_sets[room.id], footprint_tiles, context) for room in rooms}

        for orientation in ("x", "y"):
            rect_width, rect_height = self._candidate_size_tiles(geometry, orientation)
            for origin_x, origin_y, occupied_tiles in self._candidate_rectangles(footprint_tiles, rect_width, rect_height):
                if occupied_tiles & forbidden_tiles:
                    continue

                room_overlap = self._room_overlap_counts(occupied_tiles, room_by_tile)
                if not room_overlap:
                    continue
                dominant_room_id = sorted(room_overlap.items(), key=lambda item: (-item[1], item[0]))[0][0]

                if not self._rooms_remain_usable(room_tile_sets, room_overlap, occupied_tiles, context.settings.stairs.min_free_area):
                    continue

                walkable_tiles = footprint_tiles - opening_tiles - occupied_tiles
                if not walkable_tiles:
                    continue

                approach_tiles = self._approach_tiles(occupied_tiles, walkable_tiles)
                if not approach_tiles:
                    continue
                if not self._walkable_floor_is_accessible(
                    context,
                    walkable_tiles=walkable_tiles,
                    approach_tiles=approach_tiles,
                    room_by_tile=room_by_tile,
                    passage_edges=passage_edges,
                ):
                    continue

                clearance_tiles = self._expand_tiles(occupied_tiles, footprint_tiles, margin_tiles=1)
                score = self._candidate_score(
                    origin_x=origin_x,
                    origin_y=origin_y,
                    occupied_tiles=occupied_tiles,
                    room=rooms_by_id[dominant_room_id],
                    room_tiles=room_tile_sets[dominant_room_id],
                    room_score=room_scores[dominant_room_id],
                    building_center=building_center,
                    footprint_tiles=footprint_tiles,
                    orientation=orientation,
                    approach_tiles=approach_tiles,
                )
                opening = StairOpeningPlan(
                    from_story=story_plan.story_index,
                    to_story=story_plan.story_index + 1,
                    tiles=frozenset(occupied_tiles),
                    bounds=(
                        float(origin_x),
                        float(origin_y),
                        float(origin_x + rect_width),
                        float(origin_y + rect_height),
                    ),
                )
                candidates.append(
                    StairPlacement(
                        from_story=story_plan.story_index,
                        to_story=story_plan.story_index + 1,
                        room_id=dominant_room_id,
                        orientation=orientation,
                        x=origin_x,
                        y=origin_y,
                        width=float(rect_height),
                        length=float(rect_width),
                        stair_width=context.settings.stairs.width,
                        landing_size=context.settings.stairs.landing_size,
                        mid_landing_size=context.settings.stairs.mid_landing_size,
                        riser_height=context.settings.stairs.riser_height,
                        tread_depth=context.settings.stairs.tread_depth,
                        riser_count=geometry["riser_count"],
                        lower_riser_count=geometry["lower_risers"],
                        upper_riser_count=geometry["upper_risers"],
                        travel_run=geometry["travel_run"],
                        occupied_tiles=frozenset(occupied_tiles),
                        clearance_tiles=frozenset(clearance_tiles),
                        opening=opening,
                        room_score=room_scores[dominant_room_id],
                        candidate_score=score,
                    )
                )
                validation = self.validator.validate(candidates[-1], context)
                if not validation.is_valid:
                    candidates.pop()

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                -item.candidate_score,
                item.room_id,
                item.orientation,
                item.y,
                item.x,
            )
        )
        return candidates[0]

    def _stair_geometry(self, context) -> dict[str, float | int]:
        wall_height = float(context.settings.walls.wall_height)
        riser_height = float(context.settings.stairs.riser_height)
        riser_count = max(12, int(math.ceil(wall_height / max(riser_height, 0.01))))
        lower_risers = riser_count // 2
        upper_risers = riser_count - lower_risers
        travel_run = max(lower_risers, upper_risers) * float(context.settings.stairs.tread_depth)
        long_dim = max(1.0, travel_run + float(context.settings.stairs.mid_landing_size))
        short_dim = max(1.0, float(context.settings.stairs.width) * 2.0)
        min_room_tiles = int(math.ceil(long_dim * short_dim + float(context.settings.stairs.min_free_area)))
        return {
            "riser_count": riser_count,
            "lower_risers": lower_risers,
            "upper_risers": upper_risers,
            "travel_run": travel_run,
            "long_dim": long_dim,
            "short_dim": short_dim,
            "min_room_tiles": max(1, min_room_tiles),
        }

    def _candidate_size_tiles(self, geometry: dict[str, float | int], orientation: str) -> tuple[int, int]:
        long_tiles = max(1, int(math.ceil(float(geometry["long_dim"]))))
        short_tiles = max(1, int(math.ceil(float(geometry["short_dim"]))))
        if orientation == "x":
            return long_tiles, short_tiles
        return short_tiles, long_tiles

    def _candidate_rectangles(self, room_tiles: set[ShapeTile], rect_width: int, rect_height: int):
        xs = [tile_x for tile_x, _ in room_tiles]
        ys = [tile_y for _, tile_y in room_tiles]
        for origin_y in range(min(ys), max(ys) - rect_height + 2):
            for origin_x in range(min(xs), max(xs) - rect_width + 2):
                occupied_tiles = {
                    (tile_x, tile_y)
                    for tile_x in range(origin_x, origin_x + rect_width)
                    for tile_y in range(origin_y, origin_y + rect_height)
                }
                if occupied_tiles <= room_tiles:
                    yield origin_x, origin_y, occupied_tiles

    def _room_overlap_counts(self, occupied_tiles: set[ShapeTile], room_by_tile: dict[ShapeTile, int]) -> dict[int, int]:
        overlap: dict[int, int] = {}
        for tile in occupied_tiles:
            room_id = room_by_tile.get(tile)
            if room_id is None:
                continue
            overlap[room_id] = overlap.get(room_id, 0) + 1
        return overlap

    def _room_by_tile(self, rooms: list[Room], footprint_tiles: set[ShapeTile]) -> dict[ShapeTile, int]:
        if not rooms:
            return {tile: 1 for tile in footprint_tiles}
        mapping: dict[ShapeTile, int] = {}
        for room in rooms:
            for tile in room.tiles:
                mapping[tile] = room.id
        return mapping

    def _collect_forbidden_tiles(self, context, footprint_tiles: set[ShapeTile]) -> set[ShapeTile]:
        forbidden_tiles: set[ShapeTile] = set()
        for placement in context.door_placements:
            forbidden_tiles |= self._tiles_intersecting_rect(
                footprint_tiles,
                *self._opening_forbidden_rect(placement.orientation, placement.slot_start, placement.slot_end, placement.line, context.settings.stairs.door_clearance),
            )
        for placement in context.window_placements:
            forbidden_tiles |= self._tiles_intersecting_rect(
                footprint_tiles,
                *self._opening_forbidden_rect(placement.orientation, placement.start, placement.end, placement.line, context.settings.stairs.window_clearance),
            )
        return forbidden_tiles

    def _opening_forbidden_rect(self, orientation: str, start: float, end: float, line: float, clearance: float) -> tuple[float, float, float, float]:
        if orientation == "x":
            return start - clearance, line - clearance, end + clearance, line + clearance
        return line - clearance, start - clearance, line + clearance, end + clearance

    def _tiles_intersecting_rect(
        self,
        footprint_tiles: set[ShapeTile],
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> set[ShapeTile]:
        result: set[ShapeTile] = set()
        for tile_x, tile_y in footprint_tiles:
            center_x = tile_x + 0.5
            center_y = tile_y + 0.5
            if center_x < min_x or center_x > max_x:
                continue
            if center_y < min_y or center_y > max_y:
                continue
            result.add((tile_x, tile_y))
        return result

    def _door_passage_edges(self, placements) -> set[TileEdge]:
        edges: set[TileEdge] = set()
        for placement in placements:
            if placement.door_type != "interior":
                continue
            if placement.orientation == "x":
                north_tile_y = int(round(placement.line))
                south_tile_y = north_tile_y - 1
                start_x = int(math.floor(placement.slot_start + 1e-6))
                end_x = int(math.ceil(placement.slot_end - 1e-6))
                for tile_x in range(start_x, end_x):
                    edges.add(frozenset({(tile_x, south_tile_y), (tile_x, north_tile_y)}))
                continue

            east_tile_x = int(round(placement.line))
            west_tile_x = east_tile_x - 1
            start_y = int(math.floor(placement.slot_start + 1e-6))
            end_y = int(math.ceil(placement.slot_end - 1e-6))
            for tile_y in range(start_y, end_y):
                edges.add(frozenset({(west_tile_x, tile_y), (east_tile_x, tile_y)}))
        return edges

    def _approach_tiles(self, occupied_tiles: set[ShapeTile], walkable_tiles: set[ShapeTile]) -> set[ShapeTile]:
        return {
            neighbor
            for tile_x, tile_y in occupied_tiles
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1))
            if neighbor in walkable_tiles
        }

    def _walkable_floor_is_accessible(
        self,
        context,
        *,
        walkable_tiles: set[ShapeTile],
        approach_tiles: set[ShapeTile],
        room_by_tile: dict[ShapeTile, int],
        passage_edges: set[TileEdge],
    ) -> bool:
        seed_tiles = self._entry_seed_tiles(context, walkable_tiles)
        if not seed_tiles:
            seed_tiles = {min(walkable_tiles)}
        visited = self._flood_walkable(walkable_tiles, room_by_tile, passage_edges, seed_tiles)
        return bool(approach_tiles & visited) and len(visited) == len(walkable_tiles)

    def _entry_seed_tiles(self, context, walkable_tiles: set[ShapeTile]) -> set[ShapeTile]:
        seeds: set[ShapeTile] = set()
        for placement in context.door_placements:
            if placement.door_type != "entry":
                continue
            if placement.orientation == "x":
                inside_y = int(round(placement.line)) if placement.host_wall_side == "south" else int(round(placement.line)) - 1
                start_x = int(math.floor(placement.slot_start + 1e-6))
                end_x = int(math.ceil(placement.slot_end - 1e-6))
                for tile_x in range(start_x, end_x):
                    tile = (tile_x, inside_y)
                    if tile in walkable_tiles:
                        seeds.add(tile)
                continue

            inside_x = int(round(placement.line)) if placement.host_wall_side == "west" else int(round(placement.line)) - 1
            start_y = int(math.floor(placement.slot_start + 1e-6))
            end_y = int(math.ceil(placement.slot_end - 1e-6))
            for tile_y in range(start_y, end_y):
                tile = (inside_x, tile_y)
                if tile in walkable_tiles:
                    seeds.add(tile)
        return seeds

    def _flood_walkable(
        self,
        walkable_tiles: set[ShapeTile],
        room_by_tile: dict[ShapeTile, int],
        passage_edges: set[TileEdge],
        seed_tiles: set[ShapeTile],
    ) -> set[ShapeTile]:
        queue = deque(tile for tile in seed_tiles if tile in walkable_tiles)
        visited = set(queue)
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1)):
                if neighbor not in walkable_tiles or neighbor in visited:
                    continue
                if not self._tiles_connected((tile_x, tile_y), neighbor, room_by_tile, passage_edges):
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return visited

    def _tiles_connected(
        self,
        tile_a: ShapeTile,
        tile_b: ShapeTile,
        room_by_tile: dict[ShapeTile, int],
        passage_edges: set[TileEdge],
    ) -> bool:
        return True

    def _remaining_room_connected(self, room_tiles: set[ShapeTile], occupied_tiles: set[ShapeTile]) -> bool:
        remaining = room_tiles - occupied_tiles
        if not remaining:
            return False
        start = next(iter(remaining))
        queue = deque([start])
        visited = {start}
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1)):
                if neighbor not in remaining or neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return len(visited) == len(remaining)

    def _rooms_remain_usable(
        self,
        room_tile_sets: dict[int, set[ShapeTile]],
        room_overlap: dict[int, int],
        occupied_tiles: set[ShapeTile],
        min_free_area: float,
    ) -> bool:
        for room_id, overlap_count in room_overlap.items():
            room_tiles = room_tile_sets[room_id]
            remaining_area = float(len(room_tiles - occupied_tiles))
            if remaining_area < min_free_area and overlap_count >= len(room_tiles):
                return False
            if remaining_area > 0.0 and not self._remaining_room_connected(room_tiles, occupied_tiles):
                return False
        return True

    def _expand_tiles(self, tiles: set[ShapeTile], footprint_tiles: set[ShapeTile], *, margin_tiles: int) -> set[ShapeTile]:
        expanded = set(tiles)
        frontier = set(tiles)
        for _ in range(margin_tiles):
            next_frontier: set[ShapeTile] = set()
            for tile_x, tile_y in frontier:
                for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1)):
                    if neighbor in footprint_tiles and neighbor not in expanded:
                        next_frontier.add(neighbor)
            expanded |= next_frontier
            frontier = next_frontier
        return expanded

    def _room_score(self, room: Room, room_tiles: set[ShapeTile], footprint_tiles: set[ShapeTile], context) -> float:
        exterior_contacts = sum(
            1
            for tile_x, tile_y in room_tiles
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1))
            if neighbor not in footprint_tiles
        )
        door_contacts = sum(
            1
            for placement in context.door_placements
            if placement.door_type == "interior" and room.id in {placement.room_a_id, placement.room_b_id}
        )
        return room.area + (door_contacts * 2.0) - (exterior_contacts * 0.35)

    def _candidate_score(
        self,
        *,
        origin_x: int,
        origin_y: int,
        occupied_tiles: set[ShapeTile],
        room: Room,
        room_tiles: set[ShapeTile],
        room_score: float,
        building_center: tuple[float, float],
        footprint_tiles: set[ShapeTile],
        orientation: str,
        approach_tiles: set[ShapeTile],
    ) -> float:
        min_x, min_y, max_x, max_y = room.bbox
        cand_min_x = min(tile_x for tile_x, _ in occupied_tiles)
        cand_max_x = max(tile_x for tile_x, _ in occupied_tiles) + 1
        cand_min_y = min(tile_y for _, tile_y in occupied_tiles)
        cand_max_y = max(tile_y for _, tile_y in occupied_tiles) + 1
        cand_center = self._tile_centroid(occupied_tiles)
        exterior_contacts = sum(
            1
            for tile_x, tile_y in occupied_tiles
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1))
            if neighbor not in footprint_tiles
        )
        edge_contacts = sum(
            1
            for condition in (
                cand_min_x == min_x,
                cand_min_y == min_y,
                cand_max_x == max_x,
                cand_max_y == max_y,
            )
            if condition
        )
        room_width = room.width
        room_height = room.height
        orientation_bonus = 3.0 if (orientation == "x" and room_width >= room_height) or (orientation == "y" and room_height > room_width) else 0.0
        center_distance = abs(cand_center[0] - building_center[0]) + abs(cand_center[1] - building_center[1])
        return (
            room_score
            + (len(approach_tiles) * 1.5)
            + (edge_contacts * 4.0)
            + orientation_bonus
            - (exterior_contacts * 5.0)
            - center_distance
        )

    def _tile_centroid(self, tiles: set[ShapeTile]) -> tuple[float, float]:
        xs = [tile_x + 0.5 for tile_x, _ in tiles]
        ys = [tile_y + 0.5 for _, tile_y in tiles]
        return sum(xs) / len(xs), sum(ys) / len(ys)

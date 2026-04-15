from __future__ import annotations

import math
from collections import deque
from random import Random

from ..domain.rooms import Room


class RoomPlanner:
    """Plans room subdivision in the domain layer without Blender dependencies."""

    MAX_ROOM_ASPECT_RATIO = 3.0

    def plan_rooms(
        self,
        footprint_tiles: set[tuple[int, int]],
        *,
        target_rooms: int,
        min_room_side_m: float,
        rng: Random | None,
    ) -> list[Room]:
        min_room_side_tiles = self._min_room_side_tiles(min_room_side_m)
        rooms: list[Room] = [Room(id=1, tiles=frozenset(footprint_tiles))]
        next_room_id = 2

        while len(rooms) < target_rooms:
            split_index = None
            split_result = None
            room_candidates = sorted(enumerate(rooms), key=lambda item: (-len(item[1].tiles), item[1].id))
            if rng is not None and len(room_candidates) > 1:
                top_area = len(room_candidates[0][1].tiles)
                near_top = [item for item in room_candidates if len(item[1].tiles) >= top_area * 0.8]
                room_candidates = rng.sample(near_top, k=len(near_top)) + [item for item in room_candidates if item not in near_top]

            for index, room in room_candidates:
                candidate = self._find_split(room, rng=rng, min_room_side_tiles=min_room_side_tiles)
                if candidate is None:
                    continue
                split_index = index
                split_result = candidate
                break

            if split_index is None or split_result is None:
                break

            room_a_tiles, room_b_tiles = split_result
            rooms.pop(split_index)
            rooms.append(Room(id=next_room_id, tiles=frozenset(room_a_tiles)))
            rooms.append(Room(id=next_room_id + 1, tiles=frozenset(room_b_tiles)))
            next_room_id += 2

        return sorted(rooms, key=lambda room: room.id)

    def _min_room_side_tiles(self, min_room_side_m: float | None) -> int:
        if min_room_side_m is None:
            return 3
        return max(1, int(math.ceil(float(min_room_side_m))))

    def _find_split(self, room: Room, *, rng: Random | None, min_room_side_tiles: int) -> tuple[set[tuple[int, int]], set[tuple[int, int]]] | None:
        orientation_order = ["x", "y"] if room.width > room.height else ["y", "x"]
        if rng is not None and room.width != room.height and rng.random() < 0.35:
            orientation_order = list(reversed(orientation_order))
        for orientation in orientation_order:
            candidates = self._split_candidates(room, orientation, min_room_side_tiles=min_room_side_tiles)
            if not candidates:
                continue
            candidates.sort(key=lambda item: item[0])
            if rng is None or len(candidates) == 1:
                return candidates[0][1]
            shortlist = candidates[: min(3, len(candidates))]
            weights = [1.0 / (index + 1) for index in range(len(shortlist))]
            return rng.choices(shortlist, weights=weights, k=1)[0][1]
        return None

    def _split_candidates(
        self,
        room: Room,
        orientation: str,
        *,
        min_room_side_tiles: int,
    ) -> list[tuple[tuple[float, float, float], tuple[set[tuple[int, int]], set[tuple[int, int]]]]]:
        min_x, min_y, max_x, max_y = room.bbox
        cut_candidates = (
            list(range(min_x + min_room_side_tiles, max_x - min_room_side_tiles + 1))
            if orientation == "x"
            else list(range(min_y + min_room_side_tiles, max_y - min_room_side_tiles + 1))
        )
        midpoint = (min_x + max_x) * 0.5 if orientation == "x" else (min_y + max_y) * 0.5
        candidates = []
        for cut in cut_candidates:
            if orientation == "x":
                tiles_a = {tile for tile in room.tiles if tile[0] < cut}
                tiles_b = {tile for tile in room.tiles if tile[0] >= cut}
            else:
                tiles_a = {tile for tile in room.tiles if tile[1] < cut}
                tiles_b = {tile for tile in room.tiles if tile[1] >= cut}
            if not self._is_valid_room_shape(tiles_a, min_room_side_tiles=min_room_side_tiles):
                continue
            if not self._is_valid_room_shape(tiles_b, min_room_side_tiles=min_room_side_tiles):
                continue
            balance = abs(len(tiles_a) - len(tiles_b))
            compactness = self._room_aspect_ratio(tiles_a) + self._room_aspect_ratio(tiles_b)
            center_distance = abs(cut - midpoint)
            candidates.append(((balance, compactness, center_distance), (tiles_a, tiles_b)))
        return candidates

    def _is_valid_room_shape(self, tiles: set[tuple[int, int]], *, min_room_side_tiles: int) -> bool:
        if not tiles:
            return False
        min_x, min_y, max_x, max_y = self._bbox_for_tiles(tiles)
        if max_x - min_x < min_room_side_tiles or max_y - min_y < min_room_side_tiles:
            return False
        if self._room_aspect_ratio(tiles) > self.MAX_ROOM_ASPECT_RATIO:
            return False
        if not self._is_connected(tiles):
            return False
        if self._has_holes(tiles):
            return False
        if self._has_narrow_spans(tiles, min_room_side_tiles=min_room_side_tiles):
            return False
        return True

    def _bbox_for_tiles(self, tiles: set[tuple[int, int]]) -> tuple[int, int, int, int]:
        xs = [x for x, _ in tiles]
        ys = [y for _, y in tiles]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def _room_aspect_ratio(self, tiles: set[tuple[int, int]]) -> float:
        min_x, min_y, max_x, max_y = self._bbox_for_tiles(tiles)
        width = max_x - min_x
        height = max_y - min_y
        shorter = max(1, min(width, height))
        return max(width, height) / shorter

    def _is_connected(self, tiles: set[tuple[int, int]]) -> bool:
        start = next(iter(tiles))
        queue = deque([start])
        visited = {start}
        while queue:
            tile_x, tile_y = queue.popleft()
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1)):
                if neighbor not in tiles or neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return len(visited) == len(tiles)

    def _has_holes(self, tiles: set[tuple[int, int]]) -> bool:
        min_x, min_y, max_x, max_y = self._bbox_for_tiles(tiles)
        empty_cells = {(x, y) for x in range(min_x, max_x) for y in range(min_y, max_y) if (x, y) not in tiles}
        if not empty_cells:
            return False
        boundary_empty = deque(
            [cell for cell in empty_cells if cell[0] == min_x or cell[0] == max_x - 1 or cell[1] == min_y or cell[1] == max_y - 1]
        )
        reachable = set(boundary_empty)
        while boundary_empty:
            tile_x, tile_y = boundary_empty.popleft()
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1)):
                if neighbor not in empty_cells or neighbor in reachable:
                    continue
                reachable.add(neighbor)
                boundary_empty.append(neighbor)
        return len(reachable) != len(empty_cells)

    def _has_narrow_spans(self, tiles: set[tuple[int, int]], *, min_room_side_tiles: int) -> bool:
        rows: dict[int, list[int]] = {}
        cols: dict[int, list[int]] = {}
        for tile_x, tile_y in tiles:
            rows.setdefault(tile_y, []).append(tile_x)
            cols.setdefault(tile_x, []).append(tile_y)
        return self._axis_has_narrow_spans(rows, min_room_side_tiles=min_room_side_tiles) or self._axis_has_narrow_spans(
            cols,
            min_room_side_tiles=min_room_side_tiles,
        )

    def _axis_has_narrow_spans(self, grouped_positions: dict[int, list[int]], *, min_room_side_tiles: int) -> bool:
        for positions in grouped_positions.values():
            span_start = None
            prev = None
            for value in sorted(positions):
                if span_start is None:
                    span_start = value
                    prev = value
                    continue
                if value == prev + 1:
                    prev = value
                    continue
                if prev - span_start + 1 < min_room_side_tiles:
                    return True
                span_start = value
                prev = value
            if span_start is not None and prev is not None and prev - span_start + 1 < min_room_side_tiles:
                return True
        return False

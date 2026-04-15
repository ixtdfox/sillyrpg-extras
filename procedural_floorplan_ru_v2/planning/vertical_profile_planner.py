from __future__ import annotations

import math
from collections import deque
from random import Random

from ..common.shape_generator import Footprint
from ..domain.building import VerticalProfileMode


ShapeTile = tuple[int, int]


class VerticalProfilePlanner:
    """Plans per-story footprints before builders start creating geometry."""

    def plan_story_footprints(
        self,
        base_footprint: Footprint,
        *,
        story_count: int,
        shape_key: str,
        vertical_profile_mode: str,
        profile_strength: float,
        min_room_side_m: float,
        stair_width: float,
        rng: Random,
    ) -> list[Footprint]:
        mode = VerticalProfileMode(vertical_profile_mode)
        if story_count <= 1 or mode == VerticalProfileMode.STRICT:
            return [self._make_footprint(base_footprint, set(base_footprint.tiles)) for _ in range(story_count)]

        min_side_tiles = max(1, int(math.ceil(float(min_room_side_m))))
        max_offset_tiles = max(1, int(round(1 + (profile_strength * 2.0))))
        min_overlap_ratio = max(0.55, 0.8 - (profile_strength * 0.2))
        base_tiles = set(base_footprint.tiles)
        protected_core = self._protected_core(base_tiles, min_side_tiles=min_side_tiles, stair_width=stair_width)
        story_tiles: list[set[ShapeTile]] = [set(base_tiles)]

        offset_direction = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        pinwheel_start = rng.randrange(4)

        for story_index in range(1, story_count):
            previous_tiles = set(story_tiles[-1])
            candidates = self._candidate_chain(
                mode=mode,
                previous_tiles=previous_tiles,
                base_tiles=base_tiles,
                protected_core=protected_core,
                story_index=story_index,
                story_count=story_count,
                shape_key=shape_key,
                max_offset_tiles=max_offset_tiles,
                pinwheel_start=pinwheel_start,
                offset_direction=offset_direction,
                rng=rng,
            )

            next_tiles = previous_tiles
            for candidate_tiles in candidates:
                if self._is_valid_candidate(
                    candidate_tiles,
                    previous_tiles=previous_tiles,
                    protected_core=protected_core,
                    min_side_tiles=min_side_tiles,
                    min_overlap_ratio=min_overlap_ratio,
                ):
                    next_tiles = candidate_tiles
                    break
            story_tiles.append(next_tiles)

        return [self._make_footprint(base_footprint, tiles) for tiles in story_tiles]

    def _candidate_chain(
        self,
        *,
        mode: VerticalProfileMode,
        previous_tiles: set[ShapeTile],
        base_tiles: set[ShapeTile],
        protected_core: set[ShapeTile],
        story_index: int,
        story_count: int,
        shape_key: str,
        max_offset_tiles: int,
        pinwheel_start: int,
        offset_direction: tuple[int, int],
        rng: Random,
    ) -> list[set[ShapeTile]]:
        if mode == VerticalProfileMode.SETBACK:
            return self._setback_candidates(previous_tiles, story_index=story_index, max_steps=max_offset_tiles, rng=rng)
        if mode == VerticalProfileMode.OFFSET_STACK:
            return self._offset_candidates(previous_tiles, base_tiles=base_tiles, direction=offset_direction, max_shift=max_offset_tiles)
        if mode == VerticalProfileMode.PINWHEEL:
            return self._pinwheel_candidates(previous_tiles, base_tiles=base_tiles, direction_index=(pinwheel_start + story_index - 1) % 4, max_shift=max_offset_tiles)
        if mode == VerticalProfileMode.MIXED:
            return self._mixed_candidates(
                previous_tiles,
                base_tiles=base_tiles,
                protected_core=protected_core,
                story_index=story_index,
                story_count=story_count,
                shape_key=shape_key,
                max_offset_tiles=max_offset_tiles,
                pinwheel_start=pinwheel_start,
                offset_direction=offset_direction,
                rng=rng,
            )
        return [set(previous_tiles)]

    def _mixed_candidates(
        self,
        previous_tiles: set[ShapeTile],
        *,
        base_tiles: set[ShapeTile],
        protected_core: set[ShapeTile],
        story_index: int,
        story_count: int,
        shape_key: str,
        max_offset_tiles: int,
        pinwheel_start: int,
        offset_direction: tuple[int, int],
        rng: Random,
    ) -> list[set[ShapeTile]]:
        del protected_core, shape_key
        progress = story_index / max(1, story_count - 1)
        strategies: list[VerticalProfileMode] = [VerticalProfileMode.STRICT, VerticalProfileMode.SETBACK]
        if progress >= 0.25:
            strategies.append(VerticalProfileMode.OFFSET_STACK)
        if progress >= 0.5:
            strategies.append(VerticalProfileMode.PINWHEEL)
        strategies = rng.sample(strategies, k=len(strategies))

        candidates: list[set[ShapeTile]] = [set(previous_tiles)]
        for strategy in strategies:
            if strategy == VerticalProfileMode.STRICT:
                candidates.append(set(previous_tiles))
            elif strategy == VerticalProfileMode.SETBACK:
                candidates.extend(self._setback_candidates(previous_tiles, story_index=story_index, max_steps=max_offset_tiles, rng=rng))
            elif strategy == VerticalProfileMode.OFFSET_STACK:
                candidates.extend(self._offset_candidates(previous_tiles, base_tiles=base_tiles, direction=offset_direction, max_shift=max_offset_tiles))
            elif strategy == VerticalProfileMode.PINWHEEL:
                candidates.extend(
                    self._pinwheel_candidates(
                        previous_tiles,
                        base_tiles=base_tiles,
                        direction_index=(pinwheel_start + story_index - 1) % 4,
                        max_shift=max_offset_tiles,
                    )
                )
        return candidates

    def _setback_candidates(self, tiles: set[ShapeTile], *, story_index: int, max_steps: int, rng: Random) -> list[set[ShapeTile]]:
        directions = ["north", "east", "south", "west"]
        rng.shuffle(directions)
        preferred = directions[: 1 + ((story_index + max_steps) % 2)]
        candidates: list[set[ShapeTile]] = []
        for step in range(max_steps, 0, -1):
            for count in range(len(preferred), 0, -1):
                candidate = set(tiles)
                for direction in preferred[:count]:
                    candidate = self._trim_outer_edge(candidate, direction=direction, amount=step)
                candidates.append(candidate)
        candidates.append(set(tiles))
        return candidates

    def _offset_candidates(
        self,
        tiles: set[ShapeTile],
        *,
        base_tiles: set[ShapeTile],
        direction: tuple[int, int],
        max_shift: int,
    ) -> list[set[ShapeTile]]:
        del base_tiles
        candidates: list[set[ShapeTile]] = []
        for shift in range(max_shift, 0, -1):
            dx = direction[0] * shift
            dy = direction[1] * shift
            candidates.append(self._translate(tiles, dx=dx, dy=dy))
        candidates.append(set(tiles))
        return candidates

    def _pinwheel_candidates(
        self,
        tiles: set[ShapeTile],
        *,
        base_tiles: set[ShapeTile],
        direction_index: int,
        max_shift: int,
    ) -> list[set[ShapeTile]]:
        del base_tiles
        directions = ((0, 1), (1, 0), (0, -1), (-1, 0))
        names = ("north", "east", "south", "west")
        dx, dy = directions[direction_index]
        active_side = names[direction_index]
        opposite_side = names[(direction_index + 2) % 4]
        lateral_side = names[(direction_index + 1) % 4]
        candidates: list[set[ShapeTile]] = []
        for shift in range(max_shift, 0, -1):
            translated = self._translate(tiles, dx=dx * shift, dy=dy * shift)
            candidates.append(self._trim_outer_edge(translated, direction=opposite_side, amount=shift))
            candidates.append(self._trim_outer_edge(translated, direction=lateral_side, amount=max(1, shift - 1)))
        candidates.append(self._trim_outer_edge(set(tiles), direction=opposite_side, amount=1))
        candidates.append(set(tiles))
        return candidates

    def _translate(self, tiles: set[ShapeTile], *, dx: int, dy: int) -> set[ShapeTile]:
        return {(tile_x + dx, tile_y + dy) for tile_x, tile_y in tiles}

    def _trim_outer_edge(self, tiles: set[ShapeTile], *, direction: str, amount: int) -> set[ShapeTile]:
        candidate = set(tiles)
        for _ in range(max(1, amount)):
            if not candidate:
                break
            xs = [tile_x for tile_x, _ in candidate]
            ys = [tile_y for _, tile_y in candidate]
            if direction == "west":
                edge_value = min(xs)
                candidate = {tile for tile in candidate if tile[0] != edge_value}
            elif direction == "east":
                edge_value = max(xs)
                candidate = {tile for tile in candidate if tile[0] != edge_value}
            elif direction == "south":
                edge_value = min(ys)
                candidate = {tile for tile in candidate if tile[1] != edge_value}
            else:
                edge_value = max(ys)
                candidate = {tile for tile in candidate if tile[1] != edge_value}
        return candidate

    def _protected_core(self, tiles: set[ShapeTile], *, min_side_tiles: int, stair_width: float) -> set[ShapeTile]:
        if not tiles:
            return set()
        centroid_x, centroid_y = self._tile_centroid(tiles)
        target_size = max(4, int(math.ceil(stair_width)) ** 2, min_side_tiles * 2)
        start = min(tiles, key=lambda tile: (abs(tile[0] + 0.5 - centroid_x) + abs(tile[1] + 0.5 - centroid_y), tile[1], tile[0]))
        queue = deque([start])
        visited = {start}
        ordered: list[ShapeTile] = []
        while queue and len(ordered) < target_size:
            tile = queue.popleft()
            ordered.append(tile)
            tile_x, tile_y = tile
            neighbors = sorted(
                (
                    (tile_x + 1, tile_y),
                    (tile_x - 1, tile_y),
                    (tile_x, tile_y + 1),
                    (tile_x, tile_y - 1),
                ),
                key=lambda value: (abs(value[0] + 0.5 - centroid_x) + abs(value[1] + 0.5 - centroid_y), value[1], value[0]),
            )
            for neighbor in neighbors:
                if neighbor not in tiles or neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return set(ordered)

    def _is_valid_candidate(
        self,
        candidate_tiles: set[ShapeTile],
        *,
        previous_tiles: set[ShapeTile],
        protected_core: set[ShapeTile],
        min_side_tiles: int,
        min_overlap_ratio: float,
    ) -> bool:
        if not candidate_tiles:
            return False
        if protected_core and not protected_core <= candidate_tiles:
            return False
        if not self._is_connected(candidate_tiles):
            return False
        min_x, min_y, max_x, max_y = self._bounds(candidate_tiles)
        if (max_x - min_x + 1) < min_side_tiles or (max_y - min_y + 1) < min_side_tiles:
            return False
        min_area = max(min_side_tiles * min_side_tiles, len(protected_core) + min_side_tiles)
        if len(candidate_tiles) < min_area:
            return False
        overlap = len(candidate_tiles & previous_tiles)
        overlap_ratio = overlap / max(1, min(len(candidate_tiles), len(previous_tiles)))
        if overlap_ratio < min_overlap_ratio:
            return False
        if self._has_narrow_spans(candidate_tiles, min_span=min_side_tiles):
            return False
        return True

    def _make_footprint(self, base_footprint: Footprint, tiles: set[ShapeTile]) -> Footprint:
        return Footprint(shape_key=base_footprint.shape_key, tiles=frozenset(sorted(tiles)))

    def _tile_centroid(self, tiles: set[ShapeTile]) -> tuple[float, float]:
        sum_x = sum(tile_x + 0.5 for tile_x, _ in tiles)
        sum_y = sum(tile_y + 0.5 for _, tile_y in tiles)
        count = max(1, len(tiles))
        return sum_x / count, sum_y / count

    def _bounds(self, tiles: set[ShapeTile]) -> tuple[int, int, int, int]:
        xs = [tile_x for tile_x, _ in tiles]
        ys = [tile_y for _, tile_y in tiles]
        return min(xs), min(ys), max(xs), max(ys)

    def _is_connected(self, tiles: set[ShapeTile]) -> bool:
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

    def _has_narrow_spans(self, tiles: set[ShapeTile], *, min_span: int) -> bool:
        rows: dict[int, list[int]] = {}
        cols: dict[int, list[int]] = {}
        for tile_x, tile_y in tiles:
            rows.setdefault(tile_y, []).append(tile_x)
            cols.setdefault(tile_x, []).append(tile_y)
        return self._axis_has_narrow_spans(rows, min_span=min_span) or self._axis_has_narrow_spans(cols, min_span=min_span)

    def _axis_has_narrow_spans(self, grouped_positions: dict[int, list[int]], *, min_span: int) -> bool:
        for positions in grouped_positions.values():
            positions = sorted(positions)
            span_start = positions[0]
            prev = positions[0]
            for value in positions[1:]:
                if value == prev + 1:
                    prev = value
                    continue
                if prev - span_start + 1 < min_span:
                    return True
                span_start = value
                prev = value
            if prev - span_start + 1 < min_span:
                return True
        return False


__all__ = ("VerticalProfilePlanner",)

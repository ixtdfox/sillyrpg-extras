from __future__ import annotations

from ..builders.wall_utils import add_grouped_edge, merge_spans
from ..common.utils import FLOOR_TILE_SIZE_M, quantize_025
from ..domain.walls import WallRun


class TerracePlanner:
    """Plans exposed intermediate-story slab areas as terrace surfaces."""

    def has_terrace_area(self, context) -> bool:
        return bool(self._terrace_tiles(context))

    def plan_tiles(self, context) -> list[tuple[int, int]]:
        return sorted(self._terrace_tiles(context))

    def plan_boundary_runs(self, context) -> list[WallRun]:
        terrace_tiles = self._terrace_tiles(context)
        if not terrace_tiles:
            return []

        upper_tiles = self.upper_tiles(context)
        grouped_edges: dict[tuple[str, str, float], list[tuple[float, float]]] = {}
        for tile_x, tile_y in sorted(terrace_tiles):
            if (tile_x, tile_y + 1) not in terrace_tiles and (tile_x, tile_y + 1) not in upper_tiles:
                add_grouped_edge(grouped_edges, ("x", "north", quantize_025(tile_y + FLOOR_TILE_SIZE_M)), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x, tile_y - 1) not in terrace_tiles and (tile_x, tile_y - 1) not in upper_tiles:
                add_grouped_edge(grouped_edges, ("x", "south", quantize_025(float(tile_y))), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x + 1, tile_y) not in terrace_tiles and (tile_x + 1, tile_y) not in upper_tiles:
                add_grouped_edge(grouped_edges, ("y", "east", quantize_025(tile_x + FLOOR_TILE_SIZE_M)), tile_y, tile_y + FLOOR_TILE_SIZE_M)
            if (tile_x - 1, tile_y) not in terrace_tiles and (tile_x - 1, tile_y) not in upper_tiles:
                add_grouped_edge(grouped_edges, ("y", "west", quantize_025(float(tile_x))), tile_y, tile_y + FLOOR_TILE_SIZE_M)

        runs: list[WallRun] = []
        for (orientation, side, line), spans in grouped_edges.items():
            runs.extend(merge_spans(run_factory=WallRun, run_args=(orientation, side, line), spans=spans))
        return sorted(runs, key=lambda run: (run.orientation, run.side, run.line, run.start))

    def _terrace_tiles(self, context) -> set[tuple[int, int]]:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        if story_plan is None or building_plan is None:
            return set()
        if story_plan.story_index >= (building_plan.story_count - 1):
            return set()
        if getattr(story_plan, "terrace_tiles", None) is not None:
            return set(story_plan.terrace_tiles)

        current_tiles = set(getattr(context.footprint, "tiles", ()))
        upper_tiles = self.upper_tiles(context)
        return current_tiles - upper_tiles

    def upper_tiles(self, context) -> set[tuple[int, int]]:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        if story_plan is None or building_plan is None:
            return set()
        upper_index = story_plan.story_index + 1
        if upper_index >= building_plan.story_count:
            return set()
        return set(building_plan.stories[upper_index].footprint.tiles)


__all__ = ("TerracePlanner",)

from __future__ import annotations

from ..common.utils import FLOOR_TILE_SIZE_M, quantize_025
from ..domain.walls import WallRun
from ..builders.wall_utils import add_grouped_edge, merge_spans


class OuterBoundaryResolver:
    """Resolves footprint perimeter into continuous wall runs."""

    def collect_runs(self, tiles: set[tuple[int, int]]) -> list[WallRun]:
        grouped_edges: dict[tuple[str, str, float], list[tuple[float, float]]] = {}
        for tile_x, tile_y in sorted(tiles):
            if (tile_x, tile_y + 1) not in tiles:
                add_grouped_edge(grouped_edges, ("x", "north", quantize_025(tile_y + FLOOR_TILE_SIZE_M)), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x, tile_y - 1) not in tiles:
                add_grouped_edge(grouped_edges, ("x", "south", quantize_025(float(tile_y))), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x + 1, tile_y) not in tiles:
                add_grouped_edge(grouped_edges, ("y", "east", quantize_025(tile_x + FLOOR_TILE_SIZE_M)), tile_y, tile_y + FLOOR_TILE_SIZE_M)
            if (tile_x - 1, tile_y) not in tiles:
                add_grouped_edge(grouped_edges, ("y", "west", quantize_025(float(tile_x))), tile_y, tile_y + FLOOR_TILE_SIZE_M)

        runs: list[WallRun] = []
        for (orientation, side, line), spans in grouped_edges.items():
            runs.extend(merge_spans(run_factory=WallRun, run_args=(orientation, side, line), spans=spans))
        return sorted(runs, key=lambda run: (run.orientation, run.side, run.line, run.start))

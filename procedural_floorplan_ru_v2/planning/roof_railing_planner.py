from __future__ import annotations

from ..builders.wall_utils import add_grouped_edge, merge_spans
from ..common.utils import FLOOR_TILE_SIZE_M, quantize_025
from ..domain.railings import RailingPostPlacement, RailingRailSegment, RoofRailingRun
from ..domain.walls import WallRun
from .outer_boundary_resolver import OuterBoundaryResolver


class RoofRailingPlanner:
    """Plans roof railing runs from the exact outer contour of the top-story footprint."""

    POST_SPACING_M = 1.0

    def __init__(self):
        self.boundary_resolver = OuterBoundaryResolver()

    def plan(self, context) -> tuple[list[RoofRailingRun], list[RailingPostPlacement], list[RailingRailSegment]]:
        footprint_tiles = set(context.footprint.tiles)
        return self.plan_for_tiles(context, footprint_tiles=footprint_tiles, run_id_prefix="roof_railing")

    def plan_for_tiles(
        self,
        context,
        *,
        footprint_tiles: set[tuple[int, int]],
        run_id_prefix: str,
        blocked_tiles: set[tuple[int, int]] | None = None,
    ) -> tuple[list[RoofRailingRun], list[RailingPostPlacement], list[RailingRailSegment]]:
        runs = self._collect_runs(footprint_tiles, blocked_tiles=blocked_tiles)
        reference_offset = self._reference_offset(context)
        run_reference_lines = {id(run): self._run_reference_line(run, reference_offset=reference_offset) for run in runs}
        corner_tiles = set(footprint_tiles) | set(blocked_tiles or ())
        corner_map = self._build_corner_map(runs, corner_tiles, run_reference_lines)

        planned_runs: list[RoofRailingRun] = []
        post_map: dict[tuple[float, float], RailingPostPlacement] = {}
        rail_segments: list[RailingRailSegment] = []

        for run_index, run in enumerate(runs, start=1):
            run_id = f"{run_id_prefix}:{run_index}"
            start_vertex = self._run_start_vertex(run)
            end_vertex = self._run_end_vertex(run)
            start_corner = corner_map[start_vertex]
            end_corner = corner_map[end_vertex]
            post_positions = tuple(self._run_post_positions(run, start_corner=start_corner, end_corner=end_corner))
            planned_runs.append(
                RoofRailingRun(
                    run_id=run_id,
                    orientation=run.orientation,
                    side=run.side,
                    line=run.line,
                    start=run.start,
                    end=run.end,
                    inset=reference_offset,
                    start_x=start_corner["join_x"],
                    start_y=start_corner["join_y"],
                    end_x=end_corner["join_x"],
                    end_y=end_corner["join_y"],
                    start_corner_type=start_corner["corner_type"],
                    end_corner_type=end_corner["corner_type"],
                    post_positions=post_positions,
                )
            )

            for x, y in post_positions:
                key = (round(x, 6), round(y, 6))
                if key not in post_map:
                    is_corner = key == (start_corner["join_x"], start_corner["join_y"]) or key == (end_corner["join_x"], end_corner["join_y"])
                    corner_type = None
                    if key == (start_corner["join_x"], start_corner["join_y"]):
                        corner_type = start_corner["corner_type"]
                    elif key == (end_corner["join_x"], end_corner["join_y"]):
                        corner_type = end_corner["corner_type"]
                    post_map[key] = RailingPostPlacement(
                        x=key[0],
                        y=key[1],
                        run_id=None if is_corner else run_id,
                        is_corner=is_corner,
                        corner_type=corner_type,
                    )

            for level_index in range(context.settings.roof_railing.rail_count):
                for start_point, end_point in zip(post_positions, post_positions[1:]):
                    rail_segments.append(
                        RailingRailSegment(
                            run_id=run_id,
                            orientation=run.orientation,
                            start_x=start_point[0],
                            start_y=start_point[1],
                            end_x=end_point[0],
                            end_y=end_point[1],
                            level_index=level_index,
                        )
                    )

        posts = sorted(post_map.values(), key=lambda item: (item.y, item.x, item.run_id or ""))
        rails = sorted(rail_segments, key=lambda item: (item.run_id, item.level_index, item.start_y, item.start_x))
        return planned_runs, posts, rails

    def _collect_runs(
        self,
        footprint_tiles: set[tuple[int, int]],
        *,
        blocked_tiles: set[tuple[int, int]] | None,
    ) -> list[WallRun]:
        if not blocked_tiles:
            return self.boundary_resolver.collect_runs(footprint_tiles)

        grouped_edges: dict[tuple[str, str, float], list[tuple[float, float]]] = {}
        for tile_x, tile_y in sorted(footprint_tiles):
            if (tile_x, tile_y + 1) not in footprint_tiles and (tile_x, tile_y + 1) not in blocked_tiles:
                add_grouped_edge(grouped_edges, ("x", "north", quantize_025(tile_y + FLOOR_TILE_SIZE_M)), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x, tile_y - 1) not in footprint_tiles and (tile_x, tile_y - 1) not in blocked_tiles:
                add_grouped_edge(grouped_edges, ("x", "south", quantize_025(float(tile_y))), tile_x, tile_x + FLOOR_TILE_SIZE_M)
            if (tile_x + 1, tile_y) not in footprint_tiles and (tile_x + 1, tile_y) not in blocked_tiles:
                add_grouped_edge(grouped_edges, ("y", "east", quantize_025(tile_x + FLOOR_TILE_SIZE_M)), tile_y, tile_y + FLOOR_TILE_SIZE_M)
            if (tile_x - 1, tile_y) not in footprint_tiles and (tile_x - 1, tile_y) not in blocked_tiles:
                add_grouped_edge(grouped_edges, ("y", "west", quantize_025(float(tile_x))), tile_y, tile_y + FLOOR_TILE_SIZE_M)

        runs: list[WallRun] = []
        for (orientation, side, line), spans in grouped_edges.items():
            runs.extend(merge_spans(run_factory=WallRun, run_args=(orientation, side, line), spans=spans))
        return sorted(runs, key=lambda run: (run.orientation, run.side, run.line, run.start))

    def _reference_offset(self, context) -> float:
        post_half = context.settings.roof_railing.post_size * 0.5
        border_inset = context.settings.roof_border.depth if context.settings.roof_border.enabled else 0.0
        return round(max(post_half, border_inset + post_half), 6)

    def _run_reference_line(self, run, *, reference_offset: float) -> float:
        if run.orientation == "x":
            return round(run.line - reference_offset if run.side == "north" else run.line + reference_offset, 6)
        return round(run.line - reference_offset if run.side == "east" else run.line + reference_offset, 6)

    def _build_corner_map(
        self,
        runs,
        footprint_tiles: set[tuple[int, int]],
        run_reference_lines: dict[int, float],
    ) -> dict[tuple[float, float], dict[str, float | str]]:
        vertex_runs: dict[tuple[float, float], list] = {}
        for run in runs:
            vertex_runs.setdefault(self._run_start_vertex(run), []).append(run)
            vertex_runs.setdefault(self._run_end_vertex(run), []).append(run)

        corner_map: dict[tuple[float, float], dict[str, float | str]] = {}
        for vertex, incident_runs in vertex_runs.items():
            corner_map[vertex] = self._corner_descriptor(
                vertex,
                footprint_tiles,
                incident_runs=incident_runs,
                run_reference_lines=run_reference_lines,
            )
        return corner_map

    def _corner_descriptor(
        self,
        vertex: tuple[float, float],
        footprint_tiles: set[tuple[int, int]],
        *,
        incident_runs: list,
        run_reference_lines: dict[int, float],
    ) -> dict[str, float | str]:
        vertex_x = int(round(vertex[0]))
        vertex_y = int(round(vertex[1]))
        quadrants = {
            "sw": (vertex_x - 1, vertex_y - 1) in footprint_tiles,
            "se": (vertex_x, vertex_y - 1) in footprint_tiles,
            "nw": (vertex_x - 1, vertex_y) in footprint_tiles,
            "ne": (vertex_x, vertex_y) in footprint_tiles,
        }
        occupied = [name for name, present in quadrants.items() if present]
        if len(occupied) == 1:
            corner_type = "convex"
        elif len(occupied) == 3:
            corner_type = "concave"
        else:
            corner_type = "straight"

        horizontal_run = next((run for run in incident_runs if run.orientation == "x"), None)
        vertical_run = next((run for run in incident_runs if run.orientation == "y"), None)
        join_x = vertex[0]
        join_y = vertex[1]
        if vertical_run is not None:
            join_x = run_reference_lines[id(vertical_run)]
        if horizontal_run is not None:
            join_y = run_reference_lines[id(horizontal_run)]
        return {
            "vertex_x": round(vertex[0], 6),
            "vertex_y": round(vertex[1], 6),
            "join_x": round(join_x, 6),
            "join_y": round(join_y, 6),
            "corner_type": corner_type,
        }

    def _run_start_vertex(self, run) -> tuple[float, float]:
        if run.orientation == "x":
            return round(run.start, 6), round(run.line, 6)
        return round(run.line, 6), round(run.start, 6)

    def _run_end_vertex(self, run) -> tuple[float, float]:
        if run.orientation == "x":
            return round(run.end, 6), round(run.line, 6)
        return round(run.line, 6), round(run.end, 6)

    def _run_post_positions(self, run, *, start_corner: dict[str, float | str], end_corner: dict[str, float | str]) -> list[tuple[float, float]]:
        if run.orientation == "x":
            axis_positions = [float(start_corner["join_x"])]
            axis_end = float(end_corner["join_x"])
            line_value = float(start_corner["join_y"])
        else:
            axis_positions = [float(start_corner["join_y"])]
            axis_end = float(end_corner["join_y"])
            line_value = float(start_corner["join_x"])

        cursor = axis_positions[0] + self.POST_SPACING_M
        while cursor < axis_end - 1e-6:
            axis_positions.append(round(cursor, 6))
            cursor += self.POST_SPACING_M
        axis_positions.append(axis_end)

        positions: list[tuple[float, float]] = []
        for axis in axis_positions:
            if run.orientation == "x":
                x = round(axis, 6)
                y = line_value
            else:
                y = round(axis, 6)
                x = line_value
            positions.append((x, y))
        return positions

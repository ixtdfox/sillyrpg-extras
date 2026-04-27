from __future__ import annotations

from ..builders.wall_utils import split_interval
from ..common.utils import BORDER_TILE_SIZE_M
from ..domain.borders import BorderSegment
from ..domain.walls import WallRun
from .wall_planner import WallPlanner


class BorderPlanner:
    """Plans interstory and roof border segments from the real outer contour."""

    def __init__(self):
        self.wall_planner = WallPlanner()

    def plan_floor_band_segments(
        self,
        runs: list[WallRun],
        footprint_tiles: set[tuple[int, int]],
        *,
        wall_thickness: float,
        depth: float,
        height: float,
        story_index: int,
        base_z: float,
    ) -> list[BorderSegment]:
        return self._plan_segments(
            runs,
            footprint_tiles,
            border_type="floor_band",
            wall_thickness=wall_thickness,
            depth=depth,
            height=height,
            story_index=story_index,
            base_z=base_z,
        )

    def plan_roof_border_segments(
        self,
        runs: list[WallRun],
        footprint_tiles: set[tuple[int, int]],
        *,
        wall_thickness: float,
        depth: float,
        height: float,
        story_index: int,
        base_z: float,
    ) -> list[BorderSegment]:
        return self._plan_segments(
            runs,
            footprint_tiles,
            border_type="roof_border",
            wall_thickness=wall_thickness,
            depth=depth,
            height=height,
            story_index=story_index,
            base_z=base_z,
        )

    def plan_terrace_border_segments(
        self,
        runs: list[WallRun],
        footprint_tiles: set[tuple[int, int]],
        *,
        wall_thickness: float,
        depth: float,
        height: float,
        story_index: int,
        base_z: float,
    ) -> list[BorderSegment]:
        return self._plan_segments(
            runs,
            footprint_tiles,
            border_type="terrace_border",
            wall_thickness=wall_thickness,
            depth=depth,
            height=height,
            story_index=story_index,
            base_z=base_z,
        )

    def _plan_segments(
        self,
        runs: list[WallRun],
        footprint_tiles: set[tuple[int, int]],
        *,
        border_type: str,
        wall_thickness: float,
        depth: float,
        height: float,
        story_index: int,
        base_z: float,
    ) -> list[BorderSegment]:
        segments: list[BorderSegment] = []
        for run_index, run in enumerate(runs, start=1):
            run_cap_start, run_cap_end, run_trim_start, run_trim_end = self._border_corner_adjustments(
                run,
                footprint_tiles,
                wall_thickness=wall_thickness,
                depth=depth,
            )
            tile_spans = split_interval(run.start, run.end, BORDER_TILE_SIZE_M)
            last_tile_index = len(tile_spans) - 1
            for tile_index, (tile_start, tile_end) in enumerate(tile_spans, start=0):
                segments.append(
                    BorderSegment(
                        border_type=border_type,
                        orientation=run.orientation,
                        side=run.side,
                        start=tile_start,
                        end=tile_end,
                        line=run.line,
                        depth=depth,
                        height=height,
                        base_z=base_z,
                        wall_thickness=wall_thickness,
                        story_index=story_index,
                        boundary_run_id=f"{border_type}:{story_index}:{run_index}:{tile_index + 1}",
                        cap_start=run_cap_start if tile_index == 0 else 0.0,
                        cap_end=run_cap_end if tile_index == last_tile_index else 0.0,
                        trim_start=run_trim_start if tile_index == 0 else 0.0,
                        trim_end=run_trim_end if tile_index == last_tile_index else 0.0,
                    )
                )
        return segments

    def _border_corner_adjustments(
        self,
        run: WallRun,
        footprint_tiles: set[tuple[int, int]],
        *,
        wall_thickness: float,
        depth: float,
    ) -> tuple[float, float, float, float]:
        cap_start, cap_end, trim_start, trim_end = self.wall_planner._outer_corner_adjustments(
            run,
            footprint_tiles,
            depth,
        )
        convex_join_extension = self._convex_corner_extension(
            run,
            wall_thickness=wall_thickness,
            depth=depth,
        )

        for at_start in (True, False):
            if self._corner_kind(run, footprint_tiles, at_start=at_start) != "convex":
                continue

            if at_start:
                cap_start = convex_join_extension
                trim_start = 0.0
            else:
                cap_end = convex_join_extension
                trim_end = 0.0

        return cap_start, cap_end, trim_start, trim_end

    def _convex_corner_extension(
        self,
        run: WallRun,
        *,
        wall_thickness: float,
        depth: float,
    ) -> float:
        if run.orientation == self.wall_planner.placement_policy.carrying_orientation:
            return depth
        return 0.0

    def _corner_kind(
        self,
        run: WallRun,
        tiles: set[tuple[int, int]],
        *,
        at_start: bool,
    ) -> str | None:
        vertex_x = int(round(run.start if at_start else run.end)) if run.orientation == "x" else int(round(run.line))
        vertex_y = int(round(run.line)) if run.orientation == "x" else int(round(run.start if at_start else run.end))
        occupied_count = sum(
            1
            for present in (
                (vertex_x - 1, vertex_y) in tiles,
                (vertex_x, vertex_y) in tiles,
                (vertex_x - 1, vertex_y - 1) in tiles,
                (vertex_x, vertex_y - 1) in tiles,
            )
            if present
        )
        if occupied_count == 1:
            return "convex"
        if occupied_count == 3:
            return "concave"
        return None

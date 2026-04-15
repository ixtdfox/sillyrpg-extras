from __future__ import annotations

from dataclasses import dataclass

from ..builders.wall_utils import split_interval
from ..common.utils import FLOOR_TILE_SIZE_M, quantize_025
from ..domain.rooms import RoomBoundaryRun
from ..domain.walls import WallRun, WallSegment


@dataclass(frozen=True)
class WallPlacementPolicy:
    carrying_orientation: str = "x"


class WallPlanner:
    """Shared planner for turning domain wall runs into wall segments."""

    def __init__(self, placement_policy: WallPlacementPolicy | None = None):
        self.placement_policy = placement_policy or WallPlacementPolicy()

    def plan_outer_segments(
        self,
        runs: list[WallRun],
        footprint_tiles: set[tuple[int, int]],
        *,
        module_width: float,
        height: float,
        thickness: float,
    ) -> list[WallSegment]:
        segments: list[WallSegment] = []
        for run in runs:
            module_starts = split_interval(run.start, run.end, module_width)
            last_index = len(module_starts) - 1
            cap_run_start, cap_run_end, trim_run_start, trim_run_end = self._outer_corner_adjustments(
                run,
                footprint_tiles,
                thickness,
            )
            for index, (seg_start, seg_end) in enumerate(module_starts):
                segments.append(
                    WallSegment(
                        orientation=run.orientation,
                        side=run.side,
                        start=seg_start,
                        end=seg_end,
                        line=run.line,
                        height=height,
                        thickness=thickness,
                        cap_start=cap_run_start if index == 0 else 0.0,
                        cap_end=cap_run_end if index == last_index else 0.0,
                        trim_start=trim_run_start if index == 0 else 0.0,
                        trim_end=trim_run_end if index == last_index else 0.0,
                    )
                )
        return segments

    def _outer_corner_adjustments(
        self,
        run: WallRun,
        tiles: set[tuple[int, int]],
        thickness: float,
    ) -> tuple[float, float, float, float]:
        cap_start = 0.0
        cap_end = 0.0
        trim_start = 0.0
        trim_end = 0.0
        for at_start in (True, False):
            outside = self._outer_corner_outside_directions(run, tiles, at_start=at_start)
            if outside is None:
                continue
            outside_x, outside_y = outside
            if run.orientation == self.placement_policy.carrying_orientation:
                if run.orientation == "x":
                    if at_start and outside_x < 0:
                        cap_start = thickness
                    if not at_start and outside_x > 0:
                        cap_end = thickness
                else:
                    if at_start and outside_y < 0:
                        cap_start = thickness
                    if not at_start and outside_y > 0:
                        cap_end = thickness
                continue

            if run.orientation == "x":
                if at_start and outside_x > 0:
                    trim_start = thickness
                if not at_start and outside_x < 0:
                    trim_end = thickness
            else:
                if at_start and outside_y > 0:
                    trim_start = thickness
                if not at_start and outside_y < 0:
                    trim_end = thickness
        return cap_start, cap_end, trim_start, trim_end

    def _outer_corner_outside_directions(
        self,
        run: WallRun,
        tiles: set[tuple[int, int]],
        *,
        at_start: bool,
    ) -> tuple[int, int] | None:
        vertex_x = int(round(run.start if at_start else run.end)) if run.orientation == "x" else int(round(run.line))
        vertex_y = int(round(run.line)) if run.orientation == "x" else int(round(run.start if at_start else run.end))
        occupied = {
            "nw": (vertex_x - 1, vertex_y) in tiles,
            "ne": (vertex_x, vertex_y) in tiles,
            "sw": (vertex_x - 1, vertex_y - 1) in tiles,
            "se": (vertex_x, vertex_y - 1) in tiles,
        }
        inside_quadrants = [name for name, present in occupied.items() if present]
        if len(inside_quadrants) == 1:
            inside = inside_quadrants[0]
            return {"sw": (1, 1), "se": (-1, 1), "nw": (1, -1), "ne": (-1, -1)}[inside]
        if len(inside_quadrants) == 3:
            for quadrant, present in occupied.items():
                if not present:
                    return {"ne": (1, 1), "nw": (-1, 1), "se": (1, -1), "sw": (-1, -1)}[quadrant]
        return None


class InteriorWallPlanner:
    """Plans interior wall segments from shared room boundaries."""

    def plan_segments(
        self,
        runs: list[RoomBoundaryRun],
        *,
        module_width: float,
        height: float,
        thickness: float,
    ) -> list[WallSegment]:
        segments: list[WallSegment] = []
        trimmed_y_starts = self._collect_trimmed_y_run_starts(runs)
        for run in runs:
            for seg_start, seg_end in split_interval(run.start, run.end, module_width):
                segments.append(
                    WallSegment(
                        orientation=run.orientation,
                        side=run.side,
                        start=seg_start,
                        end=seg_end,
                        line=run.line,
                        height=height,
                        thickness=thickness,
                        trim_start=thickness if run in trimmed_y_starts and abs(seg_start - run.start) < 1e-6 else 0.0,
                        room_a_id=run.room_a_id,
                        room_b_id=run.room_b_id,
                    )
                )
        return segments

    def _collect_trimmed_y_run_starts(self, runs: list[RoomBoundaryRun]) -> set[RoomBoundaryRun]:
        x_start_vertices = {
            (quantize_025(run.start), quantize_025(run.line))
            for run in runs
            if run.orientation == "x" and run.side == "north"
        }
        return {
            run
            for run in runs
            if run.orientation == "y"
            and run.side == "east"
            and (quantize_025(run.line), quantize_025(run.start)) in x_start_vertices
        }

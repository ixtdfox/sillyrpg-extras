from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from .door_planner import DoorPlanner
from .outer_boundary_resolver import OuterBoundaryResolver
from .room_boundary_resolver import RoomBoundaryResolver
from .wall_planner import InteriorWallPlanner, WallPlanner
from .window_planner import WindowPlanner


@dataclass(frozen=True)
class StairValidationResult:
    is_valid: bool
    reason: str = ""


class StairPlacementValidator:
    """Validates that a stair candidate has a clear shaft and a usable upper exit."""

    def __init__(self):
        self.outer_boundary_resolver = OuterBoundaryResolver()
        self.room_boundary_resolver = RoomBoundaryResolver()
        self.wall_planner = WallPlanner()
        self.interior_wall_planner = InteriorWallPlanner()
        self.door_planner = DoorPlanner()
        self.window_planner = WindowPlanner()

    def validate(self, placement, context) -> StairValidationResult:
        story_plan = context.story_plan
        next_story = context.building_plan.stories[placement.to_story]
        shaft_bounds = placement.opening.bounds
        upper_landing_bounds = self._upper_landing_bounds(placement)

        current_wall_segments = list(context.outer_wall_segments) + list(context.interior_wall_segments)
        if self._any_wall_intersects_rect(current_wall_segments, shaft_bounds):
            return StairValidationResult(False, "current_story_wall_intersection")

        current_forbidden_tiles = self._collect_forbidden_tiles_for_context(context)
        if placement.occupied_tiles & current_forbidden_tiles:
            return StairValidationResult(False, "current_story_forbidden_zone")

        next_context = self._build_story_context(context, next_story, reserved_openings=[placement.opening])
        next_wall_segments = list(next_context.outer_wall_segments) + list(next_context.interior_wall_segments)
        if self._any_wall_intersects_rect(next_wall_segments, shaft_bounds):
            return StairValidationResult(False, "shaft_blocked_by_next_story_wall")
        if self._any_wall_intersects_rect(next_wall_segments, upper_landing_bounds):
            return StairValidationResult(False, "upper_landing_blocked")

        next_forbidden_tiles = self._collect_forbidden_tiles_for_context(next_context)
        if self._rect_tiles(upper_landing_bounds, set(next_context.footprint.tiles)) & next_forbidden_tiles:
            return StairValidationResult(False, "upper_landing_forbidden_zone")

        if not self._has_usable_upper_exit(placement, next_context):
            return StairValidationResult(False, "upper_exit_not_walkable")

        return StairValidationResult(True)

    def _build_story_context(self, base_context, story_plan, *, reserved_openings) -> SimpleNamespace:
        footprint = story_plan.footprint
        footprint_tiles = set(footprint.tiles)
        outer_runs = self.outer_boundary_resolver.collect_runs(footprint_tiles)
        outer_segments = self.wall_planner.plan_outer_segments(
            outer_runs,
            footprint_tiles,
            module_width=base_context.settings.walls.wall_module_width,
            height=base_context.settings.walls.wall_height,
            thickness=base_context.settings.walls.wall_thickness,
        )

        room_layout = list(story_plan.room_layout)
        room_boundaries = self.room_boundary_resolver.collect_runs(room_layout) if len(room_layout) > 1 else []
        interior_segments = (
            self.interior_wall_planner.plan_segments(
                room_boundaries,
                module_width=base_context.settings.walls.wall_module_width,
                height=base_context.settings.walls.wall_height,
                thickness=base_context.settings.walls.wall_thickness,
            )
            if room_boundaries
            else []
        )
        story_context = SimpleNamespace(
            footprint=footprint,
            settings=base_context.settings,
            rooms=room_layout,
            room_boundaries=room_boundaries,
            outer_wall_segments=outer_segments,
            interior_wall_segments=interior_segments,
            story_plan=SimpleNamespace(
                story_index=story_plan.story_index,
                floor_openings=list(getattr(story_plan, "floor_openings", [])) + list(reserved_openings),
            ),
            door_placements=[],
            window_placements=[],
        )
        story_context.door_placements = self.door_planner.plan(story_context)
        story_context.window_placements = self.window_planner.plan(story_context)
        return story_context

    def _upper_landing_bounds(self, placement) -> tuple[float, float, float, float]:
        x0 = float(placement.x)
        y0 = float(placement.y)
        x1 = x0 + float(placement.length)
        y1 = y0 + float(placement.width)
        lane = min(float(placement.stair_width), max(0.6, (y1 - y0) * 0.45)) if placement.orientation == "x" else min(float(placement.stair_width), max(0.6, (x1 - x0) * 0.45))
        if placement.orientation == "x":
            return x0, y1 - lane, x0 + float(placement.landing_size), y1
        return x1 - lane, y0, x1, y0 + float(placement.landing_size)

    def _has_usable_upper_exit(self, placement, next_context) -> bool:
        footprint_tiles = set(next_context.footprint.tiles)
        opening_tiles = {
            tile
            for opening in next_context.story_plan.floor_openings
            for tile in opening.tiles
        }
        walkable_tiles = footprint_tiles - opening_tiles
        landing_tiles = self._rect_tiles(self._upper_landing_bounds(placement), footprint_tiles) & placement.occupied_tiles
        if not landing_tiles:
            landing_tiles = set(placement.occupied_tiles)
        exit_tiles = {
            neighbor
            for tile_x, tile_y in landing_tiles
            for neighbor in ((tile_x + 1, tile_y), (tile_x - 1, tile_y), (tile_x, tile_y + 1), (tile_x, tile_y - 1))
            if neighbor in walkable_tiles
        }
        if not exit_tiles:
            return False
        next_forbidden_tiles = self._collect_forbidden_tiles_for_context(next_context)
        usable_exit_tiles = exit_tiles - next_forbidden_tiles
        return bool(usable_exit_tiles)

    def _collect_forbidden_tiles_for_context(self, context) -> set[tuple[int, int]]:
        footprint_tiles = set(context.footprint.tiles)
        forbidden_tiles: set[tuple[int, int]] = set()
        door_clearance = float(context.settings.stairs.door_clearance)
        window_clearance = float(context.settings.stairs.window_clearance)
        for placement in context.door_placements:
            forbidden_tiles |= self._rect_tiles(
                self._opening_forbidden_rect(placement.orientation, placement.slot_start, placement.slot_end, placement.line, door_clearance),
                footprint_tiles,
            )
        for placement in context.window_placements:
            forbidden_tiles |= self._rect_tiles(
                self._opening_forbidden_rect(placement.orientation, placement.start, placement.end, placement.line, window_clearance),
                footprint_tiles,
            )
        return forbidden_tiles

    def _opening_forbidden_rect(self, orientation: str, start: float, end: float, line: float, clearance: float) -> tuple[float, float, float, float]:
        if orientation == "x":
            return start - clearance, line - clearance, end + clearance, line + clearance
        return line - clearance, start - clearance, line + clearance, end + clearance

    def _rect_tiles(self, bounds: tuple[float, float, float, float], footprint_tiles: set[tuple[int, int]]) -> set[tuple[int, int]]:
        min_x, min_y, max_x, max_y = bounds
        result: set[tuple[int, int]] = set()
        for tile_x, tile_y in footprint_tiles:
            center_x = tile_x + 0.5
            center_y = tile_y + 0.5
            if center_x < min_x or center_x > max_x:
                continue
            if center_y < min_y or center_y > max_y:
                continue
            result.add((tile_x, tile_y))
        return result

    def _any_wall_intersects_rect(self, segments, bounds: tuple[float, float, float, float]) -> bool:
        min_x, min_y, max_x, max_y = bounds
        for segment in segments:
            if segment.orientation == "x":
                if not (min_y < segment.line < max_y):
                    continue
                if segment.end <= min_x + 1e-6 or segment.start >= max_x - 1e-6:
                    continue
                return True
            else:
                if not (min_x < segment.line < max_x):
                    continue
                if segment.end <= min_y + 1e-6 or segment.start >= max_y - 1e-6:
                    continue
                return True
        return False

from __future__ import annotations

import bpy

from ..domain.walls import WallRun
from ..factories.border_mesh_factory import BorderMeshFactory
from ..planning.border_planner import BorderPlanner
from ..planning.outer_boundary_resolver import OuterBoundaryResolver
from ..planning.terrace_planner import TerracePlanner
from .base_builder import BaseBuilder


class BorderBuilder(BaseBuilder):
    """Builds interstory floor bands and the roof border from the outer contour."""

    builder_id = "borders"

    def __init__(self):
        self.boundary_resolver = OuterBoundaryResolver()
        self.border_planner = BorderPlanner()
        self.terrace_planner = TerracePlanner()
        self.border_factory = BorderMeshFactory()

    def enabled(self, context) -> bool:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        if not context.footprint or story_plan is None or building_plan is None:
            return False
        has_floor_bands = context.settings.floor_bands.enabled and story_plan.story_index < (building_plan.story_count - 1)
        has_roof_border = context.settings.roof_border.enabled and story_plan.story_index == (building_plan.story_count - 1)
        has_terrace_border = context.settings.roof_border.enabled and self.terrace_planner.has_terrace_area(context)
        return has_floor_bands or has_roof_border or has_terrace_border

    def build(self, context) -> list[bpy.types.Object]:
        story_plan = context.story_plan
        building_plan = context.building_plan
        footprint_tiles = set(context.footprint.tiles)
        runs = self.boundary_resolver.collect_runs(footprint_tiles)
        segments = []
        terrace_runs = self.terrace_planner.plan_boundary_runs(context) if self.terrace_planner.has_terrace_area(context) else []
        add_terrace_border = context.settings.roof_border.enabled and bool(terrace_runs)
        floor_band_runs = self._exclude_runs(runs, terrace_runs) if add_terrace_border else runs

        if context.settings.floor_bands.enabled and story_plan.story_index < (building_plan.story_count - 1):
            segments.extend(
                self.border_planner.plan_floor_band_segments(
                    floor_band_runs,
                    footprint_tiles,
                    wall_thickness=context.settings.walls.wall_thickness,
                    depth=context.settings.floor_bands.depth,
                    height=context.settings.floor_bands.height,
                    story_index=story_plan.story_index,
                    base_z=context.settings.walls.wall_height,
                )
            )

        if context.settings.roof_border.enabled and story_plan.story_index == (building_plan.story_count - 1):
            segments.extend(
                self.border_planner.plan_roof_border_segments(
                    runs,
                    footprint_tiles,
                    wall_thickness=context.settings.walls.wall_thickness,
                    depth=context.settings.roof_border.depth,
                    height=context.settings.roof_border.height,
                    story_index=story_plan.story_index,
                    base_z=context.settings.walls.wall_height,
                )
            )

        if add_terrace_border:
            terrace_tiles = set(self.terrace_planner.plan_tiles(context))
            segments.extend(
                self.border_planner.plan_terrace_border_segments(
                    terrace_runs,
                    terrace_tiles,
                    wall_thickness=context.settings.walls.wall_thickness,
                    depth=context.settings.roof_border.depth,
                    height=context.settings.roof_border.height,
                    story_index=story_plan.story_index,
                    base_z=context.settings.walls.wall_height,
                )
            )

        objects = [
            self.border_factory.create_border_object(context, segment, border_index=index)
            for index, segment in enumerate(segments, start=1)
        ]
        context.border_segments.extend(segments)
        context.border_objects.extend(objects)
        context.created_objects.extend(objects)
        return objects

    def _exclude_runs(self, runs: list[WallRun], excluded_runs: list[WallRun]) -> list[WallRun]:
        excluded_by_key: dict[tuple[str, str, float], list[tuple[float, float]]] = {}
        for run in excluded_runs:
            excluded_by_key.setdefault((run.orientation, run.side, run.line), []).append((run.start, run.end))

        filtered: list[WallRun] = []
        for run in runs:
            intervals = [(run.start, run.end)]
            for exclude_start, exclude_end in sorted(excluded_by_key.get((run.orientation, run.side, run.line), [])):
                next_intervals: list[tuple[float, float]] = []
                for start, end in intervals:
                    if exclude_end <= start or exclude_start >= end:
                        next_intervals.append((start, end))
                        continue
                    if exclude_start > start:
                        next_intervals.append((start, exclude_start))
                    if exclude_end < end:
                        next_intervals.append((exclude_end, end))
                intervals = next_intervals
                if not intervals:
                    break

            filtered.extend(
                WallRun(
                    orientation=run.orientation,
                    side=run.side,
                    line=run.line,
                    start=start,
                    end=end,
                )
                for start, end in intervals
                if end - start > 1e-6
            )
        return filtered

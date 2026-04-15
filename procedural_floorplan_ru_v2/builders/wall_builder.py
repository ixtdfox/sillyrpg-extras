from __future__ import annotations

import bpy

from .. import atlas
from ..factories.wall_mesh_factory import WallMeshFactory
from ..planning.outer_boundary_resolver import OuterBoundaryResolver
from ..planning.wall_planner import WallPlanner
from .base_builder import BaseBuilder


class WallBuilder(BaseBuilder):
    """Builder внешних стен, который только координирует wall pipeline."""

    builder_id = "outer_walls"

    def __init__(self):
        self.boundary_resolver = OuterBoundaryResolver()
        self.wall_planner = WallPlanner()
        self.wall_factory = WallMeshFactory()

    def enabled(self, context) -> bool:
        return bool(context.settings.walls.outer_walls_enabled and context.footprint)

    def build(self, context) -> list[bpy.types.Object]:
        wall_tile_id = atlas.resolve_wall_tile_id(context)
        footprint_tiles = set(context.footprint.tiles)
        runs = self.boundary_resolver.collect_runs(footprint_tiles)
        segments = self.wall_planner.plan_outer_segments(
            runs,
            footprint_tiles,
            module_width=context.settings.walls.wall_module_width,
            height=context.settings.walls.wall_height,
            thickness=context.settings.walls.wall_thickness,
        )
        context.outer_wall_segments = segments

        objects = [
            self.wall_factory.create_wall_object(
                context,
                segment,
                building_part="outer_wall",
                object_prefix="OuterWall",
                wall_tile_id=wall_tile_id,
                wall_index=index,
                module_width=context.settings.walls.wall_module_width,
            )
            for index, segment in enumerate(segments, start=1)
        ]
        context.outer_wall_objects = objects
        context.created_objects.extend(objects)
        return objects

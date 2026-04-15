from __future__ import annotations

import bpy

from .. import atlas
from ..factories.roof_railing_mesh_factory import RoofRailingMeshFactory
from ..planning.roof_railing_planner import RoofRailingPlanner
from ..planning.terrace_planner import TerracePlanner
from .base_builder import BaseBuilder


class TerraceRailingBuilder(BaseBuilder):
    """Builds railing on the truly exposed terrace perimeter only."""

    builder_id = "terrace_railing"

    def __init__(self):
        self.terrace_planner = TerracePlanner()
        self.railing_planner = RoofRailingPlanner()
        self.railing_factory = RoofRailingMeshFactory()

    def enabled(self, context) -> bool:
        return bool(
            context.footprint
            and context.settings.roof_railing.enabled
            and self.terrace_planner.has_terrace_area(context)
        )

    def build(self, context) -> list[bpy.types.Object]:
        terrace_tiles = set(self.terrace_planner.plan_tiles(context))
        upper_tiles = self.terrace_planner.upper_tiles(context)
        runs, posts, rails = self.railing_planner.plan_for_tiles(
            context,
            footprint_tiles=terrace_tiles,
            run_id_prefix="terrace_railing",
            blocked_tiles=upper_tiles,
        )
        railing_tile_id = atlas.resolve_railing_tile_id(context)
        objects: list[bpy.types.Object] = []
        objects.extend(
            self.railing_factory.create_post_object(
                context,
                placement,
                post_index=index,
                railing_tile_id=railing_tile_id,
                surface_type="terrace",
            )
            for index, placement in enumerate(posts, start=1)
        )
        objects.extend(
            self.railing_factory.create_rail_object(
                context,
                segment,
                rail_index=index,
                railing_tile_id=railing_tile_id,
                surface_type="terrace",
            )
            for index, segment in enumerate(rails, start=1)
        )
        context.terrace_railing_runs = runs
        context.terrace_railing_posts = posts
        context.terrace_railing_rails = rails
        context.terrace_railing_objects.extend(objects)
        context.created_objects.extend(objects)
        return objects

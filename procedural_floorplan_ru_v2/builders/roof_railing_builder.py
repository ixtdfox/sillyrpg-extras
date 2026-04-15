from __future__ import annotations

import bpy

from .. import atlas
from ..factories.roof_railing_mesh_factory import RoofRailingMeshFactory
from ..planning.roof_railing_planner import RoofRailingPlanner
from .base_builder import BaseBuilder


class RoofRailingBuilder(BaseBuilder):
    """Builds roof railing only on the top story, following the real roof contour."""

    builder_id = "roof_railing"

    def __init__(self):
        self.railing_planner = RoofRailingPlanner()
        self.railing_factory = RoofRailingMeshFactory()

    def enabled(self, context) -> bool:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        return bool(
            context.footprint
            and context.settings.roof_railing.enabled
            and story_plan is not None
            and building_plan is not None
            and story_plan.story_index == (building_plan.story_count - 1)
        )

    def build(self, context) -> list[bpy.types.Object]:
        runs, posts, rails = self.railing_planner.plan(context)
        railing_tile_id = atlas.resolve_railing_tile_id(context)
        objects: list[bpy.types.Object] = []
        objects.extend(
            self.railing_factory.create_post_object(context, placement, post_index=index, railing_tile_id=railing_tile_id)
            for index, placement in enumerate(posts, start=1)
        )
        objects.extend(
            self.railing_factory.create_rail_object(context, segment, rail_index=index, railing_tile_id=railing_tile_id)
            for index, segment in enumerate(rails, start=1)
        )
        context.roof_railing_runs = runs
        context.roof_railing_posts = posts
        context.roof_railing_rails = rails
        context.roof_railing_objects.extend(objects)
        context.created_objects.extend(objects)
        return objects

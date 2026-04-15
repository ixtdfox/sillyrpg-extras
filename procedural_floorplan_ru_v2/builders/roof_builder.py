from __future__ import annotations

import bpy

from .. import atlas
from ..factories.roof_mesh_factory import RoofMeshFactory
from ..planning.roof_planner import RoofPlanner
from .base_builder import BaseBuilder


class RoofBuilder(BaseBuilder):
    """Builds a flat roof only for the top story."""

    builder_id = "roof"

    def __init__(self):
        self.roof_planner = RoofPlanner()
        self.roof_factory = RoofMeshFactory()

    def enabled(self, context) -> bool:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        return bool(
            context.footprint
            and story_plan is not None
            and building_plan is not None
            and story_plan.story_index == (building_plan.story_count - 1)
        )

    def build(self, context) -> list[bpy.types.Object]:
        roof_tiles = self.roof_planner.plan_tiles(context)
        roof_tile_id = atlas.resolve_roof_tile_id(context)
        obj = self.roof_factory.create_roof_object(context, roof_tiles, roof_tile_id)
        if obj is None:
            return []
        context.created_objects.append(obj)
        return [obj]

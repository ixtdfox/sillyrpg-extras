from __future__ import annotations

import bpy

from ..factories.stair_mesh_factory import StairMeshFactory
from ..planning.stair_planner import StairPlanner
from .base_builder import BaseBuilder


class StairBuilder(BaseBuilder):
    """Plans and builds inter-story stairs after walls, doors, and windows are known."""

    builder_id = "stairs"

    def __init__(self):
        self.stair_planner = StairPlanner()
        self.stair_factory = StairMeshFactory()

    def enabled(self, context) -> bool:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        return bool(
            context.footprint
            and context.settings.stairs.enabled
            and context.settings.stairs.mode.value == "internal"
            and story_plan is not None
            and building_plan is not None
            and story_plan.story_index < (building_plan.story_count - 1)
        )

    def build(self, context) -> list[bpy.types.Object]:
        placement = self.stair_planner.plan(context)
        if placement is None:
            return []

        context.stair_placements.append(placement)
        next_story = context.building_plan.stories[placement.to_story]
        if placement.opening not in next_story.floor_openings:
            next_story.floor_openings.append(placement.opening)

        objects = self.stair_factory.create_stair_objects(
            context,
            placement,
            stair_index=len(context.stair_placements),
        )
        context.stair_objects.extend(objects)
        context.created_objects.extend(objects)
        return objects

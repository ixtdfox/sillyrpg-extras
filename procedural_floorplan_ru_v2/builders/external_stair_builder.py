from __future__ import annotations

from ..factories.external_stair_mesh_factory import ExternalStairMeshFactory
from ..planning.external_stair_planner import ExternalStairPlanner


class ExternalStairBuilder:
    """Building-level builder for one shared external fire stair and evacuation doors on each story."""

    builder_id = "external_stairs"

    def __init__(self):
        self.planner = ExternalStairPlanner()
        self.mesh_factory = ExternalStairMeshFactory()

    def build_building(self, building_context) -> list:
        placements = self.planner.plan_building(building_context)
        if not placements:
            return []

        created_objects = []
        for story_context, placement in zip(building_context.stories, placements):
            stair_objects = self.mesh_factory.create_objects(
                story_context,
                placement,
                stair_index=placement.story_index + 1,
            )
            if placement.switchback_placement is not None:
                story_context.stair_placements.append(placement)
            story_context.stair_objects.extend(stair_objects)
            story_context.created_objects.extend(stair_objects)
            created_objects.extend(stair_objects)

        building_context.created_objects = [
            obj
            for story_context in building_context.stories
            for obj in story_context.created_objects
        ]
        return created_objects

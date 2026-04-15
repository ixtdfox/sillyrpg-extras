from __future__ import annotations

import bpy

from .. import atlas
from ..factories.room_metadata_factory import RoomMetadataFactory
from ..factories.wall_mesh_factory import WallMeshFactory
from ..planning.room_boundary_resolver import RoomBoundaryResolver
from ..planning.room_planner import RoomPlanner
from ..planning.wall_planner import InteriorWallPlanner
from .base_builder import BaseBuilder


class RoomSubdivisionBuilder(BaseBuilder):
    """Builder комнат как orchestration-layer между planners и factories."""

    builder_id = "room_subdivision"

    def __init__(self):
        self.room_planner = RoomPlanner()
        self.boundary_resolver = RoomBoundaryResolver()
        self.interior_wall_planner = InteriorWallPlanner()
        self.wall_factory = WallMeshFactory()
        self.room_metadata_factory = RoomMetadataFactory()

    def enabled(self, context) -> bool:
        return bool(context.footprint)

    def build(self, context) -> list[bpy.types.Object]:
        story_plan = getattr(context, "story_plan", None)
        rooms = list(story_plan.room_layout) if story_plan and story_plan.room_layout else self.room_planner.plan_rooms(
            set(context.footprint.tiles),
            target_rooms=context.settings.shape.target_room_count,
            min_room_side_m=context.settings.shape.min_room_side_m,
            rng=context.rng,
        )
        context.rooms = rooms

        objects: list[bpy.types.Object] = [
            self.room_metadata_factory.create_metadata_object(context, room)
            for room in rooms
        ]

        if len(rooms) > 1:
            wall_tile_id = atlas.resolve_wall_tile_id(context)
            room_boundaries = self.boundary_resolver.collect_runs(rooms)
            interior_segments = self.interior_wall_planner.plan_segments(
                room_boundaries,
                module_width=context.settings.walls.wall_module_width,
                height=context.settings.walls.wall_height,
                thickness=context.settings.walls.wall_thickness,
            )
            context.room_boundaries = room_boundaries
            context.interior_wall_segments = interior_segments

            objects.extend(
                self.wall_factory.create_wall_object(
                    context,
                    segment,
                    building_part="inner_wall",
                    object_prefix="InnerWall",
                    wall_tile_id=wall_tile_id,
                    wall_index=index,
                    module_width=context.settings.walls.wall_module_width,
                )
                for index, segment in enumerate(interior_segments, start=1)
            )
            context.interior_wall_objects = objects[len(rooms):]

        context.created_objects.extend(objects)
        return objects

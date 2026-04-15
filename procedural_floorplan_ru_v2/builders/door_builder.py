from __future__ import annotations

import bpy

from .. import atlas
from ..domain.walls import WallSegment
from ..factories.door_mesh_factory import DoorMeshFactory
from ..factories.wall_mesh_factory import WallMeshFactory
from ..planning.door_planner import DoorPlanner
from .base_builder import BaseBuilder


class DoorBuilder(BaseBuilder):
    """Отдельный builder дверей, который использует уже рассчитанные стены и комнаты."""

    builder_id = "doors"

    def __init__(self):
        self.door_planner = DoorPlanner()
        self.door_factory = DoorMeshFactory()
        self.wall_factory = WallMeshFactory()

    def enabled(self, context) -> bool:
        return bool(context.settings.doors.enabled and context.outer_wall_segments)

    def build(self, context) -> list[bpy.types.Object]:
        placements = self.door_planner.plan(context)
        context.door_placements = placements
        self._apply_openings(context, placements)
        objects = [
            self.door_factory.create_door_object(context, placement, door_index=index)
            for index, placement in enumerate(placements, start=1)
        ]
        context.created_objects.extend(objects)
        return objects

    def _apply_openings(self, context, placements) -> None:
        wall_tile_id = atlas.resolve_wall_tile_id(context)
        outer_doors = [placement for placement in placements if placement.door_type in {"entry", "external_stair"}]
        inner_doors = [placement for placement in placements if placement.door_type == "interior"]

        outer_segments, outer_objects = self._rebuild_wall_set(
            context,
            context.outer_wall_segments,
            context.outer_wall_objects,
            outer_doors,
            building_part="outer_wall",
            object_prefix="OuterWall",
            wall_tile_id=wall_tile_id,
        )
        inner_segments, inner_objects = self._rebuild_wall_set(
            context,
            context.interior_wall_segments,
            context.interior_wall_objects,
            inner_doors,
            building_part="inner_wall",
            object_prefix="InnerWall",
            wall_tile_id=wall_tile_id,
        )
        context.outer_wall_segments = outer_segments
        context.outer_wall_objects = outer_objects
        context.interior_wall_segments = inner_segments
        context.interior_wall_objects = inner_objects

    def _rebuild_wall_set(
        self,
        context,
        segments,
        objects,
        placements,
        *,
        building_part: str,
        object_prefix: str,
        wall_tile_id: str,
    ) -> tuple[list[WallSegment], list[bpy.types.Object]]:
        new_segments: list[WallSegment] = []
        new_objects: list[bpy.types.Object] = []
        next_index = 1

        for segment, obj in zip(segments, objects):
            matching = [placement for placement in placements if self._placement_matches_segment(placement, segment)]
            if not matching:
                new_segments.append(segment)
                new_objects.append(obj)
                continue

            bpy.data.objects.remove(obj, do_unlink=True)
            context.created_objects = [created for created in context.created_objects if created != obj]

            for replacement in self._split_segment_for_openings(segment, matching):
                new_segments.append(replacement)
                replacement_obj = self.wall_factory.create_wall_object(
                    context,
                    replacement,
                    building_part=building_part,
                    object_prefix=object_prefix,
                    wall_tile_id=wall_tile_id,
                    wall_index=next_index,
                    module_width=context.settings.walls.wall_module_width,
                )
                new_objects.append(replacement_obj)
                context.created_objects.append(replacement_obj)
                next_index += 1

        return new_segments, new_objects

    def _placement_matches_segment(self, placement, segment: WallSegment) -> bool:
        if placement.orientation != segment.orientation:
            return False
        if placement.host_wall_side != segment.side:
            return False
        if abs(placement.line - segment.line) > 1e-6:
            return False
        if placement.door_type == "interior" and (
            placement.room_a_id != segment.room_a_id or placement.room_b_id != segment.room_b_id
        ):
            return False
        return placement.slot_end > segment.start + 1e-6 and placement.slot_start < segment.end - 1e-6

    def _split_segment_for_openings(self, segment: WallSegment, placements) -> list[WallSegment]:
        placements = sorted(placements, key=lambda item: item.slot_start)
        result: list[WallSegment] = []
        cursor = segment.start
        leading = True

        for placement in placements:
            opening_start = max(segment.start, placement.slot_start)
            opening_end = min(segment.end, placement.slot_end)

            if opening_start > cursor + 1e-6:
                result.append(
                    WallSegment(
                        orientation=segment.orientation,
                        side=segment.side,
                        start=cursor,
                        end=opening_start,
                        line=segment.line,
                        height=segment.height,
                        thickness=segment.thickness,
                        cap_start=segment.cap_start if leading else 0.0,
                        cap_end=0.0,
                        trim_start=segment.trim_start if leading else 0.0,
                        trim_end=0.0,
                        base_z=segment.base_z,
                        room_a_id=segment.room_a_id,
                        room_b_id=segment.room_b_id,
                    )
                )
                leading = False

            header_height = max(0.0, segment.height - placement.height)
            if header_height > 1e-6:
                result.append(
                    WallSegment(
                        orientation=segment.orientation,
                        side=segment.side,
                        start=opening_start,
                        end=opening_end,
                        line=segment.line,
                        height=header_height,
                        thickness=segment.thickness,
                        base_z=placement.height,
                        room_a_id=segment.room_a_id,
                        room_b_id=segment.room_b_id,
                    )
                )
            cursor = opening_end

        if cursor < segment.end - 1e-6:
            result.append(
                WallSegment(
                    orientation=segment.orientation,
                    side=segment.side,
                    start=cursor,
                    end=segment.end,
                    line=segment.line,
                    height=segment.height,
                    thickness=segment.thickness,
                    cap_start=0.0,
                    cap_end=segment.cap_end,
                    trim_start=0.0,
                    trim_end=segment.trim_end,
                    base_z=segment.base_z,
                    room_a_id=segment.room_a_id,
                    room_b_id=segment.room_b_id,
                )
            )

        return [item for item in result if item.length > 1e-6 and item.height > 1e-6]

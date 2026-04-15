from __future__ import annotations

import bpy

from .. import atlas
from ..domain.walls import WallSegment
from ..factories.wall_mesh_factory import WallMeshFactory
from ..factories.window_mesh_factory import WindowMeshFactory
from ..planning.window_planner import WindowPlanner
from .base_builder import BaseBuilder


class WindowBuilder(BaseBuilder):
    """Отдельный builder окон, который работает только с внешними стенами."""

    builder_id = "windows"

    def __init__(self):
        self.window_planner = WindowPlanner()
        self.wall_factory = WallMeshFactory()
        self.window_factory = WindowMeshFactory()

    def enabled(self, context) -> bool:
        return bool(context.settings.windows.enabled and context.outer_wall_segments)

    def build(self, context) -> list[bpy.types.Object]:
        placements = self.window_planner.plan(context)
        context.window_placements = placements
        self._apply_openings(context, placements)
        objects: list[bpy.types.Object] = []
        for index, placement in enumerate(placements, start=1):
            objects.extend(self.window_factory.create_window_objects(context, placement, window_index=index))
        context.created_objects.extend(objects)
        return objects

    def _apply_openings(self, context, placements) -> None:
        wall_tile_id = atlas.resolve_wall_tile_id(context)
        new_segments: list[WallSegment] = []
        new_objects: list[bpy.types.Object] = []
        next_index = 1

        for segment, obj in zip(context.outer_wall_segments, context.outer_wall_objects):
            matching = [placement for placement in placements if self._placement_matches_segment(placement, segment)]
            if not matching:
                new_segments.append(segment)
                new_objects.append(obj)
                continue

            bpy.data.objects.remove(obj, do_unlink=True)
            context.created_objects = [created for created in context.created_objects if created != obj]

            for replacement in self._split_segment_for_windows(segment, matching):
                new_segments.append(replacement)
                replacement_obj = self.wall_factory.create_wall_object(
                    context,
                    replacement,
                    building_part="outer_wall",
                    object_prefix="OuterWall",
                    wall_tile_id=wall_tile_id,
                    wall_index=next_index,
                    module_width=context.settings.walls.wall_module_width,
                )
                new_objects.append(replacement_obj)
                context.created_objects.append(replacement_obj)
                next_index += 1

        context.outer_wall_segments = new_segments
        context.outer_wall_objects = new_objects

    def _placement_matches_segment(self, placement, segment: WallSegment) -> bool:
        if segment.base_z > placement.sill_height + 1e-6:
            return False
        if placement.orientation != segment.orientation:
            return False
        if placement.host_wall_side != segment.side:
            return False
        if abs(placement.line - segment.line) > 1e-6:
            return False
        return placement.end > segment.start + 1e-6 and placement.start < segment.end - 1e-6

    def _split_segment_for_windows(self, segment: WallSegment, placements) -> list[WallSegment]:
        placements = sorted(placements, key=lambda item: item.start)
        result: list[WallSegment] = []
        cursor = segment.start
        leading = True
        for placement in placements:
            opening_start = max(segment.start, placement.start)
            opening_end = min(segment.end, placement.end)
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

            if placement.sill_height > segment.base_z + 1e-6:
                result.append(
                    WallSegment(
                        orientation=segment.orientation,
                        side=segment.side,
                        start=opening_start,
                        end=opening_end,
                        line=segment.line,
                        height=placement.sill_height - segment.base_z,
                        thickness=segment.thickness,
                        base_z=segment.base_z,
                        room_a_id=segment.room_a_id,
                        room_b_id=segment.room_b_id,
                    )
                )

            header_base = placement.sill_height + placement.height
            header_height = (segment.base_z + segment.height) - header_base
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
                        base_z=header_base,
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

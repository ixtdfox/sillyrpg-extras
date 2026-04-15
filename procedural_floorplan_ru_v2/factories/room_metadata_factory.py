from __future__ import annotations

import bpy

from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object
from ..domain.rooms import Room


class RoomMetadataFactory:
    """Creates hidden Blender empties carrying room metadata."""

    def create_metadata_object(self, context, room: Room) -> bpy.types.Object:
        min_x, min_y, max_x, max_y = room.bbox
        center_x = round((min_x + max_x) * 0.5, 6)
        center_y = round((min_y + max_y) * 0.5, 6)

        obj = bpy.data.objects.new(f"RoomMeta_{room.id:03d}", None)
        obj.location = (center_x, center_y, 0.0)
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.35
        obj.hide_viewport = True
        obj.hide_render = True
        tag_generated_object(obj, "room_metadata", tile_size=FLOOR_TILE_SIZE_M)
        obj["room_id"] = int(room.id)
        obj["room_area"] = float(room.area)
        obj["room_bbox"] = list(room.bbox)
        obj["room_tile_count"] = int(len(room.tiles))
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

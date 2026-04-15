from __future__ import annotations

import bpy

from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object
from ..domain.walls import WallSegment
from ..builders.wall_utils import build_box_mesh, segment_geometry


class WallMeshFactory:
    """Converts domain wall segments into Blender mesh objects."""

    def create_wall_object(
        self,
        context,
        segment: WallSegment,
        *,
        building_part: str,
        object_prefix: str,
        wall_tile_id: str,
        wall_index: int,
        module_width: float,
    ) -> bpy.types.Object:
        size_x, size_y, size_z, center = segment_geometry(segment)
        mesh = bpy.data.meshes.new(f"{object_prefix}Mesh_{segment.orientation.upper()}_{wall_index:04d}")
        build_box_mesh(mesh, size_x=size_x, size_y=size_y, size_z=size_z)

        obj = bpy.data.objects.new(f"{object_prefix}_{segment.orientation.upper()}_{wall_index:04d}", mesh)
        obj.location = center
        tag_generated_object(
            obj,
            building_part,
            tile_x=int(segment.line if segment.orientation == "y" else segment.start),
            tile_y=int(segment.start if segment.orientation == "y" else segment.line),
            tile_size=FLOOR_TILE_SIZE_M,
        )
        obj["wall_orientation"] = segment.orientation
        obj["edge_side"] = segment.side
        obj["wall_height"] = float(segment.height)
        obj["wall_width"] = float(segment.length)
        obj["wall_module_width"] = float(module_width)
        obj["wall_thickness"] = float(segment.thickness)
        if segment.room_a_id is not None:
            obj["room_a_id"] = int(segment.room_a_id)
        if segment.room_b_id is not None:
            obj["room_b_id"] = int(segment.room_b_id)
        obj["atlas_category"] = "walls"
        if wall_tile_id:
            obj["atlas_tile_id"] = wall_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

from __future__ import annotations

import bpy

from ..builders.wall_utils import build_box_mesh
from ..common.utils import FLOOR_THICKNESS_M, FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object


class FloorMeshFactory:
    """Creates Blender floor tile objects from grid coordinates."""

    def create_tile(self, context, tile_x: int, tile_y: int, floor_tile_id: str) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"FloorTileMesh_{tile_x}_{tile_y}")
        x0 = float(tile_x) * FLOOR_TILE_SIZE_M
        y0 = float(tile_y) * FLOOR_TILE_SIZE_M
        slab_thickness = float(FLOOR_THICKNESS_M)
        build_box_mesh(
            mesh,
            size_x=FLOOR_TILE_SIZE_M,
            size_y=FLOOR_TILE_SIZE_M,
            size_z=slab_thickness,
        )

        obj = bpy.data.objects.new(f"FloorTile_{tile_x}_{tile_y}", mesh)
        obj.location = (
            x0 + (FLOOR_TILE_SIZE_M * 0.5),
            y0 + (FLOOR_TILE_SIZE_M * 0.5),
            -(slab_thickness * 0.5),
        )
        tag_generated_object(obj, "floor", tile_x=tile_x, tile_y=tile_y, tile_size=FLOOR_TILE_SIZE_M)
        obj["atlas_category"] = "floors"
        if floor_tile_id:
            obj["atlas_tile_id"] = floor_tile_id
        obj["footprint_shape"] = context.footprint.shape_key
        obj["floor_thickness"] = slab_thickness
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

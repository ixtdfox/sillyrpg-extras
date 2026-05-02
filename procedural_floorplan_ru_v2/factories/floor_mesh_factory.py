from __future__ import annotations

import bpy

from ..common.tile_surface_mesh import build_tile_surface_mesh
from ..common.utils import FLOOR_THICKNESS_M, FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object


class FloorMeshFactory:
    """Creates Blender floor tile objects from grid coordinates."""

    def create_floor_object(self, context, floor_tiles: list[tuple[int, int]], floor_tile_id: str) -> bpy.types.Object | None:
        if not floor_tiles:
            return None

        mesh = bpy.data.meshes.new("FloorMesh")
        slab_thickness = float(FLOOR_THICKNESS_M)
        before_faces = len(floor_tiles) * 6
        build_tile_surface_mesh(
            mesh,
            floor_tiles,
            tile_size=FLOOR_TILE_SIZE_M,
            top_z=0.0,
            bottom_z=-slab_thickness,
            include_perimeter_sides=True,
            include_bottom=False,
        )

        obj = bpy.data.objects.new("Floor", mesh)
        tag_generated_object(obj, "floor", tile_size=FLOOR_TILE_SIZE_M)
        obj["atlas_category"] = "floors"
        if floor_tile_id:
            obj["atlas_tile_id"] = floor_tile_id
        obj["footprint_shape"] = context.footprint.shape_key
        obj["floor_thickness"] = slab_thickness
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        print(
            "[MeshCleanup]",
            f"floor faces before={before_faces}",
            f"after={len(mesh.polygons)}",
            f"internalRemoved={before_faces - len(mesh.polygons)}",
        )
        return obj

    def create_tile(self, context, tile_x: int, tile_y: int, floor_tile_id: str) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"FloorTileMesh_{tile_x}_{tile_y}")
        x0 = float(tile_x) * FLOOR_TILE_SIZE_M
        y0 = float(tile_y) * FLOOR_TILE_SIZE_M
        slab_thickness = float(FLOOR_THICKNESS_M)
        build_tile_surface_mesh(
            mesh,
            [(0, 0)],
            tile_size=FLOOR_TILE_SIZE_M,
            top_z=slab_thickness * 0.5,
            bottom_z=-(slab_thickness * 0.5),
            include_perimeter_sides=True,
            include_bottom=False,
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

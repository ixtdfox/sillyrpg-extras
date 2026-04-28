from __future__ import annotations

import bpy

from ..builders.wall_utils import BOX_FACES_OUTWARD
from ..common.utils import FLOOR_THICKNESS_M, FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object


class RoofMeshFactory:
    """Builds one flat roof mesh from the exact set of roof tiles."""

    def create_roof_object(self, context, roof_tiles: list[tuple[int, int]], roof_tile_id: str) -> bpy.types.Object | None:
        return self.create_surface_object(
            context,
            roof_tiles,
            roof_tile_id,
            surface_type="roof",
            object_name="Roof_001",
        )

    def create_terrace_object(self, context, terrace_tiles: list[tuple[int, int]], terrace_tile_id: str) -> bpy.types.Object | None:
        return self.create_surface_object(
            context,
            terrace_tiles,
            terrace_tile_id,
            surface_type="terrace",
            object_name="Terrace_001",
        )

    def create_surface_object(
        self,
        context,
        surface_tiles: list[tuple[int, int]],
        surface_tile_id: str,
        *,
        surface_type: str,
        object_name: str,
    ) -> bpy.types.Object | None:
        if not surface_tiles:
            return None

        mesh = bpy.data.meshes.new(f"{object_name}Mesh")
        verts: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []
        thickness = float(FLOOR_THICKNESS_M)
        base_z = float(context.settings.walls.wall_height)

        for tile_x, tile_y in surface_tiles:
            x0 = float(tile_x) * FLOOR_TILE_SIZE_M
            y0 = float(tile_y) * FLOOR_TILE_SIZE_M
            x1 = x0 + FLOOR_TILE_SIZE_M
            y1 = y0 + FLOOR_TILE_SIZE_M
            z0 = base_z
            z1 = base_z + thickness
            start = len(verts)
            verts.extend(
                [
                    (x0, y0, z0),
                    (x1, y0, z0),
                    (x1, y1, z0),
                    (x0, y1, z0),
                    (x0, y0, z1),
                    (x1, y0, z1),
                    (x1, y1, z1),
                    (x0, y1, z1),
                ]
            )
            faces.extend(
                [
                    tuple(start + vertex_index for vertex_index in face)
                    for face in BOX_FACES_OUTWARD
                ]
            )

        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(object_name, mesh)
        tag_generated_object(obj, surface_type, tile_size=FLOOR_TILE_SIZE_M)
        obj["surface_type"] = surface_type
        obj["roof_type"] = "flat"
        obj["roof_thickness"] = thickness
        obj["is_terrace"] = surface_type == "terrace"
        obj["atlas_category"] = "roofs"
        if surface_tile_id:
            obj["atlas_tile_id"] = surface_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

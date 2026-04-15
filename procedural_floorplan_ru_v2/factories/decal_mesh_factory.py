from __future__ import annotations

import bpy
from mathutils import Vector

from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object


class DecalMeshFactory:
    """Creates facade decal planes as standalone mesh objects."""

    def create_decal_object(
        self,
        context,
        *,
        target_collection: bpy.types.Collection,
        wall_obj: bpy.types.Object,
        entry,
        material: bpy.types.Material,
        tangent_world: Vector,
        up_world: Vector,
        normal_world: Vector,
        tangent_offset: float,
        anchor_top_z: float,
        decal_index: int,
        outward_offset: float = 0.02,
    ) -> bpy.types.Object:
        width = max(0.05, float(entry.tile_width_m))
        height = max(0.05, float(entry.tile_height_m))
        wall_half_thickness = min(float(wall_obj.dimensions.x), float(wall_obj.dimensions.y)) * 0.5
        center_world = (
            wall_obj.location
            + (tangent_world * tangent_offset)
            + (normal_world * (wall_half_thickness + outward_offset))
        )
        center_world.z = float(anchor_top_z) - (height * 0.5)

        story_z_offset = float(getattr(getattr(context, "story_plan", None), "z_offset", 0.0))
        local_center = center_world.copy()
        local_center.z -= story_z_offset

        mesh = bpy.data.meshes.new(f"DecalMesh_{decal_index:04d}")
        half_width = width * 0.5
        half_height = height * 0.5
        verts = [
            ((tangent_world * -half_width) + (up_world * -half_height))[:],
            ((tangent_world * half_width) + (up_world * -half_height))[:],
            ((tangent_world * half_width) + (up_world * half_height))[:],
            ((tangent_world * -half_width) + (up_world * half_height))[:],
        ]
        mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
        mesh.update()

        self._assign_uvs(mesh, entry)

        obj = bpy.data.objects.new(f"Decal_{entry.kind}_{decal_index:04d}", mesh)
        obj.location = local_center
        tile_x = wall_obj.get("tile_x")
        tile_y = wall_obj.get("tile_y")
        tag_generated_object(
            obj,
            "decal",
            tile_x=int(tile_x) if tile_x is not None else None,
            tile_y=int(tile_y) if tile_y is not None else None,
            tile_size=FLOOR_TILE_SIZE_M,
        )
        obj["is_decal"] = True
        obj["decal_target"] = str(wall_obj.name)
        obj["decal_kind"] = str(entry.kind)
        obj["atlas_category"] = "decals"
        obj["decal_id"] = str(entry.id)
        obj["decal_width"] = width
        obj["decal_height"] = height
        obj["decal_outward_offset"] = outward_offset
        obj["decal_tangent_offset"] = tangent_offset
        obj["decal_anchor_top_z"] = float(anchor_top_z)
        obj["decal_normal_world"] = tuple(float(v) for v in normal_world)
        obj["decal_tangent_world"] = tuple(float(v) for v in tangent_world)
        if "story_index" in wall_obj:
            obj["story_index"] = int(wall_obj["story_index"])

        mesh.materials.append(material)
        apply_story_object_context(obj, context)
        link_object(target_collection, obj)
        return obj

    def _assign_uvs(self, mesh: bpy.types.Mesh, entry) -> None:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        min_u = entry.x / entry.atlas_width
        max_u = (entry.x + entry.w) / entry.atlas_width
        min_v = 1.0 - ((entry.y + entry.h) / entry.atlas_height)
        max_v = 1.0 - (entry.y / entry.atlas_height)
        uv_coords = ((min_u, min_v), (max_u, min_v), (max_u, max_v), (min_u, max_v))
        for loop_index, uv in zip((0, 1, 2, 3), uv_coords):
            uv_layer.data[loop_index].uv = uv

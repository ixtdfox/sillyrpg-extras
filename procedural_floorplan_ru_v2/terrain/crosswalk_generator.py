from __future__ import annotations

import bpy

from .mask_schema import TerrainMask, TerrainZone
from .terrain_mesh_factory import create_zone_rectangles


def create_crosswalk_objects(
    *,
    collection: bpy.types.Collection,
    mask: TerrainMask,
    material: bpy.types.Material,
    road_height_offset: float,
) -> list[bpy.types.Object]:
    objects = create_zone_rectangles(
        scene=None,
        collection=collection,
        mask=mask,
        zone=TerrainZone.CROSSWALK_HINT,
        material=material,
        object_prefix="Crosswalk",
        top_z=road_height_offset + 0.005,
        thickness=0.005,
    )
    for obj in objects:
        obj["building_part"] = "crosswalk"
    return objects

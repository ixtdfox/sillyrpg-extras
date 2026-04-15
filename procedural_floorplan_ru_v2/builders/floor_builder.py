from __future__ import annotations

import bpy

from .. import atlas
from ..factories.floor_mesh_factory import FloorMeshFactory
from .base_builder import BaseBuilder


class FloorBuilder(BaseBuilder):
    builder_id = "floor"

    def __init__(self):
        self.floor_factory = FloorMeshFactory()

    def build(self, context) -> list[bpy.types.Object]:
        floor_tile_id = atlas.resolve_floor_tile_id(context)
        story_plan = getattr(context, "story_plan", None)
        opening_tiles = {
            tile
            for opening in (story_plan.floor_openings if story_plan is not None else [])
            for tile in opening.tiles
        }
        objects = [
            self.floor_factory.create_tile(context, tile_x, tile_y, floor_tile_id)
            for tile_x, tile_y in sorted(context.footprint.tiles)
            if (tile_x, tile_y) not in opening_tiles
        ]
        context.created_objects.extend(objects)
        return objects

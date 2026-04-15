from __future__ import annotations

import bpy

from .. import atlas
from ..factories.roof_mesh_factory import RoofMeshFactory
from ..planning.terrace_planner import TerracePlanner
from .base_builder import BaseBuilder


class TerraceBuilder(BaseBuilder):
    """Builds exposed terrace slabs for story tiles left uncovered by the story above."""

    builder_id = "terrace"

    def __init__(self):
        self.terrace_planner = TerracePlanner()
        self.surface_factory = RoofMeshFactory()

    def enabled(self, context) -> bool:
        return bool(context.footprint and self.terrace_planner.has_terrace_area(context))

    def build(self, context) -> list[bpy.types.Object]:
        terrace_tiles = self.terrace_planner.plan_tiles(context)
        terrace_tile_id = atlas.resolve_roof_tile_id(context)
        obj = self.surface_factory.create_terrace_object(context, terrace_tiles, terrace_tile_id)
        context.terrace_tiles = terrace_tiles
        if obj is None:
            return []
        context.terrace_objects.append(obj)
        context.created_objects.append(obj)
        return [obj]

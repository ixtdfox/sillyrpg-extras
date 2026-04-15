from __future__ import annotations

import random

import bpy

from . import atlas
from .builders import BaseBuilder, BorderBuilder, DecalBuilder, DoorBuilder, FloorBuilder, RoofBuilder, RoofRailingBuilder, RoomSubdivisionBuilder, StairBuilder, TerraceBuilder, TerraceRailingBuilder, WallBuilder, WindowBuilder
from .config import GenerationSettings, settings_from_props
from .planning.shape_footprint_generator import ShapeFootprintGenerator
from .state import GenerationContext
from .common.utils import ensure_collection


class BuildingManager:
    def __init__(self, settings: GenerationSettings):
        self.settings = settings
        self.builders: list[BaseBuilder] = []
        self.footprint_generator = ShapeFootprintGenerator()

    def register_builder(self, builder: BaseBuilder) -> None:
        self.builders.append(builder)

    def register_default_builders(self) -> None:
        self.register_builder(FloorBuilder())
        self.register_builder(WallBuilder())
        self.register_builder(RoomSubdivisionBuilder())
        self.register_builder(DoorBuilder())
        self.register_builder(WindowBuilder())
        self.register_builder(StairBuilder())
        self.register_builder(TerraceBuilder())
        self.register_builder(BorderBuilder())
        self.register_builder(RoofBuilder())
        self.register_builder(RoofRailingBuilder())
        self.register_builder(TerraceRailingBuilder())
        self.register_builder(DecalBuilder())

    def build(self, scene: bpy.types.Scene):
        context = self._prepare_context(scene)
        context = self.build_context(context)
        if context.settings.atlas.enabled:
            atlas.apply_atlas_to_collection(context)
        return context

    def build_context(self, context: GenerationContext):
        if not self.builders:
            self.register_default_builders()
        for builder in self.builders:
            if builder.enabled(context):
                builder.build(context)
        return context

    def _prepare_context(self, scene: bpy.types.Scene) -> GenerationContext:
        collection = ensure_collection(
            scene,
            self.settings.general.collection_name,
            delete_old=self.settings.general.delete_old,
        )
        footprint = self.footprint_generator.build(self.settings.shape, seed=self.settings.general.seed)
        manifest = atlas.manifest_from_settings(self.settings, persist_default_manifest=True)
        atlas_data = atlas.build_atlas_runtime(self.settings, manifest)
        return GenerationContext(
            scene=scene,
            settings=self.settings,
            collection=collection,
            footprint=footprint,
            atlas_manifest=manifest,
            atlas_data=atlas_data,
            rng=random.Random(self.settings.general.seed),
        )


__all__ = ("BuildingManager", "GenerationContext", "GenerationSettings", "settings_from_props")

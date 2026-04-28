from __future__ import annotations

import random

import bpy

from . import atlas
from .building_manager import BuildingManager
from .builders.external_stair_builder import ExternalStairBuilder
from .common.utils import (
    FLOOR_THICKNESS_M,
    create_story_inside_volume,
    ensure_child_collection,
    ensure_collection,
    print_game_visibility_summary,
    quantize_025,
)
from .config import GenerationSettings
from .domain.building import BuildingPlan, StoryLayoutMode, StoryPlan, VerticalProfileMode
from .planning.external_stair_planner import ExternalStairPlanner
from .planning.room_planner import RoomPlanner
from .planning.shape_footprint_generator import ShapeFootprintGenerator
from .planning.vertical_profile_planner import VerticalProfilePlanner
from .state import BuildingContext, GenerationContext


class BuildingStoriesManager:
    """Building-level orchestration for multi-story generation."""

    def __init__(self, settings: GenerationSettings):
        self.settings = settings
        self.story_pipeline = BuildingManager(settings)
        self.story_pipeline.register_default_builders()
        self.external_stair_builder = ExternalStairBuilder()
        self.external_stair_planner = ExternalStairPlanner()
        self.footprint_generator = ShapeFootprintGenerator()
        self.vertical_profile_planner = VerticalProfilePlanner()
        self.room_planner = RoomPlanner()

    def build(self, scene: bpy.types.Scene) -> BuildingContext:
        collection = ensure_collection(
            scene,
            self.settings.general.collection_name,
            delete_old=self.settings.general.delete_old,
        )
        footprint = self.footprint_generator.build(self.settings.shape, seed=self.settings.general.seed)
        manifest = atlas.manifest_from_settings(self.settings, persist_default_manifest=True)
        atlas_data = atlas.build_atlas_runtime(self.settings, manifest)
        building_plan = self._build_plan(footprint)

        building_context = BuildingContext(
            scene=scene,
            settings=self.settings,
            collection=collection,
            atlas_manifest=manifest,
            atlas_data=atlas_data,
            building_plan=building_plan,
        )

        for story_plan in building_plan.stories:
            story_collection = ensure_child_collection(collection, f"Story_{story_plan.story_index}")
            story_context = GenerationContext(
                scene=scene,
                settings=self.settings,
                collection=story_collection,
                footprint=story_plan.footprint,
                atlas_manifest=manifest,
                atlas_data=atlas_data,
                rng=random.Random(story_plan.seed),
                building_plan=building_plan,
                story_plan=story_plan,
            )
            self.story_pipeline.build_context(story_context)
            inside_volume = create_story_inside_volume(story_context)
            if inside_volume is not None:
                story_context.created_objects.append(inside_volume)
            building_context.stories.append(story_context)
            building_context.created_objects.extend(story_context.created_objects)

        if self.settings.stairs.enabled and self.settings.stairs.mode.value == "external":
            self.external_stair_builder.build_building(building_context)

        if self.settings.atlas.enabled:
            atlas.apply_atlas_to_collection(building_context)
        print_game_visibility_summary(collection)
        return building_context

    def _build_plan(self, footprint) -> BuildingPlan:
        # Story stacking must preserve the exact floor slab thickness, otherwise
        # 0.10 m gets snapped away and the upper slab z-fights with lower walls.
        story_height = float(self.settings.walls.wall_height) + float(FLOOR_THICKNESS_M)
        layout_mode = StoryLayoutMode(self.settings.stories.layout_mode)
        vertical_profile_mode = VerticalProfileMode(self.settings.stories.vertical_profile_mode)
        story_count = self.settings.stories.story_count
        story_footprints = self.vertical_profile_planner.plan_story_footprints(
            footprint,
            story_count=story_count,
            shape_key=self.settings.shape.shape_mode,
            vertical_profile_mode=vertical_profile_mode.value,
            profile_strength=float(self.settings.stories.profile_strength),
            min_room_side_m=float(self.settings.shape.min_room_side_m),
            stair_width=float(self.settings.stairs.width),
            rng=random.Random(self.settings.general.seed),
        )
        all_story_footprints_same = all(story_footprints[0].tiles == item.tiles for item in story_footprints[1:]) if story_footprints else True
        shared_layout = self._plan_room_layout(self.settings.general.seed, story_footprints[0]) if layout_mode == StoryLayoutMode.SAME and all_story_footprints_same else None

        stories: list[StoryPlan] = []
        for story_index in range(story_count):
            story_footprint = story_footprints[story_index]
            if story_index < (story_count - 1):
                upper_tiles = set(story_footprints[story_index + 1].tiles)
                terrace_tiles = frozenset(sorted(set(story_footprint.tiles) - upper_tiles))
            else:
                terrace_tiles = frozenset()
            story_seed = self._story_seed(story_index, layout_mode)
            room_seed = self.settings.general.seed if layout_mode == StoryLayoutMode.SAME else story_seed
            room_layout = list(shared_layout) if shared_layout is not None else self._plan_room_layout(room_seed, story_footprint)
            stories.append(
                StoryPlan(
                    story_index=story_index,
                    z_offset=story_index * story_height,
                    seed=story_seed,
                    footprint=story_footprint,
                    terrace_tiles=terrace_tiles,
                    room_layout=room_layout,
                )
            )

        building_plan = BuildingPlan(
            footprint=footprint,
            story_count=story_count,
            layout_mode=layout_mode,
            vertical_profile_mode=vertical_profile_mode,
            story_height=story_height,
            stories=stories,
        )
        if self.settings.stairs.enabled and self.settings.stairs.mode.value == "external":
            building_plan.external_stair_stack = self.external_stair_planner.plan_stack(building_plan, self.settings)
        return building_plan

    def _plan_room_layout(self, seed: int, footprint) -> list:
        return self.room_planner.plan_rooms(
            set(footprint.tiles),
            target_rooms=self.settings.shape.target_room_count,
            min_room_side_m=self.settings.shape.min_room_side_m,
            rng=random.Random(seed),
        )

    def _story_seed(self, story_index: int, layout_mode: StoryLayoutMode) -> int:
        base_seed = self.settings.general.seed
        if layout_mode == StoryLayoutMode.SAME:
            return base_seed
        return base_seed + (story_index * 9973)


__all__ = ("BuildingStoriesManager",)

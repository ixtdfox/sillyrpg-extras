from __future__ import annotations

import random
from dataclasses import dataclass, field

import bpy

from .common.shape_generator import Footprint
from .config import GenerationSettings
from .domain.building import BuildingPlan, StoryPlan
from .domain.borders import BorderSegment
from .domain.doors import DoorPlacement
from .domain.railings import RailingPostPlacement, RailingRailSegment, RoofRailingRun
from .domain.rooms import Room, RoomBoundaryRun
from .domain.stairs import ExternalStairPlacement, StairPlacement
from .domain.walls import WallSegment
from .domain.windows import WindowPlacement


@dataclass
class GenerationContext:
    scene: bpy.types.Scene
    settings: GenerationSettings
    collection: bpy.types.Collection
    footprint: Footprint | None
    atlas_manifest: dict | None
    atlas_data: dict
    rng: random.Random | None
    building_plan: BuildingPlan | None = None
    story_plan: StoryPlan | None = None
    created_objects: list[bpy.types.Object] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    room_boundaries: list[RoomBoundaryRun] = field(default_factory=list)
    outer_wall_segments: list[WallSegment] = field(default_factory=list)
    interior_wall_segments: list[WallSegment] = field(default_factory=list)
    outer_wall_objects: list[bpy.types.Object] = field(default_factory=list)
    interior_wall_objects: list[bpy.types.Object] = field(default_factory=list)
    door_placements: list[DoorPlacement] = field(default_factory=list)
    window_placements: list[WindowPlacement] = field(default_factory=list)
    stair_placements: list[StairPlacement | ExternalStairPlacement] = field(default_factory=list)
    terrace_tiles: list[tuple[int, int]] = field(default_factory=list)
    roof_railing_runs: list[RoofRailingRun] = field(default_factory=list)
    roof_railing_posts: list[RailingPostPlacement] = field(default_factory=list)
    roof_railing_rails: list[RailingRailSegment] = field(default_factory=list)
    terrace_railing_runs: list[RoofRailingRun] = field(default_factory=list)
    terrace_railing_posts: list[RailingPostPlacement] = field(default_factory=list)
    terrace_railing_rails: list[RailingRailSegment] = field(default_factory=list)
    border_segments: list[BorderSegment] = field(default_factory=list)
    stair_objects: list[bpy.types.Object] = field(default_factory=list)
    terrace_objects: list[bpy.types.Object] = field(default_factory=list)
    roof_railing_objects: list[bpy.types.Object] = field(default_factory=list)
    terrace_railing_objects: list[bpy.types.Object] = field(default_factory=list)
    border_objects: list[bpy.types.Object] = field(default_factory=list)
    decal_objects: list[bpy.types.Object] = field(default_factory=list)
    decal_collection: bpy.types.Collection | None = None


@dataclass
class BuildingContext:
    scene: bpy.types.Scene
    settings: GenerationSettings
    collection: bpy.types.Collection
    atlas_manifest: dict | None
    atlas_data: dict
    building_plan: BuildingPlan
    stories: list[GenerationContext] = field(default_factory=list)
    created_objects: list[bpy.types.Object] = field(default_factory=list)

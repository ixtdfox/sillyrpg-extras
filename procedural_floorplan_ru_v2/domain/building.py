from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..common.shape_generator import Footprint
from .rooms import Room
from .stairs import ExternalStairStackPlan, StairOpeningPlan


class StoryLayoutMode(str, Enum):
    SAME = "same"
    RANDOM = "random"


class VerticalProfileMode(str, Enum):
    STRICT = "strict"
    SETBACK = "setback"
    OFFSET_STACK = "offset_stack"
    PINWHEEL = "pinwheel"
    MIXED = "mixed"


@dataclass
class StoryPlan:
    story_index: int
    z_offset: float
    seed: int
    footprint: Footprint
    terrace_tiles: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    room_layout: list[Room] = field(default_factory=list)
    floor_openings: list[StairOpeningPlan] = field(default_factory=list)


@dataclass
class BuildingPlan:
    footprint: Footprint
    story_count: int
    layout_mode: StoryLayoutMode
    vertical_profile_mode: VerticalProfileMode
    story_height: float
    stories: list[StoryPlan] = field(default_factory=list)
    external_stair_stack: ExternalStairStackPlan | None = None

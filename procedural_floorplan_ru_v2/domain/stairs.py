from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .doors import DoorPlacement


ShapeTile = tuple[int, int]


class StairMode(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass(frozen=True)
class StairOpeningPlan:
    from_story: int
    to_story: int
    tiles: frozenset[ShapeTile]
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class StairPlacement:
    from_story: int
    to_story: int
    room_id: int
    orientation: str
    x: float
    y: float
    width: float
    length: float
    stair_width: float
    landing_size: float
    mid_landing_size: float
    riser_height: float
    tread_depth: float
    riser_count: int
    lower_riser_count: int
    upper_riser_count: int
    travel_run: float
    occupied_tiles: frozenset[ShapeTile]
    clearance_tiles: frozenset[ShapeTile]
    opening: StairOpeningPlan
    room_score: float
    candidate_score: float
    top_elevation: float | None = None
    stair_kind: str = "internal"

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return float(self.x), float(self.y), float(self.x) + self.length, float(self.y) + self.width


@dataclass(frozen=True)
class ExternalStairFacadePlan:
    orientation: str
    side: str
    line: float
    start: float
    end: float
    landing_start: float
    landing_end: float
    landing_depth: float
    module_length: float
    module_width: float
    wall_clearance: float


@dataclass(frozen=True)
class ExternalStairStoryAccessPlan:
    story_index: int
    door_type: str
    slot_start: float
    slot_end: float
    center: float
    has_upward_flight: bool
    anchor_side: str | None


@dataclass(frozen=True)
class ExternalStairStackPlan:
    facade: ExternalStairFacadePlan
    stack_start: float
    stack_end: float
    flight_length: float
    door_landing_length: float
    forbidden_start: float
    forbidden_end: float
    story_accesses: tuple[ExternalStairStoryAccessPlan, ...]


@dataclass(frozen=True)
class ExternalStairPlacement:
    story_index: int
    has_upward_flight: bool
    facade: ExternalStairFacadePlan
    door: DoorPlacement
    door_landing_bounds: tuple[float, float, float, float]
    door_access_bounds: tuple[float, float, float, float]
    flight_bounds: tuple[float, float, float, float]
    switchback_placement: StairPlacement | None
    anchor_side: str | None = None

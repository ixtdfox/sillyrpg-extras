from __future__ import annotations

from dataclasses import dataclass

from .placement_validator import Rect


@dataclass(frozen=True)
class BuildingCandidate:
    building_index: int
    source_parcel_id: int
    seed: int
    shape_mode: str
    story_count: int
    profile_mode: str
    profile_strength: float
    target_room_count: int
    house_scale: float
    min_room_side_m: float
    collection_name: str
    estimated_width_tiles: int
    estimated_depth_tiles: int
    estimated_width_m: float
    estimated_depth_m: float


@dataclass(frozen=True)
class BuildingReservation:
    candidate: BuildingCandidate
    parcel_id: int
    rect: Rect
    center_x: float
    center_y: float
    rotation_z: float
    relocated: bool

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerrainZone(str, Enum):
    EMPTY = "empty"
    BUILDING = "building"
    ROAD = "road"
    SIDEWALK = "sidewalk"
    GRASS = "grass"
    CROSSWALK_HINT = "crosswalk_hint"
    WATER = "water"
    PLAZA = "plaza"


ZONE_COLOR_TABLE = {
    TerrainZone.EMPTY: (0, 0, 0),
    TerrainZone.BUILDING: (255, 0, 0),
    TerrainZone.ROAD: (64, 64, 64),
    TerrainZone.SIDEWALK: (176, 176, 176),
    TerrainZone.GRASS: (0, 255, 0),
    TerrainZone.CROSSWALK_HINT: (255, 255, 255),
    TerrainZone.WATER: (0, 0, 255),
    TerrainZone.PLAZA: (255, 255, 0),
}


def classify_pixel(r: int, g: int, b: int, tolerance: int = 24) -> TerrainZone:
    best_zone = TerrainZone.EMPTY
    best_distance = None
    for zone, color in ZONE_COLOR_TABLE.items():
        distance = max(abs(int(r) - color[0]), abs(int(g) - color[1]), abs(int(b) - color[2]))
        if best_distance is None or distance < best_distance:
            best_zone = zone
            best_distance = distance
    if best_distance is None or best_distance > int(tolerance):
        return TerrainZone.EMPTY
    return best_zone


@dataclass(frozen=True)
class TerrainMask:
    width: int
    height: int
    pixel_size_m: float
    zones: list[list[TerrainZone]]
    offset_x: float = 0.0
    offset_y: float = 0.0

    def world_x(self, px: float) -> float:
        return self.offset_x + (float(px) + 0.5) * self.pixel_size_m

    def world_y(self, py: float) -> float:
        return self.offset_y + (self.height - float(py) - 0.5) * self.pixel_size_m

    def cell_center_world(self, px: int, py: int) -> tuple[float, float]:
        return self.world_x(px), self.world_y(py)

    def rect_world_bounds(self, min_x: int, min_y: int, width: int, height: int) -> tuple[float, float, float, float]:
        world_min_x = self.offset_x + min_x * self.pixel_size_m
        world_max_x = self.offset_x + (min_x + width) * self.pixel_size_m
        world_max_y = self.offset_y + (self.height - min_y) * self.pixel_size_m
        world_min_y = self.offset_y + (self.height - (min_y + height)) * self.pixel_size_m
        return world_min_x, world_min_y, world_max_x, world_max_y

    def zone_at(self, px: int, py: int) -> TerrainZone:
        if px < 0 or py < 0 or px >= self.width or py >= self.height:
            return TerrainZone.EMPTY
        return self.zones[py][px]


def load_mask(path: str, downsample: int = 1):
    from .mask_loader import load_mask_image

    return load_mask_image(path, downsample=downsample)

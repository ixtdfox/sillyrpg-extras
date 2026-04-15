from __future__ import annotations

from dataclasses import dataclass

from ..common.utils import FLOOR_TILE_SIZE_M


ShapeTile = tuple[int, int]


@dataclass(frozen=True)
class Room:
    id: int
    tiles: frozenset[ShapeTile]

    @property
    def area(self) -> float:
        return float(len(self.tiles)) * FLOOR_TILE_SIZE_M * FLOOR_TILE_SIZE_M

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        xs = [x for x, _ in self.tiles]
        ys = [y for _, y in self.tiles]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    @property
    def width(self) -> int:
        min_x, _, max_x, _ = self.bbox
        return max_x - min_x

    @property
    def height(self) -> int:
        _, min_y, _, max_y = self.bbox
        return max_y - min_y


@dataclass(frozen=True)
class RoomBoundaryRun:
    orientation: str
    side: str
    line: float
    room_a_id: int
    room_b_id: int
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start

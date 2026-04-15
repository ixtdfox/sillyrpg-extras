from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RailingPostPlacement:
    x: float
    y: float
    run_id: str | None
    is_corner: bool = False
    corner_type: str | None = None


@dataclass(frozen=True)
class RailingRailSegment:
    run_id: str
    orientation: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    level_index: int


@dataclass(frozen=True)
class RoofRailingRun:
    run_id: str
    orientation: str
    side: str
    line: float
    start: float
    end: float
    inset: float
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    start_corner_type: str
    end_corner_type: str
    post_positions: tuple[tuple[float, float], ...]

    @property
    def length(self) -> float:
        if self.orientation == "x":
            return abs(self.end_x - self.start_x)
        return abs(self.end_y - self.start_y)

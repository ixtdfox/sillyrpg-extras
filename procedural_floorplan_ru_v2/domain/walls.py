from __future__ import annotations

from dataclasses import dataclass

from ..common.utils import quantize_025


@dataclass(frozen=True)
class BoundaryEdge:
    orientation: str
    side: str
    line: float
    start: float
    end: float


@dataclass(frozen=True)
class WallRun:
    orientation: str
    side: str
    line: float
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class WallSegment:
    orientation: str
    side: str
    start: float
    end: float
    line: float
    height: float
    thickness: float
    cap_start: float = 0.0
    cap_end: float = 0.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    base_z: float = 0.0
    room_a_id: int | None = None
    room_b_id: int | None = None

    @property
    def length(self) -> float:
        return quantize_025(
            (self.end - self.start)
            + self.cap_start
            + self.cap_end
            - self.trim_start
            - self.trim_end
        )

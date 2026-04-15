from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowPlacement:
    orientation: str
    line: float
    start: float
    end: float
    center: float
    width: float
    height: float
    sill_height: float
    host_wall_side: str

    @property
    def length(self) -> float:
        return self.end - self.start

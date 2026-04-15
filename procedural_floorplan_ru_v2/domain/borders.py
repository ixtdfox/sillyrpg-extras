from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BorderSegment:
    border_type: str
    orientation: str
    side: str
    start: float
    end: float
    line: float
    depth: float
    height: float
    base_z: float
    story_index: int | None = None
    boundary_run_id: str = ""
    cap_start: float = 0.0
    cap_end: float = 0.0
    trim_start: float = 0.0
    trim_end: float = 0.0

    @property
    def length(self) -> float:
        return round(
            (self.end - self.start)
            + self.cap_start
            + self.cap_end
            - self.trim_start
            - self.trim_end
            ,
            6,
        )

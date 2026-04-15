from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoorPlacement:
    door_type: str
    orientation: str
    line: float
    start: float
    end: float
    center: float
    width: float
    height: float
    thickness: float
    host_wall_side: str
    slot_start: float
    slot_end: float
    room_a_id: int | None = None
    room_b_id: int | None = None

    @property
    def length(self) -> float:
        return self.end - self.start

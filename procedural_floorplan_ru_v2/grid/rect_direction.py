from __future__ import annotations

from enum import Enum


class RectDirection(Enum):
    EAST = (1, 0)
    WEST = (-1, 0)
    NORTH = (0, 1)
    SOUTH = (0, -1)

    @property
    def dx(self) -> int:
        return int(self.value[0])

    @property
    def dy(self) -> int:
        return int(self.value[1])

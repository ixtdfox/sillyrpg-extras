from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class RectCell:
    x: int
    y: int

    def to_game_dict(self) -> dict[str, int]:
        return {"x": int(self.x), "z": int(self.y)}

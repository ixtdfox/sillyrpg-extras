from __future__ import annotations

from dataclasses import dataclass

from .rect_cell import RectCell


@dataclass(frozen=True, order=True)
class RectEdge:
    a: RectCell
    b: RectCell

    def __post_init__(self) -> None:
        dx = abs(self.a.x - self.b.x)
        dy = abs(self.a.y - self.b.y)
        if dx + dy != 1:
            raise ValueError("RectEdge must connect 4-way neighboring cells")

    def canonical(self) -> "RectEdge":
        return self if self.a <= self.b else RectEdge(self.b, self.a)

    def key(self) -> str:
        edge = self.canonical()
        return f"{edge.a.x}:{edge.a.y}->{edge.b.x}:{edge.b.y}"

    def to_game_dict(self, reason: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {"a": self.a.to_game_dict(), "b": self.b.to_game_dict()}
        if reason:
            payload["reason"] = reason
        return payload

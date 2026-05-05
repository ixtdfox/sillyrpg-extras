from __future__ import annotations

import math
from dataclasses import dataclass

from .rect_cell import RectCell
from .rect_edge import RectEdge


@dataclass(frozen=True)
class RectLayout:
    tile_size_m: float = 1.0
    origin_x: float = 0.0
    origin_y: float = 0.0

    def cell_center(self, cell: RectCell, story_z: float = 0.0) -> tuple[float, float, float]:
        return (
            self.origin_x + (cell.x + 0.5) * self.tile_size_m,
            self.origin_y + (cell.y + 0.5) * self.tile_size_m,
            story_z,
        )

    def cell_bounds(self, cell: RectCell) -> tuple[float, float, float, float]:
        return (
            self.origin_x + cell.x * self.tile_size_m,
            self.origin_y + cell.y * self.tile_size_m,
            self.origin_x + (cell.x + 1) * self.tile_size_m,
            self.origin_y + (cell.y + 1) * self.tile_size_m,
        )

    def edge_center(self, edge: RectEdge, story_z: float = 0.0) -> tuple[float, float, float]:
        a = edge.a
        b = edge.b
        if a.x != b.x:
            x = self.origin_x + max(a.x, b.x) * self.tile_size_m
            y = self.origin_y + (a.y + 0.5) * self.tile_size_m
        else:
            x = self.origin_x + (a.x + 0.5) * self.tile_size_m
            y = self.origin_y + max(a.y, b.y) * self.tile_size_m
        return x, y, story_z

    def edge_segment(self, edge: RectEdge, story_z: float = 0.0) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        a = edge.a
        b = edge.b
        if a.x != b.x:
            x = self.origin_x + max(a.x, b.x) * self.tile_size_m
            y0 = self.origin_y + a.y * self.tile_size_m
            y1 = self.origin_y + (a.y + 1) * self.tile_size_m
            return (x, y0, story_z), (x, y1, story_z)
        y = self.origin_y + max(a.y, b.y) * self.tile_size_m
        x0 = self.origin_x + a.x * self.tile_size_m
        x1 = self.origin_x + (a.x + 1) * self.tile_size_m
        return (x0, y, story_z), (x1, y, story_z)

    def snap_point_to_cell(self, x: float, y: float) -> RectCell:
        return RectCell(
            math.floor((float(x) - self.origin_x) / self.tile_size_m),
            math.floor((float(y) - self.origin_y) / self.tile_size_m),
        )

    def enumerate_cells(self, min_x: int, max_x: int, min_y: int, max_y: int) -> list[RectCell]:
        return [RectCell(x, y) for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1)]

from __future__ import annotations

from dataclasses import dataclass

from .rect_cell import RectCell
from .rect_edge import RectEdge


@dataclass(frozen=True)
class GameGridCoordinateMapper:
    """Maps logical Blender XY tile indices to exported Babylon XZ grid indices.

    Blender exports with X right, Y forward, Z up. Babylon loads glTF into its X right,
    Y up, Z forward world where Blender +Y lands on Babylon -Z.

    Logical tile bounds in Blender for (x, y) are:
      X: [x, x+1), Y: [y, y+1)

    The matching Babylon world tile must therefore be:
      X: [x, x+1), Z: [-(y+1), -y)

    Which gives integer cell mapping:
      game_x = tile_x
      game_z = -(tile_y + 1)
    """

    def cell_to_game(self, cell: RectCell) -> RectCell:
        return RectCell(int(cell.x), -int(cell.y) - 1)

    def edge_to_game(self, edge: RectEdge) -> RectEdge:
        return RectEdge(self.cell_to_game(edge.a), self.cell_to_game(edge.b)).canonical()

    def cell_to_game_dict(self, cell: RectCell) -> dict[str, int]:
        mapped = self.cell_to_game(cell)
        return {"x": mapped.x, "z": mapped.y}

    def edge_to_game_dict(self, edge: RectEdge, reason: str | None = None) -> dict[str, object]:
        mapped = self.edge_to_game(edge)
        payload: dict[str, object] = {
            "a": {"x": mapped.a.x, "z": mapped.a.y},
            "b": {"x": mapped.b.x, "z": mapped.b.y},
        }
        if reason:
            payload["reason"] = reason
        return payload

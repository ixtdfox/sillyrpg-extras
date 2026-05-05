from __future__ import annotations

from ..game_grid import GAME_GRID_ORIGIN_X_M, GAME_GRID_ORIGIN_Z_M, WORLD_TILE_SIZE_M
from .rect_layout import RectLayout

GRID_NAVIGATION_CONTRACT = "sillyrpg.grid_navigation.v3"


def create_game_rect_layout() -> RectLayout:
    return RectLayout(
        tile_size_m=WORLD_TILE_SIZE_M,
        origin_x=GAME_GRID_ORIGIN_X_M,
        origin_y=GAME_GRID_ORIGIN_Z_M,
    )

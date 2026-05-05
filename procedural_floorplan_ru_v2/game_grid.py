from __future__ import annotations

import math

WORLD_TILE_SIZE_M = 1.0
GAME_TILE_SIZE_M = WORLD_TILE_SIZE_M
GAME_GRID_ORIGIN_X_M = 0.0
GAME_GRID_ORIGIN_Z_M = 0.0


def snap_value_to_game_grid(value: float, tile_size: float = WORLD_TILE_SIZE_M) -> float:
    if tile_size <= 0.0:
        raise ValueError("tile_size must be positive")
    return round(float(value) / tile_size) * tile_size


def snap_world_point_to_nearest_rect_cell_center(
    x: float,
    y: float,
    *,
    tile_size: float = WORLD_TILE_SIZE_M,
    origin_x: float = GAME_GRID_ORIGIN_X_M,
    origin_y: float = GAME_GRID_ORIGIN_Z_M,
) -> tuple[float, float]:
    if tile_size <= 0.0:
        raise ValueError("tile_size must be positive")
    cell_x = math.floor((float(x) - origin_x) / tile_size)
    cell_y = math.floor((float(y) - origin_y) / tile_size)
    return (
        origin_x + (cell_x + 0.5) * tile_size,
        origin_y + (cell_y + 0.5) * tile_size,
    )

from __future__ import annotations

import math

from ...game_grid import GAME_TILE_SIZE_M, snap_value_to_game_grid


def tiles_to_meters(tiles: int | float) -> float:
    return float(tiles) * float(GAME_TILE_SIZE_M)


def meters_to_tiles(value_m: float) -> float:
    return float(value_m) / float(GAME_TILE_SIZE_M)


def meters_to_tile_int(value_m: float) -> int:
    return int(round(meters_to_tiles(value_m)))


def snap_meters_to_tile(value_m: float) -> float:
    return snap_value_to_game_grid(float(value_m), tile_size=GAME_TILE_SIZE_M)


def snap_rect_to_tile_bounds(x: float, y: float, width: float, depth: float) -> tuple[float, float, float, float]:
    x0 = snap_meters_to_tile(x)
    y0 = snap_meters_to_tile(y)
    x1 = snap_meters_to_tile(float(x) + float(width))
    y1 = snap_meters_to_tile(float(y) + float(depth))
    return x0, y0, x1 - x0, y1 - y0


def tile_rect_to_world(x_tiles: int, y_tiles: int, width_tiles: int, depth_tiles: int) -> tuple[float, float, float, float]:
    return (
        tiles_to_meters(x_tiles),
        tiles_to_meters(y_tiles),
        tiles_to_meters(width_tiles),
        tiles_to_meters(depth_tiles),
    )


def align_tile_origin(total_tiles: int) -> int:
    return -int(math.floor(float(total_tiles) * 0.5))

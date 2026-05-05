from __future__ import annotations


# Shared export contract with sillyrpg:
# 1 Blender meter = 1 Babylon world unit = 1 building tile.
GAME_TILE_SIZE_M = 1.0


def snap_value_to_game_grid(value: float, tile_size: float = GAME_TILE_SIZE_M) -> float:
    """Snaps a world-space coordinate to the nearest game tile grid line."""
    if tile_size <= 0.0:
        raise ValueError("tile_size must be positive")
    return round(value / tile_size) * tile_size

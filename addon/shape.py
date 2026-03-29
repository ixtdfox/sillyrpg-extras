"""Shape and volume generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Volume:
    name: str
    x: float
    y: float
    z: float
    width: float
    depth: float
    height: float


@dataclass
class ShapeResult:
    volumes: List[Volume]


def _snap_to_tile(value: float, tile: float) -> float:
    steps = max(1, round(value / tile))
    return steps * tile


def _overlap(a: Volume, b: Volume) -> bool:
    ax2, ay2 = a.x + a.width, a.y + a.depth
    bx2, by2 = b.x + b.width, b.y + b.depth
    return not (ax2 <= b.x or bx2 <= a.x or ay2 <= b.y or by2 <= a.y)


def generate_shape(params: dict, fallback_reasons: List[str]) -> ShapeResult:
    tile = params["tile_size"]
    floors = params["floors"]
    floor_h = params["floor_height"]

    main_w = _snap_to_tile(params["width"], tile)
    main_d = _snap_to_tile(params["depth"], tile)
    main_h = floors * floor_h

    main = Volume("main", 0.0, 0.0, 0.0, main_w, main_d, main_h)

    entry_w = _snap_to_tile(max(tile, main_w * 0.33), tile)
    entry_d = _snap_to_tile(tile, tile)
    entrance = Volume(
        "entrance",
        (main_w - entry_w) * 0.5,
        -entry_d + 0.02,
        0.0,
        entry_w,
        entry_d,
        floor_h,
    )

    side_w = _snap_to_tile(tile, tile)
    side_d = _snap_to_tile(max(tile * 2.0, main_d * 0.5), tile)
    side = Volume(
        "service",
        main_w - side_w + 0.02,
        (main_d - side_d) * 0.5,
        0.0,
        side_w,
        side_d,
        floor_h,
    )

    upper_w = _snap_to_tile(max(tile * 2.0, main_w * 0.66), tile)
    upper_d = _snap_to_tile(max(tile * 2.0, main_d * 0.66), tile)
    upper = Volume(
        "upper",
        (main_w - upper_w) * 0.5,
        (main_d - upper_d) * 0.5,
        floor_h,
        upper_w,
        upper_d,
        max(0.1, (floors - 1) * floor_h),
    )

    volumes = [main, entrance, side]
    if floors > 1:
        volumes.append(upper)

    # Validate connectivity with fallback to compact composition.
    disconnected = any(not _overlap(main, v) for v in volumes[1:])
    if disconnected:
        fallback_reasons.append("shape_connectivity")
        volumes = [main]

    return ShapeResult(volumes=volumes)

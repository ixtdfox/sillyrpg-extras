from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .building_style import FloorLevel


@dataclass(frozen=True)
class RectCell:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class VolumeBlock:
    role: str
    x0: float
    y0: float
    x1: float
    y1: float
    floor_start: int
    floor_count: int

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class BuildingShape:
    width_m: float
    depth_m: float
    floors: int
    tile_size: float
    floor_height: float
    slab_thickness: float
    room_count: int
    stair_zone: RectCell
    stair_opening: tuple[float, float, float, float]
    rooms: list[RectCell]
    doors: list[tuple[str, float, float]]
    floor_profiles: list[FloorLevel]
    volume_blocks: tuple[VolumeBlock, ...]
    floor_footprints: tuple[tuple[float, float, float, float], ...]

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingShape":
        tile = float(settings.tile_size)
        width = float(settings.width_m)
        depth = float(settings.depth_m)
        floors = max(1, min(3, int(settings.floors)))  # low-rise only
        room_count = max(1, int(settings.room_count))

        stair_w = max(tile * 2, math.ceil(settings.stairs_width / tile) * tile)
        stair_d = tile * 4
        zone = RectCell(tile, tile, tile + stair_w, tile + stair_d)

        margin = settings.stair_opening_margin
        opening = (
            max(0.0, zone.x0 - margin),
            max(0.0, zone.y0 - margin),
            min(width, zone.x1 + margin),
            min(depth, zone.y1 + margin),
        )

        rooms = split_rectangles(width, depth, room_count, tile, settings.seed)
        doors = choose_connected_doors(rooms, settings.seed)
        floor_profiles = [
            FloorLevel(
                floor_index=i,
                z_floor=i * float(settings.floor_height),
                is_ground=(i == 0),
                is_top=(i == floors - 1),
            )
            for i in range(floors)
        ]

        volume_blocks = build_volume_blocks(width, depth, floors, tile, int(settings.seed), str(getattr(settings, "style_preset", "MINIMAL_MODERN_VILLA")))
        floor_footprints = tuple(build_floor_footprints(width, depth, floors, volume_blocks))

        return cls(
            width_m=width,
            depth_m=depth,
            floors=floors,
            tile_size=tile,
            floor_height=float(settings.floor_height),
            slab_thickness=float(settings.slab_thickness),
            room_count=room_count,
            stair_zone=zone,
            stair_opening=opening,
            rooms=rooms,
            doors=doors,
            floor_profiles=floor_profiles,
            volume_blocks=volume_blocks,
            floor_footprints=floor_footprints,
        )


def _snap_tile(value: float, tile: float) -> float:
    return round(value / tile) * tile


def _clamp_rect(rect: tuple[float, float, float, float], width: float, depth: float, tile: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = rect
    x0 = max(0.0, min(width - tile * 2, _snap_tile(x0, tile)))
    y0 = max(0.0, min(depth - tile * 2, _snap_tile(y0, tile)))
    x1 = max(x0 + tile * 2, min(width, _snap_tile(x1, tile)))
    y1 = max(y0 + tile * 2, min(depth, _snap_tile(y1, tile)))
    return (x0, y0, x1, y1)


def build_volume_blocks(width: float, depth: float, floors: int, tile: float, seed: int, preset: str) -> tuple[VolumeBlock, ...]:
    rng = random.Random(seed * 103 + 17)
    main_w = _snap_tile(max(tile * 4, width * (0.62 + rng.random() * 0.2)), tile)
    main_d = _snap_tile(max(tile * 4, depth * (0.58 + rng.random() * 0.24)), tile)
    main_x0 = 0.0 if rng.random() < 0.65 else _snap_tile((width - main_w) * rng.random() * 0.45, tile)
    main_y0 = 0.0 if rng.random() < 0.7 else _snap_tile((depth - main_d) * rng.random() * 0.45, tile)
    main_x0, main_y0, main_x1, main_y1 = _clamp_rect((main_x0, main_y0, main_x0 + main_w, main_y0 + main_d), width, depth, tile)
    main = VolumeBlock("main", main_x0, main_y0, main_x1, main_y1, 0, floors)
    blocks = [main]

    entrance_w = _snap_tile(max(tile * 2, main.width * (0.35 + rng.random() * 0.2)), tile)
    entrance_d = _snap_tile(max(tile * 1.0, depth * (0.14 + rng.random() * 0.1)), tile)
    cx = main.x0 + main.width * (0.28 + rng.random() * 0.44)
    ex0 = max(0.0, _snap_tile(cx - entrance_w * 0.5, tile))
    ex1 = min(width, ex0 + entrance_w)
    ey0 = max(0.0, main.y0 - entrance_d)
    ey1 = min(depth, main.y0 + tile * 1.2)
    ex0, ey0, ex1, ey1 = _clamp_rect((ex0, ey0, ex1, ey1), width, depth, tile)
    blocks.append(VolumeBlock("entrance", ex0, ey0, ex1, ey1, 0, 1))

    if width >= tile * 5 and depth >= tile * 4:
        side_w = _snap_tile(max(tile * 2, width * (0.24 + rng.random() * 0.12)), tile)
        side_d = _snap_tile(max(tile * 2, depth * (0.45 + rng.random() * 0.25)), tile)
        side_on_left = rng.random() < 0.5
        side_y0 = max(0.0, min(depth - side_d, main.y0 + (main.depth - side_d) * (0.2 + rng.random() * 0.5)))
        if side_on_left:
            side_rect = (max(0.0, main.x0 - side_w + tile), side_y0, max(tile * 2, main.x0 + tile), side_y0 + side_d)
        else:
            side_rect = (min(width - tile * 2, main.x1 - tile), side_y0, min(width, main.x1 + side_w - tile), side_y0 + side_d)
        sx0, sy0, sx1, sy1 = _clamp_rect(side_rect, width, depth, tile)
        blocks.append(VolumeBlock("utility", sx0, sy0, sx1, sy1, 0, 1))

    if floors >= 2:
        upper_w = _snap_tile(max(tile * 2, main.width * (0.62 + rng.random() * 0.28)), tile)
        upper_d = _snap_tile(max(tile * 2, main.depth * (0.58 + rng.random() * 0.26)), tile)
        max_shift_x = max(0.0, main.width - upper_w)
        max_shift_y = max(0.0, main.depth - upper_d)

        if preset in {"TERRACE_HOUSE", "COMPACT_URBAN_HOUSE"}:
            shift_x = main.x0 + max_shift_x * (0.05 + rng.random() * 0.35)
            shift_y = main.y0 + max_shift_y * (0.18 + rng.random() * 0.45)
        elif preset == "MINIMAL_MODERN_VILLA":
            shift_x = main.x0 + max_shift_x * (0.2 + rng.random() * 0.55)
            shift_y = main.y0 + max_shift_y * (0.05 + rng.random() * 0.3)
        else:
            shift_x = main.x0 + max_shift_x * (0.12 + rng.random() * 0.45)
            shift_y = main.y0 + max_shift_y * (0.1 + rng.random() * 0.4)

        ux0, uy0, ux1, uy1 = _clamp_rect((shift_x, shift_y, shift_x + upper_w, shift_y + upper_d), width, depth, tile)
        blocks.append(VolumeBlock("upper", ux0, uy0, ux1, uy1, 1, min(2, floors - 1)))

    # safety: keep 2-4 blocks and deterministic order
    dedup = {}
    for block in blocks:
        key = (block.role, block.floor_start, block.floor_count, round(block.x0, 3), round(block.y0, 3), round(block.x1, 3), round(block.y1, 3))
        dedup[key] = block
    resolved = list(dedup.values())[:4]
    return tuple(resolved)


def build_floor_footprints(width: float, depth: float, floors: int, blocks: tuple[VolumeBlock, ...]) -> list[tuple[float, float, float, float]]:
    result: list[tuple[float, float, float, float]] = []
    for floor_idx in range(floors):
        active = [b for b in blocks if b.floor_start <= floor_idx < (b.floor_start + b.floor_count)]
        if not active:
            result.append((0.0, 0.0, width, depth))
            continue
        x0 = min(b.x0 for b in active)
        y0 = min(b.y0 for b in active)
        x1 = max(b.x1 for b in active)
        y1 = max(b.y1 for b in active)
        result.append((x0, y0, x1, y1))
    return result


def split_rectangles(width, depth, target_rooms, tile, seed):
    rng = random.Random(seed)
    rooms = [RectCell(0.0, 0.0, width, depth)]

    def can_split(cell):
        return (cell.x1 - cell.x0) >= tile * 4 or (cell.y1 - cell.y0) >= tile * 4

    while len(rooms) < target_rooms:
        candidates = [r for r in rooms if can_split(r)]
        if not candidates:
            break
        cell = max(candidates, key=lambda c: (c.x1 - c.x0) * (c.y1 - c.y0))
        rooms.remove(cell)
        vertical = (cell.x1 - cell.x0) >= (cell.y1 - cell.y0)
        if (cell.x1 - cell.x0) < tile * 4:
            vertical = False
        if (cell.y1 - cell.y0) < tile * 4:
            vertical = True

        if vertical:
            choices = []
            x = cell.x0 + tile * 2
            while x <= cell.x1 - tile * 2 + 1e-6:
                choices.append(x)
                x += tile
            cut = rng.choice(choices)
            rooms.append(RectCell(cell.x0, cell.y0, cut, cell.y1))
            rooms.append(RectCell(cut, cell.y0, cell.x1, cell.y1))
        else:
            choices = []
            y = cell.y0 + tile * 2
            while y <= cell.y1 - tile * 2 + 1e-6:
                choices.append(y)
                y += tile
            cut = rng.choice(choices)
            rooms.append(RectCell(cell.x0, cell.y0, cell.x1, cut))
            rooms.append(RectCell(cell.x0, cut, cell.x1, cell.y1))
    return rooms


def build_adjacency(rooms):
    shared = []
    for i, a in enumerate(rooms):
        for j in range(i + 1, len(rooms)):
            b = rooms[j]
            if abs(a.x1 - b.x0) < 1e-6 or abs(b.x1 - a.x0) < 1e-6:
                fixed = a.x1 if abs(a.x1 - b.x0) < 1e-6 else a.x0
                s0 = max(a.y0, b.y0)
                s1 = min(a.y1, b.y1)
                if s1 - s0 >= 2.0:
                    shared.append(("V", i, j, fixed, s0, s1))
            if abs(a.y1 - b.y0) < 1e-6 or abs(b.y1 - a.y0) < 1e-6:
                fixed = a.y1 if abs(a.y1 - b.y0) < 1e-6 else a.y0
                s0 = max(a.x0, b.x0)
                s1 = min(a.x1, b.x1)
                if s1 - s0 >= 2.0:
                    shared.append(("H", i, j, fixed, s0, s1))
    return shared


def pick_door_center(s0, s1, rng):
    centers = []
    x = s0 + 1.0
    while x <= s1 - 1.0 + 1e-6:
        centers.append(round(x, 3))
        x += 2.0
    return rng.choice(centers) if centers else (s0 + s1) * 0.5


def choose_connected_doors(rooms, seed):
    rng = random.Random(seed + 404)
    segs = build_adjacency(rooms)
    if not rooms:
        return []
    visited = {0}
    doors = []
    while len(visited) < len(rooms):
        frontier = []
        for ori, a, b, fixed, s0, s1 in segs:
            if (a in visited and b not in visited) or (b in visited and a not in visited):
                frontier.append((ori, a, b, fixed, s0, s1))
        if not frontier:
            break
        ori, a, b, fixed, s0, s1 = rng.choice(frontier)
        doors.append((ori, fixed, pick_door_center(s0, s1, rng)))
        visited.add(a)
        visited.add(b)
    return doors

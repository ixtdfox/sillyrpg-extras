from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .building_style import FloorProfile


@dataclass(frozen=True)
class RectCell:
    x0: float
    y0: float
    x1: float
    y1: float


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
    floor_profiles: list[FloorProfile]

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingShape":
        tile = float(settings.tile_size)
        width = float(settings.width_m)
        depth = float(settings.depth_m)
        floors = max(1, min(3, int(settings.floors)))  # low-rise only
        room_count = max(1, int(round(settings.room_count * (0.5 if fast_mode else 1.0))))

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
            FloorProfile(
                floor_index=i,
                z_floor=i * float(settings.floor_height),
                is_ground=(i == 0),
                is_top=(i == floors - 1),
            )
            for i in range(floors)
        ]

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
        )


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

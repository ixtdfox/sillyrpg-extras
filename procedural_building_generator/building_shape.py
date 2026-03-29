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
    floor_cells: tuple[tuple[tuple[int, int], ...], ...]
    composition_tier: str
    stair_status: str
    fallback_reason: str

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingShape":
        tile = float(settings.tile_size)
        width = float(settings.width_m)
        depth = float(settings.depth_m)
        floors = max(1, min(3, int(settings.floors)))  # low-rise only
        room_count = max(1, int(settings.room_count))

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

        volume_blocks, tier, fallback_reason = resolve_volume_composition(
            width,
            depth,
            floors,
            tile,
            int(settings.seed),
            str(getattr(settings, "style_preset", "MINIMAL_MODERN_VILLA")),
        )
        floor_footprints = tuple(build_floor_footprints(width, depth, floors, volume_blocks))
        floor_cells = tuple(build_floor_cells(width, depth, tile, floors, volume_blocks))
        zone, opening, stair_status, stair_fallback_reason = resolve_stair_layout(
            width,
            depth,
            floors,
            tile,
            float(settings.stairs_width),
            float(settings.stair_opening_margin),
            floor_cells,
        )
        if stair_status == "fallback-main-block":
            volume_blocks = _tier_c_blocks(width, depth, floors)
            floor_footprints = tuple(build_floor_footprints(width, depth, floors, volume_blocks))
            floor_cells = tuple(build_floor_cells(width, depth, tile, floors, volume_blocks))
            zone, opening, stair_status, _ = resolve_stair_layout(
                width,
                depth,
                floors,
                tile,
                float(settings.stairs_width),
                float(settings.stair_opening_margin),
                floor_cells,
            )
            if tier != "C":
                tier = "C"
        fallback = fallback_reason
        if stair_fallback_reason:
            fallback = f"{fallback} | {stair_fallback_reason}" if fallback else stair_fallback_reason

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
            floor_cells=floor_cells,
            composition_tier=tier,
            stair_status=stair_status,
            fallback_reason=fallback,
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
        # Robustness-first rule:
        # keep upper floors aligned with main mass so external walls are always present
        # and stair-to-floor continuity stays predictable.
        blocks.append(VolumeBlock("upper", main.x0, main.y0, main.x1, main.y1, 1, floors - 1))

    # safety: keep 2-4 blocks and deterministic order
    dedup = {}
    for block in blocks:
        key = (block.role, block.floor_start, block.floor_count, round(block.x0, 3), round(block.y0, 3), round(block.x1, 3), round(block.y1, 3))
        dedup[key] = block
    resolved = list(dedup.values())[:4]
    return tuple(resolved)


def _intersection_area(a: VolumeBlock, b: VolumeBlock) -> float:
    dx = min(a.x1, b.x1) - max(a.x0, b.x0)
    dy = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, dx) * max(0.0, dy)


def _blocks_for_floor(blocks: tuple[VolumeBlock, ...], floor_idx: int) -> list[VolumeBlock]:
    return [b for b in blocks if b.floor_start <= floor_idx < (b.floor_start + b.floor_count)]


def _validate_volume_blocks(blocks: tuple[VolumeBlock, ...], floors: int, tile: float) -> tuple[bool, str]:
    main = next((b for b in blocks if b.role == "main"), None)
    if main is None:
        return False, "missing main block"
    min_span = tile * 2
    for block in blocks:
        if block.width < min_span or block.depth < min_span:
            return False, f"{block.role} block too thin"
        if block.role != "main":
            attached = False
            for f in range(max(0, block.floor_start), min(floors, block.floor_start + block.floor_count)):
                if _intersection_area(main, block) >= tile * tile * 0.5:
                    attached = True
                    break
            if not attached:
                return False, f"detached {block.role} block"

    for floor_idx in range(floors):
        active = _blocks_for_floor(blocks, floor_idx)
        if not active:
            return False, f"empty floor {floor_idx}"
        connected: list[VolumeBlock] = [active[0]]
        pending = active[1:]
        while pending:
            progressed = False
            for block in pending[:]:
                if any(_intersection_area(block, seen) >= tile * tile * 0.5 for seen in connected):
                    connected.append(block)
                    pending.remove(block)
                    progressed = True
            if not progressed:
                return False, f"disconnected masses on floor {floor_idx}"
    return True, ""


def _tier_b_blocks(width: float, depth: float, floors: int, tile: float, seed: int) -> tuple[VolumeBlock, ...]:
    rng = random.Random(seed * 911 + 41)
    main = VolumeBlock("main", 0.0, 0.0, width, depth, 0, floors)
    blocks = [main]
    if width >= tile * 6 and depth >= tile * 6:
        ext_w = _snap_tile(max(tile * 2, width * (0.22 + rng.random() * 0.12)), tile)
        ext_d = _snap_tile(max(tile * 2, depth * (0.2 + rng.random() * 0.12)), tile)
        if rng.random() < 0.5:
            x0 = 0.0
        else:
            x0 = width - ext_w
        y0 = 0.0
        x0, y0, x1, y1 = _clamp_rect((x0, y0, x0 + ext_w, y0 + ext_d), width, depth, tile)
        blocks.append(VolumeBlock("entrance", x0, y0, x1, y1, 0, 1))
    if floors >= 2:
        shrink = tile * (1 + (seed % 2))
        ux0 = min(max(main.x0 + shrink, 0.0), width - tile * 2)
        uy0 = min(max(main.y0 + shrink, 0.0), depth - tile * 2)
        ux1 = max(ux0 + tile * 2, main.x1 - shrink)
        uy1 = max(uy0 + tile * 2, main.y1 - shrink)
        ux0, uy0, ux1, uy1 = _clamp_rect((ux0, uy0, ux1, uy1), width, depth, tile)
        blocks.append(VolumeBlock("upper", ux0, uy0, ux1, uy1, 1, min(2, floors - 1)))
    return tuple(blocks)


def _tier_c_blocks(width: float, depth: float, floors: int) -> tuple[VolumeBlock, ...]:
    return (VolumeBlock("main", 0.0, 0.0, width, depth, 0, floors),)


def resolve_volume_composition(width: float, depth: float, floors: int, tile: float, seed: int, preset: str) -> tuple[tuple[VolumeBlock, ...], str, str]:
    tier_a = build_volume_blocks(width, depth, floors, tile, seed, preset)
    ok, reason = _validate_volume_blocks(tier_a, floors, tile)
    if ok:
        return tier_a, "A", ""

    tier_b = _tier_b_blocks(width, depth, floors, tile, seed)
    ok_b, reason_b = _validate_volume_blocks(tier_b, floors, tile)
    if ok_b:
        return tier_b, "B", f"multi-volume composition invalid: {reason} -> fallback to attached two-volume shape"

    tier_c = _tier_c_blocks(width, depth, floors)
    return tier_c, "C", f"tier-b composition invalid: {reason_b} -> fallback to single coherent main block"


def _find_stair_zone(width: float, depth: float, tile: float, stairs_width: float, floors: int, floor_cells: tuple[tuple[tuple[int, int], ...], ...]) -> RectCell | None:
    stair_w_tiles = max(2, int(math.ceil(stairs_width / tile)))
    stair_d_tiles = 4
    if floors <= 1:
        return RectCell(tile, tile, tile + stair_w_tiles * tile, tile + stair_d_tiles * tile)
    shared = set(floor_cells[0]) if floor_cells else set()
    for f in range(1, floors):
        shared &= set(floor_cells[f])
    if not shared:
        return None
    nx = max(1, int(round(width / tile)))
    ny = max(1, int(round(depth / tile)))
    for iy in range(0, ny - stair_d_tiles + 1):
        for ix in range(0, nx - stair_w_tiles + 1):
            ok = True
            for tx in range(ix, ix + stair_w_tiles):
                for ty in range(iy, iy + stair_d_tiles):
                    if (tx, ty) not in shared:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return RectCell(ix * tile, iy * tile, (ix + stair_w_tiles) * tile, (iy + stair_d_tiles) * tile)
    return None


def resolve_stair_layout(width: float, depth: float, floors: int, tile: float, stairs_width: float, margin: float, floor_cells: tuple[tuple[tuple[int, int], ...], ...]) -> tuple[RectCell, tuple[float, float, float, float], str, str]:
    zone = _find_stair_zone(width, depth, tile, stairs_width, floors, floor_cells)
    if zone is None and floors > 1:
        single = _tier_c_blocks(width, depth, floors)
        fallback_cells = tuple(build_floor_cells(width, depth, tile, floors, single))
        zone = _find_stair_zone(width, depth, tile, stairs_width, floors, fallback_cells)
        if zone is None:
            zone = RectCell(tile, tile, tile + max(tile * 2, stairs_width), tile + tile * 4)
        opening = (
            max(0.0, zone.x0 - margin),
            max(0.0, zone.y0 - margin),
            min(width, zone.x1 + margin),
            min(depth, zone.y1 + margin),
        )
        return zone, opening, "fallback-main-block", "stair placement failed in composed shape -> fallback to simpler main block"

    if zone is None:
        zone = RectCell(tile, tile, tile + max(tile * 2, stairs_width), tile + tile * 4)
    opening = (
        max(0.0, zone.x0 - margin),
        max(0.0, zone.y0 - margin),
        min(width, zone.x1 + margin),
        min(depth, zone.y1 + margin),
    )
    return zone, opening, "ok", ""


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


def build_floor_cells(width: float, depth: float, tile: float, floors: int, blocks: tuple[VolumeBlock, ...]) -> list[tuple[tuple[int, int], ...]]:
    nx = max(1, int(round(width / tile)))
    ny = max(1, int(round(depth / tile)))
    out: list[tuple[tuple[int, int], ...]] = []
    for floor_idx in range(floors):
        cells: set[tuple[int, int]] = set()
        active = [b for b in blocks if b.floor_start <= floor_idx < (b.floor_start + b.floor_count)]
        for block in active:
            ix0 = max(0, int(math.floor(block.x0 / tile + 1e-6)))
            iy0 = max(0, int(math.floor(block.y0 / tile + 1e-6)))
            ix1 = min(nx, int(math.ceil(block.x1 / tile - 1e-6)))
            iy1 = min(ny, int(math.ceil(block.y1 / tile - 1e-6)))
            for ix in range(ix0, ix1):
                for iy in range(iy0, iy1):
                    cells.add((ix, iy))
        out.append(tuple(sorted(cells)))
    return out


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

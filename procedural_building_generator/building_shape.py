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
    fallback_reason: str
    stair_status: str

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingShape":
        tile = float(settings.tile_size)
        width = float(settings.width_m)
        depth = float(settings.depth_m)
        floors = max(1, min(3, int(settings.floors)))  # low-rise only
        room_count = max(1, int(settings.room_count))

        stair_w = max(tile * 2, math.ceil(settings.stairs_width / tile) * tile)
        stair_d = tile * 4

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

        volume_blocks, composition_tier, fallback_reason = build_volume_blocks(width, depth, floors, tile, int(settings.seed), str(getattr(settings, "style_preset", "MINIMAL_MODERN_VILLA")))
        floor_footprints = tuple(build_floor_footprints(width, depth, floors, volume_blocks))
        floor_cells = tuple(build_floor_cells(width, depth, tile, floors, volume_blocks))
        zone = _resolve_stair_zone(width, depth, tile, floors, stair_w, stair_d, floor_cells)
        if zone is None:
            single_main = (VolumeBlock("main", 0.0, 0.0, width, depth, 0, floors),)
            volume_blocks = single_main
            floor_footprints = tuple(build_floor_footprints(width, depth, floors, volume_blocks))
            floor_cells = tuple(build_floor_cells(width, depth, tile, floors, volume_blocks))
            zone = _resolve_stair_zone(width, depth, tile, floors, stair_w, stair_d, floor_cells)
            composition_tier = "C"
            base_reason = fallback_reason if fallback_reason != "none" else "stair placement failed"
            fallback_reason = f"{base_reason} -> fallback to coherent single block"
        if zone is None:
            zone = RectCell(tile, tile, min(width, tile + stair_w), min(depth, tile + stair_d))
            stair_status = "forced-default-zone"
        else:
            stair_status = "placed"

        margin = settings.stair_opening_margin
        opening = (
            max(0.0, zone.x0 - margin),
            max(0.0, zone.y0 - margin),
            min(width, zone.x1 + margin),
            min(depth, zone.y1 + margin),
        )

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
            composition_tier=composition_tier,
            fallback_reason=fallback_reason,
            stair_status=stair_status,
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


def _overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _blocks_attach(a: VolumeBlock, b: VolumeBlock, tile: float) -> bool:
    x_overlap = _overlap_1d(a.x0, a.x1, b.x0, b.x1)
    y_overlap = _overlap_1d(a.y0, a.y1, b.y0, b.y1)
    if x_overlap >= tile * 0.5 and y_overlap > 1e-6:
        return True
    if y_overlap >= tile * 0.5 and x_overlap > 1e-6:
        return True
    touch_x = abs(a.x1 - b.x0) <= 1e-6 or abs(b.x1 - a.x0) <= 1e-6
    touch_y = abs(a.y1 - b.y0) <= 1e-6 or abs(b.y1 - a.y0) <= 1e-6
    return (touch_x and y_overlap >= tile * 0.5) or (touch_y and x_overlap >= tile * 0.5)


def _attachment_strength(a: VolumeBlock, b: VolumeBlock) -> float:
    x_overlap = _overlap_1d(a.x0, a.x1, b.x0, b.x1)
    y_overlap = _overlap_1d(a.y0, a.y1, b.y0, b.y1)
    if x_overlap > 0.0 and y_overlap > 0.0:
        return x_overlap * y_overlap
    touch_x = abs(a.x1 - b.x0) <= 1e-6 or abs(b.x1 - a.x0) <= 1e-6
    touch_y = abs(a.y1 - b.y0) <= 1e-6 or abs(b.y1 - a.y0) <= 1e-6
    if touch_x:
        return y_overlap
    if touch_y:
        return x_overlap
    return 0.0


def _validate_blocks(width: float, depth: float, floors: int, tile: float, blocks: tuple[VolumeBlock, ...]) -> tuple[bool, str]:
    main = next((b for b in blocks if b.role == "main"), None)
    if main is None:
        return False, "missing main block"
    if main.width < tile * 2 or main.depth < tile * 2:
        return False, "main block too thin"
    for b in blocks:
        if b.width < tile * 2 or b.depth < tile * 2:
            return False, f"{b.role} block too thin"
        if b.role in {"entrance", "utility"}:
            min_area = tile * tile * (4 if b.role == "entrance" else 6)
            if b.width * b.depth < min_area:
                return False, f"{b.role} block too small"
            aspect = max(b.width, b.depth) / max(tile * 0.25, min(b.width, b.depth))
            if aspect > (4.0 if b.role == "entrance" else 3.0):
                return False, f"{b.role} block too strip-like"
        if b.x0 < -1e-6 or b.y0 < -1e-6 or b.x1 > width + 1e-6 or b.y1 > depth + 1e-6:
            return False, f"{b.role} block out of bounds"
        if b.floor_count <= 0:
            return False, f"{b.role} has no floors"
        if b.floor_start < 0 or (b.floor_start + b.floor_count) > floors:
            return False, f"{b.role} floor span invalid"
        if b.role != "main" and not _blocks_attach(main, b, tile):
            return False, f"detached {b.role} block"
        if b.role in {"entrance", "utility"}:
            strength = _attachment_strength(main, b)
            min_strength = tile * tile * (1.6 if b.role == "entrance" else 2.0)
            if strength < min_strength:
                return False, f"weak {b.role} attachment"

    floor_cells = build_floor_cells(width, depth, tile, floors, blocks)
    for floor_idx, cells in enumerate(floor_cells):
        if not cells:
            return False, f"empty floor cells on floor {floor_idx}"
        pending = set(cells)
        stack = [next(iter(pending))]
        seen = set()
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            x, y = c
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in pending and n not in seen:
                    stack.append(n)
        if len(seen) != len(pending):
            return False, f"disconnected floor mass on floor {floor_idx}"
    return True, "ok"


def _build_tier_a(width: float, depth: float, floors: int, tile: float, seed: int, preset: str) -> tuple[VolumeBlock, ...]:
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
        overlap = min(tile * 2, max(tile, side_w * 0.45))
        side_y0 = max(0.0, min(depth - side_d, main.y0 + (main.depth - side_d) * (0.2 + rng.random() * 0.5)))
        if side_on_left:
            side_rect = (max(0.0, main.x0 - side_w + overlap), side_y0, max(tile * 2, main.x0 + overlap), side_y0 + side_d)
        else:
            side_rect = (min(width - tile * 2, main.x1 - overlap), side_y0, min(width, main.x1 + side_w - overlap), side_y0 + side_d)
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


def _build_tier_b(width: float, depth: float, floors: int, tile: float, seed: int, preset: str) -> tuple[VolumeBlock, ...]:
    rng = random.Random(seed * 97 + 29)
    main_w = _snap_tile(max(tile * 5, width * (0.7 + rng.random() * 0.16)), tile)
    main_d = _snap_tile(max(tile * 5, depth * (0.68 + rng.random() * 0.16)), tile)
    mx0, my0, mx1, my1 = _clamp_rect((0.0, 0.0, main_w, main_d), width, depth, tile)
    main = VolumeBlock("main", mx0, my0, mx1, my1, 0, floors)
    entrance_w = _snap_tile(max(tile * 2, main.width * (0.3 + rng.random() * 0.12)), tile)
    ex0 = _snap_tile(main.x0 + (main.width - entrance_w) * (0.3 + rng.random() * 0.35), tile)
    ex1 = min(width, ex0 + entrance_w)
    ey1 = min(depth, main.y0 + tile * 1.2)
    ey0 = max(0.0, ey1 - tile * 2)
    ex0, ey0, ex1, ey1 = _clamp_rect((ex0, ey0, ex1, ey1), width, depth, tile)
    blocks = [main, VolumeBlock("entrance", ex0, ey0, ex1, ey1, 0, 1)]
    if floors >= 2:
        upper_inset_x = _snap_tile(tile * (1 + (seed % 2)), tile)
        upper_inset_y = _snap_tile(tile * (1 + ((seed // 2) % 2)), tile)
        ux0 = main.x0 + upper_inset_x
        uy0 = main.y0 + upper_inset_y
        ux1 = max(ux0 + tile * 2, main.x1 - upper_inset_x)
        uy1 = max(uy0 + tile * 2, main.y1 - upper_inset_y)
        ux0, uy0, ux1, uy1 = _clamp_rect((ux0, uy0, ux1, uy1), width, depth, tile)
        blocks.append(VolumeBlock("upper", ux0, uy0, ux1, uy1, 1, min(2, floors - 1)))
    return tuple(blocks)


def _build_tier_c(width: float, depth: float, floors: int) -> tuple[VolumeBlock, ...]:
    return (VolumeBlock("main", 0.0, 0.0, width, depth, 0, floors),)


def build_volume_blocks(width: float, depth: float, floors: int, tile: float, seed: int, preset: str) -> tuple[tuple[VolumeBlock, ...], str, str]:
    tiers = (
        ("A", _build_tier_a(width, depth, floors, tile, seed, preset), "none"),
        ("B", _build_tier_b(width, depth, floors, tile, seed, preset), "multi-volume composition invalid"),
        ("C", _build_tier_c(width, depth, floors), "attached two-volume composition invalid"),
    )
    prior_reason = "none"
    for idx, (tier, blocks, reason) in enumerate(tiers):
        valid, detail = _validate_blocks(width, depth, floors, tile, blocks)
        if valid:
            if idx == 0:
                return blocks, tier, "none"
            return blocks, tier, f"{prior_reason}: {detail} -> fallback to tier {tier}"
        prior_reason = reason if idx == 0 else f"{prior_reason}: {detail}"
    return tiers[-1][1], "C", f"{prior_reason}: forcing coherent single block"


def _resolve_stair_zone(width: float, depth: float, tile: float, floors: int, stair_w: float, stair_d: float, floor_cells: tuple[tuple[tuple[int, int], ...], ...]) -> RectCell | None:
    if floors <= 1:
        return RectCell(tile, tile, min(width, tile + stair_w), min(depth, tile + stair_d))
    req_w = max(2, int(round(stair_w / tile)))
    req_d = 4
    common = set(floor_cells[0]) if floor_cells else set()
    for floor_idx in range(1, min(floors, len(floor_cells))):
        common &= set(floor_cells[floor_idx])
    if not common:
        return None
    nx = max(1, int(round(width / tile)))
    ny = max(1, int(round(depth / tile)))
    candidates = []
    for iy in range(0, ny - req_d + 1):
        for ix in range(0, nx - req_w + 1):
            ok = True
            for tx in range(ix, ix + req_w):
                for ty in range(iy, iy + req_d):
                    if (tx, ty) not in common:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                candidates.append((ix, iy))
    if not candidates:
        return None
    pick_ix, pick_iy = sorted(candidates, key=lambda v: (v[0] + v[1], v[1], v[0]))[0]
    return RectCell(pick_ix * tile, pick_iy * tile, (pick_ix + req_w) * tile, (pick_iy + req_d) * tile)


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

"""Core generator logic for Procedural Floorplan RU addon.
This module is adapted from the user's patched standalone script.
"""

import bpy
import random
import math
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ============================================================
# Procedural floor plan for Blender 4.0
# Dynamic footprint version:
# house width/depth are not set directly, they are derived from
# the amount of rooms and their target sizes.
# ============================================================

DELETE_OLD = True
COLLECTION_NAME = "GeneratedFloorPlan"

WALL_HEIGHT = 2.8
WALL_THICKNESS = 0.18
FLOOR_THICKNESS = 0.08
CORRIDOR_WIDTH = 1.6
DOOR_WIDTH = 0.95
ENTRY_DOOR_WIDTH = 0.90
ENTRY_DOOR_THICKNESS = 0.05
DOOR_HEIGHT = 2.1
STAIR_WIDTH = 1.05
STAIR_LANDING = 1.05
STAIR_MID_LANDING = 1.45
STAIR_RISER = 0.175
STAIR_TREAD = 0.28
STAIR_CLEARANCE = 0.2
STAIR_MAX_PARENT_OCCUPANCY = 0.34
STAIR_MIN_FREE_AREA = 8.0
STAIR_DOOR_CLEARANCE = 0.45
STAIR_WINDOW_CLEARANCE = 0.35
WINDOW_SILL_HEIGHT = 0.9
WINDOW_HEIGHT = 1.25
WINDOW_MIN_WIDTH = 1.0
WINDOW_END_MARGIN = 0.45
WINDOW_STRIP_WIDTH = 1.0
OUTER_MARGIN = 0.0  # rooms now touch the inner face of the exterior wall
ROOM_GAP = 0.0  # keep adjacent rooms flush so we do not create double walls

MIN_ROOM_SIDE = 2.2
MAX_ASPECT = 2.4
TEXT_SIZE = 0.34

POST_MERGE_MIN_SIDE = 1.35
POST_MERGE_MIN_AREA = 3.2
POST_MERGE_MAX_ASPECT = 4.2
POST_MERGE_HARD_MAX_ASPECT = 6.0
POST_MERGE_EDGE_STRIP_SIDE = 1.15
POST_MERGE_SLIVER_RATIO = 0.24
POST_MERGE_MIN_SHARED = 0.7

RESIDUAL_MIN_AREA = 0.35
RESIDUAL_LONG_STRIP_RATIO = 3.8
RESIDUAL_SHORT_SIDE = 1.25
RESIDUAL_CORRIDOR_SHARED_BONUS = 8.0

# Global scaling of the whole house. >1.0 makes everything roomier.
HOUSE_SCALE = 1.00

TARGET_ROOM_COUNT = 6  # minimum 4: bedroom, living, bathroom, kitchen
AUTO_RANDOM_SEED = True
SEED = 42
MIN_FLOORS = 1
MAX_FLOORS = 3
FLOOR_TO_FLOOR_HEIGHT = WALL_HEIGHT + FLOOR_THICKNESS

MODULAR_TILES_ENABLED = True
WALL_TILE_WIDTH = 1.0
SURFACE_TILE_SIZE = 1.0

# creative: upper floors may have different footprints
# strict: every floor is scaled to match the 1st floor footprint exactly
BUILDING_MODE = "creative"  # or "strict"

# quad keeps the legacy rectangular generator.
# Other values use rectilinear composed footprints.
SHAPE_MODE = "quad"  # quad | l | u | h | t | courtyard | offset
STRICT_EDGE_TOL = max(WALL_THICKNESS * 0.75, 0.22)

EXTRA_ROOM_TYPES = [
    'bedroom',
    'bedroom',
    'bathroom',
    'dining',
    'study',
    'laundry',
    'pantry',
    'storage',
]

EPS = 1e-6


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.h

    @property
    def cx(self):
        return self.x + self.w * 0.5

    @property
    def cy(self):
        return self.y + self.h * 0.5

    @property
    def area(self):
        return self.w * self.h

    def inset(self, m: float):
        return Rect(self.x + m, self.y + m, max(EPS, self.w - 2*m), max(EPS, self.h - 2*m))


def scale_rect(rect: Optional["Rect"], sx: float, sy: float) -> Optional["Rect"]:
    if rect is None:
        return None
    return Rect(rect.x * sx, rect.y * sy, rect.w * sx, rect.h * sy)


def scale_floor_spec(spec: dict, target_width: float, target_depth: float) -> dict:
    src_w = spec["width"]
    src_d = spec["depth"]
    if src_w <= EPS or src_d <= EPS:
        return spec

    sx = target_width / src_w
    sy = target_depth / src_d
    if abs(sx - 1.0) < EPS and abs(sy - 1.0) < EPS:
        spec["width"] = target_width
        spec["depth"] = target_depth
        return spec

    for room in spec["rooms"]:
        room.rect = scale_rect(room.rect, sx, sy)
    spec["corridor"] = scale_rect(spec["corridor"], sx, sy)
    if spec.get("stair") is not None:
        spec["stair"].rect = scale_rect(spec["stair"].rect, sx, sy)
    if spec.get("open_void") is not None:
        spec["open_void"] = scale_rect(spec["open_void"], sx, sy)
    spec["width"] = target_width
    spec["depth"] = target_depth
    return spec


@dataclass
class Room:
    key: str
    label: str
    target_area: float
    zone: str
    rect: Optional[Rect] = None
    color: Tuple[float, float, float, float] = (0.75, 0.75, 0.75, 1.0)
    needs_corridor: bool = True
    preferred_aspect: float = 1.2


@dataclass
class Opening:
    start: float
    end: float
    z0: float = 0.0
    z1: float = DOOR_HEIGHT

    @property
    def width(self):
        return self.end - self.start




@dataclass
class StairPlacement:
    parent_key: str
    parent_label: str
    rect: Rect
    orientation: str  # 'X' or 'Y' long axis
    corner: str       # 'SW', 'SE', 'NW', 'NE'
    score: float


HOUSE_WIDTH = 0.0
HOUSE_DEPTH = 0.0


def clamp(v, a, b):
    return max(a, min(b, v))


def almost(a, b, eps=1e-5):
    return abs(a - b) <= eps


def overlap(a1, a2, b1, b2):
    s = max(a1, b1)
    e = min(a2, b2)
    return (s, e) if e - s > EPS else None


def get_collection(name: str):
    root = bpy.context.scene.collection
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        root.children.link(col)
    return col


def clear_collection(col):
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def ensure_material(name, color):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs[0].default_value = color
        bsdf.inputs[7].default_value = 0.25
    return mat


def link_obj(obj, col):
    col.objects.link(obj)


def add_box(col, name, x, y, z, sx, sy, sz, mat=None):
    bpy.ops.mesh.primitive_cube_add(location=(x, y, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx * 0.5, sy * 0.5, sz * 0.5)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    link_obj(obj, col)
    if mat:
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
    return obj


def _split_length_into_tiles(length: float, nominal: float, keep_uniform: bool = False) -> List[Tuple[float, float]]:
    if length <= EPS:
        return []
    nominal = max(EPS, nominal)
    if keep_uniform:
        count = max(1, int(round(length / nominal)))
        tile = length / count
        cursor = 0.0
        out = []
        for _ in range(count):
            out.append((cursor + tile * 0.5, tile))
            cursor += tile
        return out

    count = max(1, int(math.floor((length + EPS) / nominal)))
    out = []
    cursor = 0.0
    for _ in range(count):
        out.append((cursor + nominal * 0.5, nominal))
        cursor += nominal
    remainder = length - cursor
    if remainder > EPS:
        if out and remainder < nominal * 0.35:
            prev_center, prev_size = out[-1]
            new_size = prev_size + remainder
            out[-1] = (length - new_size * 0.5, new_size)
        else:
            out.append((cursor + remainder * 0.5, remainder))
    return out


def _modular_unit() -> float:
    return max(EPS, WALL_TILE_WIDTH if MODULAR_TILES_ENABLED else 1.0)


def _snap_local_to_unit(value: float, unit: float) -> float:
    return round(value / unit) * unit


def _snap_opening_to_module(seg_start: float, seg_end: float, opening: Opening, unit: float) -> Optional[Opening]:
    s = max(seg_start, opening.start)
    e = min(seg_end, opening.end)
    if e - s <= EPS:
        return None

    available = seg_end - seg_start
    if available <= EPS:
        return None

    max_units = max(1, int(math.floor((available + EPS) / unit)))
    preferred_units = max(1, int(round((e - s) / unit)))
    units = min(preferred_units, max_units)
    snapped_width = units * unit

    desired_start_local = (s + e) * 0.5 - snapped_width * 0.5 - seg_start
    snapped_start_local = _snap_local_to_unit(desired_start_local, unit)
    snapped_start_local = clamp(snapped_start_local, 0.0, max(0.0, available - snapped_width))

    snapped_start = seg_start + snapped_start_local
    snapped_end = min(seg_end, snapped_start + snapped_width)
    if snapped_end - snapped_start <= EPS:
        return None
    return Opening(snapped_start, snapped_end, opening.z0, opening.z1)


def add_tiled_patch(col, name, x, y, z, sx, sy, sz, tile_x: float, tile_y: float, mat=None, keep_uniform: bool = False):
    x_parts = _split_length_into_tiles(sx, tile_x, keep_uniform=keep_uniform)
    y_parts = _split_length_into_tiles(sy, tile_y, keep_uniform=keep_uniform)
    base_x = x - sx * 0.5
    base_y = y - sy * 0.5
    created = []
    for ix, (off_x, part_x) in enumerate(x_parts):
        cx = base_x + off_x
        for iy, (off_y, part_y) in enumerate(y_parts):
            cy = base_y + off_y
            created.append(add_box(col, f"{name}_tile_{ix}_{iy}", cx, cy, z, part_x, part_y, sz, mat))
    return created


def add_world_aligned_surface_tiles(col, name, x, y, z, sx, sy, sz, tile_x: float, tile_y: float, mat=None):
    """Create exact-size horizontal tiles snapped to the global meter grid.

    This is mainly used for roofs so adjacent roof patches line up to the same
    1x1 meter grid instead of producing remainder strips like 0.396 x 0.783.
    Tiles may extend slightly beyond a patch boundary when the footprint is not
    divisible by the tile size, but every created tile keeps the exact nominal size.
    """
    tile_x = max(EPS, float(tile_x))
    tile_y = max(EPS, float(tile_y))
    min_x = x - sx * 0.5
    max_x = x + sx * 0.5
    min_y = y - sy * 0.5
    max_y = y + sy * 0.5

    start_ix = math.floor(min_x / tile_x)
    end_ix = math.ceil(max_x / tile_x)
    start_iy = math.floor(min_y / tile_y)
    end_iy = math.ceil(max_y / tile_y)

    created = []
    for ix in range(start_ix, end_ix):
        cx = (ix + 0.5) * tile_x
        cell_min_x = cx - tile_x * 0.5
        cell_max_x = cx + tile_x * 0.5
        if min(cell_max_x, max_x) - max(cell_min_x, min_x) <= EPS:
            continue
        for iy in range(start_iy, end_iy):
            cy = (iy + 0.5) * tile_y
            cell_min_y = cy - tile_y * 0.5
            cell_max_y = cy + tile_y * 0.5
            if min(cell_max_y, max_y) - max(cell_min_y, min_y) <= EPS:
                continue
            created.append(add_box(col, f"{name}_tile_{ix}_{iy}", cx, cy, z, tile_x, tile_y, sz, mat))
    return created


def add_text(col, text, x, y, z, size=TEXT_SIZE):
    curve = bpy.data.curves.new(type="FONT", name=f"TXT_{text}")
    curve.body = text
    curve.size = size
    obj = bpy.data.objects.new(f"TXT_{text}", curve)
    obj.location = (x, y, z)
    link_obj(obj, col)
    return obj


def room_color(zone: str):
    if zone == "social":
        return (0.88, 0.79, 0.64, 1.0)
    if zone == "private":
        return (0.75, 0.80, 0.94, 1.0)
    if zone == "service":
        return (0.74, 0.88, 0.75, 1.0)
    return (0.80, 0.80, 0.80, 1.0)


def build_program() -> List[Room]:
    room_count = max(4, int(TARGET_ROOM_COUNT))

    rooms = [
        Room("living", "Living", random.uniform(24.0, 32.0), "social", color=room_color("social"), needs_corridor=False, preferred_aspect=random.uniform(1.25, 1.65)),
        Room("kitchen", "Kitchen", random.uniform(9.0, 13.0), "service", color=room_color("service"), preferred_aspect=random.uniform(1.0, 1.35)),
        Room("bath_1", "Bathroom", random.uniform(4.2, 6.2), "service", color=room_color("service"), preferred_aspect=random.uniform(0.9, 1.15)),
        Room("bed_1", "Bedroom 1", random.uniform(11.0, 16.0), "private", color=room_color("private"), preferred_aspect=random.uniform(1.0, 1.35)),
    ]

    extra_slots = room_count - 4
    counts = {
        "bedroom": 1,
        "bathroom": 1,
        "dining": 0,
        "study": 0,
        "laundry": 0,
        "pantry": 0,
        "storage": 0,
    }

    for _ in range(extra_slots):
        available = []
        for kind in EXTRA_ROOM_TYPES:
            if kind in {"bedroom", "bathroom"}:
                available.append(kind)
            elif counts[kind] == 0:
                available.append(kind)
        kind = random.choice(available)
        counts[kind] += 1
        if kind == "bedroom":
            idx = counts[kind]
            rooms.append(Room(f"bed_{idx}", f"Bedroom {idx}", random.uniform(10.0, 14.0), "private", color=room_color("private"), preferred_aspect=random.uniform(1.0, 1.3)))
        elif kind == "bathroom":
            idx = counts[kind]
            rooms.append(Room(f"bath_{idx}", f"Bathroom {idx}", random.uniform(4.0, 5.8), "service", color=room_color("service"), preferred_aspect=random.uniform(0.9, 1.1)))
        elif kind == "dining":
            rooms.append(Room("dining", "Dining", random.uniform(8.0, 12.0), "social", color=room_color("social"), needs_corridor=False, preferred_aspect=random.uniform(1.0, 1.3)))
        elif kind == "study":
            rooms.append(Room("study", "Study", random.uniform(7.0, 10.0), "social", color=room_color("social"), preferred_aspect=random.uniform(1.0, 1.25)))
        elif kind == "laundry":
            rooms.append(Room("laundry", "Laundry", random.uniform(3.8, 5.2), "service", color=room_color("service"), preferred_aspect=random.uniform(0.9, 1.1)))
        elif kind == "pantry":
            rooms.append(Room("pantry", "Pantry", random.uniform(2.5, 3.8), "service", color=room_color("service"), preferred_aspect=random.uniform(0.85, 1.05)))
        elif kind == "storage":
            rooms.append(Room("storage", "Storage", random.uniform(2.8, 4.5), "service", color=room_color("service"), preferred_aspect=random.uniform(0.85, 1.05)))

    return rooms


def preferred_dims(room: Room) -> Tuple[float, float]:
    aspect = max(0.75, min(room.preferred_aspect * random.uniform(0.9, 1.1), MAX_ASPECT))
    area = room.target_area * random.uniform(0.94, 1.08)
    w = math.sqrt(area * aspect)
    h = area / max(w, EPS)
    w = max(w, MIN_ROOM_SIDE)
    h = max(h, MIN_ROOM_SIDE)
    return w * HOUSE_SCALE, h * HOUSE_SCALE


def order_rooms_for_strip(rooms: List[Room]) -> List[Room]:
    def score(r: Room):
        penalty = 0
        if "bath" in r.key or r.key in {"pantry", "laundry", "storage"}:
            penalty = 100
        return (penalty, -r.target_area)
    return sorted(rooms, key=score)


def good_rect(r: Rect) -> bool:
    if min(r.w, r.h) < MIN_ROOM_SIDE:
        return False
    aspect = max(r.w / max(r.h, EPS), r.h / max(r.w, EPS))
    return aspect <= MAX_ASPECT


def split_rect_by_targets(rect: Rect, rooms: List[Room]) -> List[Rect]:
    if len(rooms) == 1:
        return [rect]

    total = sum(r.target_area for r in rooms)
    half = total * 0.5
    acc = 0.0
    split_idx = 1
    for i in range(len(rooms)-1):
        acc += rooms[i].target_area
        if acc >= half:
            split_idx = i + 1
            break

    left = rooms[:split_idx]
    right = rooms[split_idx:]
    left_area = sum(r.target_area for r in left)
    frac = left_area / total if total > 0 else 0.5

    candidates = []
    if rect.w >= rect.h:
        cut = clamp(rect.w * frac, MIN_ROOM_SIDE * len(left), rect.w - MIN_ROOM_SIDE * len(right))
        candidates.append((Rect(rect.x, rect.y, cut, rect.h), Rect(rect.x + cut, rect.y, rect.w - cut, rect.h)))
    if rect.h >= rect.w * 0.6:
        cut = clamp(rect.h * frac, MIN_ROOM_SIDE * len(left), rect.h - MIN_ROOM_SIDE * len(right))
        candidates.append((Rect(rect.x, rect.y, rect.w, cut), Rect(rect.x, rect.y + cut, rect.w, rect.h - cut)))
    if rect.w < rect.h:
        cut = clamp(rect.h * frac, MIN_ROOM_SIDE * len(left), rect.h - MIN_ROOM_SIDE * len(right))
        candidates.append((Rect(rect.x, rect.y, rect.w, cut), Rect(rect.x, rect.y + cut, rect.w, rect.h - cut)))
        cut = clamp(rect.w * frac, MIN_ROOM_SIDE * len(left), rect.w - MIN_ROOM_SIDE * len(right))
        candidates.append((Rect(rect.x, rect.y, cut, rect.h), Rect(rect.x + cut, rect.y, rect.w - cut, rect.h)))

    best = None
    best_score = 1e18
    random.shuffle(candidates)
    for a, b in candidates:
        if a.w < MIN_ROOM_SIDE or a.h < MIN_ROOM_SIDE or b.w < MIN_ROOM_SIDE or b.h < MIN_ROOM_SIDE:
            continue
        score = abs((a.w / max(a.h, EPS)) - 1.0) + abs((b.w / max(b.h, EPS)) - 1.0) + random.uniform(0.0, 0.08)
        if score < best_score:
            best_score = score
            best = (a, b)

    if best is None:
        if rect.w >= rect.h:
            cut = rect.w * frac
            best = (Rect(rect.x, rect.y, cut, rect.h), Rect(rect.x + cut, rect.y, rect.w-cut, rect.h))
        else:
            cut = rect.h * frac
            best = (Rect(rect.x, rect.y, rect.w, cut), Rect(rect.x, rect.y + cut, rect.w, rect.h-cut))

    a, b = best
    return split_rect_by_targets(a, left) + split_rect_by_targets(b, right)


def estimate_footprint(rooms: List[Room]) -> Tuple[float, float]:
    room_by_key = {r.key: r for r in rooms}
    living_w, living_h = preferred_dims(room_by_key["living"])
    kitchen_w, kitchen_h = preferred_dims(room_by_key["kitchen"])
    dining = room_by_key.get("dining")
    dining_w, dining_h = preferred_dims(dining) if dining else (0.0, 0.0)

    remaining = [r for r in rooms if r.key not in {"living", "kitchen", "dining"}]
    left_strip = [r for r in remaining if r.zone == "private"]
    right_strip = [r for r in remaining if r.zone != "private"]
    if random.random() < 0.5:
        left_strip, right_strip = right_strip, left_strip
    if random.random() < 0.5:
        left_strip, right_strip = right_strip, left_strip
    if not right_strip and len(left_strip) > 1:
        right_strip.append(left_strip.pop())
    if not left_strip and len(right_strip) > 1:
        left_strip.append(right_strip.pop())

    left_dims = [preferred_dims(r) for r in order_rooms_for_strip(left_strip)]
    right_dims = [preferred_dims(r) for r in order_rooms_for_strip(right_strip)]

    left_width = max([d[0] for d in left_dims], default=0.0)
    right_width = max([d[0] for d in right_dims], default=0.0)

    left_depth = sum(d[1] for d in left_dims) + max(0, len(left_dims)-1) * ROOM_GAP
    right_depth = sum(d[1] for d in right_dims) + max(0, len(right_dims)-1) * ROOM_GAP

    front_width = dining_w + kitchen_w + living_w + ROOM_GAP * (2 if dining else 1)
    back_width = left_width + CORRIDOR_WIDTH + right_width + ROOM_GAP * 2
    usable_width = max(front_width, back_width)

    front_depth = max(living_h, kitchen_h, dining_h)
    back_depth = max(left_depth, right_depth)
    usable_depth = front_depth + ROOM_GAP + back_depth

    width = usable_width + WALL_THICKNESS
    depth = usable_depth + WALL_THICKNESS
    return width, depth


def layout_floorplan_quad(rooms: List[Room]):
    global HOUSE_WIDTH, HOUSE_DEPTH
    HOUSE_WIDTH, HOUSE_DEPTH = estimate_footprint(rooms)

    room_by_key = {r.key: r for r in rooms}
    living = room_by_key["living"]
    kitchen = room_by_key["kitchen"]
    dining = room_by_key.get("dining")

    margin = WALL_THICKNESS * 0.5
    usable = Rect(margin, margin, HOUSE_WIDTH - 2*margin, HOUSE_DEPTH - 2*margin)

    remaining = [r for r in rooms if r.key not in {"living", "kitchen", "dining"}]
    left_strip = [r for r in remaining if r.zone == "private"]
    right_strip = [r for r in remaining if r.zone != "private"]
    if random.random() < 0.5:
        left_strip, right_strip = right_strip, left_strip
    if not right_strip and len(left_strip) > 1:
        right_strip.append(left_strip.pop())
    if not left_strip and len(right_strip) > 1:
        left_strip.append(right_strip.pop())

    left_dims = [preferred_dims(r) for r in order_rooms_for_strip(left_strip)]
    right_dims = [preferred_dims(r) for r in order_rooms_for_strip(right_strip)]
    left_width = max([d[0] for d in left_dims], default=usable.w * 0.26)
    right_width = max([d[0] for d in right_dims], default=usable.w * 0.26)

    living_w_pref, living_h_pref = preferred_dims(living)
    kitchen_w_pref, kitchen_h_pref = preferred_dims(kitchen)
    dining_w_pref, dining_h_pref = preferred_dims(dining) if dining else (0.0, 0.0)

    front_h = max(living_h_pref, kitchen_h_pref, dining_h_pref, MIN_ROOM_SIDE + 0.6)

    corridor_x = usable.x + left_width + ROOM_GAP
    corridor = Rect(corridor_x, usable.y + front_h + ROOM_GAP, CORRIDOR_WIDTH, usable.h - front_h - ROOM_GAP)

    left_zone = Rect(usable.x, corridor.y, left_width, corridor.h)
    right_zone = Rect(corridor.x2 + ROOM_GAP, corridor.y, right_width, corridor.h)

    front_left_w = max(0.0, left_zone.w)
    front_right_w = max(0.0, right_zone.w)
    front_center_w = usable.w - front_left_w - front_right_w - 2 * ROOM_GAP
    front_center_w = max(front_center_w, living_w_pref)

    place_dining_left = random.random() < 0.5
    if dining and front_left_w >= MIN_ROOM_SIDE and place_dining_left:
        x_cursor = usable.x
        dining.rect = Rect(x_cursor, usable.y, front_left_w, front_h).inset(0.0)
        x_cursor += front_left_w + ROOM_GAP
        living.rect = Rect(x_cursor, usable.y, front_center_w, front_h).inset(0.0)
        x_cursor += front_center_w + ROOM_GAP
        kitchen.rect = Rect(x_cursor, usable.y, max(MIN_ROOM_SIDE, usable.x2 - x_cursor), front_h).inset(0.0)
    else:
        x_cursor = usable.x
        left_block_w = kitchen_w_pref if dining is None else max(front_left_w, kitchen_w_pref)
        kitchen.rect = Rect(x_cursor, usable.y, max(MIN_ROOM_SIDE, left_block_w), front_h).inset(0.0)
        x_cursor += max(MIN_ROOM_SIDE, left_block_w) + ROOM_GAP
        right_remaining = usable.x2 - x_cursor
        if dining and right_remaining - living_w_pref - ROOM_GAP >= MIN_ROOM_SIDE:
            living_w = max(living_w_pref, right_remaining - front_right_w - ROOM_GAP)
            living.rect = Rect(x_cursor, usable.y, living_w, front_h).inset(0.0)
            x_cursor += living_w + ROOM_GAP
            dining.rect = Rect(x_cursor, usable.y, max(MIN_ROOM_SIDE, usable.x2 - x_cursor), front_h).inset(0.0)
        else:
            living.rect = Rect(x_cursor, usable.y, max(MIN_ROOM_SIDE, usable.x2 - x_cursor), front_h).inset(0.0)

    def assign_strip(zone: Rect, strip_rooms: List[Room]):
        if not strip_rooms:
            return
        strip_rooms = order_rooms_for_strip(strip_rooms)
        rects = split_rect_by_targets(zone, strip_rooms)
        for room, rect in zip(strip_rooms, rects):
            room.rect = rect.inset(0.0)

    assign_strip(left_zone, left_strip)
    assign_strip(right_zone, right_strip)

    for r in rooms:
        if r.rect and not good_rect(r.rect):
            if r.rect.w < MIN_ROOM_SIDE:
                r.rect = Rect(r.rect.x, r.rect.y, MIN_ROOM_SIDE, r.rect.h)
            if r.rect.h < MIN_ROOM_SIDE:
                r.rect = Rect(r.rect.x, r.rect.y, r.rect.w, MIN_ROOM_SIDE)

    return corridor, usable





def clone_room(room: Room) -> Room:
    return Room(
        key=room.key,
        label=room.label,
        target_area=room.target_area,
        zone=room.zone,
        rect=room.rect,
        color=room.color,
        needs_corridor=room.needs_corridor,
        preferred_aspect=room.preferred_aspect,
    )


def split_rooms_into_rect(zone: Rect, rooms: List[Room]):
    if not rooms:
        return
    ordered = order_rooms_for_strip(list(rooms))
    rects = split_rect_by_targets(zone, ordered)
    for room, rect in zip(ordered, rects):
        room.rect = rect.inset(0.0)


def rect_center_distance(a: Rect, b: Rect) -> float:
    return math.hypot(a.cx - b.cx, a.cy - b.cy)


def build_wing_shape(shape_mode: str, rooms: List[Room]):
    global HOUSE_WIDTH, HOUSE_DEPTH
    HOUSE_WIDTH, HOUSE_DEPTH = estimate_footprint(rooms)
    margin = WALL_THICKNESS * 0.5
    ux, uy = margin, margin
    uw, ud = HOUSE_WIDTH - 2 * margin, HOUSE_DEPTH - 2 * margin
    mode = (shape_mode or "quad").lower()

    room_by_key = {r.key: r for r in rooms}
    living = room_by_key["living"]
    kitchen = room_by_key["kitchen"]
    dining = room_by_key.get("dining")
    private_rooms = [r for r in rooms if r.key.startswith("bed_")]
    service_rooms = [r for r in rooms if r not in [living, kitchen, dining] and not r.key.startswith("bed_")]

    def half_split(items):
        items = list(order_rooms_for_strip(items))
        total = sum(r.target_area for r in items)
        acc = 0.0
        left = []
        right = []
        for r in items:
            if acc < total * 0.5:
                left.append(r)
                acc += r.target_area
            else:
                right.append(r)
        if not left and right:
            left.append(right.pop(0))
        if not right and len(left) > 1:
            right.append(left.pop())
        return left, right

    open_void = None

    if mode == "l":
        wing_w = clamp(uw * random.uniform(0.36, 0.48), MIN_ROOM_SIDE * 1.8, uw - MIN_ROOM_SIDE * 2.0)
        wing_h = clamp(ud * random.uniform(0.34, 0.46), MIN_ROOM_SIDE * 1.8, ud - MIN_ROOM_SIDE * 2.0)
        cut = random.choice(["NE", "NW", "SE", "SW"])
        if cut == "NE":
            support_zone = Rect(ux, uy, wing_w, ud)
            social_zone = Rect(ux + wing_w, uy, uw - wing_w, wing_h)
            corridor = Rect(ux + wing_w - CORRIDOR_WIDTH, uy + wing_h - CORRIDOR_WIDTH, CORRIDOR_WIDTH, CORRIDOR_WIDTH)
        elif cut == "NW":
            support_zone = Rect(ux + uw - wing_w, uy, wing_w, ud)
            social_zone = Rect(ux, uy, uw - wing_w, wing_h)
            corridor = Rect(ux + uw - wing_w, uy + wing_h - CORRIDOR_WIDTH, CORRIDOR_WIDTH, CORRIDOR_WIDTH)
        elif cut == "SE":
            support_zone = Rect(ux, uy, wing_w, ud)
            social_zone = Rect(ux + wing_w, uy + ud - wing_h, uw - wing_w, wing_h)
            corridor = Rect(ux + wing_w - CORRIDOR_WIDTH, uy + ud - wing_h, CORRIDOR_WIDTH, CORRIDOR_WIDTH)
        else:
            support_zone = Rect(ux + uw - wing_w, uy, wing_w, ud)
            social_zone = Rect(ux, uy + ud - wing_h, uw - wing_w, wing_h)
            corridor = Rect(ux + uw - wing_w, uy + ud - wing_h, CORRIDOR_WIDTH, CORRIDOR_WIDTH)
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(social_zone, social_rooms)
        split_rooms_into_rect(support_zone, private_rooms + service_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    if mode == "u":
        side_w = clamp(uw * random.uniform(0.26, 0.33), MIN_ROOM_SIDE * 1.4, uw * 0.38)
        bar_h = clamp(ud * random.uniform(0.28, 0.36), MIN_ROOM_SIDE * 1.6, ud * 0.44)
        left = Rect(ux, uy, side_w, ud)
        right = Rect(ux + uw - side_w, uy, side_w, ud)
        bottom = Rect(ux + side_w, uy, uw - 2 * side_w, bar_h)
        corridor = Rect(bottom.x, bottom.y + max(0.0, bottom.h - CORRIDOR_WIDTH), bottom.w, CORRIDOR_WIDTH)
        social_body = Rect(bottom.x, bottom.y, bottom.w, max(bottom.h - CORRIDOR_WIDTH, MIN_ROOM_SIDE))
        open_void = Rect(bottom.x, uy + bar_h, bottom.w, ud - bar_h)
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(social_body, social_rooms)
        left_rooms, right_rooms = half_split(private_rooms + service_rooms)
        split_rooms_into_rect(left, left_rooms)
        split_rooms_into_rect(right, right_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    if mode == "courtyard":
        band = clamp(min(uw, ud) * random.uniform(0.22, 0.28), MIN_ROOM_SIDE * 1.3, min(uw, ud) * 0.32)
        bottom = Rect(ux, uy, uw, band)
        top = Rect(ux, uy + ud - band, uw, band)
        left = Rect(ux, uy + band, band, max(ud - 2 * band, MIN_ROOM_SIDE))
        right = Rect(ux + uw - band, uy + band, band, max(ud - 2 * band, MIN_ROOM_SIDE))
        corridor = Rect(bottom.x + band, bottom.y + max(0.0, bottom.h - CORRIDOR_WIDTH), max(bottom.w - 2 * band, CORRIDOR_WIDTH), CORRIDOR_WIDTH)
        social_body = Rect(bottom.x, bottom.y, bottom.w, max(bottom.h - CORRIDOR_WIDTH, MIN_ROOM_SIDE))
        open_void = Rect(ux + band, uy + band, uw - 2 * band, ud - 2 * band)
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(social_body, social_rooms)
        top_private = private_rooms[:max(1, len(private_rooms)//2)]
        rest_private = private_rooms[len(top_private):]
        split_rooms_into_rect(top, top_private + service_rooms[:1])
        left_rooms, right_rooms = half_split(rest_private + service_rooms[1:])
        split_rooms_into_rect(left, left_rooms)
        split_rooms_into_rect(right, right_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    if mode == "h":
        side_w = clamp(uw * random.uniform(0.25, 0.31), MIN_ROOM_SIDE * 1.4, uw * 0.35)
        bridge_h = clamp(ud * random.uniform(0.22, 0.30), MIN_ROOM_SIDE * 1.4, ud * 0.34)
        bridge_y = uy + (ud - bridge_h) * 0.5
        left = Rect(ux, uy, side_w, ud)
        right = Rect(ux + uw - side_w, uy, side_w, ud)
        bridge = Rect(ux + side_w, bridge_y, uw - 2 * side_w, bridge_h)
        corridor = Rect(bridge.x, bridge.y + (bridge.h - CORRIDOR_WIDTH) * 0.5, bridge.w, CORRIDOR_WIDTH)
        social_body = Rect(bridge.x, bridge.y, bridge.w, max(bridge.h - CORRIDOR_WIDTH * 0.2, MIN_ROOM_SIDE))
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(social_body, social_rooms)
        left_rooms, right_rooms = half_split(private_rooms + service_rooms)
        split_rooms_into_rect(left, left_rooms)
        split_rooms_into_rect(right, right_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    if mode == "t":
        bar_h = clamp(ud * random.uniform(0.32, 0.40), MIN_ROOM_SIDE * 1.8, ud * 0.48)
        stem_w = clamp(uw * random.uniform(0.30, 0.40), MIN_ROOM_SIDE * 1.6, uw * 0.48)
        stem_x = ux + (uw - stem_w) * 0.5
        top = Rect(ux, uy + ud - bar_h, uw, bar_h)
        stem = Rect(stem_x, uy, stem_w, ud - bar_h)
        corridor = Rect(stem.x, stem.y, stem.w, max(stem.h * 0.65, CORRIDOR_WIDTH))
        stem_private = Rect(stem.x, corridor.y2, stem.w, max(stem.h - corridor.h, MIN_ROOM_SIDE)) if stem.h - corridor.h > MIN_ROOM_SIDE else stem
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(top, social_rooms + private_rooms[:1])
        split_rooms_into_rect(stem_private, private_rooms[1:] + service_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    if mode == "offset":
        top_w = clamp(uw * random.uniform(0.58, 0.72), MIN_ROOM_SIDE * 3.0, uw * 0.82)
        bottom_w = clamp(uw * random.uniform(0.58, 0.72), MIN_ROOM_SIDE * 3.0, uw * 0.82)
        top_h = clamp(ud * random.uniform(0.34, 0.42), MIN_ROOM_SIDE * 1.8, ud * 0.48)
        bottom_h = clamp(ud * random.uniform(0.34, 0.42), MIN_ROOM_SIDE * 1.8, ud * 0.48)
        top = Rect(ux + uw - top_w, uy + ud - top_h, top_w, top_h)
        bottom = Rect(ux, uy, bottom_w, bottom_h)
        connector = Rect(ux + max(0.0, bottom_w - CORRIDOR_WIDTH), uy + bottom_h, CORRIDOR_WIDTH, max(top.y - (uy + bottom_h), MIN_ROOM_SIDE))
        corridor = connector
        social_rooms = [r for r in [living, kitchen, dining] if r is not None]
        split_rooms_into_rect(bottom, social_rooms)
        split_rooms_into_rect(top, private_rooms + service_rooms)
        return corridor, Rect(ux, uy, uw, ud), open_void

    return layout_floorplan_quad(rooms) + (None,)


def layout_floorplan(rooms: List[Room]):
    mode = (SHAPE_MODE or "quad").lower()
    if mode == "quad":
        corridor, usable = layout_floorplan_quad(rooms)
        return corridor, usable, None
    return build_wing_shape(mode, rooms)


def subtract_intervals(base_start: float, base_end: float, openings: List[Opening]):
    ops = [o for o in openings if o.end - o.start > EPS]
    ops.sort(key=lambda o: o.start)
    parts = []
    cur = base_start
    for o in ops:
        if o.start > cur + EPS:
            parts.append((cur, min(o.start, base_end)))
        cur = max(cur, o.end)
    if cur < base_end - EPS:
        parts.append((cur, base_end))
    return [(s, e) for s, e in parts if e - s > EPS]


def add_wall_segment(col, name, orientation, fixed, start, end, z0, height, thickness, mat):
    length = end - start
    if length <= EPS:
        return
    if MODULAR_TILES_ENABLED:
        # Keep all tiles within the current wall strip the same length.
        # This avoids a tiny remainder tile near openings that tends to create
        # visual overlaps / z-fighting with the neighboring strip.
        parts = _split_length_into_tiles(length, WALL_TILE_WIDTH, keep_uniform=True)
        axis_start = start
        for idx, (offset, tile_len) in enumerate(parts):
            center = axis_start + offset
            if orientation == "H":
                add_box(col, f"{name}_tile_{idx}", center, fixed, z0 + height * 0.5, tile_len, thickness, height, mat)
            else:
                add_box(col, f"{name}_tile_{idx}", fixed, center, z0 + height * 0.5, thickness, tile_len, height, mat)
        return
    if orientation == "H":
        add_box(col, name, (start + end) * 0.5, fixed, z0 + height * 0.5, length, thickness, height, mat)
    else:
        add_box(col, name, fixed, (start + end) * 0.5, z0 + height * 0.5, thickness, length, height, mat)


def add_wall_with_openings(col, name, orientation, fixed, start, end, z0, height, thickness, openings, mat):
    clean_openings = []
    for op in openings:
        s = max(start, op.start)
        e = min(end, op.end)
        oz0 = max(z0, op.z0)
        oz1 = min(z0 + height, op.z1)
        if e - s > EPS and oz1 - oz0 > EPS:
            clean_openings.append(Opening(s, e, oz0, oz1))

    if MODULAR_TILES_ENABLED and clean_openings:
        unit = _modular_unit()
        snapped_openings = []
        for op in clean_openings:
            snapped = _snap_opening_to_module(start, end, op, unit)
            if snapped is not None:
                snapped_openings.append(snapped)
        clean_openings = prune_overlapping_openings(snapped_openings)

    cuts = [start, end]
    for op in clean_openings:
        cuts.extend([op.start, op.end])
    cuts = sorted(set(round(v, 6) for v in cuts))

    for i in range(len(cuts) - 1):
        s = cuts[i]
        e = cuts[i + 1]
        if e - s <= EPS:
            continue
        mid = (s + e) * 0.5
        covering = [op for op in clean_openings if op.start <= mid + EPS and op.end >= mid - EPS]
        if not covering:
            add_wall_segment(col, f"{name}_seg_{i}", orientation, fixed, s, e, z0, height, thickness, mat)
            continue

        covering.sort(key=lambda op: op.z0)
        cursor = z0
        part_idx = 0
        for op in covering:
            if op.z0 > cursor + EPS:
                add_wall_segment(col, f"{name}_part_{i}_{part_idx}", orientation, fixed, s, e, cursor, op.z0 - cursor, thickness, mat)
                part_idx += 1
            cursor = max(cursor, op.z1)
        if z0 + height > cursor + EPS:
            add_wall_segment(col, f"{name}_part_{i}_{part_idx}", orientation, fixed, s, e, cursor, z0 + height - cursor, thickness, mat)


def add_entry_door_leaf(col, name, orientation, fixed, center, z0, width, height, wall_thickness, mat):
    door_z = z0 + height * 0.5
    slab_h = max(0.1, height)
    if orientation == "H":
        cx = center
        cy = fixed + (wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5 if fixed < HOUSE_DEPTH * 0.5 else -(wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5))
        add_box(col, name, cx, cy, door_z, width, ENTRY_DOOR_THICKNESS, slab_h, mat)
    else:
        cx = fixed + (wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5 if fixed < HOUSE_WIDTH * 0.5 else -(wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5))
        cy = center
        add_box(col, name, cx, cy, door_z, ENTRY_DOOR_THICKNESS, width, slab_h, mat)

def shared_wall(a: Rect, b: Rect):
    if almost(a.x2, b.x):
        iv = overlap(a.y, a.y2, b.y, b.y2)
        if iv:
            return ("V", a.x2, iv[0], iv[1])
    if almost(b.x2, a.x):
        iv = overlap(a.y, a.y2, b.y, b.y2)
        if iv:
            return ("V", a.x, iv[0], iv[1])
    if almost(a.y2, b.y):
        iv = overlap(a.x, a.x2, b.x, b.x2)
        if iv:
            return ("H", a.y2, iv[0], iv[1])
    if almost(b.y2, a.y):
        iv = overlap(a.x, a.x2, b.x, b.x2)
        if iv:
            return ("H", a.y, iv[0], iv[1])
    return None

def rect_aspect(rect: Rect) -> float:
    return max(rect.w / max(rect.h, EPS), rect.h / max(rect.w, EPS))


def is_tiny_sliver(rect: Rect) -> bool:
    min_side = min(rect.w, rect.h)
    max_side = max(rect.w, rect.h)
    aspect = rect_aspect(rect)
    side_ratio = min_side / max(max_side, EPS)

    hard_sliver = (
        aspect >= POST_MERGE_HARD_MAX_ASPECT
        or side_ratio <= POST_MERGE_SLIVER_RATIO
        or (rect.area <= POST_MERGE_MIN_AREA * 1.6 and aspect >= POST_MERGE_MAX_ASPECT)
    )
    soft_sliver = (
        min_side < POST_MERGE_MIN_SIDE
        or rect.area < POST_MERGE_MIN_AREA
        or aspect > POST_MERGE_MAX_ASPECT
    )
    return hard_sliver or soft_sliver


def touches_outer_wall(rect: Rect) -> bool:
    tol = STRICT_EDGE_TOL
    return (
        abs(rect.x - WALL_THICKNESS * 0.5) <= tol
        or abs(rect.y - WALL_THICKNESS * 0.5) <= tol
        or abs(rect.x2 - (HOUSE_WIDTH - WALL_THICKNESS * 0.5)) <= tol
        or abs(rect.y2 - (HOUSE_DEPTH - WALL_THICKNESS * 0.5)) <= tol
    )


def is_outer_edge_strip(rect: Rect) -> bool:
    min_side = min(rect.w, rect.h)
    max_side = max(rect.w, rect.h)
    if not touches_outer_wall(rect):
        return False
    return min_side <= POST_MERGE_EDGE_STRIP_SIDE and (max_side / max(min_side, EPS)) >= 2.2


def rect_union_if_rectangular(a: Rect, b: Rect) -> Optional[Rect]:
    sw = shared_wall(a, b)
    if not sw:
        return None
    min_x = min(a.x, b.x)
    min_y = min(a.y, b.y)
    max_x = max(a.x2, b.x2)
    max_y = max(a.y2, b.y2)
    union = Rect(min_x, min_y, max_x - min_x, max_y - min_y)
    if abs(union.area - (a.area + b.area)) > 1e-4:
        return None
    return union


def post_validate_and_merge_rooms(rooms: List[Room], corridor: Rect) -> List[Room]:
    rooms = list(rooms)
    changed = True
    max_passes = 12

    for _ in range(max_passes):
        if not changed:
            break
        changed = False

        tiny_rooms = sorted(
            [
                r for r in rooms
                if r.rect and (is_tiny_sliver(r.rect) or is_outer_edge_strip(r.rect))
            ],
            key=lambda r: (
                0 if is_outer_edge_strip(r.rect) else 1,
                r.rect.area,
                min(r.rect.w, r.rect.h),
                -rect_aspect(r.rect),
            )
        )
        if not tiny_rooms:
            break

        for room in tiny_rooms:
            if room not in rooms or not room.rect:
                continue

            candidates = []
            for other in rooms:
                if other is room or not other.rect:
                    continue
                sw = shared_wall(room.rect, other.rect)
                if not sw:
                    continue
                shared_len = sw[3] - sw[2]
                if shared_len < POST_MERGE_MIN_SHARED:
                    continue
                merged = rect_union_if_rectangular(room.rect, other.rect)
                if not merged:
                    continue
                score = shared_len * 10.0 + other.rect.area
                if not is_tiny_sliver(other.rect):
                    score += 25.0
                if not is_outer_edge_strip(other.rect):
                    score += 6.0
                if other.zone == room.zone:
                    score += 8.0
                if other.key == 'living':
                    score += 3.0
                if touches_outer_wall(room.rect) and touches_outer_wall(other.rect):
                    score += 5.0
                if rect_aspect(merged) <= max(POST_MERGE_MAX_ASPECT, rect_aspect(other.rect) + 0.75):
                    score += 10.0
                candidates.append((score, other, merged))

            if not candidates:
                continue

            candidates.sort(key=lambda x: x[0], reverse=True)
            _, target, merged = candidates[0]
            target.rect = merged
            rooms.remove(room)
            changed = True
            break

    return rooms



def rect_contains(outer: Rect, inner: Rect) -> bool:
    return (
        inner.x >= outer.x - EPS and inner.y >= outer.y - EPS
        and inner.x2 <= outer.x2 + EPS and inner.y2 <= outer.y2 + EPS
    )


def rect_intersection(a: Rect, b: Rect) -> Optional[Rect]:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    if x2 - x1 <= EPS or y2 - y1 <= EPS:
        return None
    return Rect(x1, y1, x2 - x1, y2 - y1)


def collect_residual_rects(usable: Rect, rooms: List[Room], corridor: Rect) -> List[Rect]:
    rects = [r.rect for r in rooms if r.rect] + [corridor]
    xs = {usable.x, usable.x2}
    ys = {usable.y, usable.y2}
    for r in rects:
        xs.update([r.x, r.x2])
        ys.update([r.y, r.y2])
    xs = sorted(xs)
    ys = sorted(ys)

    cells = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cell = Rect(xs[i], ys[j], xs[i+1] - xs[i], ys[j+1] - ys[j])
            if cell.area <= EPS:
                continue
            covered = any(rect_contains(r, cell) for r in rects)
            if not covered and rect_contains(usable, cell):
                cells.append(cell)

    # Merge residual cells greedily into bigger rectangles.
    changed = True
    while changed:
        changed = False
        used = [False] * len(cells)
        merged = []
        for i, a in enumerate(cells):
            if used[i]:
                continue
            cur = a
            local_changed = True
            while local_changed:
                local_changed = False
                for j, b in enumerate(cells):
                    if i == j or used[j]:
                        continue
                    u = rect_union_if_rectangular(cur, b)
                    if u and abs((cur.area + b.area) - u.area) <= 1e-4:
                        cur = u
                        used[j] = True
                        local_changed = True
                        changed = True
            used[i] = True
            if cur.area >= RESIDUAL_MIN_AREA:
                merged.append(cur)
        cells = merged
    return cells


def merge_room_into_corridor(room: Room, corridor: Rect) -> Optional[Rect]:
    if not room.rect:
        return None
    return rect_union_if_rectangular(room.rect, corridor)


def best_neighbor_for_residual(residual: Rect, rooms: List[Room], corridor: Rect):
    candidates = []
    c_sw = shared_wall(residual, corridor)
    if c_sw:
        shared_len = c_sw[3] - c_sw[2]
        merged = rect_union_if_rectangular(residual, corridor)
        if merged:
            score = shared_len * 10.0 + RESIDUAL_CORRIDOR_SHARED_BONUS
            if min(residual.w, residual.h) <= RESIDUAL_SHORT_SIDE:
                score += 8.0
            if rect_aspect(residual) >= RESIDUAL_LONG_STRIP_RATIO:
                score += 8.0
            candidates.append((score, "corridor", None, merged))

    for room in rooms:
        if not room.rect:
            continue
        sw = shared_wall(residual, room.rect)
        if not sw:
            continue
        shared_len = sw[3] - sw[2]
        merged = rect_union_if_rectangular(residual, room.rect)
        if not merged:
            continue
        score = shared_len * 10.0 + room.rect.area
        if room.zone == "social":
            score += 1.5
        if room.zone == "private":
            score += 1.0
        if rect_aspect(merged) <= max(POST_MERGE_MAX_ASPECT, rect_aspect(room.rect) + 1.2):
            score += 8.0
        candidates.append((score, "room", room, merged))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def resolve_residual_spaces(rooms: List[Room], corridor: Rect, usable: Rect):
    residuals = collect_residual_rects(usable, rooms, corridor)
    if not residuals:
        return rooms, corridor

    made_progress = True
    passes = 0
    while made_progress and passes < 6:
        made_progress = False
        passes += 1
        residuals = collect_residual_rects(usable, rooms, corridor)
        if not residuals:
            break
        residuals.sort(key=lambda r: (0 if min(r.w, r.h) <= RESIDUAL_SHORT_SIDE else 1, -rect_aspect(r), -r.area))
        for residual in residuals:
            choice = best_neighbor_for_residual(residual, rooms, corridor)
            if not choice:
                continue
            _, kind, room, merged = choice
            if kind == "corridor":
                corridor = merged
            else:
                room.rect = merged
            made_progress = True
            break

    # Very last fallback: convert any leftover acceptable rectangle into storage.
    residuals = collect_residual_rects(usable, rooms, corridor)
    idx = 1
    for residual in residuals:
        if residual.area < 1.5 or min(residual.w, residual.h) < 0.9:
            continue
        rooms.append(Room(
            key=f"residual_{idx}",
            label="Storage",
            target_area=residual.area,
            zone="service",
            rect=residual,
            color=room_color("service"),
            preferred_aspect=1.0,
        ))
        idx += 1
    return rooms, corridor



def make_window_opening(start: float, end: float, sill: float = WINDOW_SILL_HEIGHT, height: float = WINDOW_HEIGHT):
    return Opening(start, end, sill, sill + height)


def quantize_window_width(desired: float, span: float) -> float:
    available = span - WINDOW_END_MARGIN * 2
    if available < 1.0 - EPS:
        return 0.0
    max_modules = max(1, int(math.floor(available + EPS)))
    width = int(round(desired))
    width = max(1, min(width, max_modules))
    return float(width)


def outer_window_openings_for_room(room: Room, ori: str, fixed: float, start: float, end: float):
    ops = []
    edge_tol = max(WALL_THICKNESS * 0.75, 0.22)
    inner_min_x = WALL_THICKNESS * 0.5
    inner_min_y = WALL_THICKNESS * 0.5
    inner_max_x = HOUSE_WIDTH - WALL_THICKNESS * 0.5
    inner_max_y = HOUSE_DEPTH - WALL_THICKNESS * 0.5

    def near(a: float, b: float) -> bool:
        return abs(a - b) <= edge_tol

    def horizontal_window_for_span(a0: float, a1: float, zone: str):
        span = a1 - a0
        if span < WINDOW_MIN_WIDTH + WINDOW_END_MARGIN * 2:
            return []
        if zone in ("bathroom", "storage", "laundry", "pantry"):
            w = quantize_window_width(min(WINDOW_STRIP_WIDTH, max(WINDOW_MIN_WIDTH, span * 0.28)), span)
            if w < 1.0 - EPS:
                return []
            c = (a0 + a1) * 0.5
            return [make_window_opening(c - w * 0.5, c + w * 0.5, 1.15, 0.75)]
        if zone == "living":
            w = quantize_window_width(max(WINDOW_MIN_WIDTH, span * 0.58), span)
            if w < 1.0 - EPS:
                return []
            c = (a0 + a1) * 0.5
            return [make_window_opening(c - w * 0.5, c + w * 0.5, 0.65, 1.65)]
        if zone == "kitchen":
            w = quantize_window_width(max(WINDOW_MIN_WIDTH, span * 0.42), span)
            if w < 1.0 - EPS:
                return []
            c = (a0 + a1) * 0.5
            return [make_window_opening(c - w * 0.5, c + w * 0.5, 1.0, 1.05)]
        w = quantize_window_width(max(WINDOW_MIN_WIDTH, span * 0.45), span)
        if w < 1.0 - EPS:
            return []
        c = (a0 + a1) * 0.5
        return [make_window_opening(c - w * 0.5, c + w * 0.5, 0.8, 1.35)]

    if room.rect is None:
        return ops

    if ori == "H":
        if almost(fixed, 0.0):
            if room.rect.y <= inner_min_y + edge_tol or near(room.rect.y, inner_min_y):
                span0 = max(start, room.rect.x + WINDOW_END_MARGIN)
                span1 = min(end, room.rect.x2 - WINDOW_END_MARGIN)
                ops.extend(horizontal_window_for_span(span0, span1, room.key))
        elif almost(fixed, HOUSE_DEPTH):
            if room.rect.y2 >= inner_max_y - edge_tol or near(room.rect.y2, inner_max_y):
                span0 = max(start, room.rect.x + WINDOW_END_MARGIN)
                span1 = min(end, room.rect.x2 - WINDOW_END_MARGIN)
                ops.extend(horizontal_window_for_span(span0, span1, room.key))
    else:
        if almost(fixed, 0.0):
            if room.rect.x <= inner_min_x + edge_tol or near(room.rect.x, inner_min_x):
                span0 = max(start, room.rect.y + WINDOW_END_MARGIN)
                span1 = min(end, room.rect.y2 - WINDOW_END_MARGIN)
                ops.extend(horizontal_window_for_span(span0, span1, room.key))
        elif almost(fixed, HOUSE_WIDTH):
            if room.rect.x2 >= inner_max_x - edge_tol or near(room.rect.x2, inner_max_x):
                span0 = max(start, room.rect.y + WINDOW_END_MARGIN)
                span1 = min(end, room.rect.y2 - WINDOW_END_MARGIN)
                ops.extend(horizontal_window_for_span(span0, span1, room.key))

    return ops


def prune_overlapping_openings(openings: List[Opening]):
    if not openings:
        return []
    openings = sorted(openings, key=lambda op: (op.start, op.end, op.z0, op.z1))
    out = []
    for op in openings:
        bad = False
        for ex in out:
            if overlap(op.start, op.end, ex.start, ex.end) and not (op.z1 <= ex.z0 + EPS or ex.z1 <= op.z0 + EPS):
                bad = True
                break
        if not bad:
            out.append(op)
    return out








def offset_openings(openings: List[Opening], z_offset: float) -> List[Opening]:
    if abs(z_offset) <= EPS:
        return list(openings)
    return [Opening(op.start, op.end, op.z0 + z_offset, op.z1 + z_offset) for op in openings]


def classify_room_kind(room: Room) -> str:
    if room.key.startswith("bath"):
        return "bathroom"
    if room.key.startswith("bed"):
        return "bedroom"
    if room.key.startswith("residual_") or room.key == "storage":
        return "storage"
    return room.key


def stair_dims():
    risers = max(12, int(round(WALL_HEIGHT / STAIR_RISER)))
    risers_first = risers // 2
    risers_second = risers - risers_first
    run1 = risers_first * STAIR_TREAD
    run2 = risers_second * STAIR_TREAD
    long_dim = max(run1, run2) + STAIR_LANDING + STAIR_CLEARANCE * 2.0
    short_dim = STAIR_WIDTH * 2.0 + STAIR_CLEARANCE * 2.0
    return short_dim, long_dim, risers_first, risers_second


def stair_candidate_rect(parent: Rect, orientation: str, corner: str) -> Rect:
    short_dim, long_dim, _, _ = stair_dims()
    if orientation == "X":
        w, h = long_dim, short_dim
    else:
        w, h = short_dim, long_dim

    if corner == "SW":
        return Rect(parent.x, parent.y, w, h)
    if corner == "SE":
        return Rect(parent.x2 - w, parent.y, w, h)
    if corner == "NW":
        return Rect(parent.x, parent.y2 - h, w, h)
    return Rect(parent.x2 - w, parent.y2 - h, w, h)


def candidate_touches_exterior(candidate: Rect):
    sides = []
    if almost(candidate.x, WALL_THICKNESS * 0.5):
        sides.append(("V", 0.0, candidate.y, candidate.y2))
    if almost(candidate.x2, HOUSE_WIDTH - WALL_THICKNESS * 0.5):
        sides.append(("V", HOUSE_WIDTH, candidate.y, candidate.y2))
    if almost(candidate.y, WALL_THICKNESS * 0.5):
        sides.append(("H", 0.0, candidate.x, candidate.x2))
    if almost(candidate.y2, HOUSE_DEPTH - WALL_THICKNESS * 0.5):
        sides.append(("H", HOUSE_DEPTH, candidate.x, candidate.x2))
    return sides


def candidate_window_or_entrance_conflict(parent: Room, candidate: Rect) -> bool:
    room_kind = classify_room_kind(parent)
    for ori, fixed, start, end in candidate_touches_exterior(candidate):
        ops = []
        temp_room = Room(parent.key, parent.label, parent.target_area, parent.zone, rect=parent.rect)
        temp_room.key = room_kind
        ops.extend(outer_window_openings_for_room(temp_room, ori, fixed, start, end))
        if ori == "H" and almost(fixed, 0.0):
            entrance = Opening(HOUSE_WIDTH * 0.5 - 0.6, HOUSE_WIDTH * 0.5 + 0.6, 0.0, DOOR_HEIGHT)
            iv = overlap(start, end, entrance.start - STAIR_WINDOW_CLEARANCE, entrance.end + STAIR_WINDOW_CLEARANCE)
            if iv:
                return True
        for op in ops:
            iv = overlap(start, end, op.start - STAIR_WINDOW_CLEARANCE, op.end + STAIR_WINDOW_CLEARANCE)
            if iv:
                return True
    return False


def opening_intervals_on_shared_wall(a: Rect, b: Rect, ori: str, fixed: float):
    sw = shared_wall(a, b)
    if not sw or sw[0] != ori or not almost(sw[1], fixed):
        return []
    iv = (sw[2], sw[3])
    if iv[1] - iv[0] <= EPS:
        return []
    mid = (iv[0] + iv[1]) * 0.5
    half = min(DOOR_WIDTH * 0.5, (iv[1] - iv[0]) * 0.4)
    return [(mid - half, mid + half)]


def candidate_door_conflict(parent_rect: Rect, candidate: Rect, all_rects: List[Rect]) -> bool:
    edges = []
    if almost(candidate.x, parent_rect.x):
        edges.append(("V", parent_rect.x, candidate.y, candidate.y2))
    if almost(candidate.x2, parent_rect.x2):
        edges.append(("V", parent_rect.x2, candidate.y, candidate.y2))
    if almost(candidate.y, parent_rect.y):
        edges.append(("H", parent_rect.y, candidate.x, candidate.x2))
    if almost(candidate.y2, parent_rect.y2):
        edges.append(("H", parent_rect.y2, candidate.x, candidate.x2))

    for ori, fixed, start, end in edges:
        for other in all_rects:
            if other is parent_rect:
                continue
            for ds, de in opening_intervals_on_shared_wall(parent_rect, other, ori, fixed):
                iv = overlap(start, end, ds - STAIR_DOOR_CLEARANCE, de + STAIR_DOOR_CLEARANCE)
                if iv:
                    return True
    return False


def room_stair_parent_score(room: Room, corridor: Rect) -> float:
    kind = classify_room_kind(room)
    area = room.rect.area if room.rect else 0.0
    score = area
    if kind == "living":
        score += 18.0
    elif kind == "dining":
        score += 8.0
    elif kind == "study":
        score += 5.0
    elif kind == "bedroom":
        score -= 32.0
    elif kind in {"bathroom", "laundry", "pantry", "storage", "kitchen"}:
        score -= 70.0
    if room.rect:
        sw = shared_wall(room.rect, corridor)
        if sw:
            score += 34.0
        if touches_outer_wall(room.rect):
            score -= 10.0
        if min(room.rect.w, room.rect.h) >= 3.2:
            score += 3.0
    return score


def corridor_stair_parent_score(corridor: Rect) -> float:
    score = corridor.area + 58.0
    if min(corridor.w, corridor.h) >= 2.2:
        score += 16.0
    if max(corridor.w, corridor.h) >= 5.5:
        score += 8.0
    return score


def stair_core_spine_distance(cand: Rect, corridor: Rect) -> float:
    return abs(cand.cx - corridor.cx) + abs(cand.cy - corridor.cy)


def candidate_interior_wall_bonus(parent_rect: Rect, cand: Rect) -> float:
    bonus = 0.0
    if almost(cand.x, parent_rect.x) or almost(cand.x2, parent_rect.x2):
        bonus += 7.0
    if almost(cand.y, parent_rect.y) or almost(cand.y2, parent_rect.y2):
        bonus += 7.0
    return bonus


def candidate_center_cut_penalty(parent_rect: Rect, cand: Rect) -> float:
    px = min(abs(cand.cx - parent_rect.x), abs(parent_rect.x2 - cand.cx))
    py = min(abs(cand.cy - parent_rect.y), abs(parent_rect.y2 - cand.cy))
    d = min(px, py)
    return max(0.0, d - 0.65) * 8.0


def candidate_remaining_bands(parent_rect: Rect, cand: Rect):
    return {
        "left": max(0.0, cand.x - parent_rect.x),
        "right": max(0.0, parent_rect.x2 - cand.x2),
        "bottom": max(0.0, cand.y - parent_rect.y),
        "top": max(0.0, parent_rect.y2 - cand.y2),
    }


def candidate_remaining_shape_penalty(parent_rect: Rect, cand: Rect, room, corridor: Rect) -> float:
    bands = candidate_remaining_bands(parent_rect, cand)
    narrow = sum(1 for v in bands.values() if 0.0 < v < 1.0)
    penalty = narrow * 10.0

    if room is None:
        travel = max(bands["left"] + bands["right"], bands["top"] + bands["bottom"])
        if travel < 1.15:
            penalty += 40.0
        if min(parent_rect.w, parent_rect.h) <= 2.0 and min(bands.values()) < 0.55:
            penalty += 18.0
    else:
        kind = classify_room_kind(room)
        if kind == "living":
            if 0.9 < bands["left"] and 0.9 < bands["right"]:
                penalty += 28.0
            if 0.9 < bands["top"] and 0.9 < bands["bottom"]:
                penalty += 28.0
        if touches_outer_wall(parent_rect):
            for side_val in bands.values():
                if side_val > 0:
                    penalty += 1.0
    return penalty


def stair_score_for_candidate(parent_key, parent_label, parent_rect, room, corridor, cand, orientation, corner):
    base_parent_score = corridor_stair_parent_score(parent_rect) if room is None else room_stair_parent_score(room, corridor)
    occ = cand.area / max(parent_rect.area, EPS)
    score = base_parent_score

    if room is None:
        score += 42.0
    else:
        kind = classify_room_kind(room)
        if shared_wall(room.rect, corridor):
            score += 22.0
        if kind == "living":
            score += 6.0

    score += candidate_interior_wall_bonus(parent_rect, cand)
    score -= candidate_center_cut_penalty(parent_rect, cand)

    score -= stair_core_spine_distance(cand, corridor) * (4.2 if room is None else 2.0)

    if orientation == "Y" and parent_rect.h >= parent_rect.w:
        score += 10.0
    elif orientation == "X" and parent_rect.w > parent_rect.h:
        score += 10.0
    else:
        score += 2.0

    score += (1.0 - occ) * 24.0
    score -= candidate_remaining_shape_penalty(parent_rect, cand, room, corridor)

    exterior_contacts = len(candidate_touches_exterior(cand))
    score -= exterior_contacts * (10.0 if room is None else 8.0)
    if almost(cand.y, WALL_THICKNESS * 0.5) and overlap(cand.x, cand.x2, HOUSE_WIDTH * 0.5 - 1.0, HOUSE_WIDTH * 0.5 + 1.0):
        score -= 24.0
    if almost(cand.x, WALL_THICKNESS * 0.5) or almost(cand.x2, HOUSE_WIDTH - WALL_THICKNESS * 0.5):
        score -= 12.0
    if almost(cand.y2, HOUSE_DEPTH - WALL_THICKNESS * 0.5):
        score -= 8.0

    if corner in ("NW", "NE", "SW", "SE"):
        score += 3.0

    return score



def choose_stair_placement(rooms: List[Room], corridor: Rect) -> Optional[StairPlacement]:
    short_dim, long_dim, _, _ = stair_dims()
    parent_spaces = [("corridor", "Corridor", corridor, None)] + [(r.key, r.label, r.rect, r) for r in rooms if r.rect]
    all_rects = [r.rect for r in rooms if r.rect] + [corridor]

    def collect(stage: str):
        candidates = []
        for parent_key, parent_label, parent_rect, room in parent_spaces:
            if parent_rect is None:
                continue

            min_free_area = STAIR_MIN_FREE_AREA if stage == "strict" else (5.0 if stage == "relaxed" else 3.0)
            max_occupancy = (0.40 if room is None else STAIR_MAX_PARENT_OCCUPANCY)
            if stage == "fallback":
                max_occupancy = 0.55 if room is None else 0.48

            if parent_rect.area <= min_free_area:
                continue

            for orientation in ("X", "Y"):
                need_w = long_dim if orientation == "X" else short_dim
                need_h = short_dim if orientation == "X" else long_dim
                if parent_rect.w + EPS < need_w or parent_rect.h + EPS < need_h:
                    continue

                for corner in ("SW", "SE", "NW", "NE"):
                    cand = stair_candidate_rect(parent_rect, orientation, corner)
                    occ = cand.area / max(parent_rect.area, EPS)
                    if occ > max_occupancy:
                        continue
                    if parent_rect.area - cand.area < min_free_area:
                        continue

                    if candidate_door_conflict(parent_rect, cand, all_rects):
                        continue

                    if room is not None and stage != "fallback" and candidate_window_or_entrance_conflict(room, cand):
                        continue

                    score = stair_score_for_candidate(parent_key, parent_label, parent_rect, room, corridor, cand, orientation, corner)
                    if stage == "relaxed":
                        score -= 3.0
                    elif stage == "fallback":
                        score -= 8.0

                    candidates.append(StairPlacement(parent_key, parent_label, cand, orientation, corner, score))
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    for stage in ("strict", "relaxed", "fallback"):
        cands = collect(stage)
        if cands:
            best = cands[0]
            print(f"[FloorPlan] Stair placement stage={stage}: parent={best.parent_label}, corner={best.corner}, orientation={best.orientation}, score={best.score:.2f}")
            return best

    print("[FloorPlan] Stair placement: no valid candidate found.")
    return None



def add_stairs(col, stair: StairPlacement, z_offset=0.0):
    """
    Robust switchback stair generator.

    Instead of trying to derive geometry from corner-specific turns, this builds
    a compact U-shaped stair strictly inside stair.rect:
      - lower flight along one side of the footprint
      - full-width turning landing at the far end
      - upper flight back along the opposite side
      - top platform at the upper-flight exit

    This is intentionally simple and conservative so it does not produce
    inverted or detached pieces.
    """
    stair_mat = ensure_material("FP_Stair", (0.62, 0.62, 0.66, 1.0))
    landing_mat = ensure_material("FP_Landing", (0.68, 0.68, 0.72, 1.0))
    void_mat = ensure_material("FP_StairVoid", (0.50, 0.50, 0.54, 1.0))

    platform_thickness = 0.14
    landing_thickness = 0.16
    _, _, risers_first, risers_second = stair_dims()

    # base slab / footprint marker
    add_box(
        col,
        "StairFootprint",
        stair.rect.cx,
        stair.rect.cy,
        FLOOR_THICKNESS * 0.55 + z_offset,
        max(stair.rect.w - 0.04, 0.08),
        max(stair.rect.h - 0.04, 0.08),
        FLOOR_THICKNESS * 1.1,
        void_mat,
    )

    x0, y0 = stair.rect.x, stair.rect.y
    x1, y1 = stair.rect.x2, stair.rect.y2
    ix0 = x0 + STAIR_CLEARANCE
    ix1 = x1 - STAIR_CLEARANCE
    iy0 = y0 + STAIR_CLEARANCE
    iy1 = y1 - STAIR_CLEARANCE

    inner_w = max(ix1 - ix0, 0.8)
    inner_h = max(iy1 - iy0, 0.8)

    # Choose the long axis. We only draw two canonical variants.
    horizontal = (stair.orientation == "X") if abs(inner_w - inner_h) > 0.05 else (inner_w >= inner_h)

    def add_step(name, cx, cy, cz, sx, sy, sz):
        add_box(col, name, cx, cy, cz + z_offset, max(sx, 0.04), max(sy, 0.04), max(sz, 0.04), stair_mat)

    if horizontal:
        lane = min(STAIR_WIDTH, inner_h * 0.38)
        lane = max(lane, 0.7)
        lane = min(lane, inner_h * 0.48)
        lane_bottom_y0 = iy0
        lane_bottom_y1 = iy0 + lane
        lane_top_y1 = iy1
        lane_top_y0 = iy1 - lane

        landing_len = max(STAIR_LANDING, lane)
        landing_len = min(landing_len, inner_w * 0.35)
        platform_len = max(0.9, min(STAIR_WIDTH, inner_w * 0.28))

        x_turn0 = ix1 - landing_len
        x_turn1 = ix1
        lower_run = max(x_turn0 - ix0, 0.8)
        upper_run = max(x_turn0 - (ix0 + platform_len), 0.8)

        tread1 = lower_run / max(risers_first, 1)
        tread2 = upper_run / max(risers_second, 1)

        # lower flight: climbs east on bottom lane
        for i in range(risers_first):
            sx0 = ix0 + tread1 * i
            sx1 = sx0 + tread1
            height = (i + 1) * (WALL_HEIGHT * 0.5 / max(risers_first, 1))
            add_step(
                f"StairStepA_{i}",
                (sx0 + sx1) * 0.5,
                (lane_bottom_y0 + lane_bottom_y1) * 0.5,
                FLOOR_THICKNESS + height * 0.5,
                sx1 - sx0,
                lane_bottom_y1 - lane_bottom_y0,
                height,
            )

        # turning landing at the far end
        add_box(
            col,
            "StairLanding",
            (x_turn0 + x_turn1) * 0.5,
            (iy0 + iy1) * 0.5,
            FLOOR_THICKNESS + WALL_HEIGHT * 0.5 + z_offset,
            x_turn1 - x_turn0,
            iy1 - iy0,
            landing_thickness,
            landing_mat,
        )

        # upper flight: climbs west on top lane
        for i in range(risers_second):
            sx1 = x_turn0 - tread2 * i
            sx0 = sx1 - tread2
            height = WALL_HEIGHT * 0.5 + (i + 1) * (WALL_HEIGHT * 0.5 / max(risers_second, 1))
            add_step(
                f"StairStepB_{i}",
                (sx0 + sx1) * 0.5,
                (lane_top_y0 + lane_top_y1) * 0.5,
                FLOOR_THICKNESS + height * 0.5,
                sx1 - sx0,
                lane_top_y1 - lane_top_y0,
                height,
            )

        # top platform at the exit of the upper flight
        plat_x0 = ix0
        plat_x1 = ix0 + platform_len
        add_box(
            col,
            "StairTopPlatform",
            (plat_x0 + plat_x1) * 0.5,
            (lane_top_y0 + lane_top_y1) * 0.5,
            FLOOR_THICKNESS + WALL_HEIGHT + platform_thickness * 0.5 + z_offset,
            plat_x1 - plat_x0,
            lane_top_y1 - lane_top_y0,
            platform_thickness,
            landing_mat,
        )

    else:
        lane = min(STAIR_WIDTH, inner_w * 0.38)
        lane = max(lane, 0.7)
        lane = min(lane, inner_w * 0.48)
        lane_left_x0 = ix0
        lane_left_x1 = ix0 + lane
        lane_right_x1 = ix1
        lane_right_x0 = ix1 - lane

        landing_len = max(STAIR_LANDING, lane)
        landing_len = min(landing_len, inner_h * 0.35)
        platform_len = max(0.9, min(STAIR_WIDTH, inner_h * 0.28))

        y_turn0 = iy1 - landing_len
        y_turn1 = iy1
        lower_run = max(y_turn0 - iy0, 0.8)
        upper_run = max(y_turn0 - (iy0 + platform_len), 0.8)

        tread1 = lower_run / max(risers_first, 1)
        tread2 = upper_run / max(risers_second, 1)

        # lower flight: climbs north on left lane
        for i in range(risers_first):
            sy0 = iy0 + tread1 * i
            sy1 = sy0 + tread1
            height = (i + 1) * (WALL_HEIGHT * 0.5 / max(risers_first, 1))
            add_step(
                f"StairStepA_{i}",
                (lane_left_x0 + lane_left_x1) * 0.5,
                (sy0 + sy1) * 0.5,
                FLOOR_THICKNESS + height * 0.5,
                lane_left_x1 - lane_left_x0,
                sy1 - sy0,
                height,
            )

        add_box(
            col,
            "StairLanding",
            (ix0 + ix1) * 0.5,
            (y_turn0 + y_turn1) * 0.5,
            FLOOR_THICKNESS + WALL_HEIGHT * 0.5 + z_offset,
            ix1 - ix0,
            y_turn1 - y_turn0,
            landing_thickness,
            landing_mat,
        )

        # upper flight: climbs south on right lane
        for i in range(risers_second):
            sy1 = y_turn0 - tread2 * i
            sy0 = sy1 - tread2
            height = WALL_HEIGHT * 0.5 + (i + 1) * (WALL_HEIGHT * 0.5 / max(risers_second, 1))
            add_step(
                f"StairStepB_{i}",
                (lane_right_x0 + lane_right_x1) * 0.5,
                (sy0 + sy1) * 0.5,
                FLOOR_THICKNESS + height * 0.5,
                lane_right_x1 - lane_right_x0,
                sy1 - sy0,
                height,
            )

        plat_y0 = iy0
        plat_y1 = iy0 + platform_len
        add_box(
            col,
            "StairTopPlatform",
            (lane_right_x0 + lane_right_x1) * 0.5,
            (plat_y0 + plat_y1) * 0.5,
            FLOOR_THICKNESS + WALL_HEIGHT + platform_thickness * 0.5 + z_offset,
            lane_right_x1 - lane_right_x0,
            plat_y1 - plat_y0,
            platform_thickness,
            landing_mat,
        )

    add_text(col, "Stairs → 2F", stair.rect.x + 0.12, stair.rect.cy, z_offset + 0.05, size=0.24)

def is_inner_face_of_exterior_for_rect(rect: Rect, ori: str, fixed: float) -> bool:
    # In strict mode upper floors are scaled to the 1F footprint. That scaling can leave
    # room edges a tiny bit off the ideal inner shell plane, so using EPS here is too strict
    # and causes a duplicate "skin wall" (SW_...) to be drawn behind windows.
    tol = max(STRICT_EDGE_TOL, WALL_THICKNESS * 1.1, 0.28)
    inner_x0 = WALL_THICKNESS * 0.5
    inner_y0 = WALL_THICKNESS * 0.5
    inner_x1 = HOUSE_WIDTH - WALL_THICKNESS * 0.5
    inner_y1 = HOUSE_DEPTH - WALL_THICKNESS * 0.5

    if ori == "H":
        return (
            abs(fixed - inner_y0) <= tol and abs(rect.y - inner_y0) <= tol
        ) or (
            abs(fixed - inner_y1) <= tol and abs(rect.y2 - inner_y1) <= tol
        )
    return (
        abs(fixed - inner_x0) <= tol and abs(rect.x - inner_x0) <= tol
    ) or (
        abs(fixed - inner_x1) <= tol and abs(rect.x2 - inner_x1) <= tol
    )

def opening_for_outer_entrance_on_rect(rect: Rect, ori: str, fixed: float, start: float, end: float):
    entrance_center_x = HOUSE_WIDTH * 0.5
    entrance_half = max(_modular_unit() * 0.5, 0.5)
    entrance = Opening(entrance_center_x - entrance_half, entrance_center_x + entrance_half)

    if ori != "H":
        return []
    # Interior wall just behind the exterior entrance. Use the same relaxed tolerance as the
    # outer-face detector so strict-mode scaling does not brick up the entry.
    tol = max(STRICT_EDGE_TOL, WALL_THICKNESS * 1.1, 0.28)
    if abs(fixed - WALL_THICKNESS * 0.5) > tol:
        return []
    if abs(rect.y - WALL_THICKNESS * 0.5) > tol:
        return []
    iv = overlap(start, end, entrance.start, entrance.end)
    if not iv:
        return []
    return [Opening(iv[0], iv[1], 0.0, DOOR_HEIGHT)]


def edge_openings_to_corridor(room: Rect, corridor: Rect, ori: str, fixed: float, start: float, end: float):
    ops = []
    if ori == "V":
        if almost(fixed, room.x2) and almost(room.x2, corridor.x):
            iv = overlap(start, end, max(room.y, corridor.y), min(room.y2, corridor.y2))
            if iv:
                mid = (iv[0] + iv[1]) * 0.5
                half = min(max(_modular_unit() * 0.5, DOOR_WIDTH * 0.5), (iv[1] - iv[0]) * 0.4)
                ops.append(Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT))
        if almost(fixed, room.x) and almost(room.x, corridor.x2):
            iv = overlap(start, end, max(room.y, corridor.y), min(room.y2, corridor.y2))
            if iv:
                mid = (iv[0] + iv[1]) * 0.5
                half = min(max(_modular_unit() * 0.5, DOOR_WIDTH * 0.5), (iv[1] - iv[0]) * 0.4)
                ops.append(Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT))
    else:
        if almost(fixed, room.y2) and almost(room.y2, corridor.y):
            iv = overlap(start, end, max(room.x, corridor.x), min(room.x2, corridor.x2))
            if iv:
                mid = (iv[0] + iv[1]) * 0.5
                half = min(DOOR_WIDTH * 0.5, (iv[1] - iv[0]) * 0.4)
                ops.append(Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT))
        if almost(fixed, room.y) and almost(room.y, corridor.y2):
            iv = overlap(start, end, max(room.x, corridor.x), min(room.x2, corridor.x2))
            if iv:
                mid = (iv[0] + iv[1]) * 0.5
                half = min(DOOR_WIDTH * 0.5, (iv[1] - iv[0]) * 0.4)
                ops.append(Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT))
    return ops



def rect_intersection(a: Rect, b: Rect) -> Optional[Rect]:
    ix0 = max(a.x, b.x)
    iy0 = max(a.y, b.y)
    ix1 = min(a.x2, b.x2)
    iy1 = min(a.y2, b.y2)
    if ix1 - ix0 <= EPS or iy1 - iy0 <= EPS:
        return None
    return Rect(ix0, iy0, ix1 - ix0, iy1 - iy0)


def subtract_rect(rect: Rect, hole: Optional[Rect]) -> List[Rect]:
    if hole is None:
        return [rect]
    inter = rect_intersection(rect, hole)
    if inter is None:
        return [rect]

    parts: List[Rect] = []
    if inter.x - rect.x > EPS:
        parts.append(Rect(rect.x, rect.y, inter.x - rect.x, rect.h))
    if rect.x2 - inter.x2 > EPS:
        parts.append(Rect(inter.x2, rect.y, rect.x2 - inter.x2, rect.h))
    if inter.y - rect.y > EPS:
        parts.append(Rect(inter.x, rect.y, inter.w, inter.y - rect.y))
    if rect.y2 - inter.y2 > EPS:
        parts.append(Rect(inter.x, inter.y2, inter.w, rect.y2 - inter.y2))
    return [p for p in parts if p.w > EPS and p.h > EPS]


def expand_rect(rect: Optional[Rect], margin: float) -> Optional[Rect]:
    if rect is None:
        return None
    return Rect(rect.x - margin, rect.y - margin, rect.w + margin * 2.0, rect.h + margin * 2.0)


def subtract_wall_interval_for_void(ori: str, fixed: float, start: float, end: float, void_rect: Optional[Rect]) -> List[Tuple[float, float]]:
    if void_rect is None:
        return [(start, end)]

    if ori == "H":
        if not (void_rect.y - EPS < fixed < void_rect.y2 + EPS):
            return [(start, end)]
        hole = overlap(start, end, void_rect.x, void_rect.x2)
    else:
        if not (void_rect.x - EPS < fixed < void_rect.x2 + EPS):
            return [(start, end)]
        hole = overlap(start, end, void_rect.y, void_rect.y2)

    if not hole:
        return [(start, end)]

    parts = []
    if hole[0] - start > EPS:
        parts.append((start, hole[0]))
    if end - hole[1] > EPS:
        parts.append((hole[1], end))
    return parts


def subtract_many_rects(rects: List[Rect], holes: List[Rect]) -> List[Rect]:
    parts = list(rects)
    for hole in [h for h in holes if h is not None]:
        new_parts = []
        for part in parts:
            new_parts.extend(subtract_rect(part, hole))
        parts = new_parts
    return [p for p in parts if p.w > EPS and p.h > EPS]


def boundary_segments_from_rects(items: List[Tuple[str, Optional[Room], Rect]]):
    segments = []
    rects = [it[2] for it in items]
    for idx, (kind, room, rect) in enumerate(items):
        edges = [
            ("H", rect.y, rect.x, rect.x2),
            ("H", rect.y2, rect.x, rect.x2),
            ("V", rect.x, rect.y, rect.y2),
            ("V", rect.x2, rect.y, rect.y2),
        ]
        for ori, fixed, start, end in edges:
            remaining = [(start, end)]
            for jdx, other in enumerate(rects):
                if jdx == idx:
                    continue
                sw = shared_wall(rect, other)
                if sw and sw[0] == ori and almost(sw[1], fixed):
                    new_remaining = []
                    for a, b in remaining:
                        iv = overlap(a, b, sw[2], sw[3])
                        if not iv:
                            new_remaining.append((a, b))
                        else:
                            if iv[0] - a > EPS:
                                new_remaining.append((a, iv[0]))
                            if b - iv[1] > EPS:
                                new_remaining.append((iv[1], b))
                    remaining = new_remaining
            for a, b in remaining:
                if b - a > EPS:
                    segments.append({"kind": kind, "room": room, "ori": ori, "fixed": fixed, "start": a, "end": b})
    return segments


def segment_overlap_len(seg, ori: str, fixed: float, start: float, end: float) -> float:
    if seg["ori"] != ori or not almost(seg["fixed"], fixed):
        return 0.0
    iv = overlap(seg["start"], seg["end"], start, end)
    return 0.0 if not iv else iv[1] - iv[0]


def is_boundary_edge(segments, ori: str, fixed: float, start: float, end: float) -> bool:
    return any(segment_overlap_len(seg, ori, fixed, start, end) > EPS for seg in segments)


def boundary_window_openings_for_room(room: Room, ori: str, start: float, end: float):
    span = end - start
    if span < WINDOW_MIN_WIDTH + WINDOW_END_MARGIN * 2:
        return []
    zone = room.zone
    if room.key == "living":
        width = quantize_window_width(max(2.0, span * 0.52), span)
        sill = 0.45
        height = max(1.55, WINDOW_HEIGHT + 0.2)
    elif room.key == "kitchen" or room.key == "study" or room.key.startswith("bed_") or room.key == "dining":
        width = quantize_window_width(max(1.0, span * 0.38), span)
        sill = WINDOW_SILL_HEIGHT
        height = WINDOW_HEIGHT
    elif room.key.startswith("bath") or room.key in {"laundry", "pantry", "storage"}:
        width = quantize_window_width(max(WINDOW_MIN_WIDTH, WINDOW_STRIP_WIDTH), span)
        sill = 1.35
        height = 0.72
    else:
        width = quantize_window_width(max(1.0, span * 0.33), span)
        sill = WINDOW_SILL_HEIGHT
        height = WINDOW_HEIGHT
    if width < 1.0 - EPS:
        return []
    mid = (start + end) * 0.5
    return [make_window_opening(mid - width * 0.5, mid + width * 0.5, sill, height)]


def choose_entrance_segment(boundary_segments):
    candidates = [s for s in boundary_segments if s["ori"] == "H"]
    if candidates:
        min_y = min(s["fixed"] for s in candidates)
        south = [s for s in candidates if abs(s["fixed"] - min_y) <= EPS and (s["end"] - s["start"]) >= DOOR_WIDTH + 0.5]
        if south:
            south.sort(key=lambda s: (-(s["end"] - s["start"]), abs(((s["start"] + s["end"]) * 0.5) - (HOUSE_WIDTH * 0.5))))
            return south[0]
    candidates = [s for s in boundary_segments if (s["end"] - s["start"]) >= DOOR_WIDTH + 0.5]
    if not candidates:
        return None
    candidates.sort(key=lambda s: -(s["end"] - s["start"]))
    return candidates[0]


def footprint_rects_from_layout(rooms: List[Room], corridor: Rect, open_void: Optional[Rect] = None) -> List[Rect]:
    rects = [r.rect for r in rooms if r.rect is not None] + [corridor]
    if open_void is not None:
        rects = subtract_many_rects(rects, [open_void])
    return rects


def draw_geometry(col, rooms: List[Room], corridor: Rect, stair: Optional[StairPlacement] = None, z_offset: float = 0.0, include_entrance: bool = True, inherited_void: Optional[Rect] = None, open_void: Optional[Rect] = None):
    wall_mat = ensure_material("FP_Wall", (0.90, 0.90, 0.92, 1.0))
    base_mat = ensure_material("FP_Base", (0.24, 0.24, 0.26, 1.0))
    cor_mat = ensure_material("FP_Corridor", (0.83, 0.72, 0.56, 1.0))
    entry_door_mat = ensure_material("FP_EntryDoor", (0.10, 0.10, 0.12, 1.0))

    valid_rooms = [r for r in rooms if r.rect is not None]
    void_rect = expand_rect(inherited_void, max(WALL_THICKNESS * 0.35, 0.10))

    use_legacy_quad_shell = ((SHAPE_MODE or "quad").lower() == "quad" and open_void is None)

    if use_legacy_quad_shell:
        base_rect = Rect(0.0, 0.0, HOUSE_WIDTH, HOUSE_DEPTH)
        for i, patch in enumerate(subtract_rect(base_rect, void_rect)):
            if MODULAR_TILES_ENABLED:
                add_tiled_patch(col, f"Base_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset - FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, SURFACE_TILE_SIZE, SURFACE_TILE_SIZE, base_mat)
            else:
                add_box(col, f"Base_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset - FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, base_mat)
    else:
        footprint_rects = footprint_rects_from_layout(valid_rooms, corridor, open_void=open_void)
        for i, patch in enumerate(subtract_many_rects(footprint_rects, [void_rect])):
            if MODULAR_TILES_ENABLED:
                add_tiled_patch(col, f"Base_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset - FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, SURFACE_TILE_SIZE, SURFACE_TILE_SIZE, base_mat)
            else:
                add_box(col, f"Base_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset - FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, base_mat)

    for r in valid_rooms:
        room_mat = ensure_material(f"MAT_{r.key}", r.color)
        room_patches = subtract_many_rects([r.rect], [void_rect, open_void] if open_void else [void_rect])
        for i, patch in enumerate(room_patches):
            if MODULAR_TILES_ENABLED:
                add_tiled_patch(col, f"FLR_{r.key}_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset + FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, SURFACE_TILE_SIZE, SURFACE_TILE_SIZE, room_mat)
            else:
                add_box(col, f"FLR_{r.key}_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset + FLOOR_THICKNESS*0.5, patch.w, patch.h, FLOOR_THICKNESS, room_mat)
        add_text(col, r.label, r.rect.x + 0.2, r.rect.cy, z_offset + 0.03)

    cor_patches = subtract_many_rects([corridor], [void_rect, open_void] if open_void else [void_rect])
    for i, patch in enumerate(cor_patches):
        if MODULAR_TILES_ENABLED:
            add_tiled_patch(col, f"FLR_Corridor_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset + FLOOR_THICKNESS*0.52, patch.w, patch.h, FLOOR_THICKNESS*1.02, SURFACE_TILE_SIZE, SURFACE_TILE_SIZE, cor_mat)
        else:
            add_box(col, f"FLR_Corridor_{int(z_offset*1000)}_{i}", patch.cx, patch.cy, z_offset + FLOOR_THICKNESS*0.52, patch.w, patch.h, FLOOR_THICKNESS*1.02, cor_mat)

    if use_legacy_quad_shell:
        outer = [
            ("H", 0.0, 0.0, HOUSE_WIDTH),
            ("H", HOUSE_DEPTH, 0.0, HOUSE_WIDTH),
            ("V", 0.0, 0.0, HOUSE_DEPTH),
            ("V", HOUSE_WIDTH, 0.0, HOUSE_DEPTH),
        ]
        entrance_ops = {("H", 0.0): [Opening(HOUSE_WIDTH*0.5 - 0.6, HOUSE_WIDTH*0.5 + 0.6, 0.0, DOOR_HEIGHT)]} if include_entrance else {}
        for i, (ori, fixed, start, end) in enumerate(outer):
            ops = list(entrance_ops.get((ori, fixed), []))
            for room in rooms:
                ops.extend(outer_window_openings_for_room(room, ori, fixed, start, end))
            ops = prune_overlapping_openings(ops)
            ops = offset_openings(ops, z_offset)
            add_wall_with_openings(col, f"OW_{i}_{int(z_offset*1000)}", ori, fixed, start, end, z_offset, WALL_HEIGHT, WALL_THICKNESS, ops, wall_mat)
            if include_entrance and ori == "H" and almost(fixed, 0.0):
                add_entry_door_leaf(
                    col,
                    f"EntryDoor_{i}_{int(z_offset*1000)}",
                    ori,
                    fixed,
                    HOUSE_WIDTH * 0.5,
                    z_offset,
                    ENTRY_DOOR_WIDTH,
                    DOOR_HEIGHT - 0.02,
                    WALL_THICKNESS,
                    entry_door_mat,
                )

        boundary_segments = []
        entrance_seg = None
    else:
        items = [("room", r, r.rect) for r in valid_rooms] + [("corridor", None, corridor)]
        boundary_segments = boundary_segments_from_rects(items)
        entrance_seg = choose_entrance_segment(boundary_segments) if include_entrance else None

        for i, seg in enumerate(boundary_segments):
            ops = []
            seg_name_prefix = "OW"
            is_entrance_segment = entrance_seg is seg
            if is_entrance_segment:
                mid = (seg["start"] + seg["end"]) * 0.5
                seg_len = max(0.0, seg["end"] - seg["start"])
                target_half = ENTRY_DOOR_WIDTH * 0.5
                safe_half = max(0.20, (seg_len - 0.30) * 0.5)
                half = min(target_half, safe_half)
                ops.append(Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT))
                seg["_entry_mid"] = mid
                seg["_entry_half"] = half
                seg_name_prefix = "OW"
            window_ops = []
            if seg["kind"] == "room" and seg["room"] is not None:
                window_ops = boundary_window_openings_for_room(seg["room"], seg["ori"], seg["start"], seg["end"])
                ops.extend(window_ops)
                if window_ops and not is_entrance_segment:
                    seg_name_prefix = "OWW"
            ops = prune_overlapping_openings(ops)
            ops = offset_openings(ops, z_offset)
            add_wall_with_openings(col, f"{seg_name_prefix}_{i}_{int(z_offset*1000)}", seg["ori"], seg["fixed"], seg["start"], seg["end"], z_offset, WALL_HEIGHT, WALL_THICKNESS, ops, wall_mat)
            if is_entrance_segment and "_entry_mid" in seg and "_entry_half" in seg:
                add_entry_door_leaf(
                    col,
                    f"EntryDoor_{i}_{int(z_offset*1000)}",
                    seg["ori"],
                    seg["fixed"],
                    seg["_entry_mid"],
                    z_offset,
                    seg["_entry_half"] * 2.0,
                    DOOR_HEIGHT - 0.02,
                    WALL_THICKNESS,
                    entry_door_mat,
                )

    all_rects = [r.rect for r in valid_rooms] + [corridor]
    for idx, rect in enumerate(all_rects):
        edges = [
            ("H", rect.y, rect.x, rect.x2),
            ("H", rect.y2, rect.x, rect.x2),
            ("V", rect.x, rect.y, rect.y2),
            ("V", rect.x2, rect.y, rect.y2),
        ]
        for eidx, (ori, fixed, start, end) in enumerate(edges):
            neighbor_found = False
            for jdx, other in enumerate(all_rects):
                if jdx == idx:
                    continue
                sw = shared_wall(rect, other)
                if sw and sw[0] == ori and almost(sw[1], fixed):
                    iv = overlap(start, end, sw[2], sw[3])
                    if iv:
                        neighbor_found = True
                        break

            if neighbor_found:
                for jdx, other in enumerate(all_rects):
                    if jdx <= idx:
                        continue
                    sw = shared_wall(rect, other)
                    if sw and sw[0] == ori and almost(sw[1], fixed):
                        iv = overlap(start, end, sw[2], sw[3])
                        if not iv:
                            continue
                        openings = []
                        if other == corridor or rect == corridor:
                            room_rect = rect if other == corridor else other
                            openings.extend(edge_openings_to_corridor(room_rect, corridor, ori, fixed, iv[0], iv[1]))
                        else:
                            mid = (iv[0] + iv[1]) * 0.5
                            half = min(DOOR_WIDTH * 0.5, (iv[1] - iv[0]) * 0.35)
                            openings.append(Opening(mid-half, mid+half))
                        for seg_idx, (seg_start, seg_end) in enumerate(subtract_wall_interval_for_void(ori, fixed, iv[0], iv[1], void_rect)):
                            seg_openings = []
                            for op in openings:
                                op_iv = overlap(seg_start, seg_end, op.start, op.end)
                                if op_iv:
                                    seg_openings.append(Opening(op_iv[0], op_iv[1], op.z0, op.z1))
                            seg_openings = offset_openings(seg_openings, z_offset)
                            add_wall_with_openings(col, f"IW_{idx}_{jdx}_{eidx}_{seg_idx}_{int(z_offset*1000)}", ori, fixed, seg_start, seg_end, z_offset, WALL_HEIGHT, WALL_THICKNESS*0.88, seg_openings, wall_mat)
            else:
                if use_legacy_quad_shell:
                    if (ori == "H" and (almost(fixed, 0.0) or almost(fixed, HOUSE_DEPTH))) or (ori == "V" and (almost(fixed, 0.0) or almost(fixed, HOUSE_WIDTH))):
                        continue
                else:
                    if is_boundary_edge(boundary_segments, ori, fixed, start, end):
                        continue
                if is_inner_face_of_exterior_for_rect(rect, ori, fixed):
                    continue
                openings = opening_for_outer_entrance_on_rect(rect, ori, fixed, start, end) if include_entrance else []
                for seg_idx, (seg_start, seg_end) in enumerate(subtract_wall_interval_for_void(ori, fixed, start, end, void_rect)):
                    seg_openings = []
                    for op in openings:
                        op_iv = overlap(seg_start, seg_end, op.start, op.end)
                        if op_iv:
                            seg_openings.append(Opening(op_iv[0], op_iv[1], op.z0, op.z1))
                    seg_openings = offset_openings(seg_openings, z_offset)
                    add_wall_with_openings(col, f"SW_{idx}_{eidx}_{seg_idx}_{int(z_offset*1000)}", ori, fixed, seg_start, seg_end, z_offset, WALL_HEIGHT, WALL_THICKNESS*0.88, seg_openings, wall_mat)


def add_roof_patches(col, current_patches: List[Rect], z_offset: float, next_patches: Optional[List[Rect]] = None, opening_rect: Optional[Rect] = None, open_void: Optional[Rect] = None):
    roof_mat = ensure_material("FP_Roof", (0.72, 0.72, 0.74, 1.0))
    roof_z = z_offset + WALL_HEIGHT + FLOOR_THICKNESS * 0.5
    roof_targets = list(current_patches)
    if next_patches:
        roof_targets = subtract_many_rects(roof_targets, list(next_patches))
    if open_void is not None:
        roof_targets = subtract_many_rects(roof_targets, [open_void])
    if opening_rect is not None:
        roof_targets = subtract_many_rects(roof_targets, [opening_rect])

    for patch_index, patch in enumerate(roof_targets):
        if MODULAR_TILES_ENABLED:
            add_world_aligned_surface_tiles(
                col,
                f"Roof_{int(z_offset*1000)}_{patch_index}",
                patch.cx,
                patch.cy,
                roof_z,
                patch.w,
                patch.h,
                FLOOR_THICKNESS,
                SURFACE_TILE_SIZE,
                SURFACE_TILE_SIZE,
                roof_mat,
            )
        else:
            add_box(col, f"Roof_{int(z_offset*1000)}_{patch_index}", patch.cx, patch.cy, roof_z, patch.w, patch.h, FLOOR_THICKNESS, roof_mat)



# ============================================================
# Atlas pipeline — Stage 1
# Uses the existing generated geometry and assigns atlas-based
# materials/UVs without converting the house to modular tiles yet.
# ============================================================

ATLAS_ENABLED = True
ATLAS_MANIFEST_PATH = "//house_atlas.json"
ATLAS_IMAGE_PATH = ""   # if empty, taken from manifest meta.source_image
ATLAS_INCLUDE_INTERIOR_WALLS = False
ATLAS_RANDOM_PICK = True

def _atlas_abs(path_str: str) -> str:
    if not path_str:
        return ""
    try:
        return bpy.path.abspath(path_str)
    except Exception:
        return path_str

def _load_json(path_str: str):
    path = Path(_atlas_abs(path_str))
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def _write_default_atlas_manifest(path_str: str):
    path = Path(_atlas_abs(path_str))
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "meta": {
            "atlas_width": 1024,
            "atlas_height": 1024,
            "source_image": "//house_atlas.png",
            "style": "anime_modern_house",
            "random_pick": True,
            "version": 1
        },
        "walls": [
            {"id": "wall_01", "x": 0, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_02", "x": 256, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_03", "x": 512, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_04", "x": 768, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0}
        ],
        "wall_windows": [
            {"id": "wall_window_01", "x": 0, "y": 256, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_window_02", "x": 256, "y": 256, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_window_03", "x": 512, "y": 256, "w": 512, "h": 256, "tile_width_m": 2.0, "tile_height_m": 3.0}
        ],
        "wall_doors": [
            {"id": "wall_door_01", "x": 0, "y": 512, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_door_02", "x": 256, "y": 512, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 3.0},
            {"id": "wall_door_03", "x": 512, "y": 512, "w": 512, "h": 256, "tile_width_m": 2.0, "tile_height_m": 3.0}
        ],
        "floors": [
            {"id": "floor_01", "x": 0, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0},
            {"id": "floor_02", "x": 256, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0}
        ],
        "roofs": [
            {"id": "roof_01", "x": 512, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0},
            {"id": "roof_02", "x": 768, "y": 768, "w": 256, "h": 256, "tile_width_m": 2.0, "tile_height_m": 2.0}
        ],
        "stairs": [
            {"id": "stair_01", "x": 768, "y": 512, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0},
            {"id": "stair_02", "x": 896, "y": 512, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0}
        ],
        "stair_landings": [
            {"id": "landing_01", "x": 768, "y": 640, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0},
            {"id": "landing_02", "x": 896, "y": 640, "w": 128, "h": 128, "tile_width_m": 1.0, "tile_height_m": 1.0}
        ]
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[Atlas] Wrote default manifest: {path}")
    return manifest

def _atlas_pick(entries, seed_value: int, salt: str):
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]
    idx = abs(hash(f"{seed_value}:{salt}")) % len(entries)
    return entries[idx]

def _load_atlas_image(image_path: str):
    abs_path = _atlas_abs(image_path)
    if not abs_path or not Path(abs_path).exists():
        print(f"[Atlas] Image not found: {abs_path}")
        return None
    for img in bpy.data.images:
        if bpy.path.abspath(img.filepath) == abs_path:
            return img
    try:
        return bpy.data.images.load(abs_path)
    except Exception as e:
        print(f"[Atlas] Failed to load image: {e}")
        return None

def _ensure_atlas_material(mat_name: str, image):
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = nt.nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (80, 0)
    tex = nt.nodes.new(type="ShaderNodeTexImage")
    tex.location = (-260, 0)
    tex.image = image
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.blend_method = 'CLIP'
    return mat

def _assign_uv_to_bbox(obj, region, atlas_w, atlas_h):
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="AtlasUV")
    uv_layer = mesh.uv_layers.active.data

    min_u = region["x"] / atlas_w
    max_u = (region["x"] + region["w"]) / atlas_w
    # image origin in JSON is top-left; Blender UV origin is bottom-left
    min_v = 1.0 - (region["y"] + region["h"]) / atlas_h
    max_v = 1.0 - region["y"] / atlas_h

    span_u = max(max_u - min_u, EPS)
    span_v = max(max_v - min_v, EPS)
    tile_w = max(float(region.get("tile_width_m", 1.0)), EPS)
    tile_h = max(float(region.get("tile_height_m", 1.0)), EPS)
    eps_uv = 1e-6
    mw = obj.matrix_world

    def repeat_with_face_hint(value: float, size: float, center: float) -> float:
        """Repeat value inside one tile, but do not collapse exact tile boundaries.

        When geometry is snapped to the same world grid as tile_width_m / tile_height_m
        (for example 1x1 roof tiles on a 1-meter grid), raw modulo sends both sides
        of the face to 0.0. That collapses the UVs into a line or a point.
        We use the face center as a hint: an exact boundary on the "far" side of
        the face becomes 1.0-eps, while the "near" side stays 0.0.
        """
        scaled = value / size
        nearest = round(scaled)
        if abs(scaled - nearest) <= 1e-6:
            boundary = nearest * size
            return 1.0 - eps_uv if value > center and abs(value - boundary) <= 1e-6 else 0.0
        t = scaled % 1.0
        if t >= 1.0 - eps_uv:
            t = 1.0 - eps_uv
        if t < 0.0:
            t += 1.0
        return t

    def project_coords(world_v, use_xy: bool, use_xz: bool):
        if use_xy:
            return world_v.x, world_v.y
        if use_xz:
            return world_v.x, world_v.z
        return world_v.y, world_v.z

    for poly in mesh.polygons:
        n = (mw.to_3x3() @ poly.normal).normalized()
        use_xy = abs(n.z) > 0.7
        use_xz = abs(n.y) > 0.7

        projected = []
        loop_data = []
        for li in poly.loop_indices:
            local_v = mesh.vertices[mesh.loops[li].vertex_index].co
            world_v = mw @ local_v
            px, py = project_coords(world_v, use_xy, use_xz)
            projected.append((px, py))
            loop_data.append((li, px, py))

        face_min_x = min(p[0] for p in projected)
        face_max_x = max(p[0] for p in projected)
        face_min_y = min(p[1] for p in projected)
        face_max_y = max(p[1] for p in projected)
        face_center_x = (face_min_x + face_max_x) * 0.5
        face_center_y = (face_min_y + face_max_y) * 0.5
        face_span_x = max(face_max_x - face_min_x, EPS)
        face_span_y = max(face_max_y - face_min_y, EPS)

        # Small modular faces (like the 1x1 roof tiles) should always fill the whole
        # atlas tile. This avoids the classic collapse when all vertices sit exactly
        # on integer world coordinates.
        if face_span_x <= tile_w + 1e-6 and face_span_y <= tile_h + 1e-6:
            for li, px, py in loop_data:
                fu = (px - face_min_x) / face_span_x if face_span_x > EPS else 0.0
                fv = (py - face_min_y) / face_span_y if face_span_y > EPS else 0.0
                fu = min(max(fu, 0.0), 1.0 - eps_uv)
                fv = min(max(fv, 0.0), 1.0 - eps_uv)
                uv_layer[li].uv = (min_u + fu * span_u, min_v + fv * span_v)
            continue

        for li, px, py in loop_data:
            fu = repeat_with_face_hint(px, tile_w, face_center_x)
            fv = repeat_with_face_hint(py, tile_h, face_center_y)
            uv_layer[li].uv = (min_u + fu * span_u, min_v + fv * span_v)

def apply_atlas_stage1(collection_name: str, seed_value: int):
    manifest = _load_json(ATLAS_MANIFEST_PATH)
    if manifest is None:
        manifest = _write_default_atlas_manifest(ATLAS_MANIFEST_PATH)

    meta = manifest.get("meta", {})
    atlas_w = meta.get("atlas_width", 1024)
    atlas_h = meta.get("atlas_height", 1024)
    img_path = ATLAS_IMAGE_PATH or meta.get("source_image", "")
    image = _load_atlas_image(img_path)
    if image is None:
        print("[Atlas] Skipping atlas assignment because image could not be loaded.")
        return

    cats = {
        "walls": manifest.get("walls", []),
        "wall_windows": manifest.get("wall_windows", []),
        "wall_doors": manifest.get("wall_doors", []),
        "floors": manifest.get("floors", []),
        "roofs": manifest.get("roofs", []),
        "stairs": manifest.get("stairs", []),
        "stair_landings": manifest.get("stair_landings", [])
    }

    mat_cache = {}
    def mat_for(cat):
        if cat not in mat_cache:
            mat_cache[cat] = _ensure_atlas_material(f"Atlas_{cat}", image)
        return mat_cache[cat]

    col = bpy.data.collections.get(collection_name)
    if col is None:
        print(f"[Atlas] Collection not found: {collection_name}")
        return

    for obj in col.objects:
        if obj.type != 'MESH':
            continue
        name = obj.name
        category = None
        if name.startswith("Roof_"):
            category = "roofs"
        elif name.startswith("FLR_") or name.startswith("Base_"):
            category = "floors"
        elif name.startswith("StairStep"):
            category = "stairs"
        elif name.startswith("StairLanding") or name.startswith("StairTopPlatform"):
            category = "stair_landings"
        elif name.startswith("OWD_"):
            category = "wall_doors"
        elif name.startswith("OWW_"):
            category = "wall_windows"
        elif name.startswith("OW_"):
            category = "walls"
        elif ATLAS_INCLUDE_INTERIOR_WALLS and (name.startswith("IW_") or name.startswith("SW_")):
            category = "walls"

        if not category:
            continue

        region = _atlas_pick(cats.get(category, []), seed_value, f"{name}:{category}")
        if not region:
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat_for(category))
        _assign_uv_to_bbox(obj, region, atlas_w, atlas_h)

    print("[Atlas] Stage 1 materials assigned.")

def generate():
    global HOUSE_WIDTH, HOUSE_DEPTH
    seed = random.SystemRandom().randint(0, 2**31 - 1) if AUTO_RANDOM_SEED else SEED
    random.seed(seed)
    floors = random.randint(MIN_FLOORS, MAX_FLOORS)
    print(f"[FloorPlan] Seed: {seed}")
    print(f"[FloorPlan] Floors: {floors}")
    print(f"[FloorPlan] Mode: {BUILDING_MODE}")
    print(f"[FloorPlan] Shape: {SHAPE_MODE}")

    col = get_collection(COLLECTION_NAME)
    if DELETE_OLD:
        clear_collection(col)

    floor_specs = []
    base_width = None
    base_depth = None

    for floor_index in range(floors):
        rooms = build_program()
        corridor, usable, open_void = layout_floorplan(rooms)
        if (SHAPE_MODE or "quad").lower() == "quad":
            rooms, corridor = resolve_residual_spaces(rooms, corridor, usable)
            rooms = post_validate_and_merge_rooms(rooms, corridor)
            rooms = post_validate_and_merge_rooms(rooms, corridor)
            rooms, corridor = resolve_residual_spaces(rooms, corridor, usable)
        valid_rooms = [r for r in rooms if r.rect is not None]
        if len(valid_rooms) != len(rooms):
            print(f"[FloorPlan] Warning: dropped {len(rooms) - len(valid_rooms)} unplaced rooms before drawing on floor {floor_index + 1}.")
        rooms = valid_rooms

        stair = choose_stair_placement(rooms, corridor) if floor_index < floors - 1 else None

        spec = {
            "rooms": rooms,
            "corridor": corridor,
            "stair": stair,
            "width": HOUSE_WIDTH,
            "depth": HOUSE_DEPTH,
            "open_void": open_void,
        }

        if floor_index == 0:
            base_width = spec["width"]
            base_depth = spec["depth"]
        elif BUILDING_MODE.lower() == "strict" and base_width is not None and base_depth is not None:
            spec = scale_floor_spec(spec, base_width, base_depth)

        floor_specs.append(spec)

    max_depth = max(spec["depth"] for spec in floor_specs) if floor_specs else 0.0
    inherited_void = None

    for floor_index, spec in enumerate(floor_specs):
        HOUSE_WIDTH = spec["width"]
        HOUSE_DEPTH = spec["depth"]
        z_offset = floor_index * FLOOR_TO_FLOOR_HEIGHT

        draw_geometry(col, spec["rooms"], spec["corridor"], spec["stair"], z_offset=z_offset, include_entrance=(floor_index == 0), inherited_void=inherited_void, open_void=spec.get("open_void"))

        if spec["stair"] is not None:
            add_stairs(col, spec["stair"], z_offset=z_offset)

        next_spec = floor_specs[floor_index + 1] if floor_index < len(floor_specs) - 1 else None
        opening_rect = next_spec["stair"].rect if (next_spec is not None and next_spec["stair"] is not None) else None
        current_patches = footprint_rects_from_layout(spec["rooms"], spec["corridor"], open_void=spec.get("open_void"))
        next_patches = footprint_rects_from_layout(next_spec["rooms"], next_spec["corridor"], open_void=next_spec.get("open_void")) if next_spec is not None else None
        add_roof_patches(col, current_patches, z_offset, next_patches=next_patches, opening_rect=opening_rect, open_void=spec.get("open_void"))

        inherited_void = spec["stair"].rect if spec["stair"] is not None else None

        add_text(col, f"Floor {floor_index + 1}", 0.2, spec["depth"] + 0.05, z_offset + 0.03, size=0.24)

    add_text(col, f"Seed: {seed} | Mode: {BUILDING_MODE} | Shape: {SHAPE_MODE}", 0.2, max_depth + 0.35, 0.03, size=0.25)
    add_text(col, f"Floors: {floors}", 2.3, max_depth + 0.35, 0.03, size=0.28)

    if ATLAS_ENABLED:
        apply_atlas_stage1(COLLECTION_NAME, seed)

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'


_DEFAULTS = {
    "DELETE_OLD": DELETE_OLD,
    "COLLECTION_NAME": COLLECTION_NAME,
    "WALL_HEIGHT": WALL_HEIGHT,
    "WALL_THICKNESS": WALL_THICKNESS,
    "FLOOR_THICKNESS": FLOOR_THICKNESS,
    "CORRIDOR_WIDTH": CORRIDOR_WIDTH,
    "DOOR_WIDTH": DOOR_WIDTH,
    "ENTRY_DOOR_WIDTH": ENTRY_DOOR_WIDTH,
    "ENTRY_DOOR_THICKNESS": ENTRY_DOOR_THICKNESS,
    "DOOR_HEIGHT": DOOR_HEIGHT,
    "STAIR_WIDTH": STAIR_WIDTH,
    "STAIR_LANDING": STAIR_LANDING,
    "STAIR_MID_LANDING": STAIR_MID_LANDING,
    "STAIR_RISER": STAIR_RISER,
    "STAIR_TREAD": STAIR_TREAD,
    "STAIR_CLEARANCE": STAIR_CLEARANCE,
    "STAIR_MAX_PARENT_OCCUPANCY": STAIR_MAX_PARENT_OCCUPANCY,
    "STAIR_MIN_FREE_AREA": STAIR_MIN_FREE_AREA,
    "STAIR_DOOR_CLEARANCE": STAIR_DOOR_CLEARANCE,
    "STAIR_WINDOW_CLEARANCE": STAIR_WINDOW_CLEARANCE,
    "WINDOW_SILL_HEIGHT": WINDOW_SILL_HEIGHT,
    "WINDOW_HEIGHT": WINDOW_HEIGHT,
    "WINDOW_MIN_WIDTH": WINDOW_MIN_WIDTH,
    "WINDOW_END_MARGIN": WINDOW_END_MARGIN,
    "WINDOW_STRIP_WIDTH": WINDOW_STRIP_WIDTH,
    "OUTER_MARGIN": OUTER_MARGIN,
    "ROOM_GAP": ROOM_GAP,
    "MIN_ROOM_SIDE": MIN_ROOM_SIDE,
    "MAX_ASPECT": MAX_ASPECT,
    "TEXT_SIZE": TEXT_SIZE,
    "POST_MERGE_MIN_SIDE": POST_MERGE_MIN_SIDE,
    "POST_MERGE_MIN_AREA": POST_MERGE_MIN_AREA,
    "POST_MERGE_MAX_ASPECT": POST_MERGE_MAX_ASPECT,
    "POST_MERGE_HARD_MAX_ASPECT": POST_MERGE_HARD_MAX_ASPECT,
    "POST_MERGE_EDGE_STRIP_SIDE": POST_MERGE_EDGE_STRIP_SIDE,
    "POST_MERGE_SLIVER_RATIO": POST_MERGE_SLIVER_RATIO,
    "POST_MERGE_MIN_SHARED": POST_MERGE_MIN_SHARED,
    "RESIDUAL_MIN_AREA": RESIDUAL_MIN_AREA,
    "RESIDUAL_LONG_STRIP_RATIO": RESIDUAL_LONG_STRIP_RATIO,
    "RESIDUAL_SHORT_SIDE": RESIDUAL_SHORT_SIDE,
    "RESIDUAL_CORRIDOR_SHARED_BONUS": RESIDUAL_CORRIDOR_SHARED_BONUS,
    "HOUSE_SCALE": HOUSE_SCALE,
    "TARGET_ROOM_COUNT": TARGET_ROOM_COUNT,
    "AUTO_RANDOM_SEED": AUTO_RANDOM_SEED,
    "SEED": SEED,
    "MIN_FLOORS": MIN_FLOORS,
    "MAX_FLOORS": MAX_FLOORS,
    "BUILDING_MODE": BUILDING_MODE,
    "SHAPE_MODE": SHAPE_MODE,
    "ATLAS_ENABLED": ATLAS_ENABLED,
    "ATLAS_MANIFEST_PATH": ATLAS_MANIFEST_PATH,
    "ATLAS_IMAGE_PATH": ATLAS_IMAGE_PATH,
    "ATLAS_INCLUDE_INTERIOR_WALLS": ATLAS_INCLUDE_INTERIOR_WALLS,
    "ATLAS_RANDOM_PICK": ATLAS_RANDOM_PICK,
    "MODULAR_TILES_ENABLED": MODULAR_TILES_ENABLED,
    "WALL_TILE_WIDTH": WALL_TILE_WIDTH,
    "SURFACE_TILE_SIZE": SURFACE_TILE_SIZE,
}


def reset_defaults():
    apply_settings(_DEFAULTS)


def apply_settings(settings: dict):
    global DELETE_OLD, COLLECTION_NAME
    global WALL_HEIGHT, WALL_THICKNESS, FLOOR_THICKNESS, CORRIDOR_WIDTH, DOOR_WIDTH, ENTRY_DOOR_WIDTH, ENTRY_DOOR_THICKNESS, DOOR_HEIGHT
    global STAIR_WIDTH, STAIR_LANDING, STAIR_MID_LANDING, STAIR_RISER, STAIR_TREAD, STAIR_CLEARANCE
    global STAIR_MAX_PARENT_OCCUPANCY, STAIR_MIN_FREE_AREA, STAIR_DOOR_CLEARANCE, STAIR_WINDOW_CLEARANCE
    global WINDOW_SILL_HEIGHT, WINDOW_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_END_MARGIN, WINDOW_STRIP_WIDTH
    global OUTER_MARGIN, ROOM_GAP, MIN_ROOM_SIDE, MAX_ASPECT, TEXT_SIZE
    global POST_MERGE_MIN_SIDE, POST_MERGE_MIN_AREA, POST_MERGE_MAX_ASPECT, POST_MERGE_HARD_MAX_ASPECT, POST_MERGE_EDGE_STRIP_SIDE, POST_MERGE_SLIVER_RATIO, POST_MERGE_MIN_SHARED
    global RESIDUAL_MIN_AREA, RESIDUAL_LONG_STRIP_RATIO, RESIDUAL_SHORT_SIDE, RESIDUAL_CORRIDOR_SHARED_BONUS
    global HOUSE_SCALE, TARGET_ROOM_COUNT, AUTO_RANDOM_SEED, SEED, MIN_FLOORS, MAX_FLOORS, FLOOR_TO_FLOOR_HEIGHT
    global BUILDING_MODE, SHAPE_MODE, STRICT_EDGE_TOL
    global ATLAS_ENABLED, ATLAS_MANIFEST_PATH, ATLAS_IMAGE_PATH, ATLAS_INCLUDE_INTERIOR_WALLS, ATLAS_RANDOM_PICK
    global MODULAR_TILES_ENABLED, WALL_TILE_WIDTH, SURFACE_TILE_SIZE

    for key, value in settings.items():
        if key in globals():
            globals()[key] = value

    FLOOR_TO_FLOOR_HEIGHT = WALL_HEIGHT + FLOOR_THICKNESS
    WALL_TILE_WIDTH = max(0.05, WALL_TILE_WIDTH)
    SURFACE_TILE_SIZE = max(0.05, SURFACE_TILE_SIZE)
    STRICT_EDGE_TOL = max(WALL_THICKNESS * 0.75, 0.22)


def generate_from_settings(settings: dict):
    apply_settings(settings)
    generate()

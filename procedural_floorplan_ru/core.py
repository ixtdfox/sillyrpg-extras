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
from mathutils import Vector, Matrix

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

ROOF_BORDER_ENABLED = True
ROOF_BORDER_WIDTH = 0.2
ROOF_BORDER_HEIGHT = 0.2
ROOF_BORDER_TILE_CATEGORY = "roof_borders"
ROOF_BORDER_TILE_ID = ""

FLOOR_BAND_ENABLED = True
FLOOR_BAND_DEPTH = 0.1
FLOOR_BAND_HEIGHT = 0.1
FLOOR_BAND_TILE_CATEGORY = "floor_bands"
FLOOR_BAND_TILE_ID = ""

RAILINGS_ENABLED = False
RAILING_HEIGHT = 1.1
RAILING_POST_SIZE = 0.06
RAILING_RAIL_THICKNESS = 0.04
RAILING_RAIL_COUNT = 3
RAILING_TILE_CATEGORY = "railings"
RAILING_TILE_ID = ""

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


def ceil_to_meter(v: float) -> float:
    return float(max(1, int(math.ceil(v - EPS))))


def quantize_house_shell(width: float, depth: float) -> Tuple[float, float]:
    # Keep the OUTER shell aligned to whole meters on X/Y.
    # This makes roof tiling and facade/module coverage land on a stable 1x1 grid
    # and avoids the recurring +X/+Y half-wall gaps.
    return ceil_to_meter(width), ceil_to_meter(depth)


def _build_meter_line_map(values: List[float], start: float, end: float) -> dict:
    unique = sorted({round(v, 6) for v in values if start - EPS <= v <= end + EPS})
    if len(unique) <= 2:
        return {v: v for v in unique}

    module_count = max(1, int(round(end - start)))
    interior = unique[1:-1]
    desired = []
    for value in interior:
        idx = int(round(value - start))
        idx = max(1, min(module_count - 1, idx)) if module_count > 1 else 0
        desired.append(idx)

    assigned = desired[:] if desired else []
    for i in range(1, len(assigned)):
        assigned[i] = max(assigned[i], assigned[i - 1] + 1)
    for i in range(len(assigned) - 2, -1, -1):
        assigned[i] = min(assigned[i], assigned[i + 1] - 1)
    if assigned:
        min_allowed = 1
        max_allowed = max(1, module_count - 1)
        for i, idx in enumerate(assigned):
            assigned[i] = max(min_allowed, min(max_allowed, idx))

    mapping = {unique[0]: start, unique[-1]: end}
    for value, idx in zip(interior, assigned):
        mapping[value] = start + float(idx)
    return mapping


def quantize_layout_to_meter_grid(rooms: List["Room"], corridor: "Rect", stair=None, open_void: Optional["Rect"] = None):
    inner_x0 = WALL_THICKNESS * 0.5
    inner_y0 = WALL_THICKNESS * 0.5
    inner_x1 = HOUSE_WIDTH - WALL_THICKNESS * 0.5
    inner_y1 = HOUSE_DEPTH - WALL_THICKNESS * 0.5

    x_values = [inner_x0, inner_x1, corridor.x, corridor.x2]
    y_values = [inner_y0, inner_y1, corridor.y, corridor.y2]

    rects = [r.rect for r in rooms if r.rect is not None]
    if open_void is not None:
        rects.append(open_void)
    if stair is not None and getattr(stair, 'rect', None) is not None:
        rects.append(stair.rect)
    for rect in rects:
        x_values.extend([rect.x, rect.x2])
        y_values.extend([rect.y, rect.y2])

    x_map = _build_meter_line_map(x_values, inner_x0, inner_x1)
    y_map = _build_meter_line_map(y_values, inner_y0, inner_y1)

    def remap(rect: Optional[Rect]) -> Optional[Rect]:
        if rect is None:
            return None
        x1 = x_map.get(round(rect.x, 6), rect.x)
        x2 = x_map.get(round(rect.x2, 6), rect.x2)
        y1 = y_map.get(round(rect.y, 6), rect.y)
        y2 = y_map.get(round(rect.y2, 6), rect.y2)
        return Rect(x1, y1, max(EPS, x2 - x1), max(EPS, y2 - y1))

    for room in rooms:
        room.rect = remap(room.rect)
    corridor = remap(corridor)
    if stair is not None and getattr(stair, 'rect', None) is not None:
        stair.rect = remap(stair.rect)
    if open_void is not None:
        open_void = remap(open_void)
    return rooms, corridor, stair, open_void


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

    if col is not None:
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




def normalize_openings_for_segment(openings: List[Opening], seg_start: float, seg_end: float) -> List[Opening]:
    clean = []
    for op in openings:
        s = max(seg_start, op.start)
        e = min(seg_end, op.end)
        if e - s > EPS:
            clean.append(Opening(s, e, op.z0, op.z1))
    if MODULAR_TILES_ENABLED and clean:
        unit = _modular_unit()
        snapped = []
        for op in clean:
            sop = _snap_opening_to_module(seg_start, seg_end, op, unit)
            if sop is not None:
                snapped.append(sop)
        clean = snapped
    return prune_overlapping_openings(clean)

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
    return quantize_house_shell(width, depth)


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
        obj = add_box(col, name, cx, cy, door_z, width, ENTRY_DOOR_THICKNESS, slab_h, mat)
    else:
        cx = fixed + (wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5 if fixed < HOUSE_WIDTH * 0.5 else -(wall_thickness * 0.5 - ENTRY_DOOR_THICKNESS * 0.5))
        cy = center
        obj = add_box(col, name, cx, cy, door_z, ENTRY_DOOR_THICKNESS, width, slab_h, mat)
    obj["atlas_category"] = "wall_doors"
    obj["generated_entry_door"] = True
    return obj


def add_window_glass(col, name, orientation, fixed, opening: Opening, z0: float, wall_thickness: float):
    # Plug the opening with a thin insert positioned slightly toward the interior side
    # of the exterior wall. The interior offset must depend on the wall side; otherwise
    # west/south walls look correct while east/north walls appear shifted, or vice versa.
    width = max(0.08, opening.end - opening.start + 0.06)
    height = max(0.08, opening.z1 - opening.z0 + 0.06)
    depth = max(0.03, min(0.08, wall_thickness * 0.35))
    center = (opening.start + opening.end) * 0.5
    center_z = z0 + (opening.z0 + opening.z1) * 0.5

    inward = max(0.0, wall_thickness * 0.5 - depth * 0.5 - 0.002)
    if orientation == "H":
        # South wall (small fixed) offsets to +Y, north wall to -Y.
        cy = fixed + (inward if fixed < HOUSE_DEPTH * 0.5 else -inward)
        obj = add_box(col, name, center, cy, center_z, width, depth, height)
    else:
        # West wall (small fixed) offsets to +X, east wall to -X.
        cx = fixed + (inward if fixed < HOUSE_WIDTH * 0.5 else -inward)
        obj = add_box(col, name, cx, center, center_z, depth, width, height)

    obj["atlas_category"] = "glass"
    obj["atlas_tile_id"] = "glass_01"
    obj["atlas_force_bbox"] = True
    obj["generated_glass"] = True
    return obj

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










def remove_openings_overlapping_blockers(openings: List[Opening], blockers: List[Opening]) -> List[Opening]:
    if not openings or not blockers:
        return list(openings)
    out = []
    for op in openings:
        bad = False
        for blk in blockers:
            if overlap(op.start, op.end, blk.start, blk.end) and not (op.z1 <= blk.z0 + EPS or blk.z1 <= op.z0 + EPS):
                bad = True
                break
        if not bad:
            out.append(op)
    return out


def apply_linear_gap_blockers(openings: List[Opening], blocked_intervals: List[Tuple[float, float]]) -> List[Opening]:
    if not openings or not blocked_intervals:
        return list(openings)
    blockers = [Opening(a, b, -1.0e6, 1.0e6) for (a, b) in blocked_intervals if b - a > EPS]
    return remove_openings_overlapping_blockers(openings, blockers)



def entrance_gap_blockers_for_segment(seg, entrance_seg, entrance_opening: Optional[Opening], gap: float) -> List[Tuple[float, float]]:
    if entrance_seg is None or entrance_opening is None:
        return []
    if seg["ori"] != entrance_seg["ori"] or not almost(seg["fixed"], entrance_seg["fixed"]):
        return []
    blocked_start = entrance_opening.start - gap
    blocked_end = entrance_opening.end + gap
    iv = overlap(seg["start"], seg["end"], blocked_start, blocked_end)
    return [iv] if iv else []



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
        entrance_ops = {("H", 0.0): [Opening(HOUSE_WIDTH*0.5 - ENTRY_DOOR_WIDTH*0.5, HOUSE_WIDTH*0.5 + ENTRY_DOOR_WIDTH*0.5, 0.0, DOOR_HEIGHT)]} if include_entrance else {}
        for i, (ori, fixed, start, end) in enumerate(outer):
            raw_entrance_ops = list(entrance_ops.get((ori, fixed), []))
            entrance_only_ops = normalize_openings_for_segment(raw_entrance_ops, start, end)
            raw_glass_ops = []
            for room in rooms:
                room_ops = outer_window_openings_for_room(room, ori, fixed, start, end)
                raw_glass_ops.extend(room_ops)
            glass_ops = normalize_openings_for_segment(raw_glass_ops, start, end)
            glass_ops = remove_openings_overlapping_blockers(glass_ops, entrance_only_ops)
            ops = prune_overlapping_openings(entrance_only_ops + glass_ops)
            ops = offset_openings(ops, z_offset)
            add_wall_with_openings(col, f"OW_{i}_{int(z_offset*1000)}", ori, fixed, start, end, z_offset, WALL_HEIGHT, WALL_THICKNESS, ops, wall_mat)
            for gidx, glass_op in enumerate(glass_ops):
                add_window_glass(col, f"GLZ_{i}_{gidx}_{int(z_offset*1000)}", ori, fixed, glass_op, z_offset, WALL_THICKNESS)
            if include_entrance and ori == "H" and almost(fixed, 0.0) and entrance_only_ops:
                door_op = entrance_only_ops[0]
                add_entry_door_leaf(
                    col,
                    f"EntryDoor_{i}_{int(z_offset*1000)}",
                    ori,
                    fixed,
                    (door_op.start + door_op.end) * 0.5,
                    z_offset,
                    door_op.end - door_op.start,
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
        entrance_reference_opening = None
        entrance_gap = _modular_unit()
        if entrance_seg is not None:
            mid = (entrance_seg["start"] + entrance_seg["end"]) * 0.5
            seg_len = max(0.0, entrance_seg["end"] - entrance_seg["start"])
            target_half = ENTRY_DOOR_WIDTH * 0.5
            safe_half = max(0.20, (seg_len - 0.30) * 0.5)
            half = min(target_half, safe_half)
            entrance_reference_opening = Opening(mid - half, mid + half, 0.0, DOOR_HEIGHT)

        for i, seg in enumerate(boundary_segments):
            entrance_only_ops = []
            seg_name_prefix = "OW"
            is_entrance_segment = entrance_seg is seg
            if is_entrance_segment and entrance_reference_opening is not None:
                raw_entrance_ops = [entrance_reference_opening]
                entrance_only_ops = normalize_openings_for_segment(raw_entrance_ops, seg["start"], seg["end"])
                seg_name_prefix = "OW"
            window_ops = []
            if seg["kind"] == "room" and seg["room"] is not None and not is_entrance_segment:
                raw_window_ops = boundary_window_openings_for_room(seg["room"], seg["ori"], seg["start"], seg["end"])
                window_ops = normalize_openings_for_segment(raw_window_ops, seg["start"], seg["end"])
                if window_ops:
                    seg_name_prefix = "OWW"
            window_ops = apply_linear_gap_blockers(window_ops, entrance_gap_blockers_for_segment(seg, entrance_seg, entrance_reference_opening, entrance_gap))
            window_ops = remove_openings_overlapping_blockers(window_ops, entrance_only_ops)
            ops = prune_overlapping_openings(entrance_only_ops + window_ops)
            ops = offset_openings(ops, z_offset)
            add_wall_with_openings(col, f"{seg_name_prefix}_{i}_{int(z_offset*1000)}", seg["ori"], seg["fixed"], seg["start"], seg["end"], z_offset, WALL_HEIGHT, WALL_THICKNESS, ops, wall_mat)
            for gidx, glass_op in enumerate(window_ops):
                add_window_glass(col, f"GLZ_{i}_{gidx}_{int(z_offset*1000)}", seg["ori"], seg["fixed"], glass_op, z_offset, WALL_THICKNESS)
            if is_entrance_segment and entrance_only_ops:
                door_op = entrance_only_ops[0]
                add_entry_door_leaf(
                    col,
                    f"EntryDoor_{i}_{int(z_offset*1000)}",
                    seg["ori"],
                    seg["fixed"],
                    (door_op.start + door_op.end) * 0.5,
                    z_offset,
                    door_op.end - door_op.start,
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


def _outerize_roof_patch(patch: Rect) -> Rect:
    inner_x0 = WALL_THICKNESS * 0.5
    inner_y0 = WALL_THICKNESS * 0.5
    inner_x1 = HOUSE_WIDTH - WALL_THICKNESS * 0.5
    inner_y1 = HOUSE_DEPTH - WALL_THICKNESS * 0.5
    x0, y0, x1, y1 = patch.x, patch.y, patch.x2, patch.y2
    if abs(x0 - inner_x0) <= max(STRICT_EDGE_TOL, 0.25):
        x0 = 0.0
    if abs(y0 - inner_y0) <= max(STRICT_EDGE_TOL, 0.25):
        y0 = 0.0
    if abs(x1 - inner_x1) <= max(STRICT_EDGE_TOL, 0.25):
        x1 = HOUSE_WIDTH
    if abs(y1 - inner_y1) <= max(STRICT_EDGE_TOL, 0.25):
        y1 = HOUSE_DEPTH
    return Rect(x0, y0, max(EPS, x1 - x0), max(EPS, y1 - y0))


def add_roof_tiles_world_aligned(col, name_prefix: str, patch: Rect, z: float, thickness: float, tile_size: float, mat=None):
    tile_size = max(EPS, tile_size)
    patch = _outerize_roof_patch(patch)
    start_x = int(math.floor(patch.x + EPS))
    end_x = int(math.ceil(patch.x2 - EPS))
    start_y = int(math.floor(patch.y + EPS))
    end_y = int(math.ceil(patch.y2 - EPS))
    created = []
    idx = 0
    for gx in range(start_x, end_x):
        for gy in range(start_y, end_y):
            created.append(add_box(col, f"{name_prefix}_tile_{idx}", gx + tile_size * 0.5, gy + tile_size * 0.5, z, tile_size, tile_size, thickness, mat))
            idx += 1
    return created




def _boundary_runs_from_rects(rects: List[Rect], unit: float = 1.0):
    unit = max(EPS, float(unit))
    edge_counts = {}

    def add_h(y: float, x0: float, x1: float):
        length = x1 - x0
        steps = max(1, int(round(length / unit)))
        cursor = x0
        for _ in range(steps):
            key = ("H", round(y, 6), round(cursor, 6), round(cursor + unit, 6))
            edge_counts[key] = edge_counts.get(key, 0) + 1
            cursor += unit

    def add_v(x: float, y0: float, y1: float):
        length = y1 - y0
        steps = max(1, int(round(length / unit)))
        cursor = y0
        for _ in range(steps):
            key = ("V", round(x, 6), round(cursor, 6), round(cursor + unit, 6))
            edge_counts[key] = edge_counts.get(key, 0) + 1
            cursor += unit

    for rect in rects:
        if rect.w <= EPS or rect.h <= EPS:
            continue
        add_h(rect.y, rect.x, rect.x2)
        add_h(rect.y2, rect.x, rect.x2)
        add_v(rect.x, rect.y, rect.y2)
        add_v(rect.x2, rect.y, rect.y2)

    boundary = [key for key, count in edge_counts.items() if count == 1]
    h_groups = {}
    v_groups = {}
    for ori, fixed, a0, a1 in boundary:
        if ori == "H":
            h_groups.setdefault(fixed, []).append((a0, a1))
        else:
            v_groups.setdefault(fixed, []).append((a0, a1))

    runs = []
    for fixed, parts in h_groups.items():
        parts.sort()
        cur0 = cur1 = None
        for a0, a1 in parts:
            if cur0 is None:
                cur0, cur1 = a0, a1
            elif abs(a0 - cur1) <= 1e-5:
                cur1 = a1
            else:
                runs.append(("H", fixed, cur0, cur1))
                cur0, cur1 = a0, a1
        if cur0 is not None:
            runs.append(("H", fixed, cur0, cur1))

    for fixed, parts in v_groups.items():
        parts.sort()
        cur0 = cur1 = None
        for a0, a1 in parts:
            if cur0 is None:
                cur0, cur1 = a0, a1
            elif abs(a0 - cur1) <= 1e-5:
                cur1 = a1
            else:
                runs.append(("V", fixed, cur0, cur1))
                cur0, cur1 = a0, a1
        if cur0 is not None:
            runs.append(("V", fixed, cur0, cur1))

    return runs


def _point_in_any_rect(px: float, py: float, rects: List[Rect], margin: float = 1e-4) -> bool:
    for rect in rects:
        if (rect.x + margin) <= px <= (rect.x2 - margin) and (rect.y + margin) <= py <= (rect.y2 - margin):
            return True
    return False


def _add_tiled_linear_trim(col, name_prefix: str, runs, z_center: float, vertical_size: float, side_size: float, *, inward=True, atlas_category="walls", atlas_tile_id="", source_rects: Optional[List[Rect]] = None, align_to_wall_outer_face: bool = True, protrude_outward: bool = False, end_overlap: float = 0.0):
    tile_len = 1.0
    created = []
    vertical_size = max(0.01, float(vertical_size))
    side_size = max(0.01, float(side_size))
    end_overlap = max(0.0, float(end_overlap))
    source_rects = source_rects or []
    probe = max(0.02, max(side_size, WALL_THICKNESS) * 0.6)
    for run_idx, (orientation, fixed, start, end) in enumerate(runs):
        mid_axis = (start + end) * 0.5
        if orientation == "H":
            inside_pos = _point_in_any_rect(mid_axis, fixed + probe, source_rects)
            inside_neg = _point_in_any_rect(mid_axis, fixed - probe, source_rects)
        else:
            inside_pos = _point_in_any_rect(fixed + probe, mid_axis, source_rects)
            inside_neg = _point_in_any_rect(fixed - probe, mid_axis, source_rects)
        if inside_pos and not inside_neg:
            dir_sign = 1.0 if inward else -1.0
        elif inside_neg and not inside_pos:
            dir_sign = -1.0 if inward else 1.0
        else:
            dir_sign = 1.0

        side_offset = dir_sign * side_size * 0.5
        if align_to_wall_outer_face:
            if protrude_outward:
                side_offset = dir_sign * ((WALL_THICKNESS * 0.5) + (side_size * 0.5))
            else:
                side_offset = dir_sign * ((WALL_THICKNESS * 0.5) - (side_size * 0.5))

        # When the trim is pushed outward from the wall face (for example FloorBand),
        # half of the visual corner distance comes from the wall thickness itself.
        # In that case, extending only by half of the trim depth is not enough and
        # leaves a small square notch near the corner post. Extend at least up to the
        # trim centerline offset so perpendicular runs actually meet.
        overlap_for_run = end_overlap
        if align_to_wall_outer_face and protrude_outward:
            # Outward trims need a stronger corner extension than roof borders.
            # Extending only to the trim centerline can still leave a tiny notch
            # against corner posts / perpendicular runs because the visible contact
            # happens at the outer trim face, not at the centerline.
            overlap_for_run = max(
                overlap_for_run,
                abs(side_offset) + (side_size * 0.5),
                (WALL_THICKNESS * 0.5) + side_size,
            )

        extended_start = start - overlap_for_run
        extended_end = end + overlap_for_run
        parts = _split_length_into_tiles(extended_end - extended_start, tile_len, keep_uniform=True)
        axis_start = extended_start

        for tile_idx, (offset, seg_len) in enumerate(parts):
            center_axis = axis_start + offset
            if orientation == "H":
                x = center_axis
                y = fixed + side_offset
                obj = add_box(col, f"{name_prefix}_{run_idx}_{tile_idx}", x, y, z_center, seg_len, side_size, vertical_size)
            else:
                x = fixed + side_offset
                y = center_axis
                obj = add_box(col, f"{name_prefix}_{run_idx}_{tile_idx}", x, y, z_center, side_size, seg_len, vertical_size)

            obj["atlas_category"] = str(atlas_category or "walls")
            if atlas_tile_id:
                obj["atlas_tile_id"] = str(atlas_tile_id)
            created.append(obj)
    return created




def add_external_corner_posts(col, z_offset: float):
    """Add slim vertical posts on the four outer building corners to hide wall seams.

    Posts should sit *outside* the wall planes so they visually cover the outer corner,
    instead of being centered on the wall intersection and sinking into both walls.
    """
    post_size = max(0.04, min(0.12, WALL_THICKNESS * 0.6))
    post_z = z_offset + WALL_HEIGHT * 0.5
    half = post_size * 0.5
    corners = [
        (-half, -half),
        (HOUSE_WIDTH + half, -half),
        (-half, HOUSE_DEPTH + half),
        (HOUSE_WIDTH + half, HOUSE_DEPTH + half),
    ]
    created = []
    for idx, (cx, cy) in enumerate(corners):
        obj = add_box(col, f"CornerPost_{int(z_offset*1000)}_{idx}", cx, cy, post_z, post_size, post_size, WALL_HEIGHT)
        obj["atlas_category"] = str("walls")
        created.append(obj)
    return created

def add_roof_borders(col, roof_patches: List[Rect], z_offset: float):
    if not ROOF_BORDER_ENABLED:
        return []
    perimeter_rects = [Rect(0.0, 0.0, HOUSE_WIDTH, HOUSE_DEPTH)]
    roof_z = z_offset + WALL_HEIGHT + FLOOR_THICKNESS * 0.5
    # Continue the wall upward: the border starts at the wall top and extends above it.
    top_z = z_offset + WALL_HEIGHT + ROOF_BORDER_HEIGHT * 0.5
    runs = _boundary_runs_from_rects(perimeter_rects, unit=1.0)
    return _add_tiled_linear_trim(
        col,
        f"RoofBorder_{int(z_offset*1000)}",
        runs,
        top_z,
        ROOF_BORDER_HEIGHT,
        ROOF_BORDER_WIDTH,
        inward=True,
        atlas_category=ROOF_BORDER_TILE_CATEGORY,
        atlas_tile_id=ROOF_BORDER_TILE_ID,
        source_rects=perimeter_rects,
        align_to_wall_outer_face=True,
        end_overlap=ROOF_BORDER_WIDTH * 0.5,
    )


def add_floor_seam_bands(col, footprint_rects: List[Rect], z_offset: float):
    if not FLOOR_BAND_ENABLED or z_offset <= EPS:
        return []
    perimeter_rects = [Rect(0.0, 0.0, HOUSE_WIDTH, HOUSE_DEPTH)]
    # Make the band read as a continuation/cover strip of the seam rather than a hanging piece.
    # Center it on the seam line so it covers the joint without leaving a gap above.
    seam_z = z_offset - FLOOR_THICKNESS * 0.5
    runs = _boundary_runs_from_rects(perimeter_rects, unit=1.0)
    return _add_tiled_linear_trim(
        col,
        f"FloorBand_{int(z_offset*1000)}",
        runs,
        seam_z,
        FLOOR_BAND_HEIGHT,
        FLOOR_BAND_DEPTH,
        inward=False,
        atlas_category=FLOOR_BAND_TILE_CATEGORY,
        atlas_tile_id=FLOOR_BAND_TILE_ID,
        source_rects=perimeter_rects,
        align_to_wall_outer_face=True,
        protrude_outward=True,
        end_overlap=max(FLOOR_BAND_DEPTH, WALL_THICKNESS * 0.5 + FLOOR_BAND_DEPTH),
    )

def add_roof_railings(col, z_offset: float):
    if not RAILINGS_ENABLED:
        return []
    perimeter_rects = [Rect(0.0, 0.0, HOUSE_WIDTH, HOUSE_DEPTH)]
    runs = _boundary_runs_from_rects(perimeter_rects, unit=1.0)
    created = []
    post = max(0.02, float(RAILING_POST_SIZE))
    rail_t = max(0.01, float(RAILING_RAIL_THICKNESS))
    rail_h = max(0.35, float(RAILING_HEIGHT))
    rail_count = max(1, int(RAILING_RAIL_COUNT))
    base_z = z_offset + WALL_HEIGHT + rail_h * 0.5
    source_rects = perimeter_rects
    probe = max(0.02, max(post, WALL_THICKNESS) * 0.6)

    def _side_sign(orientation, fixed, start, end):
        mid_axis = (start + end) * 0.5
        if orientation == "H":
            inside_pos = _point_in_any_rect(mid_axis, fixed + probe, source_rects)
            inside_neg = _point_in_any_rect(mid_axis, fixed - probe, source_rects)
        else:
            inside_pos = _point_in_any_rect(fixed + probe, mid_axis, source_rects)
            inside_neg = _point_in_any_rect(fixed - probe, mid_axis, source_rects)
        if inside_pos and not inside_neg:
            return 1.0
        if inside_neg and not inside_pos:
            return -1.0
        return 1.0

    def _post_xy(orientation, fixed, axis_value, side_offset):
        if orientation == "H":
            return axis_value, fixed + side_offset
        return fixed + side_offset, axis_value

    levels = []
    if rail_count == 1:
        levels = [max(rail_t * 0.5, rail_h - rail_t * 0.5)]
    else:
        bottom = min(0.35, rail_h * 0.35)
        top = rail_h - (rail_t * 0.5)
        span = max(0.05, top - bottom)
        levels = [bottom + span * (i / (rail_count - 1)) for i in range(rail_count)]

    # Precompute side offsets for rectangle borders so each outer corner gets exactly one shared post.
    h_offsets = {}
    v_offsets = {}
    for orientation, fixed, start, end in runs:
        side_sign = _side_sign(orientation, fixed, start, end)
        side_offset = side_sign * ((WALL_THICKNESS * 0.5) - (post * 0.5))
        key = round(fixed, 6)
        if orientation == "H":
            h_offsets[key] = side_offset
        else:
            v_offsets[key] = side_offset

    min_x = 0.0
    max_x = HOUSE_WIDTH
    min_y = 0.0
    max_y = HOUSE_DEPTH

    def _corner_xy(axis_x, axis_y):
        if abs(axis_x - min_x) <= EPS:
            x = min_x + v_offsets.get(round(min_x, 6), 0.0)
        else:
            x = max_x + v_offsets.get(round(max_x, 6), 0.0)
        if abs(axis_y - min_y) <= EPS:
            y = min_y + h_offsets.get(round(min_y, 6), 0.0)
        else:
            y = max_y + h_offsets.get(round(max_y, 6), 0.0)
        return x, y

    placed_posts = set()

    def _ensure_post(name, x, y):
        key = (round(x, 6), round(y, 6))
        if key in placed_posts:
            return
        placed_posts.add(key)
        obj = add_box(col, name, x, y, base_z, post, post, rail_h)
        obj["atlas_category"] = str(RAILING_TILE_CATEGORY or "walls")
        if RAILING_TILE_ID:
            obj["atlas_tile_id"] = str(RAILING_TILE_ID)
        created.append(obj)

    for run_idx, (orientation, fixed, start, end) in enumerate(runs):
        side_offset = h_offsets.get(round(fixed, 6), 0.0) if orientation == "H" else v_offsets.get(round(fixed, 6), 0.0)
        run_len = end - start
        if run_len <= EPS:
            continue

        positions = []
        coords = []

        if orientation == "H":
            sx, sy = _corner_xy(start, fixed)
            ex, ey = _corner_xy(end, fixed)
            positions.append(sx)
            coords.append((sx, sy))
        else:
            sx, sy = _corner_xy(fixed, start)
            ex, ey = _corner_xy(fixed, end)
            positions.append(sy)
            coords.append((sx, sy))

        axis_value = start + 1.0
        interior_idx = 0
        while axis_value < end - EPS:
            x, y = _post_xy(orientation, fixed, axis_value, side_offset)
            positions.append(axis_value)
            coords.append((x, y))
            interior_idx += 1
            axis_value += 1.0

        if orientation == "H":
            positions.append(ex)
            coords.append((ex, ey))
        else:
            positions.append(ey)
            coords.append((ex, ey))

        # Create one shared post per unique coordinate, including the outer corner posts.
        for post_idx, (x, y) in enumerate(coords):
            _ensure_post(f"RailingPost_{int(z_offset*1000)}_{run_idx}_{post_idx}", x, y)

        # Create rails only between neighboring posts, so corner joints stop at the corner post.
        for level_idx, level in enumerate(levels):
            z = z_offset + WALL_HEIGHT + level
            for seg_idx in range(len(coords) - 1):
                (x0, y0) = coords[seg_idx]
                (x1, y1) = coords[seg_idx + 1]
                if orientation == "H":
                    seg_len = x1 - x0
                    if seg_len <= EPS:
                        continue
                    x = (x0 + x1) * 0.5
                    y = y0
                    obj = add_box(col, f"RailingRail_{int(z_offset*1000)}_{run_idx}_{level_idx}_{seg_idx}", x, y, z, seg_len, rail_t, rail_t)
                else:
                    seg_len = y1 - y0
                    if seg_len <= EPS:
                        continue
                    x = x0
                    y = (y0 + y1) * 0.5
                    obj = add_box(col, f"RailingRail_{int(z_offset*1000)}_{run_idx}_{level_idx}_{seg_idx}", x, y, z, rail_t, seg_len, rail_t)
                obj["atlas_category"] = str(RAILING_TILE_CATEGORY or "walls")
                if RAILING_TILE_ID:
                    obj["atlas_tile_id"] = str(RAILING_TILE_ID)
                created.append(obj)
    return created


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
            add_roof_tiles_world_aligned(col, f"Roof_{int(z_offset*1000)}_{patch_index}", patch, roof_z, FLOOR_THICKNESS, SURFACE_TILE_SIZE, roof_mat)
        else:
            add_box(col, f"Roof_{int(z_offset*1000)}_{patch_index}", patch.cx, patch.cy, roof_z, patch.w, patch.h, FLOOR_THICKNESS, roof_mat)
    # RoofBorder should follow the old simple generation logic, but only on the
    # final roof level. Intermediate exposed patches between floors should not
    # receive RoofBorder.
    is_top_roof = next_patches is None
    if is_top_roof:
        add_roof_borders(col, roof_targets, z_offset)
        add_roof_railings(col, z_offset)
    return roof_targets



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

DECALS_ENABLED = False
DECAL_MANIFEST_PATH = "//decal_atlas_v2.json"
DECAL_IMAGE_PATH = ""   # if empty, taken from decal manifest meta.source_image
DECAL_DENSITY = 0.35
DECAL_ENABLE_STREAKS = True
DECAL_ENABLE_GRIME = False
DECAL_ENABLE_GROUND_STRIPS = False
DECAL_ENABLE_CRACKS = False
DECAL_ENABLE_CORNER_DIRT = False
DECAL_ENABLE_EDGE_DIRT = False
DEBUG_LOG_ENABLED = False
DEBUG_TEXT_NAME = "FloorPlan_Debug_Log"

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
        "glass": [
            {"id": "glass_01", "x": 512, "y": 256, "w": 512, "h": 256, "tile_width_m": 2.0, "tile_height_m": 3.0}
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
        "roof_borders": [
            {"id": "roof_border_01", "x": 0, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 0.2}
        ],
        "floor_bands": [
            {"id": "floor_band_01", "x": 256, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 0.1}
        ],
        "railings": [
            {"id": "railing_01", "x": 512, "y": 0, "w": 256, "h": 256, "tile_width_m": 1.0, "tile_height_m": 1.0}
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

def _assign_uv_to_bbox(obj, region, atlas_w, atlas_h, rotate_cw_90=False):
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="AtlasUV")
    uv_layer = mesh.uv_layers.active.data

    min_u = region["x"] / atlas_w
    max_u = (region["x"] + region["w"]) / atlas_w
    # image origin in JSON is top-left; Blender UV origin is bottom-left
    min_v = 1.0 - (region["y"] + region["h"]) / atlas_h
    max_v = 1.0 - region["y"] / atlas_h

    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    minz, maxz = min(zs), max(zs)

    def remap(val, a, b, c, d):
        if abs(b - a) < 1e-8:
            return (c + d) * 0.5
        t = (val - a) / (b - a)
        return c + (d - c) * t

    for poly in mesh.polygons:
        n = poly.normal
        use_xy = abs(n.z) > 0.7
        use_xz = abs(n.y) > 0.7

        for li in poly.loop_indices:
            v = mesh.vertices[mesh.loops[li].vertex_index].co

            if use_xy:
                u = remap(v.x, minx, maxx, min_u, max_u)
                vv = remap(v.y, miny, maxy, min_v, max_v)
            elif use_xz:
                u = remap(v.x, minx, maxx, min_u, max_u)
                vv = remap(v.z, minz, maxz, min_v, max_v)
            else:
                u = remap(v.y, miny, maxy, min_u, max_u)
                vv = remap(v.z, minz, maxz, min_v, max_v)

            if rotate_cw_90:
                local_u = 0.5 if abs(max_u - min_u) < 1e-8 else (u - min_u) / (max_u - min_u)
                local_v = 0.5 if abs(max_v - min_v) < 1e-8 else (vv - min_v) / (max_v - min_v)

                rot_u = local_v
                rot_v = 1.0 - local_u

                u = min_u + (max_u - min_u) * rot_u
                vv = min_v + (max_v - min_v) * rot_v

            uv_layer[li].uv = (u, vv)


def _assign_uv_to_world_basis(obj, region, atlas_w, atlas_h, tangent_world, up_world=Vector((0.0, 0.0, 1.0))):
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="AtlasUV")
    uv_layer = mesh.uv_layers.active.data

    tangent = tangent_world.normalized()
    up = up_world.normalized()

    min_u = region["x"] / atlas_w
    max_u = (region["x"] + region["w"]) / atlas_w
    # image origin in JSON is top-left; Blender UV origin is bottom-left
    min_v = 1.0 - (region["y"] + region["h"]) / atlas_h
    max_v = 1.0 - region["y"] / atlas_h

    world_verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    us = [co.dot(tangent) for co in world_verts]
    vs = [co.dot(up) for co in world_verts]
    min_proj_u, max_proj_u = min(us), max(us)
    min_proj_v, max_proj_v = min(vs), max(vs)

    def remap(val, a, b, c, d):
        if abs(b - a) < 1e-8:
            return (c + d) * 0.5
        t = (val - a) / (b - a)
        return c + (d - c) * t

    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            co = world_verts[vi]
            u = remap(co.dot(tangent), min_proj_u, max_proj_u, min_u, max_u)
            vv = remap(co.dot(up), min_proj_v, max_proj_v, min_v, max_v)
            uv_layer[li].uv = (u, vv)

def apply_atlas_stage1(collection_name: str, seed_value: int, manifest_override: Optional[dict] = None, persist_default_manifest: bool = True):
    manifest = manifest_override if manifest_override is not None else _load_json(ATLAS_MANIFEST_PATH)
    if manifest is None:
        if persist_default_manifest:
            manifest = _write_default_atlas_manifest(ATLAS_MANIFEST_PATH)
        else:
            manifest = _default_atlas_manifest()

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
        "glass": manifest.get("glass", manifest.get("wall_windows", [])),
        "wall_windows": manifest.get("wall_windows", []),
        "wall_doors": manifest.get("wall_doors", []),
        "floors": manifest.get("floors", []),
        "roofs": manifest.get("roofs", []),
        "stairs": manifest.get("stairs", []),
        "stair_landings": manifest.get("stair_landings", []),
        "roof_borders": manifest.get("roof_borders", manifest.get("walls", [])),
        "floor_bands": manifest.get("floor_bands", manifest.get("walls", [])),
        "railings": manifest.get("railings", manifest.get("walls", [])),
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

        # Generated window glass uses a dedicated glass atlas category.
        if name.startswith("GLZ_") or obj.get("generated_glass"):
            category = "glass"
        if name.startswith("RoofBorder_"):
            category = "roof_borders"
        elif name.startswith("FloorBand_"):
            category = "floor_bands"
        elif name.startswith("Roof_"):
            category = "roofs"
        elif name.startswith("FLR_") or name.startswith("Base_"):
            category = "floors"
        elif name.startswith("StairStep"):
            category = "stairs"
        elif name.startswith("StairLanding") or name.startswith("StairTopPlatform"):
            category = "stair_landings"
        elif name.startswith("RailingPost_") or name.startswith("RailingRail_"):
            category = "railings"
        elif name.startswith("OWD_") or name.startswith("EntryDoor_") or obj.get("generated_entry_door"):
            category = "wall_doors"
        elif name.startswith("OWW_"):
            category = "walls"
        elif name.startswith("OW_"):
            category = "walls"
        elif ATLAS_INCLUDE_INTERIOR_WALLS and (name.startswith("IW_") or name.startswith("SW_")):
            category = "walls"

        override_category = obj.get("atlas_category")
        override_tile_id = obj.get("atlas_tile_id")
        if override_category:
            category = str(override_category)

        if not category:
            continue
        regions = cats.get(category, [])
        region = None
        if override_tile_id:
            override_tile_id = str(override_tile_id)
            for entry in regions:
                if entry.get("id") == override_tile_id:
                    region = entry
                    break
        if region is None:
            region = _atlas_pick(regions, seed_value, f"{name}:{category}")
        if not region:
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat_for(category))
        _assign_uv_to_bbox(obj, region, atlas_w, atlas_h)

    print("[Atlas] Stage 1 materials assigned.")



def _debug_text_block():
    text = bpy.data.texts.get(DEBUG_TEXT_NAME)
    if text is None:
        text = bpy.data.texts.new(DEBUG_TEXT_NAME)
    return text


def _debug_reset():
    if not DEBUG_LOG_ENABLED:
        return
    _debug_text_block().clear()


def _debug_log(message: str):
    if not DEBUG_LOG_ENABLED:
        return
    line = f"[FloorPlan] {message}"
    print(line)
    _debug_text_block().write(line + "\n")


def _resolve_decal_walls(col):
    walls = []
    for obj in col.objects:
        if obj.type != 'MESH':
            continue
        if obj.get('is_decal') or obj.get('generated_glass') or obj.get('generated_entry_door'):
            continue
        if obj.name.startswith(('OW_', 'OWW_', 'SEG_')):
            walls.append(obj)
    return walls


def _ensure_decal_collection(parent_name: str):
    name = f"{parent_name}_DECALS"
    root = bpy.context.scene.collection
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        root.children.link(col)
    return col


def _ensure_decal_material(mat_name: str, image):
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)

    out = nt.nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (760, 0)

    mix = nt.nodes.new(type="ShaderNodeMixShader")
    mix.location = (520, 0)

    transparent = nt.nodes.new(type="ShaderNodeBsdfTransparent")
    transparent.location = (260, 120)

    bsdf = nt.nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (260, -40)
    bsdf.inputs['Roughness'].default_value = 0.95
    bsdf.inputs['Metallic'].default_value = 0.0

    tex = nt.nodes.new(type="ShaderNodeTexImage")
    tex.location = (-520, 40)
    tex.image = image

    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], mix.inputs['Fac'])
    nt.links.new(transparent.outputs['BSDF'], mix.inputs[1])
    nt.links.new(bsdf.outputs['BSDF'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])

    mat.blend_method = 'BLEND'
    mat.shadow_method = 'NONE'
    mat.use_backface_culling = False
    mat.show_transparent_back = True
    return mat

def _collection_bbox_and_center(col):
    xs=[]; ys=[]; zs=[]
    for obj in col.objects:
        if obj.type != 'MESH':
            continue
        for c in obj.bound_box:
            wc = obj.matrix_world @ Vector(c)
            xs.append(wc.x); ys.append(wc.y); zs.append(wc.z)
    if not xs:
        return None, Vector((0.0,0.0,0.0))
    mn = Vector((min(xs), min(ys), min(zs)))
    mx = Vector((max(xs), max(ys), max(zs)))
    return (mn, mx), (mn + mx) * 0.5


def _normalize_under_roof_region(entry, idx, default_width_px=216, default_height_px=216, default_height_m=0.5):
    if not isinstance(entry, dict):
        return None

    def _to_int(value, fallback=None):
        try:
            if value is None:
                return fallback
            iv = int(value)
            return iv
        except Exception:
            return fallback

    x = _to_int(entry.get("x"), 0)
    y = _to_int(entry.get("y"), 0)

    width_candidates = [
        entry.get("w"),
        entry.get("width"),
        entry.get("tile_px_w"),
        entry.get("g"),
    ]
    w = None
    for candidate in width_candidates:
        w = _to_int(candidate, None)
        if w and w > 0:
            break
    if not w or w <= 0:
        w = default_width_px

    height_candidates = [
        entry.get("h"),
        entry.get("height"),
        entry.get("tile_px_h"),
    ]
    h = None
    for candidate in height_candidates:
        h = _to_int(candidate, None)
        if h and h > 0:
            break
    if not h or h <= 0:
        h = default_height_px

    tile_width_m = float(entry.get("tile_width_m", 1.0) or 1.0)

    height_m_candidates = [
        entry.get("decal_height_m"),
        entry.get("height_m"),
        entry.get("tile_height_m"),
    ]
    tile_height_m = None
    for candidate in height_m_candidates:
        try:
            if candidate is None:
                continue
            fv = float(candidate)
            if fv > 0.0:
                tile_height_m = fv
                break
        except Exception:
            continue
    if tile_height_m is None:
        tile_height_m = float(default_height_m if default_height_m and default_height_m > 0.0 else 0.5)

    return {
        "id": str(entry.get("id", f"under_roof_{idx:02d}")),
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "tile_width_m": tile_width_m,
        "tile_height_m": tile_height_m,
    }


def _under_roof_regions_from_manifest(manifest):
    raw_entries = []
    default_height_m = 0.5
    if isinstance(manifest, dict):
        meta = manifest.get("meta", {}) if isinstance(manifest.get("meta"), dict) else {}
        for candidate in [
            meta.get("under_roof_decal_height_m"),
            meta.get("decal_height_m"),
            manifest.get("under_roof_decal_height_m"),
            manifest.get("decal_height_m"),
        ]:
            try:
                if candidate is None:
                    continue
                fv = float(candidate)
                if fv > 0.0:
                    default_height_m = fv
                    break
            except Exception:
                continue

        if isinstance(manifest.get("under_roof_drips"), list):
            raw_entries = manifest.get("under_roof_drips", [])
        elif isinstance(manifest.get("roof_drips"), list):
            raw_entries = manifest.get("roof_drips", [])
        elif isinstance(manifest.get("streaks"), list):
            raw_entries = manifest.get("streaks", [])

    regions = []
    for idx, entry in enumerate(raw_entries):
        region = _normalize_under_roof_region(entry, idx, default_height_m=default_height_m)
        if region is not None:
            regions.append(region)
    return regions


def _wall_decal_world_basis(wall_obj, center):
    dims = wall_obj.dimensions
    thin_x = dims.x <= dims.y
    up_world = Vector((0.0, 0.0, 1.0))

    if thin_x:
        outward = -1.0 if wall_obj.location.x < center.x else 1.0
        normal_world = Vector((outward, 0.0, 0.0))
        wall_span = max(dims.y, 0.2)
    else:
        outward = -1.0 if wall_obj.location.y < center.y else 1.0
        normal_world = Vector((0.0, outward, 0.0))
        wall_span = max(dims.x, 0.2)

    # Keep a right-handed basis for every facade.
    # tangent x up == normal, so opposite facades don't get mirrored UVs.
    tangent_world = up_world.cross(normal_world).normalized()

    return thin_x, wall_span, tangent_world, up_world, normal_world


def _create_wall_decal_plane(target_col, wall_obj, region, atlas_w, atlas_h, image, category, seed_tag, center, *, width_override=None, height_override=None, anchor_top_z=None, tangent_offset=0.0):
    dims = wall_obj.dimensions
    eps = 0.03
    thin_x, wall_span, tangent_world, up_world, normal_world = _wall_decal_world_basis(wall_obj, center)

    width = float(width_override if width_override is not None else max(region.get("tile_width_m", 1.0), 0.2))
    height = float(height_override if height_override is not None else max(region.get("tile_height_m", 1.0), 0.2))

    if anchor_top_z is None:
        anchor_top_z = wall_obj.location.z + dims.z * 0.5
    z_center = anchor_top_z - height * 0.5

    loc = wall_obj.location.copy()
    rot_basis = Matrix((tangent_world, up_world, normal_world)).transposed()
    rot = rot_basis.to_euler('XYZ')

    loc += tangent_world * tangent_offset
    loc += normal_world * ((dims.x * 0.5 if thin_x else dims.y * 0.5) + eps)
    loc.z = z_center

    bpy.ops.mesh.primitive_plane_add(location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = f"DECAL_{category}_{wall_obj.name}_{abs(hash(seed_tag)) % 99999}"
    obj.scale = (max(0.08, width * 0.5), max(0.08, height * 0.5), 1.0)
    obj.show_in_front = True
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    link_obj(obj, target_col)
    obj["atlas_category"] = category
    obj["is_decal"] = True
    obj["decal_target"] = wall_obj.name
    obj["decal_basis"] = "world_tangent_up_normal_v2"
    obj["decal_tangent_world"] = tuple(tangent_world)
    obj["decal_normal_world"] = tuple(normal_world)
    obj.data.materials.clear()
    obj.data.materials.append(_ensure_decal_material(f"Decal_{category}", image))
    _assign_uv_to_world_basis(obj, region, atlas_w, atlas_h, tangent_world, up_world)
    return obj


def apply_decals_stage1(collection_name: str, seed_value: int):
    _debug_reset()
    _debug_log(f"Decal pipeline start: collection={collection_name}, seed={seed_value}")
    manifest = _load_json(DECAL_MANIFEST_PATH)
    if manifest is None:
        _debug_log(f"Decal manifest not found: {DECAL_MANIFEST_PATH}")
        print('[Decal] Manifest not found, skipping decals.')
        return

    meta = manifest.get('meta', {})
    atlas_w = meta.get('atlas_width', 1024)
    atlas_h = meta.get('atlas_height', 1024)
    img_path = DECAL_IMAGE_PATH or meta.get('source_image', '')
    _debug_log(f"Decal manifest loaded: atlas={atlas_w}x{atlas_h}, image={img_path}")
    image = _load_atlas_image(img_path)
    if image is None:
        _debug_log(f"Decal image not found: {img_path}")
        print('[Decal] Image not found, skipping decals.')
        return

    col = bpy.data.collections.get(collection_name)
    if col is None:
        _debug_log(f"Collection not found: {collection_name}")
        return

    bbox, center = _collection_bbox_and_center(col)
    if bbox is None:
        _debug_log('Collection bbox is empty, skipping decals.')
        return

    decal_col = _ensure_decal_collection(collection_name)
    for obj in list(decal_col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in list(col.objects):
        if obj.get('is_decal'):
            bpy.data.objects.remove(obj, do_unlink=True)

    walls = _resolve_decal_walls(col)
    regions = _under_roof_regions_from_manifest(manifest)
    if not DECAL_ENABLE_STREAKS or not regions:
        _debug_log('Under-roof drips disabled or manifest has no valid under_roof_drips/streaks entries.')
        print('[Decal] Under-roof drips disabled or no valid entries found.')
        return

    rng = random.Random(seed_value + 99173)
    tile_width_m = 1.0
    created_count = 0

    _debug_log(f"Candidate walls before top-band filter: {len(walls)}")
    _debug_log(f"Under-roof regions: {len(regions)}")

    wall_infos = []
    top_bands = {}
    band_step = 0.1
    for wall in walls:
        dims = wall.dimensions
        wall_span_guess = max(dims.x, dims.y)
        wall_thickness_guess = min(dims.x, dims.y)
        # Do not drop short top strips above windows: they still belong to the
        # upper facade band and must receive under-roof drips. We only filter
        # out near-square pieces and extremely tiny wall fragments.
        if wall_span_guess < 0.2 or dims.z < 0.08 or wall_thickness_guess > wall_span_guess * 0.75:
            _debug_log(f"Wall {wall.name}: skip geometry filter span={wall_span_guess:.3f} z={dims.z:.3f} thick={wall_thickness_guess:.3f}")
            continue
        _, wall_span, _, _, _ = _wall_decal_world_basis(wall, center)
        wall_top_z = wall.location.z + dims.z * 0.5
        band_key = round(wall_top_z / band_step) * band_step
        info = {
            'wall': wall,
            'dims': dims,
            'wall_span': wall_span,
            'wall_top_z': wall_top_z,
            'band_key': band_key,
        }
        wall_infos.append(info)
        top_bands[band_key] = top_bands.get(band_key, 0.0) + wall_span

    if not wall_infos:
        _debug_log('No walls left after geometry filter.')
        print('[Decal] No suitable walls for under-roof drips.')
        return

    strongest_band_span = max(top_bands.values()) if top_bands else 0.0
    valid_band_keys = {
        key for key, total_span in top_bands.items()
        if total_span >= max(2.0, strongest_band_span * 0.35)
    }
    wall_infos = [info for info in wall_infos if info['band_key'] in valid_band_keys]

    _debug_log(f"Top bands: {sorted((round(k,3), round(v,3)) for k,v in top_bands.items())}")
    _debug_log(f"Valid top bands: {sorted(round(v,3) for v in valid_band_keys)}")
    _debug_log(f"Candidate walls after top-band filter: {len(wall_infos)}")

    for info in wall_infos:
        wall = info['wall']
        dims = info['dims']
        wall_span = info['wall_span']
        wall_top_z = info['wall_top_z']
        tile_count = max(1, int(math.floor((wall_span + 1e-6) / tile_width_m)))
        used_span = tile_count * tile_width_m
        start_offset = -used_span * 0.5 + tile_width_m * 0.5

        _debug_log(f"Wall {wall.name}: span={wall_span:.3f}m, tile_count={tile_count}, top_z={wall_top_z:.3f}")

        for tile_index in range(tile_count):
            tangent_offset = start_offset + tile_index * tile_width_m
            region = rng.choice(regions)
            width_world = tile_width_m
            requested_height_world = float(region.get("tile_height_m", 0.5) or 0.5)
            height_world = min(requested_height_world, max(0.05, dims.z - 0.02))

            obj = _create_wall_decal_plane(
                decal_col,
                wall,
                region,
                atlas_w,
                atlas_h,
                image,
                'under_roof_drips',
                f'{seed_value}:{wall.name}:under_roof:{tile_index}:{region.get("id", "tile")}',
                center,
                width_override=width_world,
                height_override=height_world,
                anchor_top_z=wall_top_z,
                tangent_offset=tangent_offset,
            )
            obj['decal_anchor'] = 'roof_bottom'
            obj['decal_tile_width_m'] = width_world
            obj['decal_fixed_height_m'] = height_world
            created_count += 1
            _debug_log(f"  created under-roof drip wall={wall.name} tile={tile_index} region={region.get('id', '<no-id>')} offset={tangent_offset:.3f}")

    _debug_log(f"Decals assigned total: {created_count}")
    print(f'[Decal] Under-roof drips assigned: {created_count}')


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
        rooms, corridor, stair, open_void = quantize_layout_to_meter_grid(rooms, corridor, stair=stair, open_void=open_void)

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
        add_floor_seam_bands(col, current_patches, z_offset)
        add_external_corner_posts(col, z_offset)

        inherited_void = spec["stair"].rect if spec["stair"] is not None else None

        add_text(col, f"Floor {floor_index + 1}", 0.2, spec["depth"] + 0.05, z_offset + 0.03, size=0.24)

    add_text(col, f"Seed: {seed} | Mode: {BUILDING_MODE} | Shape: {SHAPE_MODE}", 0.2, max_depth + 0.35, 0.03, size=0.25)
    add_text(col, f"Floors: {floors}", 2.3, max_depth + 0.35, 0.03, size=0.28)

    if ATLAS_ENABLED:
        apply_atlas_stage1(COLLECTION_NAME, seed)
    if DECALS_ENABLED:
        apply_decals_stage1(COLLECTION_NAME, seed)

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
    "DECALS_ENABLED": DECALS_ENABLED,
    "DECAL_MANIFEST_PATH": DECAL_MANIFEST_PATH,
    "DECAL_IMAGE_PATH": DECAL_IMAGE_PATH,
    "DECAL_DENSITY": DECAL_DENSITY,
    "DECAL_ENABLE_STREAKS": DECAL_ENABLE_STREAKS,
    "DECAL_ENABLE_GRIME": DECAL_ENABLE_GRIME,
    "DECAL_ENABLE_GROUND_STRIPS": DECAL_ENABLE_GROUND_STRIPS,
    "DECAL_ENABLE_CRACKS": DECAL_ENABLE_CRACKS,
    "DECAL_ENABLE_CORNER_DIRT": DECAL_ENABLE_CORNER_DIRT,
    "DECAL_ENABLE_EDGE_DIRT": DECAL_ENABLE_EDGE_DIRT,
    "DEBUG_LOG_ENABLED": DEBUG_LOG_ENABLED,
    "MODULAR_TILES_ENABLED": MODULAR_TILES_ENABLED,
    "WALL_TILE_WIDTH": WALL_TILE_WIDTH,
    "SURFACE_TILE_SIZE": SURFACE_TILE_SIZE,
    "ROOF_BORDER_ENABLED": ROOF_BORDER_ENABLED,
    "ROOF_BORDER_WIDTH": ROOF_BORDER_WIDTH,
    "ROOF_BORDER_HEIGHT": ROOF_BORDER_HEIGHT,
    "ROOF_BORDER_TILE_CATEGORY": ROOF_BORDER_TILE_CATEGORY,
    "ROOF_BORDER_TILE_ID": ROOF_BORDER_TILE_ID,
    "FLOOR_BAND_ENABLED": FLOOR_BAND_ENABLED,
    "FLOOR_BAND_DEPTH": FLOOR_BAND_DEPTH,
    "FLOOR_BAND_HEIGHT": FLOOR_BAND_HEIGHT,
    "FLOOR_BAND_TILE_CATEGORY": FLOOR_BAND_TILE_CATEGORY,
    "FLOOR_BAND_TILE_ID": FLOOR_BAND_TILE_ID,
    "RAILINGS_ENABLED": RAILINGS_ENABLED,
    "RAILING_HEIGHT": RAILING_HEIGHT,
    "RAILING_POST_SIZE": RAILING_POST_SIZE,
    "RAILING_RAIL_THICKNESS": RAILING_RAIL_THICKNESS,
    "RAILING_RAIL_COUNT": RAILING_RAIL_COUNT,
    "RAILING_TILE_CATEGORY": RAILING_TILE_CATEGORY,
    "RAILING_TILE_ID": RAILING_TILE_ID,
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
    global DECALS_ENABLED, DECAL_MANIFEST_PATH, DECAL_IMAGE_PATH, DECAL_DENSITY, DECAL_ENABLE_STREAKS, DECAL_ENABLE_GRIME, DECAL_ENABLE_GROUND_STRIPS, DECAL_ENABLE_CRACKS, DECAL_ENABLE_CORNER_DIRT, DECAL_ENABLE_EDGE_DIRT, DEBUG_LOG_ENABLED
    global MODULAR_TILES_ENABLED, WALL_TILE_WIDTH, SURFACE_TILE_SIZE
    global ROOF_BORDER_ENABLED, ROOF_BORDER_WIDTH, ROOF_BORDER_HEIGHT, ROOF_BORDER_TILE_CATEGORY, ROOF_BORDER_TILE_ID
    global FLOOR_BAND_ENABLED, FLOOR_BAND_DEPTH, FLOOR_BAND_HEIGHT, FLOOR_BAND_TILE_CATEGORY, FLOOR_BAND_TILE_ID
    global RAILINGS_ENABLED, RAILING_HEIGHT, RAILING_POST_SIZE, RAILING_RAIL_THICKNESS, RAILING_RAIL_COUNT, RAILING_TILE_CATEGORY, RAILING_TILE_ID

    for key, value in settings.items():
        if key in globals():
            globals()[key] = value

    FLOOR_TO_FLOOR_HEIGHT = WALL_HEIGHT + FLOOR_THICKNESS
    WALL_TILE_WIDTH = max(0.05, WALL_TILE_WIDTH)
    SURFACE_TILE_SIZE = max(0.05, SURFACE_TILE_SIZE)
    ROOF_BORDER_WIDTH = max(0.01, ROOF_BORDER_WIDTH)
    ROOF_BORDER_HEIGHT = max(0.01, ROOF_BORDER_HEIGHT)
    FLOOR_BAND_DEPTH = max(0.01, FLOOR_BAND_DEPTH)
    FLOOR_BAND_HEIGHT = max(0.01, FLOOR_BAND_HEIGHT)
    STRICT_EDGE_TOL = max(WALL_THICKNESS * 0.75, 0.22)


def generate_from_settings(settings: dict):
    apply_settings(settings)
    generate()

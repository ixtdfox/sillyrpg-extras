import math
import random

import bpy
from mathutils import Vector

from .batching import MeshBatcher
from .utils import (
    COLLECTION_NAME,
    HANDLE_NAME,
    ROOT_NAME,
    clear_generated_objects,
    ensure_collection,
    ensure_empty,
    ensure_materials,
)


class RectCell:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1


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


class BuildingGenerator:
    def __init__(self):
        self.col = ensure_collection(COLLECTION_NAME)
        self.mats = ensure_materials()
        self.batch = MeshBatcher()
        self.fast_mode = False
        self.detail_scale = 1.0

    def get_state(self):
        s = bpy.context.scene.pb_settings
        root = ensure_empty(ROOT_NAME, 'ARROWS', (0, 0, 0))
        handle = ensure_empty(HANDLE_NAME, 'CUBE', (s.width_m, s.depth_m, 0))
        return s, root, handle

    def local_to_world(self, s, root, x, y, z):
        return Vector((
            root.location.x + x - s.width_m * 0.5,
            root.location.y + y - s.depth_m * 0.5,
            root.location.z + z,
        ))

    def stair_zone(self, s):
        tile = s.tile_size
        w = max(tile * 2, math.ceil(s.stairs_width / tile) * tile)
        d = tile * 4
        return RectCell(tile, tile, tile + w, tile + d)

    def opening_from_stair_zone(self, s, zone):
        m = s.stair_opening_margin
        return (
            max(0.0, zone.x0 - m),
            max(0.0, zone.y0 - m),
            min(s.width_m, zone.x1 + m),
            min(s.depth_m, zone.y1 + m),
        )

    def clear(self):
        clear_generated_objects(self.col)

    def add_box(self, group, sx, sy, sz, center):
        self.batch.add_box(group, sx, sy, sz, center)

    def add_ring_parts(self, s, root, z_center, thickness, x0, y0, x1, y1, group):
        if y0 > 0:
            self.add_box(group, s.width_m, y0, thickness, self.local_to_world(s, root, s.width_m * 0.5, y0 * 0.5, z_center))
        if y1 < s.depth_m:
            sy = s.depth_m - y1
            self.add_box(group, s.width_m, sy, thickness, self.local_to_world(s, root, s.width_m * 0.5, y1 + sy * 0.5, z_center))
        if x0 > 0 and y1 > y0:
            sx = x0
            sy = y1 - y0
            self.add_box(group, sx, sy, thickness, self.local_to_world(s, root, x0 * 0.5, y0 + sy * 0.5, z_center))
        if x1 < s.width_m and y1 > y0:
            sx = s.width_m - x1
            sy = y1 - y0
            self.add_box(group, sx, sy, thickness, self.local_to_world(s, root, x1 + sx * 0.5, y0 + sy * 0.5, z_center))

    def add_window_parts(self, s, root, wx, wy, z_floor, axis, outward_sign):
        sill = s.window_sill_h
        head = s.window_head_h
        tile = s.tile_size
        glass_major = tile * 0.76
        side = (tile - glass_major) * 0.5
        zc = root.location.z + z_floor + sill + (head - sill) * 0.5
        if axis == "x":
            self.add_box("wall", tile, s.wall_thickness, sill, (wx, wy, root.location.z + z_floor + sill * 0.5))
            self.add_box("trim", tile, s.wall_thickness, s.floor_height - head, (wx, wy, root.location.z + z_floor + head + (s.floor_height - head) * 0.5))
            self.add_box("trim", side, s.wall_thickness, head - sill, (wx - glass_major * 0.5 - side * 0.5, wy, zc))
            self.add_box("trim", side, s.wall_thickness, head - sill, (wx + glass_major * 0.5 + side * 0.5, wy, zc))
            self.add_box("glass", glass_major, s.wall_thickness * 0.35, head - sill, (wx, wy + outward_sign * s.wall_thickness * 0.25, zc))
        else:
            self.add_box("wall", s.wall_thickness, tile, sill, (wx, wy, root.location.z + z_floor + sill * 0.5))
            self.add_box("trim", s.wall_thickness, tile, s.floor_height - head, (wx, wy, root.location.z + z_floor + head + (s.floor_height - head) * 0.5))
            self.add_box("trim", s.wall_thickness, side, head - sill, (wx, wy - glass_major * 0.5 - side * 0.5, zc))
            self.add_box("trim", s.wall_thickness, side, head - sill, (wx, wy + glass_major * 0.5 + side * 0.5, zc))
            self.add_box("glass", s.wall_thickness * 0.35, glass_major, head - sill, (wx + outward_sign * s.wall_thickness * 0.25, wy, zc))

    def build_outer_walls(self, s, root, z_floor, floor_index, rng):
        entry_ix = int(s.width_m // s.tile_size // 2)

        x = 0.0
        ix = 0
        while x < s.width_m - 1e-6:
            cx = x + s.tile_size * 0.5
            p = self.local_to_world(s, root, cx, 0.0, z_floor)
            wx, wy = p.x, p.y - s.wall_thickness * 0.5
            if floor_index == 0 and ix == entry_ix:
                dw = s.door_width
                dh = s.door_height
                side = (s.tile_size - dw) * 0.5
                if side > 0.05:
                    self.add_box("trim", side, s.wall_thickness, dh, (wx - dw * 0.5 - side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
                    self.add_box("trim", side, s.wall_thickness, dh, (wx + dw * 0.5 + side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
                top_h = s.floor_height - dh
                if top_h > 0.05:
                    self.add_box("trim", s.tile_size, s.wall_thickness, top_h, (wx, wy, root.location.z + z_floor + dh + top_h * 0.5))
                self.add_box("glass", dw * 0.9, s.wall_thickness * 0.35, dh * 0.92, (wx, wy + s.wall_thickness * 0.12, root.location.z + z_floor + dh * 0.5))
            else:
                kind = "window" if (ix % 2 == 0 or rng.random() < 0.55) else "solid"
                if kind == "solid":
                    self.add_box("wall", s.tile_size, s.wall_thickness, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
                else:
                    self.add_window_parts(s, root, wx, wy, z_floor, "x", +1)
            x += s.tile_size
            ix += 1

        x = 0.0
        ix = 0
        while x < s.width_m - 1e-6:
            cx = x + s.tile_size * 0.5
            p = self.local_to_world(s, root, cx, s.depth_m, z_floor)
            wx, wy = p.x, p.y + s.wall_thickness * 0.5
            kind = "window" if (ix % 2 == 1 or rng.random() < 0.35) else "solid"
            if kind == "solid":
                self.add_box("wall", s.tile_size, s.wall_thickness, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
            else:
                self.add_window_parts(s, root, wx, wy, z_floor, "x", -1)
            x += s.tile_size
            ix += 1

        y = 0.0
        iy = 0
        side_prob = 0.45 if self.fast_mode else 0.7
        while y < s.depth_m - 1e-6:
            cy = y + s.tile_size * 0.5
            p = self.local_to_world(s, root, 0.0, cy, z_floor)
            wx, wy = p.x - s.wall_thickness * 0.5, p.y
            kind = "window" if (iy % 2 == 0 and rng.random() < side_prob) else "solid"
            if kind == "solid":
                self.add_box("wall", s.wall_thickness, s.tile_size, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
            else:
                self.add_window_parts(s, root, wx, wy, z_floor, "y", -1)
            y += s.tile_size
            iy += 1

        y = 0.0
        iy = 0
        while y < s.depth_m - 1e-6:
            cy = y + s.tile_size * 0.5
            p = self.local_to_world(s, root, s.width_m, cy, z_floor)
            wx, wy = p.x + s.wall_thickness * 0.5, p.y
            kind = "window" if (iy % 2 == 1 and rng.random() < side_prob) else "solid"
            if kind == "solid":
                self.add_box("wall", s.wall_thickness, s.tile_size, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
            else:
                self.add_window_parts(s, root, wx, wy, z_floor, "y", +1)
            y += s.tile_size
            iy += 1

    def build_inner_walls(self, s, root, z_floor, rooms, doors, zone):
        lookup_v = {}
        lookup_h = {}
        for ori, fixed, center in doors:
            if ori == "V":
                lookup_v.setdefault(round(fixed, 3), []).append(center)
            else:
                lookup_h.setdefault(round(fixed, 3), []).append(center)

        for ori, a, b, fixed, s0, s1 in build_adjacency(rooms):
            if ori == "V" and zone.x0 < fixed < zone.x1 and not (s1 <= zone.y0 or s0 >= zone.y1):
                continue
            if ori == "H" and zone.y0 < fixed < zone.y1 and not (s1 <= zone.x0 or s0 >= zone.x1):
                continue

            p = s0
            while p < s1 - 1e-6:
                tc = p + s.tile_size * 0.5
                door_centers = lookup_v.get(round(fixed, 3), []) if ori == "V" else lookup_h.get(round(fixed, 3), [])
                make_door = any(abs(tc - dc) <= s.tile_size * 0.51 for dc in door_centers)

                if ori == "V":
                    wp = self.local_to_world(s, root, fixed, tc, z_floor)
                    wx, wy = wp.x, wp.y
                    if make_door:
                        side = max(0.0, (s.tile_size - s.door_width) * 0.5)
                        if side > 0.05:
                            self.add_box("trim", s.wall_thickness, side, s.door_height, (wx, wy - s.door_width * 0.5 - side * 0.5, root.location.z + z_floor + s.door_height * 0.5))
                            self.add_box("trim", s.wall_thickness, side, s.door_height, (wx, wy + s.door_width * 0.5 + side * 0.5, root.location.z + z_floor + s.door_height * 0.5))
                        top_h = s.floor_height - s.door_height
                        if top_h > 0.05:
                            self.add_box("wall", s.wall_thickness, s.tile_size, top_h, (wx, wy, root.location.z + z_floor + s.door_height + top_h * 0.5))
                    else:
                        self.add_box("trim", s.wall_thickness, s.tile_size, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
                else:
                    wp = self.local_to_world(s, root, tc, fixed, z_floor)
                    wx, wy = wp.x, wp.y
                    if make_door:
                        side = max(0.0, (s.tile_size - s.door_width) * 0.5)
                        if side > 0.05:
                            self.add_box("trim", side, s.wall_thickness, s.door_height, (wx - s.door_width * 0.5 - side * 0.5, wy, root.location.z + z_floor + s.door_height * 0.5))
                            self.add_box("trim", side, s.wall_thickness, s.door_height, (wx + s.door_width * 0.5 + side * 0.5, wy, root.location.z + z_floor + s.door_height * 0.5))
                        top_h = s.floor_height - s.door_height
                        if top_h > 0.05:
                            self.add_box("wall", s.tile_size, s.wall_thickness, top_h, (wx, wy, root.location.z + z_floor + s.door_height + top_h * 0.5))
                    else:
                        self.add_box("trim", s.tile_size, s.wall_thickness, s.floor_height, (wx, wy, root.location.z + z_floor + s.floor_height * 0.5))
                p += s.tile_size

    def build_stairs(self, s, root, z_floor, zone):
        clear_h = s.floor_height
        rise = s.stairs_rise_step
        run = s.stairs_run_step
        stair_w = min(s.stairs_width, (zone.x1 - zone.x0) - 0.2)
        n_steps = max(1, math.ceil(clear_h / rise))
        exact_rise = clear_h / n_steps
        first = n_steps // 2
        second = n_steps - first
        landing_depth = 1.0
        x_mid = (zone.x0 + zone.x1) * 0.5
        y_start = zone.y0 + 0.35
        for i in range(first):
            z = z_floor + exact_rise * (i + 0.5)
            y = y_start + run * i
            self.add_box("floor", stair_w, run, exact_rise, self.local_to_world(s, root, x_mid, y, z))
        landing_y = y_start + run * first + landing_depth * 0.5
        landing_z = z_floor + exact_rise * first + 0.05
        self.add_box("floor", stair_w, landing_depth, 0.10, self.local_to_world(s, root, x_mid, landing_y, landing_z))
        y2 = y_start + run * first + landing_depth
        for i in range(second):
            z = z_floor + exact_rise * (first + i + 0.5)
            y = y2 + run * i
            self.add_box("floor", stair_w, run, exact_rise, self.local_to_world(s, root, x_mid, y, z))

    def build(self, quality="full"):
        s, root, handle = self.get_state()
        self.fast_mode = (quality == "preview")
        self.detail_scale = s.preview_detail_scale if self.fast_mode else 1.0
        self.batch = MeshBatcher()

        handle.location.x = root.location.x + s.width_m
        handle.location.y = root.location.y + s.depth_m
        handle.location.z = root.location.z

        self.clear()

        rng = random.Random(s.seed)
        zone = self.stair_zone(s)
        room_count = max(1, int(round(s.room_count * (0.5 if self.fast_mode else 1.0))))
        rooms = split_rectangles(s.width_m, s.depth_m, room_count, s.tile_size, s.seed)
        doors = choose_connected_doors(rooms, s.seed)

        pad = s.lot_padding
        self.add_box("floor", s.width_m + pad * 2, s.depth_m + pad * 2, 0.06,
                     self.local_to_world(s, root, s.width_m * 0.5, s.depth_m * 0.5, -0.03))

        for floor_index in range(s.floors):
            z_floor = floor_index * s.floor_height

            if z_floor <= 1e-6:
                self.add_box("floor", s.width_m, s.depth_m, s.slab_thickness,
                             self.local_to_world(s, root, s.width_m * 0.5, s.depth_m * 0.5, z_floor - s.slab_thickness * 0.5))
            else:
                x0, y0, x1, y1 = self.opening_from_stair_zone(s, zone)
                self.add_ring_parts(s, root, z_floor - s.slab_thickness * 0.5, s.slab_thickness, x0, y0, x1, y1, "floor")

            if floor_index < s.floors - 1:
                x0, y0, x1, y1 = self.opening_from_stair_zone(s, zone)
                self.add_ring_parts(s, root, z_floor + s.floor_height + s.slab_thickness * 0.5, s.slab_thickness, x0, y0, x1, y1, "trim")
            else:
                self.add_box("roof", s.width_m, s.depth_m, s.slab_thickness,
                             self.local_to_world(s, root, s.width_m * 0.5, s.depth_m * 0.5, z_floor + s.floor_height + s.slab_thickness * 0.5))

            self.build_outer_walls(s, root, z_floor, floor_index, rng)
            self.build_inner_walls(s, root, z_floor, rooms, doors, zone)

            if floor_index == 0:
                self.add_box("floor", 2.4, 1.4, 0.04,
                             self.local_to_world(s, root, s.width_m * 0.5, s.wall_thickness + 1.2, z_floor + 0.02))

            if floor_index < s.floors - 1:
                self.build_stairs(s, root, z_floor, zone)

        self.add_box("trim", s.width_m, s.parapet_thickness, s.parapet_height,
                     self.local_to_world(s, root, s.width_m * 0.5, 0.0, s.floors * s.floor_height + s.parapet_height * 0.5))
        self.add_box("trim", s.width_m, s.parapet_thickness, s.parapet_height,
                     self.local_to_world(s, root, s.width_m * 0.5, s.depth_m, s.floors * s.floor_height + s.parapet_height * 0.5))
        self.add_box("trim", s.parapet_thickness, s.depth_m, s.parapet_height,
                     self.local_to_world(s, root, 0.0, s.depth_m * 0.5, s.floors * s.floor_height + s.parapet_height * 0.5))
        self.add_box("trim", s.parapet_thickness, s.depth_m, s.parapet_height,
                     self.local_to_world(s, root, s.width_m, s.depth_m * 0.5, s.floors * s.floor_height + s.parapet_height * 0.5))

        self.batch.build_objects(self.col, self.mats, smooth=not self.fast_mode)

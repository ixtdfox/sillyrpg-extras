from __future__ import annotations

import math

from mathutils import Vector

from .batching import MeshBatcher
from .building_shape import build_adjacency


class BuildingAssembler:
    def __init__(self, batch: MeshBatcher):
        self.batch = batch

    def add_box(self, group, sx, sy, sz, center):
        self.batch.add_box(group, sx, sy, sz, center)

    def local_to_world(self, shape, root, x, y, z):
        return Vector((
            root.location.x + x - shape.width_m * 0.5,
            root.location.y + y - shape.depth_m * 0.5,
            root.location.z + z,
        ))

    def add_ring_parts(self, shape, root, z_center, thickness, x0, y0, x1, y1, group):
        if y0 > 0:
            self.add_box(group, shape.width_m, y0, thickness, self.local_to_world(shape, root, shape.width_m * 0.5, y0 * 0.5, z_center))
        if y1 < shape.depth_m:
            sy = shape.depth_m - y1
            self.add_box(group, shape.width_m, sy, thickness, self.local_to_world(shape, root, shape.width_m * 0.5, y1 + sy * 0.5, z_center))
        if x0 > 0 and y1 > y0:
            sx = x0
            sy = y1 - y0
            self.add_box(group, sx, sy, thickness, self.local_to_world(shape, root, sx * 0.5, y0 + sy * 0.5, z_center))
        if x1 < shape.width_m and y1 > y0:
            sx = shape.width_m - x1
            sy = y1 - y0
            self.add_box(group, sx, sy, thickness, self.local_to_world(shape, root, x1 + sx * 0.5, y0 + sy * 0.5, z_center))

    def add_window_parts(self, settings, wx, wy, z_floor, axis, outward_sign, root):
        sill = settings.window_sill_h
        head = settings.window_head_h
        tile = settings.tile_size
        glass_major = tile * 0.76
        side = (tile - glass_major) * 0.5
        zc = root.location.z + z_floor + sill + (head - sill) * 0.5
        if axis == "x":
            self.add_box("wall", tile, settings.wall_thickness, sill, (wx, wy, root.location.z + z_floor + sill * 0.5))
            self.add_box("trim", tile, settings.wall_thickness, settings.floor_height - head, (wx, wy, root.location.z + z_floor + head + (settings.floor_height - head) * 0.5))
            self.add_box("trim", side, settings.wall_thickness, head - sill, (wx - glass_major * 0.5 - side * 0.5, wy, zc))
            self.add_box("trim", side, settings.wall_thickness, head - sill, (wx + glass_major * 0.5 + side * 0.5, wy, zc))
            self.add_box("glass", glass_major, settings.wall_thickness * 0.35, head - sill, (wx, wy + outward_sign * settings.wall_thickness * 0.25, zc))
        else:
            self.add_box("wall", settings.wall_thickness, tile, sill, (wx, wy, root.location.z + z_floor + sill * 0.5))
            self.add_box("trim", settings.wall_thickness, tile, settings.floor_height - head, (wx, wy, root.location.z + z_floor + head + (settings.floor_height - head) * 0.5))
            self.add_box("trim", settings.wall_thickness, side, head - sill, (wx, wy - glass_major * 0.5 - side * 0.5, zc))
            self.add_box("trim", settings.wall_thickness, side, head - sill, (wx, wy + glass_major * 0.5 + side * 0.5, zc))
            self.add_box("glass", settings.wall_thickness * 0.35, glass_major, head - sill, (wx + outward_sign * settings.wall_thickness * 0.25, wy, zc))

    def build_outer_walls(self, settings, shape, style, root, floor_profile):
        z_floor = floor_profile.z_floor
        tile = shape.tile_size

        front_stack = style.facade_stack_for_side(
            floor_profile,
            "front",
            shape.width_m,
            tile,
            require_center_entrance=floor_profile.is_ground,
        )
        back_stack = style.facade_stack_for_side(floor_profile, "back", shape.width_m, tile)
        left_stack = style.facade_stack_for_side(floor_profile, "left", shape.depth_m, tile)
        right_stack = style.facade_stack_for_side(floor_profile, "right", shape.depth_m, tile)

        front_slots = front_stack.slot_modules(tile)
        back_slots = back_stack.slot_modules(tile)
        left_slots = left_stack.slot_modules(tile)
        right_slots = right_stack.slot_modules(tile)

        for ix, (front_module, back_module) in enumerate(zip(front_slots, back_slots)):
            cx = ix * tile + tile * 0.5
            front_pos = self.local_to_world(shape, root, cx, 0.0, z_floor)
            back_pos = self.local_to_world(shape, root, cx, shape.depth_m, z_floor)

            for face, p, y_sign, module in (
                ("front", front_pos, -1, front_module),
                ("back", back_pos, +1, back_module),
            ):
                wx, wy = p.x, p.y + y_sign * settings.wall_thickness * 0.5
                self._build_facade_module(settings, shape, root, z_floor, face, wx, wy, module)

        for iy, (left_module, right_module) in enumerate(zip(left_slots, right_slots)):
            cy = iy * tile + tile * 0.5
            left_pos = self.local_to_world(shape, root, 0.0, cy, z_floor)
            right_pos = self.local_to_world(shape, root, shape.width_m, cy, z_floor)

            for face, p, x_sign, module in (
                ("left", left_pos, -1, left_module),
                ("right", right_pos, +1, right_module),
            ):
                wx, wy = p.x + x_sign * settings.wall_thickness * 0.5, p.y
                self._build_facade_module(settings, shape, root, z_floor, face, wx, wy, module)

    def _build_facade_module(self, settings, shape, root, z_floor, face, wx, wy, module):
        module_id = module.id
        tile = shape.tile_size
        if module_id == "EntranceDoorModule":
            dw = settings.door_width
            dh = settings.door_height
            side = (tile - dw) * 0.5
            if side > 0.05:
                self.add_box("trim", side, settings.wall_thickness, dh, (wx - dw * 0.5 - side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
                self.add_box("trim", side, settings.wall_thickness, dh, (wx + dw * 0.5 + side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
            top_h = settings.floor_height - dh
            if top_h > 0.05:
                self.add_box("trim", tile, settings.wall_thickness, top_h, (wx, wy, root.location.z + z_floor + dh + top_h * 0.5))
            self.add_box("glass", dw * 0.9, settings.wall_thickness * 0.35, dh * 0.92, (wx, wy + settings.wall_thickness * 0.12, root.location.z + z_floor + dh * 0.5))
            return

        if module_id in {"SolidWallModule", "ServiceWallModule", "CornerModule"}:
            if face in {"front", "back"}:
                self.add_box("wall", tile, settings.wall_thickness, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
            else:
                self.add_box("wall", settings.wall_thickness, tile, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
            return

        outward = {
            "front": +1,
            "back": -1,
            "left": -1,
            "right": +1,
        }[face]
        axis = "x" if face in {"front", "back"} else "y"
        self.add_window_parts(settings, wx, wy, z_floor, axis, outward, root)

        if module_id == "BalconyModule" and face in {"front", "back"}:
            balcony_depth = max(0.15, settings.wall_thickness * 1.6)
            y_offset = -balcony_depth * 0.5 if face == "front" else balcony_depth * 0.5
            self.add_box(
                "trim",
                tile * 0.85,
                balcony_depth,
                0.08,
                (wx, wy + y_offset, root.location.z + z_floor + settings.window_sill_h - 0.04),
            )
    def build_inner_walls(self, settings, shape, root, floor_profile):
        lookup_v = {}
        lookup_h = {}
        for ori, fixed, center in shape.doors:
            if ori == "V":
                lookup_v.setdefault(round(fixed, 3), []).append(center)
            else:
                lookup_h.setdefault(round(fixed, 3), []).append(center)

        zone = shape.stair_zone
        z_floor = floor_profile.z_floor
        for ori, a, b, fixed, s0, s1 in build_adjacency(shape.rooms):
            if ori == "V" and zone.x0 < fixed < zone.x1 and not (s1 <= zone.y0 or s0 >= zone.y1):
                continue
            if ori == "H" and zone.y0 < fixed < zone.y1 and not (s1 <= zone.x0 or s0 >= zone.x1):
                continue

            p = s0
            while p < s1 - 1e-6:
                tc = p + shape.tile_size * 0.5
                door_centers = lookup_v.get(round(fixed, 3), []) if ori == "V" else lookup_h.get(round(fixed, 3), [])
                make_door = any(abs(tc - dc) <= shape.tile_size * 0.51 for dc in door_centers)

                if ori == "V":
                    wp = self.local_to_world(shape, root, fixed, tc, z_floor)
                    wx, wy = wp.x, wp.y
                    if make_door:
                        side = max(0.0, (shape.tile_size - settings.door_width) * 0.5)
                        if side > 0.05:
                            self.add_box("trim", settings.wall_thickness, side, settings.door_height, (wx, wy - settings.door_width * 0.5 - side * 0.5, root.location.z + z_floor + settings.door_height * 0.5))
                            self.add_box("trim", settings.wall_thickness, side, settings.door_height, (wx, wy + settings.door_width * 0.5 + side * 0.5, root.location.z + z_floor + settings.door_height * 0.5))
                        top_h = settings.floor_height - settings.door_height
                        if top_h > 0.05:
                            self.add_box("wall", settings.wall_thickness, shape.tile_size, top_h, (wx, wy, root.location.z + z_floor + settings.door_height + top_h * 0.5))
                    else:
                        self.add_box("trim", settings.wall_thickness, shape.tile_size, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
                else:
                    wp = self.local_to_world(shape, root, tc, fixed, z_floor)
                    wx, wy = wp.x, wp.y
                    if make_door:
                        side = max(0.0, (shape.tile_size - settings.door_width) * 0.5)
                        if side > 0.05:
                            self.add_box("trim", side, settings.wall_thickness, settings.door_height, (wx - settings.door_width * 0.5 - side * 0.5, wy, root.location.z + z_floor + settings.door_height * 0.5))
                            self.add_box("trim", side, settings.wall_thickness, settings.door_height, (wx + settings.door_width * 0.5 + side * 0.5, wy, root.location.z + z_floor + settings.door_height * 0.5))
                        top_h = settings.floor_height - settings.door_height
                        if top_h > 0.05:
                            self.add_box("wall", shape.tile_size, settings.wall_thickness, top_h, (wx, wy, root.location.z + z_floor + settings.door_height + top_h * 0.5))
                    else:
                        self.add_box("trim", shape.tile_size, settings.wall_thickness, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
                p += shape.tile_size

    def build_stairs(self, settings, shape, root, floor_profile):
        z_floor = floor_profile.z_floor
        zone = shape.stair_zone
        clear_h = settings.floor_height
        rise = settings.stairs_rise_step
        run = settings.stairs_run_step
        stair_w = min(settings.stairs_width, (zone.x1 - zone.x0) - 0.2)
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
            self.add_box("floor", stair_w, run, exact_rise, self.local_to_world(shape, root, x_mid, y, z))
        landing_y = y_start + run * first + landing_depth * 0.5
        landing_z = z_floor + exact_rise * first + 0.05
        self.add_box("floor", stair_w, landing_depth, 0.10, self.local_to_world(shape, root, x_mid, landing_y, landing_z))
        y2 = y_start + run * first + landing_depth
        for i in range(second):
            z = z_floor + exact_rise * (first + i + 0.5)
            y = y2 + run * i
            self.add_box("floor", stair_w, run, exact_rise, self.local_to_world(shape, root, x_mid, y, z))

    def assemble(self, settings, shape, style, root):
        pad = settings.lot_padding
        self.add_box(
            "floor",
            shape.width_m + pad * 2,
            shape.depth_m + pad * 2,
            0.06,
            self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m * 0.5, -0.03),
        )

        for floor_profile in shape.floor_profiles:
            z_floor = floor_profile.z_floor
            x0, y0, x1, y1 = shape.stair_opening

            if floor_profile.is_ground:
                self.add_box(
                    "floor",
                    shape.width_m,
                    shape.depth_m,
                    settings.slab_thickness,
                    self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m * 0.5, z_floor - settings.slab_thickness * 0.5),
                )
            else:
                self.add_ring_parts(shape, root, z_floor - settings.slab_thickness * 0.5, settings.slab_thickness, x0, y0, x1, y1, "floor")

            if not floor_profile.is_top:
                self.add_ring_parts(shape, root, z_floor + settings.floor_height + settings.slab_thickness * 0.5, settings.slab_thickness, x0, y0, x1, y1, "trim")
            else:
                self.add_box(
                    "roof",
                    shape.width_m,
                    shape.depth_m,
                    settings.slab_thickness,
                    self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m * 0.5, z_floor + settings.floor_height + settings.slab_thickness * 0.5),
                )

            self.build_outer_walls(settings, shape, style, root, floor_profile)
            self.build_inner_walls(settings, shape, root, floor_profile)

            if floor_profile.is_ground:
                self.add_box(
                    "floor",
                    2.4,
                    1.4,
                    0.04,
                    self.local_to_world(shape, root, shape.width_m * 0.5, settings.wall_thickness + 1.2, z_floor + 0.02),
                )

            if not floor_profile.is_top:
                self.build_stairs(settings, shape, root, floor_profile)

        top_z = shape.floors * settings.floor_height + settings.parapet_height * 0.5
        self.add_box("trim", shape.width_m, settings.parapet_thickness, settings.parapet_height,
                     self.local_to_world(shape, root, shape.width_m * 0.5, 0.0, top_z))
        self.add_box("trim", shape.width_m, settings.parapet_thickness, settings.parapet_height,
                     self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m, top_z))
        self.add_box("trim", settings.parapet_thickness, shape.depth_m, settings.parapet_height,
                     self.local_to_world(shape, root, 0.0, shape.depth_m * 0.5, top_z))
        self.add_box("trim", settings.parapet_thickness, shape.depth_m, settings.parapet_height,
                     self.local_to_world(shape, root, shape.width_m, shape.depth_m * 0.5, top_z))

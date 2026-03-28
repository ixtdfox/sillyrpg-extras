from __future__ import annotations

import math

from mathutils import Vector

from .asset_facade_module import resolve_asset_module
from .batching import MeshBatcher
from .building_shape import build_adjacency
from .utils import GENERATOR_TAG


class BuildingAssembler:
    def __init__(self, batch: MeshBatcher, generated_collection, asset_helper_collection):
        self.batch = batch
        self.generated_collection = generated_collection
        self.asset_helper_collection = asset_helper_collection

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

        self._build_horizontal_accents(settings, shape, floor_profile, root)
        self._build_vertical_accents(settings, shape, floor_profile, root, front_slots, back_slots, left_slots, right_slots)

    def _build_facade_module(self, settings, shape, root, z_floor, face, wx, wy, module):
        module_id = module.id
        tile = shape.tile_size
        if self._place_asset_module(settings, module_id, face, wx, wy, root.location.z + z_floor):
            return

        if module_id == "EntranceDoorModule":
            self._build_entrance_module(settings, root, z_floor, face, wx, wy, tile)
            return

        if module_id in {"SolidWallModule", "ServiceWallModule", "CornerModule", "SolidWallBayModule", "ServiceBayModule"}:
            self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)
            if module_id == "ServiceBayModule":
                self._build_service_bay_overlay(face, settings, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "RecessedStripModule":
            self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)
            self._build_recessed_strip(face, settings, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "AccentPanelModule":
            inset = max(0.05, settings.wall_thickness * 0.2)
            panel_h = settings.floor_height * 0.72
            panel_z = root.location.z + z_floor + panel_h * 0.5 + settings.floor_height * 0.14
            if face in {"front", "back"}:
                self.add_box("trim", tile * 0.82, settings.wall_thickness * 0.42, panel_h, (wx, wy - inset if face == "front" else wy + inset, panel_z))
                self.add_box("wall", tile, settings.wall_thickness, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
            else:
                self.add_box("trim", settings.wall_thickness * 0.42, tile * 0.82, panel_h, (wx - inset if face == "left" else wx + inset, wy, panel_z))
                self.add_box("wall", settings.wall_thickness, tile, settings.floor_height, (wx, wy, root.location.z + z_floor + settings.floor_height * 0.5))
            return

        if module_id == "NarrowWindowBayModule":
            self._build_window_variant(settings, root, z_floor, face, wx, wy, width_factor=0.58, sill_offset=0.08)
            return

        if module_id == "WideWindowBayModule":
            self._build_window_variant(settings, root, z_floor, face, wx, wy, width_factor=0.92, sill_offset=-0.03)
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
            self._build_balcony_variant(settings, root, z_floor, face, wx, wy, tile)

    def _build_window_variant(self, settings, root, z_floor, face, wx, wy, width_factor: float, sill_offset: float):
        local = type("VariantSettings", (), {})()
        for key in ("window_sill_h", "window_head_h", "tile_size", "wall_thickness", "floor_height"):
            setattr(local, key, getattr(settings, key))
        local.window_sill_h = max(0.2, settings.window_sill_h + sill_offset)
        local.window_head_h = min(settings.floor_height - 0.1, settings.window_head_h + sill_offset * 0.5)
        local.tile_size = settings.tile_size * max(0.45, min(1.0, width_factor))
        axis = "x" if face in {"front", "back"} else "y"
        outward = {"front": +1, "back": -1, "left": -1, "right": +1}[face]
        self.add_window_parts(local, wx, wy, z_floor, axis, outward, root)

    def _build_full_wall(self, face, settings, tile, wx, wy, z_floor_world):
        if face in {"front", "back"}:
            self.add_box("wall", tile, settings.wall_thickness, settings.floor_height, (wx, wy, z_floor_world + settings.floor_height * 0.5))
        else:
            self.add_box("wall", settings.wall_thickness, tile, settings.floor_height, (wx, wy, z_floor_world + settings.floor_height * 0.5))

    def _build_service_bay_overlay(self, face, settings, tile, wx, wy, z_floor_world):
        panel_h = settings.floor_height * 0.34
        panel_z = z_floor_world + settings.window_sill_h + panel_h * 0.55
        if face in {"front", "back"}:
            self.add_box("trim", tile * 0.82, settings.wall_thickness * 0.4, panel_h, (wx, wy, panel_z))
        else:
            self.add_box("trim", settings.wall_thickness * 0.4, tile * 0.82, panel_h, (wx, wy, panel_z))

    def _build_recessed_strip(self, face, settings, tile, wx, wy, z_floor_world):
        strip_h = settings.floor_height * 0.8
        strip_z = z_floor_world + settings.floor_height * 0.52
        recess = settings.wall_thickness * 0.25
        if face == "front":
            self.add_box("trim", tile * 0.26, settings.wall_thickness * 0.2, strip_h, (wx, wy + recess, strip_z))
        elif face == "back":
            self.add_box("trim", tile * 0.26, settings.wall_thickness * 0.2, strip_h, (wx, wy - recess, strip_z))
        elif face == "left":
            self.add_box("trim", settings.wall_thickness * 0.2, tile * 0.26, strip_h, (wx + recess, wy, strip_z))
        else:
            self.add_box("trim", settings.wall_thickness * 0.2, tile * 0.26, strip_h, (wx - recess, wy, strip_z))

    def _build_entrance_module(self, settings, root, z_floor, face, wx, wy, tile):
        dw = settings.door_width
        dh = settings.door_height
        style = getattr(settings, "entrance_style", "RECESSED")
        recess_depth = settings.wall_thickness * (1.4 if style in {"RECESSED", "BOLD"} else 0.55)
        canopy_factor = 0.25 if style == "FLAT" else (0.65 if style == "RECESSED" else 0.9)
        frame_factor = 0.2 if style == "FLAT" else (0.6 if style == "RECESSED" else 0.85)
        depth_sign = -1.0 if face == "front" else 1.0
        door_plane_y = wy + depth_sign * recess_depth

        side = (tile - dw) * 0.5
        if side > 0.05:
            self.add_box("trim", side, settings.wall_thickness, dh, (wx - dw * 0.5 - side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
            self.add_box("trim", side, settings.wall_thickness, dh, (wx + dw * 0.5 + side * 0.5, wy, root.location.z + z_floor + dh * 0.5))
        top_h = settings.floor_height - dh
        if top_h > 0.05:
            self.add_box("trim", tile, settings.wall_thickness, top_h, (wx, wy, root.location.z + z_floor + dh + top_h * 0.5))
        self.add_box("glass", dw * 0.9, settings.wall_thickness * 0.35, dh * 0.92, (wx, door_plane_y, root.location.z + z_floor + dh * 0.5))

        if frame_factor > 0.3:
            frame_w = settings.wall_thickness * (0.5 + frame_factor * 0.9)
            frame_h = dh + 0.3
            self.add_box("trim", frame_w, settings.wall_thickness * 0.9, frame_h, (wx - dw * 0.58, wy, root.location.z + z_floor + frame_h * 0.5))
            self.add_box("trim", frame_w, settings.wall_thickness * 0.9, frame_h, (wx + dw * 0.58, wy, root.location.z + z_floor + frame_h * 0.5))

        if canopy_factor > 0.3 and getattr(settings, "canopy_depth", 0.0) > 0.0:
            depth = max(0.2, settings.canopy_depth * (0.45 + canopy_factor * 0.7))
            width = max(dw + 0.6, settings.canopy_width * 0.5)
            self.add_box(
                "trim",
                width,
                depth,
                0.08,
                (wx, wy + depth_sign * depth * 0.5, root.location.z + z_floor + min(settings.floor_height - 0.1, settings.canopy_height)),
            )

    def _build_balcony_variant(self, settings, root, z_floor, face, wx, wy, tile):
        style_seed = int(settings.seed) * 237 + int(round((wx + wy + z_floor) * 10.0))
        rng = math.fmod(style_seed * 0.61803398875, 1.0)
        is_projecting = rng > 0.45
        if is_projecting:
            depth = max(0.18, settings.wall_thickness * 2.2)
            y_offset = -depth * 0.5 if face == "front" else depth * 0.5
            self.add_box("trim", tile * 0.9, depth, 0.09, (wx, wy + y_offset, root.location.z + z_floor + settings.window_sill_h - 0.05))
            rail_h = 0.82
            self.add_box("trim", tile * 0.9, settings.wall_thickness * 0.35, rail_h, (wx, wy + (-depth if face == "front" else depth), root.location.z + z_floor + settings.window_sill_h + rail_h * 0.5))
        else:
            rail_h = 0.78
            rail_y = wy + (-settings.wall_thickness * 0.45 if face == "front" else settings.wall_thickness * 0.45)
            self.add_box("trim", tile * 0.76, settings.wall_thickness * 0.26, rail_h, (wx, rail_y, root.location.z + z_floor + settings.window_sill_h + rail_h * 0.5))

    def _build_horizontal_accents(self, settings, shape, floor_profile, root):
        z_floor = floor_profile.z_floor
        band_density = getattr(settings, "band_density", 0.5)
        strength = getattr(settings, "accent_strength", 0.5)
        if band_density <= 0.01 and strength <= 0.01:
            return
        band_t = settings.wall_thickness * (0.22 + strength * 0.48)
        if band_density > 0.15:
            z = z_floor + settings.floor_height + settings.slab_thickness * 0.5
            self._add_perimeter_band(settings, shape, root, z, band_t, "trim")
        if band_density > 0.28:
            z = z_floor + settings.window_sill_h
            self._add_perimeter_band(settings, shape, root, z, band_t * 0.7, "trim")
        if floor_profile.is_top:
            z = z_floor + settings.floor_height + settings.parapet_height * 0.2
            self._add_perimeter_band(settings, shape, root, z, band_t * 1.2, "roof")

    def _add_perimeter_band(self, settings, shape, root, z, thickness, group):
        h = max(0.04, thickness)
        self.add_box(group, shape.width_m, thickness, h, self.local_to_world(shape, root, shape.width_m * 0.5, 0.0, z))
        self.add_box(group, shape.width_m, thickness, h, self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m, z))
        self.add_box(group, thickness, shape.depth_m, h, self.local_to_world(shape, root, 0.0, shape.depth_m * 0.5, z))
        self.add_box(group, thickness, shape.depth_m, h, self.local_to_world(shape, root, shape.width_m, shape.depth_m * 0.5, z))

    def _build_vertical_accents(self, settings, shape, floor_profile, root, front_slots, back_slots, left_slots, right_slots):
        fin_strength = getattr(settings, "vertical_fins", 0.45)
        if fin_strength <= 0.01:
            return
        z = floor_profile.z_floor + settings.floor_height * 0.5
        fin_w = settings.tile_size * (0.08 + fin_strength * 0.16)
        fin_d = settings.wall_thickness * (0.24 + fin_strength * 0.55)
        fin_h = settings.floor_height * (0.75 + fin_strength * 0.2)

        def add_fin(face, cx, cy):
            if face == "front":
                self.add_box("trim", fin_w, fin_d, fin_h, (cx, cy - fin_d * 0.5, root.location.z + z))
            elif face == "back":
                self.add_box("trim", fin_w, fin_d, fin_h, (cx, cy + fin_d * 0.5, root.location.z + z))
            elif face == "left":
                self.add_box("trim", fin_d, fin_w, fin_h, (cx - fin_d * 0.5, cy, root.location.z + z))
            else:
                self.add_box("trim", fin_d, fin_w, fin_h, (cx + fin_d * 0.5, cy, root.location.z + z))

        for ix, module in enumerate(front_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cx = self.local_to_world(shape, root, ix * settings.tile_size + settings.tile_size * 0.5, 0.0, 0.0).x
                add_fin("front", cx, self.local_to_world(shape, root, 0.0, 0.0, 0.0).y)
        for ix, module in enumerate(back_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cx = self.local_to_world(shape, root, ix * settings.tile_size + settings.tile_size * 0.5, shape.depth_m, 0.0).x
                add_fin("back", cx, self.local_to_world(shape, root, 0.0, shape.depth_m, 0.0).y)
        for iy, module in enumerate(left_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cy = self.local_to_world(shape, root, 0.0, iy * settings.tile_size + settings.tile_size * 0.5, 0.0).y
                add_fin("left", self.local_to_world(shape, root, 0.0, 0.0, 0.0).x, cy)
        for iy, module in enumerate(right_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cy = self.local_to_world(shape, root, shape.width_m, iy * settings.tile_size + settings.tile_size * 0.5, 0.0).y
                add_fin("right", self.local_to_world(shape, root, shape.width_m, 0.0, 0.0).x, cy)

    def _place_asset_module(self, settings, module_id, face, wx, wy, z_floor_world):
        asset_module = resolve_asset_module(settings, module_id)
        src_obj = asset_module.asset_object
        if src_obj is None:
            return False

        if self.asset_helper_collection.objects.get(src_obj.name) is None:
            self.asset_helper_collection.objects.link(src_obj)

        inst = src_obj.copy()
        inst.data = src_obj.data
        inst.animation_data_clear()
        inst["generated_by"] = GENERATOR_TAG
        inst["pb_asset_instance"] = True
        inst["pb_module_id"] = module_id
        inst.name = f"PB_{module_id}_Instance"

        rot_map = {
            "front": 0.0,
            "right": math.pi * 0.5,
            "back": math.pi,
            "left": -math.pi * 0.5,
        }
        bbox_center_x = sum(v[0] for v in src_obj.bound_box) / 8.0
        bbox_center_y = sum(v[1] for v in src_obj.bound_box) / 8.0
        bbox_min_z = min(v[2] for v in src_obj.bound_box)

        inst.rotation_mode = 'XYZ'
        inst.location = (wx - bbox_center_x, wy - bbox_center_y, z_floor_world - bbox_min_z)
        inst.rotation_euler = (0.0, 0.0, rot_map.get(face, 0.0))
        self.generated_collection.objects.link(inst)
        return True
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

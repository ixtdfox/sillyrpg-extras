from __future__ import annotations

import math
import random

from mathutils import Vector

from .asset_facade_module import resolve_asset_module
from .batching import MeshBatcher
from .building_shape import build_adjacency
from .utils import GENERATOR_TAG


class BuildingAssembler:
    WINDOW_OVERLAP = 0.015
    MODULE_OVERLAP = 0.004
    SURFACE_EPSILON = 0.012
    MIN_WINDOW_WIDTH = 0.8
    MIN_WINDOW_HEIGHT = 0.7
    STAIR_GAP_EPS = 1e-6

    def __init__(self, batch: MeshBatcher, generated_collection, asset_helper_collection, asset_instance_collection):
        self.batch = batch
        self.generated_collection = generated_collection
        self.asset_helper_collection = asset_helper_collection
        self.asset_instance_collection = asset_instance_collection

    def add_box(self, group, sx, sy, sz, center):
        self.batch.add_box(group, sx, sy, sz, center)

    @staticmethod
    def _face_normal(face: str):
        return {
            "front": (0.0, -1.0),
            "back": (0.0, 1.0),
            "left": (-1.0, 0.0),
            "right": (1.0, 0.0),
        }[face]

    def _offset_on_face(self, face: str, wx: float, wy: float, distance: float):
        nx, ny = self._face_normal(face)
        return wx + nx * distance, wy + ny * distance

    def local_to_world(self, shape, root, x, y, z):
        return Vector((
            root.location.x + x - shape.width_m * 0.5,
            root.location.y + y - shape.depth_m * 0.5,
            root.location.z + z,
        ))

    def local_rect_to_world(self, shape, root, rect, x, y, z):
        x0, y0, _, _ = rect
        return self.local_to_world(shape, root, x0 + x, y0 + y, z)

    def _rectangles_from_cells(self, cells, tile):
        remaining = set(cells)
        rects = []
        while remaining:
            sx, sy = min(remaining)
            ex = sx + 1
            while (ex, sy) in remaining:
                ex += 1
            ey = sy + 1
            growing = True
            while growing:
                for ix in range(sx, ex):
                    if (ix, ey) not in remaining:
                        growing = False
                        break
                if growing:
                    ey += 1
            for ix in range(sx, ex):
                for iy in range(sy, ey):
                    remaining.discard((ix, iy))
            rects.append((sx * tile, sy * tile, ex * tile, ey * tile))
        return rects

    def _opening_cells(self, shape):
        x0, y0, x1, y1 = shape.stair_opening
        cells = set()
        nx = max(1, int(round(shape.width_m / shape.tile_size)))
        ny = max(1, int(round(shape.depth_m / shape.tile_size)))
        for ix in range(nx):
            for iy in range(ny):
                cx0 = ix * shape.tile_size
                cy0 = iy * shape.tile_size
                cx1 = cx0 + shape.tile_size
                cy1 = cy0 + shape.tile_size
                if not (cx1 <= x0 + self.STAIR_GAP_EPS or cx0 >= x1 - self.STAIR_GAP_EPS or cy1 <= y0 + self.STAIR_GAP_EPS or cy0 >= y1 - self.STAIR_GAP_EPS):
                    cells.add((ix, iy))
        return cells

    @staticmethod
    def _stair_rect_fits(footprint_rect, opening_rect):
        fx0, fy0, fx1, fy1 = footprint_rect
        x0, y0, x1, y1 = opening_rect
        return fx0 <= x0 and fy0 <= y0 and fx1 >= x1 and fy1 >= y1

    @staticmethod
    def _cell_contains_point(cells, tile, x, y):
        ix = int(math.floor(x / tile + 1e-6))
        iy = int(math.floor(y / tile + 1e-6))
        return (ix, iy) in cells

    def _boundary_runs(self, cells, tile):
        cells = set(cells)
        by_face = {"front": {}, "back": {}, "left": {}, "right": {}}
        for ix, iy in cells:
            if (ix, iy - 1) not in cells:
                by_face["front"].setdefault(iy * tile, []).append(ix)
            if (ix, iy + 1) not in cells:
                by_face["back"].setdefault((iy + 1) * tile, []).append(ix)
            if (ix - 1, iy) not in cells:
                by_face["left"].setdefault(ix * tile, []).append(iy)
            if (ix + 1, iy) not in cells:
                by_face["right"].setdefault((ix + 1) * tile, []).append(iy)

        runs = {"front": [], "back": [], "left": [], "right": []}
        for face, lines in by_face.items():
            for fixed, vals in lines.items():
                vals = sorted(set(vals))
                start = vals[0]
                prev = vals[0]
                for v in vals[1:]:
                    if v == prev + 1:
                        prev = v
                        continue
                    runs[face].append((fixed, start * tile, (prev + 1) * tile))
                    start = prev = v
                runs[face].append((fixed, start * tile, (prev + 1) * tile))
        return runs

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

    def _add_volume_shell(self, shape, root, block, z0, floors, settings):
        if floors <= 0:
            return
        h = floors * settings.floor_height
        cx = (block.x0 + block.x1) * 0.5
        cy = (block.y0 + block.y1) * 0.5
        self.add_box("wall", block.x1 - block.x0, block.y1 - block.y0, h, self.local_to_world(shape, root, cx, cy, z0 + h * 0.5))
        self.add_box("roof", block.x1 - block.x0, block.y1 - block.y0, settings.slab_thickness, self.local_to_world(shape, root, cx, cy, z0 + h + settings.slab_thickness * 0.5))

    def _build_auxiliary_volumes(self, settings, shape, style, root):
        for block in getattr(shape, "volume_blocks", ()):
            if block.role == "main":
                continue
            self._add_volume_shell(shape, root, block, block.floor_start * settings.floor_height, block.floor_count, settings)
            if block.role == "upper":
                self._build_terrace_guard(shape, root, block, settings)

    def _build_terrace_guard(self, shape, root, upper_block, settings):
        rail_h = max(0.28, settings.parapet_height * 0.9)
        z = settings.floor_height + settings.slab_thickness + rail_h * 0.5
        t = max(0.05, settings.parapet_thickness * 0.7)
        if upper_block.x0 > shape.tile_size:
            self.add_box("trim", upper_block.x0, t, rail_h, self.local_to_world(shape, root, upper_block.x0 * 0.5, t * 0.5, z))
        if upper_block.x1 < shape.width_m - shape.tile_size:
            span = shape.width_m - upper_block.x1
            self.add_box("trim", span, t, rail_h, self.local_to_world(shape, root, upper_block.x1 + span * 0.5, t * 0.5, z))

    @staticmethod
    def _rects_overlap(a, b):
        return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])

    def _safe_roof_rect(self, shape, settings, roof_rect=None):
        rx0, ry0, rx1, ry1 = roof_rect if roof_rect is not None else (0.0, 0.0, shape.width_m, shape.depth_m)
        inset = max(settings.parapet_thickness + 0.06, settings.wall_thickness * 0.35)
        return (rx0 + inset, ry0 + inset, max(rx0 + inset + 0.1, rx1 - inset), max(ry0 + inset + 0.1, ry1 - inset))

    def _add_roof_box_if_valid(self, shape, root, rect, z_bottom, h, group, avoid_rects):
        x0, y0, x1, y1 = rect
        if x1 - x0 <= 0.08 or y1 - y0 <= 0.08 or h <= 0.01:
            return False
        for blocked in avoid_rects:
            if self._rects_overlap(rect, blocked):
                return False
        self.add_box(
            group,
            x1 - x0,
            y1 - y0,
            h,
            self.local_to_world(shape, root, (x0 + x1) * 0.5, (y0 + y1) * 0.5, z_bottom + h * 0.5),
        )
        return True

    def _build_roof_silhouette(self, settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=None):
        profile = getattr(style, "roof_profile_preference", getattr(settings, "roof_profile", "RAISED_PARAPET"))
        rx0, ry0, rx1, ry1 = roof_rect if roof_rect is not None else (0.0, 0.0, shape.width_m, shape.depth_m)
        rw = rx1 - rx0
        rd = ry1 - ry0
        parapet_h = settings.parapet_height
        parapet_t = settings.parapet_thickness
        if profile == "FLAT":
            parapet_h *= 0.72
        elif profile == "RAISED_PARAPET":
            parapet_h *= 1.35
        elif profile == "STEPPED_PARAPET":
            parapet_h *= 1.15
        elif profile == "ACCESS_VOLUME":
            parapet_h *= 1.0

        top_z = roof_z + parapet_h * 0.5
        self.add_box("trim", rw, parapet_t, parapet_h, self.local_to_world(shape, root, rx0 + rw * 0.5, ry0, top_z))
        self.add_box("trim", rw, parapet_t, parapet_h, self.local_to_world(shape, root, rx0 + rw * 0.5, ry1, top_z))
        self.add_box("trim", parapet_t, rd, parapet_h, self.local_to_world(shape, root, rx0, ry0 + rd * 0.5, top_z))
        self.add_box("trim", parapet_t, rd, parapet_h, self.local_to_world(shape, root, rx1, ry0 + rd * 0.5, top_z))

        safe = self._safe_roof_rect(shape, settings, roof_rect=roof_rect)

        if profile == "STEPPED_PARAPET":
            step_h = max(0.08, parapet_h * 0.32)
            step_t = max(parapet_t * 0.85, settings.wall_thickness * 0.22)
            step_len = max(shape.tile_size * 1.2, rw * 0.22)
            y_front = safe[1] + step_t * 0.5
            y_back = safe[3] - step_t * 0.5
            z = roof_z + parapet_h + step_h * 0.5
            x_a = safe[0] + step_len * 0.5
            x_b = safe[2] - step_len * 0.5
            self.add_box("trim", step_len, step_t, step_h, self.local_to_world(shape, root, x_a, y_front, z))
            self.add_box("trim", step_len, step_t, step_h, self.local_to_world(shape, root, x_b, y_front, z))
            self.add_box("trim", step_len, step_t, step_h, self.local_to_world(shape, root, x_a, y_back, z))
            self.add_box("trim", step_len, step_t, step_h, self.local_to_world(shape, root, x_b, y_back, z))

        if profile in {"ACCESS_VOLUME", "RAISED_PARAPET"}:
            vol_w = max(shape.tile_size * 1.2, min(rw * 0.28, rw - shape.tile_size * 2.0))
            vol_d = max(shape.tile_size * 1.1, min(rd * 0.22, rd - shape.tile_size * 2.0))
            vol_h = max(settings.floor_height * 0.32, 0.9)
            side = "front" if rng.random() < 0.5 else "back"
            y0 = safe[1] + 0.45 if side == "front" else safe[3] - vol_d - 0.45
            x0 = safe[0] + (safe[2] - safe[0] - vol_w) * (0.2 + rng.random() * 0.6)
            access_rect = (x0, y0, x0 + vol_w, y0 + vol_d)
            if self._add_roof_box_if_valid(shape, root, access_rect, roof_z + 0.01, vol_h, "wall", blocked_rects):
                blocked_rects.append(access_rect)
                door_h = min(vol_h * 0.74, settings.door_height * 0.85)
                door_w = min(vol_w * 0.34, settings.door_width)
                if side == "front":
                    self.add_box("glass", door_w, settings.wall_thickness * 0.3, door_h, self.local_to_world(shape, root, x0 + vol_w * 0.5, y0 + settings.wall_thickness * 0.18, roof_z + door_h * 0.5))
                else:
                    self.add_box("glass", door_w, settings.wall_thickness * 0.3, door_h, self.local_to_world(shape, root, x0 + vol_w * 0.5, y0 + vol_d - settings.wall_thickness * 0.18, roof_z + door_h * 0.5))

        return parapet_h

    def _build_rooftop_equipment(self, settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=None):
        density = max(0.0, min(1.0, getattr(style, "roof_detail_density", getattr(settings, "roof_detail_density", 0.5))))
        amount = max(0, int(getattr(settings, "rooftop_equipment_amount", 0)))
        if density <= 0.01 or amount <= 0:
            return

        safe = self._safe_roof_rect(shape, settings, roof_rect=roof_rect)
        layout_mode = rng.choice(("central", "offset", "sparse"))
        spawn = max(1, round(amount * (0.5 + density * 0.9)))
        if layout_mode == "sparse":
            spawn = max(1, round(spawn * 0.55))

        cx = (safe[0] + safe[2]) * 0.5
        cy = (safe[1] + safe[3]) * 0.5
        for idx in range(spawn):
            if layout_mode == "central":
                px = cx + (rng.random() - 0.5) * (safe[2] - safe[0]) * 0.36
                py = cy + (rng.random() - 0.5) * (safe[3] - safe[1]) * 0.36
            elif layout_mode == "offset":
                px = safe[0] + (safe[2] - safe[0]) * (0.18 + 0.64 * rng.random())
                py = safe[1] + (safe[3] - safe[1]) * (0.1 + 0.34 * rng.random()) if rng.random() < 0.5 else safe[1] + (safe[3] - safe[1]) * (0.56 + 0.34 * rng.random())
            else:
                px = safe[0] + (safe[2] - safe[0]) * (0.1 + 0.8 * rng.random())
                py = safe[1] + (safe[3] - safe[1]) * (0.1 + 0.8 * rng.random())

            kind_roll = rng.random()
            if kind_roll < 0.26:
                # HVAC box
                sx = shape.tile_size * (0.45 + rng.random() * 0.55)
                sy = shape.tile_size * (0.35 + rng.random() * 0.5)
                h = 0.32 + rng.random() * 0.55
                group = "trim"
            elif kind_roll < 0.48:
                # Vent shaft
                s = shape.tile_size * (0.18 + rng.random() * 0.18)
                sx = sy = s
                h = 0.6 + rng.random() * 0.95
                group = "trim"
            elif kind_roll < 0.66 and rng.random() < getattr(settings, "skylight_chance", 0.35):
                # Skylight block
                sx = shape.tile_size * (0.46 + rng.random() * 0.4)
                sy = shape.tile_size * (0.34 + rng.random() * 0.35)
                h = 0.22 + rng.random() * 0.18
                group = "glass"
            elif kind_roll < 0.82 and rng.random() < getattr(settings, "solar_panel_chance", 0.45):
                # Solar panel group (thin tilted reads)
                sx = shape.tile_size * (0.82 + rng.random() * 0.9)
                sy = shape.tile_size * (0.3 + rng.random() * 0.24)
                h = 0.08 + rng.random() * 0.05
                group = "roof"
            else:
                # Service hatch
                sx = shape.tile_size * (0.34 + rng.random() * 0.25)
                sy = shape.tile_size * (0.34 + rng.random() * 0.25)
                h = 0.09 + rng.random() * 0.06
                group = "roof"

            rect = (px - sx * 0.5, py - sy * 0.5, px + sx * 0.5, py + sy * 0.5)
            placed = self._add_roof_box_if_valid(shape, root, rect, roof_z + 0.01, h, group, blocked_rects)
            if placed and layout_mode != "sparse" and idx % 3 == 0 and group == "roof":
                # lightweight panel support for rooftop canopy/panel read
                self.add_box("trim", sx * 0.9, max(0.04, settings.wall_thickness * 0.2), 0.06, self.local_to_world(shape, root, px, py - sy * 0.18, roof_z + 0.14))

            if placed and group in {"trim", "roof"}:
                center = self.local_to_world(shape, root, px, py, roof_z + 0.01)
                self._place_rooftop_utility_asset(settings, center.x, center.y, roof_z + 0.01)

    def _build_top_floor_accents(self, settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=None):
        safe = self._safe_roof_rect(shape, settings, roof_rect=roof_rect)
        if getattr(style, "roof_profile_preference", "RAISED_PARAPET") == "FLAT":
            choice = rng.choice(("setback", "setback", "utility"))
        elif getattr(style, "roof_profile_preference", "RAISED_PARAPET") == "STEPPED_PARAPET":
            choice = rng.choice(("utility", "setback", "utility"))
        else:
            choice = rng.choice(("setback", "canopy", "utility"))
        if choice == "setback":
            band_d = max(shape.tile_size * 0.55, shape.depth_m * 0.11)
            rect = (safe[0], safe[1], safe[2], min(safe[3], safe[1] + band_d))
            if self._add_roof_box_if_valid(shape, root, rect, roof_z + 0.01, 0.12, "trim", blocked_rects):
                self.add_box("roof", rect[2] - rect[0], 0.08, 0.06, self.local_to_world(shape, root, (rect[0] + rect[2]) * 0.5, rect[3], roof_z + 0.15))
        elif choice == "canopy":
            strip_d = max(0.45, min(shape.depth_m * 0.08, shape.tile_size * 0.6))
            strip_w = max(shape.width_m * 0.34, shape.tile_size * 2.0)
            cx = shape.width_m * (0.32 + rng.random() * 0.36)
            x0 = max(safe[0], cx - strip_w * 0.5)
            x1 = min(safe[2], cx + strip_w * 0.5)
            rect = (x0, safe[1], x1, safe[1] + strip_d)
            self._add_roof_box_if_valid(shape, root, rect, roof_z + 0.22, 0.08, "trim", blocked_rects)
        else:
            util_w = max(shape.tile_size * 1.1, min(shape.width_m * 0.2, shape.width_m - shape.tile_size * 2.2))
            util_d = max(shape.tile_size * 0.95, min(shape.depth_m * 0.18, shape.depth_m - shape.tile_size * 2.0))
            util_h = max(0.72, settings.floor_height * 0.28)
            x0 = safe[0] + (safe[2] - safe[0] - util_w) * (0.12 + rng.random() * 0.76)
            y0 = safe[1] + (safe[3] - safe[1] - util_d) * (0.2 + rng.random() * 0.65)
            rect = (x0, y0, x0 + util_w, y0 + util_d)
            if self._add_roof_box_if_valid(shape, root, rect, roof_z + 0.01, util_h, "wall", blocked_rects):
                blocked_rects.append(rect)

    def _window_layout(self, settings, tile_width: float, width_factor: float = 1.0, sill_offset: float = 0.0, head_offset: float = 0.0):
        floor_h = float(settings.floor_height)
        clearance = float(getattr(settings, "minimum_window_clearance", 0.5))
        overlap = float(getattr(settings, "window_overlap", self.WINDOW_OVERLAP))
        overlap = max(0.0, overlap)
        max_sill = max(0.0, floor_h - 0.8)
        max_head = max(0.0, floor_h - 0.05)
        sill = max(0.0, min(max_sill, float(settings.window_sill_h) + sill_offset))
        head = max(0.0, min(max_head, float(settings.window_head_h) + head_offset))
        if head <= sill + clearance or head <= sill:
            return None
        window_h = head - sill
        if window_h < self.MIN_WINDOW_HEIGHT:
            return None

        max_window_width = tile_width * 0.9
        requested_window_width = tile_width * max(0.45, min(1.0, width_factor))
        window_width = min(max_window_width, requested_window_width)
        window_width = max(self.MIN_WINDOW_WIDTH, window_width)
        if window_width > max_window_width + 1e-6 or window_width >= tile_width:
            return None
        trim_nominal = (tile_width - window_width) * 0.5
        if trim_nominal <= 0.01:
            return None
        # Single source of truth: left trim + glass + right trim == tile
        left_trim = trim_nominal
        right_trim = trim_nominal
        glass_nominal = tile_width - left_trim - right_trim

        return {
            "tile": tile_width,
            "sill": sill,
            "head": head,
            "clearance": clearance,
            "overlap": overlap,
            "left_trim": left_trim,
            "right_trim": right_trim,
            "glass_nominal": glass_nominal,
            "window_h": window_h,
            "lower_h": sill,
            "upper_h": floor_h - head,
        }

    def add_window_parts(self, settings, wx, wy, z_floor, axis, root, layout, face):
        tile = layout["tile"]
        overlap = layout["overlap"]
        lower_a, lower_b = 0.0, layout["sill"] + overlap
        win_a, win_b = layout["sill"] - overlap, layout["head"] + overlap
        upper_a, upper_b = layout["head"] - overlap, float(settings.floor_height)
        lower_h = max(0.01, lower_b - lower_a)
        win_h = max(0.01, win_b - win_a)
        upper_h = max(0.01, upper_b - upper_a)

        trim_left = layout["left_trim"]
        trim_right = layout["right_trim"]
        glass_nominal = layout["glass_nominal"]

        left_a = -tile * 0.5
        left_b = -tile * 0.5 + trim_left + overlap
        glass_a = -tile * 0.5 + trim_left - overlap
        glass_b = glass_a + glass_nominal + overlap * 2.0
        right_a = tile * 0.5 - trim_right - overlap
        right_b = tile * 0.5

        left_w = max(0.01, left_b - left_a)
        right_w = max(0.01, right_b - right_a)
        glass_w = max(0.01, glass_b - glass_a)

        z_base = root.location.z + z_floor
        z_lower = z_base + (lower_a + lower_b) * 0.5
        z_window = z_base + (win_a + win_b) * 0.5
        z_upper = z_base + (upper_a + upper_b) * 0.5

        base_depth = settings.wall_thickness
        trim_depth = max(0.03, min(base_depth * 0.55, base_depth - self.SURFACE_EPSILON))
        glass_depth = max(0.02, min(base_depth * 0.22, trim_depth - self.SURFACE_EPSILON))
        trim_outset = (base_depth - trim_depth) * 0.5 + self.SURFACE_EPSILON
        glass_inset = (base_depth - glass_depth) * 0.5 + self.SURFACE_EPSILON
        trim_wx, trim_wy = self._offset_on_face(face, wx, wy, trim_outset)
        glass_wx, glass_wy = self._offset_on_face(face, wx, wy, -glass_inset)

        if axis == "x":
            self.add_box("wall", tile, base_depth, lower_h, (wx, wy, z_lower))
            self.add_box("trim", tile, trim_depth, upper_h, (trim_wx, trim_wy, z_upper))
            self.add_box("trim", left_w, trim_depth, win_h, (trim_wx + (left_a + left_b) * 0.5, trim_wy, z_window))
            self.add_box("trim", right_w, trim_depth, win_h, (trim_wx + (right_a + right_b) * 0.5, trim_wy, z_window))
            self.add_box("glass", glass_w, glass_depth, win_h, (glass_wx + (glass_a + glass_b) * 0.5, glass_wy, z_window))
        else:
            self.add_box("wall", base_depth, tile, lower_h, (wx, wy, z_lower))
            self.add_box("trim", trim_depth, tile, upper_h, (trim_wx, trim_wy, z_upper))
            self.add_box("trim", trim_depth, left_w, win_h, (trim_wx, trim_wy + (left_a + left_b) * 0.5, z_window))
            self.add_box("trim", trim_depth, right_w, win_h, (trim_wx, trim_wy + (right_a + right_b) * 0.5, z_window))
            self.add_box("glass", glass_depth, glass_w, win_h, (glass_wx, glass_wy + (glass_a + glass_b) * 0.5, z_window))

    def build_outer_walls(self, settings, shape, style, root, floor_profile, footprint_rect=None):
        z_floor = floor_profile.z_floor
        tile = shape.tile_size
        fx0, fy0, fx1, fy1 = footprint_rect if footprint_rect is not None else (0.0, 0.0, shape.width_m, shape.depth_m)
        fwidth = fx1 - fx0
        fdepth = fy1 - fy0

        front_stack = style.facade_stack_for_side(
            floor_profile,
            "front",
            fwidth,
            tile,
            require_center_entrance=floor_profile.is_ground,
        )
        back_stack = style.facade_stack_for_side(floor_profile, "back", fwidth, tile)
        left_stack = style.facade_stack_for_side(floor_profile, "left", fdepth, tile)
        right_stack = style.facade_stack_for_side(floor_profile, "right", fdepth, tile)

        front_slots = front_stack.slot_modules(tile)
        back_slots = back_stack.slot_modules(tile)
        left_slots = left_stack.slot_modules(tile)
        right_slots = right_stack.slot_modules(tile)

        for ix, (front_module, back_module) in enumerate(zip(front_slots, back_slots)):
            cx = ix * tile + tile * 0.5
            front_pos = self.local_rect_to_world(shape, root, (fx0, fy0, fx1, fy1), cx, 0.0, z_floor)
            back_pos = self.local_rect_to_world(shape, root, (fx0, fy0, fx1, fy1), cx, fdepth, z_floor)

            for face, p, y_sign, module in (
                ("front", front_pos, -1, front_module),
                ("back", back_pos, +1, back_module),
            ):
                wx, wy = p.x, p.y + y_sign * settings.wall_thickness * 0.5
                self._build_facade_module(settings, shape, style, root, z_floor, face, wx, wy, module)

        for iy, (left_module, right_module) in enumerate(zip(left_slots, right_slots)):
            cy = iy * tile + tile * 0.5
            left_pos = self.local_rect_to_world(shape, root, (fx0, fy0, fx1, fy1), 0.0, cy, z_floor)
            right_pos = self.local_rect_to_world(shape, root, (fx0, fy0, fx1, fy1), fwidth, cy, z_floor)

            for face, p, x_sign, module in (
                ("left", left_pos, -1, left_module),
                ("right", right_pos, +1, right_module),
            ):
                wx, wy = p.x + x_sign * settings.wall_thickness * 0.5, p.y
                self._build_facade_module(settings, shape, style, root, z_floor, face, wx, wy, module)

        self._build_horizontal_accents(settings, shape, style, floor_profile, root, footprint_rect=(fx0, fy0, fx1, fy1))
        self._build_vertical_accents(settings, shape, style, floor_profile, root, front_slots, back_slots, left_slots, right_slots, footprint_rect=(fx0, fy0, fx1, fy1))

    def build_outer_walls_cells(self, settings, shape, style, root, floor_profile, cells):
        tile = shape.tile_size
        z_floor = floor_profile.z_floor
        runs = self._boundary_runs(cells, tile)

        for face in ("front", "back", "left", "right"):
            for fixed, a0, a1 in runs[face]:
                side_w = max(tile, a1 - a0)
                stack = style.facade_stack_for_side(
                    floor_profile,
                    face,
                    side_w,
                    tile,
                    require_center_entrance=floor_profile.is_ground and face == "front",
                )
                slots = stack.slot_modules(tile)
                for idx, module in enumerate(slots):
                    c = a0 + idx * tile + tile * 0.5
                    if face == "front":
                        p = self.local_to_world(shape, root, c, fixed, z_floor)
                        wx, wy = p.x, p.y - settings.wall_thickness * 0.5
                    elif face == "back":
                        p = self.local_to_world(shape, root, c, fixed, z_floor)
                        wx, wy = p.x, p.y + settings.wall_thickness * 0.5
                    elif face == "left":
                        p = self.local_to_world(shape, root, fixed, c, z_floor)
                        wx, wy = p.x - settings.wall_thickness * 0.5, p.y
                    else:
                        p = self.local_to_world(shape, root, fixed, c, z_floor)
                        wx, wy = p.x + settings.wall_thickness * 0.5, p.y
                    self._build_facade_module(settings, shape, style, root, z_floor, face, wx, wy, module)

    def _build_facade_module(self, settings, shape, style, root, z_floor, face, wx, wy, module):
        module_id = module.id
        tile = shape.tile_size
        if self._place_asset_module(settings, module_id, face, wx, wy, root.location.z + z_floor):
            return

        if module_id == "EntranceDoorModule":
            self._build_entrance_module(settings, style, root, z_floor, face, wx, wy, tile)
            return

        if module_id in {"SolidWallModule", "ServiceWallModule", "CornerModule", "SolidWallBayModule"}:
            self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "ServiceBayModule":
            self._build_service_bay_module(face, settings, style, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "RecessedStripModule":
            self._build_recessed_strip(face, settings, style, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "AccentPanelModule":
            self._build_accent_panel_module(face, settings, style, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id == "WideWindowBayModule":
            if not self._build_window_variant(settings, root, z_floor, face, wx, wy, width_factor=0.92, sill_offset=-0.03):
                self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)
            return

        if module_id in {"StandardWindowModule", "StairWindowModule", "BalconyModule"}:
            if not self._build_window_variant(settings, root, z_floor, face, wx, wy, width_factor=1.0, sill_offset=0.0):
                self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)
                return

            if module_id == "BalconyModule" and face in {"front", "back"}:
                self._build_balcony_variant(settings, style, root, z_floor, face, wx, wy, tile)
            return

        self._build_full_wall(face, settings, tile, wx, wy, root.location.z + z_floor)

    def _build_window_variant(self, settings, root, z_floor, face, wx, wy, width_factor: float, sill_offset: float):
        if not getattr(settings, "window_is_valid", True):
            return False
        tile = settings.tile_size
        layout = self._window_layout(
            settings,
            tile_width=tile,
            width_factor=width_factor,
            sill_offset=sill_offset,
            head_offset=sill_offset * 0.5,
        )
        if layout is None:
            return False
        axis = "x" if face in {"front", "back"} else "y"
        self.add_window_parts(settings, wx, wy, z_floor, axis, root, layout, face)
        return True

    def _build_full_wall(self, face, settings, tile, wx, wy, z_floor_world):
        module_overlap = max(0.0, float(getattr(settings, "module_overlap", self.MODULE_OVERLAP)))
        tile_with_overlap = tile + module_overlap * 2.0
        if face in {"front", "back"}:
            self.add_box("wall", tile_with_overlap, settings.wall_thickness, settings.floor_height, (wx, wy, z_floor_world + settings.floor_height * 0.5))
        else:
            self.add_box("wall", settings.wall_thickness, tile_with_overlap, settings.floor_height, (wx, wy, z_floor_world + settings.floor_height * 0.5))

    def _build_service_bay_module(self, face, settings, style, tile, wx, wy, z_floor_world):
        self._build_full_wall(face, settings, tile, wx, wy, z_floor_world)
        panel_h = settings.floor_height * (0.3 + getattr(style, "accent_strength", 0.5) * 0.16)
        panel_z = z_floor_world + settings.window_sill_h + panel_h * 0.55
        depth = max(settings.wall_thickness * 0.36, self.SURFACE_EPSILON * 2.2)
        offset = settings.wall_thickness * 0.5 + depth * 0.5 + self.SURFACE_EPSILON
        ox, oy = self._offset_on_face(face, wx, wy, offset)
        if face in {"front", "back"}:
            self.add_box("trim", tile * 0.82, depth, panel_h, (ox, oy, panel_z))
        else:
            self.add_box("trim", depth, tile * 0.82, panel_h, (ox, oy, panel_z))

    def _build_recessed_strip(self, face, settings, style, tile, wx, wy, z_floor_world):
        self._build_full_wall(face, settings, tile, wx, wy, z_floor_world)
        strip_depth = max(settings.wall_thickness * 0.32, self.SURFACE_EPSILON * 2.2)
        strip_width = tile * 0.2
        strip_h = settings.floor_height * 0.82
        strip_z = z_floor_world + settings.floor_height * 0.5
        offset = settings.wall_thickness * 0.5 + strip_depth * 0.5 + self.SURFACE_EPSILON
        ox, oy = self._offset_on_face(face, wx, wy, offset)
        if face in {"front", "back"}:
            self.add_box("trim", strip_width, strip_depth, strip_h, (ox, oy, strip_z))
        else:
            self.add_box("trim", strip_depth, strip_width, strip_h, (ox, oy, strip_z))

    def _build_accent_panel_module(self, face, settings, style, tile, wx, wy, z_floor_world):
        self._build_full_wall(face, settings, tile, wx, wy, z_floor_world)
        panel_h = settings.floor_height * 0.72
        panel_z = z_floor_world + panel_h * 0.5 + settings.floor_height * 0.14
        panel_depth = max(settings.wall_thickness * 0.46, self.SURFACE_EPSILON * 2.4)
        offset = settings.wall_thickness * 0.5 + panel_depth * 0.5 + self.SURFACE_EPSILON
        ox, oy = self._offset_on_face(face, wx, wy, offset)
        if face in {"front", "back"}:
            self.add_box("trim", tile * 0.82, panel_depth, panel_h, (ox, oy, panel_z))
        else:
            self.add_box("trim", panel_depth, tile * 0.82, panel_h, (ox, oy, panel_z))

    def _build_entrance_module(self, settings, style, root, z_floor, face, wx, wy, tile):
        dw = settings.door_width
        dh = settings.door_height
        entry_style = getattr(style, "entrance_preference", getattr(settings, "entrance_style", "RECESSED_ENTRY"))
        legacy_map = {"RECESSED": "RECESSED_ENTRY", "FLAT": "FRAMED_PORTAL", "BOLD": "CANOPY_COLUMNS"}
        entry_style = legacy_map.get(entry_style, entry_style)
        recess_depth = settings.wall_thickness * (1.55 if entry_style in {"RECESSED_ENTRY", "STAIR_REVEAL"} else 0.65)
        canopy_factor = 0.25 if entry_style == "FRAMED_PORTAL" else (0.9 if entry_style in {"CANOPY_COLUMNS", "STAIR_REVEAL"} else 0.65)
        frame_factor = 0.5 if entry_style == "RECESSED_ENTRY" else (0.75 if entry_style == "FRAMED_PORTAL" else 0.9)
        depth_sign = -1.0 if face == "front" else 1.0
        door_plane_y = wy + depth_sign * min(settings.wall_thickness * 0.25, recess_depth * 0.4)

        side = (tile - dw) * 0.5
        if side > 0.05:
            trim_depth = max(0.03, settings.wall_thickness * 0.45)
            ox, oy = self._offset_on_face(face, wx, wy, (settings.wall_thickness - trim_depth) * 0.5 + self.SURFACE_EPSILON)
            self.add_box("trim", side, trim_depth, dh, (ox - dw * 0.5 - side * 0.5, oy, root.location.z + z_floor + dh * 0.5))
            self.add_box("trim", side, trim_depth, dh, (ox + dw * 0.5 + side * 0.5, oy, root.location.z + z_floor + dh * 0.5))
        top_h = settings.floor_height - dh
        if top_h > 0.05:
            trim_depth = max(0.03, settings.wall_thickness * 0.45)
            ox, oy = self._offset_on_face(face, wx, wy, (settings.wall_thickness - trim_depth) * 0.5 + self.SURFACE_EPSILON)
            self.add_box("trim", tile, trim_depth, top_h, (ox, oy, root.location.z + z_floor + dh + top_h * 0.5))
        self.add_box("glass", dw * 0.9, max(0.02, settings.wall_thickness * 0.2), dh * 0.92, (wx, door_plane_y, root.location.z + z_floor + dh * 0.5))

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
        if entry_style in {"CANOPY_COLUMNS", "STAIR_REVEAL"}:
            col_w = max(0.08, settings.wall_thickness * 0.42)
            col_h = min(settings.floor_height - 0.05, dh + 0.45)
            ycol = wy + depth_sign * max(0.2, settings.canopy_depth * 0.35)
            self.add_box("trim", col_w, col_w, col_h, (wx - dw * 0.65, ycol, root.location.z + z_floor + col_h * 0.5))
            self.add_box("trim", col_w, col_w, col_h, (wx + dw * 0.65, ycol, root.location.z + z_floor + col_h * 0.5))
        if entry_style == "STAIR_REVEAL":
            step_h = 0.09
            for i in range(3):
                self.add_box("floor", dw + 1.0 + i * 0.26, 0.32, step_h, (wx, wy + depth_sign * (0.62 + i * 0.28), root.location.z + z_floor + step_h * (i + 0.5)))

    def _build_balcony_variant(self, settings, style, root, z_floor, face, wx, wy, tile):
        style_seed = int(settings.seed) * 237 + int(round((wx + wy + z_floor) * 10.0))
        rng = math.fmod(style_seed * 0.61803398875, 1.0)
        balcony_bias = getattr(style, "balcony_preference", 0.4)
        is_projecting = rng > (0.68 - balcony_bias * 0.32)
        if is_projecting:
            depth = max(0.12, settings.wall_thickness * (1.4 + balcony_bias * 1.6))
            y_offset = -depth * 0.5 if face == "front" else depth * 0.5
            self.add_box("trim", tile * 0.9, depth, 0.09, (wx, wy + y_offset, root.location.z + z_floor + settings.window_sill_h - 0.05))
            rail_h = 0.82
            self.add_box("trim", tile * 0.9, settings.wall_thickness * 0.35, rail_h, (wx, wy + (-depth if face == "front" else depth), root.location.z + z_floor + settings.window_sill_h + rail_h * 0.5))
        else:
            rail_h = 0.78
            rail_y = wy + (-settings.wall_thickness * 0.45 if face == "front" else settings.wall_thickness * 0.45)
            self.add_box("trim", tile * 0.76, settings.wall_thickness * 0.26, rail_h, (wx, rail_y, root.location.z + z_floor + settings.window_sill_h + rail_h * 0.5))

    def _build_horizontal_accents(self, settings, shape, style, floor_profile, root, footprint_rect=None):
        z_floor = floor_profile.z_floor
        band_density = getattr(style, "band_density", getattr(settings, "band_density", 0.5))
        strength = getattr(style, "accent_strength", getattr(settings, "accent_strength", 0.5))
        if band_density <= 0.01 and strength <= 0.01:
            return
        band_t = settings.wall_thickness * (0.22 + strength * 0.48)
        if band_density > 0.15:
            z = z_floor + settings.floor_height + settings.slab_thickness * 0.5
            self._add_perimeter_band(settings, shape, root, z, band_t, "trim", footprint_rect=footprint_rect)
        if band_density > 0.28:
            z = z_floor + settings.window_sill_h
            self._add_perimeter_band(settings, shape, root, z, band_t * 0.7, "trim", footprint_rect=footprint_rect)
        if floor_profile.is_top:
            z = z_floor + settings.floor_height + settings.parapet_height * 0.2
            self._add_perimeter_band(settings, shape, root, z, band_t * 1.2, "roof", footprint_rect=footprint_rect)

    def _add_perimeter_band(self, settings, shape, root, z, thickness, group, footprint_rect=None):
        fx0, fy0, fx1, fy1 = footprint_rect if footprint_rect is not None else (0.0, 0.0, shape.width_m, shape.depth_m)
        fw = fx1 - fx0
        fd = fy1 - fy0
        h = max(0.04, thickness)
        self.add_box(group, fw, thickness, h, self.local_to_world(shape, root, fx0 + fw * 0.5, fy0, z))
        self.add_box(group, fw, thickness, h, self.local_to_world(shape, root, fx0 + fw * 0.5, fy1, z))
        self.add_box(group, thickness, fd, h, self.local_to_world(shape, root, fx0, fy0 + fd * 0.5, z))
        self.add_box(group, thickness, fd, h, self.local_to_world(shape, root, fx1, fy0 + fd * 0.5, z))

    def _build_vertical_accents(self, settings, shape, style, floor_profile, root, front_slots, back_slots, left_slots, right_slots, footprint_rect=None):
        fin_strength = getattr(style, "vertical_fins", getattr(settings, "vertical_fins", 0.45))
        if fin_strength <= 0.01:
            return
        z = floor_profile.z_floor + settings.floor_height * 0.5
        fin_w = settings.tile_size * (0.08 + fin_strength * 0.16)
        fin_d = settings.wall_thickness * (0.24 + fin_strength * 0.55)
        fin_h = settings.floor_height * (0.75 + fin_strength * 0.2)

        fx0, fy0, fx1, fy1 = footprint_rect if footprint_rect is not None else (0.0, 0.0, shape.width_m, shape.depth_m)
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
                cx = self.local_to_world(shape, root, fx0 + ix * settings.tile_size + settings.tile_size * 0.5, fy0, 0.0).x
                add_fin("front", cx, self.local_to_world(shape, root, fx0, fy0, 0.0).y)
        for ix, module in enumerate(back_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cx = self.local_to_world(shape, root, fx0 + ix * settings.tile_size + settings.tile_size * 0.5, fy1, 0.0).x
                add_fin("back", cx, self.local_to_world(shape, root, fx0, fy1, 0.0).y)
        for iy, module in enumerate(left_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cy = self.local_to_world(shape, root, fx0, fy0 + iy * settings.tile_size + settings.tile_size * 0.5, 0.0).y
                add_fin("left", self.local_to_world(shape, root, fx0, fy0, 0.0).x, cy)
        for iy, module in enumerate(right_slots):
            if module.id in {"SolidWallBayModule", "RecessedStripModule", "ServiceBayModule"}:
                cy = self.local_to_world(shape, root, fx1, fy0 + iy * settings.tile_size + settings.tile_size * 0.5, 0.0).y
                add_fin("right", self.local_to_world(shape, root, fx1, fy0, 0.0).x, cy)

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
        self.asset_instance_collection.objects.link(inst)
        return True

    def _place_rooftop_utility_asset(self, settings, world_x, world_y, z_floor_world):
        mode = getattr(settings, "facade_module_mode", "HYBRID")
        if mode == "PROCEDURAL_ONLY":
            return False
        src_obj = getattr(settings, "rooftop_utility_asset", None)
        if src_obj is None:
            return False
        if self.asset_helper_collection.objects.get(src_obj.name) is None:
            self.asset_helper_collection.objects.link(src_obj)

        inst = src_obj.copy()
        inst.data = src_obj.data
        inst.animation_data_clear()
        inst["generated_by"] = GENERATOR_TAG
        inst["pb_asset_instance"] = True
        inst["pb_module_id"] = "RooftopUtilityModule"
        inst.name = "PB_RooftopUtility_Instance"

        bbox_center_x = sum(v[0] for v in src_obj.bound_box) / 8.0
        bbox_center_y = sum(v[1] for v in src_obj.bound_box) / 8.0
        bbox_min_z = min(v[2] for v in src_obj.bound_box)
        inst.rotation_mode = 'XYZ'
        inst.location = (world_x - bbox_center_x, world_y - bbox_center_y, z_floor_world - bbox_min_z)
        inst.rotation_euler = (0.0, 0.0, 0.0)
        self.asset_instance_collection.objects.link(inst)
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
        ground_cells = set(shape.floor_cells[0]) if getattr(shape, "floor_cells", None) else set()
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
                px, py = (fixed, tc) if ori == "V" else (tc, fixed)
                if ground_cells and not self._cell_contains_point(ground_cells, shape.tile_size, px, py):
                    p += shape.tile_size
                    continue

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
        rise = max(0.05, settings.stairs_rise_step)
        stair_w = min(settings.stairs_width, (zone.x1 - zone.x0) - 0.2)
        n_steps = max(1, math.ceil(clear_h / rise))
        exact_rise = clear_h / n_steps
        y_start = zone.y0 + 0.25
        y_end = zone.y1 - 0.2
        available_depth = max(0.8, y_end - y_start)
        run = max(0.12, available_depth / n_steps)
        x_mid = (zone.x0 + zone.x1) * 0.5
        for i in range(n_steps):
            z = z_floor + exact_rise * (i + 0.5)
            y = y_start + run * i
            self.add_box("floor", stair_w, run, exact_rise, self.local_to_world(shape, root, x_mid, y, z))
        top_cap_y = min(zone.y1 - 0.25, y_start + run * n_steps)
        top_cap_h = max(0.12, exact_rise)
        self.add_box("floor", stair_w, max(0.28, run * 1.25), top_cap_h, self.local_to_world(shape, root, x_mid, top_cap_y, z_floor + clear_h + top_cap_h * 0.5 - 0.02))

    def assemble(self, settings, shape, style, root):
        pad = settings.lot_padding
        self.add_box(
            "floor",
            shape.width_m + pad * 2,
            shape.depth_m + pad * 2,
            0.06,
            self.local_to_world(shape, root, shape.width_m * 0.5, shape.depth_m * 0.5, -0.03),
        )

        stair_opening_cells = self._opening_cells(shape)
        stair_segments_built = 0
        stairs_required = max(0, shape.floors - 1)

        for floor_profile in shape.floor_profiles:
            z_floor = floor_profile.z_floor
            x0, y0, x1, y1 = shape.stair_opening
            fx0, fy0, fx1, fy1 = shape.floor_footprints[floor_profile.floor_index] if getattr(shape, "floor_footprints", None) else (0.0, 0.0, shape.width_m, shape.depth_m)
            fw = max(shape.tile_size * 2, fx1 - fx0)
            fd = max(shape.tile_size * 2, fy1 - fy0)
            floor_cells = set(shape.floor_cells[floor_profile.floor_index]) if getattr(shape, "floor_cells", None) else set()
            stair_inside = self._stair_rect_fits((fx0, fy0, fx1, fy1), (x0, y0, x1, y1))
            use_cell_shell = bool(floor_cells)
            needs_opening_from_below = floor_profile.floor_index > 0 and shape.floors > 1
            needs_opening_to_above = (not floor_profile.is_top) and shape.floors > 1
            next_stair_inside = False
            if (not floor_profile.is_top) and getattr(shape, "floor_footprints", None):
                nx0, ny0, nx1, ny1 = shape.floor_footprints[floor_profile.floor_index + 1]
                next_stair_inside = self._stair_rect_fits((nx0, ny0, nx1, ny1), (x0, y0, x1, y1))
            can_build_stairs_here = (not floor_profile.is_top) and stair_inside and next_stair_inside

            if floor_profile.is_ground:
                if use_cell_shell:
                    for rx0, ry0, rx1, ry1 in self._rectangles_from_cells(floor_cells, shape.tile_size):
                        self.add_box("floor", rx1 - rx0, ry1 - ry0, settings.slab_thickness, self.local_to_world(shape, root, (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, z_floor - settings.slab_thickness * 0.5))
                else:
                    self.add_box("floor", fw, fd, settings.slab_thickness, self.local_to_world(shape, root, fx0 + fw * 0.5, fy0 + fd * 0.5, z_floor - settings.slab_thickness * 0.5))
            else:
                if use_cell_shell:
                    slab_cells = floor_cells - stair_opening_cells if needs_opening_from_below else floor_cells
                    for rx0, ry0, rx1, ry1 in self._rectangles_from_cells(slab_cells, shape.tile_size):
                        self.add_box("floor", rx1 - rx0, ry1 - ry0, settings.slab_thickness, self.local_to_world(shape, root, (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, z_floor - settings.slab_thickness * 0.5))
                elif stair_inside:
                    self.add_ring_parts(shape, root, z_floor - settings.slab_thickness * 0.5, settings.slab_thickness, x0, y0, x1, y1, "floor")
                else:
                    self.add_box("floor", fw, fd, settings.slab_thickness, self.local_to_world(shape, root, fx0 + fw * 0.5, fy0 + fd * 0.5, z_floor - settings.slab_thickness * 0.5))

            if not floor_profile.is_top:
                if use_cell_shell:
                    cap_cells = floor_cells - stair_opening_cells if needs_opening_to_above else floor_cells
                    for rx0, ry0, rx1, ry1 in self._rectangles_from_cells(cap_cells, shape.tile_size):
                        self.add_box("trim", rx1 - rx0, ry1 - ry0, settings.slab_thickness, self.local_to_world(shape, root, (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, z_floor + settings.floor_height + settings.slab_thickness * 0.5))
                elif stair_inside:
                    self.add_ring_parts(shape, root, z_floor + settings.floor_height + settings.slab_thickness * 0.5, settings.slab_thickness, x0, y0, x1, y1, "trim")
                else:
                    self.add_box("trim", fw, fd, settings.slab_thickness, self.local_to_world(shape, root, fx0 + fw * 0.5, fy0 + fd * 0.5, z_floor + settings.floor_height + settings.slab_thickness * 0.5))
            else:
                if use_cell_shell:
                    for rx0, ry0, rx1, ry1 in self._rectangles_from_cells(floor_cells, shape.tile_size):
                        self.add_box("roof", rx1 - rx0, ry1 - ry0, settings.slab_thickness, self.local_to_world(shape, root, (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5, z_floor + settings.floor_height + settings.slab_thickness * 0.5))
                else:
                    self.add_box("roof", fw, fd, settings.slab_thickness, self.local_to_world(shape, root, fx0 + fw * 0.5, fy0 + fd * 0.5, z_floor + settings.floor_height + settings.slab_thickness * 0.5))

            if use_cell_shell:
                self.build_outer_walls_cells(settings, shape, style, root, floor_profile, floor_cells)
            else:
                self.build_outer_walls(settings, shape, style, root, floor_profile, footprint_rect=(fx0, fy0, fx1, fy1))
            if floor_profile.is_ground and stair_inside:
                self.build_inner_walls(settings, shape, root, floor_profile)

            if floor_profile.is_ground:
                self.add_box(
                    "floor",
                    2.4,
                    1.4,
                    0.04,
                    self.local_to_world(shape, root, fx0 + fw * 0.5, fy0 + settings.wall_thickness + 1.2, z_floor + 0.02),
                )

            if can_build_stairs_here:
                self.build_stairs(settings, shape, root, floor_profile)
                stair_segments_built += 1

        roof_z = shape.floors * settings.floor_height
        top_rect = shape.floor_footprints[-1] if getattr(shape, "floor_footprints", None) else (0.0, 0.0, shape.width_m, shape.depth_m)
        blocked_rects = [shape.stair_opening] if (top_rect[0] <= shape.stair_opening[0] and top_rect[1] <= shape.stair_opening[1] and top_rect[2] >= shape.stair_opening[2] and top_rect[3] >= shape.stair_opening[3]) else []
        rng = random.Random((int(settings.seed) * 73856093) ^ (shape.floors * 19349663) ^ int(shape.width_m * 100) ^ (int(shape.depth_m * 100) << 1))
        self._build_roof_silhouette(settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=top_rect)
        self._build_rooftop_equipment(settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=top_rect)
        self._build_top_floor_accents(settings, shape, style, root, roof_z, blocked_rects, rng, roof_rect=top_rect)
        if stairs_required > 0 and stair_segments_built < stairs_required:
            print(f"[PBG] stair placement failed: built {stair_segments_built}/{stairs_required} segments")

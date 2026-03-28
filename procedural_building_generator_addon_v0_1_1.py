bl_info = {
    "name": "Procedural Building Generator",
    "author": "OpenAI",
    "version": (0, 1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Proc Building",
    "description": "Interactive low-rise procedural building generator with panel controls",
    "category": "Object",
}

import bpy
import math
import random
import time
from mathutils import Vector
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty

GENERATOR_TAG = "PROC_BUILDING_ADDON"
COLLECTION_NAME = "ProcBuilding_Runtime"
ROOT_NAME = "BuildingRoot"
HANDLE_NAME = "BuildingSizeHandle"

_LAST_CONTROLLER_SIG = None
_LAST_PROPS_SIG = None
_LAST_CHANGE_TS = 0.0
_LAST_REBUILD_TS = 0.0
_LAST_QUALITY = None
_TIMER_INSTALLED = False


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def snap_to_step(v, step):
    return round(v / step) * step


def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        return col
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def clear_generated_objects(col):
    for obj in list(col.objects):
        if obj.get("generated_by") == GENERATOR_TAG:
            bpy.data.objects.remove(obj, do_unlink=True)


def ensure_empty(name, empty_type='PLAIN_AXES', location=(0, 0, 0)):
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = empty_type
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = empty_type
    return obj


def world_box(sx, sy, sz, center):
    cx, cy, cz = center
    x = sx * 0.5
    y = sy * 0.5
    z = sz * 0.5
    verts = [
        (cx - x, cy - y, cz - z), (cx + x, cy - y, cz - z),
        (cx + x, cy + y, cz - z), (cx - x, cy + y, cz - z),
        (cx - x, cy - y, cz + z), (cx + x, cy - y, cz + z),
        (cx + x, cy + y, cz + z), (cx - x, cy + y, cz + z),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7),
        (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    return verts, faces


def clear_nodes(mat):
    for n in list(mat.node_tree.nodes):
        mat.node_tree.nodes.remove(n)


def get_or_create_material(name, kind):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    clear_nodes(mat)
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)

    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-1200, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-980, 0)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-760, 120)
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.42

    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.location = (-760, -120)
    voronoi.inputs["Scale"].default_value = 14.0

    mix = nodes.new("ShaderNodeMixRGB")
    mix.location = (-420, 40)
    mix.inputs["Fac"].default_value = 0.22

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-520, -150)

    bump = nodes.new("ShaderNodeBump")
    bump.location = (180, -180)

    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
    links.new(noise.outputs["Fac"], mix.inputs["Color1"])
    links.new(voronoi.outputs["Distance"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if kind == "wall":
        bsdf.inputs["Base Color"].default_value = (0.91, 0.90, 0.86, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.68
        ramp.color_ramp.elements[0].color = (0.50, 0.50, 0.50, 1.0)
        ramp.color_ramp.elements[1].color = (0.66, 0.66, 0.66, 1.0)
        bump.inputs["Strength"].default_value = 0.05
    elif kind == "trim":
        bsdf.inputs["Base Color"].default_value = (0.97, 0.97, 0.94, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.34
        bump.inputs["Strength"].default_value = 0.015
    elif kind == "roof":
        bsdf.inputs["Base Color"].default_value = (0.36, 0.39, 0.41, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.86
        bump.inputs["Strength"].default_value = 0.03
    elif kind == "floor":
        bsdf.inputs["Base Color"].default_value = (0.74, 0.75, 0.76, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.82
        bump.inputs["Strength"].default_value = 0.04
    elif kind == "metal":
        bsdf.inputs["Base Color"].default_value = (0.56, 0.60, 0.64, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.9
        bsdf.inputs["Roughness"].default_value = 0.28
        bump.inputs["Strength"].default_value = 0.01
    elif kind == "glass":
        bsdf.inputs["Base Color"].default_value = (0.62, 0.84, 0.97, 0.20)
        bsdf.inputs["Roughness"].default_value = 0.03
        bsdf.inputs["IOR"].default_value = 1.45
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 1.0
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = 1.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 0.16
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'HASHED'
        if hasattr(mat, "use_screen_refraction"):
            mat.use_screen_refraction = True
    elif kind == "accent":
        bsdf.inputs["Base Color"].default_value = (0.34, 0.52, 0.68, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.45

    return mat


def ensure_materials():
    return {
        "wall": get_or_create_material("PB_Addon_Wall", "wall"),
        "trim": get_or_create_material("PB_Addon_Trim", "trim"),
        "roof": get_or_create_material("PB_Addon_Roof", "roof"),
        "floor": get_or_create_material("PB_Addon_Floor", "floor"),
        "metal": get_or_create_material("PB_Addon_Metal", "metal"),
        "glass": get_or_create_material("PB_Addon_Glass", "glass"),
        "accent": get_or_create_material("PB_Addon_Accent", "accent"),
    }


class MeshBatcher:
    def __init__(self):
        self.data = {}

    def add_box(self, group, sx, sy, sz, center):
        verts, faces = world_box(sx, sy, sz, center)
        if group not in self.data:
            self.data[group] = {"verts": [], "faces": []}
        base = len(self.data[group]["verts"])
        self.data[group]["verts"].extend(verts)
        self.data[group]["faces"].extend([(a + base, b + base, c + base, d + base) for (a, b, c, d) in faces])

    def build_objects(self, collection, materials, smooth=False):
        for group, payload in self.data.items():
            if not payload["verts"] or not payload["faces"]:
                continue
            mesh = bpy.data.meshes.new(f"{group}_mesh")
            mesh.from_pydata(payload["verts"], [], payload["faces"])
            mesh.update()
            if smooth:
                for poly in mesh.polygons:
                    poly.use_smooth = True
            obj = bpy.data.objects.new(f"{group}_obj", mesh)
            obj["generated_by"] = GENERATOR_TAG
            if group in materials:
                obj.data.materials.append(materials[group])
            collection.objects.link(obj)


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


class PBSettings(bpy.types.PropertyGroup):
    width_m: FloatProperty(name="Width", default=16.0, min=8.0, step=200)
    depth_m: FloatProperty(name="Depth", default=12.0, min=8.0, step=200)
    floors: IntProperty(name="Floors", default=2, min=1, max=3)
    room_count: IntProperty(name="Rooms", default=6, min=1, max=12)
    seed: IntProperty(name="Seed", default=11)
    detail_amount: FloatProperty(name="Detail", default=0.75, min=0.0, max=1.0)
    balcony_chance: FloatProperty(name="Balconies", default=0.45, min=0.0, max=1.0)
    roof_style: IntProperty(name="Roof Style", default=1, min=0, max=2)
    tile_size: FloatProperty(name="Tile Size", default=2.0, min=1.0)
    floor_height: FloatProperty(name="Floor Height", default=2.8, min=2.2)
    wall_thickness: FloatProperty(name="Wall Thickness", default=0.18, min=0.05)
    slab_thickness: FloatProperty(name="Slab Thickness", default=0.18, min=0.05)
    window_sill_h: FloatProperty(name="Window Sill", default=0.85, min=0.2)
    window_head_h: FloatProperty(name="Window Head", default=2.25, min=1.2)
    door_width: FloatProperty(name="Door Width", default=1.0, min=0.6)
    door_height: FloatProperty(name="Door Height", default=2.1, min=1.6)
    stairs_width: FloatProperty(name="Stairs Width", default=1.4, min=1.0)
    stairs_run_step: FloatProperty(name="Stair Run", default=0.28, min=0.15)
    stairs_rise_step: FloatProperty(name="Stair Rise", default=0.175, min=0.1)
    stair_opening_margin: FloatProperty(name="Opening Margin", default=0.18, min=0.0)
    lot_padding: FloatProperty(name="Lot Padding", default=1.5, min=0.0)
    parapet_height: FloatProperty(name="Parapet Height", default=0.32, min=0.0)
    parapet_thickness: FloatProperty(name="Parapet Thickness", default=0.12, min=0.02)
    canopy_depth: FloatProperty(name="Canopy Depth", default=1.2, min=0.0)
    canopy_width: FloatProperty(name="Canopy Width", default=3.8, min=0.0)
    canopy_height: FloatProperty(name="Canopy Height", default=2.45, min=0.0)
    interactive_preview: BoolProperty(name="Interactive Preview", default=True)
    preview_detail_scale: FloatProperty(name="Preview Detail Scale", default=0.35, min=0.0, max=1.0)
    rebuild_interval_ms: IntProperty(name="Rebuild Interval ms", default=120, min=10, max=1000)
    idle_full_rebuild_ms: IntProperty(name="Idle Full Rebuild ms", default=320, min=50, max=2000)
    auto_rebuild: BoolProperty(name="Auto Rebuild", default=True)


class PB_OT_setup_controllers(bpy.types.Operator):
    bl_idname = "pb.setup_controllers"
    bl_label = "Setup Controllers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.pb_settings
        ensure_empty(ROOT_NAME, 'ARROWS', (0, 0, 0))
        ensure_empty(HANDLE_NAME, 'CUBE', (s.width_m, s.depth_m, 0))
        self.report({'INFO'}, "Controllers created")
        return {'FINISHED'}


class PB_OT_build_now(bpy.types.Operator):
    bl_idname = "pb.build_now"
    bl_label = "Build Now"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        BuildingGenerator().build("full")
        self.report({'INFO'}, "Building rebuilt")
        return {'FINISHED'}


class PB_OT_clear_generated(bpy.types.Operator):
    bl_idname = "pb.clear_generated"
    bl_label = "Clear Generated"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear_generated_objects(ensure_collection(COLLECTION_NAME))
        self.report({'INFO'}, "Generated building cleared")
        return {'FINISHED'}


class PB_PT_main_panel(bpy.types.Panel):
    bl_label = "Procedural Building"
    bl_idname = "PB_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Proc Building'

    def draw(self, context):
        layout = self.layout
        s = context.scene.pb_settings

        col = layout.column(align=True)
        col.operator("pb.setup_controllers", icon='EMPTY_AXIS')
        col.operator("pb.build_now", icon='FILE_REFRESH')
        col.operator("pb.clear_generated", icon='TRASH')

        layout.separator()

        box = layout.box()
        box.label(text="Footprint")
        box.prop(s, "width_m")
        box.prop(s, "depth_m")
        box.prop(s, "floors")
        box.prop(s, "room_count")
        box.prop(s, "seed")

        box = layout.box()
        box.label(text="Style")
        box.prop(s, "detail_amount")
        box.prop(s, "balcony_chance")
        box.prop(s, "roof_style")

        box = layout.box()
        box.label(text="Construction")
        box.prop(s, "tile_size")
        box.prop(s, "floor_height")
        box.prop(s, "wall_thickness")
        box.prop(s, "slab_thickness")
        box.prop(s, "door_width")
        box.prop(s, "door_height")
        box.prop(s, "window_sill_h")
        box.prop(s, "window_head_h")

        box = layout.box()
        box.label(text="Stairs")
        box.prop(s, "stairs_width")
        box.prop(s, "stairs_run_step")
        box.prop(s, "stairs_rise_step")
        box.prop(s, "stair_opening_margin")

        box = layout.box()
        box.label(text="Site / Extras")
        box.prop(s, "lot_padding")
        box.prop(s, "parapet_height")
        box.prop(s, "parapet_thickness")
        box.prop(s, "canopy_width")
        box.prop(s, "canopy_depth")
        box.prop(s, "canopy_height")

        box = layout.box()
        box.label(text="Performance")
        box.prop(s, "auto_rebuild")
        box.prop(s, "interactive_preview")
        box.prop(s, "preview_detail_scale")
        box.prop(s, "rebuild_interval_ms")
        box.prop(s, "idle_full_rebuild_ms")


def read_controller_sig():
    root = bpy.data.objects.get(ROOT_NAME)
    handle = bpy.data.objects.get(HANDLE_NAME)
    if not root or not handle:
        return None
    return (
        round(root.location.x, 4), round(root.location.y, 4), round(root.location.z, 4),
        round(handle.location.x, 4), round(handle.location.y, 4), round(handle.location.z, 4),
    )


def read_props_sig():
    s = bpy.context.scene.pb_settings
    return (
        round(s.width_m, 4), round(s.depth_m, 4),
        s.floors, s.room_count, s.seed,
        round(s.detail_amount, 4), round(s.balcony_chance, 4),
        s.roof_style, round(s.tile_size, 4), round(s.floor_height, 4),
        round(s.wall_thickness, 4), round(s.slab_thickness, 4),
        round(s.window_sill_h, 4), round(s.window_head_h, 4),
        round(s.door_width, 4), round(s.door_height, 4),
        round(s.stairs_width, 4), round(s.stairs_run_step, 4),
        round(s.stairs_rise_step, 4), round(s.stair_opening_margin, 4),
        round(s.lot_padding, 4),
        round(s.parapet_height, 4), round(s.parapet_thickness, 4),
        round(s.canopy_depth, 4), round(s.canopy_width, 4), round(s.canopy_height, 4),
        int(s.interactive_preview), round(s.preview_detail_scale, 4),
        s.rebuild_interval_ms, s.idle_full_rebuild_ms, int(s.auto_rebuild),
    )


def active_generated_object_selected():
    obj = bpy.context.view_layer.objects.active
    if obj is None:
        return False
    return bool(obj.get("generated_by") == GENERATOR_TAG)


def timer_should_pause():
    ctx = bpy.context
    if ctx.mode != 'OBJECT':
        return True
    if active_generated_object_selected():
        return True
    if not ctx.scene.pb_settings.auto_rebuild:
        return True
    return False


def proc_building_timer():
    global _LAST_CONTROLLER_SIG, _LAST_PROPS_SIG, _LAST_CHANGE_TS, _LAST_REBUILD_TS, _LAST_QUALITY

    scene = bpy.context.scene
    if not hasattr(scene, "pb_settings"):
        return 0.25

    controller_sig = read_controller_sig()
    props_sig = read_props_sig()
    if controller_sig is None:
        return 0.25

    now = time.perf_counter()
    s = scene.pb_settings

    controller_changed = controller_sig != _LAST_CONTROLLER_SIG
    props_changed = props_sig != _LAST_PROPS_SIG

    if controller_changed or props_changed:
        _LAST_CONTROLLER_SIG = controller_sig
        _LAST_PROPS_SIG = props_sig
        _LAST_CHANGE_TS = now

    if timer_should_pause():
        return 0.12

    time_since_change_ms = (now - _LAST_CHANGE_TS) * 1000.0
    time_since_rebuild_ms = (now - _LAST_REBUILD_TS) * 1000.0

    quality = "full"
    if s.interactive_preview and controller_changed:
        quality = "preview"
    elif s.interactive_preview and time_since_change_ms < s.idle_full_rebuild_ms and _LAST_QUALITY == "preview":
        quality = "preview"

    if time_since_rebuild_ms >= s.rebuild_interval_ms:
        if (controller_changed or props_changed) or (quality != _LAST_QUALITY and time_since_change_ms >= s.rebuild_interval_ms):
            try:
                BuildingGenerator().build(quality)
                _LAST_REBUILD_TS = now
                _LAST_QUALITY = quality
            except Exception as e:
                print("Proc building rebuild failed:", e)

    return 0.08 if s.interactive_preview else 0.15


def install_timer():
    global _TIMER_INSTALLED
    if _TIMER_INSTALLED:
        return
    bpy.app.timers.register(proc_building_timer, first_interval=0.15, persistent=True)
    _TIMER_INSTALLED = True


classes = (
    PBSettings,
    PB_OT_setup_controllers,
    PB_OT_build_now,
    PB_OT_clear_generated,
    PB_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pb_settings = PointerProperty(type=PBSettings)
    install_timer()


def unregister():
    if hasattr(bpy.types.Scene, "pb_settings"):
        del bpy.types.Scene.pb_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

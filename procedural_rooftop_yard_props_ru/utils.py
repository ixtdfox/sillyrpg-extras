from __future__ import annotations

import math
from typing import Iterable

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector


ADDON_ID = "procedural_rooftop_yard_props_ru"


def addon_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent


def ensure_collection(scene: bpy.types.Scene, collection_name: str, delete_old: bool) -> bpy.types.Collection:
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
    elif delete_old:
        clear_collection(collection)
    ensure_collection_linked(scene.collection, collection)
    return collection


def ensure_collection_linked(parent: bpy.types.Collection, collection: bpy.types.Collection) -> None:
    if collection == parent:
        return
    if collection not in parent.children[:]:
        parent.children.link(collection)
    collection.hide_viewport = False
    collection.hide_render = False


def ensure_child_collection(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    for child in parent.children:
        if child.name == name:
            ensure_collection_linked(parent, child)
            return child
    child = bpy.data.collections.new(name)
    ensure_collection_linked(parent, child)
    return child


def clear_collection(collection: bpy.types.Collection) -> None:
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for child in list(collection.children):
        clear_collection(child)
        bpy.data.collections.remove(child)


def link_object(collection: bpy.types.Collection, obj: bpy.types.Object) -> None:
    if obj not in collection.objects[:]:
        collection.objects.link(obj)


def iter_collection_objects_recursive(collection: bpy.types.Collection) -> Iterable[bpy.types.Object]:
    yield from collection.objects
    for child in collection.children:
        yield from iter_collection_objects_recursive(child)


def focus_generated_objects(context: bpy.types.Context, objects: list[bpy.types.Object]) -> None:
    if not objects:
        return
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]


def set_generated_metadata(obj: bpy.types.Object, prop_type: str, prop_category: str, region_names: list[str] | None = None) -> None:
    obj["generated_by"] = ADDON_ID
    obj["procedural_rooftop_yard"] = True
    obj["prop_type"] = prop_type
    obj["prop_category"] = prop_category
    if region_names:
        obj["atlas_regions"] = ",".join(sorted(set(region_names)))


def next_object_name(prefix: str) -> str:
    index = 1
    while bpy.data.objects.get(f"{prefix}_{index:03d}") is not None:
        index += 1
    return f"{prefix}_{index:03d}"


def create_mesh_object(name: str, bm: bmesh.types.BMesh, collection: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link_object(collection, obj)
    return obj


def new_bmesh_box(size: tuple[float, float, float]) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return bm


def new_bmesh_plane(size: tuple[float, float]) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.scale(bm, vec=(size[0], size[1], 1.0), verts=bm.verts)
    return bm


def new_bmesh_cylinder(radius: float, depth: float, vertices: int = 12) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=max(3, vertices),
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    return bm


def new_bmesh_cone(radius_bottom: float, radius_top: float, depth: float, vertices: int = 12) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=max(3, vertices),
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
    )
    return bm


def new_bmesh_uv_sphere(radius: float, segments: int = 12, rings: int = 8) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=max(4, segments), v_segments=max(3, rings), radius=radius)
    return bm


def apply_transform(
    obj: bpy.types.Object,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    obj.location = location
    obj.rotation_euler = Euler(rotation)
    return obj


def create_box(
    name: str,
    collection: bpy.types.Collection,
    size: tuple[float, float, float],
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return apply_transform(create_mesh_object(name, new_bmesh_box(size), collection), location, rotation)


def create_panel_plane(
    name: str,
    collection: bpy.types.Collection,
    size: tuple[float, float],
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return apply_transform(create_mesh_object(name, new_bmesh_plane(size), collection), location, rotation)


def create_cylinder(
    name: str,
    collection: bpy.types.Collection,
    radius: float,
    depth: float,
    vertices: int = 12,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return apply_transform(create_mesh_object(name, new_bmesh_cylinder(radius, depth, vertices), collection), location, rotation)


def create_cone(
    name: str,
    collection: bpy.types.Collection,
    radius_bottom: float,
    radius_top: float,
    depth: float,
    vertices: int = 12,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return apply_transform(create_mesh_object(name, new_bmesh_cone(radius_bottom, radius_top, depth, vertices), collection), location, rotation)


def create_sphere(
    name: str,
    collection: bpy.types.Collection,
    radius: float,
    segments: int = 12,
    rings: int = 8,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return apply_transform(create_mesh_object(name, new_bmesh_uv_sphere(radius, segments, rings), collection), location)


def create_pipe_between_points(
    name: str,
    collection: bpy.types.Collection,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    vertices: int = 8,
) -> bpy.types.Object:
    start_vec = Vector(start)
    end_vec = Vector(end)
    direction = end_vec - start_vec
    depth = max(0.001, direction.length)
    obj = create_cylinder(name, collection, radius=radius, depth=depth, vertices=vertices)
    mid = (start_vec + end_vec) * 0.5
    obj.location = mid
    up = Vector((0.0, 0.0, 1.0))
    quat = up.rotation_difference(direction.normalized())
    obj.rotation_euler = quat.to_euler()
    return obj


def add_bevel_modifier(obj: bpy.types.Object, amount: float, segments: int = 1) -> None:
    modifier = obj.modifiers.new(name="RY_Bevel", type="BEVEL")
    modifier.width = amount
    modifier.segments = segments
    modifier.limit_method = "ANGLE"


def shade_smooth_safe(obj: bpy.types.Object) -> None:
    if obj.type != "MESH":
        return
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    try:
        obj.data.use_auto_smooth = True
    except Exception:
        pass


def create_text_label(text: str, collection: bpy.types.Collection, location: tuple[float, float, float], size: float = 0.35) -> bpy.types.Object:
    curve = bpy.data.curves.new(name=f"{text}_Curve", type="FONT")
    curve.body = text
    curve.size = size
    obj = bpy.data.objects.new(f"Label_{text}", curve)
    obj.location = location
    link_object(collection, obj)
    return obj


def create_empty_root(name: str, collection: bpy.types.Collection, location: tuple[float, float, float]) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.location = location
    link_object(collection, obj)
    return obj


def parent_parts(root: bpy.types.Object, parts: list[bpy.types.Object]) -> None:
    for part in parts:
        part.parent = root


def world_bbox_2d(obj: bpy.types.Object) -> tuple[float, float]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [corner.x for corner in corners]
    ys = [corner.y for corner in corners]
    return max(xs) - min(xs), max(ys) - min(ys)


def rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], padding: float = 0.0) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (
        ax1 + padding <= bx0
        or bx1 + padding <= ax0
        or ay1 + padding <= by0
        or by1 + padding <= ay0
    )


def compute_rotated_footprint(footprint: tuple[float, float], rotation_z: float) -> tuple[float, float]:
    angle = abs(int(round(math.degrees(rotation_z))) % 180)
    if angle == 90:
        return footprint[1], footprint[0]
    return footprint[0], footprint[1]


def rect_from_center(center: tuple[float, float], size: tuple[float, float]) -> tuple[float, float, float, float]:
    return (
        center[0] - size[0] * 0.5,
        center[1] - size[1] * 0.5,
        center[0] + size[0] * 0.5,
        center[1] + size[1] * 0.5,
    )


def sample_position_in_rect(rng, width: float, depth: float, margin: float, footprint: tuple[float, float]) -> tuple[float, float]:
    half_w = max(footprint[0] * 0.5, 0.001)
    half_d = max(footprint[1] * 0.5, 0.001)
    x = rng.uniform(-width * 0.5 + margin + half_w, width * 0.5 - margin - half_w)
    y = rng.uniform(-depth * 0.5 + margin + half_d, depth * 0.5 - margin - half_d)
    return x, y


def sample_position_around_building(
    rng,
    yard_width: float,
    yard_depth: float,
    building_width: float,
    building_depth: float,
    margin: float,
    footprint: tuple[float, float],
) -> tuple[float, float]:
    for _ in range(100):
        x, y = sample_position_in_rect(rng, yard_width, yard_depth, margin, footprint)
        rect = rect_from_center((x, y), footprint)
        building = rect_from_center((0.0, 0.0), (building_width + margin * 2.0, building_depth + margin * 2.0))
        if not rects_overlap(rect, building, 0.0):
            return x, y
    return 0.0, 0.0


def make_rotation(rotation_z: float) -> tuple[float, float, float]:
    return 0.0, 0.0, rotation_z


def list_unique_region_names(parts: list[bpy.types.Object]) -> list[str]:
    result: list[str] = []
    for part in parts:
        region = str(part.get("atlas_region_name", ""))
        if region and region not in result:
            result.append(region)
    return result

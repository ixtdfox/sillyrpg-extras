from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .mask_schema import TerrainMask, TerrainZone

if TYPE_CHECKING:
    import bpy


ADDON_ID = "procedural_floorplan_ru_v2"


@dataclass(frozen=True)
class GridRectangle:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class EdgeSegment:
    orientation: str
    line: int
    start: int
    length: int


def decompose_zone_to_rectangles(mask: TerrainMask, zone: TerrainZone) -> list[GridRectangle]:
    visited = [[False for _x in range(mask.width)] for _y in range(mask.height)]
    rectangles: list[GridRectangle] = []

    for py in range(mask.height):
        for px in range(mask.width):
            if visited[py][px] or mask.zone_at(px, py) != zone:
                continue
            width = 1
            while px + width < mask.width and not visited[py][px + width] and mask.zone_at(px + width, py) == zone:
                width += 1
            height = 1
            while py + height < mask.height:
                row_ok = True
                for cursor_x in range(px, px + width):
                    if visited[py + height][cursor_x] or mask.zone_at(cursor_x, py + height) != zone:
                        row_ok = False
                        break
                if not row_ok:
                    break
                height += 1
            for fill_y in range(py, py + height):
                for fill_x in range(px, px + width):
                    visited[fill_y][fill_x] = True
            rectangles.append(GridRectangle(px, py, width, height))
    return rectangles


def create_zone_rectangles(
    *,
    scene,
    collection,
    mask: TerrainMask,
    zone: TerrainZone,
    material,
    object_prefix: str,
    top_z: float,
    thickness: float,
) -> list[bpy.types.Object]:
    import bpy

    objects: list[bpy.types.Object] = []
    for index, rect in enumerate(decompose_zone_to_rectangles(mask, zone)):
        min_x, min_y, max_x, max_y = mask.rect_world_bounds(rect.x, rect.y, rect.width, rect.height)
        obj = create_box_object(
            name=f"{object_prefix}_{index:03d}",
            collection=collection,
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            min_z=top_z - thickness,
            max_z=top_z,
            material=material,
            building_part=zone.value,
        )
        obj["terrain_zone"] = zone.value
        objects.append(obj)
    return objects


def create_box_object(
    *,
    name: str,
    collection,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    min_z: float,
    max_z: float,
    material,
    building_part: str,
) -> "bpy.types.Object":
    import bpy
    from mathutils import Vector

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    vertices = [
        Vector((min_x, min_y, min_z)),
        Vector((max_x, min_y, min_z)),
        Vector((max_x, max_y, min_z)),
        Vector((min_x, max_y, min_z)),
        Vector((min_x, min_y, max_z)),
        Vector((max_x, min_y, max_z)),
        Vector((max_x, max_y, max_z)),
        Vector((min_x, max_y, max_z)),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata([tuple(vertex) for vertex in vertices], [], faces)
    mesh.update(calc_edges=True)
    if material is not None:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj["generated_by"] = ADDON_ID
    obj["building_part"] = building_part
    obj["terrain_generated"] = True
    if obj not in collection.objects[:]:
        collection.objects.link(obj)
    return obj


def collect_curb_segments(mask: TerrainMask, road_zone: TerrainZone = TerrainZone.ROAD) -> list[EdgeSegment]:
    horizontal: dict[int, list[tuple[int, int]]] = {}
    vertical: dict[int, list[tuple[int, int]]] = {}
    curb_neighbors = {TerrainZone.SIDEWALK, TerrainZone.GRASS}

    for py in range(mask.height):
        for px in range(mask.width):
            if mask.zone_at(px, py) != road_zone:
                continue
            if mask.zone_at(px, py - 1) in curb_neighbors:
                horizontal.setdefault(py, []).append((px, px + 1))
            if mask.zone_at(px, py + 1) in curb_neighbors:
                horizontal.setdefault(py + 1, []).append((px, px + 1))
            if mask.zone_at(px - 1, py) in curb_neighbors:
                vertical.setdefault(px, []).append((py, py + 1))
            if mask.zone_at(px + 1, py) in curb_neighbors:
                vertical.setdefault(px + 1, []).append((py, py + 1))

    segments: list[EdgeSegment] = []
    for line, spans in horizontal.items():
        segments.extend(_merge_spans("horizontal", line, spans))
    for line, spans in vertical.items():
        segments.extend(_merge_spans("vertical", line, spans))
    return segments


def _merge_spans(orientation: str, line: int, spans: list[tuple[int, int]]) -> list[EdgeSegment]:
    ordered = sorted(spans)
    if not ordered:
        return []
    merged: list[EdgeSegment] = []
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        merged.append(EdgeSegment(orientation=orientation, line=line, start=current_start, length=current_end - current_start))
        current_start, current_end = start, end
    merged.append(EdgeSegment(orientation=orientation, line=line, start=current_start, length=current_end - current_start))
    return merged


def create_curb_objects(
    *,
    collection,
    mask: TerrainMask,
    material,
    road_z: float,
    curb_height: float,
    curb_width: float,
) -> list["bpy.types.Object"]:
    import bpy

    objects: list[bpy.types.Object] = []
    half_width = curb_width * 0.5
    for index, segment in enumerate(collect_curb_segments(mask)):
        if segment.orientation == "horizontal":
            min_x = mask.offset_x + segment.start * mask.pixel_size_m
            max_x = min_x + segment.length * mask.pixel_size_m
            center_line_y = mask.offset_y + (mask.height - segment.line) * mask.pixel_size_m
            min_y = center_line_y - half_width
            max_y = center_line_y + half_width
        else:
            center_line_x = mask.offset_x + segment.line * mask.pixel_size_m
            min_x = center_line_x - half_width
            max_x = center_line_x + half_width
            max_y = mask.offset_y + (mask.height - segment.start) * mask.pixel_size_m
            min_y = max_y - segment.length * mask.pixel_size_m
        obj = create_box_object(
            name=f"Curb_{index:03d}",
            collection=collection,
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            min_z=road_z,
            max_z=road_z + curb_height,
            material=material,
            building_part="curb",
        )
        obj["terrain_zone"] = "curb"
        objects.append(obj)
    return objects

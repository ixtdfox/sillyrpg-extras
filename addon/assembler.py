"""Geometry assembly for building masses, floors, walls, roof, and details."""

from __future__ import annotations

import bmesh
import bpy
from .batching import BuildBatch

WALL_THICKNESS = 0.2
SLAB_THICKNESS = 0.22
EPS = 0.015


def _new_mesh_object(name: str, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _add_box(name: str, origin, size):
    ox, oy, oz = origin
    sx, sy, sz = size
    x2, y2, z2 = ox + sx, oy + sy, oz + sz
    verts = [
        (ox, oy, oz),
        (x2, oy, oz),
        (x2, y2, oz),
        (ox, y2, oz),
        (ox, oy, z2),
        (x2, oy, z2),
        (x2, y2, z2),
        (ox, y2, z2),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return _new_mesh_object(name, verts, faces)


def _opening_segments(total_w, opening_x, opening_w):
    left = (0.0, max(0.0, opening_x))
    right_start = min(total_w, opening_x + opening_w)
    right = (right_start, total_w)
    segments = []
    if left[1] - left[0] > 0.02:
        segments.append(left)
    if right[1] - right[0] > 0.02:
        segments.append(right)
    return segments


def _build_volume(batch: BuildBatch, volume, styled, floors, floor_h):
    # Slabs
    for f in range(floors):
        z = volume.z + f * floor_h
        slab = _add_box(
            f"{volume.name}_slab_{f}",
            (volume.x, volume.y, z),
            (volume.width, volume.depth, SLAB_THICKNESS),
        )
        batch.add(slab)

    # Roof slab + parapet + equipment
    roof_z = volume.z + volume.height
    roof = _add_box(
        f"{volume.name}_roof",
        (volume.x, volume.y, roof_z - SLAB_THICKNESS),
        (volume.width, volume.depth, SLAB_THICKNESS),
    )
    batch.add(roof)
    parapet = _add_box(
        f"{volume.name}_parapet",
        (volume.x - EPS, volume.y - EPS, roof_z),
        (volume.width + 2 * EPS, volume.depth + 2 * EPS, 0.35),
    )
    batch.add(parapet)

    equip = _add_box(
        f"{volume.name}_hvac",
        (volume.x + volume.width * 0.7, volume.y + volume.depth * 0.7, roof_z + 0.35),
        (1.0, 0.8, 0.6),
    )
    batch.add(equip)

    openings = [o for o in styled.openings if o.volume_name == volume.name and o.face == "front"]

    # Walls per floor with opening replacement on front side.
    for f in range(floors):
        z0 = volume.z + f * floor_h + SLAB_THICKNESS - EPS
        wall_h = floor_h - SLAB_THICKNESS + EPS

        floor_openings = [o for o in openings if z0 <= volume.z + o.z_offset <= z0 + wall_h]
        if floor_openings:
            op = floor_openings[0]
            for sx0, sx1 in _opening_segments(volume.width, op.x_offset, op.width):
                wall = _add_box(
                    f"{volume.name}_front_wall_{f}_{sx0:.2f}",
                    (volume.x + sx0, volume.y - WALL_THICKNESS + EPS, z0),
                    (sx1 - sx0, WALL_THICKNESS, wall_h),
                )
                batch.add(wall)

            top_h = wall_h - (op.z_offset + op.height - f * floor_h)
            if top_h > 0.02:
                lintel = _add_box(
                    f"{volume.name}_lintel_{f}",
                    (volume.x + op.x_offset, volume.y - WALL_THICKNESS + EPS, volume.z + op.z_offset + op.height),
                    (op.width, WALL_THICKNESS, top_h),
                )
                batch.add(lintel)
        else:
            wall = _add_box(
                f"{volume.name}_front_wall_{f}",
                (volume.x, volume.y - WALL_THICKNESS + EPS, z0),
                (volume.width, WALL_THICKNESS, wall_h),
            )
            batch.add(wall)

        # other walls (solid)
        side_a = _add_box(
            f"{volume.name}_left_wall_{f}",
            (volume.x - EPS, volume.y, z0),
            (WALL_THICKNESS, volume.depth, wall_h),
        )
        side_b = _add_box(
            f"{volume.name}_right_wall_{f}",
            (volume.x + volume.width - WALL_THICKNESS + EPS, volume.y, z0),
            (WALL_THICKNESS, volume.depth, wall_h),
        )
        back = _add_box(
            f"{volume.name}_back_wall_{f}",
            (volume.x, volume.y + volume.depth - EPS, z0),
            (volume.width, WALL_THICKNESS, wall_h),
        )
        for o in (side_a, side_b, back):
            batch.add(o)


def _build_balcony(batch: BuildBatch, volume, balcony):
    base = _add_box(
        f"{volume.name}_balcony",
        (
            volume.x + balcony["x_offset"],
            volume.y - balcony["depth"] + EPS,
            volume.z + volume.height - 0.22,
        ),
        (balcony["width"], balcony["depth"], balcony["height"]),
    )
    rail = _add_box(
        f"{volume.name}_balcony_rail",
        (
            volume.x + balcony["x_offset"],
            volume.y - balcony["depth"] + EPS,
            volume.z + volume.height - 0.1,
        ),
        (balcony["width"], 0.06, 1.05),
    )
    batch.add(base)
    batch.add(rail)


def _build_stairs(batch: BuildBatch, stair_plan, main):
    if not stair_plan.required or not stair_plan.valid:
        return

    risers = 16
    tread = stair_plan.run / risers
    rise = stair_plan.rise / risers

    for i in range(risers):
        step = _add_box(
            f"stair_step_{i}",
            (main.x + stair_plan.x, main.y + stair_plan.y + i * tread, main.z + i * rise),
            (stair_plan.width, tread + EPS, rise),
        )
        batch.add(step)

    landing = _add_box(
        "stair_landing",
        (
            main.x + stair_plan.x,
            main.y + stair_plan.y + stair_plan.run,
            main.z + stair_plan.rise,
        ),
        (stair_plan.width, stair_plan.top_landing, 0.12),
    )
    batch.add(landing)


def assemble(context, styled_shape, stair_plan, params):
    del context
    batch = BuildBatch()
    floor_h = params["floor_height"]
    floors = params["floors"]

    for volume in styled_shape.shape.volumes:
        vol_floors = max(1, round(volume.height / floor_h))
        _build_volume(batch, volume, styled_shape, vol_floors, floor_h)

    for bal in styled_shape.balconies:
        volume = next((v for v in styled_shape.shape.volumes if v.name == bal["volume_name"]), None)
        if volume:
            _build_balcony(batch, volume, bal)

    main = next((v for v in styled_shape.shape.volumes if v.name == "main"), None)
    if floors > 1 and main is not None:
        _build_stairs(batch, stair_plan, main)

    return batch.objects


def cleanup_meshes(context, objects):
    del context
    for obj in objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

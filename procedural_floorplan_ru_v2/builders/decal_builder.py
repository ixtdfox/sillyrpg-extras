from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..common.utils import ensure_child_collection
from ..decal_manifest import DecalRuntime, ensure_decal_image, ensure_decal_material, load_decal_runtime
from ..factories.decal_mesh_factory import DecalMeshFactory
from .base_builder import BaseBuilder


class DecalBuilder(BaseBuilder):
    """Builds facade decal planes after all primary facade geometry is ready."""

    builder_id = "decal"

    def __init__(self):
        self.decal_factory = DecalMeshFactory()

    def enabled(self, context) -> bool:
        story_plan = getattr(context, "story_plan", None)
        building_plan = getattr(context, "building_plan", None)
        return bool(
            context.settings.decals.enabled
            and context.settings.decals.enable_streaks
            and context.outer_wall_objects
            and story_plan is not None
            and building_plan is not None
            and story_plan.story_index == (building_plan.story_count - 1)
        )

    def build(self, context) -> list[bpy.types.Object]:
        if not self._has_roof(context):
            return []

        runtime = load_decal_runtime(context.settings)
        if runtime is None:
            return []

        image = ensure_decal_image(runtime)
        if image is None:
            return []

        material = ensure_decal_material(image)
        decal_collection = ensure_child_collection(context.collection, "Decals")
        context.decal_collection = decal_collection

        objects: list[bpy.types.Object] = []
        for wall_obj in self._iter_target_walls(context):
            objects.extend(
                self._build_wall_streaks(
                    context,
                    wall_obj=wall_obj,
                    runtime=runtime,
                    material=material,
                    target_collection=decal_collection,
                    start_index=len(objects) + 1,
                )
            )

        context.decal_objects.extend(objects)
        context.created_objects.extend(objects)
        return objects

    def _iter_target_walls(self, context):
        for wall_obj in context.outer_wall_objects:
            if wall_obj is None or wall_obj.type != "MESH":
                continue
            if wall_obj.get("building_part") != "outer_wall":
                continue
            if wall_obj.get("is_decal") or wall_obj.get("is_window_glass"):
                continue
            yield wall_obj

    def _build_wall_streaks(
        self,
        context,
        *,
        wall_obj: bpy.types.Object,
        runtime: DecalRuntime,
        material: bpy.types.Material,
        target_collection: bpy.types.Collection,
        start_index: int,
    ) -> list[bpy.types.Object]:
        wall_length = max(0.1, float(wall_obj.get("wall_width", max(wall_obj.dimensions.x, wall_obj.dimensions.y))))
        slot_count = max(1, int(math.floor(wall_length + 1e-6)))
        if slot_count <= 0:
            return []

        density = float(context.settings.decals.density)
        half_length = wall_length * 0.5
        slot_width = wall_length / slot_count
        tangent_world, up_world, normal_world = self._wall_basis(wall_obj)
        wall_top_z = float(wall_obj.location.z + (wall_obj.dimensions.z * 0.5))

        created: list[bpy.types.Object] = []
        for slot_index in range(slot_count):
            if context.rng.random() > density:
                continue

            entry = self._pick_entry(runtime, context)
            width = min(float(entry.tile_width_m), max(0.1, wall_length - 0.05))
            height = min(float(entry.tile_height_m), max(0.05, wall_obj.dimensions.z - 0.05))
            entry_world = _RuntimeEntryView(runtime, entry, width=width, height=height)

            slot_start = -half_length + (slot_index * slot_width)
            slot_end = slot_start + slot_width
            global_min = -half_length + (width * 0.5)
            global_max = half_length - (width * 0.5)
            if global_min > global_max:
                continue

            local_min = max(global_min, slot_start + 0.05)
            local_max = min(global_max, slot_end - 0.05)
            if local_min <= local_max:
                tangent_offset = context.rng.uniform(local_min, local_max)
            else:
                tangent_offset = min(max((slot_start + slot_end) * 0.5, global_min), global_max)

            created.append(
                self.decal_factory.create_decal_object(
                    context,
                    target_collection=target_collection,
                    wall_obj=wall_obj,
                    entry=entry_world,
                    material=material,
                    tangent_world=tangent_world,
                    up_world=up_world,
                    normal_world=normal_world,
                    tangent_offset=tangent_offset,
                    anchor_top_z=wall_top_z,
                    decal_index=start_index + len(created),
                )
            )
        return created

    def _pick_entry(self, runtime: DecalRuntime, context):
        entry_count = len(runtime.streak_entries)
        if entry_count == 1:
            return runtime.streak_entries[0]
        return runtime.streak_entries[context.rng.randrange(entry_count)]

    def _wall_basis(self, wall_obj: bpy.types.Object) -> tuple[Vector, Vector, Vector]:
        up_world = Vector((0.0, 0.0, 1.0))
        orientation = str(wall_obj.get("wall_orientation", "x"))
        side = str(wall_obj.get("edge_side", "north"))

        if orientation == "x":
            normal_world = Vector((0.0, 1.0 if side == "north" else -1.0, 0.0))
        else:
            normal_world = Vector((1.0 if side == "east" else -1.0, 0.0, 0.0))
        tangent_world = up_world.cross(normal_world).normalized()
        return tangent_world, up_world, normal_world

    def _has_roof(self, context) -> bool:
        return any(str(obj.get("building_part", "")) == "roof" for obj in context.created_objects)


class _RuntimeEntryView:
    def __init__(self, runtime: DecalRuntime, entry, *, width: float, height: float):
        self.id = entry.id
        self.kind = entry.kind
        self.x = entry.x
        self.y = entry.y
        self.w = entry.w
        self.h = entry.h
        self.tile_width_m = width
        self.tile_height_m = height
        self.atlas_width = float(runtime.atlas_width)
        self.atlas_height = float(runtime.atlas_height)

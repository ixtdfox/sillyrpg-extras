from __future__ import annotations

import bpy

from ..builders.wall_utils import build_box_mesh
from ..common.utils import apply_story_object_context, link_object, tag_generated_object
from ..domain.railings import RailingPostPlacement, RailingRailSegment


class RoofRailingMeshFactory:
    """Creates roof railing posts and rails from planned contour-following runs."""

    def create_post_object(
        self,
        context,
        placement: RailingPostPlacement,
        *,
        post_index: int,
        railing_tile_id: str,
        surface_type: str = "roof",
    ) -> bpy.types.Object:
        post_size = float(context.settings.roof_railing.post_size)
        height = float(context.settings.roof_railing.height)
        base_z = float(context.settings.walls.wall_height)
        mesh = bpy.data.meshes.new(f"RailingPostMesh_{post_index:04d}")
        build_box_mesh(mesh, size_x=post_size, size_y=post_size, size_z=height)

        name_prefix = "TerraceRailingPost" if surface_type == "terrace" else "RailingPost"
        obj = bpy.data.objects.new(f"{name_prefix}_{post_index:04d}", mesh)
        obj.location = (placement.x, placement.y, base_z + (height * 0.5))
        self._tag_railing_object(
            obj,
            context,
            surface_type=surface_type,
            railing_part="post",
            railing_tile_id=railing_tile_id,
            run_id=placement.run_id,
            is_corner_post=placement.is_corner,
            corner_type=placement.corner_type,
        )
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def create_rail_object(
        self,
        context,
        segment: RailingRailSegment,
        *,
        rail_index: int,
        railing_tile_id: str,
        surface_type: str = "roof",
    ) -> bpy.types.Object:
        thickness = float(context.settings.roof_railing.rail_thickness)
        height = float(context.settings.roof_railing.height)
        rail_count = max(1, int(context.settings.roof_railing.rail_count))
        base_z = float(context.settings.walls.wall_height)
        top_center_offset = max(thickness * 0.5, height - (thickness * 0.5))
        if rail_count == 1:
            center_offset = top_center_offset
        else:
            center_offset = top_center_offset * float(segment.level_index + 1) / float(rail_count)
        rail_z = base_z + center_offset
        length = abs(segment.end_x - segment.start_x) if segment.orientation == "x" else abs(segment.end_y - segment.start_y)
        mesh = bpy.data.meshes.new(f"RailingRailMesh_{rail_index:04d}")
        if segment.orientation == "x":
            build_box_mesh(mesh, size_x=max(length, 0.04), size_y=thickness, size_z=thickness)
            center = ((segment.start_x + segment.end_x) * 0.5, segment.start_y, rail_z)
        else:
            build_box_mesh(mesh, size_x=thickness, size_y=max(length, 0.04), size_z=thickness)
            center = (segment.start_x, (segment.start_y + segment.end_y) * 0.5, rail_z)

        name_prefix = "TerraceRailingRail" if surface_type == "terrace" else "RailingRail"
        obj = bpy.data.objects.new(f"{name_prefix}_{rail_index:04d}", mesh)
        obj.location = center
        self._tag_railing_object(
            obj,
            context,
            surface_type=surface_type,
            railing_part="rail",
            railing_tile_id=railing_tile_id,
            run_id=segment.run_id,
            is_corner_post=False,
            corner_type=None,
        )
        obj["rail_level_index"] = int(segment.level_index)
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _tag_railing_object(
        self,
        obj,
        context,
        *,
        surface_type: str,
        railing_part: str,
        railing_tile_id: str,
        run_id: str | None,
        is_corner_post: bool,
        corner_type: str | None,
    ) -> None:
        tag_generated_object(obj, "terrace_railing" if surface_type == "terrace" else "roof_railing")
        obj["surface_type"] = surface_type
        obj["railing_part"] = railing_part
        obj["railing_height"] = float(context.settings.roof_railing.height)
        obj["post_size"] = float(context.settings.roof_railing.post_size)
        obj["rail_thickness"] = float(context.settings.roof_railing.rail_thickness)
        obj["rail_count"] = int(context.settings.roof_railing.rail_count)
        if run_id:
            obj["run_id"] = run_id
        obj["is_corner_post"] = is_corner_post
        if corner_type:
            obj["corner_type"] = corner_type
        obj["atlas_category"] = "railings"
        if railing_tile_id:
            obj["atlas_tile_id"] = railing_tile_id

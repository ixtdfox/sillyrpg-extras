from __future__ import annotations

import bpy

from .. import atlas
from ..builders.wall_utils import build_box_mesh
from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, tag_generated_object
from ..domain.borders import BorderSegment


class BorderMeshFactory:
    """Creates Blender mesh objects for border segments."""

    def create_border_object(
        self,
        context,
        segment: BorderSegment,
        *,
        border_index: int,
    ) -> bpy.types.Object:
        size_x, size_y, size_z, center = self._segment_geometry(context, segment)
        prefix_map = {
            "floor_band": "FloorBand",
            "roof_border": "RoofBorder",
            "terrace_border": "TerraceBorder",
        }
        prefix = prefix_map.get(segment.border_type, "Border")
        mesh = bpy.data.meshes.new(f"{prefix}Mesh_{segment.orientation.upper()}_{border_index:04d}")
        build_box_mesh(mesh, size_x=size_x, size_y=size_y, size_z=size_z)

        obj = bpy.data.objects.new(f"{prefix}_{segment.orientation.upper()}_{border_index:04d}", mesh)
        obj.location = center
        tile_x, tile_y = self._tile_anchor(segment)
        tag_generated_object(obj, "border", tile_x=tile_x, tile_y=tile_y, tile_size=FLOOR_TILE_SIZE_M)
        obj["border_type"] = segment.border_type
        obj["border_depth"] = float(segment.depth)
        obj["border_height"] = float(segment.height)
        obj["wall_orientation"] = segment.orientation
        obj["edge_side"] = segment.side
        obj["boundary_run_id"] = segment.boundary_run_id
        obj["surface_type"] = "terrace" if segment.border_type == "terrace_border" else "roof" if segment.border_type == "roof_border" else "story"
        if segment.story_index is not None:
            obj["story_index"] = int(segment.story_index)
        obj["atlas_category"] = "floor_bands" if segment.border_type == "floor_band" else "roof_borders"
        border_tile_id = atlas.resolve_border_tile_id(context, segment.border_type)
        if border_tile_id:
            obj["atlas_tile_id"] = border_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _segment_geometry(self, context, segment: BorderSegment) -> tuple[float, float, float, tuple[float, float, float]]:
        if segment.orientation == "x":
            start = round(segment.start - segment.cap_start + segment.trim_start, 6)
            end = round(segment.end + segment.cap_end - segment.trim_end, 6)
            center_x = round((start + end) * 0.5, 6)
            center_y = round(segment.line + (segment.depth * 0.5 if segment.side == "north" else -segment.depth * 0.5), 6)
            return (
                round(end - start, 6),
                segment.depth,
                segment.height,
                (center_x, center_y, round(segment.base_z + segment.height * 0.5, 6)),
            )

        start = round(segment.start - segment.cap_start + segment.trim_start, 6)
        end = round(segment.end + segment.cap_end - segment.trim_end, 6)
        center_y = round((start + end) * 0.5, 6)
        center_x = round(segment.line + (segment.depth * 0.5 if segment.side == "east" else -segment.depth * 0.5), 6)
        return (
            segment.depth,
            round(end - start, 6),
            segment.height,
            (center_x, center_y, round(segment.base_z + segment.height * 0.5, 6)),
        )

    def _tile_anchor(self, segment: BorderSegment) -> tuple[int, int]:
        if segment.orientation == "x":
            return int(segment.start), int(segment.line)
        return int(segment.line), int(segment.start)

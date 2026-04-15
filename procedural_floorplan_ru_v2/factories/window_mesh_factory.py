from __future__ import annotations

import bpy

from .. import atlas
from ..builders.wall_utils import build_box_mesh
from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, quantize_025, tag_generated_object
from ..domain.windows import WindowPlacement


class WindowMeshFactory:
    """Создаёт только стекло окна по window placement."""

    def create_window_objects(
        self,
        context,
        placement: WindowPlacement,
        *,
        window_index: int,
    ) -> list[bpy.types.Object]:
        glass = self._create_glass_object(context, placement, window_index)
        return [glass]

    def _create_glass_object(self, context, placement: WindowPlacement, window_index: int) -> bpy.types.Object:
        size_x, size_y, size_z, center = self._glass_geometry(context, placement)
        mesh = bpy.data.meshes.new(f"WindowGlassMesh_{window_index:03d}")
        build_box_mesh(mesh, size_x=size_x, size_y=size_y, size_z=size_z)
        obj = bpy.data.objects.new(f"WindowGlass_{window_index:03d}", mesh)
        obj.location = center
        self._tag_window_object(obj, placement, is_glass=True)
        obj["atlas_category"] = "glass"
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _tag_window_object(self, obj, placement: WindowPlacement, *, is_glass: bool) -> None:
        if placement.orientation == "x":
            tile_x = int(placement.center)
            tile_y = int(placement.line)
        else:
            tile_x = int(placement.line)
            tile_y = int(placement.center)
        tag_generated_object(obj, "window", tile_x=tile_x, tile_y=tile_y, tile_size=FLOOR_TILE_SIZE_M)
        obj["window_width"] = float(placement.width)
        obj["window_height"] = float(placement.height)
        obj["window_sill_height"] = float(placement.sill_height)
        obj["wall_orientation"] = placement.orientation
        obj["edge_side"] = placement.host_wall_side
        obj["is_window_glass"] = bool(is_glass)

    def _glass_geometry(self, context, placement: WindowPlacement) -> tuple[float, float, float, tuple[float, float, float]]:
        wall_half = float(context.settings.walls.wall_thickness) * 0.5
        glass_thickness = min(0.05, wall_half * 2.0)
        width = max(0.1, placement.width - 0.05)
        height = max(0.1, placement.height - 0.05)
        center_z = placement.sill_height + placement.height * 0.5
        if placement.orientation == "x":
            center = (
                placement.center,
                placement.line + (wall_half if placement.host_wall_side == "north" else -wall_half),
                center_z,
            )
            return width, glass_thickness, height, center
        center = (
            placement.line + (wall_half if placement.host_wall_side == "east" else -wall_half),
            placement.center,
            center_z,
        )
        return glass_thickness, width, height, center

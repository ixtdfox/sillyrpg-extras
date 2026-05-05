from __future__ import annotations

import json
import math

import bpy

from .. import atlas
from ..builders.wall_utils import build_box_mesh
from ..common.utils import FLOOR_TILE_SIZE_M, apply_story_object_context, link_object, quantize_025, tag_generated_object
from ..domain.doors import DoorPlacement
from ..grid import RectCell, RectEdge, create_game_rect_layout


class DoorMeshFactory:
    """Создаёт Blender-объекты дверей по доменным placement-описаниям."""

    def create_door_object(
        self,
        context,
        placement: DoorPlacement,
        *,
        door_index: int,
    ) -> bpy.types.Object:
        size_x, size_y, size_z, center = self._door_geometry(context, placement)
        if placement.door_type == "entry":
            prefix = "EntryDoor"
        elif placement.door_type == "external_stair":
            prefix = "ExternalStairDoor"
        else:
            prefix = "InteriorDoor"
        mesh = bpy.data.meshes.new(f"{prefix}Mesh_{door_index:03d}")
        build_box_mesh(mesh, size_x=size_x, size_y=size_y, size_z=size_z)
        obj = bpy.data.objects.new(f"{prefix}_{door_index:03d}", mesh)
        obj.location = center
        tile_x, tile_y = self._tile_anchor(placement)
        tag_generated_object(
            obj,
            "door",
            tile_x=tile_x,
            tile_y=tile_y,
            tile_size=FLOOR_TILE_SIZE_M,
        )
        obj["door_type"] = placement.door_type
        obj["door_width"] = float(placement.width)
        obj["door_height"] = float(placement.height)
        obj["door_thickness"] = float(placement.thickness)
        obj["wall_orientation"] = placement.orientation
        obj["edge_side"] = placement.host_wall_side
        obj["door_slot_start"] = float(placement.slot_start)
        obj["door_slot_end"] = float(placement.slot_end)
        door_edge = self._door_edge(placement)
        edge_center = create_game_rect_layout().edge_center(door_edge)
        actual_center = (float(obj.location.x), float(obj.location.y))
        if abs(actual_center[0] - edge_center[0]) > 0.51 or abs(actual_center[1] - edge_center[1]) > 0.51:
            print(
                f"[GridValidation] Door {obj.name} is misaligned: "
                f"expected edge center=({edge_center[0]:.3f}, {edge_center[1]:.3f}) "
                f"actual=({actual_center[0]:.3f}, {actual_center[1]:.3f}) edge={door_edge.key()}"
            )
        obj["opensNavigationEdge"] = True
        obj["door_edge"] = json.dumps(door_edge.to_game_dict(), separators=(",", ":"))
        obj["door_center_world"] = json.dumps({"x": edge_center[0], "z": edge_center[1]}, separators=(",", ":"))
        obj["atlas_category"] = "outside_doors" if placement.door_type in {"entry", "external_stair"} else "inside_doors"
        door_tile_id = atlas.resolve_door_tile_id(context, placement.door_type)
        if door_tile_id:
            obj["atlas_tile_id"] = door_tile_id
        if placement.room_a_id is not None:
            obj["room_a_id"] = int(placement.room_a_id)
        if placement.room_b_id is not None:
            obj["room_b_id"] = int(placement.room_b_id)
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _door_geometry(self, context, placement: DoorPlacement) -> tuple[float, float, float, tuple[float, float, float]]:
        wall_half_thickness = float(context.settings.walls.wall_thickness) * 0.5
        if placement.orientation == "x":
            size_x = placement.width
            size_y = placement.thickness
            center_y = quantize_025(
                placement.line
                + (wall_half_thickness if placement.host_wall_side in {"north", "east"} else -wall_half_thickness)
            )
            center = (
                placement.center,
                center_y,
                placement.height / 2.0,
            )
        else:
            size_x = placement.thickness
            size_y = placement.width
            center_x = quantize_025(
                placement.line
                + (wall_half_thickness if placement.host_wall_side in {"north", "east"} else -wall_half_thickness)
            )
            center = (
                center_x,
                placement.center,
                placement.height / 2.0,
            )
        return size_x, size_y, placement.height, center

    def _tile_anchor(self, placement: DoorPlacement) -> tuple[int, int]:
        if placement.orientation == "x":
            return int(placement.center), int(placement.line)
        return int(placement.line), int(placement.center)

    def _door_edge(self, placement: DoorPlacement) -> RectEdge:
        if placement.orientation == "x":
            x = math.floor(float(placement.center))
            y_line = round(float(placement.line))
            return RectEdge(RectCell(x, y_line - 1), RectCell(x, y_line))
        x_line = round(float(placement.line))
        y = math.floor(float(placement.center))
        return RectEdge(RectCell(x_line - 1, y), RectCell(x_line, y))

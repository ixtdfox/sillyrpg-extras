from __future__ import annotations

import bpy

from .. import atlas
from ..builders.wall_utils import build_box_mesh
from ..common.utils import apply_story_object_context, link_object, tag_generated_object
from ..domain.stairs import StairPlacement


class StairMeshFactory:
    """Builds a compact switchback stair out of simple box meshes."""

    PLATFORM_THICKNESS = 0.14
    LANDING_THICKNESS = 0.16

    def create_stair_objects(self, context, placement: StairPlacement, *, stair_index: int) -> list[bpy.types.Object]:
        stair_tile_id = atlas.resolve_stair_tile_id(context, "steps")
        landing_tile_id = atlas.resolve_stair_tile_id(context, "landing")
        if placement.orientation == "x":
            return self._create_horizontal_stair(context, placement, stair_index=stair_index, stair_tile_id=stair_tile_id, landing_tile_id=landing_tile_id)
        return self._create_vertical_stair(context, placement, stair_index=stair_index, stair_tile_id=stair_tile_id, landing_tile_id=landing_tile_id)

    def _create_horizontal_stair(self, context, placement: StairPlacement, *, stair_index: int, stair_tile_id: str, landing_tile_id: str) -> list[bpy.types.Object]:
        objects: list[bpy.types.Object] = []
        top_elevation = float(placement.top_elevation if placement.top_elevation is not None else context.settings.walls.wall_height)
        x0 = float(placement.x)
        y0 = float(placement.y)
        x1 = x0 + float(placement.length)
        y1 = y0 + float(placement.width)
        lane = min(float(placement.stair_width), max(0.6, (y1 - y0) * 0.45))
        lane_bottom_y0 = y0
        lane_bottom_y1 = y0 + lane
        lane_top_y1 = y1
        lane_top_y0 = y1 - lane
        mid_landing_start = x1 - float(placement.mid_landing_size)
        lower_run = max(0.5, mid_landing_start - x0)
        upper_run = max(0.5, mid_landing_start - (x0 + float(placement.landing_size)))
        tread_a = lower_run / max(placement.lower_riser_count, 1)
        tread_b = upper_run / max(placement.upper_riser_count, 1)
        lower_total_rise = placement.lower_riser_count * float(placement.riser_height)

        for step_index in range(placement.lower_riser_count):
            sx0 = x0 + (tread_a * step_index)
            sx1 = sx0 + tread_a
            step_height = (step_index + 1) * float(placement.riser_height)
            objects.append(
                self._create_box_object(
                    context,
                    placement,
                    name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_StepA_{step_index + 1:02d}",
                    center=((sx0 + sx1) * 0.5, (lane_bottom_y0 + lane_bottom_y1) * 0.5, step_height * 0.5),
                    size=(sx1 - sx0, lane_bottom_y1 - lane_bottom_y0, step_height),
                    atlas_category="stairs",
                    atlas_tile_id=stair_tile_id,
                    building_part="stair",
                )
            )

        objects.append(
            self._create_box_object(
                context,
                placement,
                name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_MidLanding",
                center=((mid_landing_start + x1) * 0.5, (y0 + y1) * 0.5, lower_total_rise + (self.LANDING_THICKNESS * 0.5)),
                size=(x1 - mid_landing_start, y1 - y0, self.LANDING_THICKNESS),
                atlas_category="stair_landings",
                atlas_tile_id=landing_tile_id,
                building_part="stair",
            )
        )

        for step_index in range(placement.upper_riser_count):
            sx1 = mid_landing_start - (tread_b * step_index)
            sx0 = sx1 - tread_b
            step_height = lower_total_rise + ((step_index + 1) * float(placement.riser_height))
            objects.append(
                self._create_box_object(
                    context,
                    placement,
                    name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_StepB_{step_index + 1:02d}",
                    center=((sx0 + sx1) * 0.5, (lane_top_y0 + lane_top_y1) * 0.5, step_height * 0.5),
                    size=(sx1 - sx0, lane_top_y1 - lane_top_y0, step_height),
                    atlas_category="stairs",
                    atlas_tile_id=stair_tile_id,
                    building_part="stair",
                )
            )

        objects.append(
            self._create_box_object(
                context,
                placement,
                name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}",
                center=((x0 + (x0 + float(placement.landing_size))) * 0.5, (lane_top_y0 + lane_top_y1) * 0.5, top_elevation + (self.PLATFORM_THICKNESS * 0.5)),
                size=(float(placement.landing_size), lane_top_y1 - lane_top_y0, self.PLATFORM_THICKNESS),
                atlas_category="stair_landings",
                atlas_tile_id=landing_tile_id,
                building_part="stair",
            )
        )
        return objects

    def _create_vertical_stair(self, context, placement: StairPlacement, *, stair_index: int, stair_tile_id: str, landing_tile_id: str) -> list[bpy.types.Object]:
        objects: list[bpy.types.Object] = []
        top_elevation = float(placement.top_elevation if placement.top_elevation is not None else context.settings.walls.wall_height)
        x0 = float(placement.x)
        y0 = float(placement.y)
        x1 = x0 + float(placement.length)
        y1 = y0 + float(placement.width)
        lane = min(float(placement.stair_width), max(0.6, (x1 - x0) * 0.45))
        lane_left_x0 = x0
        lane_left_x1 = x0 + lane
        lane_right_x1 = x1
        lane_right_x0 = x1 - lane
        mid_landing_start = y1 - float(placement.mid_landing_size)
        lower_run = max(0.5, mid_landing_start - y0)
        upper_run = max(0.5, mid_landing_start - (y0 + float(placement.landing_size)))
        tread_a = lower_run / max(placement.lower_riser_count, 1)
        tread_b = upper_run / max(placement.upper_riser_count, 1)
        lower_total_rise = placement.lower_riser_count * float(placement.riser_height)

        for step_index in range(placement.lower_riser_count):
            sy0 = y0 + (tread_a * step_index)
            sy1 = sy0 + tread_a
            step_height = (step_index + 1) * float(placement.riser_height)
            objects.append(
                self._create_box_object(
                    context,
                    placement,
                    name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_StepA_{step_index + 1:02d}",
                    center=((lane_left_x0 + lane_left_x1) * 0.5, (sy0 + sy1) * 0.5, step_height * 0.5),
                    size=(lane_left_x1 - lane_left_x0, sy1 - sy0, step_height),
                    atlas_category="stairs",
                    atlas_tile_id=stair_tile_id,
                    building_part="stair",
                )
            )

        objects.append(
            self._create_box_object(
                context,
                placement,
                name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_MidLanding",
                center=((x0 + x1) * 0.5, (mid_landing_start + y1) * 0.5, lower_total_rise + (self.LANDING_THICKNESS * 0.5)),
                size=(x1 - x0, y1 - mid_landing_start, self.LANDING_THICKNESS),
                atlas_category="stair_landings",
                atlas_tile_id=landing_tile_id,
                building_part="stair",
            )
        )

        for step_index in range(placement.upper_riser_count):
            sy1 = mid_landing_start - (tread_b * step_index)
            sy0 = sy1 - tread_b
            step_height = lower_total_rise + ((step_index + 1) * float(placement.riser_height))
            objects.append(
                self._create_box_object(
                    context,
                    placement,
                    name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}_StepB_{step_index + 1:02d}",
                    center=((lane_right_x0 + lane_right_x1) * 0.5, (sy0 + sy1) * 0.5, step_height * 0.5),
                    size=(lane_right_x1 - lane_right_x0, sy1 - sy0, step_height),
                    atlas_category="stairs",
                    atlas_tile_id=stair_tile_id,
                    building_part="stair",
                )
            )

        objects.append(
            self._create_box_object(
                context,
                placement,
                name=f"Stair_Story{placement.from_story}_to_Story{placement.to_story}",
                center=((lane_right_x0 + lane_right_x1) * 0.5, (y0 + (y0 + float(placement.landing_size))) * 0.5, top_elevation + (self.PLATFORM_THICKNESS * 0.5)),
                size=(lane_right_x1 - lane_right_x0, float(placement.landing_size), self.PLATFORM_THICKNESS),
                atlas_category="stair_landings",
                atlas_tile_id=landing_tile_id,
                building_part="stair",
            )
        )
        return objects

    def _create_box_object(
        self,
        context,
        placement: StairPlacement,
        *,
        name: str,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        atlas_category: str,
        atlas_tile_id: str,
        building_part: str,
    ) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        build_box_mesh(mesh, size_x=max(size[0], 0.04), size_y=max(size[1], 0.04), size_z=max(size[2], 0.04))
        obj = bpy.data.objects.new(name, mesh)
        obj.location = center
        tag_generated_object(obj, building_part, tile_x=placement.x, tile_y=placement.y)
        obj["from_story"] = int(placement.from_story)
        obj["to_story"] = int(placement.to_story)
        obj["stair_width"] = float(placement.stair_width)
        obj["stair_riser"] = float(placement.riser_height)
        obj["stair_tread"] = float(placement.tread_depth)
        obj["landing_size"] = float(placement.landing_size)
        obj["mid_landing_size"] = float(placement.mid_landing_size)
        obj["stair_orientation"] = placement.orientation
        obj["stair_room_id"] = int(placement.room_id)
        obj["stair_kind"] = str(getattr(placement, "stair_kind", "internal"))
        obj["atlas_category"] = atlas_category
        if atlas_tile_id:
            obj["atlas_tile_id"] = atlas_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

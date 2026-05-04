from __future__ import annotations

import math

import bpy

from .. import atlas
from ..builders.wall_utils import build_box_mesh
from ..common.utils import apply_story_object_context, link_object, tag_generated_object
from ..domain.stairs import ExternalStairPlacement


class ExternalStairMeshFactory:
    """Creates landing decks, switchback stair modules, and simple safety rails outside the facade."""

    LANDING_THICKNESS = 0.16
    TREAD_THICKNESS = 0.04
    STRINGER_THICKNESS = 0.08

    def create_objects(self, context, placement: ExternalStairPlacement, *, stair_index: int) -> list[bpy.types.Object]:
        objects: list[bpy.types.Object] = []
        landing_tile_id = atlas.resolve_stair_tile_id(context, "landing")
        stair_tile_id = atlas.resolve_stair_tile_id(context, "steps")
        if self._should_create_door_landing(placement):
            objects.append(self._create_landing_object(context, placement, stair_index=stair_index, landing_tile_id=landing_tile_id))
            objects.extend(self._create_landing_rails(context, placement, stair_index=stair_index))
        if placement.switchback_placement is not None:
            objects.extend(self._create_lightweight_stair(context, placement, stair_index=stair_index, stair_tile_id=stair_tile_id, landing_tile_id=landing_tile_id))
        return objects

    def _should_create_door_landing(self, placement: ExternalStairPlacement) -> bool:
        return placement.story_index > 0

    def _external_story_span(self, context) -> tuple[int, int]:
        story_plan = getattr(context, "story_plan", None)
        from_story = int(getattr(story_plan, "story_index", 0))
        return from_story, from_story + 1

    def _tag_external_stair_object(
        self,
        obj: bpy.types.Object,
        context,
        *,
        stair_part: str,
        from_story: int | None = None,
        to_story: int | None = None,
        story_index: int | None = None,
        landing_story: int | None = None,
    ) -> None:
        default_from, default_to = self._external_story_span(context)
        if from_story is None:
            from_story = default_from
        if to_story is None:
            to_story = default_to
        if story_index is None:
            story_index = from_story
        obj["stair_kind"] = "external"
        obj["stair_part"] = stair_part
        obj["story_index"] = int(story_index)
        obj["from_story"] = int(from_story)
        obj["to_story"] = int(to_story)
        obj["game_visibility_behavior"] = "external_stair_connector"
        obj["game_hide_when_above_player"] = False
        if landing_story is not None:
            obj["stair_landing_story"] = int(landing_story)

    def _create_landing_object(self, context, placement: ExternalStairPlacement, *, stair_index: int, landing_tile_id: str) -> bpy.types.Object:
        x0, y0, x1, y1 = placement.door_landing_bounds
        mesh = bpy.data.meshes.new(f"ExternalLandingMesh_{stair_index:03d}")
        build_box_mesh(
            mesh,
            size_x=max(x1 - x0, 0.04),
            size_y=max(y1 - y0, 0.04),
            size_z=self.LANDING_THICKNESS,
        )
        obj = bpy.data.objects.new(f"ExternalLanding_Story{placement.story_index:02d}", mesh)
        obj.location = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, self.LANDING_THICKNESS * 0.5)
        tag_generated_object(obj, "stair", tile_x=int(x0), tile_y=int(y0))
        self._tag_external_stair_object(
            obj,
            context,
            stair_part="landing",
            from_story=max(0, int(placement.story_index) - 1),
            to_story=int(placement.story_index),
            story_index=int(placement.story_index),
            landing_story=int(placement.story_index),
        )
        obj["has_upward_flight"] = bool(placement.has_upward_flight)
        obj["stair_facade_orientation"] = placement.facade.orientation
        obj["stair_facade_side"] = placement.facade.side
        obj["atlas_category"] = "stair_landings"
        if landing_tile_id:
            obj["atlas_tile_id"] = landing_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _create_landing_rails(self, context, placement: ExternalStairPlacement, *, stair_index: int) -> list[bpy.types.Object]:
        x0, y0, x1, y1 = placement.door_landing_bounds
        fx0, fy0, fx1, fy1 = placement.flight_bounds
        eps = 1e-4
        base_z = self.LANDING_THICKNESS
        objects: list[bpy.types.Object] = []

        if placement.facade.orientation == "x":
            stair_connected_x = None
            if abs(fx1 - x0) < eps:
                stair_connected_x = x0
            elif abs(fx0 - x1) < eps:
                stair_connected_x = x1

            outer_edge_y = y1 if placement.facade.side == "north" else y0
            free_side_x = x1 if stair_connected_x == x0 else x0

            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="x",
                    fixed_coord=outer_edge_y,
                    segment_start=x0,
                    segment_end=x1,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix="Landing_Outer",
                )
            )
            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="y",
                    fixed_coord=free_side_x,
                    segment_start=y0,
                    segment_end=y1,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix="Landing_FreeSide",
                )
            )
        else:
            stair_connected_y = None
            if abs(fy1 - y0) < eps:
                stair_connected_y = y0
            elif abs(fy0 - y1) < eps:
                stair_connected_y = y1

            outer_edge_x = x1 if placement.facade.side == "east" else x0
            free_side_y = y1 if stair_connected_y == y0 else y0

            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="y",
                    fixed_coord=outer_edge_x,
                    segment_start=y0,
                    segment_end=y1,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix="Landing_Outer",
                )
            )
            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="x",
                    fixed_coord=free_side_y,
                    segment_start=x0,
                    segment_end=x1,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix="Landing_FreeSide",
                )
            )
        for obj in objects:
            obj["story_index"] = int(placement.story_index)
            obj["from_story"] = max(0, int(placement.story_index) - 1)
            obj["to_story"] = int(placement.story_index)
            obj["stair_landing_story"] = int(placement.story_index)
        return objects

    def _create_edge_post(
        self,
        context,
        x: float,
        y: float,
        height: float,
        post_size: float,
        stair_index: int,
        suffix: str,
        rail_tile_id: str,
        *,
        base_z: float = 0.0,
    ) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"ExternalStairPostMesh_{stair_index:03d}_{suffix}")
        build_box_mesh(mesh, size_x=post_size, size_y=post_size, size_z=height)
        obj = bpy.data.objects.new(f"ExternalStairPost_{stair_index:03d}_{suffix}", mesh)
        obj.location = (x, y, base_z + (height * 0.5))
        tag_generated_object(obj, "stair", tile_x=int(x), tile_y=int(y))
        self._tag_external_stair_object(obj, context, stair_part="rail_post")
        obj["atlas_category"] = "railings"
        if rail_tile_id:
            obj["atlas_tile_id"] = rail_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _create_edge_rail(
        self,
        context,
        *,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        stair_index: int,
        suffix: str,
        rail_tile_id: str,
    ) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"ExternalStairRailMesh_{stair_index:03d}_{suffix}")
        build_box_mesh(mesh, size_x=max(size[0], 0.04), size_y=max(size[1], 0.04), size_z=max(size[2], 0.04))
        obj = bpy.data.objects.new(f"ExternalStairRail_{stair_index:03d}_{suffix}", mesh)
        obj.location = center
        tag_generated_object(obj, "stair", tile_x=int(center[0]), tile_y=int(center[1]))
        self._tag_external_stair_object(obj, context, stair_part="rail")
        obj["atlas_category"] = "railings"
        if rail_tile_id:
            obj["atlas_tile_id"] = rail_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _rail_z(self, height: float, rail_thickness: float, rail_count: int, level_index: int) -> float:
        top_center_offset = max(rail_thickness * 0.5, height - (rail_thickness * 0.5))
        if rail_count == 1:
            return top_center_offset
        return top_center_offset * float(level_index + 1) / float(rail_count)

    def _create_flight_rails_horizontal(
        self,
        context,
        *,
        run_start: float,
        run_end: float,
        y0: float,
        y1: float,
        start_base_z: float,
        end_base_z: float,
        stair_index: int,
        suffix: str,
    ) -> list[bpy.types.Object]:
        return self._create_flight_rails(
            context,
            axis="x",
            run_start=run_start,
            run_end=run_end,
            side_a=y0,
            side_b=y1,
            start_base_z=start_base_z,
            end_base_z=end_base_z,
            stair_index=stair_index,
            suffix=suffix,
        )

    def _create_flight_rails_vertical(
        self,
        context,
        *,
        run_start: float,
        run_end: float,
        x0: float,
        x1: float,
        start_base_z: float,
        end_base_z: float,
        stair_index: int,
        suffix: str,
    ) -> list[bpy.types.Object]:
        return self._create_flight_rails(
            context,
            axis="y",
            run_start=run_start,
            run_end=run_end,
            side_a=x0,
            side_b=x1,
            start_base_z=start_base_z,
            end_base_z=end_base_z,
            stair_index=stair_index,
            suffix=suffix,
        )

    def _create_flight_rails(
        self,
        context,
        *,
        axis: str,
        run_start: float,
        run_end: float,
        side_a: float,
        side_b: float,
        start_base_z: float,
        end_base_z: float,
        stair_index: int,
        suffix: str,
    ) -> list[bpy.types.Object]:
        height = float(context.settings.roof_railing.height)
        post_size = float(context.settings.roof_railing.post_size)
        rail_thickness = float(context.settings.roof_railing.rail_thickness)
        rail_count = max(1, int(context.settings.roof_railing.rail_count))
        rail_tile_id = atlas.resolve_railing_tile_id(context)
        objects: list[bpy.types.Object] = []
        side_positions = (side_a, side_b)
        side_labels = ("A", "B")

        for side_value, side_label in zip(side_positions, side_labels):
            start_suffix = f"{suffix}_{side_label}_P0"
            end_suffix = f"{suffix}_{side_label}_P1"
            if axis == "x":
                objects.append(
                    self._create_edge_post(
                        context,
                        run_start,
                        side_value,
                        height,
                        post_size,
                        stair_index,
                        start_suffix,
                        rail_tile_id,
                        base_z=start_base_z,
                    )
                )
                objects.append(
                    self._create_edge_post(
                        context,
                        run_end,
                        side_value,
                        height,
                        post_size,
                        stair_index,
                        end_suffix,
                        rail_tile_id,
                        base_z=end_base_z,
                    )
                )
            else:
                objects.append(
                    self._create_edge_post(
                        context,
                        side_value,
                        run_start,
                        height,
                        post_size,
                        stair_index,
                        start_suffix,
                        rail_tile_id,
                        base_z=start_base_z,
                    )
                )
                objects.append(
                    self._create_edge_post(
                        context,
                        side_value,
                        run_end,
                        height,
                        post_size,
                        stair_index,
                        end_suffix,
                        rail_tile_id,
                        base_z=end_base_z,
                    )
                )

            for level_index in range(rail_count):
                z_offset = self._rail_z(height, rail_thickness, rail_count, level_index)
                if axis == "x":
                    rail_start = (run_start, side_value, start_base_z + z_offset)
                    rail_end = (run_end, side_value, end_base_z + z_offset)
                else:
                    rail_start = (side_value, run_start, start_base_z + z_offset)
                    rail_end = (side_value, run_end, end_base_z + z_offset)
                objects.append(
                    self._create_sloped_rail(
                        context,
                        start=rail_start,
                        end=rail_end,
                        thickness=rail_thickness,
                        stair_index=stair_index,
                        suffix=f"{suffix}_{side_label}_R{level_index + 1}",
                        rail_tile_id=rail_tile_id,
            )
        )

        return objects

    def _create_mid_landing_rail_segment(
        self,
        context,
        *,
        axis: str,
        fixed_coord: float,
        segment_start: float,
        segment_end: float,
        base_z: float,
        stair_index: int,
        suffix: str,
    ) -> list[bpy.types.Object]:
        height = float(context.settings.roof_railing.height)
        post_size = float(context.settings.roof_railing.post_size)
        rail_thickness = float(context.settings.roof_railing.rail_thickness)
        rail_count = max(1, int(context.settings.roof_railing.rail_count))
        rail_tile_id = atlas.resolve_railing_tile_id(context)
        segment_length = segment_end - segment_start
        min_segment_length = max(post_size * 2.0, 0.04)
        if segment_length < min_segment_length:
            return []

        objects: list[bpy.types.Object] = []
        if axis == "x":
            objects.append(
                self._create_edge_post(
                    context,
                    segment_start,
                    fixed_coord,
                    height,
                    post_size,
                    stair_index,
                    f"{suffix}_P0",
                    rail_tile_id,
                    base_z=base_z,
                )
            )
            objects.append(
                self._create_edge_post(
                    context,
                    segment_end,
                    fixed_coord,
                    height,
                    post_size,
                    stair_index,
                    f"{suffix}_P1",
                    rail_tile_id,
                    base_z=base_z,
                )
            )
            for level_index in range(rail_count):
                objects.append(
                    self._create_edge_rail(
                        context,
                        center=(
                            (segment_start + segment_end) * 0.5,
                            fixed_coord,
                            base_z + self._rail_z(height, rail_thickness, rail_count, level_index),
                        ),
                        size=(segment_length, rail_thickness, rail_thickness),
                        stair_index=stair_index,
                        suffix=f"{suffix}_R{level_index + 1}",
                        rail_tile_id=rail_tile_id,
                    )
                )
        else:
            objects.append(
                self._create_edge_post(
                    context,
                    fixed_coord,
                    segment_start,
                    height,
                    post_size,
                    stair_index,
                    f"{suffix}_P0",
                    rail_tile_id,
                    base_z=base_z,
                )
            )
            objects.append(
                self._create_edge_post(
                    context,
                    fixed_coord,
                    segment_end,
                    height,
                    post_size,
                    stair_index,
                    f"{suffix}_P1",
                    rail_tile_id,
                    base_z=base_z,
                )
            )
            for level_index in range(rail_count):
                objects.append(
                    self._create_edge_rail(
                        context,
                        center=(
                            fixed_coord,
                            (segment_start + segment_end) * 0.5,
                            base_z + self._rail_z(height, rail_thickness, rail_count, level_index),
                        ),
                        size=(rail_thickness, segment_length, rail_thickness),
                        stair_index=stair_index,
                        suffix=f"{suffix}_R{level_index + 1}",
                        rail_tile_id=rail_tile_id,
                    )
                )
        return objects

    def _subtract_blocked_intervals(
        self,
        span_start: float,
        span_end: float,
        blocked_intervals: list[tuple[float, float]],
        *,
        min_segment_length: float,
    ) -> list[tuple[float, float]]:
        clamped_blocks: list[tuple[float, float]] = []
        for block_start, block_end in blocked_intervals:
            start = max(span_start, min(block_start, block_end))
            end = min(span_end, max(block_start, block_end))
            if end > start:
                clamped_blocks.append((start, end))

        if not clamped_blocks:
            return [(span_start, span_end)] if (span_end - span_start) >= min_segment_length else []

        clamped_blocks.sort(key=lambda item: item[0])
        merged_blocks: list[list[float]] = []
        for start, end in clamped_blocks:
            if not merged_blocks or start > merged_blocks[-1][1]:
                merged_blocks.append([start, end])
            else:
                merged_blocks[-1][1] = max(merged_blocks[-1][1], end)

        segments: list[tuple[float, float]] = []
        cursor = span_start
        for start, end in merged_blocks:
            if (start - cursor) >= min_segment_length:
                segments.append((cursor, start))
            cursor = max(cursor, end)
        if (span_end - cursor) >= min_segment_length:
            segments.append((cursor, span_end))
        return segments

    def _create_mid_landing_rails_horizontal(
        self,
        context,
        *,
        x0: float,
        mid_landing_end: float,
        y0: float,
        y1: float,
        lane_bottom_y0: float,
        lane_bottom_y1: float,
        lane_top_y0: float,
        lane_top_y1: float,
        lower_total_rise: float,
        stair_index: int,
    ) -> list[bpy.types.Object]:
        post_size = float(context.settings.roof_railing.post_size)
        min_segment_length = max(post_size * 2.0, 0.04)
        base_z = lower_total_rise + self.LANDING_THICKNESS
        objects: list[bpy.types.Object] = []

        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="y",
                fixed_coord=x0,
                segment_start=y0,
                segment_end=y1,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Left",
            )
        )
        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="x",
                fixed_coord=y0,
                segment_start=x0,
                segment_end=mid_landing_end,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Bottom",
            )
        )
        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="x",
                fixed_coord=y1,
                segment_start=x0,
                segment_end=mid_landing_end,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Top",
            )
        )

        right_side_segments = self._subtract_blocked_intervals(
            y0,
            y1,
            [(lane_bottom_y0, lane_bottom_y1), (lane_top_y0, lane_top_y1)],
            min_segment_length=min_segment_length,
        )
        for segment_index, (segment_start, segment_end) in enumerate(right_side_segments, start=1):
            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="y",
                    fixed_coord=mid_landing_end,
                    segment_start=segment_start,
                    segment_end=segment_end,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix=f"MidLanding_Right_{segment_index}",
                )
            )
        return objects

    def _create_mid_landing_rails_vertical(
        self,
        context,
        *,
        x0: float,
        x1: float,
        y0: float,
        mid_landing_end: float,
        lane_left_x0: float,
        lane_left_x1: float,
        lane_right_x0: float,
        lane_right_x1: float,
        lower_total_rise: float,
        stair_index: int,
    ) -> list[bpy.types.Object]:
        post_size = float(context.settings.roof_railing.post_size)
        min_segment_length = max(post_size * 2.0, 0.04)
        base_z = lower_total_rise + self.LANDING_THICKNESS
        objects: list[bpy.types.Object] = []

        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="x",
                fixed_coord=y0,
                segment_start=x0,
                segment_end=x1,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Bottom",
            )
        )
        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="y",
                fixed_coord=x0,
                segment_start=y0,
                segment_end=mid_landing_end,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Left",
            )
        )
        objects.extend(
            self._create_mid_landing_rail_segment(
                context,
                axis="y",
                fixed_coord=x1,
                segment_start=y0,
                segment_end=mid_landing_end,
                base_z=base_z,
                stair_index=stair_index,
                suffix="MidLanding_Right",
            )
        )

        top_side_segments = self._subtract_blocked_intervals(
            x0,
            x1,
            [(lane_left_x0, lane_left_x1), (lane_right_x0, lane_right_x1)],
            min_segment_length=min_segment_length,
        )
        for segment_index, (segment_start, segment_end) in enumerate(top_side_segments, start=1):
            objects.extend(
                self._create_mid_landing_rail_segment(
                    context,
                    axis="x",
                    fixed_coord=mid_landing_end,
                    segment_start=segment_start,
                    segment_end=segment_end,
                    base_z=base_z,
                    stair_index=stair_index,
                    suffix=f"MidLanding_Top_{segment_index}",
                )
            )
        return objects

    def _create_sloped_rail(
        self,
        context,
        *,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        thickness: float,
        stair_index: int,
        suffix: str,
        rail_tile_id: str,
    ) -> bpy.types.Object:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        length = max(math.sqrt((dx * dx) + (dy * dy) + (dz * dz)), 0.04)
        mesh = bpy.data.meshes.new(f"ExternalStairRailMesh_{stair_index:03d}_{suffix}")
        build_box_mesh(mesh, size_x=length, size_y=max(thickness, 0.04), size_z=max(thickness, 0.04))
        obj = bpy.data.objects.new(f"ExternalStairRail_{stair_index:03d}_{suffix}", mesh)
        obj.location = (
            (start[0] + end[0]) * 0.5,
            (start[1] + end[1]) * 0.5,
            (start[2] + end[2]) * 0.5,
        )
        yaw = math.atan2(dy, dx)
        horizontal = math.sqrt((dx * dx) + (dy * dy))
        pitch = math.atan2(dz, horizontal)
        obj.rotation_euler = (0.0, -pitch, yaw)
        tag_generated_object(obj, "stair", tile_x=int(obj.location.x), tile_y=int(obj.location.y))
        self._tag_external_stair_object(obj, context, stair_part="rail")
        obj["atlas_category"] = "railings"
        if rail_tile_id:
            obj["atlas_tile_id"] = rail_tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _create_lightweight_stair(self, context, placement: ExternalStairPlacement, *, stair_index: int, stair_tile_id: str, landing_tile_id: str) -> list[bpy.types.Object]:
        switchback = placement.switchback_placement
        if switchback is None:
            return []
        if switchback.orientation == "x":
            return self._create_lightweight_horizontal(context, placement, switchback, stair_index=stair_index, stair_tile_id=stair_tile_id, landing_tile_id=landing_tile_id)
        return self._create_lightweight_vertical(context, placement, switchback, stair_index=stair_index, stair_tile_id=stair_tile_id, landing_tile_id=landing_tile_id)

    def _create_lightweight_horizontal(self, context, placement: ExternalStairPlacement, switchback, *, stair_index: int, stair_tile_id: str, landing_tile_id: str) -> list[bpy.types.Object]:
        objects: list[bpy.types.Object] = []
        x0 = float(switchback.x)
        y0 = float(switchback.y)
        x1 = x0 + float(switchback.length)
        y1 = y0 + float(switchback.width)
        lane = min(float(switchback.stair_width), max(0.6, (y1 - y0) * 0.45))
        lane_bottom_y0 = y0
        lane_bottom_y1 = y0 + lane
        lane_top_y1 = y1
        lane_top_y0 = y1 - lane
        mid_landing_end = x0 + float(switchback.mid_landing_size)
        run_start = mid_landing_end
        run_end = x1
        lower_run = max(0.5, run_end - run_start)
        upper_run = max(0.5, run_end - run_start)
        tread_a = lower_run / max(switchback.lower_riser_count, 1)
        tread_b = upper_run / max(switchback.upper_riser_count, 1)
        lower_total_rise = switchback.lower_riser_count * float(switchback.riser_height)
        top_elevation = float(switchback.top_elevation or context.settings.walls.wall_height)

        for step_index in range(switchback.lower_riser_count):
            sx1 = run_end - (tread_a * step_index)
            sx0 = sx1 - tread_a
            step_height = (step_index + 1) * float(switchback.riser_height)
            objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_TreadA_{step_index + 1:02d}", ((sx0 + sx1) * 0.5, (lane_bottom_y0 + lane_bottom_y1) * 0.5, step_height), (sx1 - sx0, lane_bottom_y1 - lane_bottom_y0, self.TREAD_THICKNESS), stair_tile_id, "tread"))

        objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_MidLanding", ((x0 + mid_landing_end) * 0.5, (y0 + y1) * 0.5, lower_total_rise + (self.LANDING_THICKNESS * 0.5)), (mid_landing_end - x0, y1 - y0, self.LANDING_THICKNESS), landing_tile_id, "mid_landing"))
        objects.extend(
            self._create_mid_landing_rails_horizontal(
                context,
                x0=x0,
                mid_landing_end=mid_landing_end,
                y0=y0,
                y1=y1,
                lane_bottom_y0=lane_bottom_y0,
                lane_bottom_y1=lane_bottom_y1,
                lane_top_y0=lane_top_y0,
                lane_top_y1=lane_top_y1,
                lower_total_rise=lower_total_rise,
                stair_index=stair_index,
            )
        )

        for step_index in range(switchback.upper_riser_count):
            sx0 = run_start + (tread_b * step_index)
            sx1 = sx0 + tread_b
            step_height = lower_total_rise + ((step_index + 1) * float(switchback.riser_height))
            objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_TreadB_{step_index + 1:02d}", ((sx0 + sx1) * 0.5, (lane_top_y0 + lane_top_y1) * 0.5, step_height), (sx1 - sx0, lane_top_y1 - lane_top_y0, self.TREAD_THICKNESS), stair_tile_id, "tread"))

        objects.extend(
            [
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerA", (run_end, lane_bottom_y0 + (lane * 0.18), self.TREAD_THICKNESS * 0.5), (run_start, lane_bottom_y0 + (lane * 0.18), lower_total_rise - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerB", (run_end, lane_bottom_y1 - (lane * 0.18), self.TREAD_THICKNESS * 0.5), (run_start, lane_bottom_y1 - (lane * 0.18), lower_total_rise - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerC", (run_start, lane_top_y0 + (lane * 0.18), lower_total_rise + (self.TREAD_THICKNESS * 0.5)), (run_end, lane_top_y0 + (lane * 0.18), top_elevation - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerD", (run_start, lane_top_y1 - (lane * 0.18), lower_total_rise + (self.TREAD_THICKNESS * 0.5)), (run_end, lane_top_y1 - (lane * 0.18), top_elevation - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
            ]
        )
        objects.extend(
            self._create_flight_rails_horizontal(
                context,
                run_start=run_end,
                run_end=run_start,
                y0=lane_bottom_y0,
                y1=lane_bottom_y1,
                start_base_z=self.TREAD_THICKNESS * 0.5,
                end_base_z=lower_total_rise - (self.TREAD_THICKNESS * 0.5),
                stair_index=stair_index,
                suffix="LowerFlight",
            )
        )
        objects.extend(
            self._create_flight_rails_horizontal(
                context,
                run_start=run_start,
                run_end=run_end,
                y0=lane_top_y0,
                y1=lane_top_y1,
                start_base_z=lower_total_rise + (self.TREAD_THICKNESS * 0.5),
                end_base_z=top_elevation - (self.TREAD_THICKNESS * 0.5),
                stair_index=stair_index,
                suffix="UpperFlight",
            )
        )
        return objects

    def _create_lightweight_vertical(self, context, placement: ExternalStairPlacement, switchback, *, stair_index: int, stair_tile_id: str, landing_tile_id: str) -> list[bpy.types.Object]:
        objects: list[bpy.types.Object] = []
        x0 = float(switchback.x)
        y0 = float(switchback.y)
        x1 = x0 + float(switchback.width)
        y1 = y0 + float(switchback.length)
        lane = min(float(switchback.stair_width), max(0.6, (x1 - x0) * 0.45))
        lane_left_x0 = x0
        lane_left_x1 = x0 + lane
        lane_right_x1 = x1
        lane_right_x0 = x1 - lane
        mid_landing_end = y0 + float(switchback.mid_landing_size)
        run_start = mid_landing_end
        run_end = y1
        lower_run = max(0.5, run_end - run_start)
        upper_run = max(0.5, run_end - run_start)
        tread_a = lower_run / max(switchback.lower_riser_count, 1)
        tread_b = upper_run / max(switchback.upper_riser_count, 1)
        lower_total_rise = switchback.lower_riser_count * float(switchback.riser_height)
        top_elevation = float(switchback.top_elevation or context.settings.walls.wall_height)

        for step_index in range(switchback.lower_riser_count):
            sy1 = run_end - (tread_a * step_index)
            sy0 = sy1 - tread_a
            step_height = (step_index + 1) * float(switchback.riser_height)
            objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_TreadA_{step_index + 1:02d}", ((lane_left_x0 + lane_left_x1) * 0.5, (sy0 + sy1) * 0.5, step_height), (lane_left_x1 - lane_left_x0, sy1 - sy0, self.TREAD_THICKNESS), stair_tile_id, "tread"))

        objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_MidLanding", ((x0 + x1) * 0.5, (y0 + mid_landing_end) * 0.5, lower_total_rise + (self.LANDING_THICKNESS * 0.5)), (x1 - x0, mid_landing_end - y0, self.LANDING_THICKNESS), landing_tile_id, "mid_landing"))
        objects.extend(
            self._create_mid_landing_rails_vertical(
                context,
                x0=x0,
                x1=x1,
                y0=y0,
                mid_landing_end=mid_landing_end,
                lane_left_x0=lane_left_x0,
                lane_left_x1=lane_left_x1,
                lane_right_x0=lane_right_x0,
                lane_right_x1=lane_right_x1,
                lower_total_rise=lower_total_rise,
                stair_index=stair_index,
            )
        )

        for step_index in range(switchback.upper_riser_count):
            sy0 = run_start + (tread_b * step_index)
            sy1 = sy0 + tread_b
            step_height = lower_total_rise + ((step_index + 1) * float(switchback.riser_height))
            objects.append(self._create_stair_piece(context, f"ExtStair_{stair_index:03d}_TreadB_{step_index + 1:02d}", ((lane_right_x0 + lane_right_x1) * 0.5, (sy0 + sy1) * 0.5, step_height), (lane_right_x1 - lane_right_x0, sy1 - sy0, self.TREAD_THICKNESS), stair_tile_id, "tread"))

        objects.extend(
            [
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerA", (lane_left_x0 + (lane * 0.18), run_end, self.TREAD_THICKNESS * 0.5), (lane_left_x0 + (lane * 0.18), run_start, lower_total_rise - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerB", (lane_left_x1 - (lane * 0.18), run_end, self.TREAD_THICKNESS * 0.5), (lane_left_x1 - (lane * 0.18), run_start, lower_total_rise - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerC", (lane_right_x0 + (lane * 0.18), run_start, lower_total_rise + (self.TREAD_THICKNESS * 0.5)), (lane_right_x0 + (lane * 0.18), run_end, top_elevation - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
                self._create_sloped_stringer(context, f"ExtStair_{stair_index:03d}_StringerD", (lane_right_x1 - (lane * 0.18), run_start, lower_total_rise + (self.TREAD_THICKNESS * 0.5)), (lane_right_x1 - (lane * 0.18), run_end, top_elevation - (self.TREAD_THICKNESS * 0.5)), stair_tile_id),
            ]
        )
        objects.extend(
            self._create_flight_rails_vertical(
                context,
                run_start=run_end,
                run_end=run_start,
                x0=lane_left_x0,
                x1=lane_left_x1,
                start_base_z=self.TREAD_THICKNESS * 0.5,
                end_base_z=lower_total_rise - (self.TREAD_THICKNESS * 0.5),
                stair_index=stair_index,
                suffix="LowerFlight",
            )
        )
        objects.extend(
            self._create_flight_rails_vertical(
                context,
                run_start=run_start,
                run_end=run_end,
                x0=lane_right_x0,
                x1=lane_right_x1,
                start_base_z=lower_total_rise + (self.TREAD_THICKNESS * 0.5),
                end_base_z=top_elevation - (self.TREAD_THICKNESS * 0.5),
                stair_index=stair_index,
                suffix="UpperFlight",
            )
        )
        return objects

    def _create_stair_piece(self, context, name: str, center: tuple[float, float, float], size: tuple[float, float, float], tile_id: str, stair_part: str) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        build_box_mesh(mesh, size_x=max(size[0], 0.04), size_y=max(size[1], 0.04), size_z=max(size[2], 0.04))
        obj = bpy.data.objects.new(name, mesh)
        obj.location = center
        tag_generated_object(obj, "stair", tile_x=int(center[0]), tile_y=int(center[1]))
        landing_story = self._external_story_span(context)[0] if "landing" in stair_part else None
        self._tag_external_stair_object(obj, context, stair_part=stair_part, landing_story=landing_story)
        obj["atlas_category"] = "stairs" if stair_part == "tread" or stair_part == "stringer" else "stair_landings"
        if tile_id:
            obj["atlas_tile_id"] = tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

    def _create_sloped_stringer(
        self,
        context,
        name: str,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        tile_id: str,
    ) -> bpy.types.Object:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        length = max(math.sqrt((dx * dx) + (dy * dy) + (dz * dz)), 0.04)
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        build_box_mesh(mesh, size_x=length, size_y=self.STRINGER_THICKNESS, size_z=self.STRINGER_THICKNESS)
        obj = bpy.data.objects.new(name, mesh)
        obj.location = (
            (start[0] + end[0]) * 0.5,
            (start[1] + end[1]) * 0.5,
            (start[2] + end[2]) * 0.5,
        )
        yaw = math.atan2(dy, dx)
        horizontal = math.sqrt((dx * dx) + (dy * dy))
        pitch = math.atan2(dz, horizontal)
        obj.rotation_euler = (0.0, -pitch, yaw)
        tag_generated_object(obj, "stair", tile_x=int(obj.location.x), tile_y=int(obj.location.y))
        self._tag_external_stair_object(obj, context, stair_part="stringer")
        obj["atlas_category"] = "stairs"
        if tile_id:
            obj["atlas_tile_id"] = tile_id
        apply_story_object_context(obj, context)
        link_object(context.collection, obj)
        return obj

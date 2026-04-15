from __future__ import annotations

import math

from ..common.utils import quantize_025
from ..domain.doors import DoorPlacement
from ..domain.stairs import (
    ExternalStairFacadePlan,
    ExternalStairPlacement,
    ExternalStairStackPlan,
    ExternalStairStoryAccessPlan,
    StairMode,
    StairOpeningPlan,
    StairPlacement,
)
from .outer_boundary_resolver import OuterBoundaryResolver


class ExternalStairPlanner:
    """Plans a compact facade stair stack, reserved access doors, and later build placements."""

    def __init__(self):
        self.boundary_resolver = OuterBoundaryResolver()

    def plan_stack(self, building_plan, settings) -> ExternalStairStackPlan | None:
        if settings.stairs.mode != StairMode.EXTERNAL or building_plan.story_count <= 1:
            return None

        flight_length, door_landing_length, module_width = self._module_dimensions(
            story_height=float(building_plan.story_height),
            stair_settings=settings.stairs,
            door_width=float(settings.doors.entry_width),
        )
        module_length = quantize_025(flight_length + door_landing_length)
        facade = self._choose_facade(building_plan.footprint.tiles, settings, module_length=module_length, module_width=module_width)
        if facade is None:
            return None

        run_center = (facade.start + facade.end) * 0.5
        stack_start = quantize_025(run_center - (module_length * 0.5))
        stack_end = quantize_025(stack_start + module_length)
        if stack_start < facade.landing_start:
            stack_start = facade.landing_start
            stack_end = quantize_025(stack_start + module_length)
        if stack_end > facade.landing_end:
            stack_end = facade.landing_end
            stack_start = quantize_025(stack_end - module_length)
        door_width = float(settings.doors.entry_width)
        landing_start = quantize_025(stack_end - door_landing_length)
        landing_end = stack_end
        door_center = quantize_025((landing_start + landing_end) * 0.5)
        slot_start = quantize_025(door_center - (door_width * 0.5))
        slot_end = quantize_025(slot_start + door_width)
        if slot_start < landing_start:
            slot_start = landing_start
            slot_end = quantize_025(slot_start + door_width)
        if slot_end > landing_end:
            slot_end = landing_end
            slot_start = quantize_025(slot_end - door_width)
        door_center = quantize_025((slot_start + slot_end) * 0.5)
        forbidden_start = quantize_025(stack_start - settings.windows.min_door_offset)
        forbidden_end = quantize_025(stack_end + settings.windows.min_door_offset)

        accesses = tuple(
            ExternalStairStoryAccessPlan(
                story_index=story_index,
                door_type="entry" if story_index == 0 else "external_stair",
                slot_start=slot_start,
                slot_end=slot_end,
                center=door_center,
                has_upward_flight=story_index < (building_plan.story_count - 1),
                anchor_side="start" if story_index % 2 == 0 else "end" if story_index < (building_plan.story_count - 1) else None,
            )
            for story_index in range(building_plan.story_count)
        )

        return ExternalStairStackPlan(
            facade=facade,
            stack_start=stack_start,
            stack_end=stack_end,
            flight_length=flight_length,
            door_landing_length=door_landing_length,
            forbidden_start=forbidden_start,
            forbidden_end=forbidden_end,
            story_accesses=accesses,
        )

    def plan_building(self, building_context) -> list[ExternalStairPlacement]:
        stack = getattr(building_context.building_plan, "external_stair_stack", None)
        if stack is None or building_context.settings.stairs.mode != StairMode.EXTERNAL:
            return []

        placements: list[ExternalStairPlacement] = []
        for story_context in building_context.stories:
            access = stack.story_accesses[story_context.story_plan.story_index]
            door = self._resolve_story_door(story_context, stack, access)
            if door is None:
                return []
            switchback = None
            if access.has_upward_flight:
                switchback = self._make_switchback_placement(
                    building_context,
                    stack,
                    access,
                )
            placements.append(
                ExternalStairPlacement(
                    story_index=access.story_index,
                    has_upward_flight=access.has_upward_flight,
                    facade=stack.facade,
                    door=door,
                    door_landing_bounds=self._door_landing_bounds(stack),
                    door_access_bounds=self._door_access_bounds(stack, access, building_context.settings.stairs.door_clearance),
                    flight_bounds=self._flight_bounds(stack),
                    switchback_placement=switchback,
                    anchor_side=access.anchor_side,
                )
            )
        return placements

    def reserved_door_for_story(self, context) -> DoorPlacement | None:
        building_plan = getattr(context, "building_plan", None)
        stack = getattr(building_plan, "external_stair_stack", None)
        story_plan = getattr(context, "story_plan", None)
        if story_plan is None or context.settings.stairs.mode != StairMode.EXTERNAL:
            return None
        if stack is None:
            return self._reserve_ground_entry_without_stack(context)
        access = stack.story_accesses[story_plan.story_index]
        return self._door_from_access(access, stack.facade, context)

    def reuse_ground_entry(self, context, placements: list[DoorPlacement]) -> DoorPlacement | None:
        building_plan = getattr(context, "building_plan", None)
        stack = getattr(building_plan, "external_stair_stack", None)
        story_plan = getattr(context, "story_plan", None)
        if stack is None or story_plan is None or story_plan.story_index != 0:
            return None
        for placement in placements:
            if placement.door_type != "entry":
                continue
            if placement.orientation != stack.facade.orientation or placement.host_wall_side != stack.facade.side:
                continue
            if abs(placement.line - stack.facade.line) > 1e-6:
                continue
            if placement.slot_end > stack.stack_start + 1e-6 and placement.slot_start < stack.stack_end - 1e-6:
                return placement
        return None

    def _reserve_ground_entry_without_stack(self, context) -> DoorPlacement | None:
        building_plan = getattr(context, "building_plan", None)
        story_plan = getattr(context, "story_plan", None)
        if building_plan is None or story_plan is None:
            return None
        if building_plan.story_count != 1 or story_plan.story_index != 0:
            return None

        door_width = float(context.settings.doors.entry_width)
        _, door_landing_length, module_width = self._module_dimensions(
            story_height=float(building_plan.story_height),
            stair_settings=context.settings.stairs,
            door_width=door_width,
        )
        facade = self._choose_facade(
            building_plan.footprint.tiles,
            context.settings,
            module_length=door_landing_length,
            module_width=module_width,
        )
        if facade is None:
            return None

        run_center = (facade.start + facade.end) * 0.5
        stack_start = quantize_025(run_center - (door_landing_length * 0.5))
        stack_end = quantize_025(stack_start + door_landing_length)
        if stack_start < facade.landing_start:
            stack_start = facade.landing_start
            stack_end = quantize_025(stack_start + door_landing_length)
        if stack_end > facade.landing_end:
            stack_end = facade.landing_end
            stack_start = quantize_025(stack_end - door_landing_length)

        door_center = quantize_025((stack_start + stack_end) * 0.5)
        slot_start = quantize_025(door_center - (door_width * 0.5))
        slot_end = quantize_025(slot_start + door_width)
        if slot_start < stack_start:
            slot_start = stack_start
            slot_end = quantize_025(slot_start + door_width)
        if slot_end > stack_end:
            slot_end = stack_end
            slot_start = quantize_025(slot_end - door_width)
        door_center = quantize_025((slot_start + slot_end) * 0.5)

        access = ExternalStairStoryAccessPlan(
            story_index=0,
            door_type="entry",
            slot_start=slot_start,
            slot_end=slot_end,
            center=door_center,
            has_upward_flight=False,
            anchor_side=None,
        )
        return self._door_from_access(access, facade, context)

    def _module_dimensions(self, *, story_height: float, stair_settings, door_width: float) -> tuple[float, float, float]:
        riser_count = max(12, int(math.ceil(story_height / max(float(stair_settings.riser_height), 0.01))))
        lower_risers = riser_count // 2
        upper_risers = riser_count - lower_risers
        travel_run = max(lower_risers, upper_risers) * float(stair_settings.tread_depth)
        flight_length = quantize_025(float(stair_settings.mid_landing_size) + travel_run)
        door_landing_length = quantize_025(max(door_width + (float(stair_settings.door_clearance) * 2.0), float(stair_settings.width) + 0.5))
        module_width = quantize_025(max(float(stair_settings.width) * 2.0, float(stair_settings.landing_size)))
        return flight_length, door_landing_length, module_width

    def _choose_facade(self, footprint_tiles, settings, *, module_length: float, module_width: float) -> ExternalStairFacadePlan | None:
        runs = self.boundary_resolver.collect_runs(set(footprint_tiles))
        min_margin = max(float(settings.doors.min_corner_offset), float(settings.doors.min_edge_offset))
        wall_clearance = quantize_025(float(settings.walls.wall_thickness) + 0.25)
        landing_depth = module_width
        candidates: list[ExternalStairFacadePlan] = []
        for run in runs:
            usable_length = run.length - (min_margin * 2.0)
            if usable_length + 1e-6 < module_length:
                continue
            candidates.append(
                ExternalStairFacadePlan(
                    orientation=run.orientation,
                    side=run.side,
                    line=float(run.line),
                    start=float(run.start),
                    end=float(run.end),
                    landing_start=quantize_025(run.start + min_margin),
                    landing_end=quantize_025(run.end - min_margin),
                    landing_depth=landing_depth,
                    module_length=module_length,
                    module_width=module_width,
                    wall_clearance=wall_clearance,
                )
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-(item.end - item.start), item.orientation, item.side, item.line, item.start))
        return candidates[0]

    def _door_from_access(self, access: ExternalStairStoryAccessPlan, facade: ExternalStairFacadePlan, context) -> DoorPlacement:
        door_height = float(context.settings.doors.entry_height)
        if access.door_type == "external_stair":
            door_height = float(context.settings.doors.entry_height)
        return DoorPlacement(
            door_type=access.door_type,
            orientation=facade.orientation,
            line=facade.line,
            start=access.slot_start,
            end=access.slot_end,
            center=access.center,
            width=float(access.slot_end - access.slot_start),
            height=door_height,
            thickness=min(float(context.settings.doors.leaf_thickness), float(context.settings.walls.wall_thickness)),
            host_wall_side=facade.side,
            slot_start=access.slot_start,
            slot_end=access.slot_end,
        )

    def _resolve_story_door(self, context, stack: ExternalStairStackPlan, access: ExternalStairStoryAccessPlan) -> DoorPlacement | None:
        for placement in context.door_placements:
            if placement.door_type != access.door_type:
                continue
            if placement.orientation != stack.facade.orientation or placement.host_wall_side != stack.facade.side:
                continue
            if abs(placement.line - stack.facade.line) > 1e-6:
                continue
            if abs(placement.slot_start - access.slot_start) <= 1e-6 and abs(placement.slot_end - access.slot_end) <= 1e-6:
                return placement
        return None

    def candidate_tile_slots(self, start: float, end: float, min_margin: float, width: float) -> list[float]:
        lower_bound = start + min_margin
        upper_bound = end - min_margin
        candidates: list[float] = []
        for value in range(int(start), int(end)):
            candidate_start = float(value)
            candidate_end = candidate_start + width
            if candidate_start + 1e-6 < start or candidate_end - 1e-6 > end:
                continue
            if candidate_start + 1e-6 < lower_bound:
                continue
            if candidate_end - 1e-6 > upper_bound:
                continue
            candidates.append(quantize_025(candidate_start))
        return candidates

    def _door_landing_bounds(self, stack: ExternalStairStackPlan) -> tuple[float, float, float, float]:
        facade = stack.facade
        if facade.orientation == "x":
            x0 = quantize_025(stack.stack_end - stack.door_landing_length)
            x1 = stack.stack_end
            if facade.side == "north":
                y0 = facade.line + facade.wall_clearance
                y1 = y0 + facade.landing_depth
            else:
                y1 = facade.line - facade.wall_clearance
                y0 = y1 - facade.landing_depth
            return round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)

        y0 = quantize_025(stack.stack_end - stack.door_landing_length)
        y1 = stack.stack_end
        if facade.side == "east":
            x0 = facade.line + facade.wall_clearance
            x1 = x0 + facade.landing_depth
        else:
            x1 = facade.line - facade.wall_clearance
            x0 = x1 - facade.landing_depth
        return round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)

    def _flight_bounds(self, stack: ExternalStairStackPlan) -> tuple[float, float, float, float]:
        facade = stack.facade
        if facade.orientation == "x":
            x0 = stack.stack_start
            x1 = quantize_025(stack.stack_start + stack.flight_length)
            if facade.side == "north":
                y0 = facade.line + facade.wall_clearance
                y1 = y0 + facade.landing_depth
            else:
                y1 = facade.line - facade.wall_clearance
                y0 = y1 - facade.landing_depth
            return round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)

        y0 = stack.stack_start
        y1 = quantize_025(stack.stack_start + stack.flight_length)
        if facade.side == "east":
            x0 = facade.line + facade.wall_clearance
            x1 = x0 + facade.landing_depth
        else:
            x1 = facade.line - facade.wall_clearance
            x0 = x1 - facade.landing_depth
        return round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)

    def _door_access_bounds(
        self,
        stack: ExternalStairStackPlan,
        access: ExternalStairStoryAccessPlan,
        clearance: float,
    ) -> tuple[float, float, float, float]:
        landing = self._door_landing_bounds(stack)
        along_start = quantize_025(max(access.slot_start - float(clearance), stack.stack_end - stack.door_landing_length))
        along_end = quantize_025(min(access.slot_end + float(clearance), stack.stack_end))
        if stack.facade.orientation == "x":
            return round(along_start, 6), round(landing[1], 6), round(along_end, 6), round(landing[3], 6)
        return round(landing[0], 6), round(along_start, 6), round(landing[2], 6), round(along_end, 6)

    def _make_switchback_placement(self, building_context, stack: ExternalStairStackPlan, access: ExternalStairStoryAccessPlan) -> StairPlacement:
        story_height = float(building_context.building_plan.story_height)
        stair_settings = building_context.settings.stairs
        riser_count = max(12, int(math.ceil(story_height / max(float(stair_settings.riser_height), 0.01))))
        lower_risers = riser_count // 2
        upper_risers = riser_count - lower_risers
        actual_riser_height = story_height / float(riser_count)
        travel_run = max(lower_risers, upper_risers) * float(stair_settings.tread_depth)
        flight_bounds = self._flight_bounds(stack)
        module_length = stack.flight_length
        module_width = stack.facade.module_width

        if stack.facade.orientation == "x":
            origin_x = flight_bounds[0]
            origin_y = flight_bounds[1]
            orientation = "x"
        else:
            origin_x = flight_bounds[0]
            origin_y = flight_bounds[1]
            orientation = "y"

        return StairPlacement(
            from_story=access.story_index,
            to_story=access.story_index + 1,
            room_id=0,
            orientation=orientation,
            x=round(origin_x, 6),
            y=round(origin_y, 6),
            width=module_width,
            length=module_length,
            stair_width=float(stair_settings.width),
            landing_size=stack.door_landing_length,
            mid_landing_size=float(stair_settings.mid_landing_size),
            riser_height=actual_riser_height,
            tread_depth=float(stair_settings.tread_depth),
            riser_count=riser_count,
            lower_riser_count=lower_risers,
            upper_riser_count=upper_risers,
            travel_run=travel_run,
            occupied_tiles=frozenset(),
            clearance_tiles=frozenset(),
            opening=StairOpeningPlan(from_story=access.story_index, to_story=access.story_index + 1, tiles=frozenset(), bounds=(0.0, 0.0, 0.0, 0.0)),
            room_score=0.0,
            candidate_score=0.0,
            top_elevation=story_height,
            stair_kind="external",
        )

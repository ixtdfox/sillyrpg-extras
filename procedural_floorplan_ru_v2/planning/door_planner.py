from __future__ import annotations

from collections import defaultdict

from ..common.utils import quantize_025
from ..domain.doors import DoorPlacement
from ..domain.rooms import RoomBoundaryRun
from ..domain.walls import WallSegment
from .external_stair_planner import ExternalStairPlanner


DOOR_WIDTH_M = 1.0
DOOR_HEIGHT_M = 2.0


class DoorPlanner:
    """Планирует входную и межкомнатные двери по уже рассчитанным границам и сегментам стен."""

    def __init__(self):
        self.external_stair_planner = ExternalStairPlanner()

    def plan(self, context) -> list[DoorPlacement]:
        if not context.settings.doors.enabled:
            return []

        placements: list[DoorPlacement] = []
        story_plan = getattr(context, "story_plan", None)
        story_index = story_plan.story_index if story_plan is not None else 0
        external_reserved = self.external_stair_planner.reserved_door_for_story(context)
        if context.settings.stairs.mode.value == "external":
            if external_reserved is not None:
                placements.append(external_reserved)
        elif story_index == 0:
            entry_door = self._plan_entry_door(
                context.outer_wall_segments,
                context.settings.doors,
                context.settings.walls.wall_thickness,
            )
            if entry_door is not None:
                placements.append(entry_door)

        placements.extend(
            self._plan_interior_doors(
                context.room_boundaries,
                context.rooms,
                context.settings.doors,
                context.settings.walls.wall_thickness,
            )
        )
        return placements

    def _plan_entry_door(self, segments: list[WallSegment], door_settings, wall_thickness: float) -> DoorPlacement | None:
        min_margin = max(door_settings.min_edge_offset, door_settings.min_corner_offset)
        outer_runs = self._merge_outer_segments(segments)
        candidates = [
            (run, slot_start)
            for run in outer_runs
            for slot_start in self._candidate_tile_slots(run[3], run[4], min_margin)
        ]
        if not candidates:
            return None

        (orientation, side, line, run_start, run_end), slot_start = sorted(
            candidates,
            key=lambda item: (
                -(item[0][4] - item[0][3]),
                abs((item[1] + 0.5) - ((item[0][3] + item[0][4]) * 0.5)),
                item[0][1],
                item[0][2],
                item[1],
            ),
        )[0]
        slot_end = quantize_025(slot_start + DOOR_WIDTH_M)
        return DoorPlacement(
            door_type="entry",
            orientation=orientation,
            line=line,
            start=slot_start,
            end=slot_end,
            center=quantize_025(slot_start + (DOOR_WIDTH_M * 0.5)),
            width=DOOR_WIDTH_M,
            height=DOOR_HEIGHT_M,
            thickness=min(door_settings.leaf_thickness, wall_thickness),
            host_wall_side=side,
            slot_start=slot_start,
            slot_end=slot_end,
        )

    def _plan_interior_doors(self, runs: list[RoomBoundaryRun], rooms, door_settings, wall_thickness: float) -> list[DoorPlacement]:
        if len(rooms) <= 1:
            return []

        min_margin = max(door_settings.min_edge_offset, door_settings.min_corner_offset)
        grouped: dict[tuple[int, int], list[RoomBoundaryRun]] = defaultdict(list)
        for run in runs:
            if self._candidate_tile_slots(run.start, run.end, min_margin):
                grouped[(run.room_a_id, run.room_b_id)].append(run)

        if not grouped:
            return []

        room_ids = sorted(room.id for room in rooms)
        parent = {room_id: room_id for room_id in room_ids}

        def find(room_id: int) -> int:
            while parent[room_id] != room_id:
                parent[room_id] = parent[parent[room_id]]
                room_id = parent[room_id]
            return room_id

        def union(room_a: int, room_b: int) -> bool:
            root_a = find(room_a)
            root_b = find(room_b)
            if root_a == root_b:
                return False
            if root_a < root_b:
                parent[root_b] = root_a
            else:
                parent[root_a] = root_b
            return True

        placements: list[DoorPlacement] = []
        edges = sorted(
            grouped.items(),
            key=lambda item: (
                -max(run.length for run in item[1]),
                item[0][0],
                item[0][1],
            ),
        )
        for (room_a_id, room_b_id), candidates in edges:
            if not union(room_a_id, room_b_id):
                continue
            run = sorted(
                candidates,
                key=lambda item: (-item.length, item.orientation, item.line, item.start),
            )[0]
            slot_start = sorted(
                self._candidate_tile_slots(run.start, run.end, min_margin),
                key=lambda value: abs((value + 0.5) - ((run.start + run.end) * 0.5)),
            )[0]
            slot_end = quantize_025(slot_start + DOOR_WIDTH_M)
            placements.append(
                DoorPlacement(
                    door_type="interior",
                    orientation=run.orientation,
                    line=run.line,
                    start=slot_start,
                    end=slot_end,
                    center=quantize_025(slot_start + (DOOR_WIDTH_M * 0.5)),
                    width=DOOR_WIDTH_M,
                    height=DOOR_HEIGHT_M,
                    thickness=min(door_settings.leaf_thickness, wall_thickness),
                    host_wall_side=run.side,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    room_a_id=room_a_id,
                    room_b_id=room_b_id,
                )
            )
        return placements

    def _candidate_tile_slots(self, start: float, end: float, min_margin: float) -> list[float]:
        lower_bound = start + min_margin
        upper_bound = end - min_margin
        candidates: list[float] = []
        for value in range(int(start), int(end)):
            candidate_start = float(value)
            candidate_end = candidate_start + DOOR_WIDTH_M
            if candidate_start + 1e-6 < start or candidate_end - 1e-6 > end:
                continue
            if candidate_start + 1e-6 < lower_bound:
                continue
            if candidate_end - 1e-6 > upper_bound:
                continue
            candidates.append(quantize_025(candidate_start))
        return candidates

    def _merge_outer_segments(self, segments: list[WallSegment]) -> list[tuple[str, str, float, float, float]]:
        grouped: dict[tuple[str, str, float], list[tuple[float, float]]] = defaultdict(list)
        for segment in segments:
            grouped[(segment.orientation, segment.side, segment.line)].append((segment.start, segment.end))

        runs: list[tuple[str, str, float, float, float]] = []
        for (orientation, side, line), spans in grouped.items():
            sorted_spans = sorted(spans)
            if not sorted_spans:
                continue
            current_start, current_end = sorted_spans[0]
            for span_start, span_end in sorted_spans[1:]:
                if abs(span_start - current_end) <= 1e-6:
                    current_end = max(current_end, span_end)
                    continue
                runs.append((orientation, side, line, current_start, current_end))
                current_start, current_end = span_start, span_end
            runs.append((orientation, side, line, current_start, current_end))
        return runs

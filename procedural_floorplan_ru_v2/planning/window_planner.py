from __future__ import annotations

from collections import defaultdict
import math

from ..common.utils import quantize_025
from ..domain.windows import WindowPlacement


class WindowPlanner:
    """Планирует окна на внешних wall runs с учётом запретных зон."""

    def plan(self, context) -> list[WindowPlacement]:
        settings = context.settings.windows
        if not settings.enabled:
            return []
        if context.settings.walls.wall_height <= settings.sill_height + settings.height:
            return []

        runs = self._merge_outer_segments(context.outer_wall_segments)
        exterior_doors = [placement for placement in context.door_placements if placement.door_type in {"entry", "external_stair"}]
        junction_points = self._collect_partition_junctions(runs, context.interior_wall_segments)
        placements: list[WindowPlacement] = []

        for run in runs:
            forbidden = self._build_forbidden_intervals(context, run, exterior_doors, junction_points, settings)
            allowed = self._subtract_intervals(
                [(quantize_025(run[3]), quantize_025(run[4]))],
                forbidden,
            )
            for start, end in allowed:
                placements.extend(
                    self._place_windows_in_interval(
                        run,
                        start,
                        end,
                        settings,
                        rng=getattr(context, "rng", None),
                    )
                )
        return placements

    def _merge_outer_segments(self, segments) -> list[tuple[str, str, float, float, float]]:
        grouped: dict[tuple[str, str, float], list[tuple[float, float]]] = defaultdict(list)
        for segment in segments:
            grouped[(segment.orientation, segment.side, segment.line)].append((segment.start, segment.end))

        runs: list[tuple[str, str, float, float, float]] = []
        for (orientation, side, line), spans in grouped.items():
            current_start = None
            current_end = None
            for span_start, span_end in sorted(spans):
                if current_start is None:
                    current_start, current_end = span_start, span_end
                    continue
                if abs(span_start - current_end) <= 1e-6:
                    current_end = max(current_end, span_end)
                    continue
                runs.append((orientation, side, line, current_start, current_end))
                current_start, current_end = span_start, span_end
            if current_start is not None:
                runs.append((orientation, side, line, current_start, current_end))
        return sorted(runs, key=lambda item: (item[0], item[1], item[2], item[3]))

    def _collect_partition_junctions(self, runs, interior_segments) -> dict[tuple[str, str, float], list[float]]:
        junctions: dict[tuple[str, str, float], list[float]] = defaultdict(list)
        for orientation, side, line, start, end in runs:
            for segment in interior_segments:
                if orientation == segment.orientation:
                    continue
                if orientation == "x":
                    touches = abs(segment.start - line) <= 1e-6 or abs(segment.end - line) <= 1e-6
                    point = segment.line
                else:
                    touches = abs(segment.start - line) <= 1e-6 or abs(segment.end - line) <= 1e-6
                    point = segment.line
                if not touches:
                    continue
                if point < start - 1e-6 or point > end + 1e-6:
                    continue
                junctions[(orientation, side, line)].append(quantize_025(point))
        return junctions

    def _build_forbidden_intervals(self, context, run, exterior_doors, junction_points, settings) -> list[tuple[float, float]]:
        orientation, side, line, start, end = run
        edge_margin = max(settings.min_corner_offset, settings.min_edge_offset)
        forbidden = [
            (quantize_025(start), quantize_025(start + edge_margin)),
            (quantize_025(end - edge_margin), quantize_025(end)),
        ]

        for door in exterior_doors:
            if door.orientation != orientation or door.host_wall_side != side or abs(door.line - line) > 1e-6:
                continue
            forbidden.append(
                (
                    quantize_025(door.start - settings.min_door_offset),
                    quantize_025(door.end + settings.min_door_offset),
                )
            )

        for point in junction_points.get((orientation, side, line), []):
            forbidden.append(
                (
                    quantize_025(point - settings.min_partition_offset),
                    quantize_025(point + settings.min_partition_offset),
                )
            )
        building_plan = getattr(context, "building_plan", None)
        stack = getattr(building_plan, "external_stair_stack", None)
        story_plan = getattr(context, "story_plan", None)
        if stack is not None and story_plan is not None:
            facade = stack.facade
            access = stack.story_accesses[story_plan.story_index]
            if facade.orientation == orientation and facade.side == side and abs(facade.line - line) <= 1e-6:
                forbidden.append(
                    (
                        quantize_025(stack.forbidden_start),
                        quantize_025(stack.forbidden_end),
                    )
                )
                forbidden.append(
                    (
                        quantize_025(access.slot_start - settings.min_door_offset),
                        quantize_025(access.slot_end + settings.min_door_offset),
                    )
                )
        return forbidden

    def _subtract_intervals(self, intervals, forbidden) -> list[tuple[float, float]]:
        result = [(quantize_025(start), quantize_025(end)) for start, end in intervals if end > start + 1e-6]
        for forbid_start, forbid_end in sorted(forbidden):
            next_result: list[tuple[float, float]] = []
            for start, end in result:
                if forbid_end <= start + 1e-6 or forbid_start >= end - 1e-6:
                    next_result.append((start, end))
                    continue
                if forbid_start > start + 1e-6:
                    next_result.append((start, quantize_025(min(forbid_start, end))))
                if forbid_end < end - 1e-6:
                    next_result.append((quantize_025(max(forbid_end, start)), end))
            result = [(a, b) for a, b in next_result if b - a >= 0.25 - 1e-6]
        return result

    def _place_windows_in_interval(self, run, start: float, end: float, settings, *, rng=None) -> list[WindowPlacement]:
        base_width = settings.width
        double_width = quantize_025(settings.width * 2.0)
        interval_length = quantize_025(end - start)
        if interval_length < base_width - 1e-6:
            return []

        orientation, side, line, _, _ = run
        placements: list[WindowPlacement] = []
        last_window_end = None
        cursor = math.ceil(start - 1e-6)
        while cursor + base_width <= end + 1e-6:
            window_start = quantize_025(float(cursor))
            if last_window_end is not None and window_start < last_window_end + settings.min_edge_offset - 1e-6:
                cursor = int(math.ceil((last_window_end + settings.min_edge_offset) - 1e-6))
                continue

            width_options: list[float] = []
            if self._window_fits(window_start, end, double_width):
                width_options.append(double_width)
            if self._window_fits(window_start, end, base_width):
                width_options.append(base_width)
            if not width_options:
                cursor += 1
                continue

            chosen_width = self._choose_window_width(width_options, rng)
            window_end = quantize_025(window_start + chosen_width)
            placements.append(
                WindowPlacement(
                    orientation=orientation,
                    line=line,
                    start=window_start,
                    end=window_end,
                    center=quantize_025((window_start + window_end) * 0.5),
                    width=chosen_width,
                    height=settings.height,
                    sill_height=settings.sill_height,
                    host_wall_side=side,
                )
            )
            last_window_end = window_end
            cursor = int(math.ceil((window_end + settings.min_edge_offset) - 1e-6))
        return placements

    def _window_fits(self, start: float, end: float, width: float) -> bool:
        return start + width <= end + 1e-6

    def _choose_window_width(self, width_options: list[float], rng) -> float:
        if len(width_options) == 1:
            return width_options[0]
        if rng is None:
            return max(width_options)
        if rng.random() < 0.5:
            return max(width_options)
        return min(width_options)

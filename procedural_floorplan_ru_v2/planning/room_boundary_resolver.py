from __future__ import annotations

from ..builders.wall_utils import add_grouped_edge, merge_spans
from ..common.utils import FLOOR_TILE_SIZE_M, quantize_025
from ..domain.rooms import Room, RoomBoundaryRun


class RoomBoundaryResolver:
    """Builds shared boundaries between adjacent rooms without duplicates."""

    def collect_runs(self, rooms: list[Room]) -> list[RoomBoundaryRun]:
        tile_to_room: dict[tuple[int, int], int] = {}
        for room in rooms:
            for tile in room.tiles:
                tile_to_room[tile] = room.id

        grouped_edges: dict[tuple, list[tuple[float, float]]] = {}
        for tile_x, tile_y in sorted(tile_to_room):
            room_id = tile_to_room[(tile_x, tile_y)]
            east_room = tile_to_room.get((tile_x + 1, tile_y))
            if east_room is not None and east_room != room_id:
                room_a_id, room_b_id = sorted((room_id, east_room))
                add_grouped_edge(
                    grouped_edges,
                    ("y", "east", quantize_025(tile_x + FLOOR_TILE_SIZE_M), room_a_id, room_b_id),
                    tile_y,
                    tile_y + FLOOR_TILE_SIZE_M,
                )

            north_room = tile_to_room.get((tile_x, tile_y + 1))
            if north_room is not None and north_room != room_id:
                room_a_id, room_b_id = sorted((room_id, north_room))
                add_grouped_edge(
                    grouped_edges,
                    ("x", "north", quantize_025(tile_y + FLOOR_TILE_SIZE_M), room_a_id, room_b_id),
                    tile_x,
                    tile_x + FLOOR_TILE_SIZE_M,
                )

        runs: list[RoomBoundaryRun] = []
        for (orientation, side, line, room_a_id, room_b_id), spans in grouped_edges.items():
            runs.extend(
                merge_spans(
                    run_factory=RoomBoundaryRun,
                    run_args=(orientation, side, line, room_a_id, room_b_id),
                    spans=spans,
                )
            )
        return sorted(runs, key=lambda run: (run.orientation, run.line, run.start, run.room_a_id, run.room_b_id))

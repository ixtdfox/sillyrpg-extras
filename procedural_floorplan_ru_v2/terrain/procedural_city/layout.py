from __future__ import annotations

# Layout/asset placement logic adapted from local MIT project /home/tony/pets/bpy-city.

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import math
import os
import random

from .metrics import align_tile_origin, tile_rect_to_world, tiles_to_meters


@dataclass(frozen=True)
class CityBlock:
    block_id: int
    grid_x: int
    grid_y: int
    x_tiles: int
    y_tiles: int
    width_tiles: int
    depth_tiles: int
    outer_x_tiles: int
    outer_y_tiles: int
    outer_width_tiles: int
    outer_depth_tiles: int
    x: float
    y: float
    width: float
    depth: float
    zone: str


@dataclass(frozen=True)
class CityParcel:
    parcel_id: int
    block_id: int
    x_tiles: int
    y_tiles: int
    width_tiles: int
    depth_tiles: int
    x: float
    y: float
    width: float
    depth: float
    frontage_direction: str
    min_stories: int
    max_stories: int
    building_kind: str


@dataclass(frozen=True)
class RoadSegment:
    segment_id: str
    orientation: str
    x_tiles: int
    y_tiles: int
    width_tiles: int
    depth_tiles: int
    x: float
    y: float
    width: float
    depth: float
    road_type: str


@dataclass(frozen=True)
class IntersectionPatch:
    patch_id: str
    x_tiles: int
    y_tiles: int
    width_tiles: int
    depth_tiles: int
    x: float
    y: float
    width: float
    depth: float


@dataclass(frozen=True)
class CityLayout:
    blocks: list[CityBlock]
    parcels: list[CityParcel]
    roads: list[RoadSegment]
    intersections: list[IntersectionPatch]
    origin_x_tiles: int
    origin_y_tiles: int
    total_width_tiles: int
    total_depth_tiles: int
    total_width: float
    total_depth: float


ZONE_LAYOUT_RULES = {
    "suburb_residential": {
        "parcels": (1, 3),
        "story_bias": (1, 3),
        "building_kinds": ("house", "apartment", "townhouse"),
    },
    "mixed_city": {
        "parcels": (2, 5),
        "story_bias": (2, 5),
        "building_kinds": ("apartment", "office", "mixed_use", "townhouse"),
    },
    "dense_city": {
        "parcels": (4, 8),
        "story_bias": (3, 7),
        "building_kinds": ("mixed_use", "apartment", "compact"),
    },
    "industrial_edge": {
        "parcels": (1, 3),
        "story_bias": (1, 2),
        "building_kinds": ("warehouse", "office", "compact"),
    },
}


def generate_city_layout(settings, *, use_multiprocessing: bool | None = None, worker_count: int | None = None) -> CityLayout:
    total_width_tiles = settings.width_blocks * settings.block_size_tiles + (settings.width_blocks + 1) * settings.road_width_tiles
    total_depth_tiles = settings.depth_blocks * settings.block_size_tiles + (settings.depth_blocks + 1) * settings.road_width_tiles
    origin_x_tiles = align_tile_origin(total_width_tiles)
    origin_y_tiles = align_tile_origin(total_depth_tiles)

    roads: list[RoadSegment] = []
    intersections: list[IntersectionPatch] = []
    blocks: list[CityBlock] = []
    parcels: list[CityParcel] = []

    for road_index in range(settings.width_blocks + 1):
        x_tiles = origin_x_tiles + road_index * (settings.block_size_tiles + settings.road_width_tiles)
        x, y, width, depth = tile_rect_to_world(x_tiles, origin_y_tiles, settings.road_width_tiles, total_depth_tiles)
        roads.append(
            RoadSegment(
                segment_id=f"v_{road_index:02d}",
                orientation="vertical",
                x_tiles=x_tiles,
                y_tiles=origin_y_tiles,
                width_tiles=settings.road_width_tiles,
                depth_tiles=total_depth_tiles,
                x=x,
                y=y,
                width=width,
                depth=depth,
                road_type="street",
            )
        )

    for road_index in range(settings.depth_blocks + 1):
        y_tiles = origin_y_tiles + road_index * (settings.block_size_tiles + settings.road_width_tiles)
        x, y, width, depth = tile_rect_to_world(origin_x_tiles, y_tiles, total_width_tiles, settings.road_width_tiles)
        roads.append(
            RoadSegment(
                segment_id=f"h_{road_index:02d}",
                orientation="horizontal",
                x_tiles=origin_x_tiles,
                y_tiles=y_tiles,
                width_tiles=total_width_tiles,
                depth_tiles=settings.road_width_tiles,
                x=x,
                y=y,
                width=width,
                depth=depth,
                road_type="street",
            )
        )

    for gx in range(settings.width_blocks + 1):
        for gy in range(settings.depth_blocks + 1):
            x_tiles = origin_x_tiles + gx * (settings.block_size_tiles + settings.road_width_tiles)
            y_tiles = origin_y_tiles + gy * (settings.block_size_tiles + settings.road_width_tiles)
            x, y, width, depth = tile_rect_to_world(x_tiles, y_tiles, settings.road_width_tiles, settings.road_width_tiles)
            intersections.append(
                IntersectionPatch(
                    patch_id=f"i_{gx:02d}_{gy:02d}",
                    x_tiles=x_tiles,
                    y_tiles=y_tiles,
                    width_tiles=settings.road_width_tiles,
                    depth_tiles=settings.road_width_tiles,
                    x=x,
                    y=y,
                    width=width,
                    depth=depth,
                )
            )

    use_mp = bool(settings.use_multiprocessing if use_multiprocessing is None else use_multiprocessing)
    workers = int(settings.worker_count if worker_count is None else worker_count)
    tasks = [
        {
            "settings": _settings_to_payload(settings),
            "origin_x_tiles": origin_x_tiles,
            "origin_y_tiles": origin_y_tiles,
            "gx": gx,
            "gy": gy,
            "block_id": gy * settings.width_blocks + gx + 1,
        }
        for gy in range(settings.depth_blocks)
        for gx in range(settings.width_blocks)
    ]
    task_results = _plan_blocks(tasks, use_multiprocessing=use_mp, worker_count=workers)
    parcel_id = 0
    for block_payload, parcel_payloads in task_results:
        if block_payload is None:
            continue
        block = CityBlock(**block_payload)
        blocks.append(block)
        for payload in parcel_payloads:
            parcel_id += 1
            parcels.append(CityParcel(parcel_id=parcel_id, **payload))

    return CityLayout(
        blocks=blocks,
        parcels=parcels,
        roads=roads,
        intersections=intersections,
        origin_x_tiles=origin_x_tiles,
        origin_y_tiles=origin_y_tiles,
        total_width_tiles=total_width_tiles,
        total_depth_tiles=total_depth_tiles,
        total_width=tiles_to_meters(total_width_tiles),
        total_depth=tiles_to_meters(total_depth_tiles),
    )


def plan_prop_points(layout: CityLayout, settings, *, use_multiprocessing: bool | None = None, worker_count: int | None = None) -> dict[str, list[tuple[float, float]]]:
    use_mp = bool(settings.use_multiprocessing if use_multiprocessing is None else use_multiprocessing)
    workers = int(settings.worker_count if worker_count is None else worker_count)
    block_payloads = [_block_to_payload(block) for block in layout.blocks]
    if not use_mp or len(block_payloads) <= 1:
        tree_points: list[tuple[float, float]] = []
        for payload in block_payloads:
            tree_points.extend(_tree_candidates_worker(payload))
        return {"trees": tree_points}
    max_workers = workers if workers > 0 else min(len(block_payloads), max(1, (os.cpu_count() or 1) - 1))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        tree_lists = list(executor.map(_tree_candidates_worker, block_payloads))
    tree_points: list[tuple[float, float]] = []
    for payload in tree_lists:
        tree_points.extend(payload)
    return {"trees": tree_points}


def _zone_for_block(zone_layout: str, gx: int, gy: int, width_blocks: int, depth_blocks: int) -> str:
    if zone_layout == "industrial_edge":
        return "industrial" if gx == 0 or gy == 0 else "mixed"
    if zone_layout == "dense_city":
        return "dense_core"
    if zone_layout == "mixed_city":
        return "mixed"
    edge = gx in {0, width_blocks - 1} or gy in {0, depth_blocks - 1}
    return "suburb_edge" if edge else "suburb_core"


def _plan_blocks(tasks: list[dict], *, use_multiprocessing: bool, worker_count: int) -> list[tuple[dict | None, list[dict]]]:
    if not use_multiprocessing or len(tasks) <= 1:
        return [_plan_block_worker(task) for task in tasks]
    max_workers = worker_count if worker_count > 0 else min(len(tasks), max(1, (os.cpu_count() or 1) - 1))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_plan_block_worker, tasks))


def _plan_block_worker(task: dict) -> tuple[dict | None, list[dict]]:
    settings = task["settings"]
    gx = int(task["gx"])
    gy = int(task["gy"])
    block_id = int(task["block_id"])
    origin_x_tiles = int(task["origin_x_tiles"])
    origin_y_tiles = int(task["origin_y_tiles"])

    outer_x_tiles = origin_x_tiles + settings["road_width_tiles"] + gx * (settings["block_size_tiles"] + settings["road_width_tiles"])
    outer_y_tiles = origin_y_tiles + settings["road_width_tiles"] + gy * (settings["block_size_tiles"] + settings["road_width_tiles"])
    buildable_x_tiles = outer_x_tiles + settings["sidewalk_width_tiles"]
    buildable_y_tiles = outer_y_tiles + settings["sidewalk_width_tiles"]
    buildable_width_tiles = settings["block_size_tiles"] - settings["sidewalk_width_tiles"] * 2
    buildable_depth_tiles = settings["block_size_tiles"] - settings["sidewalk_width_tiles"] * 2
    if buildable_width_tiles < settings["min_building_width_tiles"] or buildable_depth_tiles < settings["min_building_depth_tiles"]:
        return None, []

    x, y, width, depth = tile_rect_to_world(buildable_x_tiles, buildable_y_tiles, buildable_width_tiles, buildable_depth_tiles)
    block_payload = {
        "block_id": block_id,
        "grid_x": gx,
        "grid_y": gy,
        "x_tiles": buildable_x_tiles,
        "y_tiles": buildable_y_tiles,
        "width_tiles": buildable_width_tiles,
        "depth_tiles": buildable_depth_tiles,
        "outer_x_tiles": outer_x_tiles,
        "outer_y_tiles": outer_y_tiles,
        "outer_width_tiles": settings["block_size_tiles"],
        "outer_depth_tiles": settings["block_size_tiles"],
        "x": x,
        "y": y,
        "width": width,
        "depth": depth,
        "zone": _zone_for_block(settings["zone_layout"], gx, gy, settings["width_blocks"], settings["depth_blocks"]),
    }
    rng = random.Random(int(settings["seed"]) + block_id * 7919)
    rules = ZONE_LAYOUT_RULES.get(settings["zone_layout"], ZONE_LAYOUT_RULES["suburb_residential"])
    parcel_payloads = _subdivide_block_payload(block_payload=block_payload, settings=settings, rules=rules, rng=rng)
    return block_payload, parcel_payloads


def _subdivide_block_payload(*, block_payload: dict, settings: dict, rules: dict, rng: random.Random) -> list[dict]:
    inner_x_tiles = block_payload["x_tiles"] + settings["block_inner_margin_tiles"]
    inner_y_tiles = block_payload["y_tiles"] + settings["block_inner_margin_tiles"]
    inner_width_tiles = block_payload["width_tiles"] - settings["block_inner_margin_tiles"] * 2
    inner_depth_tiles = block_payload["depth_tiles"] - settings["block_inner_margin_tiles"] * 2
    if inner_width_tiles < settings["min_building_width_tiles"] or inner_depth_tiles < settings["min_building_depth_tiles"]:
        inner_x_tiles = block_payload["x_tiles"]
        inner_y_tiles = block_payload["y_tiles"]
        inner_width_tiles = block_payload["width_tiles"]
        inner_depth_tiles = block_payload["depth_tiles"]
    if inner_width_tiles < settings["min_building_width_tiles"] or inner_depth_tiles < settings["min_building_depth_tiles"]:
        return []

    min_parcels, max_parcels = rules["parcels"]
    desired = rng.randint(min_parcels, max_parcels)
    if desired <= 1:
        cols = 1
        rows = 1
    else:
        aspect = max(0.5, inner_width_tiles / max(1, inner_depth_tiles))
        cols = max(1, int(round(math.sqrt(desired * aspect))))
        rows = max(1, int(math.ceil(desired / cols)))

    cols, rows = _fit_grid_counts(
        inner_width_tiles=inner_width_tiles,
        inner_depth_tiles=inner_depth_tiles,
        min_width_tiles=settings["min_building_width_tiles"],
        min_depth_tiles=settings["min_building_depth_tiles"],
        gap_tiles=settings["parcel_gap_tiles"],
        cols=cols,
        rows=rows,
    )
    width_sizes = _split_sizes(inner_width_tiles, cols, settings["parcel_gap_tiles"], settings["min_building_width_tiles"], rng)
    depth_sizes = _split_sizes(inner_depth_tiles, rows, settings["parcel_gap_tiles"], settings["min_building_depth_tiles"], rng)
    if not width_sizes or not depth_sizes:
        return []

    story_low, story_high = rules["story_bias"]
    parcels: list[dict] = []
    cursor_y = inner_y_tiles
    for row_index, depth_tiles in enumerate(depth_sizes):
        cursor_x = inner_x_tiles
        for col_index, width_tiles in enumerate(width_sizes):
            if width_tiles < settings["min_building_width_tiles"] or depth_tiles < settings["min_building_depth_tiles"]:
                cursor_x += width_tiles + settings["parcel_gap_tiles"]
                continue
            x, y, width, depth = tile_rect_to_world(cursor_x, cursor_y, width_tiles, depth_tiles)
            parcels.append(
                {
                    "block_id": block_payload["block_id"],
                    "x_tiles": cursor_x,
                    "y_tiles": cursor_y,
                    "width_tiles": width_tiles,
                    "depth_tiles": depth_tiles,
                    "x": x,
                    "y": y,
                    "width": width,
                    "depth": depth,
                    "frontage_direction": _frontage_direction(row_index, col_index, len(depth_sizes), len(width_sizes)),
                    "min_stories": max(settings["min_stories"], story_low),
                    "max_stories": min(settings["max_stories"], story_high),
                    "building_kind": rng.choice(rules["building_kinds"]),
                }
            )
            cursor_x += width_tiles + settings["parcel_gap_tiles"]
        cursor_y += depth_tiles + settings["parcel_gap_tiles"]
    return parcels


def _settings_to_payload(settings) -> dict:
    return {
        "seed": int(settings.seed),
        "width_blocks": int(settings.width_blocks),
        "depth_blocks": int(settings.depth_blocks),
        "block_size_tiles": int(settings.block_size_tiles),
        "road_width_tiles": int(settings.road_width_tiles),
        "sidewalk_width_tiles": int(settings.sidewalk_width_tiles),
        "block_inner_margin_tiles": int(settings.block_inner_margin_tiles),
        "parcel_gap_tiles": int(settings.parcel_gap_tiles),
        "min_building_width_tiles": int(settings.min_building_width_tiles),
        "min_building_depth_tiles": int(settings.min_building_depth_tiles),
        "min_stories": int(settings.min_stories),
        "max_stories": int(settings.max_stories),
        "zone_layout": str(settings.zone_layout),
    }


def _block_to_payload(block: CityBlock) -> dict:
    return {
        "block_id": int(block.block_id),
        "grid_x": int(block.grid_x),
        "grid_y": int(block.grid_y),
        "x_tiles": int(block.x_tiles),
        "y_tiles": int(block.y_tiles),
        "width_tiles": int(block.width_tiles),
        "depth_tiles": int(block.depth_tiles),
        "outer_x_tiles": int(block.outer_x_tiles),
        "outer_y_tiles": int(block.outer_y_tiles),
        "outer_width_tiles": int(block.outer_width_tiles),
        "outer_depth_tiles": int(block.outer_depth_tiles),
        "x": float(block.x),
        "y": float(block.y),
        "width": float(block.width),
        "depth": float(block.depth),
        "zone": str(block.zone),
    }


def _tree_candidates_worker(block_payload: dict) -> list[tuple[float, float]]:
    candidates: list[tuple[float, float]] = []
    inset = 1.5
    step = 2.0
    x = float(block_payload["x"]) + inset
    max_x = float(block_payload["x"]) + float(block_payload["width"]) - inset
    y0 = float(block_payload["y"]) + inset
    y1 = float(block_payload["y"]) + float(block_payload["depth"]) - inset
    while x <= max_x + 1e-6:
        candidates.append((x, y0))
        candidates.append((x, y1))
        x += step
    y = y0 + step
    while y <= y1 - step + 1e-6:
        candidates.append((float(block_payload["x"]) + inset, y))
        candidates.append((float(block_payload["x"]) + float(block_payload["width"]) - inset, y))
        y += step
    center_x = float(block_payload["x"]) + float(block_payload["width"]) * 0.5
    center_y = float(block_payload["y"]) + float(block_payload["depth"]) * 0.5
    candidates.extend(
        [
            (center_x - step, center_y - step),
            (center_x + step, center_y - step),
            (center_x - step, center_y + step),
            (center_x + step, center_y + step),
        ]
    )
    return candidates


def _fit_grid_counts(*, inner_width_tiles: int, inner_depth_tiles: int, min_width_tiles: int, min_depth_tiles: int, gap_tiles: int, cols: int, rows: int) -> tuple[int, int]:
    cols = max(1, cols)
    rows = max(1, rows)
    while cols > 1 and inner_width_tiles - gap_tiles * (cols - 1) < min_width_tiles * cols:
        cols -= 1
    while rows > 1 and inner_depth_tiles - gap_tiles * (rows - 1) < min_depth_tiles * rows:
        rows -= 1
    return max(1, cols), max(1, rows)


def _split_sizes(total_tiles: int, count: int, gap_tiles: int, min_size: int, rng: random.Random) -> list[int]:
    if count <= 0:
        return []
    usable_tiles = total_tiles - gap_tiles * (count - 1)
    if usable_tiles < min_size * count:
        return []
    sizes = [min_size] * count
    remaining = usable_tiles - min_size * count
    if remaining <= 0:
        return sizes
    weights = [rng.uniform(0.75, 1.25) for _ in range(count)]
    weight_sum = sum(weights) or 1.0
    extras = [int(round(remaining * (weight / weight_sum))) for weight in weights]
    delta = remaining - sum(extras)
    for index in range(abs(delta)):
        extras[index % count] += 1 if delta > 0 else -1
    for index, extra in enumerate(extras):
        sizes[index] += extra
    while sum(sizes) > usable_tiles:
        largest = max(range(count), key=lambda item: sizes[item])
        if sizes[largest] <= min_size:
            break
        sizes[largest] -= 1
    while sum(sizes) < usable_tiles:
        smallest = min(range(count), key=lambda item: sizes[item])
        sizes[smallest] += 1
    return sizes


def _frontage_direction(row_index: int, col_index: int, rows: int, cols: int) -> str:
    if row_index == 0:
        return "south"
    if row_index == rows - 1:
        return "north"
    if col_index == 0:
        return "west"
    if col_index == cols - 1:
        return "east"
    return "south"

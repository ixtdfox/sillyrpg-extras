from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "terrain" / "procedural_city"


def _ensure_stub_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_stub_package("procedural_floorplan_ru_v2", ROOT)
_ensure_stub_package("procedural_floorplan_ru_v2.terrain", ROOT / "terrain")
_ensure_stub_package("procedural_floorplan_ru_v2.terrain.procedural_city", PACKAGE)
game_grid = _load("procedural_floorplan_ru_v2.game_grid", ROOT / "game_grid.py")
metrics = _load("procedural_floorplan_ru_v2.terrain.procedural_city.metrics", PACKAGE / "metrics.py")
layout = _load("procedural_floorplan_ru_v2.terrain.procedural_city.layout", PACKAGE / "layout.py")


@dataclass(frozen=True)
class DummySettings:
    seed: int = 12345
    width_blocks: int = 3
    depth_blocks: int = 2
    block_size_tiles: int = 18
    road_width_tiles: int = 3
    sidewalk_width_tiles: int = 1
    block_inner_margin_tiles: int = 1
    parcel_gap_tiles: int = 1
    min_building_width_tiles: int = 5
    min_building_depth_tiles: int = 5
    min_stories: int = 1
    max_stories: int = 4
    zone_layout: str = "suburb_residential"


def _is_tile_aligned(value: float) -> bool:
    tile = float(game_grid.GAME_TILE_SIZE_M)
    snapped = round(float(value) / tile) * tile
    return abs(snapped - float(value)) < 1e-6


def main() -> None:
    city = layout.generate_city_layout(DummySettings())
    assert len(city.blocks) == 6
    assert len(city.intersections) == (DummySettings.width_blocks + 1) * (DummySettings.depth_blocks + 1)
    assert len(city.roads) == (DummySettings.width_blocks + 1) + (DummySettings.depth_blocks + 1)
    assert city.parcels

    for road in city.roads:
        assert _is_tile_aligned(road.x)
        assert _is_tile_aligned(road.y)
        assert _is_tile_aligned(road.width)
        assert _is_tile_aligned(road.depth)
    for block in city.blocks:
        assert _is_tile_aligned(block.x)
        assert _is_tile_aligned(block.y)
        assert _is_tile_aligned(block.width)
        assert _is_tile_aligned(block.depth)
    for parcel in city.parcels:
        assert _is_tile_aligned(parcel.x)
        assert _is_tile_aligned(parcel.y)
        assert _is_tile_aligned(parcel.width)
        assert _is_tile_aligned(parcel.depth)
        assert parcel.width_tiles >= DummySettings.min_building_width_tiles
        assert parcel.depth_tiles >= DummySettings.min_building_depth_tiles
        assert parcel.min_stories >= 1
        assert parcel.max_stories >= parcel.min_stories
        block = next(item for item in city.blocks if item.block_id == parcel.block_id)
        assert parcel.x >= block.x
        assert parcel.y >= block.y
        assert parcel.x + parcel.width <= block.x + block.width + 1e-6
        assert parcel.y + parcel.depth <= block.y + block.depth + 1e-6

    assert city.roads[0].width == metrics.tiles_to_meters(DummySettings.road_width_tiles)
    assert city.blocks[0].outer_width_tiles == DummySettings.block_size_tiles

    for parcel in city.parcels:
        for road in city.roads:
            overlap_x = not (parcel.x + parcel.width <= road.x or parcel.x >= road.x + road.width)
            overlap_y = not (parcel.y + parcel.depth <= road.y or parcel.y >= road.y + road.depth)
            assert not (overlap_x and overlap_y), f"Parcel {parcel.parcel_id} overlaps road {road.segment_id}"

    candidate_roots = [Path("/home/tony/pets/bpy-city/assets"), Path("/home/tony/pets/bpy-city")]
    for root in candidate_roots:
        normalized = root / "assets" if (root / "assets").exists() else root
        nature_dir = normalized / "nature" / "Models" / "GLTF format"
        if nature_dir.exists():
            tree_assets = [item for item in nature_dir.iterdir() if item.is_file() and "tree" in item.stem.lower()]
            assert tree_assets, f"No tree assets found in {nature_dir}"
            break

    print("smoke_procedural_city_layout: ok")

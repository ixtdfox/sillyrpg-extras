from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "terrain"


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
_ensure_stub_package("procedural_floorplan_ru_v2.terrain", PACKAGE)
mask_schema = _load("procedural_floorplan_ru_v2.terrain.mask_schema", PACKAGE / "mask_schema.py")
region_extractor = _load("procedural_floorplan_ru_v2.terrain.region_extractor", PACKAGE / "region_extractor.py")
terrain_mesh_factory = _load("procedural_floorplan_ru_v2.terrain.terrain_mesh_factory", PACKAGE / "terrain_mesh_factory.py")


def main() -> None:
    TerrainZone = mask_schema.TerrainZone
    mask = mask_schema.TerrainMask(
        width=6,
        height=4,
        pixel_size_m=1.0,
        zones=[
            [TerrainZone.BUILDING, TerrainZone.BUILDING, TerrainZone.EMPTY, TerrainZone.ROAD, TerrainZone.ROAD, TerrainZone.ROAD],
            [TerrainZone.BUILDING, TerrainZone.EMPTY, TerrainZone.EMPTY, TerrainZone.ROAD, TerrainZone.ROAD, TerrainZone.ROAD],
            [TerrainZone.EMPTY, TerrainZone.EMPTY, TerrainZone.GRASS, TerrainZone.GRASS, TerrainZone.ROAD, TerrainZone.ROAD],
            [TerrainZone.SIDEWALK, TerrainZone.SIDEWALK, TerrainZone.GRASS, TerrainZone.GRASS, TerrainZone.ROAD, TerrainZone.ROAD],
        ],
    )
    building_regions = region_extractor.extract_regions(mask, TerrainZone.BUILDING)
    road_regions = region_extractor.extract_regions(mask, TerrainZone.ROAD)
    assert len(building_regions) == 1
    assert building_regions[0].area_px == 3
    assert len(road_regions) == 1
    assert road_regions[0].area_px == 10

    rects = terrain_mesh_factory.decompose_zone_to_rectangles(mask, TerrainZone.ROAD)
    rect_shapes = sorted((rect.x, rect.y, rect.width, rect.height) for rect in rects)
    assert rect_shapes == [(3, 0, 3, 2), (4, 2, 2, 2)]
    print("smoke_terrain_region_extractor: ok")


if __name__ == "__main__":
    main()

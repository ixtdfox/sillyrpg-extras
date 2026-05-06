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


def main() -> None:
    TerrainZone = mask_schema.TerrainZone
    assert mask_schema.classify_pixel(250, 10, 10) == TerrainZone.BUILDING
    assert mask_schema.classify_pixel(60, 60, 60) == TerrainZone.ROAD
    assert mask_schema.classify_pixel(185, 185, 185) == TerrainZone.SIDEWALK
    assert mask_schema.classify_pixel(5, 250, 5) == TerrainZone.GRASS
    assert mask_schema.classify_pixel(255, 255, 255) == TerrainZone.CROSSWALK_HINT
    assert mask_schema.classify_pixel(123, 22, 201, tolerance=10) == TerrainZone.EMPTY

    mask = mask_schema.TerrainMask(
        width=4,
        height=2,
        pixel_size_m=2.0,
        zones=[
            [TerrainZone.BUILDING, TerrainZone.BUILDING, TerrainZone.ROAD, TerrainZone.ROAD],
            [TerrainZone.GRASS, TerrainZone.GRASS, TerrainZone.SIDEWALK, TerrainZone.SIDEWALK],
        ],
        offset_x=-4.0,
        offset_y=-2.0,
    )
    assert mask.cell_center_world(0, 0) == (-3.0, 1.0)
    assert mask.rect_world_bounds(0, 0, 2, 1) == (-4.0, 0.0, 0.0, 2.0)
    print("smoke_terrain_mask_parser: ok")


if __name__ == "__main__":
    main()

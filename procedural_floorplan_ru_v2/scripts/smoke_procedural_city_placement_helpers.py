from __future__ import annotations

import importlib.util
import sys
import types
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
placement = _load("procedural_floorplan_ru_v2.terrain.procedural_city.placement_validator", PACKAGE / "placement_validator.py")


def main() -> None:
    Rect = placement.Rect
    container = Rect(0.0, 0.0, 10.0, 8.0)
    rect = Rect(-1.0, 1.0, 7.0, 7.0)
    dx, dy = placement.clamp_rect_translation_into(container, rect)
    translated = placement.rect_translate(rect, dx, dy)
    assert (dx, dy) == (1.0, 0.0)
    assert placement.rect_contains(container, translated)

    too_large = Rect(0.0, 0.0, 12.0, 8.0)
    assert placement.clamp_rect_translation_into(container, too_large) is None

    registry = placement.PlacementRegistry(placed_buildings=[Rect(1.0, 1.0, 3.0, 3.0)], forbidden=[Rect(6.0, 0.0, 7.0, 2.0)], spacing_m=0.25)
    assert not registry.can_place(Rect(2.9, 1.0, 5.0, 3.0), allowed_area=container)
    assert not registry.can_place(Rect(6.1, 0.1, 6.8, 1.8), allowed_area=container)
    assert registry.can_place(Rect(3.6, 3.6, 5.0, 5.0), allowed_area=container)
    print("smoke_procedural_city_placement_helpers: ok")


if __name__ == "__main__":
    main()

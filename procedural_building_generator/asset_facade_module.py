from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetFacadeModule:
    module_id: str
    asset_object: object | None


def resolve_asset_module(settings, module_id: str) -> AssetFacadeModule:
    mode = getattr(settings, "facade_module_mode", "HYBRID")
    if mode == "PROCEDURAL_ONLY":
        return AssetFacadeModule(module_id=module_id, asset_object=None)

    module_to_prop = {
        "StandardWindowModule": "window_asset",
        "NarrowWindowBayModule": "window_asset",
        "WideWindowBayModule": "window_asset",
        "StairWindowModule": "window_asset",
        "EntranceDoorModule": "entrance_asset",
        "CornerModule": "corner_asset",
        "BalconyModule": "balcony_asset",
    }
    prop_name = module_to_prop.get(module_id)
    asset_obj = getattr(settings, prop_name, None) if prop_name else None
    return AssetFacadeModule(module_id=module_id, asset_object=asset_obj)

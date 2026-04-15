from __future__ import annotations

from ..common.shape_generator import Footprint, generate_footprint
from ..config import ShapeSettings


class ShapeFootprintGenerator:
    """Thin OOP wrapper around footprint generation settings and strategy selection."""

    def build(self, shape_settings: ShapeSettings, *, seed: int) -> Footprint:
        return generate_footprint(
            shape_key=shape_settings.shape_mode,
            room_count=shape_settings.target_room_count,
            min_room_side_m=shape_settings.min_room_side_m,
            house_scale=shape_settings.house_scale,
            seed=seed,
        )

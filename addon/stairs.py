"""Stair planning and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class StairPlan:
    required: bool
    valid: bool
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    width: float = 1.0
    run: float = 3.2
    rise: float = 2.8
    top_landing: float = 0.8
    opening_w: float = 1.2
    opening_d: float = 3.4


def plan_stairs(styled_shape, params: dict, fallback_reasons: List[str]) -> StairPlan:
    floors = params["floors"]
    floor_h = params["floor_height"]
    if floors <= 1:
        return StairPlan(required=False, valid=True)

    main = next((v for v in styled_shape.shape.volumes if v.name == "main"), None)
    if main is None:
        fallback_reasons.append("stairs_no_main")
        return StairPlan(required=True, valid=False)

    width = 1.0
    run = max(3.2, floor_h / 0.175 * 0.28)  # 17.5cm rise, 28cm tread rule-of-thumb
    x = max(0.3, main.width - width - 0.6)
    y = 0.4

    # Keep stairs inside footprint.
    if x + width > main.width - 0.2 or y + run > main.depth - 0.2:
        # Relocate toward center
        x = max(0.3, (main.width - width) * 0.5)
        y = max(0.3, (main.depth - run) * 0.5)

    valid = (x + width <= main.width - 0.2) and (y + run <= main.depth - 0.2)
    top_landing = 0.8

    if top_landing < 0.8:
        top_landing = 0.8

    if not valid:
        fallback_reasons.append("stairs_relocated_failed")

    return StairPlan(
        required=True,
        valid=valid,
        x=x,
        y=y,
        z=0.0,
        width=width,
        run=run,
        rise=floor_h,
        top_landing=top_landing,
        opening_w=width + 0.2,
        opening_d=run + 0.2,
    )

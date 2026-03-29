"""Architectural style rules for facade zoning and features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .shape import ShapeResult


@dataclass
class Opening:
    volume_name: str
    face: str
    kind: str
    x_offset: float
    z_offset: float
    width: float
    height: float


@dataclass
class StyledShape:
    shape: ShapeResult
    zones: Dict[str, str] = field(default_factory=dict)
    openings: List[Opening] = field(default_factory=list)
    balconies: List[dict] = field(default_factory=list)


def apply_style(shape_result: ShapeResult, params: dict, fallback_reasons: List[str]) -> StyledShape:
    styled = StyledShape(shape=shape_result)
    floor_h = params["floor_height"]
    tile = params["tile_size"]

    for volume in shape_result.volumes:
        if volume.name in {"main", "upper"}:
            styled.zones[volume.name] = "dominant"
        elif volume.name == "service":
            styled.zones[volume.name] = "service"
        else:
            styled.zones[volume.name] = "neutral"

    # Entry door
    entry = next((v for v in shape_result.volumes if v.name == "entrance"), None)
    if entry is not None:
        styled.openings.append(
            Opening(
                volume_name="entrance",
                face="front",
                kind="door",
                x_offset=max(0.2, entry.width * 0.5 - 0.5),
                z_offset=0.0,
                width=min(1.2, entry.width - 0.4),
                height=min(2.4, floor_h - 0.2),
            )
        )

    # Large glazing + vertical strips
    for volume in shape_result.volumes:
        if volume.height < floor_h:
            continue

        w = min(max(0.8, volume.width * 0.33), volume.width - 0.4)
        h = min(floor_h * 0.75, floor_h - 0.4)

        for floor_idx in range(params["floors"]):
            z = floor_idx * floor_h + 0.9
            if z + h > volume.height:
                break
            styled.openings.append(
                Opening(
                    volume_name=volume.name,
                    face="front",
                    kind="window",
                    x_offset=max(0.2, (volume.width - w) * 0.5),
                    z_offset=z,
                    width=w,
                    height=h,
                )
            )

        # Asymmetric side strip window.
        strip_w = min(1.0, max(0.8, tile * 0.5))
        strip_h = min(volume.height - 0.4, floor_h * 1.4)
        if strip_h > 0.8 and volume.depth > 1.6:
            styled.openings.append(
                Opening(
                    volume_name=volume.name,
                    face="left",
                    kind="window",
                    x_offset=0.3,
                    z_offset=0.8,
                    width=strip_w,
                    height=strip_h,
                )
            )

    if params.get("balconies", True):
        upper = next((v for v in shape_result.volumes if v.name == "upper"), None)
        if upper is not None:
            styled.balconies.append(
                {
                    "volume_name": upper.name,
                    "width": max(tile, upper.width * 0.5),
                    "depth": 1.2,
                    "height": 0.12,
                    "x_offset": max(0.2, (upper.width * 0.5) * 0.25),
                    "z_offset": 0.15,
                }
            )

    if not styled.openings:
        fallback_reasons.append("style_openings_fallback")

    return styled

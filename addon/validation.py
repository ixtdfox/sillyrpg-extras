"""Parameter validation and fool protection clamping."""

from __future__ import annotations


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def validate_parameters(params: dict, fallback_reasons: list) -> dict:
    out = dict(params)

    out["tile_size"] = max(0.01, float(out.get("tile_size", 2.0)))
    out["floor_height"] = max(2.4, float(out.get("floor_height", 2.8)))
    out["floors"] = max(1, int(out.get("floors", 2)))
    out["width"] = max(out["tile_size"] * 2, float(out.get("width", 10.0)))
    out["depth"] = max(out["tile_size"] * 2, float(out.get("depth", 8.0)))

    out["window_head"] = _clamp(
        float(out.get("window_head", 2.2)),
        1.8,
        out["floor_height"],
    )
    out["door_height"] = _clamp(
        float(out.get("door_height", 2.2)),
        1.9,
        out["floor_height"] - 0.05,
    )

    if out["door_height"] >= out["floor_height"]:
        fallback_reasons.append("door_height_clamped")
        out["door_height"] = out["floor_height"] - 0.05

    if out.get("rooms", 1) < 1:
        fallback_reasons.append("rooms_clamped")
        out["rooms"] = 1

    return out

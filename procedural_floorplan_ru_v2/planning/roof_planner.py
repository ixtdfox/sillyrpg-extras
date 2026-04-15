from __future__ import annotations


class RoofPlanner:
    """Plans a simple flat roof that exactly follows the top-story footprint."""

    def plan_tiles(self, context) -> list[tuple[int, int]]:
        return sorted(set(context.footprint.tiles))

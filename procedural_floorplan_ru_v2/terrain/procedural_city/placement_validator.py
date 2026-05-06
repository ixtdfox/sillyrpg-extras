from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def rect_width(rect: Rect) -> float:
    return float(rect.max_x - rect.min_x)


def rect_depth(rect: Rect) -> float:
    return float(rect.max_y - rect.min_y)


def inflate_rect(rect: Rect, margin_m: float) -> Rect:
    margin = float(margin_m)
    return Rect(rect.min_x - margin, rect.min_y - margin, rect.max_x + margin, rect.max_y + margin)


def rects_overlap(a: Rect, b: Rect, epsilon: float = 1e-4) -> bool:
    return not (
        a.max_x <= b.min_x + epsilon
        or a.min_x >= b.max_x - epsilon
        or a.max_y <= b.min_y + epsilon
        or a.min_y >= b.max_y - epsilon
    )


def rect_contains(container: Rect, rect: Rect, epsilon: float = 1e-4) -> bool:
    return (
        rect.min_x >= container.min_x - epsilon
        and rect.max_x <= container.max_x + epsilon
        and rect.min_y >= container.min_y - epsilon
        and rect.max_y <= container.max_y + epsilon
    )


def rect_from_parcel(parcel, inset_m: float = 0.0) -> Rect:
    return Rect(
        float(parcel.x) + inset_m,
        float(parcel.y) + inset_m,
        float(parcel.x + parcel.width) - inset_m,
        float(parcel.y + parcel.depth) - inset_m,
    )


def rect_from_block(block, inset_m: float = 0.0) -> Rect:
    return Rect(
        float(block.x) + inset_m,
        float(block.y) + inset_m,
        float(block.x + block.width) - inset_m,
        float(block.y + block.depth) - inset_m,
    )


def rect_from_road(road) -> Rect:
    return Rect(float(road.x), float(road.y), float(road.x + road.width), float(road.y + road.depth))


def rect_from_intersection(patch) -> Rect:
    return Rect(float(patch.x), float(patch.y), float(patch.x + patch.width), float(patch.y + patch.depth))


@dataclass
class PlacementRegistry:
    placed_buildings: list[Rect] = field(default_factory=list)
    forbidden: list[Rect] = field(default_factory=list)
    spacing_m: float = 0.15

    def can_place(self, rect: Rect, allowed_area: Rect | None = None) -> bool:
        if allowed_area is not None and not rect_contains(allowed_area, rect):
            return False
        inflated = inflate_rect(rect, self.spacing_m)
        for other in self.placed_buildings:
            if rects_overlap(inflated, inflate_rect(other, self.spacing_m)):
                return False
        for forbidden in self.forbidden:
            if rects_overlap(inflated, forbidden):
                return False
        return True

    def reserve(self, rect: Rect) -> None:
        self.placed_buildings.append(rect)

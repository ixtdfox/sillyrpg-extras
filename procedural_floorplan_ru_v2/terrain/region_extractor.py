from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .mask_schema import TerrainMask, TerrainZone


@dataclass(frozen=True)
class TerrainRegion:
    zone: TerrainZone
    pixels: frozenset[tuple[int, int]]
    bounds_px: tuple[int, int, int, int]
    area_px: int
    centroid_px: tuple[float, float]


def extract_regions(mask: TerrainMask, zone: TerrainZone, min_area_px: int = 1) -> list[TerrainRegion]:
    visited = [[False for _x in range(mask.width)] for _y in range(mask.height)]
    regions: list[TerrainRegion] = []

    for py in range(mask.height):
        for px in range(mask.width):
            if visited[py][px] or mask.zone_at(px, py) != zone:
                continue
            region_pixels = _collect_region(mask, zone, px, py, visited)
            if len(region_pixels) < max(1, int(min_area_px)):
                continue
            xs = [item[0] for item in region_pixels]
            ys = [item[1] for item in region_pixels]
            regions.append(
                TerrainRegion(
                    zone=zone,
                    pixels=frozenset(region_pixels),
                    bounds_px=(min(xs), min(ys), max(xs), max(ys)),
                    area_px=len(region_pixels),
                    centroid_px=(sum(xs) / len(xs), sum(ys) / len(ys)),
                )
            )
    return regions


def _collect_region(mask: TerrainMask, zone: TerrainZone, start_x: int, start_y: int, visited: list[list[bool]]) -> set[tuple[int, int]]:
    queue = deque([(start_x, start_y)])
    visited[start_y][start_x] = True
    pixels: set[tuple[int, int]] = set()

    while queue:
        px, py = queue.popleft()
        pixels.add((px, py))
        for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
            if nx < 0 or ny < 0 or nx >= mask.width or ny >= mask.height:
                continue
            if visited[ny][nx] or mask.zone_at(nx, ny) != zone:
                continue
            visited[ny][nx] = True
            queue.append((nx, ny))
    return pixels

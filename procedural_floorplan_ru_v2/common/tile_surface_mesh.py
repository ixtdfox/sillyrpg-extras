from __future__ import annotations

import bpy


Tile = tuple[int, int]


def build_tile_surface_mesh(
    mesh: bpy.types.Mesh,
    tiles: list[Tile] | set[Tile] | frozenset[Tile],
    *,
    tile_size: float,
    top_z: float,
    bottom_z: float | None = None,
    include_perimeter_sides: bool = True,
    include_bottom: bool = False,
) -> None:
    """Builds a clean shell from grid tiles without hidden internal box faces."""
    sorted_tiles = sorted({(int(tile_x), int(tile_y)) for tile_x, tile_y in tiles})
    tile_set = set(sorted_tiles)
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    vertex_index: dict[tuple[float, float, float], int] = {}

    def v(co: tuple[float, float, float]) -> int:
        key = (round(float(co[0]), 6), round(float(co[1]), 6), round(float(co[2]), 6))
        index = vertex_index.get(key)
        if index is None:
            index = len(verts)
            vertex_index[key] = index
            verts.append(key)
        return index

    for tile_x, tile_y in sorted_tiles:
        x0 = float(tile_x) * tile_size
        y0 = float(tile_y) * tile_size
        x1 = x0 + tile_size
        y1 = y0 + tile_size

        faces.append(
            (
                v((x0, y0, top_z)),
                v((x1, y0, top_z)),
                v((x1, y1, top_z)),
                v((x0, y1, top_z)),
            )
        )

        if include_bottom and bottom_z is not None:
            faces.append(
                (
                    v((x0, y1, bottom_z)),
                    v((x1, y1, bottom_z)),
                    v((x1, y0, bottom_z)),
                    v((x0, y0, bottom_z)),
                )
            )

        if not include_perimeter_sides or bottom_z is None:
            continue

        if (tile_x, tile_y - 1) not in tile_set:
            faces.append(
                (
                    v((x0, y0, bottom_z)),
                    v((x1, y0, bottom_z)),
                    v((x1, y0, top_z)),
                    v((x0, y0, top_z)),
                )
            )
        if (tile_x + 1, tile_y) not in tile_set:
            faces.append(
                (
                    v((x1, y0, bottom_z)),
                    v((x1, y1, bottom_z)),
                    v((x1, y1, top_z)),
                    v((x1, y0, top_z)),
                )
            )
        if (tile_x, tile_y + 1) not in tile_set:
            faces.append(
                (
                    v((x1, y1, bottom_z)),
                    v((x0, y1, bottom_z)),
                    v((x0, y1, top_z)),
                    v((x1, y1, top_z)),
                )
            )
        if (tile_x - 1, tile_y) not in tile_set:
            faces.append(
                (
                    v((x0, y1, bottom_z)),
                    v((x0, y0, bottom_z)),
                    v((x0, y0, top_z)),
                    v((x0, y1, top_z)),
                )
            )

    mesh.from_pydata(verts, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)

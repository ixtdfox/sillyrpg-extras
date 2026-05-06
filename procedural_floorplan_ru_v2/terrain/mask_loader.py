from __future__ import annotations

from pathlib import Path

import bpy

from .mask_schema import TerrainMask, classify_pixel


def load_mask_image(path: str, *, downsample: int = 1, pixel_size_m: float = 1.0, tolerance: int = 24) -> TerrainMask:
    resolved_path = Path(bpy.path.abspath(path)).expanduser()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Файл mask не найден: {resolved_path}")

    image = bpy.data.images.load(str(resolved_path), check_existing=True)
    if image is None:
        raise RuntimeError("Blender не смог загрузить изображение mask")
    if image.size[0] <= 0 or image.size[1] <= 0:
        raise ValueError("Изображение mask пустое")

    width = int(image.size[0])
    height = int(image.size[1])
    step = max(1, int(downsample))
    pixels = list(image.pixels[:])
    if not pixels:
        raise ValueError("Изображение mask не содержит пикселей")

    sampled_x = list(range(0, width, step))
    sampled_y = list(range(0, height, step))
    ds_width = len(sampled_x)
    ds_height = len(sampled_y)
    offset_x = -(ds_width * pixel_size_m) * 0.5
    offset_y = -(ds_height * pixel_size_m) * 0.5
    zones = [[None for _x in range(ds_width)] for _y in range(ds_height)]

    for y_raw in sampled_y:
        for x_raw in sampled_x:
            pixel_index = (y_raw * width + x_raw) * 4
            r = int(round(pixels[pixel_index] * 255.0))
            g = int(round(pixels[pixel_index + 1] * 255.0))
            b = int(round(pixels[pixel_index + 2] * 255.0))
            top_down_y = height - 1 - y_raw
            py = top_down_y // step
            px = x_raw // step
            zones[py][px] = classify_pixel(r, g, b, tolerance=tolerance)

    return TerrainMask(
        width=ds_width,
        height=ds_height,
        pixel_size_m=float(pixel_size_m),
        zones=zones,
        offset_x=offset_x,
        offset_y=offset_y,
    )

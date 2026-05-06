from __future__ import annotations

import binascii
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import bpy

from .building_placer import place_buildings_from_mask
from .collection_utils import delete_collection_tree, ensure_terrain_scene_collections, validate_generated_buildings_parent
from .crosswalk_generator import create_crosswalk_objects
from .mask_loader import load_mask_image
from .mask_schema import TerrainZone
from .region_extractor import extract_regions
from .terrain_materials import ensure_terrain_material
from .terrain_mesh_factory import create_curb_objects, create_zone_rectangles


class TerrainSceneGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TerrainGenerationStats:
    buildings_created: int = 0
    road_objects: int = 0
    sidewalk_objects: int = 0
    grass_objects: int = 0
    curb_objects: int = 0
    crosswalk_objects: int = 0


class TerrainSceneGenerator:
    def generate(self, context, props, terrain_settings, progress=None) -> TerrainGenerationStats:
        _progress_set(progress, 5, "Validating terrain scene settings", report=True)
        self._validate(terrain_settings)
        _progress_set(progress, 15, "Loading image mask", report=True)
        terrain_mask = load_mask_image(
            terrain_settings.mask_path,
            downsample=terrain_settings.downsample,
            pixel_size_m=terrain_settings.pixel_size_m,
        )
        _progress_set(progress, 25, "Extracting terrain regions", report=True)
        building_regions = extract_regions(terrain_mask, TerrainZone.BUILDING, min_area_px=terrain_settings.min_building_area_px)
        road_regions = extract_regions(terrain_mask, TerrainZone.ROAD, min_area_px=1)
        if not building_regions:
            raise TerrainSceneGenerationError("Mask не содержит building-pixels подходящего размера")
        if not road_regions:
            raise TerrainSceneGenerationError("Mask не содержит road-pixels")

        _progress_set(progress, 35, "Preparing terrain scene collections", report=True)
        collections = ensure_terrain_scene_collections(
            context.scene,
            terrain_settings.collection_name,
            delete_old=terrain_settings.delete_old,
        )
        collections["root"]["terrain_environment_type"] = terrain_settings.environment_type
        collections["root"]["terrain_generated_by"] = "terrain_scene_generator"
        collections["root"]["terrain_scene_id"] = terrain_settings.collection_name

        _progress_set(progress, 45, "Generating roads and sidewalks", report=True)
        materials = self._materials(terrain_settings)
        road_objects = create_zone_rectangles(
            scene=context.scene,
            collection=collections["roads"],
            mask=terrain_mask,
            zone=TerrainZone.ROAD,
            material=materials["road"],
            object_prefix="Road",
            top_z=terrain_settings.road_height_offset,
            thickness=0.02,
        )
        sidewalk_objects = create_zone_rectangles(
            scene=context.scene,
            collection=collections["sidewalks"],
            mask=terrain_mask,
            zone=TerrainZone.SIDEWALK,
            material=materials["sidewalk"],
            object_prefix="Sidewalk",
            top_z=terrain_settings.sidewalk_height_offset,
            thickness=0.04,
        )
        grass_objects = create_zone_rectangles(
            scene=context.scene,
            collection=collections["grass"],
            mask=terrain_mask,
            zone=TerrainZone.GRASS,
            material=materials["grass"],
            object_prefix="Grass",
            top_z=0.0,
            thickness=0.02,
        )
        _progress_set(progress, 65, "Generating curbs and crosswalks", report=True)
        curb_objects = create_curb_objects(
            collection=collections["curbs"],
            mask=terrain_mask,
            material=materials["curb"],
            road_z=terrain_settings.road_height_offset,
            curb_height=terrain_settings.curb_height,
            curb_width=terrain_settings.curb_width,
        )
        crosswalk_objects = []
        if terrain_settings.generate_crosswalks:
            crosswalk_objects = create_crosswalk_objects(
                collection=collections["crosswalks"],
                mask=terrain_mask,
                material=materials["crosswalk"],
                road_height_offset=terrain_settings.road_height_offset,
            )

        _progress_set(progress, 70, f"Generating buildings 0/{len(building_regions)}", report=True)
        building_collections = place_buildings_from_mask(
            scene=context.scene,
            props=props,
            terrain_settings=terrain_settings,
            terrain_mask=terrain_mask,
            buildings_collection=collections["buildings"],
            terrain_root_name=terrain_settings.collection_name,
            progress=progress,
            progress_start=70,
            progress_end=92,
        )
        if terrain_settings.generate_debug_markers:
            _progress_set(progress, 96, "Creating debug markers", report=True)
            self._create_debug_markers(collections["debug"], terrain_mask, building_regions)

        _progress_set(progress, 100, "Terrain generation done", report=True)
        validate_generated_buildings_parent(context.scene, collections["root"], collections["buildings"])
        print(f"[terrain] Generated buildings: {len(building_collections)} collections under {collections['root'].name}/{collections['buildings'].name}")
        return TerrainGenerationStats(
            buildings_created=len(building_collections),
            road_objects=len(road_objects),
            sidewalk_objects=len(sidewalk_objects),
            grass_objects=len(grass_objects),
            curb_objects=len(curb_objects),
            crosswalk_objects=len(crosswalk_objects),
        )

    def clear(self, scene: bpy.types.Scene, terrain_collection_name: str) -> bool:
        root = bpy.data.collections.get(str(terrain_collection_name))
        if root is None:
            return False
        delete_collection_tree(root)
        return True

    def _validate(self, terrain_settings) -> None:
        if terrain_settings.environment_type != "city":
            raise TerrainSceneGenerationError(f"Пока поддерживается только environment type 'city', получено: {terrain_settings.environment_type}")
        if not terrain_settings.mask_path.strip():
            raise TerrainSceneGenerationError("Не указан путь к image mask")
        if terrain_settings.pixel_size_m <= 0.0:
            raise TerrainSceneGenerationError("terrain_pixel_size_m должен быть больше нуля")
        if terrain_settings.downsample <= 0:
            raise TerrainSceneGenerationError("terrain_downsample должен быть >= 1")

    def _materials(self, terrain_settings):
        return {
            "road": ensure_terrain_material(
                "Terrain_Road_Asphalt",
                (0.08, 0.08, 0.08, 1.0),
                terrain_settings.textures.road_texture_path,
            ),
            "sidewalk": ensure_terrain_material(
                "Terrain_Sidewalk_Concrete",
                (0.63, 0.63, 0.63, 1.0),
                terrain_settings.textures.sidewalk_texture_path,
            ),
            "curb": ensure_terrain_material(
                "Terrain_Curb_Concrete",
                (0.78, 0.78, 0.78, 1.0),
                terrain_settings.textures.curb_texture_path,
            ),
            "grass": ensure_terrain_material(
                "Terrain_Grass",
                (0.13, 0.48, 0.13, 1.0),
                terrain_settings.textures.grass_texture_path,
            ),
            "crosswalk": ensure_terrain_material(
                "Terrain_Crosswalk_White",
                (0.96, 0.96, 0.96, 1.0),
                "",
            ),
        }

    def _create_debug_markers(self, collection: bpy.types.Collection, terrain_mask, building_regions) -> None:
        for region_index, region in enumerate(building_regions):
            empty = bpy.data.objects.new(f"Region_{region_index:03d}_Marker", None)
            x, y = terrain_mask.cell_center_world(region.centroid_px[0], region.centroid_px[1])
            empty.location = (x, y, 0.25)
            empty.empty_display_type = "PLAIN_AXES"
            empty["terrain_region_id"] = int(region_index)
            empty["terrain_zone"] = region.zone.value
            collection.objects.link(empty)


def _progress_set(progress, percent: int, label: str, report: bool = False) -> None:
    if progress is not None:
        progress.update(percent, label=label, report=report)


def create_sample_mask_legend() -> Path:
    width = 256
    height = 128
    output_path = Path(tempfile.gettempdir()) / "procedural_floorplan_terrain_mask_legend.png"
    rows = [
        (255, 0, 0),
        (64, 64, 64),
        (176, 176, 176),
        (0, 255, 0),
        (255, 255, 255),
        (0, 0, 0),
        (0, 0, 255),
        (255, 255, 0),
    ]
    raw = bytearray()
    band_h = max(1, height // len(rows))
    for y in range(height):
        raw.append(0)
        color = rows[min(len(rows) - 1, y // band_h)]
        for _x in range(width):
            raw.extend((color[0], color[1], color[2], 255))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", binascii.crc32(tag + data) & 0xFFFFFFFF)

    png = bytearray()
    png.extend(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), level=9)))
    png.extend(chunk(b"IEND", b""))
    output_path.write_bytes(bytes(png))
    return output_path

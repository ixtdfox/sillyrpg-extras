from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerrainTextureSettings:
    road_texture_path: str
    sidewalk_texture_path: str
    curb_texture_path: str
    grass_texture_path: str


@dataclass(frozen=True)
class TerrainSettings:
    enabled: bool
    environment_type: str
    mask_path: str
    collection_name: str
    delete_old: bool
    pixel_size_m: float
    downsample: int
    seed: int
    building_max_stories: int
    building_min_stories: int
    building_density: float
    min_building_area_px: int
    road_height_offset: float
    sidewalk_height_offset: float
    curb_height: float
    curb_width: float
    generate_crosswalks: bool
    crosswalk_spacing_m: float
    crosswalk_width_m: float
    generate_debug_markers: bool
    textures: TerrainTextureSettings


def terrain_settings_from_props(props) -> TerrainSettings:
    min_stories = max(1, int(props.terrain_building_min_stories))
    max_stories = max(1, int(props.terrain_building_max_stories))
    if min_stories > max_stories:
        min_stories, max_stories = max_stories, min_stories

    return TerrainSettings(
        enabled=bool(getattr(props, "terrain_enabled", False)),
        environment_type=str(getattr(props, "terrain_environment_type", "city")),
        mask_path=str(getattr(props, "terrain_mask_path", "")),
        collection_name=str(getattr(props, "terrain_collection_name", "GeneratedTerrainScene")),
        delete_old=bool(getattr(props, "terrain_delete_old", True)),
        pixel_size_m=max(0.01, float(getattr(props, "terrain_pixel_size_m", 1.0))),
        downsample=max(1, int(getattr(props, "terrain_downsample", 1))),
        seed=int(getattr(props, "terrain_seed", 12345)),
        building_max_stories=max_stories,
        building_min_stories=min_stories,
        building_density=min(1.0, max(0.0, float(getattr(props, "terrain_building_density", 1.0)))),
        min_building_area_px=max(1, int(getattr(props, "terrain_min_building_area_px", 12))),
        road_height_offset=float(getattr(props, "terrain_road_height_offset", 0.0)),
        sidewalk_height_offset=float(getattr(props, "terrain_sidewalk_height_offset", 0.04)),
        curb_height=max(0.0, float(getattr(props, "terrain_curb_height", 0.12))),
        curb_width=max(0.01, float(getattr(props, "terrain_curb_width", 0.18))),
        generate_crosswalks=bool(getattr(props, "terrain_generate_crosswalks", True)),
        crosswalk_spacing_m=max(0.05, float(getattr(props, "terrain_crosswalk_spacing_m", 0.45))),
        crosswalk_width_m=max(0.1, float(getattr(props, "terrain_crosswalk_width_m", 2.5))),
        generate_debug_markers=bool(getattr(props, "terrain_generate_debug_markers", False)),
        textures=TerrainTextureSettings(
            road_texture_path=str(getattr(props, "terrain_road_texture_path", "")),
            sidewalk_texture_path=str(getattr(props, "terrain_sidewalk_texture_path", "")),
            curb_texture_path=str(getattr(props, "terrain_curb_texture_path", "")),
            grass_texture_path=str(getattr(props, "terrain_grass_texture_path", "")),
        ),
    )

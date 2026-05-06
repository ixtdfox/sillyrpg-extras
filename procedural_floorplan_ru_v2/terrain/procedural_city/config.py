from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProceduralCitySettings:
    collection_name: str
    delete_old: bool
    seed: int
    width_blocks: int
    depth_blocks: int
    block_size_tiles: int
    road_width_tiles: int
    sidewalk_width_tiles: int
    block_inner_margin_tiles: int
    parcel_gap_tiles: int
    min_building_width_tiles: int
    min_building_depth_tiles: int
    min_stories: int
    max_stories: int
    building_density: float
    zone_layout: str
    include_ground: bool
    include_cars: bool
    car_density: float
    include_trees: bool
    tree_density: float
    include_street_furniture: bool
    include_traffic_lights: bool
    assets_root: str
    use_multiprocessing: bool = True
    worker_count: int = 0
    avoid_building_overlaps: bool = True
    allow_relocate_buildings: bool = True
    building_spacing_tiles: float = 0.25
    keep_rejected_buildings: bool = False
    generate_debug_markers: bool = False

    @property
    def block_size_m(self) -> float:
        from .metrics import tiles_to_meters

        return tiles_to_meters(self.block_size_tiles)

    @property
    def road_width_m(self) -> float:
        from .metrics import tiles_to_meters

        return tiles_to_meters(self.road_width_tiles)

    @property
    def sidewalk_width_m(self) -> float:
        from .metrics import tiles_to_meters

        return tiles_to_meters(self.sidewalk_width_tiles)


def procedural_city_settings_from_props(props) -> ProceduralCitySettings:
    min_stories = max(1, int(getattr(props, "terrain_building_min_stories", 1)))
    max_stories = max(min_stories, int(getattr(props, "terrain_building_max_stories", 4)))
    return ProceduralCitySettings(
        collection_name=str(getattr(props, "terrain_collection_name", "GeneratedTerrainScene")),
        delete_old=bool(getattr(props, "terrain_delete_old", True)),
        seed=int(getattr(props, "terrain_seed", 12345)),
        width_blocks=max(1, int(getattr(props, "terrain_city_width_blocks", 6))),
        depth_blocks=max(1, int(getattr(props, "terrain_city_depth_blocks", 5))),
        block_size_tiles=max(8, int(getattr(props, "terrain_block_size_tiles", 18))),
        road_width_tiles=max(1, int(getattr(props, "terrain_road_width_tiles", 3))),
        sidewalk_width_tiles=max(0, int(getattr(props, "terrain_sidewalk_width_tiles", 1))),
        block_inner_margin_tiles=max(0, int(getattr(props, "terrain_block_inner_margin_tiles", 1))),
        parcel_gap_tiles=max(0, int(getattr(props, "terrain_parcel_gap_tiles", 1))),
        min_building_width_tiles=max(2, int(getattr(props, "terrain_min_building_width_tiles", 5))),
        min_building_depth_tiles=max(2, int(getattr(props, "terrain_min_building_depth_tiles", 5))),
        min_stories=min_stories,
        max_stories=max_stories,
        building_density=min(1.0, max(0.0, float(getattr(props, "terrain_building_density", 0.8)))),
        zone_layout=str(getattr(props, "terrain_zone_layout", "suburb_residential")),
        include_ground=bool(getattr(props, "terrain_include_ground", True)),
        include_cars=bool(getattr(props, "terrain_include_cars", True)),
        car_density=min(1.0, max(0.0, float(getattr(props, "terrain_car_density", 0.35)))),
        include_trees=bool(getattr(props, "terrain_include_trees", True)),
        tree_density=min(1.0, max(0.0, float(getattr(props, "terrain_tree_density", 0.65)))),
        include_street_furniture=bool(getattr(props, "terrain_include_street_furniture", True)),
        include_traffic_lights=bool(getattr(props, "terrain_include_traffic_lights", True)),
        assets_root=str(getattr(props, "terrain_bpy_city_assets_root", "/home/tony/pets/bpy-city/assets")),
        use_multiprocessing=bool(getattr(props, "terrain_use_multiprocessing", True)),
        worker_count=max(0, int(getattr(props, "terrain_worker_count", 0))),
        avoid_building_overlaps=bool(getattr(props, "terrain_avoid_building_overlaps", True)),
        allow_relocate_buildings=bool(getattr(props, "terrain_allow_relocate_buildings", True)),
        building_spacing_tiles=max(0.0, float(getattr(props, "terrain_building_spacing_tiles", 0.25))),
        keep_rejected_buildings=bool(getattr(props, "terrain_keep_rejected_buildings", False)),
        generate_debug_markers=bool(getattr(props, "terrain_generate_debug_markers", False)),
    )

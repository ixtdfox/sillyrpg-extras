from __future__ import annotations

from dataclasses import dataclass

from .common.utils import quantize_025
from .domain.building import VerticalProfileMode
from .domain.stairs import StairMode


@dataclass(frozen=True)
class GeneralSettings:
    delete_old: bool
    randomize_seed_each_build: bool
    collection_name: str
    seed: int
    text_size: float


@dataclass(frozen=True)
class ShapeSettings:
    target_room_count: int
    min_room_side_m: float
    house_scale: float
    shape_mode: str


@dataclass(frozen=True)
class StorySettings:
    story_count: int
    layout_mode: str
    vertical_profile_mode: str
    profile_strength: float


@dataclass(frozen=True)
class FloorBandSettings:
    enabled: bool
    depth: float
    height: float


@dataclass(frozen=True)
class RoofBorderSettings:
    enabled: bool
    depth: float
    height: float


@dataclass(frozen=True)
class WallSettings:
    outer_walls_enabled: bool
    wall_height: float
    wall_module_width: float
    wall_thickness: float


@dataclass(frozen=True)
class AtlasSettings:
    enabled: bool
    manifest_path: str
    image_path: str
    include_interior_walls: bool
    random_pick: bool


@dataclass(frozen=True)
class DecalSettings:
    enabled: bool
    manifest_path: str
    image_path: str
    density: float
    enable_streaks: bool


@dataclass(frozen=True)
class DoorSettings:
    enabled: bool
    interior_width: float
    interior_height: float
    entry_width: float
    entry_height: float
    leaf_thickness: float
    min_edge_offset: float
    min_corner_offset: float


@dataclass(frozen=True)
class WindowSettings:
    enabled: bool
    width: float
    height: float
    sill_height: float
    min_corner_offset: float
    min_door_offset: float
    min_partition_offset: float
    min_edge_offset: float


@dataclass(frozen=True)
class StairSettings:
    enabled: bool
    mode: StairMode
    width: float
    landing_size: float
    mid_landing_size: float
    riser_height: float
    tread_depth: float
    min_free_area: float
    door_clearance: float
    window_clearance: float


@dataclass(frozen=True)
class RoofRailingSettings:
    enabled: bool
    height: float
    post_size: float
    rail_thickness: float
    rail_count: int


@dataclass(frozen=True)
class GenerationSettings:
    general: GeneralSettings
    shape: ShapeSettings
    stories: StorySettings
    floor_bands: FloorBandSettings
    roof_border: RoofBorderSettings
    walls: WallSettings
    atlas: AtlasSettings
    decals: DecalSettings
    doors: DoorSettings
    windows: WindowSettings
    stairs: StairSettings
    roof_railing: RoofRailingSettings

    # Backward-compatible accessors for existing atlas/UI helpers.
    @property
    def delete_old(self) -> bool:
        return self.general.delete_old

    @property
    def randomize_seed_each_build(self) -> bool:
        return self.general.randomize_seed_each_build

    @property
    def collection_name(self) -> str:
        return self.general.collection_name

    @property
    def seed(self) -> int:
        return self.general.seed

    @property
    def text_size(self) -> float:
        return self.general.text_size

    @property
    def target_room_count(self) -> int:
        return self.shape.target_room_count

    @property
    def min_room_side_m(self) -> float:
        return self.shape.min_room_side_m

    @property
    def house_scale(self) -> float:
        return self.shape.house_scale

    @property
    def shape_mode(self) -> str:
        return self.shape.shape_mode

    @property
    def story_count(self) -> int:
        return self.stories.story_count

    @property
    def story_layout_mode(self) -> str:
        return self.stories.layout_mode

    @property
    def vertical_profile_mode(self) -> str:
        return self.stories.vertical_profile_mode

    @property
    def vertical_profile_strength(self) -> float:
        return self.stories.profile_strength

    @property
    def floor_bands_enabled(self) -> bool:
        return self.floor_bands.enabled

    @property
    def floor_band_depth(self) -> float:
        return self.floor_bands.depth

    @property
    def floor_band_height(self) -> float:
        return self.floor_bands.height

    @property
    def roof_border_enabled(self) -> bool:
        return self.roof_border.enabled

    @property
    def roof_border_depth(self) -> float:
        return self.roof_border.depth

    @property
    def roof_border_height(self) -> float:
        return self.roof_border.height

    @property
    def outer_walls_enabled(self) -> bool:
        return self.walls.outer_walls_enabled

    @property
    def wall_height(self) -> float:
        return self.walls.wall_height

    @property
    def wall_module_width(self) -> float:
        return self.walls.wall_module_width

    @property
    def wall_thickness(self) -> float:
        return self.walls.wall_thickness

    @property
    def atlas_enabled(self) -> bool:
        return self.atlas.enabled

    @property
    def atlas_manifest_path(self) -> str:
        return self.atlas.manifest_path

    @property
    def atlas_image_path(self) -> str:
        return self.atlas.image_path

    @property
    def atlas_include_interior_walls(self) -> bool:
        return self.atlas.include_interior_walls

    @property
    def atlas_random_pick(self) -> bool:
        return self.atlas.random_pick

    @property
    def decals_enabled(self) -> bool:
        return self.decals.enabled

    @property
    def decal_manifest_path(self) -> str:
        return self.decals.manifest_path

    @property
    def decal_image_path(self) -> str:
        return self.decals.image_path

    @property
    def decal_density(self) -> float:
        return self.decals.density

    @property
    def decal_enable_streaks(self) -> bool:
        return self.decals.enable_streaks

    @property
    def doors_enabled(self) -> bool:
        return self.doors.enabled

    @property
    def interior_door_width(self) -> float:
        return self.doors.interior_width

    @property
    def interior_door_height(self) -> float:
        return self.doors.interior_height

    @property
    def entry_door_width(self) -> float:
        return self.doors.entry_width

    @property
    def entry_door_height(self) -> float:
        return self.doors.entry_height

    @property
    def door_leaf_thickness(self) -> float:
        return self.doors.leaf_thickness

    @property
    def door_min_edge_offset(self) -> float:
        return self.doors.min_edge_offset

    @property
    def door_min_corner_offset(self) -> float:
        return self.doors.min_corner_offset

    @property
    def windows_enabled(self) -> bool:
        return self.windows.enabled

    @property
    def window_width(self) -> float:
        return self.windows.width

    @property
    def window_height(self) -> float:
        return self.windows.height

    @property
    def window_sill_height(self) -> float:
        return self.windows.sill_height

    @property
    def window_min_corner_offset(self) -> float:
        return self.windows.min_corner_offset

    @property
    def window_min_door_offset(self) -> float:
        return self.windows.min_door_offset

    @property
    def window_min_partition_offset(self) -> float:
        return self.windows.min_partition_offset

    @property
    def window_min_edge_offset(self) -> float:
        return self.windows.min_edge_offset

    @property
    def stairs_enabled(self) -> bool:
        return self.stairs.enabled

    @property
    def stair_width(self) -> float:
        return self.stairs.width

    @property
    def stair_mode(self) -> str:
        return self.stairs.mode.value

    @property
    def stair_landing_size(self) -> float:
        return self.stairs.landing_size

    @property
    def stair_mid_landing_size(self) -> float:
        return self.stairs.mid_landing_size

    @property
    def stair_riser_height(self) -> float:
        return self.stairs.riser_height

    @property
    def stair_tread_depth(self) -> float:
        return self.stairs.tread_depth

    @property
    def stair_min_free_area(self) -> float:
        return self.stairs.min_free_area

    @property
    def stair_door_clearance(self) -> float:
        return self.stairs.door_clearance

    @property
    def stair_window_clearance(self) -> float:
        return self.stairs.window_clearance

    @property
    def roof_railing_enabled(self) -> bool:
        return self.roof_railing.enabled

    @property
    def railing_height(self) -> float:
        return self.roof_railing.height

    @property
    def railing_post_size(self) -> float:
        return self.roof_railing.post_size

    @property
    def railing_rail_thickness(self) -> float:
        return self.roof_railing.rail_thickness

    @property
    def railing_rail_count(self) -> int:
        return self.roof_railing.rail_count


def settings_from_props(props) -> GenerationSettings:
    return GenerationSettings(
        general=GeneralSettings(
            delete_old=bool(props.delete_old),
            randomize_seed_each_build=bool(props.randomize_seed_each_build),
            collection_name=str(props.collection_name),
            seed=int(props.seed),
            text_size=float(props.text_size),
        ),
        shape=ShapeSettings(
            target_room_count=int(props.target_room_count),
            min_room_side_m=float(props.min_room_side_m),
            house_scale=float(props.house_scale),
            shape_mode=str(props.shape_mode),
        ),
        stories=StorySettings(
            story_count=int(props.story_count),
            layout_mode=str(props.story_layout_mode),
            vertical_profile_mode=VerticalProfileMode(str(props.vertical_profile_mode)).value,
            profile_strength=min(1.0, max(0.0, float(props.vertical_profile_strength))),
        ),
        floor_bands=FloorBandSettings(
            enabled=bool(props.floor_bands_enabled),
            depth=max(0.25, quantize_025(float(props.floor_band_depth))),
            height=max(0.25, quantize_025(float(props.floor_band_height))),
        ),
        roof_border=RoofBorderSettings(
            enabled=bool(props.roof_border_enabled),
            depth=max(0.25, quantize_025(float(props.roof_border_depth))),
            height=max(0.25, quantize_025(float(props.roof_border_height))),
        ),
        walls=WallSettings(
            outer_walls_enabled=bool(props.outer_walls_enabled),
            wall_height=max(0.25, quantize_025(float(props.wall_height))),
            wall_module_width=max(0.25, quantize_025(float(props.wall_module_width))),
            wall_thickness=max(0.25, quantize_025(float(props.wall_thickness))),
        ),
        atlas=AtlasSettings(
            enabled=bool(props.atlas_enabled),
            manifest_path=str(props.atlas_manifest_path),
            image_path=str(props.atlas_image_path),
            include_interior_walls=bool(props.atlas_include_interior_walls),
            random_pick=bool(props.atlas_random_pick),
        ),
        decals=DecalSettings(
            enabled=bool(props.decals_enabled),
            manifest_path=str(props.decal_manifest_path),
            image_path=str(props.decal_image_path),
            density=min(1.0, max(0.0, float(props.decal_density))),
            enable_streaks=bool(props.decal_enable_streaks),
        ),
        doors=DoorSettings(
            enabled=bool(props.doors_enabled),
            interior_width=max(0.25, quantize_025(float(props.interior_door_width))),
            interior_height=max(0.25, quantize_025(float(props.interior_door_height))),
            entry_width=max(0.25, quantize_025(float(props.entry_door_width))),
            entry_height=max(0.25, quantize_025(float(props.entry_door_height))),
            leaf_thickness=max(0.1, round(float(props.door_leaf_thickness) / 0.05) * 0.05),
            min_edge_offset=max(0.25, quantize_025(float(props.door_min_edge_offset))),
            min_corner_offset=max(0.25, quantize_025(float(props.door_min_corner_offset))),
        ),
        windows=WindowSettings(
            enabled=bool(props.windows_enabled),
            width=max(0.25, quantize_025(float(props.window_width))),
            height=max(0.25, quantize_025(float(props.window_height))),
            sill_height=max(0.25, quantize_025(float(props.window_sill_height))),
            min_corner_offset=max(0.25, quantize_025(float(props.window_min_corner_offset))),
            min_door_offset=max(0.25, quantize_025(float(props.window_min_door_offset))),
            min_partition_offset=max(0.25, quantize_025(float(props.window_min_partition_offset))),
            min_edge_offset=max(0.25, quantize_025(float(props.window_min_edge_offset))),
        ),
        stairs=StairSettings(
            enabled=bool(props.stairs_enabled),
            mode=StairMode(str(props.stair_mode)),
            width=max(0.25, quantize_025(float(props.stair_width))),
            landing_size=max(0.25, quantize_025(float(props.stair_landing_size))),
            mid_landing_size=max(0.25, quantize_025(float(props.stair_mid_landing_size))),
            riser_height=max(0.05, round(float(props.stair_riser_height) / 0.01) * 0.01),
            tread_depth=max(0.25, quantize_025(float(props.stair_tread_depth))),
            min_free_area=max(1.0, quantize_025(float(props.stair_min_free_area))),
            door_clearance=max(0.25, quantize_025(float(props.stair_door_clearance))),
            window_clearance=max(0.25, quantize_025(float(props.stair_window_clearance))),
        ),
        roof_railing=RoofRailingSettings(
            enabled=bool(props.roof_railing_enabled),
            height=max(0.25, quantize_025(float(props.railing_height))),
            post_size=max(0.02, round(float(props.railing_post_size) / 0.01) * 0.01),
            rail_thickness=max(0.01, round(float(props.railing_rail_thickness) / 0.01) * 0.01),
            rail_count=max(1, int(props.railing_rail_count)),
        ),
    )

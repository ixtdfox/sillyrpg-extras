import bpy

from .batching import MeshBatcher
from .building_assembler import BuildingAssembler
from .building_shape import BuildingShape
from .building_style import BuildingStyle
from .utils import (
    ASSET_HELPER_COLLECTION_NAME,
    COLLECTION_NAME,
    HANDLE_NAME,
    ROOT_NAME,
    clear_generated_objects,
    ensure_child_collection,
    ensure_collection,
    ensure_empty,
    ensure_materials,
)


class BuildingGenerator:
    _cached_shape = None
    _cached_shape_sig = None

    def __init__(self):
        self.col = ensure_collection(COLLECTION_NAME)
        self.asset_helper_col = ensure_child_collection(self.col, ASSET_HELPER_COLLECTION_NAME, hidden=True)
        self.mats = ensure_materials()
        self.batch = MeshBatcher()
        self.fast_mode = False
        self.detail_scale = 1.0

    def get_state(self):
        s = bpy.context.scene.pb_settings
        root = ensure_empty(ROOT_NAME, 'ARROWS', (0, 0, 0))
        handle = ensure_empty(HANDLE_NAME, 'CUBE', (s.width_m, s.depth_m, 0))
        return s, root, handle

    def clear(self):
        clear_generated_objects(self.col)

    @staticmethod
    def shape_signature(settings, fast_mode):
        return (
            round(settings.width_m, 4), round(settings.depth_m, 4),
            int(settings.floors), int(settings.room_count), int(settings.seed),
            round(settings.tile_size, 4), round(settings.floor_height, 4),
            round(settings.slab_thickness, 4), round(settings.stairs_width, 4),
            round(settings.stair_opening_margin, 4), bool(fast_mode),
        )

    def resolve_shape(self, settings, rebuild_shape):
        sig = self.shape_signature(settings, self.fast_mode)
        if rebuild_shape or BuildingGenerator._cached_shape is None or BuildingGenerator._cached_shape_sig != sig:
            shape = BuildingShape.from_settings(settings, self.fast_mode)
            BuildingGenerator._cached_shape = shape
            BuildingGenerator._cached_shape_sig = sig
            return shape
        return BuildingGenerator._cached_shape

    def build(self, quality="full", rebuild_shape=True):
        settings, root, handle = self.get_state()
        self.fast_mode = (quality == "preview")
        self.detail_scale = settings.preview_detail_scale if self.fast_mode else 1.0
        self.batch = MeshBatcher()

        handle.location.x = root.location.x + settings.width_m
        handle.location.y = root.location.y + settings.depth_m
        handle.location.z = root.location.z

        self.clear()

        shape = self.resolve_shape(settings, rebuild_shape)
        style = BuildingStyle.from_settings(settings, self.fast_mode)
        assembler = BuildingAssembler(self.batch, self.col, self.asset_helper_col)
        assembler.assemble(settings, shape, style, root)

        self.batch.build_objects(self.col, self.mats, smooth=not self.fast_mode)

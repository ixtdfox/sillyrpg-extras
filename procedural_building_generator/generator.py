import bpy

from .batching import MeshBatcher
from .building_assembler import BuildingAssembler
from .building_shape import BuildingShape
from .building_style import BuildingStyle
from .utils import (
    COLLECTION_NAME,
    HANDLE_NAME,
    ROOT_NAME,
    clear_generated_objects,
    ensure_collection,
    ensure_empty,
    ensure_materials,
)


class BuildingGenerator:
    def __init__(self):
        self.col = ensure_collection(COLLECTION_NAME)
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

    def build(self, quality="full"):
        settings, root, handle = self.get_state()
        self.fast_mode = (quality == "preview")
        self.detail_scale = settings.preview_detail_scale if self.fast_mode else 1.0
        self.batch = MeshBatcher()

        handle.location.x = root.location.x + settings.width_m
        handle.location.y = root.location.y + settings.depth_m
        handle.location.z = root.location.z

        self.clear()

        shape = BuildingShape.from_settings(settings, self.fast_mode)
        style = BuildingStyle.from_settings(settings, self.fast_mode)
        assembler = BuildingAssembler(self.batch)
        assembler.assemble(settings, shape, style, root)

        self.batch.build_objects(self.col, self.mats, smooth=not self.fast_mode)

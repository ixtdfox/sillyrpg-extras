from __future__ import annotations

import bpy

from ..common.utils import ensure_collection, link_object
from ..game_grid import WORLD_TILE_SIZE_M
from ..grid import RectCell, create_game_rect_layout

PREVIEW_COLLECTION_NAME = "Game_Rect_Grid_Preview_DO_NOT_EXPORT"
PREVIEW_OBJECT_NAME = "GameRectGridPreview"
PREVIEW_MATERIAL_NAME = "GameRectGridPreview_Cyan"


class GameRectGridPreviewService:
    def refresh_preview(self, scene: bpy.types.Scene, props) -> bpy.types.Object | None:
        # This preview is drawn in Blender XY (visual authoring space).
        # Exported game navigation uses GameGridCoordinateMapper to convert XY -> Babylon XZ.
        self.remove_preview(scene)
        if not bool(getattr(props, "game_rect_grid_preview_enabled", False)):
            return None

        size_tiles = int(getattr(props, "game_rect_grid_preview_radius_tiles", 24))
        y_offset = float(getattr(props, "game_rect_grid_preview_y_offset", 0.03))
        half = max(1, size_tiles // 2)
        layout = create_game_rect_layout()

        verts: list[tuple[float, float, float]] = []
        edges: list[tuple[int, int]] = []
        for x in range(-half, half + 1):
            for y in range(-half, half + 1):
                min_x, min_y, max_x, max_y = layout.cell_bounds(RectCell(x, y))
                base = len(verts)
                verts.extend([
                    (min_x, min_y, y_offset),
                    (max_x, min_y, y_offset),
                    (max_x, max_y, y_offset),
                    (min_x, max_y, y_offset),
                ])
                edges.extend([(base, base + 1), (base + 1, base + 2), (base + 2, base + 3), (base + 3, base)])

        mesh = bpy.data.meshes.new(f"{PREVIEW_OBJECT_NAME}Mesh")
        mesh.from_pydata(verts, edges, [])
        mesh.update()
        obj = bpy.data.objects.new(PREVIEW_OBJECT_NAME, mesh)
        obj["game_rect_grid_preview"] = True
        obj["export_exclude"] = True
        obj["do_not_export"] = True
        obj["grid_contract"] = "sillyrpg.grid_navigation.v3"
        obj["grid_type"] = "rect"
        obj["tile_size_m"] = float(WORLD_TILE_SIZE_M)
        obj["preview_space"] = "blender_xy"
        obj.hide_render = True

        collection = ensure_collection(scene, PREVIEW_COLLECTION_NAME, delete_old=False)
        link_object(collection, obj)
        obj.data.materials.append(self._material())
        return obj

    def remove_preview(self, scene: bpy.types.Scene) -> None:
        collection = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
        if collection is None:
            return
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if len(collection.objects) == 0:
            for parent in bpy.data.collections:
                if collection.name in parent.children:
                    parent.children.unlink(collection)
            if collection.name in scene.collection.children:
                scene.collection.children.unlink(collection)
            bpy.data.collections.remove(collection)

    def _material(self) -> bpy.types.Material:
        material = bpy.data.materials.get(PREVIEW_MATERIAL_NAME)
        if material is None:
            material = bpy.data.materials.new(PREVIEW_MATERIAL_NAME)
            material.diffuse_color = (0.1, 0.85, 1.0, 0.45)
        return material

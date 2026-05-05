from __future__ import annotations

import bpy


class GeneratedBuildingCleaner:
    """Hard-cleans one generated building collection without touching preview debug collections."""

    PREVIEW_COLLECTION_NAMES = {"Game_Rect_Grid_Preview_DO_NOT_EXPORT", "__GameRectGridPreview"}

    def clean_building_collection(self, scene: bpy.types.Scene, collection_name: str) -> bpy.types.Collection:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
            scene.collection.children.link(collection)
            return collection

        self._clear_collection(collection)
        if collection not in scene.collection.children[:]:
            scene.collection.children.link(collection)
        collection.hide_viewport = False
        collection.hide_render = False
        return collection

    def _clear_collection(self, collection: bpy.types.Collection) -> None:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for child in list(collection.children):
            if child.name in self.PREVIEW_COLLECTION_NAMES:
                continue
            self._clear_collection(child)
            bpy.data.collections.remove(child)

from __future__ import annotations

# Layout/asset placement logic adapted from local MIT project /home/tony/pets/bpy-city.

from pathlib import Path

import bpy


def normalize_bpy_city_assets_root(path: str) -> Path:
    raw = str(path).strip()
    resolved = Path(bpy.path.abspath(raw or ".")).expanduser()
    if (resolved / "assets").exists():
        return resolved / "assets"
    return resolved


class ProceduralCityAssetLibrary:
    def __init__(self, assets_root: str, hidden_collection: bpy.types.Collection):
        self.requested_root = str(assets_root)
        self.assets_root = normalize_bpy_city_assets_root(assets_root)
        self.hidden_collection = hidden_collection
        self.loaded_objects: dict[str, bpy.types.Object] = {}
        self.asset_counts: dict[str, int] = {}
        self.warnings: list[str] = []
        self.import_failures: dict[str, str] = {}
        self.catalog = self.scan_assets()
        self.asset_counts = {key: len(value) for key, value in self.catalog.items()}

    def scan_assets(self) -> dict[str, list[str]]:
        categories = {
            "cars": [],
            "trucks": [],
            "special_vehicles": [],
            "trees": [],
            "trees_tropical": [],
            "bushes": [],
            "flowers": [],
            "traffic_lights": [],
            "road_props": [],
            "benches": [],
            "street_furniture": [],
        }
        if not self.assets_root.exists():
            self.warnings.append(f"Assets root not found: {self.assets_root}")
            return categories

        patterns = [
            ("cars", self.assets_root / "cars" / "Models" / "GLB format"),
            ("nature", self.assets_root / "nature" / "Models" / "GLTF format"),
            ("furniture", self.assets_root / "furniture" / "Models" / "GLTF format"),
            ("roads", self.assets_root / "roads" / "Models" / "GLB format"),
        ]
        for kind, directory in patterns:
            if not directory.exists():
                continue
            for asset in sorted(list(directory.glob("*.glb")) + list(directory.glob("*.gltf"))):
                name = asset.stem.lower()
                if kind == "cars":
                    if any(flag in name for flag in ("ambulance", "firetruck", "police", "tractor")):
                        categories["special_vehicles"].append(str(asset))
                    elif any(flag in name for flag in ("truck", "delivery", "garbage")):
                        categories["trucks"].append(str(asset))
                    elif not any(flag in name for flag in ("debris", "wheel", "cone", "box")):
                        categories["cars"].append(str(asset))
                elif kind == "nature":
                    if "tree" in name:
                        if "palm" in name:
                            categories["trees_tropical"].append(str(asset))
                        else:
                            categories["trees"].append(str(asset))
                    elif "bush" in name or "plant_bush" in name:
                        categories["bushes"].append(str(asset))
                    elif "flower" in name:
                        categories["flowers"].append(str(asset))
                elif kind == "furniture":
                    if "bench" in name:
                        categories["benches"].append(str(asset))
                    elif any(flag in name for flag in ("trash", "potted", "plant", "lamp", "seat")):
                        categories["street_furniture"].append(str(asset))
                elif kind == "roads":
                    if "light-" in name or "traffic" in name:
                        categories["traffic_lights"].append(str(asset))
                    elif any(flag in name for flag in ("sign", "construction", "barrier")):
                        categories["road_props"].append(str(asset))
        return categories

    def has_assets(self) -> bool:
        return any(values for values in self.catalog.values())

    def load_asset(self, filepath: str) -> bpy.types.Object | None:
        if filepath in self.loaded_objects:
            return self.loaded_objects[filepath]
        filepath_obj = Path(filepath)
        if not filepath_obj.exists():
            self.import_failures[filepath] = "file_not_found"
            return None
        existing = {obj.as_pointer() for obj in bpy.data.objects}
        existing_collections = {collection.as_pointer() for collection in bpy.data.collections}
        try:
            bpy.ops.import_scene.gltf(filepath=str(filepath_obj))
        except Exception as exc:
            self.import_failures[filepath] = str(exc)
            self.warnings.append(f"Asset import failed: {filepath_obj.name}: {exc}")
            return None
        imported_all = [obj for obj in bpy.data.objects if obj.as_pointer() not in existing]
        imported_meshes = [obj for obj in imported_all if obj.type == "MESH"]
        if not imported_meshes:
            for obj in imported_all:
                bpy.data.objects.remove(obj, do_unlink=True)
            self.import_failures[filepath] = "no_mesh_objects"
            self.warnings.append(f"Asset import produced no mesh: {filepath_obj.name}")
            return None
        main_obj = imported_meshes[0]
        if len(imported_meshes) > 1:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in imported_meshes:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = main_obj
            bpy.ops.object.join()
            main_obj = bpy.context.view_layer.objects.active
        for obj in imported_all:
            if obj == main_obj:
                continue
            bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(main_obj.users_collection):
            collection.objects.unlink(main_obj)
        self.hidden_collection.objects.link(main_obj)
        main_obj.hide_viewport = True
        main_obj.hide_render = True
        main_obj.name = f"Asset_{filepath_obj.stem}"
        asset_id = _asset_id_from_path(filepath_obj)
        main_obj["generated_by"] = "procedural_city"
        main_obj["asset_id"] = asset_id
        main_obj["instance_group"] = asset_id
        main_obj["is_linked_duplicate"] = False
        for collection in list(bpy.data.collections):
            if collection.as_pointer() in existing_collections or collection == self.hidden_collection:
                continue
            if not collection.objects[:] and not collection.children[:]:
                bpy.data.collections.remove(collection)
        self.loaded_objects[filepath] = main_obj
        return main_obj

    def choose_asset(self, category_names: tuple[str, ...], rng) -> str | None:
        candidates: list[str] = []
        for category_name in category_names:
            candidates.extend(self.catalog.get(category_name, []))
        if not candidates:
            return None
        return rng.choice(candidates)

    def create_instance(
        self,
        *,
        filepath: str,
        collection: bpy.types.Collection,
        location: tuple[float, float, float],
        rotation_z: float = 0.0,
        scale: float = 1.0,
        prop_type: str = "",
    ) -> bpy.types.Object | None:
        original = self.load_asset(filepath)
        if original is None:
            return None
        instance = original.copy()
        instance.data = original.data
        instance.location = location
        instance.rotation_euler = (0.0, 0.0, rotation_z)
        instance.scale = (scale, scale, scale)
        asset_id = str(original.get("asset_id", _asset_id_from_path(Path(filepath))))
        instance["generated_by"] = "procedural_city"
        instance["asset_id"] = asset_id
        instance["instance_group"] = asset_id
        instance["is_linked_duplicate"] = True
        if prop_type:
            instance["prop_type"] = prop_type
        collection.objects.link(instance)
        return instance


def _asset_id_from_path(path: Path) -> str:
    return path.stem.strip().lower().replace(" ", "_")

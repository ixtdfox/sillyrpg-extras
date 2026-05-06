from __future__ import annotations

import bpy

from ..common.utils import ensure_child_collection, ensure_collection, ensure_collection_linked


def ensure_terrain_scene_collections(scene: bpy.types.Scene, root_name: str, *, delete_old: bool) -> dict[str, bpy.types.Collection]:
    root = ensure_collection(scene, root_name, delete_old=delete_old)
    terrain = ensure_child_collection(root, "01_Terrain")
    buildings = ensure_child_collection(root, "buildings")
    _migrate_old_buildings_collection(root, buildings)
    props = ensure_child_collection(root, "03_Props")
    asset_library_hidden = ensure_child_collection(root, "04_AssetLibrary_Hidden")
    metadata = ensure_child_collection(root, "99_Metadata")
    debug = ensure_child_collection(root, "00_Debug")
    return {
        "root": root,
        "terrain": terrain,
        "buildings": buildings,
        "props": props,
        "asset_library_hidden": asset_library_hidden,
        "metadata": metadata,
        "debug": debug,
        "ground": ensure_child_collection(terrain, "Ground"),
        "roads": ensure_child_collection(terrain, "Roads"),
        "intersections": ensure_child_collection(terrain, "Intersections"),
        "sidewalks": ensure_child_collection(terrain, "Sidewalks"),
        "curbs": ensure_child_collection(terrain, "Curbs"),
        "grass": ensure_child_collection(terrain, "Grass"),
        "crosswalks": ensure_child_collection(terrain, "Crosswalks"),
        "lane_marks": ensure_child_collection(terrain, "LaneMarks"),
        "cars": ensure_child_collection(props, "Cars"),
        "trees": ensure_child_collection(props, "Trees"),
        "traffic_lights": ensure_child_collection(props, "TrafficLights"),
        "street_furniture": ensure_child_collection(props, "StreetFurniture"),
    }


def relink_collection(parent: bpy.types.Collection, child: bpy.types.Collection, scene: bpy.types.Scene | None = None) -> None:
    ensure_collection_linked(parent, child)
    for existing_parent in list(bpy.data.collections):
        if existing_parent == parent:
            continue
        if child not in existing_parent.children[:]:
            continue
        if existing_parent.name == "02_Buildings" or (scene is not None and existing_parent == scene.collection):
            existing_parent.children.unlink(child)
    if scene is not None and child in scene.collection.children[:]:
        scene.collection.children.unlink(child)


def delete_collection_tree(collection: bpy.types.Collection) -> None:
    for child in list(collection.children):
        delete_collection_tree(child)
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def iter_collection_objects_recursive(collection: bpy.types.Collection):
    for obj in collection.objects:
        yield obj
    for child in collection.children:
        yield from iter_collection_objects_recursive(child)


def validate_generated_buildings_parent(scene: bpy.types.Scene, root: bpy.types.Collection, buildings: bpy.types.Collection) -> None:
    if buildings.name != "buildings":
        print(f"[terrain] WARNING: expected buildings collection name 'buildings', got '{buildings.name}'")
    stray_scene_children = []
    for child in scene.collection.children:
        if child == root:
            continue
        if _is_generated_building_collection(child, root.name):
            stray_scene_children.append(child.name)
    if stray_scene_children:
        print(f"[terrain] WARNING: generated building collections left at scene root: {stray_scene_children}")
    old = root.children.get("02_Buildings")
    if old is not None and old.children[:]:
        print(f"[terrain] WARNING: legacy 02_Buildings still has children: {[child.name for child in old.children]}")
    print(f"[terrain] Generated buildings parent: {root.name}/{buildings.name}")


def _migrate_old_buildings_collection(root: bpy.types.Collection, buildings: bpy.types.Collection) -> None:
    old = root.children.get("02_Buildings")
    if old is None or old == buildings:
        return
    for child in list(old.children):
        if not _is_generated_building_collection(child, root.name):
            continue
        ensure_collection_linked(buildings, child)
        old.children.unlink(child)
    for obj in list(old.objects):
        if not _is_generated_building_object(obj, root.name):
            continue
        if obj not in buildings.objects[:]:
            buildings.objects.link(obj)
        old.objects.unlink(obj)
    if not old.children[:] and not old.objects[:]:
        root.children.unlink(old)
        bpy.data.collections.remove(old)


def _is_generated_building_collection(collection: bpy.types.Collection, root_name: str) -> bool:
    if str(collection.get("terrain_scene_id", "")) == root_name:
        return True
    if str(collection.get("terrain_zone", "")) == "building":
        return True
    if str(collection.get("terrain_generated_by", "")) in {"terrain_scene_generator", "procedural_city_generator"}:
        return True
    for obj in iter_collection_objects_recursive(collection):
        if _is_generated_building_object(obj, root_name):
            return True
    return False


def _is_generated_building_object(obj: bpy.types.Object, root_name: str) -> bool:
    return (
        str(obj.get("terrain_scene_id", "")) == root_name
        or str(obj.get("terrain_zone", "")) == "building"
        or str(obj.get("terrain_generated_by", "")) in {"terrain_scene_generator", "procedural_city_generator"}
    )

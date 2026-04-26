from __future__ import annotations

from pathlib import Path

import bpy

from . import atlas_manifest, utils


TRANSPARENT_REGIONS = {"chainlink", "glass_light", "lamp_glow"}
EMISSIVE_REGIONS = {"lamp_glow"}


def _load_or_create_image(image_path: str):
    abs_path = atlas_manifest._abs_path(image_path)
    if abs_path and Path(abs_path).exists():
        for image in bpy.data.images:
            if bpy.path.abspath(image.filepath) == abs_path:
                return image
        try:
            return bpy.data.images.load(abs_path)
        except Exception:
            pass
    image = bpy.data.images.get("RY_Atlas_Placeholder")
    if image is None:
        image = bpy.data.images.new("RY_Atlas_Placeholder", width=2, height=2, alpha=True)
        image.generated_color = (0.75, 0.75, 0.78, 1.0)
    return image


def _ensure_material(name: str, image, *, transparent: bool = False, emissive: bool = False):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    node_tree = material.node_tree
    for node in list(node_tree.nodes):
        node_tree.nodes.remove(node)

    output = node_tree.nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (420, 0)
    texture = node_tree.nodes.new(type="ShaderNodeTexImage")
    texture.location = (-320, 0)
    texture.image = image

    if emissive:
        emission = node_tree.nodes.new(type="ShaderNodeEmission")
        emission.location = (120, 120)
        emission.inputs["Strength"].default_value = 1.8
        bsdf = node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (120, -80)
        mix = node_tree.nodes.new(type="ShaderNodeAddShader")
        mix.location = (280, 0)
        node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
        node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
        node_tree.links.new(emission.outputs["Emission"], mix.inputs[0])
        node_tree.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
        node_tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    else:
        bsdf = node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (120, 0)
        node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
        node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    material.blend_method = "HASHED" if transparent else "OPAQUE"
    material.shadow_method = "HASHED" if transparent else "OPAQUE"
    material.use_backface_culling = False
    return material


def ensure_material_for_region(runtime: dict, region_name: str):
    image = _load_or_create_image(runtime.get("image_path", ""))
    transparent = region_name in TRANSPARENT_REGIONS
    emissive = region_name in EMISSIVE_REGIONS
    suffix = "Emissive" if emissive else "Transparent" if transparent else "Opaque"
    return _ensure_material(f"RY_Atlas_{suffix}", image, transparent=transparent, emissive=emissive)


def assign_uv_region(obj: bpy.types.Object, runtime: dict, region_name: str) -> None:
    region = runtime.get("regions", {}).get(region_name)
    if obj.type != "MESH" or region is None:
        return

    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="AtlasUV")
    uv_layer = mesh.uv_layers.active.data

    atlas_w = float(runtime.get("atlas_width", 1024))
    atlas_h = float(runtime.get("atlas_height", 1024))
    min_u = region["x"] / atlas_w
    max_u = (region["x"] + region["w"]) / atlas_w
    min_v = 1.0 - (region["y"] + region["h"]) / atlas_h
    max_v = 1.0 - region["y"] / atlas_h

    def remap(value, source_min, source_max, target_min, target_max):
        if abs(source_max - source_min) < 1e-8:
            return (target_min + target_max) * 0.5
        factor = (value - source_min) / (source_max - source_min)
        return target_min + (target_max - target_min) * factor

    for polygon in mesh.polygons:
        nx = abs(polygon.normal.x)
        ny = abs(polygon.normal.y)
        nz = abs(polygon.normal.z)
        if nz >= nx and nz >= ny:
            primary_axis, secondary_axis = "x", "y"
        elif nx >= ny:
            primary_axis, secondary_axis = "y", "z"
        else:
            primary_axis, secondary_axis = "x", "z"

        polygon_vertices = [mesh.vertices[mesh.loops[loop_index].vertex_index].co for loop_index in polygon.loop_indices]
        primary_values = [getattr(vertex, primary_axis) for vertex in polygon_vertices]
        secondary_values = [getattr(vertex, secondary_axis) for vertex in polygon_vertices]
        min_primary, max_primary = min(primary_values), max(primary_values)
        min_secondary, max_secondary = min(secondary_values), max(secondary_values)
        for loop_index in polygon.loop_indices:
            vert = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            u = remap(getattr(vert, primary_axis), min_primary, max_primary, min_u, max_u)
            v = remap(getattr(vert, secondary_axis), min_secondary, max_secondary, min_v, max_v)
            uv_layer[loop_index].uv = (u, v)


def apply_material_and_uv(obj: bpy.types.Object, runtime: dict, region_name: str) -> None:
    if obj.type != "MESH":
        return
    material = ensure_material_for_region(runtime, region_name)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    assign_uv_region(obj, runtime, region_name)
    obj["atlas_region_name"] = region_name


def update_collection_uvs(collection: bpy.types.Collection, runtime: dict) -> None:
    for obj in utils.iter_collection_objects_recursive(collection):
        if obj.type != "MESH":
            continue
        if not obj.get("procedural_rooftop_yard"):
            continue
        region_name = str(obj.get("atlas_region_name", ""))
        if region_name:
            apply_material_and_uv(obj, runtime, region_name)


classes = ()


def register():
    pass


def unregister():
    pass

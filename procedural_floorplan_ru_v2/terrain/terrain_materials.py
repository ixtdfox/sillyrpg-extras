from __future__ import annotations

from pathlib import Path

import bpy


def ensure_terrain_material(name: str, base_color: tuple[float, float, float, float], texture_path: str = "") -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    node_tree = material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (400, 0)
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (120, 0)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = 0.9
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    resolved_texture_path = Path(bpy.path.abspath(texture_path)).expanduser() if texture_path else None
    if resolved_texture_path and resolved_texture_path.exists():
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        tex_coord.location = (-700, 0)
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.location = (-500, 0)
        mapping.inputs["Scale"].default_value[0] = 1.0
        mapping.inputs["Scale"].default_value[1] = 1.0
        image_node = nodes.new(type="ShaderNodeTexImage")
        image_node.location = (-250, 0)
        image_node.image = bpy.data.images.load(str(resolved_texture_path), check_existing=True)
        image_node.interpolation = "Smart"
        links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])

    return material

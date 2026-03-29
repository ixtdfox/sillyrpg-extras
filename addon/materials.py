"""Material setup with lightweight procedural fallback nodes."""

from __future__ import annotations

import bpy


def _get_or_create_material(name: str, base_color):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True

    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    ao_mix = nt.nodes.new("ShaderNodeMixRGB")

    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.58
    noise.inputs["Scale"].default_value = 38.0
    bump.inputs["Strength"].default_value = 0.08
    ao_mix.blend_type = "MULTIPLY"
    ao_mix.inputs["Fac"].default_value = 0.2

    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def apply_materials(objects, params):
    detail = params.get("detail", 0.5)
    dominant = _get_or_create_material("RPG_Dominant", (0.82, 0.83, 0.84))
    neutral = _get_or_create_material("RPG_Neutral", (0.55, 0.56, 0.58))
    service = _get_or_create_material("RPG_Service", (0.30, 0.31, 0.33))
    glass = _get_or_create_material("RPG_Glass", (0.22, 0.32, 0.38))
    glass.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = max(0.03, 0.2 - detail * 0.1)

    for obj in objects:
        name = obj.name.lower()
        if "window" in name or "glass" in name:
            mat = glass
        elif "service" in name or "hvac" in name:
            mat = service
        elif "entrance" in name or "parapet" in name:
            mat = neutral
        else:
            mat = dominant

        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(mat)

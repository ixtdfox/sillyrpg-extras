import bpy

GENERATOR_TAG = "PROC_BUILDING_ADDON"
COLLECTION_NAME = "ProcBuilding_Runtime"
ASSET_HELPER_COLLECTION_NAME = "ProcBuilding_FacadeAssets"
ROOT_NAME = "BuildingRoot"
HANDLE_NAME = "BuildingSizeHandle"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def snap_to_step(v, step):
    return round(v / step) * step


def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        return col
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def ensure_child_collection(parent, name, hidden=False):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if parent.children.get(col.name) is None:
        parent.children.link(col)
    if hidden:
        col.hide_viewport = True
        col.hide_render = True
    return col


def clear_generated_objects(col):
    for obj in list(col.objects):
        if obj.get("generated_by") == GENERATOR_TAG:
            bpy.data.objects.remove(obj, do_unlink=True)


def ensure_empty(name, empty_type='PLAIN_AXES', location=(0, 0, 0)):
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = empty_type
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = empty_type
    return obj


def world_box(sx, sy, sz, center):
    cx, cy, cz = center
    x = sx * 0.5
    y = sy * 0.5
    z = sz * 0.5
    verts = [
        (cx - x, cy - y, cz - z), (cx + x, cy - y, cz - z),
        (cx + x, cy + y, cz - z), (cx - x, cy + y, cz - z),
        (cx - x, cy - y, cz + z), (cx + x, cy - y, cz + z),
        (cx + x, cy + y, cz + z), (cx - x, cy + y, cz + z),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7),
        (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    return verts, faces


def clear_nodes(mat):
    for n in list(mat.node_tree.nodes):
        mat.node_tree.nodes.remove(n)


def get_or_create_material(name, kind):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_fake_user = True
    clear_nodes(mat)
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)

    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-1300, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-1120, 0)
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])

    coarse_noise = nodes.new("ShaderNodeTexNoise")
    coarse_noise.name = "PB_CoarseNoise"
    coarse_noise.location = (-920, 120)
    coarse_noise.inputs["Scale"].default_value = 2.4
    coarse_noise.inputs["Detail"].default_value = 3.0

    fine_noise = nodes.new("ShaderNodeTexNoise")
    fine_noise.name = "PB_FineNoise"
    fine_noise.location = (-920, -60)
    fine_noise.inputs["Scale"].default_value = 24.0
    fine_noise.inputs["Detail"].default_value = 6.0
    fine_noise.inputs["Roughness"].default_value = 0.5

    rough_mix = nodes.new("ShaderNodeMath")
    rough_mix.operation = 'MULTIPLY'
    rough_mix.location = (-660, 20)
    rough_mix.inputs[1].default_value = 0.2

    bump = nodes.new("ShaderNodeBump")
    bump.location = (180, -180)
    bump.inputs["Strength"].default_value = 0.025

    links.new(mapping.outputs["Vector"], coarse_noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], fine_noise.inputs["Vector"])
    links.new(fine_noise.outputs["Fac"], rough_mix.inputs[0])
    links.new(fine_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if kind == "wall":
        color_mix = nodes.new("ShaderNodeMixRGB")
        color_mix.name = "PB_WallColorMix"
        color_mix.location = (-300, 160)
        color_mix.blend_type = 'MIX'
        color_mix.inputs["Fac"].default_value = 0.13
        color_mix.inputs["Color1"].default_value = (0.91, 0.90, 0.86, 1.0)
        color_mix.inputs["Color2"].default_value = (0.86, 0.86, 0.83, 1.0)
        links.new(coarse_noise.outputs["Fac"], color_mix.inputs["Fac"])

        seam_wave = nodes.new("ShaderNodeTexWave")
        seam_wave.name = "PB_WallSeamWave"
        seam_wave.location = (-670, 250)
        seam_wave.wave_type = 'BANDS'
        seam_wave.bands_direction = 'Z'
        seam_wave.inputs["Scale"].default_value = 2.1
        seam_wave.inputs["Distortion"].default_value = 1.5
        links.new(mapping.outputs["Vector"], seam_wave.inputs["Vector"])

        seam_contrast = nodes.new("ShaderNodeMath")
        seam_contrast.name = "PB_WallSeamStrength"
        seam_contrast.operation = 'MULTIPLY'
        seam_contrast.location = (-420, 260)
        seam_contrast.inputs[1].default_value = 0.015
        links.new(seam_wave.outputs["Color"], seam_contrast.inputs[0])

        geometry = nodes.new("ShaderNodeNewGeometry")
        geometry.location = (-920, -300)
        separate = nodes.new("ShaderNodeSeparateXYZ")
        separate.location = (-720, -300)
        map_range = nodes.new("ShaderNodeMapRange")
        map_range.name = "PB_WallDirtMap"
        map_range.location = (-500, -300)
        map_range.inputs["From Min"].default_value = 0.0
        map_range.inputs["From Max"].default_value = 2.6
        map_range.inputs["To Min"].default_value = 1.0
        map_range.inputs["To Max"].default_value = 0.0
        map_range.clamp = True
        links.new(geometry.outputs["Position"], separate.inputs["Vector"])
        links.new(separate.outputs["Z"], map_range.inputs["Value"])

        dirt_mix = nodes.new("ShaderNodeMath")
        dirt_mix.name = "PB_WallDirtStrength"
        dirt_mix.operation = 'MULTIPLY'
        dirt_mix.location = (-280, -300)
        dirt_mix.inputs[1].default_value = 0.35
        links.new(map_range.outputs["Result"], dirt_mix.inputs[0])

        dirt_color = nodes.new("ShaderNodeMixRGB")
        dirt_color.name = "PB_WallDirtColor"
        dirt_color.location = (-40, 80)
        dirt_color.blend_type = 'MULTIPLY'
        dirt_color.inputs["Color2"].default_value = (0.88, 0.86, 0.84, 1.0)
        links.new(dirt_mix.outputs["Value"], dirt_color.inputs["Fac"])
        links.new(color_mix.outputs["Color"], dirt_color.inputs["Color1"])
        links.new(dirt_color.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(rough_mix.outputs["Value"], bsdf.inputs["Roughness"])
        links.new(seam_contrast.outputs["Value"], bump.inputs["Strength"])
        bsdf.inputs["Roughness"].default_value = 0.7
    elif kind == "trim":
        bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.90, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.44
        bump.inputs["Strength"].default_value = 0.01
    elif kind == "roof":
        roof_color = nodes.new("ShaderNodeMixRGB")
        roof_color.name = "PB_RoofColorMix"
        roof_color.location = (-240, 120)
        roof_color.inputs["Color1"].default_value = (0.21, 0.23, 0.25, 1.0)
        roof_color.inputs["Color2"].default_value = (0.15, 0.16, 0.18, 1.0)
        roof_color.inputs["Fac"].default_value = 0.22
        links.new(coarse_noise.outputs["Fac"], roof_color.inputs["Fac"])
        links.new(roof_color.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.87
        bump.inputs["Strength"].default_value = 0.02
    elif kind == "floor":
        bsdf.inputs["Base Color"].default_value = (0.74, 0.75, 0.76, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.82
        bump.inputs["Strength"].default_value = 0.04
    elif kind == "metal":
        bsdf.inputs["Base Color"].default_value = (0.56, 0.60, 0.64, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.9
        bsdf.inputs["Roughness"].default_value = 0.28
        bump.inputs["Strength"].default_value = 0.01
    elif kind == "glass":
        tint_mix = nodes.new("ShaderNodeMixRGB")
        tint_mix.name = "PB_GlassTintMix"
        tint_mix.location = (-220, 120)
        tint_mix.inputs["Fac"].default_value = 0.6
        tint_mix.inputs["Color1"].default_value = (0.53, 0.66, 0.74, 1.0)
        tint_mix.inputs["Color2"].default_value = (0.18, 0.24, 0.30, 1.0)

        fresnel = nodes.new("ShaderNodeLayerWeight")
        fresnel.location = (-450, -130)
        fresnel.inputs["Blend"].default_value = 0.23
        links.new(fresnel.outputs["Facing"], tint_mix.inputs["Fac"])
        links.new(tint_mix.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(rough_mix.outputs["Value"], bsdf.inputs["Roughness"])

        rough_mix.inputs[1].default_value = 0.08
        bsdf.inputs["Roughness"].default_value = 0.06
        bsdf.inputs["IOR"].default_value = 1.45
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 1.0
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = 1.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 0.13
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'HASHED'
        if hasattr(mat, "use_screen_refraction"):
            mat.use_screen_refraction = True
    elif kind == "accent":
        accent_mix = nodes.new("ShaderNodeMixRGB")
        accent_mix.name = "PB_AccentColorMix"
        accent_mix.location = (-200, 100)
        accent_mix.inputs["Fac"].default_value = 0.72
        accent_mix.inputs["Color1"].default_value = (0.46, 0.48, 0.50, 1.0)
        accent_mix.inputs["Color2"].default_value = (0.34, 0.52, 0.68, 1.0)
        links.new(accent_mix.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.39
    else:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6

    return mat


def ensure_materials():
    return {
        "wall": get_or_create_material("PB_Addon_Wall", "wall"),
        "trim": get_or_create_material("PB_Addon_Trim", "trim"),
        "roof": get_or_create_material("PB_Addon_Roof", "roof"),
        "floor": get_or_create_material("PB_Addon_Floor", "floor"),
        "metal": get_or_create_material("PB_Addon_Metal", "metal"),
        "glass": get_or_create_material("PB_Addon_Glass", "glass"),
        "accent": get_or_create_material("PB_Addon_Accent", "accent"),
    }


def _principled_node(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _node_by_name(material, name):
    if material is None or material.node_tree is None:
        return None
    return material.node_tree.nodes.get(name)


def apply_style_material_tuning(materials, style):
    wall_mat = materials.get("wall")
    trim_mat = materials.get("trim")
    roof_mat = materials.get("roof")
    accent_mat = materials.get("accent")
    glass_mat = materials.get("glass")

    wall = _principled_node(wall_mat)
    trim = _principled_node(trim_mat)
    roof = _principled_node(roof_mat)
    accent = _principled_node(accent_mat)
    glass = _principled_node(glass_mat)

    if wall:
        r, g, b = getattr(style, "wall_tint", (0.91, 0.9, 0.86))
        variation = getattr(style, "wall_tint_variation", 0.28)
        wall_mix = _node_by_name(wall_mat, "PB_WallColorMix")
        dirt_strength = _node_by_name(wall_mat, "PB_WallDirtStrength")
        seam_strength = _node_by_name(wall_mat, "PB_WallSeamStrength")
        if wall_mix:
            wall_mix.inputs["Color1"].default_value = (r, g, b, 1.0)
            wall_mix.inputs["Color2"].default_value = (clamp(r - 0.05, 0.0, 1.0), clamp(g - 0.05, 0.0, 1.0), clamp(b - 0.05, 0.0, 1.0), 1.0)
            wall_mix.inputs["Fac"].default_value = 0.08 + variation * 0.26
        else:
            wall.inputs["Base Color"].default_value = (r, g, b, 1.0)
        if dirt_strength:
            dirt_strength.inputs[1].default_value = 0.06 + getattr(style, "dirt_amount", 0.34) * 0.74
        if seam_strength:
            seam_strength.inputs[1].default_value = max(0.0, variation - 0.14) * 0.07
        wall.inputs["Roughness"].default_value = 0.62 + getattr(style, "dirt_amount", 0.34) * 0.18
    if trim:
        r, g, b = getattr(style, "trim_tint", (0.97, 0.97, 0.94))
        trim.inputs["Base Color"].default_value = (r, g, b, 1.0)
        trim.inputs["Roughness"].default_value = 0.38
    if roof:
        roof.inputs["Base Color"].default_value = (0.20, 0.22, 0.24, 1.0)
        roof.inputs["Roughness"].default_value = 0.82 + getattr(style, "roof_detail_density", 0.5) * 0.1
        roof_mix = _node_by_name(roof_mat, "PB_RoofColorMix")
        if roof_mix:
            roof_mix.inputs["Fac"].default_value = 0.12 + getattr(style, "roof_detail_density", 0.5) * 0.2
    if accent:
        r, g, b = getattr(style, "accent_tint", (0.34, 0.52, 0.68))
        accent_mix = _node_by_name(accent_mat, "PB_AccentColorMix")
        if accent_mix:
            accent_mix.inputs["Color2"].default_value = (r, g, b, 1.0)
            accent_mix.inputs["Fac"].default_value = 0.1 + getattr(style, "accent_color_strength", 0.72) * 0.85
        else:
            accent.inputs["Base Color"].default_value = (r, g, b, 1.0)
    if glass:
        wall_luma = sum(getattr(style, "wall_tint", (0.91, 0.9, 0.86))) / 3.0
        tint_strength = getattr(style, "glass_tint_strength", 0.62)
        glass_tint = 0.40 + wall_luma * 0.18
        tint_mix = _node_by_name(glass_mat, "PB_GlassTintMix")
        if tint_mix:
            tint_mix.inputs["Fac"].default_value = 0.25 + tint_strength * 0.65
            tint_mix.inputs["Color1"].default_value = (glass_tint, 0.72, 0.82, 1.0)
            tint_mix.inputs["Color2"].default_value = (glass_tint * 0.38, 0.18, 0.24, 1.0)
        glass.inputs["Roughness"].default_value = 0.02 + (1.0 - tint_strength) * 0.08

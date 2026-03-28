import bpy

GENERATOR_TAG = "PROC_BUILDING_ADDON"
COLLECTION_NAME = "ProcBuilding_Runtime"
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
    if mat:
        return mat

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    clear_nodes(mat)
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)

    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-1200, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-980, 0)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-760, 120)
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.42

    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.location = (-760, -120)
    voronoi.inputs["Scale"].default_value = 14.0

    mix = nodes.new("ShaderNodeMixRGB")
    mix.location = (-420, 40)
    mix.inputs["Fac"].default_value = 0.22

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-520, -150)

    bump = nodes.new("ShaderNodeBump")
    bump.location = (180, -180)

    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
    links.new(noise.outputs["Fac"], mix.inputs["Color1"])
    links.new(voronoi.outputs["Distance"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if kind == "wall":
        bsdf.inputs["Base Color"].default_value = (0.91, 0.90, 0.86, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.68
        ramp.color_ramp.elements[0].color = (0.50, 0.50, 0.50, 1.0)
        ramp.color_ramp.elements[1].color = (0.66, 0.66, 0.66, 1.0)
        bump.inputs["Strength"].default_value = 0.05
    elif kind == "trim":
        bsdf.inputs["Base Color"].default_value = (0.97, 0.97, 0.94, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.34
        bump.inputs["Strength"].default_value = 0.015
    elif kind == "roof":
        bsdf.inputs["Base Color"].default_value = (0.36, 0.39, 0.41, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.86
        bump.inputs["Strength"].default_value = 0.03
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
        bsdf.inputs["Base Color"].default_value = (0.62, 0.84, 0.97, 0.20)
        bsdf.inputs["Roughness"].default_value = 0.03
        bsdf.inputs["IOR"].default_value = 1.45
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 1.0
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = 1.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 0.16
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'HASHED'
        if hasattr(mat, "use_screen_refraction"):
            mat.use_screen_refraction = True
    elif kind == "accent":
        bsdf.inputs["Base Color"].default_value = (0.34, 0.52, 0.68, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.45

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

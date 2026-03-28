import bpy

from .utils import GENERATOR_TAG, world_box


class MeshBatcher:
    def __init__(self):
        self.data = {}

    def add_box(self, group, sx, sy, sz, center):
        verts, faces = world_box(sx, sy, sz, center)
        if group not in self.data:
            self.data[group] = {"verts": [], "faces": []}
        base = len(self.data[group]["verts"])
        self.data[group]["verts"].extend(verts)
        self.data[group]["faces"].extend([(a + base, b + base, c + base, d + base) for (a, b, c, d) in faces])

    def build_objects(self, collection, materials, smooth=False):
        for group, payload in self.data.items():
            if not payload["verts"] or not payload["faces"]:
                continue
            mesh = bpy.data.meshes.new(f"{group}_mesh")
            mesh.from_pydata(payload["verts"], [], payload["faces"])
            mesh.update()
            if smooth:
                for poly in mesh.polygons:
                    poly.use_smooth = True
            obj = bpy.data.objects.new(f"{group}_obj", mesh)
            obj["generated_by"] = GENERATOR_TAG
            if group in materials:
                obj.data.materials.append(materials[group])
            collection.objects.link(obj)

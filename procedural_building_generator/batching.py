import bmesh
import bpy
import math

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
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
            mesh.validate(clean_customdata=True)
            mesh.use_auto_smooth = True
            if hasattr(mesh, "auto_smooth_angle"):
                mesh.auto_smooth_angle = math.radians(45.0)
            for poly in mesh.polygons:
                poly.use_smooth = False
            obj = bpy.data.objects.new(f"{group}_obj", mesh)
            obj["generated_by"] = GENERATOR_TAG
            if group in materials:
                obj.data.materials.append(materials[group])
            collection.objects.link(obj)

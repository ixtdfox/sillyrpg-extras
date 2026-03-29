import bmesh
import bpy
import math

from .utils import GENERATOR_TAG, world_box


class MeshBatcher:
    def __init__(self):
        self.data = {}
        self._bbox_records = []
        self._reported_overlap = False

    def add_box(self, group, sx, sy, sz, center):
        cx, cy, cz = center
        bbox = (
            cx - sx * 0.5,
            cy - sy * 0.5,
            cz - sz * 0.5,
            cx + sx * 0.5,
            cy + sy * 0.5,
            cz + sz * 0.5,
        )
        self._debug_overlap_check(group, bbox)
        verts, faces = world_box(sx, sy, sz, center)
        if group not in self.data:
            self.data[group] = {"verts": [], "faces": []}
        base = len(self.data[group]["verts"])
        self.data[group]["verts"].extend(verts)
        self.data[group]["faces"].extend([(a + base, b + base, c + base, d + base) for (a, b, c, d) in faces])
        self._bbox_records.append((group, bbox))

    def _debug_overlap_check(self, group, bbox):
        eps = 0.0005
        x0, y0, z0, x1, y1, z1 = bbox
        for other_group, other in self._bbox_records[-240:]:
            ox0, oy0, oz0, ox1, oy1, oz1 = other
            ix = min(x1, ox1) - max(x0, ox0)
            iy = min(y1, oy1) - max(y0, oy0)
            iz = min(z1, oz1) - max(z0, oz0)
            if ix > eps and iy > eps and iz > eps:
                if not self._reported_overlap:
                    print("Overlapping geometry detected in facade module")
                    self._reported_overlap = True
                return
            coplanar_x = abs(x1 - ox0) <= eps or abs(ox1 - x0) <= eps
            coplanar_y = abs(y1 - oy0) <= eps or abs(oy1 - y0) <= eps
            coplanar_z = abs(z1 - oz0) <= eps or abs(oz1 - z0) <= eps
            touching_axes = int(coplanar_x) + int(coplanar_y) + int(coplanar_z)
            if touching_axes == 1 and (ix > eps or iy > eps or iz > eps):
                if group == other_group and not self._reported_overlap:
                    print("Overlapping geometry detected in facade module")
                    self._reported_overlap = True
                return

    @staticmethod
    def _remove_duplicate_faces(bm):
        seen = {}
        delete_faces = []
        for face in bm.faces:
            key = tuple(sorted(v.index for v in face.verts))
            if key in seen:
                delete_faces.append(face)
            else:
                seen[key] = face
        if delete_faces:
            bmesh.ops.delete(bm, geom=delete_faces, context='FACES')

    def build_objects(self, collection, materials, smooth=False):
        for group, payload in self.data.items():
            if not payload["verts"] or not payload["faces"]:
                continue
            mesh = bpy.data.meshes.new(f"{group}_mesh")
            mesh.from_pydata(payload["verts"], [], payload["faces"])
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
            self._remove_duplicate_faces(bm)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
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

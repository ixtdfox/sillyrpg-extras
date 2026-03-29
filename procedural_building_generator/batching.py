import bmesh
import bpy
import math

from .utils import GENERATOR_TAG, world_box


class MeshBatcher:
    _INTENTIONAL_OVERLAP_GROUPS = {"wall", "roof"}

    def __init__(self):
        self.data = {}
        self._bbox_records = []
        self._reported_overlap = False
        self._skipped_overlaps = 0

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
        if not self._debug_overlap_check(group, bbox):
            self._skipped_overlaps += 1
            return
        verts, faces = world_box(sx, sy, sz, center)
        if group not in self.data:
            self.data[group] = {"verts": [], "faces": []}
        base = len(self.data[group]["verts"])
        self.data[group]["verts"].extend(verts)
        self.data[group]["faces"].extend([(a + base, b + base, c + base, d + base) for (a, b, c, d) in faces])
        self._bbox_records.append((group, bbox))

    def _debug_overlap_check(self, group, bbox):
        if group in self._INTENTIONAL_OVERLAP_GROUPS:
            return True
        eps = 0.0005
        x0, y0, z0, x1, y1, z1 = bbox
        for other_group, other in self._bbox_records[-240:]:
            ox0, oy0, oz0, ox1, oy1, oz1 = other
            ix = min(x1, ox1) - max(x0, ox0)
            iy = min(y1, oy1) - max(y0, oy0)
            iz = min(z1, oz1) - max(z0, oz0)
            if ix > eps and iy > eps and iz > eps:
                if not self._reported_overlap:
                    print("Overlapping geometry detected in facade module; skipping intersecting box")
                    self._reported_overlap = True
                return False
        return True

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

    @staticmethod
    def _remove_internal_faces(bm):
        internal = [face for face in bm.faces if face.calc_area() <= 1e-8]
        if internal:
            bmesh.ops.delete(bm, geom=internal, context='FACES')

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
            self._remove_internal_faces(bm)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
            if bm.faces:
                bmesh.ops.dissolve_limit(
                    bm,
                    angle_limit=0.0005,
                    use_dissolve_boundaries=False,
                    verts=bm.verts,
                    edges=bm.edges,
                )
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
            if self._skipped_overlaps:
                obj["skipped_overlap_boxes"] = int(self._skipped_overlaps)
            if group in materials:
                obj.data.materials.append(materials[group])
            collection.objects.link(obj)

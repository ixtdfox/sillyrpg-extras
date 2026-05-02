from __future__ import annotations

from dataclasses import dataclass
from mathutils import Vector

import bpy

from ..common.utils import ADDON_ID, iter_collection_objects_recursive, print_game_visibility_summary


@dataclass
class OptimizationResult:
    groups_optimized: int = 0
    objects_removed: int = 0
    objects_created: int = 0
    skipped_objects: int = 0


class GeneratedMeshOptimizer:
    """Оптимизирует сгенерированные mesh-тайлы без пересчёта UV по общему bbox."""

    debug = False

    SAFE_PARTS = {
        "floor",
        "roof",
        "terrace",
        "outer_wall",
        "inner_wall",
        "border",
        "roof_railing",
        "terrace_railing",
        "stair",
    }
    UNSAFE_PARTS = {"door", "window", "decal", "room_metadata", "metadata", "helper", "visibility_volume"}

    def optimize_collection(self, collection: bpy.types.Collection, *, selected_only: bool = False) -> OptimizationResult:
        result = OptimizationResult()
        candidates = self.collect_candidates(collection, selected_only=selected_only)
        groups = self.group_objects(candidates)

        handled = set()
        for group_key, objects in groups.items():
            handled.update(objects)
            if not objects:
                continue
            optimized_objects = [obj for obj in objects if bool(obj.get("optimized_mesh", False))]
            source_objects = [obj for obj in objects if not bool(obj.get("optimized_mesh", False))]

            if source_objects:
                if self.debug and group_key and group_key[0] == "border":
                    self.debug_border_group(group_key, source_objects)
                try:
                    combined = self.combine_group(group_key, source_objects)
                except Exception:
                    result.skipped_objects += len(source_objects)
                    continue
                if combined is None:
                    result.skipped_objects += len(source_objects)
                    continue
                result.groups_optimized += 1
                result.objects_created += 1
                result.objects_removed += len(source_objects)
            elif selected_only and optimized_objects:
                for obj in optimized_objects:
                    if str(obj.get("building_part", "")) in {"outer_wall", "inner_wall"}:
                        cleanup = self.cleanup_wall_mesh(obj.data)
                        self._tag_wall_cleanup(obj, cleanup)
                        if cleanup["opposite"] or cleanup["bottom"]:
                            print(
                                "[MeshCleanup]",
                                f"wall group={obj.name}",
                                f"removedInternalFaces={cleanup['opposite']}",
                                f"removedBottomFaces={cleanup['bottom']}",
                            )
                    if str(obj.get("building_part", "")) != "border":
                        self.remove_doubles(obj.data)
                result.groups_optimized += len(optimized_objects)

        result.skipped_objects += len([obj for obj in candidates if obj not in handled])
        print_game_visibility_summary(collection)
        return result

    def collect_candidates(self, collection: bpy.types.Collection, selected_only: bool = False) -> list[bpy.types.Object]:
        objects = list(iter_collection_objects_recursive(collection))
        if selected_only:
            objects = [obj for obj in objects if obj.select_get()]

        candidates: list[bpy.types.Object] = []
        for obj in objects:
            if obj.type != "MESH":
                continue
            if obj.get("generated_by") != ADDON_ID:
                continue
            part = str(obj.get("building_part", ""))
            if part in self.UNSAFE_PARTS or part not in self.SAFE_PARTS:
                continue
            if self._is_helper_or_decal(obj):
                continue
            candidates.append(obj)
        return candidates

    def group_objects(self, objects: list[bpy.types.Object]) -> dict[tuple, list[bpy.types.Object]]:
        groups: dict[tuple, list[bpy.types.Object]] = {}
        for obj in objects:
            key = self._group_key(obj)
            if key is None:
                continue
            groups.setdefault(key, []).append(obj)
        return groups

    def combine_group(self, group_key: tuple, objects: list[bpy.types.Object]) -> bpy.types.Object | None:
        mesh_objects = [obj for obj in objects if obj.type == "MESH" and obj.data is not None]
        if not mesh_objects:
            return None
        source_bbox = self.world_bbox_for_objects(mesh_objects)

        verts_world: list[Vector] = []
        faces: list[list[int]] = []
        face_materials: list[int] = []
        face_uvs: list[list[tuple[float, float]]] = []
        materials: list[bpy.types.Material] = []
        material_index: dict[int, int] = {}
        has_uv = False

        for obj in mesh_objects:
            mesh = obj.data
            source_uv = mesh.uv_layers.active.data if mesh.uv_layers.active else None
            local_material_map: dict[int, int] = {}
            for index, material in enumerate(mesh.materials):
                if material is None:
                    continue
                material_key = material.as_pointer()
                if material_key not in material_index:
                    material_index[material_key] = len(materials)
                    materials.append(material)
                local_material_map[index] = material_index[material_key]

            vertex_offset = len(verts_world)
            verts_world.extend(obj.matrix_world @ vertex.co for vertex in mesh.vertices)
            for polygon in mesh.polygons:
                faces.append([vertex_offset + mesh.loops[loop_index].vertex_index for loop_index in polygon.loop_indices])
                face_materials.append(local_material_map.get(polygon.material_index, 0))
                if source_uv is not None:
                    has_uv = True
                    face_uvs.append([tuple(source_uv[loop_index].uv) for loop_index in polygon.loop_indices])
                else:
                    face_uvs.append([(0.0, 0.0) for _loop_index in polygon.loop_indices])

        if not verts_world or not faces:
            return None

        center = self._bbox_center(verts_world)
        verts_local = [tuple(vertex - center) for vertex in verts_world]
        mesh_name = f"{self._group_name(group_key)}Mesh"
        combined_mesh = bpy.data.meshes.new(mesh_name)
        combined_mesh.from_pydata(verts_local, [], faces)
        combined_mesh.validate(clean_customdata=False)
        combined_mesh.update(calc_edges=True)
        for material in materials:
            combined_mesh.materials.append(material)
        for polygon, material_slot in zip(combined_mesh.polygons, face_materials):
            polygon.material_index = material_slot
        if has_uv:
            uv_layer = combined_mesh.uv_layers.new(name="AtlasUV")
            for polygon, uvs in zip(combined_mesh.polygons, face_uvs):
                for loop_index, uv in zip(polygon.loop_indices, uvs):
                    uv_layer.data[loop_index].uv = uv

        combined_obj = bpy.data.objects.new(self._group_name(group_key), combined_mesh)
        combined_obj.location = center
        self._copy_group_properties(group_key, mesh_objects, combined_obj)
        try:
            self._link_like_sources(mesh_objects, combined_obj)
            if str(group_key[0]) in {"outer_wall", "inner_wall"}:
                cleanup = self.cleanup_wall_mesh(combined_mesh)
                self._tag_wall_cleanup(combined_obj, cleanup)
                if cleanup["opposite"] or cleanup["bottom"]:
                    print(
                        "[MeshCleanup]",
                        f"wall group={combined_obj.name}",
                        f"removedInternalFaces={cleanup['opposite']}",
                        f"removedBottomFaces={cleanup['bottom']}",
                    )
            if str(group_key[0]) != "border":
                self.remove_doubles(combined_mesh)
            self.warn_if_bbox_mismatch(group_key, source_bbox, self.world_bbox_for_object(combined_obj))
        except Exception:
            bpy.data.objects.remove(combined_obj, do_unlink=True)
            raise

        for obj in mesh_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        return combined_obj

    def remove_doubles(self, mesh: bpy.types.Mesh, threshold: float = 1e-6) -> None:
        import bmesh

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=threshold)
            bm.to_mesh(mesh)
            mesh.update()
        finally:
            bm.free()

    def cleanup_wall_mesh(self, mesh: bpy.types.Mesh) -> dict[str, int]:
        removed_opposite = self.remove_exact_opposite_faces(mesh)
        removed_bottom = self.remove_bottom_faces(mesh)
        return {
            "opposite": removed_opposite,
            "bottom": removed_bottom,
        }

    def remove_bottom_faces(self, mesh: bpy.types.Mesh, threshold: float = 0.999) -> int:
        import bmesh

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.normal_update()
            faces_to_delete = [face for face in bm.faces if face.normal.z < -threshold]
            removed = len(faces_to_delete)
            if removed:
                bmesh.ops.delete(bm, geom=faces_to_delete, context="FACES")
                bm.to_mesh(mesh)
                mesh.update()
            return removed
        finally:
            bm.free()

    def remove_exact_opposite_faces(self, mesh: bpy.types.Mesh, precision: int = 6) -> int:
        import bmesh

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.normal_update()
            bm.faces.ensure_lookup_table()
            buckets: dict[tuple[tuple[float, float, float], ...], list] = {}
            for face in bm.faces:
                key = tuple(
                    sorted(
                        (
                            round(float(vertex.co.x), precision),
                            round(float(vertex.co.y), precision),
                            round(float(vertex.co.z), precision),
                        )
                        for vertex in face.verts
                    )
                )
                buckets.setdefault(key, []).append(face)

            faces_to_delete = []

            def marked(face) -> bool:
                return any(face is existing for existing in faces_to_delete)

            for bucket_faces in buckets.values():
                unused = [face for face in bucket_faces if face.is_valid]
                while unused:
                    face = unused.pop()
                    if marked(face):
                        continue
                    match_index = None
                    for index, other in enumerate(unused):
                        if marked(other):
                            continue
                        if abs(face.calc_area() - other.calc_area()) > 1e-8:
                            continue
                        if face.normal.dot(other.normal) > -0.999:
                            continue
                        match_index = index
                        break
                    if match_index is None:
                        continue
                    other = unused.pop(match_index)
                    faces_to_delete.append(face)
                    faces_to_delete.append(other)

            removed = len(faces_to_delete)
            if removed:
                bmesh.ops.delete(bm, geom=list(faces_to_delete), context="FACES")
                bm.to_mesh(mesh)
                mesh.update()
            return removed
        finally:
            bm.free()

    def _group_key(self, obj: bpy.types.Object) -> tuple | None:
        part = str(obj.get("building_part", ""))
        story = self._prop(obj, "story_index", None)

        if part == "floor":
            return self._with_game_group_key(obj, ("floor", story))
        if part in {"roof", "terrace"}:
            return self._with_game_group_key(
                obj,
                (part, story, self._prop(obj, "surface_type", part)),
            )
        if part == "outer_wall":
            return self._with_game_group_key(
                obj,
                ("outer_wall", story, self._prop(obj, "edge_side", ""), self._prop(obj, "wall_orientation", "")),
            )
        if part == "inner_wall":
            boundary_id = self._prop(obj, "boundary_run_id", "")
            if boundary_id:
                return self._with_game_group_key(obj, ("inner_wall", story, boundary_id))
            return self._with_game_group_key(obj, (
                "inner_wall",
                story,
                self._prop(obj, "wall_orientation", ""),
                self._prop(obj, "edge_side", ""),
                self._prop(obj, "room_a_id", ""),
                self._prop(obj, "room_b_id", ""),
                self._line_anchor(obj),
            ))
        if part == "border":
            return self._with_game_group_key(obj, (
                "border",
                story,
                self._prop(obj, "border_type", ""),
                self._prop(obj, "edge_side", ""),
                self._prop(obj, "wall_orientation", ""),
                self._prop(obj, "surface_type", ""),
                self._border_run_token(obj),
                self._border_line_token(obj),
            ))
        if part in {"roof_railing", "terrace_railing"}:
            run_token = self._prop(
                obj,
                "run_id",
                f"corner_{self._prop(obj, 'tile_x', round(float(obj.location.x), 4))}_{self._prop(obj, 'tile_y', round(float(obj.location.y), 4))}",
            )
            return self._with_game_group_key(obj, (
                part,
                story,
                self._prop(obj, "surface_type", ""),
                run_token,
            ))
        if part == "stair":
            return self._with_game_group_key(obj, self._stair_group_key(obj, story))
        return None

    def _tag_wall_cleanup(self, obj: bpy.types.Object, cleanup: dict[str, int]) -> None:
        obj["mesh_cleanup_internal_faces_removed"] = True
        obj["mesh_cleanup_bottom_faces_removed"] = True
        obj["mesh_cleanup_removed_internal_face_count"] = int(cleanup["opposite"])
        obj["mesh_cleanup_removed_bottom_face_count"] = int(cleanup["bottom"])

    def _with_game_group_key(self, obj: bpy.types.Object, base_key: tuple) -> tuple:
        return base_key + (
            "game",
            self._prop(obj, "game_building_id", ""),
            self._prop(obj, "game_story_index", self._prop(obj, "story_index", "")),
            self._prop(obj, "game_visibility_role", ""),
            self._prop(obj, "game_occluder", ""),
            self._prop(obj, "game_hide_when_above_player", ""),
            self._prop(obj, "game_part", self._prop(obj, "building_part", "")),
        )

    def _stair_group_key(self, obj: bpy.types.Object, story) -> tuple:
        stair_kind = self._prop(obj, "stair_kind", "internal")
        if stair_kind == "external":
            name_key = self._external_stair_name_key(obj)
            return (
                "stair",
                "external",
                self._prop(obj, "story_index", story),
                self._prop(obj, "stair_facade_side", ""),
                self._prop(obj, "stair_facade_orientation", ""),
                name_key,
            )
        return (
            "stair",
            self._prop(obj, "from_story", story),
            self._prop(obj, "to_story", ""),
            stair_kind,
            self._prop(obj, "stair_orientation", ""),
            self._prop(obj, "stair_room_id", ""),
            self._prop(obj, "tile_x", ""),
            self._prop(obj, "tile_y", ""),
        )

    def _copy_group_properties(self, group_key: tuple, sources: list[bpy.types.Object], target: bpy.types.Object) -> None:
        part = str(group_key[0])
        target["generated_by"] = ADDON_ID
        target["optimized_mesh"] = True
        target["uv_baked"] = True
        target["atlas_baked"] = True
        target["source_object_count"] = len(sources)
        target["building_part"] = "stair" if part == "stair" else part

        for prop_name in (
            "story_index",
            "surface_type",
            "edge_side",
            "wall_orientation",
            "border_type",
            "border_wall_thickness",
            "stair_kind",
            "from_story",
            "to_story",
            "stair_orientation",
            "stair_room_id",
            "stair_facade_side",
            "stair_facade_orientation",
            "atlas_category",
            "atlas_tile_id",
            "boundary_run_id",
            "game_visibility",
            "game_visibility_role",
            "game_occluder",
            "game_hide_when_above_player",
            "game_inside_volume_source",
            "game_building_id",
            "game_story_index",
            "game_part",
            "game_wall_height",
            "game_story_z_offset",
            "game_surface_type",
        ):
            value = self._shared_prop(sources, prop_name)
            if value is not None:
                target[prop_name] = value

    def _group_name(self, group_key: tuple) -> str:
        group_key = self._base_group_key(group_key)
        part = str(group_key[0])
        story = group_key[1] if len(group_key) > 1 else None
        prefix = f"Story{story}_" if story not in {None, ""} else ""
        if part == "floor":
            return f"{prefix}Floor_Optimized"
        if part == "outer_wall":
            side = self._title_token(group_key[2])
            return f"{prefix}OuterWall_{side}_Optimized"
        if part == "inner_wall":
            return f"{prefix}InnerWall_{self._suffix(group_key[2:])}_Optimized"
        if part in {"roof", "terrace"}:
            return f"{prefix}{part.title()}_Optimized"
        if part == "border":
            return f"{prefix}Border_{self._suffix(group_key[2:])}_Optimized"
        if part in {"roof_railing", "terrace_railing"}:
            return f"{prefix}{self._title_token(part)}_{self._suffix(group_key[2:])}_Optimized"
        if part == "stair":
            if len(group_key) > 2 and group_key[1] != "external":
                return f"Stair_Story{group_key[1]}_to_Story{group_key[2]}_Optimized"
            return f"ExternalStair_{self._suffix(group_key[2:])}_Optimized"
        return f"{self._title_token(part)}_Optimized"

    def _base_group_key(self, group_key: tuple) -> tuple:
        if "game" not in group_key:
            return group_key
        return group_key[: group_key.index("game")]

    def _is_helper_or_decal(self, obj: bpy.types.Object) -> bool:
        if bool(obj.get("is_room_metadata", False)):
            return True
        category = str(obj.get("atlas_category", ""))
        return category == "decals" or "decal" in obj.name.lower()

    def _bbox_center(self, vertices: list[Vector]) -> Vector:
        min_x = min(vertex.x for vertex in vertices)
        max_x = max(vertex.x for vertex in vertices)
        min_y = min(vertex.y for vertex in vertices)
        max_y = max(vertex.y for vertex in vertices)
        min_z = min(vertex.z for vertex in vertices)
        max_z = max(vertex.z for vertex in vertices)
        return Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))

    def _link_like_sources(self, sources: list[bpy.types.Object], target: bpy.types.Object) -> None:
        collections = list(sources[0].users_collection)
        if not collections:
            bpy.context.scene.collection.objects.link(target)
            return
        for collection in collections:
            if target not in collection.objects[:]:
                collection.objects.link(target)

    def _shared_prop(self, objects: list[bpy.types.Object], prop_name: str):
        sentinel = object()
        value = sentinel
        for obj in objects:
            current = obj.get(prop_name, sentinel)
            if current is sentinel:
                return None
            if value is sentinel:
                value = current
            elif current != value:
                return None
        return None if value is sentinel else value

    def _prop(self, obj: bpy.types.Object, name: str, default):
        return obj.get(name, default)

    def _line_anchor(self, obj: bpy.types.Object) -> tuple:
        orientation = str(obj.get("wall_orientation", ""))
        if orientation == "x":
            return ("line_y", round(float(obj.location.y), 5))
        if orientation == "y":
            return ("line_x", round(float(obj.location.x), 5))
        return ("tile", self._prop(obj, "tile_x", ""), self._prop(obj, "tile_y", ""))

    def _border_run_token(self, obj: bpy.types.Object) -> str:
        boundary_id = str(obj.get("boundary_run_id", ""))
        parts = boundary_id.split(":")
        if len(parts) >= 3:
            try:
                return f"Run{int(parts[2]):03d}"
            except ValueError:
                return f"Run{parts[2]}"
        if boundary_id:
            return boundary_id
        return self._suffix((self._prop(obj, "edge_side", ""), self._line_anchor(obj)))

    def _border_line_token(self, obj: bpy.types.Object) -> str:
        orientation = str(obj.get("wall_orientation", ""))
        if orientation == "x":
            return f"LineY{round(float(obj.location.y), 5)}"
        if orientation == "y":
            return f"LineX{round(float(obj.location.x), 5)}"
        return self._suffix(("Tile", self._prop(obj, "tile_x", ""), self._prop(obj, "tile_y", "")))

    def world_bbox_for_objects(self, objects: list[bpy.types.Object]) -> tuple[Vector, Vector] | None:
        boxes = [self.world_bbox_for_object(obj) for obj in objects]
        boxes = [box for box in boxes if box is not None]
        if not boxes:
            return None
        return (
            Vector((min(box[0].x for box in boxes), min(box[0].y for box in boxes), min(box[0].z for box in boxes))),
            Vector((max(box[1].x for box in boxes), max(box[1].y for box in boxes), max(box[1].z for box in boxes))),
        )

    def world_bbox_for_object(self, obj: bpy.types.Object) -> tuple[Vector, Vector] | None:
        if obj.type != "MESH" or obj.data is None or not obj.data.vertices:
            return None
        points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        return (
            Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
            Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
        )

    def warn_if_bbox_mismatch(
        self,
        group_key: tuple,
        source_bbox: tuple[Vector, Vector] | None,
        optimized_bbox: tuple[Vector, Vector] | None,
        *,
        tolerance: float = 1e-5,
    ) -> None:
        if source_bbox is None or optimized_bbox is None:
            return
        deltas = [
            abs(source_bbox[0].x - optimized_bbox[0].x),
            abs(source_bbox[0].y - optimized_bbox[0].y),
            abs(source_bbox[0].z - optimized_bbox[0].z),
            abs(source_bbox[1].x - optimized_bbox[1].x),
            abs(source_bbox[1].y - optimized_bbox[1].y),
            abs(source_bbox[1].z - optimized_bbox[1].z),
        ]
        if max(deltas) > tolerance:
            print(
                "[procedural_floorplan_ru_v2] Mesh optimizer bbox mismatch",
                group_key,
                "source=",
                tuple(tuple(round(component, 6) for component in vector) for vector in source_bbox),
                "optimized=",
                tuple(tuple(round(component, 6) for component in vector) for vector in optimized_bbox),
            )

    def debug_border_group(self, group_key: tuple, objects: list[bpy.types.Object]) -> None:
        print(
            "[procedural_floorplan_ru_v2] Border optimizer group",
            group_key,
            "sources=",
            [obj.name for obj in objects],
        )

    def _external_stair_name_key(self, obj: bpy.types.Object) -> str:
        name = obj.name
        if name.startswith("ExtStair_"):
            return "_".join(name.split("_")[:2])
        if name.startswith("ExternalStair"):
            return "_".join(name.split("_")[:2])
        if name.startswith("ExternalLanding"):
            return name.split("_")[0]
        return f"{self._prop(obj, 'tile_x', '')}_{self._prop(obj, 'tile_y', '')}_{self._prop(obj, 'stair_part', '')}"

    def _suffix(self, values) -> str:
        text = "_".join(self._title_token(value) for value in values if value not in {None, ""})
        return text or "Group"

    def _title_token(self, value) -> str:
        return str(value).replace(":", "_").replace("-", "_").title()

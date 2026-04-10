
import bpy
from . import core
from . import atlas_manifest


SETTING_NAMES = [
    "delete_old", "collection_name", "wall_height", "wall_thickness", "floor_thickness", "corridor_width",
    "door_width", "entry_door_width", "entry_door_thickness", "door_height", "stair_width", "stair_landing",
    "stair_mid_landing", "stair_riser", "stair_tread", "stair_clearance", "stair_max_parent_occupancy",
    "stair_min_free_area", "stair_door_clearance", "stair_window_clearance", "window_sill_height",
    "window_height", "window_min_width", "window_end_margin", "window_strip_width", "outer_margin",
    "room_gap", "min_room_side", "max_aspect", "text_size", "post_merge_min_side", "post_merge_min_area",
    "post_merge_max_aspect", "post_merge_hard_max_aspect", "post_merge_edge_strip_side", "post_merge_sliver_ratio",
    "post_merge_min_shared", "residual_min_area", "residual_long_strip_ratio", "residual_short_side",
    "residual_corridor_shared_bonus", "house_scale", "target_room_count", "auto_random_seed", "seed",
    "min_floors", "max_floors", "building_mode", "shape_mode", "atlas_enabled", "atlas_manifest_path",
    "atlas_image_path", "atlas_include_interior_walls", "atlas_random_pick",
    "decals_enabled", "decal_manifest_path", "decal_image_path", "decal_density",
    "decal_enable_streaks", "decal_enable_grime", "decal_enable_ground_strips",
    "decal_enable_cracks", "decal_enable_corner_dirt", "decal_enable_edge_dirt", "debug_log_enabled",
    "modular_tiles_enabled", "wall_tile_width", "surface_tile_size",
]

KEY_MAP = {
    "delete_old": "DELETE_OLD",
    "collection_name": "COLLECTION_NAME",
    "wall_height": "WALL_HEIGHT",
    "wall_thickness": "WALL_THICKNESS",
    "floor_thickness": "FLOOR_THICKNESS",
    "corridor_width": "CORRIDOR_WIDTH",
    "door_width": "DOOR_WIDTH",
    "entry_door_width": "ENTRY_DOOR_WIDTH",
    "entry_door_thickness": "ENTRY_DOOR_THICKNESS",
    "door_height": "DOOR_HEIGHT",
    "stair_width": "STAIR_WIDTH",
    "stair_landing": "STAIR_LANDING",
    "stair_mid_landing": "STAIR_MID_LANDING",
    "stair_riser": "STAIR_RISER",
    "stair_tread": "STAIR_TREAD",
    "stair_clearance": "STAIR_CLEARANCE",
    "stair_max_parent_occupancy": "STAIR_MAX_PARENT_OCCUPANCY",
    "stair_min_free_area": "STAIR_MIN_FREE_AREA",
    "stair_door_clearance": "STAIR_DOOR_CLEARANCE",
    "stair_window_clearance": "STAIR_WINDOW_CLEARANCE",
    "window_sill_height": "WINDOW_SILL_HEIGHT",
    "window_height": "WINDOW_HEIGHT",
    "window_min_width": "WINDOW_MIN_WIDTH",
    "window_end_margin": "WINDOW_END_MARGIN",
    "window_strip_width": "WINDOW_STRIP_WIDTH",
    "outer_margin": "OUTER_MARGIN",
    "room_gap": "ROOM_GAP",
    "min_room_side": "MIN_ROOM_SIDE",
    "max_aspect": "MAX_ASPECT",
    "text_size": "TEXT_SIZE",
    "post_merge_min_side": "POST_MERGE_MIN_SIDE",
    "post_merge_min_area": "POST_MERGE_MIN_AREA",
    "post_merge_max_aspect": "POST_MERGE_MAX_ASPECT",
    "post_merge_hard_max_aspect": "POST_MERGE_HARD_MAX_ASPECT",
    "post_merge_edge_strip_side": "POST_MERGE_EDGE_STRIP_SIDE",
    "post_merge_sliver_ratio": "POST_MERGE_SLIVER_RATIO",
    "post_merge_min_shared": "POST_MERGE_MIN_SHARED",
    "residual_min_area": "RESIDUAL_MIN_AREA",
    "residual_long_strip_ratio": "RESIDUAL_LONG_STRIP_RATIO",
    "residual_short_side": "RESIDUAL_SHORT_SIDE",
    "residual_corridor_shared_bonus": "RESIDUAL_CORRIDOR_SHARED_BONUS",
    "house_scale": "HOUSE_SCALE",
    "target_room_count": "TARGET_ROOM_COUNT",
    "auto_random_seed": "AUTO_RANDOM_SEED",
    "seed": "SEED",
    "min_floors": "MIN_FLOORS",
    "max_floors": "MAX_FLOORS",
    "building_mode": "BUILDING_MODE",
    "shape_mode": "SHAPE_MODE",
    "atlas_enabled": "ATLAS_ENABLED",
    "atlas_manifest_path": "ATLAS_MANIFEST_PATH",
    "atlas_image_path": "ATLAS_IMAGE_PATH",
    "atlas_include_interior_walls": "ATLAS_INCLUDE_INTERIOR_WALLS",
    "atlas_random_pick": "ATLAS_RANDOM_PICK",
    "decals_enabled": "DECALS_ENABLED",
    "decal_manifest_path": "DECAL_MANIFEST_PATH",
    "decal_image_path": "DECAL_IMAGE_PATH",
    "decal_density": "DECAL_DENSITY",
    "decal_enable_streaks": "DECAL_ENABLE_STREAKS",
    "decal_enable_grime": "DECAL_ENABLE_GRIME",
    "decal_enable_ground_strips": "DECAL_ENABLE_GROUND_STRIPS",
    "decal_enable_cracks": "DECAL_ENABLE_CRACKS",
    "decal_enable_corner_dirt": "DECAL_ENABLE_CORNER_DIRT",
    "decal_enable_edge_dirt": "DECAL_ENABLE_EDGE_DIRT",
    "debug_log_enabled": "DEBUG_LOG_ENABLED",
    "modular_tiles_enabled": "MODULAR_TILES_ENABLED",
    "wall_tile_width": "WALL_TILE_WIDTH",
    "surface_tile_size": "SURFACE_TILE_SIZE",
}


def _settings_from_props(props):
    return {KEY_MAP[name]: getattr(props, name) for name in SETTING_NAMES}


class FLOORPLAN_OT_generate(bpy.types.Operator):
    bl_idname = "floorplan_ru.generate"
    bl_label = "Сгенерировать дом"
    bl_description = "Создать новый дом по текущим настройкам"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.floorplan_ru_settings
        settings = _settings_from_props(props)
        try:
            core.generate_from_settings(settings)
        except Exception as exc:
            self.report({'ERROR'}, f"Ошибка генерации: {exc}")
            raise
        self.report({'INFO'}, "Дом сгенерирован")
        return {'FINISHED'}


class FLOORPLAN_OT_reset_defaults(bpy.types.Operator):
    bl_idname = "floorplan_ru.reset_defaults"
    bl_label = "Сбросить настройки"
    bl_description = "Вернуть значения по умолчанию"

    def execute(self, context):
        from .props import apply_defaults_to_props
        apply_defaults_to_props(context.scene.floorplan_ru_settings)
        self.report({'INFO'}, "Настройки сброшены")
        return {'FINISHED'}




class FLOORPLAN_OT_atlas_load_manifest(bpy.types.Operator):
    bl_idname = "floorplan_ru.atlas_load_manifest"
    bl_label = "Загрузить manifest.json"
    bl_description = "Прочитать manifest.json и заполнить редактор атласа"

    def execute(self, context):
        props = context.scene.floorplan_ru_settings
        try:
            manifest, path = atlas_manifest.load_manifest_from_props(props)
            if manifest is None:
                manifest = core._write_default_atlas_manifest(props.atlas_manifest_path)
                path = atlas_manifest._abs_path(props.atlas_manifest_path)
            props.atlas_manifest_json = __import__('json').dumps(manifest, ensure_ascii=False)
            atlas_manifest.sync_editor_from_manifest(props)
            self.report({'INFO'}, f"Manifest загружен: {path.name}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Не удалось загрузить manifest: {exc}")
            return {'CANCELLED'}


class FLOORPLAN_OT_atlas_save_manifest(bpy.types.Operator):
    bl_idname = "floorplan_ru.atlas_save_manifest"
    bl_label = "Сохранить manifest.json"
    bl_description = "Записать изменения редактора обратно в manifest.json"

    def execute(self, context):
        props = context.scene.floorplan_ru_settings
        try:
            manifest = atlas_manifest.apply_editor_to_manifest(props)
            path = atlas_manifest.save_manifest_to_props(props, manifest)
            props.atlas_manifest_json = __import__('json').dumps(manifest, ensure_ascii=False)
            atlas_manifest.sync_editor_from_manifest(props)
            self.report({'INFO'}, f"Manifest сохранён: {path.name}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Не удалось сохранить manifest: {exc}")
            return {'CANCELLED'}


class FLOORPLAN_OT_atlas_apply_existing(bpy.types.Operator):
    bl_idname = "floorplan_ru.atlas_apply_existing"
    bl_label = "Применить атлас"
    bl_description = "Применить атлас к уже сгенерированному дому без полной регенерации"

    def execute(self, context):
        props = context.scene.floorplan_ru_settings
        try:
            if props.atlas_manifest_json:
                manifest = atlas_manifest.apply_editor_to_manifest(props)
                atlas_manifest.save_manifest_to_props(props, manifest)
            settings = _settings_from_props(props)
            core.apply_settings(settings)
            seed_value = props.seed if not props.auto_random_seed else 0
            core.apply_atlas_stage1(props.collection_name, seed_value)
            if props.decals_enabled:
                core.apply_decals_stage1(props.collection_name, seed_value)
            self.report({'INFO'}, "Атлас и декали применены к текущему дому")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Не удалось применить атлас: {exc}")
            return {'CANCELLED'}

classes = (
    FLOORPLAN_OT_generate,
    FLOORPLAN_OT_reset_defaults,
    FLOORPLAN_OT_atlas_load_manifest,
    FLOORPLAN_OT_atlas_save_manifest,
    FLOORPLAN_OT_atlas_apply_existing,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

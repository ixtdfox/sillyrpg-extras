from __future__ import annotations

import json
import random

import bpy

from . import addon, atlas_manifest, furniture_placement, generator, props as props_module, textures, utils


def _maybe_randomize_seed(settings):
    if settings.randomize_each_run:
        settings.seed = random.randint(0, 2_147_483_647)
        if hasattr(settings, "furniture_seed"):
            settings.furniture_seed = settings.seed


class RY_OT_generate_single(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_single"
    bl_label = "Сгенерировать объект"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = generator.generate_single(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации объекта: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Объект сгенерирован")
        return {"FINISHED"}


class RY_OT_generate_preview(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_preview"
    bl_label = "Сгенерировать набор ассетов"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = generator.generate_preview(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка preview: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Preview pack сгенерирован")
        return {"FINISHED"}


class RY_OT_generate_roof(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_roof"
    bl_label = "Сгенерировать крышу"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = generator.generate_roof(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации крыши: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Крыша сгенерирована")
        return {"FINISHED"}


class RY_OT_generate_yard(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_yard"
    bl_label = "Сгенерировать территорию"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = generator.generate_yard(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации территории: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Территория сгенерирована")
        return {"FINISHED"}


class RY_OT_generate_combo(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_combo"
    bl_label = "Сгенерировать по режиму"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        if settings.generation_mode == "roof":
            return bpy.ops.rooftop_yard_ru.generate_roof()
        if settings.generation_mode == "yard":
            return bpy.ops.rooftop_yard_ru.generate_yard()
        if settings.generation_mode == "roof_yard":
            result = bpy.ops.rooftop_yard_ru.generate_roof()
            if result != {"FINISHED"}:
                return result
            original_clear = settings.clear_previous_before_generate
            settings.clear_previous_before_generate = False
            try:
                result = bpy.ops.rooftop_yard_ru.generate_yard()
            finally:
                settings.clear_previous_before_generate = original_clear
            return result
        if settings.generation_mode == "furniture":
            return bpy.ops.rooftop_yard_ru.generate_furniture()
        return bpy.ops.rooftop_yard_ru.generate_preview()


class RY_OT_generate_furniture(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_furniture"
    bl_label = "Сгенерировать мебель"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = furniture_placement.generate_furniture_in_rectangle(context, settings, use_selected_bounds=False)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации мебели: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Мебель сгенерирована")
        return {"FINISHED"}


class RY_OT_generate_selected_room_furniture(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_selected_room_furniture"
    bl_label = "Сгенерировать мебель для выбранной комнаты"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = furniture_placement.generate_furniture_in_rectangle(context, settings, use_selected_bounds=True)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации мебели в выбранной комнате: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Мебель для выбранной комнаты сгенерирована")
        return {"FINISHED"}


class RY_OT_generate_furniture_catalog_preview(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_furniture_catalog_preview"
    bl_label = "Показать каталог мебели"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = furniture_placement.generate_furniture_catalog_preview(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка каталога мебели: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Каталог мебели сгенерирован")
        return {"FINISHED"}


class RY_OT_generate_single_furniture(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.generate_single_furniture"
    bl_label = "Сгенерировать выбранный интерьерный объект"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        _maybe_randomize_seed(settings)
        try:
            objects = furniture_placement.generate_single_furniture(context, settings)
            utils.focus_generated_objects(context, objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации интерьерного объекта: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Интерьерный объект сгенерирован")
        return {"FINISHED"}


class RY_OT_clear_generated(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.clear_generated"
    bl_label = "Очистить сгенерированное"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        generator.clear_generated(context, settings)
        self.report({"INFO"}, "Сгенерированные объекты удалены")
        return {"FINISHED"}


class RY_OT_reset_defaults(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.reset_defaults"
    bl_label = "Сбросить настройки"

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        props_module.apply_defaults_to_props(settings)
        manifest = atlas_manifest.manifest_from_settings(settings, persist_default_manifest=True)
        settings.manifest_json = json.dumps(manifest, ensure_ascii=False)
        atlas_manifest.sync_editor_from_manifest(settings)
        self.report({"INFO"}, "Настройки сброшены")
        return {"FINISHED"}


class RY_OT_reload_manifest(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.reload_manifest"
    bl_label = "Перезагрузить манифест"

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        try:
            manifest, path = atlas_manifest.load_manifest_from_props(settings)
            if manifest is None:
                manifest = atlas_manifest.write_default_manifest(settings.manifest_path)
            settings.manifest_json = json.dumps(manifest, ensure_ascii=False)
            atlas_manifest.sync_editor_from_manifest(settings)
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось загрузить manifest: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Manifest загружен: {path.name if manifest else 'default'}")
        return {"FINISHED"}


class RY_OT_save_manifest(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.save_manifest"
    bl_label = "Сохранить манифест"

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        try:
            manifest = atlas_manifest.apply_editor_to_manifest(settings)
            path = atlas_manifest.save_manifest_to_props(settings, manifest)
            settings.manifest_json = json.dumps(manifest, ensure_ascii=False)
            atlas_manifest.sync_editor_from_manifest(settings)
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось сохранить manifest: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Manifest сохранён: {path.name}")
        return {"FINISHED"}


class RY_OT_update_uvs(bpy.types.Operator):
    bl_idname = "rooftop_yard_ru.update_uvs"
    bl_label = "Обновить UV по манифесту"

    def execute(self, context):
        settings = context.scene.rooftop_yard_props_settings
        try:
            manifest = atlas_manifest.manifest_from_settings(settings, persist_default_manifest=True)
            runtime = atlas_manifest.build_runtime(settings, manifest)
            collection = bpy.data.collections.get(settings.target_collection_name)
            if collection is None:
                raise RuntimeError("Коллекция сгенерированных объектов не найдена")
            textures.update_collection_uvs(collection, runtime)
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось обновить UV: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "UV обновлены без пересборки геометрии")
        return {"FINISHED"}


classes = (
    RY_OT_generate_single,
    RY_OT_generate_preview,
    RY_OT_generate_roof,
    RY_OT_generate_yard,
    RY_OT_generate_combo,
    RY_OT_generate_furniture,
    RY_OT_generate_selected_room_furniture,
    RY_OT_generate_furniture_catalog_preview,
    RY_OT_generate_single_furniture,
    RY_OT_clear_generated,
    RY_OT_reset_defaults,
    RY_OT_reload_manifest,
    RY_OT_save_manifest,
    RY_OT_update_uvs,
)


def register():
    for cls in classes:
        addon.safe_register_class(cls)


def unregister():
    for cls in reversed(classes):
        addon.safe_unregister_class(cls)

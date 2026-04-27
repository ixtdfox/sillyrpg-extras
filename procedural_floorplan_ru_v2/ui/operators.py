from __future__ import annotations

import json
import random

import bpy

from .. import atlas
from ..building_stories_manager import BuildingStoriesManager
from ..building_manager import GenerationContext, settings_from_props
from ..common.utils import ensure_collection, focus_generated_objects
from ..optimization import GeneratedMeshOptimizer
from .props import apply_defaults_to_props


class FLOORPLAN_V2_OT_generate(bpy.types.Operator):
    """Оператор полной генерации здания по текущим настройкам."""

    bl_idname = "floorplan_ru_v2.generate"
    bl_label = "Сгенерировать дом"
    bl_description = "Создать здание выбранной формы с заданным числом этажей"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Собирает настройки, запускает менеджер генерации и переводит фокус на результат.

        Как это работает:
        оператор считывает `PropertyGroup` из сцены, преобразует его в обычный
        набор настроек, затем создаёт building-level manager, который строит
        общий footprint, подготавливает stories и вызывает существующие builders
        для каждого этажа. После успешной сборки оператор выделяет созданные
        объекты, а при любой ошибке сообщает её в интерфейс.
        """
        props = context.scene.floorplan_ru_v2_settings
        if props.randomize_seed_each_build:
            props.seed = random.randint(0, 2_147_483_647)
        settings = settings_from_props(props)
        try:
            manager = BuildingStoriesManager(settings)
            generation_context = manager.build(context.scene)
            focus_generated_objects(context, generation_context.created_objects)
        except Exception as exc:
            self.report({"ERROR"}, f"Ошибка генерации: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Здание сгенерировано: этажей {settings.story_count}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_reset_defaults(bpy.types.Operator):
    """Оператор сброса пользовательских настроек к стартовым значениям."""

    bl_idname = "floorplan_ru_v2.reset_defaults"
    bl_label = "Сбросить настройки"
    bl_description = "Вернуть значения по умолчанию"

    def execute(self, context):
        """Перезаписывает все свойства значениями по умолчанию.

        Как это работает:
        оператор обращается к helper-функции, которая последовательно выставляет
        значения в `floorplan_ru_v2_settings`, включая скрытые поля редактора
        атласа. За счёт этого в UI и в данных сцены не остаётся старого состояния.
        """
        apply_defaults_to_props(context.scene.floorplan_ru_v2_settings)
        self.report({"INFO"}, "Настройки сброшены")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_atlas_load_manifest(bpy.types.Operator):
    """Оператор загрузки atlas manifest.json в свойства и редактор аддона."""

    bl_idname = "floorplan_ru_v2.atlas_load_manifest"
    bl_label = "Загрузить manifest.json"
    bl_description = "Прочитать manifest.json и заполнить редактор атласа"

    def execute(self, context):
        """Читает manifest.json и синхронизирует элементы редактора с его содержимым.

        Как это работает:
        оператор получает путь из настроек, пытается прочитать JSON и, если файл
        ещё не существует, создаёт шаблонный manifest. Затем JSON сериализуется
        обратно в строковое свойство Blender, после чего вызывается синхронизация,
        которая раскладывает данные по отдельным UI-полям.
        """
        props = context.scene.floorplan_ru_v2_settings
        try:
            manifest, path = atlas.load_manifest_from_props(props)
            if manifest is None:
                manifest = atlas.write_default_manifest(props.atlas_manifest_path)
            props.atlas_manifest_json = json.dumps(manifest, ensure_ascii=False)
            atlas.sync_editor_from_manifest(props)
            self.report({"INFO"}, f"Manifest загружен: {path.name}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось загрузить manifest: {exc}")
            return {"CANCELLED"}


class FLOORPLAN_V2_OT_atlas_save_manifest(bpy.types.Operator):
    """Оператор сохранения состояния редактора обратно в manifest.json."""

    bl_idname = "floorplan_ru_v2.atlas_save_manifest"
    bl_label = "Сохранить manifest.json"
    bl_description = "Записать изменения редактора обратно в manifest.json"

    def execute(self, context):
        """Собирает данные из UI, обновляет manifest и записывает его на диск.

        Как это работает:
        сначала оператор просит модуль атласа слить поля редактора в структуру
        manifest, затем сохраняет её по пути из настроек. После записи строковое
        представление JSON и UI снова синхронизируются, чтобы интерфейс отражал
        уже нормализованное содержимое файла.
        """
        props = context.scene.floorplan_ru_v2_settings
        try:
            manifest = atlas.apply_editor_to_manifest(props)
            path = atlas.save_manifest_to_props(props, manifest)
            props.atlas_manifest_json = json.dumps(manifest, ensure_ascii=False)
            atlas.sync_editor_from_manifest(props)
            self.report({"INFO"}, f"Manifest сохранён: {path.name}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось сохранить manifest: {exc}")
            return {"CANCELLED"}


class FLOORPLAN_V2_OT_atlas_apply_existing(bpy.types.Operator):
    """Оператор повторного применения атласа к уже существующему полу."""

    bl_idname = "floorplan_ru_v2.atlas_apply_existing"
    bl_label = "Применить атлас"
    bl_description = "Применить атлас к уже сгенерированному полу без регенерации"

    def execute(self, context):
        """Пересчитывает atlas runtime и раскладывает материалы без регенерации геометрии.

        Как это работает:
        оператор поднимает обычные настройки, получает manifest из файла или
        из уже открытого редактора и вручную собирает укороченный `GenerationContext`.
        В этот контекст не включается footprint и генератор случайных чисел,
        потому что геометрия уже существует. Дальше модуль атласа проходит по
        объектам коллекции и обновляет им материалы и UV-настройки.
        """
        props = context.scene.floorplan_ru_v2_settings
        try:
            settings = settings_from_props(props)
            manifest = atlas.manifest_from_settings(settings, persist_default_manifest=True)
            if props.atlas_manifest_json:
                manifest = atlas.apply_editor_to_manifest(props)
            generation_context = GenerationContext(
                scene=context.scene,
                settings=settings,
                collection=ensure_collection(context.scene, settings.collection_name, delete_old=False),
                footprint=None,
                atlas_manifest=manifest,
                atlas_data=atlas.build_atlas_runtime(settings, manifest),
                rng=None,
            )
            atlas.apply_atlas_to_collection(generation_context)
            self.report({"INFO"}, "Атлас применён к текущему полу")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось применить атлас: {exc}")
            return {"CANCELLED"}


class FLOORPLAN_V2_OT_optimize_generated_meshes(bpy.types.Operator):
    """Оператор объединения сгенерированных тайлов в крупные baked mesh-объекты."""

    bl_idname = "floorplan_ru_v2.optimize_generated_meshes"
    bl_label = "Оптимизировать меши"
    bl_description = "Объединить сгенерированные тайлы в крупные меши без растягивания текстур"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        try:
            settings = settings_from_props(props)
            collection = ensure_collection(context.scene, settings.collection_name, delete_old=False)
            optimizer = GeneratedMeshOptimizer()
            selected_only = bool(optimizer.collect_candidates(collection, selected_only=True))
            result = optimizer.optimize_collection(collection, selected_only=selected_only)
            scope = "выделение" if selected_only else "коллекция"
            self.report(
                {"INFO"},
                f"Оптимизация завершена ({scope}): групп {result.groups_optimized}, удалено объектов {result.objects_removed}",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось оптимизировать меши: {exc}")
            return {"CANCELLED"}

classes = (
    FLOORPLAN_V2_OT_generate,
    FLOORPLAN_V2_OT_reset_defaults,
    FLOORPLAN_V2_OT_atlas_load_manifest,
    FLOORPLAN_V2_OT_atlas_save_manifest,
    FLOORPLAN_V2_OT_atlas_apply_existing,
    FLOORPLAN_V2_OT_optimize_generated_meshes,
)


def register():
    """Регистрирует все Blender-операторы модуля в фиксированном порядке."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Снимает регистрацию операторов в обратном порядке, как требует Blender."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

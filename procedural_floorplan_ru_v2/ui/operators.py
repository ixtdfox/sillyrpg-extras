from __future__ import annotations

import json
import random

import bpy
from mathutils import Matrix, Vector

from .. import atlas
from ..building_stories_manager import BuildingStoriesManager
from ..building_manager import GenerationContext, settings_from_props
from ..common.progress import GenerationProgress
from ..common.utils import ensure_collection, focus_generated_objects
from ..game_grid import GAME_TILE_SIZE_M, snap_value_to_game_grid, snap_world_point_to_nearest_rect_cell_center
from ..navigation import ensure_building_root, regenerate_existing_stair_navigation, set_selected_stair_navigation_visibility, set_stair_navigation_visibility, validate_stair_navigation
from ..metadata import NavigationMetadataExporter
from ..optimization import GeneratedMeshOptimizer
from ..preview import GameRectGridPreviewService
from ..terrain import (
    ProceduralCityGenerationError,
    ProceduralCityGenerator,
    TerrainSceneGenerationError,
    TerrainSceneGenerator,
    create_sample_mask_legend,
    procedural_city_settings_from_props,
    terrain_settings_from_props,
)
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
            NavigationMetadataExporter().create_rect_contract_from_collection(
                generation_context.collection,
                building_id=str(settings.general.collection_name),
            )
            focus_generated_objects(context, generation_context.created_objects)
            if bool(getattr(props, "game_rect_grid_preview_enabled", False)):
                GameRectGridPreviewService().refresh_preview(context.scene, props)
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


class FLOORPLAN_V2_OT_generate_terrain_scene(bpy.types.Operator):
    """Генерирует terrain scene в выбранном режиме."""

    bl_idname = "floorplan_ru_v2.generate_terrain_scene"
    bl_label = "Generate terrain scene"
    bl_description = "Создать procedural city или legacy image-mask terrain scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        if not props.terrain_enabled:
            self.report({"WARNING"}, "Включите Terrain enabled")
            return {"CANCELLED"}
        props.terrain_generation_status = "Preparing terrain scene..."
        props.terrain_generation_progress = 0.0
        progress = GenerationProgress(
            wm=getattr(context, "window_manager", None),
            total=100,
            operator=self,
            props=props,
        )
        progress.begin("Preparing terrain scene...", report=True)
        mode = str(getattr(props, "terrain_generation_mode", "procedural_city"))
        try:
            if mode == "procedural_city":
                city_settings = procedural_city_settings_from_props(props)
                stats = ProceduralCityGenerator().generate(context, props, city_settings, progress=progress)
                progress.update(100, "Done.")
                if stats.asset_counts:
                    self.report(
                        {"INFO"},
                        "Assets: cars=%d trees=%d tropicalTrees=%d bushes=%d benches=%d trafficLights=%d"
                        % (
                            stats.asset_counts.get("cars", 0),
                            stats.asset_counts.get("trees", 0),
                            stats.asset_counts.get("trees_tropical", 0),
                            stats.asset_counts.get("bushes", 0),
                            stats.asset_counts.get("benches", 0),
                            stats.asset_counts.get("traffic_lights", 0),
                        ),
                    )
                self.report(
                    {"INFO"},
                    "Props placed: cars=%d trees=%d streetFurniture=%d trafficLights=%d"
                    % (
                        stats.cars_created,
                        stats.trees_created,
                        stats.street_furniture_created,
                        stats.traffic_lights_created,
                    ),
                )
                for warning in stats.warnings[:4]:
                    self.report({"WARNING"}, warning)
                self.report(
                    {"INFO"},
                    f"Procedural city создан: buildings={stats.buildings_created}, blocks={stats.blocks_created}, parcels={stats.parcels_created}, props={stats.cars_created + stats.trees_created + stats.street_furniture_created + stats.traffic_lights_created}",
                )
                return {"FINISHED"}

            terrain_settings = terrain_settings_from_props(props)
            stats = TerrainSceneGenerator().generate(context, props, terrain_settings, progress=progress)
            progress.update(100, "Done.")
            self.report(
                {"INFO"},
                f"Legacy image-mask terrain создан: buildings={stats.buildings_created}, roads={stats.road_objects}, sidewalks={stats.sidewalk_objects}",
            )
            return {"FINISHED"}
        except ProceduralCityGenerationError as exc:
            progress.update(progress.current, f"Terrain generation failed: {exc}")
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except TerrainSceneGenerationError as exc:
            progress.update(progress.current, f"Terrain generation failed: {exc}")
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except FileNotFoundError as exc:
            progress.update(progress.current, f"Terrain generation failed: {exc}")
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            progress.update(progress.current, f"Terrain generation failed: {exc}")
            if mode == "procedural_city":
                self.report({"ERROR"}, f"Ошибка procedural city generation: {exc}")
            else:
                self.report({"ERROR"}, f"Ошибка terrain generation: {exc}")
            return {"CANCELLED"}
        finally:
            progress.end("" if "failed" in props.terrain_generation_status.lower() else "Done.")


class FLOORPLAN_V2_OT_finalize_terrain_buildings(bpy.types.Operator):
    """Оптимизирует только здания внутри terrain scene."""

    bl_idname = "floorplan_ru_v2.finalize_terrain_buildings"
    bl_label = "Finalize all buildings"
    bl_description = "Оптимизировать и смержить здания внутри terrain scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        root = bpy.data.collections.get(str(props.terrain_collection_name))
        if root is None:
            self.report({"WARNING"}, f"Terrain scene не найдена: {props.terrain_collection_name}")
            return {"CANCELLED"}
        buildings_root = root.children.get("buildings")
        if buildings_root is None:
            buildings_root = root.children.get("02_Buildings")
        if buildings_root is None:
            self.report({"WARNING"}, "В terrain scene нет коллекции buildings")
            return {"CANCELLED"}

        optimizer = GeneratedMeshOptimizer()
        buildings_processed = 0
        groups_optimized = 0
        objects_removed = 0
        for collection in buildings_root.children:
            result = optimizer.optimize_collection(collection, selected_only=False)
            buildings_processed += 1
            groups_optimized += result.groups_optimized
            objects_removed += result.objects_removed

        self.report(
            {"INFO"},
            f"Finalize buildings: processed={buildings_processed}, groups={groups_optimized}, removed={objects_removed}",
        )
        return {"FINISHED"}


class FLOORPLAN_V2_OT_clear_terrain_scene(bpy.types.Operator):
    """Удаляет всю terrain scene collection без влияния на обычную генерацию."""

    bl_idname = "floorplan_ru_v2.clear_terrain_scene"
    bl_label = "Clear terrain scene"
    bl_description = "Удалить terrain scene collection и её содержимое"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        removed = ProceduralCityGenerator().clear(context.scene, str(props.terrain_collection_name))
        if not removed:
            self.report({"WARNING"}, f"Terrain scene не найдена: {props.terrain_collection_name}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Удалена terrain scene: {props.terrain_collection_name}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_create_terrain_mask_legend(bpy.types.Operator):
    """Создаёт sample PNG legend для terrain mask."""

    bl_idname = "floorplan_ru_v2.create_terrain_mask_legend"
    bl_label = "Create sample mask legend"
    bl_description = "Сгенерировать PNG-пример terrain mask во временную директорию"

    def execute(self, context):
        try:
            path = create_sample_mask_legend()
        except Exception as exc:
            self.report({"ERROR"}, f"Не удалось создать mask legend: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Sample mask legend создан: {path}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_refresh_game_rect_grid_preview(bpy.types.Operator):
    """Rebuilds the non-exported game rect grid preview."""

    bl_idname = "floorplan_ru_v2.refresh_game_rect_grid_preview"
    bl_label = "Обновить preview"
    bl_description = "Пересоздать debug сетку игры во viewport"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        props.game_rect_grid_preview_enabled = True
        GameRectGridPreviewService().refresh_preview(context.scene, props)
        self.report({"INFO"}, "Game rect preview обновлён")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_remove_game_rect_grid_preview(bpy.types.Operator):
    """Removes the non-exported game rect grid preview."""

    bl_idname = "floorplan_ru_v2.remove_game_rect_grid_preview"
    bl_label = "Удалить preview"
    bl_description = "Удалить debug сетку игры из viewport"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        props.game_rect_grid_preview_enabled = False
        GameRectGridPreviewService().remove_preview(context.scene)
        self.report({"INFO"}, "Game rect preview удалён")
        return {"FINISHED"}


def _collection_objects_recursive(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    """Returns all objects linked to a collection and its child collections once."""
    objects: list[bpy.types.Object] = []
    seen: set[int] = set()

    def visit(current: bpy.types.Collection) -> None:
        for obj in current.objects:
            key = obj.as_pointer()
            if key in seen:
                continue
            seen.add(key)
            objects.append(obj)
        for child in current.children:
            visit(child)

    visit(collection)
    return objects


def _object_world_bbox_xz(obj: bpy.types.Object) -> list[tuple[float, float]]:
    """Returns world-space Blender X/Y bbox points for objects with real bounds."""
    if bool(obj.get("game_rect_grid_preview", False)) or bool(obj.get("floorplan_debug", False)):
        return []
    if not getattr(obj, "bound_box", None):
        return []
    if all(abs(coord) < 1e-12 for corner in obj.bound_box for coord in corner):
        return []
    matrix = obj.matrix_world
    return [(point.x, point.y) for point in (matrix @ Vector(corner) for corner in obj.bound_box)]


def _collection_bbox_min_xz(objects: list[bpy.types.Object]) -> tuple[float, float] | None:
    points: list[tuple[float, float]] = []
    for obj in objects:
        points.extend(_object_world_bbox_xz(obj))
    if not points:
        return None
    return min(point[0] for point in points), min(point[1] for point in points)


def _top_level_objects_within(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    object_keys = {obj.as_pointer() for obj in objects}
    return [obj for obj in objects if obj.parent is None or obj.parent.as_pointer() not in object_keys]


def _building_grid_anchor(collection: bpy.types.Collection) -> bpy.types.Object | None:
    for obj in _collection_objects_recursive(collection):
        if bool(obj.get("building_grid_anchor", False)) and bool(obj.get("building_root", False)):
            return obj
    return None


def _translate_building_objects(collection: bpy.types.Collection, objects: list[bpy.types.Object], shift_x: float, shift_y: float) -> None:
    shift = Matrix.Translation((shift_x, shift_y, 0.0))
    anchor = _building_grid_anchor(collection)
    if anchor is not None:
        anchor.matrix_world = shift @ anchor.matrix_world
        return
    for obj in _top_level_objects_within(objects):
        if bool(obj.get("game_rect_grid_preview", False)) or bool(obj.get("floorplan_debug", False)):
            continue
        obj.matrix_world = shift @ obj.matrix_world


class FLOORPLAN_V2_OT_align_building_to_game_grid(bpy.types.Operator):
    """Сдвигает сгенерированное здание на метрическую tile-сетку игры."""

    bl_idname = "floorplan_ru_v2.align_building_to_game_grid"
    bl_label = "Выровнять по сетке игры"
    bl_description = "Сдвигает building anchor на tile grid игры; для старых сцен использует bbox min X/Y"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection_name = str(props.collection_name)
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            self.report({"WARNING"}, f"Коллекция не найдена: {collection_name}")
            return {"CANCELLED"}

        ensure_building_root(collection)
        objects = [obj for obj in _collection_objects_recursive(collection) if not bool(obj.get("game_rect_grid_preview", False))]
        if not objects:
            self.report({"WARNING"}, f"Коллекция пуста: {collection_name}")
            return {"CANCELLED"}

        anchor = _building_grid_anchor(collection)
        if anchor is not None:
            anchor_x = float(anchor.matrix_world.translation.x)
            anchor_y = float(anchor.matrix_world.translation.y)
            snapped_x = snap_value_to_game_grid(anchor_x, GAME_TILE_SIZE_M)
            snapped_y = snap_value_to_game_grid(anchor_y, GAME_TILE_SIZE_M)
            shift_x = snapped_x - anchor_x
            shift_y = snapped_y - anchor_y
            anchor_name = "building anchor"
        else:
            bbox_min = _collection_bbox_min_xz(objects)
            if bbox_min is None:
                self.report({"WARNING"}, "В коллекции нет объектов с bbox для выравнивания")
                return {"CANCELLED"}
            min_x, min_y = bbox_min
            snapped_x = snap_value_to_game_grid(min_x, GAME_TILE_SIZE_M)
            snapped_y = snap_value_to_game_grid(min_y, GAME_TILE_SIZE_M)
            shift_x = snapped_x - min_x
            shift_y = snapped_y - min_y
            anchor_name = "bbox min"

        if abs(shift_x) < 1e-6 and abs(shift_y) < 1e-6:
            self.report({"INFO"}, f"Здание уже выровнено по сетке игры: tile={GAME_TILE_SIZE_M:.3f}m")
            return {"FINISHED"}

        _translate_building_objects(collection, objects, shift_x, shift_y)
        if bool(getattr(props, "game_rect_grid_preview_enabled", False)):
            GameRectGridPreviewService().refresh_preview(context.scene, props)

        self.report(
            {"INFO"},
            f"Здание выровнено по tile grid игры ({anchor_name}): shift=({shift_x:.3f}, {shift_y:.3f}, 0.000), tile={GAME_TILE_SIZE_M:.3f}m",
        )
        return {"FINISHED"}


class FLOORPLAN_V2_OT_align_building_anchor_to_rect_center(bpy.types.Operator):
    """Snaps the logical building anchor to the nearest game rect center."""

    bl_idname = "floorplan_ru_v2.align_building_anchor_to_rect_center"
    bl_label = "Выровнять якорь к центру rect"
    bl_description = "Сдвигает BuildingRoot/building_grid_anchor к ближайшему центру сетки игры"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection_name = str(props.collection_name)
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            self.report({"WARNING"}, f"Коллекция не найдена: {collection_name}")
            return {"CANCELLED"}

        anchor = ensure_building_root(collection)
        objects = _collection_objects_recursive(collection)
        anchor_x = float(anchor.matrix_world.translation.x)
        anchor_y = float(anchor.matrix_world.translation.y)
        snapped_x, snapped_y = snap_world_point_to_nearest_rect_cell_center(anchor_x, anchor_y, tile_size=GAME_TILE_SIZE_M)
        shift_x = snapped_x - anchor_x
        shift_y = snapped_y - anchor_y
        if abs(shift_x) < 1e-6 and abs(shift_y) < 1e-6:
            self.report({"INFO"}, "Building anchor уже стоит в центре game rect")
            return {"FINISHED"}

        _translate_building_objects(collection, objects, shift_x, shift_y)
        if bool(getattr(props, "game_rect_grid_preview_enabled", False)):
            GameRectGridPreviewService().refresh_preview(context.scene, props)
        self.report({"INFO"}, f"Building anchor сдвинут к центру rect: shift=({shift_x:.3f}, {shift_y:.3f}, 0.000)")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_show_stair_nav(bpy.types.Operator):
    """Показывает редактируемые nav checkpoint objects во viewport."""

    bl_idname = "floorplan_ru_v2.show_stair_nav"
    bl_label = "Show Stair Nav"
    bl_description = "Показать navigation checkpoint objects лестниц"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection = ensure_collection(context.scene, str(props.collection_name), delete_old=False)
        count = set_stair_navigation_visibility(collection, visible=True)
        self.report({"INFO"}, f"Показано stair nav objects: {count}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_hide_stair_nav(bpy.types.Operator):
    """Скрывает nav checkpoint objects во viewport, оставляя их экспортируемыми узлами."""

    bl_idname = "floorplan_ru_v2.hide_stair_nav"
    bl_label = "Hide Stair Nav"
    bl_description = "Скрыть navigation checkpoint objects лестниц во viewport"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection = ensure_collection(context.scene, str(props.collection_name), delete_old=False)
        count = set_stair_navigation_visibility(collection, visible=False)
        self.report({"INFO"}, f"Скрыто stair nav objects: {count}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_show_selected_stair_nav(bpy.types.Operator):
    """Показывает debug только для выбранного stair_id."""

    bl_idname = "floorplan_ru_v2.show_selected_stair_nav"
    bl_label = "Show Selected Stair Nav Only"
    bl_description = "Показать checkpoint-и и path preview только выбранной лестницы"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection = ensure_collection(context.scene, str(props.collection_name), delete_old=False)
        count, stair_id = set_selected_stair_navigation_visibility(collection, context.selected_objects)
        if stair_id is None:
            self.report({"WARNING"}, "Выберите stair connector, checkpoint или path preview")
            return {"FINISHED"}
        self.report({"INFO"}, f"Показан только stair_id={stair_id}: nav objects={count}")
        return {"FINISHED"}


class FLOORPLAN_V2_OT_validate_stair_nav(bpy.types.Operator):
    """Проверяет stair connector/checkpoint metadata and ordering."""

    bl_idname = "floorplan_ru_v2.validate_stair_nav"
    bl_label = "Validate Stair Navigation"
    bl_description = "Проверить navigation checkpoint-и лестниц"

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection = ensure_collection(context.scene, str(props.collection_name), delete_old=False)
        result = validate_stair_navigation(collection)
        for warning in result.warnings:
            print(f"[StairNavigationValidation] WARNING {warning}")
        if result.ok:
            message = f"Stair nav OK: connectors={result.connector_count}, checkpoints={result.checkpoint_count}"
            print(f"[StairNavigationValidation] {message}")
            self.report({"INFO"}, message)
            return {"FINISHED"}
        message = f"Stair nav warnings={len(result.warnings)}; см. console"
        print(f"[StairNavigationValidation] {message}")
        self.report({"WARNING"}, message)
        return {"FINISHED"}


class FLOORPLAN_V2_OT_regenerate_stair_nav(bpy.types.Operator):
    """Явно пересоздаёт checkpoint-и из сохранённой centerline metadata."""

    bl_idname = "floorplan_ru_v2.regenerate_stair_nav"
    bl_label = "Regenerate Stair Nav Checkpoints"
    bl_description = "Пересоздать stair navigation checkpoint-и по сохранённой centerline"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.floorplan_ru_v2_settings
        collection = ensure_collection(context.scene, str(props.collection_name), delete_old=False)
        count = regenerate_existing_stair_navigation(collection)
        if count <= 0:
            self.report({"WARNING"}, "Нет stair_connector с сохранённой centerline; сгенерируйте здание заново")
            return {"FINISHED"}
        self.report({"INFO"}, f"Пересоздано stair nav connector-ов: {count}")
        return {"FINISHED"}

classes = (
    FLOORPLAN_V2_OT_generate,
    FLOORPLAN_V2_OT_reset_defaults,
    FLOORPLAN_V2_OT_atlas_load_manifest,
    FLOORPLAN_V2_OT_atlas_save_manifest,
    FLOORPLAN_V2_OT_atlas_apply_existing,
    FLOORPLAN_V2_OT_optimize_generated_meshes,
    FLOORPLAN_V2_OT_generate_terrain_scene,
    FLOORPLAN_V2_OT_finalize_terrain_buildings,
    FLOORPLAN_V2_OT_clear_terrain_scene,
    FLOORPLAN_V2_OT_create_terrain_mask_legend,
    FLOORPLAN_V2_OT_refresh_game_rect_grid_preview,
    FLOORPLAN_V2_OT_remove_game_rect_grid_preview,
    FLOORPLAN_V2_OT_align_building_to_game_grid,
    FLOORPLAN_V2_OT_align_building_anchor_to_rect_center,
    FLOORPLAN_V2_OT_show_stair_nav,
    FLOORPLAN_V2_OT_hide_stair_nav,
    FLOORPLAN_V2_OT_show_selected_stair_nav,
    FLOORPLAN_V2_OT_validate_stair_nav,
    FLOORPLAN_V2_OT_regenerate_stair_nav,
)


def register():
    """Регистрирует все Blender-операторы модуля в фиксированном порядке."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Снимает регистрацию операторов в обратном порядке, как требует Blender."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

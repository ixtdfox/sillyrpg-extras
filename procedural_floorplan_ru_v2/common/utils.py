from __future__ import annotations

from typing import Iterable

import bpy


ADDON_ID = "procedural_floorplan_ru_v2"
GRID_STEP_M = 0.5
FLOOR_TILE_SIZE_M = 1.0
FLOOR_THICKNESS_M = 0.10
BORDER_TILE_SIZE_M = 1.0
BORDER_TILE_OVERLAP_M = 0.05
WALL_GRID_STEP_M = 0.25


def round_to_step(value: float, step: float = GRID_STEP_M) -> float:
    """Округляет значение к ближайшему шагу сетки.

    Как это работает:
    значение сначала переводится в количество шагов, затем округляется до
    ближайшего целого и умножается обратно на размер шага. Финальное
    округление до 6 знаков убирает накопившийся шум float-арифметики.
    """
    return round(round(value / step) * step, 6)


def ensure_half_step(value: float) -> float:
    """Приводит значение к сетке с шагом в полметра через общий helper."""
    return round_to_step(value, GRID_STEP_M)


def quantize_025(value: float) -> float:
    """Приводит значение к ближайшему числу, кратному 0.25 метра.

    Как это работает:
    функция использует общий механизм округления к шагу сетки, но фиксирует
    шаг равным `0.25`. Это позволяет единообразно квантизовать высоты, толщины,
    длины модулей и координаты стен независимо от того, откуда пришло число:
    из UI, из вычислений периметра или из промежуточной геометрии.
    """
    return round_to_step(value, WALL_GRID_STEP_M)


def ensure_collection(
    scene: bpy.types.Scene,
    collection_name: str,
    delete_old: bool,
) -> bpy.types.Collection:
    """Возвращает рабочую коллекцию генератора, создавая или очищая её при необходимости.

    Как это работает:
    функция ищет коллекцию по имени в глобальных данных Blender. Если её нет,
    она создаётся. Если коллекция уже есть и запрошена очистка, из неё
    рекурсивно удаляются объекты и дочерние коллекции. В конце коллекция
    обязательно привязывается к корневой коллекции сцены.
    """
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
    elif delete_old:
        clear_collection(collection)
    ensure_collection_linked(scene.collection, collection)
    return collection


def ensure_collection_linked(
    parent: bpy.types.Collection,
    collection: bpy.types.Collection,
) -> None:
    """Гарантирует, что коллекция подключена к родителю и видима в сцене.

    Как это работает:
    сначала отбрасывается вырожденный случай, когда коллекция уже является
    родительской. Затем идёт проверка по списку детей и при отсутствии связи
    выполняется `link`. После этого флаги скрытия сбрасываются, чтобы новые
    объекты были видны и во viewport, и в рендере.
    """
    if collection == parent:
        return
    if collection not in parent.children[:]:
        parent.children.link(collection)
    collection.hide_viewport = False
    collection.hide_render = False


def ensure_child_collection(
    parent: bpy.types.Collection,
    collection_name: str,
) -> bpy.types.Collection:
    """Возвращает дочернюю коллекцию с гарантированной привязкой к родителю."""
    for child in parent.children:
        if child.name == collection_name:
            collection = child
            break
    else:
        collection = bpy.data.collections.new(collection_name)
    ensure_collection_linked(parent, collection)
    return collection


def clear_collection(collection: bpy.types.Collection) -> None:
    """Полностью очищает коллекцию вместе с вложенными дочерними коллекциями.

    Как это работает:
    сначала копируется список объектов, чтобы безопасно удалять их во время
    обхода. Затем рекурсивно очищаются дочерние коллекции и удаляются сами
    контейнеры коллекций. Такой порядок гарантирует, что во вложенной иерархии
    не останется висящих объектов.
    """
    objects = list(collection.objects)
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    child_collections = list(collection.children)
    for child in child_collections:
        clear_collection(child)
        bpy.data.collections.remove(child)


def link_object(collection: bpy.types.Collection, obj: bpy.types.Object) -> None:
    """Привязывает объект к коллекции только если он ещё не добавлен."""
    if obj not in collection.objects[:]:
        collection.objects.link(obj)


def apply_story_object_context(obj: bpy.types.Object, context) -> None:
    """Добавляет story-метаданные, префикс имени и Z-смещение для объекта."""
    story_plan = getattr(context, "story_plan", None)
    if story_plan is None:
        return
    location = obj.location.copy()
    location.z += float(story_plan.z_offset)
    obj.location = location
    obj.name = f"Story{story_plan.story_index}_{obj.name}"
    obj["story_index"] = int(story_plan.story_index)
    obj["story_z_offset"] = float(story_plan.z_offset)


def iter_collection_objects_recursive(collection: bpy.types.Collection):
    """Итерирует объекты коллекции и всех её дочерних коллекций."""
    yield from collection.objects
    for child in collection.children:
        yield from iter_collection_objects_recursive(child)


def tag_generated_object(
    obj: bpy.types.Object,
    building_part: str,
    *,
    tile_x: int | None = None,
    tile_y: int | None = None,
    tile_size: float = FLOOR_TILE_SIZE_M,
) -> None:
    """Записывает в custom properties метаданные о сгенерированном объекте.

    Как это работает:
    функция сохраняет идентификатор аддона, тип строительной части и размер
    тайла, а координаты по сетке записывает только если они действительно
    переданы. Эти метаданные потом позволяют повторно находить и обрабатывать
    объекты без анализа их имени или геометрии.
    """
    obj["generated_by"] = ADDON_ID
    obj["building_part"] = building_part
    obj["tile_size"] = float(tile_size)
    if tile_x is not None:
        obj["tile_x"] = int(tile_x)
    if tile_y is not None:
        obj["tile_y"] = int(tile_y)


def selected_objects_in_collection(collection: bpy.types.Collection) -> Iterable[bpy.types.Object]:
    """Возвращает итератор по объектам коллекции без дополнительной фильтрации."""
    yield from collection.objects


def focus_generated_objects(context: bpy.types.Context, objects: list[bpy.types.Object]) -> None:
    """Выделяет сгенерированные объекты и делает первый из них активным.

    Как это работает:
    если список пуст, функция сразу завершает работу. Иначе она снимает текущее
    выделение, принудительно раскрывает каждый объект во viewport, отмечает их
    как выбранные и назначает первый объект активным. Это переводит пользователя
    прямо к результату генерации.
    """
    if not objects:
        return
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.hide_viewport = False
        obj.hide_set(False)
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]

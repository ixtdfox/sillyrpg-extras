from __future__ import annotations

from typing import Iterable

import bpy


ADDON_ID = "procedural_floorplan_ru_v2"
GRID_STEP_M = 0.5
FLOOR_TILE_SIZE_M = 1.0
FLOOR_THICKNESS_M = 0.10
BORDER_TILE_SIZE_M = 1.0
# Border tiles must meet exactly along a run. Corner caps/trims are applied
# only to true run ends by the border planner, never to interior tile joints.
BORDER_TILE_OVERLAP_M = 0.0
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
        if _preserve_on_generated_clear(obj):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
    child_collections = list(collection.children)
    for child in child_collections:
        if _collection_contains_preserved_objects(child):
            continue
        clear_collection(child)
        bpy.data.collections.remove(child)


def _preserve_on_generated_clear(obj: bpy.types.Object) -> bool:
    """Keeps editable navigation helpers and their building root across regeneration."""
    return bool(obj.get("nav_kind", "")) or bool(obj.get("building_root", False))


def _collection_contains_preserved_objects(collection: bpy.types.Collection) -> bool:
    if any(_preserve_on_generated_clear(obj) for obj in collection.objects):
        return True
    return any(_collection_contains_preserved_objects(child) for child in collection.children)


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
    apply_game_visibility_metadata(obj, context)


def apply_game_visibility_metadata(obj: bpy.types.Object, context) -> None:
    """Adds the stable exported game visibility metadata contract."""
    part = str(obj.get("building_part", obj.get("part", ""))).lower()
    if not part:
        return

    stair_kind = str(obj.get("stair_kind", "")).lower()
    is_external_stair = part == "stair" and stair_kind == "external"
    role = "ignore" if is_external_stair else _game_visibility_role(part)
    story_plan = getattr(context, "story_plan", None)
    settings = getattr(context, "settings", None)
    general_settings = getattr(settings, "general", None)
    collection = getattr(context, "collection", None)
    building_id = str(
        getattr(general_settings, "collection_name", "")
        or getattr(collection, "name", "")
        or obj.name
    )
    story_index = int(getattr(story_plan, "story_index", obj.get("story_index", 0)))
    story_z_offset = float(getattr(story_plan, "z_offset", obj.get("story_z_offset", 0.0)))

    obj["game_visibility"] = True
    obj["game_building_id"] = building_id
    obj["game_story_index"] = story_index
    obj["game_part"] = _game_part(obj, part)
    obj["game_visibility_role"] = role
    if is_external_stair:
        obj["game_visibility_behavior"] = "external_stair_connector"
    obj["game_occluder"] = role == "wall_halo"
    obj["game_hide_when_above_player"] = False if is_external_stair else role in {"wall_halo", "hide_above_player"}
    obj["game_story_z_offset"] = story_z_offset

    wall_height = obj.get("wall_height")
    if wall_height is not None:
        obj["game_wall_height"] = float(wall_height)
    surface_type = obj.get("surface_type")
    if surface_type is not None:
        obj["game_surface_type"] = str(surface_type)
    if part == "floor":
        obj["game_inside_volume_source"] = True


def _game_visibility_role(part: str) -> str:
    if part in {"outer_wall", "inner_wall"}:
        return "wall_halo"
    if part in {"roof", "terrace", "floor", "ceiling", "roof_railing", "terrace_railing", "stair"}:
        return "hide_above_player"
    if part == "border":
        return "hide_above_player"
    if part == "visibility_volume":
        return "inside_volume"
    if part == "ground":
        return "ground"
    return "ignore"


def _game_part(obj: bpy.types.Object, part: str) -> str:
    if part == "border":
        return str(obj.get("border_type", part))
    return part


def create_story_inside_volume(context) -> bpy.types.Object | None:
    """Creates a simple exported helper volume for story-level inside detection."""
    story_plan = getattr(context, "story_plan", None)
    footprint = getattr(context, "footprint", None)
    tiles = list(getattr(footprint, "tiles", []) or [])
    if story_plan is None or not tiles:
        return None

    min_x = min(tile[0] for tile in tiles) * FLOOR_TILE_SIZE_M
    min_y = min(tile[1] for tile in tiles) * FLOOR_TILE_SIZE_M
    max_x = (max(tile[0] for tile in tiles) + 1) * FLOOR_TILE_SIZE_M
    max_y = (max(tile[1] for tile in tiles) + 1) * FLOOR_TILE_SIZE_M
    walls_settings = getattr(getattr(context, "settings", None), "walls", None)
    height = float(getattr(walls_settings, "wall_height", FLOOR_TILE_SIZE_M))
    story_z_offset = float(getattr(story_plan, "z_offset", 0.0))
    verts = [
        (min_x, min_y, 0.0),
        (max_x, min_y, 0.0),
        (max_x, max_y, 0.0),
        (min_x, max_y, 0.0),
        (min_x, min_y, height),
        (max_x, min_y, height),
        (max_x, max_y, height),
        (min_x, max_y, height),
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    mesh = bpy.data.meshes.new(f"Story{story_plan.story_index}_InsideVolumeMesh")
    mesh.from_pydata(verts, edges, [])
    mesh.update()
    obj = bpy.data.objects.new("InsideVolume", mesh)
    tag_generated_object(obj, "visibility_volume", tile_size=FLOOR_TILE_SIZE_M)
    obj["game_inside_volume_source"] = True
    obj["game_volume_kind"] = "aabb"
    obj["game_volume_min"] = (min_x, min_y, story_z_offset)
    obj["game_volume_max"] = (max_x, max_y, story_z_offset + height)
    apply_story_object_context(obj, context)
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_render = True
    link_object(context.collection, obj)
    return obj


def print_game_visibility_summary(collection: bpy.types.Collection) -> None:
    """Prints one compact summary line per generated building/story."""
    stats: dict[tuple[str, int], dict[str, int]] = {}
    for obj in iter_collection_objects_recursive(collection):
        if not bool(obj.get("game_visibility", False)):
            continue
        building_id = str(obj.get("game_building_id", ""))
        story_index = int(obj.get("game_story_index", obj.get("story_index", 0)))
        role = str(obj.get("game_visibility_role", "ignore"))
        bucket = stats.setdefault((building_id, story_index), {"wallHalo": 0, "hideAbove": 0, "insideVolumes": 0})
        if role == "wall_halo":
            bucket["wallHalo"] += 1
        if bool(obj.get("game_hide_when_above_player", False)):
            bucket["hideAbove"] += 1
        if role == "inside_volume":
            bucket["insideVolumes"] += 1
    for (building_id, story_index), bucket in sorted(stats.items()):
        print(
            "[GameVisibilityMetadata]",
            f"building={building_id}",
            f"story={story_index}",
            f"wallHalo={bucket['wallHalo']}",
            f"hideAbove={bucket['hideAbove']}",
            f"insideVolumes={bucket['insideVolumes']}",
        )


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

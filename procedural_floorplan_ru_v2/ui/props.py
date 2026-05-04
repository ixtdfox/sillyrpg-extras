from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from .. import atlas
from ..common.utils import quantize_025


DEFAULTS = {
    "DELETE_OLD": True,
    "RANDOMIZE_SEED_EACH_BUILD": False,
    "COLLECTION_NAME": "GeneratedFloorPlanV2",
    "SEED": 42,
    "TARGET_ROOM_COUNT": 6,
    "MIN_ROOM_SIDE_M": 3.0,
    "HOUSE_SCALE": 1.0,
    "TEXT_SIZE": 0.34,
    "SHAPE_MODE": "rectangle",
    "STORY_COUNT": 1,
    "STORY_LAYOUT_MODE": "same",
    "VERTICAL_PROFILE_MODE": "strict",
    "VERTICAL_PROFILE_STRENGTH": 0.45,
    "FLOOR_BANDS_ENABLED": True,
    "FLOOR_BAND_DEPTH": 0.10,
    "FLOOR_BAND_HEIGHT": 0.10,
    "ROOF_BORDER_ENABLED": True,
    "ROOF_BORDER_DEPTH": 0.20,
    "ROOF_BORDER_HEIGHT": 0.20,
    "ATLAS_ENABLED": True,
    "ATLAS_MANIFEST_PATH": "//house_atlas.json",
    "ATLAS_IMAGE_PATH": "",
    "ATLAS_INCLUDE_INTERIOR_WALLS": False,
    "ATLAS_RANDOM_PICK": True,
    "DECALS_ENABLED": False,
    "DECAL_MANIFEST_PATH": "//decal_atlas_v2.json",
    "DECAL_IMAGE_PATH": "",
    "DECAL_DENSITY": 0.35,
    "DECAL_ENABLE_STREAKS": True,
    "OUTER_WALLS_ENABLED": True,
    "WALL_HEIGHT": 3.0,
    "WALL_MODULE_WIDTH": 1.0,
    "WALL_THICKNESS": 0.25,
    "DOORS_ENABLED": True,
    "INTERIOR_DOOR_WIDTH": 1.0,
    "INTERIOR_DOOR_HEIGHT": 2.0,
    "ENTRY_DOOR_WIDTH": 1.0,
    "ENTRY_DOOR_HEIGHT": 2.0,
    "DOOR_LEAF_THICKNESS": 0.1,
    "DOOR_MIN_EDGE_OFFSET": 0.5,
    "DOOR_MIN_CORNER_OFFSET": 0.5,
    "WINDOWS_ENABLED": True,
    "WINDOW_WIDTH": 1.0,
    "WINDOW_HEIGHT": 1.25,
    "WINDOW_SILL_HEIGHT": 0.9,
    "WINDOW_MIN_CORNER_OFFSET": 1.0,
    "WINDOW_MIN_DOOR_OFFSET": 1.0,
    "WINDOW_MIN_PARTITION_OFFSET": 1.0,
    "WINDOW_MIN_EDGE_OFFSET": 1.0,
    "STAIRS_ENABLED": True,
    "STAIR_MODE": "internal",
    "GENERATE_STAIR_NAV_CHECKPOINTS": True,
    "STAIR_WIDTH": 1.05,
    "STAIR_LANDING_SIZE": 1.05,
    "STAIR_MID_LANDING_SIZE": 1.45,
    "STAIR_RISER_HEIGHT": 0.17,
    "STAIR_TREAD_DEPTH": 0.28,
    "STAIR_MIN_FREE_AREA": 8.0,
    "STAIR_DOOR_CLEARANCE": 0.45,
    "STAIR_WINDOW_CLEARANCE": 0.35,
    "ROOF_RAILING_ENABLED": True,
    "RAILING_HEIGHT": 1.10,
    "RAILING_POST_SIZE": 0.06,
    "RAILING_RAIL_THICKNESS": 0.04,
    "RAILING_RAIL_COUNT": 3,
}

SHAPE_ITEMS = [
    ("rectangle", "Прямоугольник", "Прямоугольная форма"),
    ("l_shape", "L", "L-образная форма"),
    ("u_shape", "U", "U-образная форма"),
    ("h_shape", "H", "H-образная форма"),
    ("t_shape", "T", "T-образная форма"),
    ("courdoner", "Курдонер", "Форма с парадным внутренним двором"),
    ("offset", "Смещенный", "Составная форма со смещённым объёмом"),
]

STORY_LAYOUT_ITEMS = [
    ("same", "Одинаковые комнаты", "Все этажи используют один и тот же room layout"),
    ("random", "Рандом", "Форма дома общая, но комнаты каждого этажа строятся отдельно"),
]

VERTICAL_PROFILE_ITEMS = [
    ("strict", "STRICT", "Старый режим: все этажи используют один и тот же footprint"),
    ("setback", "SETBACK", "Верхние этажи постепенно отступают от краёв и образуют лесенку"),
    ("offset_stack", "OFFSET_STACK", "Этажи сохраняют форму, но смещаются относительно друг друга"),
    ("pinwheel", "PINWHEEL", "Этажи по очереди меняют доминирующее направление вокруг центрального ядра"),
    ("mixed", "MIXED", "Детерминированно комбинирует несколько стратегий по этажам"),
]

STAIR_MODE_ITEMS = [
    ("internal", "Внутренняя", "Генерировать лестницы внутри здания по текущей логике"),
    ("external", "Внешняя", "Генерировать наружную пожарную лестницу вдоль фасада"),
]


def _on_atlas_category_changed(self, context):
    """Обновляет поля редактора при смене категории тайлов.

    Как это работает:
    если сейчас активна защита от рекурсивной синхронизации, функция ничего не
    делает. Иначе она перечитывает выбранную категорию из `atlas_manifest_json`
    и подставляет в свойства данные первого или текущего тайла этой категории.
    """
    if getattr(self, "atlas_sync_lock", False):
        return
    atlas.sync_editor_from_manifest(self)


def _on_atlas_tile_changed(self, context):
    """Обновляет детальные поля редактора при выборе другого тайла.

    Как это работает:
    callback использует ту же синхронизацию, что и смена категории, но запускается
    только когда пользователь переключает конкретный элемент списка тайлов.
    Блокировка нужна, чтобы не зациклить `update`-обработчики при массовой записи.
    """
    if getattr(self, "atlas_sync_lock", False):
        return
    atlas.sync_editor_from_manifest(self)


def _quantize_wall_value(props, attr_name: str) -> None:
    """Приводит одно wall-свойство к сетке 0.25 без рекурсивного зацикливания."""
    if getattr(props, "wall_sync_lock", False):
        return
    raw_value = float(getattr(props, attr_name))
    snapped_value = max(0.25, quantize_025(raw_value))
    if abs(raw_value - snapped_value) < 1e-9:
        return
    props.wall_sync_lock = True
    try:
        setattr(props, attr_name, snapped_value)
    finally:
        props.wall_sync_lock = False


def _on_wall_height_changed(self, _context):
    """Сразу снапит высоту стены к сетке 0.25 после изменения в UI."""
    _quantize_wall_value(self, "wall_height")


def _on_wall_module_width_changed(self, _context):
    """Сразу снапит длину модульного стенового сегмента к сетке 0.25."""
    _quantize_wall_value(self, "wall_module_width")


def _on_wall_thickness_changed(self, _context):
    """Сразу снапит толщину стены к сетке 0.25."""
    _quantize_wall_value(self, "wall_thickness")


def _quantize_door_value(props, attr_name: str) -> None:
    """Приводит одно door-свойство к сетке 0.25 без рекурсивной синхронизации."""
    if getattr(props, "door_sync_lock", False):
        return
    raw_value = float(getattr(props, attr_name))
    snapped_value = max(0.25, quantize_025(raw_value))
    if abs(raw_value - snapped_value) < 1e-9:
        return
    props.door_sync_lock = True
    try:
        setattr(props, attr_name, snapped_value)
    finally:
        props.door_sync_lock = False


def _on_interior_door_width_changed(self, _context):
    """Сразу снапит ширину межкомнатной двери к сетке 0.25."""
    _quantize_door_value(self, "interior_door_width")


def _on_interior_door_height_changed(self, _context):
    """Сразу снапит высоту межкомнатной двери к сетке 0.25."""
    _quantize_door_value(self, "interior_door_height")


def _on_entry_door_width_changed(self, _context):
    """Сразу снапит ширину входной двери к сетке 0.25."""
    _quantize_door_value(self, "entry_door_width")


def _on_entry_door_height_changed(self, _context):
    """Сразу снапит высоту входной двери к сетке 0.25."""
    _quantize_door_value(self, "entry_door_height")


def _on_door_leaf_thickness_changed(self, _context):
    """Сразу снапит толщину дверной створки к шагу 0.05 с минимумом 0.1 м."""
    if getattr(self, "door_sync_lock", False):
        return
    raw_value = float(self.door_leaf_thickness)
    snapped_value = max(0.1, round(raw_value / 0.05) * 0.05)
    if abs(raw_value - snapped_value) < 1e-9:
        return
    self.door_sync_lock = True
    try:
        self.door_leaf_thickness = snapped_value
    finally:
        self.door_sync_lock = False


def _on_door_min_edge_offset_changed(self, _context):
    """Сразу снапит минимальный отступ двери от края стены к сетке 0.25."""
    _quantize_door_value(self, "door_min_edge_offset")


def _on_door_min_corner_offset_changed(self, _context):
    """Сразу снапит минимальный отступ двери от угла к сетке 0.25."""
    _quantize_door_value(self, "door_min_corner_offset")


def _quantize_window_value(props, attr_name: str) -> None:
    """Приводит одно window-свойство к сетке 0.25 без рекурсивной синхронизации."""
    if getattr(props, "window_sync_lock", False):
        return
    raw_value = float(getattr(props, attr_name))
    snapped_value = max(0.25, quantize_025(raw_value))
    if abs(raw_value - snapped_value) < 1e-9:
        return
    props.window_sync_lock = True
    try:
        setattr(props, attr_name, snapped_value)
    finally:
        props.window_sync_lock = False


def _on_window_width_changed(self, _context):
    """Сразу снапит ширину окна к сетке 0.25."""
    _quantize_window_value(self, "window_width")


def _on_window_height_changed(self, _context):
    """Сразу снапит высоту окна к сетке 0.25."""
    _quantize_window_value(self, "window_height")


def _on_window_sill_height_changed(self, _context):
    """Сразу снапит высоту подоконника к сетке 0.25."""
    _quantize_window_value(self, "window_sill_height")


def _on_window_min_corner_offset_changed(self, _context):
    """Сразу снапит минимальный отступ окна от угла к сетке 0.25."""
    _quantize_window_value(self, "window_min_corner_offset")


def _on_window_min_door_offset_changed(self, _context):
    """Сразу снапит минимальный отступ окна от двери к сетке 0.25."""
    _quantize_window_value(self, "window_min_door_offset")


def _on_window_min_partition_offset_changed(self, _context):
    """Сразу снапит минимальный отступ окна от внутренней перегородки к сетке 0.25."""
    _quantize_window_value(self, "window_min_partition_offset")


def _on_window_min_edge_offset_changed(self, _context):
    """Сразу снапит минимальный отступ окна от края фасада к сетке 0.25."""
    _quantize_window_value(self, "window_min_edge_offset")


def _quantize_stair_value(props, attr_name: str) -> None:
    """Приводит stair-свойство к сетке 0.25 без рекурсивной синхронизации."""
    if getattr(props, "stair_sync_lock", False):
        return
    raw_value = float(getattr(props, attr_name))
    snapped_value = max(0.25, quantize_025(raw_value))
    if abs(raw_value - snapped_value) < 1e-9:
        return
    props.stair_sync_lock = True
    try:
        setattr(props, attr_name, snapped_value)
    finally:
        props.stair_sync_lock = False


def _on_stair_width_changed(self, _context):
    _quantize_stair_value(self, "stair_width")


def _on_stair_landing_size_changed(self, _context):
    _quantize_stair_value(self, "stair_landing_size")


def _on_stair_mid_landing_size_changed(self, _context):
    _quantize_stair_value(self, "stair_mid_landing_size")


def _on_stair_tread_depth_changed(self, _context):
    _quantize_stair_value(self, "stair_tread_depth")


def _on_stair_min_free_area_changed(self, _context):
    _quantize_stair_value(self, "stair_min_free_area")


def _on_stair_door_clearance_changed(self, _context):
    _quantize_stair_value(self, "stair_door_clearance")


def _on_stair_window_clearance_changed(self, _context):
    _quantize_stair_value(self, "stair_window_clearance")


def _on_stair_riser_height_changed(self, _context):
    if getattr(self, "stair_sync_lock", False):
        return
    raw_value = float(self.stair_riser_height)
    snapped_value = max(0.05, round(raw_value / 0.01) * 0.01)
    if abs(raw_value - snapped_value) < 1e-9:
        return
    self.stair_sync_lock = True
    try:
        self.stair_riser_height = snapped_value
    finally:
        self.stair_sync_lock = False


def _on_railing_height_changed(self, _context):
    _quantize_border_value(self, "railing_height")


def _on_railing_post_size_changed(self, _context):
    if getattr(self, "railing_sync_lock", False):
        return
    raw_value = float(self.railing_post_size)
    snapped_value = max(0.02, round(raw_value / 0.01) * 0.01)
    if abs(raw_value - snapped_value) < 1e-9:
        return
    self.railing_sync_lock = True
    try:
        self.railing_post_size = snapped_value
    finally:
        self.railing_sync_lock = False


def _on_railing_rail_thickness_changed(self, _context):
    if getattr(self, "railing_sync_lock", False):
        return
    raw_value = float(self.railing_rail_thickness)
    snapped_value = max(0.01, round(raw_value / 0.01) * 0.01)
    if abs(raw_value - snapped_value) < 1e-9:
        return
    self.railing_sync_lock = True
    try:
        self.railing_rail_thickness = snapped_value
    finally:
        self.railing_sync_lock = False


def _quantize_border_value(props, attr_name: str) -> None:
    """Приводит одно border-свойство к сетке 0.25 без рекурсивного зацикливания."""
    if getattr(props, "border_sync_lock", False):
        return
    raw_value = float(getattr(props, attr_name))
    snapped_value = max(0.25, quantize_025(raw_value))
    if abs(raw_value - snapped_value) < 1e-9:
        return
    props.border_sync_lock = True
    try:
        setattr(props, attr_name, snapped_value)
    finally:
        props.border_sync_lock = False


def _on_floor_band_depth_changed(self, _context):
    _quantize_border_value(self, "floor_band_depth")


def _on_floor_band_height_changed(self, _context):
    _quantize_border_value(self, "floor_band_height")


def _on_roof_border_depth_changed(self, _context):
    _quantize_border_value(self, "roof_border_depth")


def _on_roof_border_height_changed(self, _context):
    _quantize_border_value(self, "roof_border_height")


def _on_min_room_side_changed(self, _context):
    """Снапит минимальную сторону комнаты к шагу 0.5 м."""
    raw_value = float(self.min_room_side_m)
    snapped_value = max(1.0, round(raw_value * 2.0) / 2.0)
    if abs(raw_value - snapped_value) < 1e-9:
        return
    self.min_room_side_m = snapped_value


def apply_defaults_to_props(props) -> None:
    """Заполняет все свойства аддона исходными значениями.

    Как это работает:
    функция не ограничивается публичными настройками генерации, а также
    сбрасывает скрытые поля редактора атласа и временные флаги синхронизации.
    За счёт этого новое состояние эквивалентно только что зарегистрированному
    аддону, а не частичному сбросу отдельных параметров.
    """
    props.delete_old = DEFAULTS["DELETE_OLD"]
    props.randomize_seed_each_build = DEFAULTS["RANDOMIZE_SEED_EACH_BUILD"]
    props.collection_name = DEFAULTS["COLLECTION_NAME"]
    props.seed = DEFAULTS["SEED"]
    props.target_room_count = DEFAULTS["TARGET_ROOM_COUNT"]
    props.min_room_side_m = DEFAULTS["MIN_ROOM_SIDE_M"]
    props.house_scale = DEFAULTS["HOUSE_SCALE"]
    props.text_size = DEFAULTS["TEXT_SIZE"]
    props.shape_mode = DEFAULTS["SHAPE_MODE"]
    props.story_count = DEFAULTS["STORY_COUNT"]
    props.story_layout_mode = DEFAULTS["STORY_LAYOUT_MODE"]
    props.vertical_profile_mode = DEFAULTS["VERTICAL_PROFILE_MODE"]
    props.vertical_profile_strength = DEFAULTS["VERTICAL_PROFILE_STRENGTH"]
    props.floor_bands_enabled = DEFAULTS["FLOOR_BANDS_ENABLED"]
    props.floor_band_depth = DEFAULTS["FLOOR_BAND_DEPTH"]
    props.floor_band_height = DEFAULTS["FLOOR_BAND_HEIGHT"]
    props.roof_border_enabled = DEFAULTS["ROOF_BORDER_ENABLED"]
    props.roof_border_depth = DEFAULTS["ROOF_BORDER_DEPTH"]
    props.roof_border_height = DEFAULTS["ROOF_BORDER_HEIGHT"]
    props.atlas_enabled = DEFAULTS["ATLAS_ENABLED"]
    props.atlas_manifest_path = DEFAULTS["ATLAS_MANIFEST_PATH"]
    props.atlas_image_path = DEFAULTS["ATLAS_IMAGE_PATH"]
    props.atlas_include_interior_walls = DEFAULTS["ATLAS_INCLUDE_INTERIOR_WALLS"]
    props.atlas_random_pick = DEFAULTS["ATLAS_RANDOM_PICK"]
    props.decals_enabled = DEFAULTS["DECALS_ENABLED"]
    props.decal_manifest_path = DEFAULTS["DECAL_MANIFEST_PATH"]
    props.decal_image_path = DEFAULTS["DECAL_IMAGE_PATH"]
    props.decal_density = DEFAULTS["DECAL_DENSITY"]
    props.decal_enable_streaks = DEFAULTS["DECAL_ENABLE_STREAKS"]
    props.outer_walls_enabled = DEFAULTS["OUTER_WALLS_ENABLED"]
    props.wall_height = DEFAULTS["WALL_HEIGHT"]
    props.wall_module_width = DEFAULTS["WALL_MODULE_WIDTH"]
    props.wall_thickness = DEFAULTS["WALL_THICKNESS"]
    props.doors_enabled = DEFAULTS["DOORS_ENABLED"]
    props.interior_door_width = DEFAULTS["INTERIOR_DOOR_WIDTH"]
    props.interior_door_height = DEFAULTS["INTERIOR_DOOR_HEIGHT"]
    props.entry_door_width = DEFAULTS["ENTRY_DOOR_WIDTH"]
    props.entry_door_height = DEFAULTS["ENTRY_DOOR_HEIGHT"]
    props.door_leaf_thickness = DEFAULTS["DOOR_LEAF_THICKNESS"]
    props.door_min_edge_offset = DEFAULTS["DOOR_MIN_EDGE_OFFSET"]
    props.door_min_corner_offset = DEFAULTS["DOOR_MIN_CORNER_OFFSET"]
    props.windows_enabled = DEFAULTS["WINDOWS_ENABLED"]
    props.window_width = DEFAULTS["WINDOW_WIDTH"]
    props.window_height = DEFAULTS["WINDOW_HEIGHT"]
    props.window_sill_height = DEFAULTS["WINDOW_SILL_HEIGHT"]
    props.window_min_corner_offset = DEFAULTS["WINDOW_MIN_CORNER_OFFSET"]
    props.window_min_door_offset = DEFAULTS["WINDOW_MIN_DOOR_OFFSET"]
    props.window_min_partition_offset = DEFAULTS["WINDOW_MIN_PARTITION_OFFSET"]
    props.window_min_edge_offset = DEFAULTS["WINDOW_MIN_EDGE_OFFSET"]
    props.stairs_enabled = DEFAULTS["STAIRS_ENABLED"]
    props.stair_mode = DEFAULTS["STAIR_MODE"]
    props.generate_stair_nav_checkpoints = DEFAULTS["GENERATE_STAIR_NAV_CHECKPOINTS"]
    props.stair_width = DEFAULTS["STAIR_WIDTH"]
    props.stair_landing_size = DEFAULTS["STAIR_LANDING_SIZE"]
    props.stair_mid_landing_size = DEFAULTS["STAIR_MID_LANDING_SIZE"]
    props.stair_riser_height = DEFAULTS["STAIR_RISER_HEIGHT"]
    props.stair_tread_depth = DEFAULTS["STAIR_TREAD_DEPTH"]
    props.stair_min_free_area = DEFAULTS["STAIR_MIN_FREE_AREA"]
    props.stair_door_clearance = DEFAULTS["STAIR_DOOR_CLEARANCE"]
    props.stair_window_clearance = DEFAULTS["STAIR_WINDOW_CLEARANCE"]
    props.roof_railing_enabled = DEFAULTS["ROOF_RAILING_ENABLED"]
    props.railing_height = DEFAULTS["RAILING_HEIGHT"]
    props.railing_post_size = DEFAULTS["RAILING_POST_SIZE"]
    props.railing_rail_thickness = DEFAULTS["RAILING_RAIL_THICKNESS"]
    props.railing_rail_count = DEFAULTS["RAILING_RAIL_COUNT"]
    props.atlas_manifest_json = ""
    props.atlas_sync_lock = False
    props.wall_sync_lock = False
    props.door_sync_lock = False
    props.window_sync_lock = False
    props.stair_sync_lock = False
    props.railing_sync_lock = False
    props.border_sync_lock = False
    props.atlas_category = "floors"
    props.atlas_tile = ""
    props.atlas_tile_id = ""
    props.atlas_x = 0
    props.atlas_y = 0
    props.atlas_w = 0
    props.atlas_h = 0
    props.atlas_tile_width_m = 1.0
    props.atlas_tile_height_m = 1.0
    props.atlas_window_offset_x = 0.0
    props.atlas_window_offset_y = 0.0
    props.atlas_window_width_scale = 1.0
    props.atlas_window_height_scale = 1.0
    props.atlas_door_offset_x = 0.0
    props.atlas_door_offset_y = 0.0
    props.atlas_door_width_scale = 1.0
    props.atlas_door_height_scale = 1.0


class FloorplanV2Settings(bpy.types.PropertyGroup):
    """Центральное хранилище пользовательских настроек аддона в Blender Scene."""

    delete_old: BoolProperty(name="Удалять старое", description="Перед генерацией удалить ранее созданные объекты", default=DEFAULTS["DELETE_OLD"])
    randomize_seed_each_build: BoolProperty(
        name="Новый seed",
        description="Перед каждой генерацией случайно менять seed",
        default=DEFAULTS["RANDOMIZE_SEED_EACH_BUILD"],
    )
    collection_name: StringProperty(name="Имя коллекции", description="Коллекция Blender для нового генератора", default=DEFAULTS["COLLECTION_NAME"])
    seed: IntProperty(name="Seed", description="Зерно генерации формы", default=DEFAULTS["SEED"], min=0)
    target_room_count: IntProperty(name="Количество комнат", description="Влияет на размер и сложность footprint", default=DEFAULTS["TARGET_ROOM_COUNT"], min=1, soft_max=30)
    min_room_side_m: FloatProperty(
        name="Мин. сторона комнаты",
        description="Минимальная допустимая ширина комнаты и узких участков формы, в метрах",
        default=DEFAULTS["MIN_ROOM_SIDE_M"],
        min=1.0,
        soft_max=8.0,
        precision=1,
        step=50,
        update=_on_min_room_side_changed,
    )
    house_scale: FloatProperty(name="Масштаб дома", description="Масштаб footprint", default=DEFAULTS["HOUSE_SCALE"], min=0.5, soft_max=3.0, step=10)
    text_size: FloatProperty(name="Размер подписей", description="Зарезервировано под будущие подписи", default=DEFAULTS["TEXT_SIZE"], min=0.05, soft_max=2.0)
    shape_mode: EnumProperty(name="Форма", description="Базовая форма дома", items=SHAPE_ITEMS, default=DEFAULTS["SHAPE_MODE"])
    story_count: IntProperty(
        name="Количество этажей",
        description="Сколько этажей будет сгенерировано на основе одного базового footprint",
        default=DEFAULTS["STORY_COUNT"],
        min=1,
        soft_max=10,
    )
    story_layout_mode: EnumProperty(
        name="Режим планировки этажей",
        description="Одинаковая seed-логика планировки на всех этажах или независимая генерация по story seed",
        items=STORY_LAYOUT_ITEMS,
        default=DEFAULTS["STORY_LAYOUT_MODE"],
    )
    vertical_profile_mode: EnumProperty(
        name="Вертикальный профиль",
        description="Как footprint меняется между этажами",
        items=VERTICAL_PROFILE_ITEMS,
        default=DEFAULTS["VERTICAL_PROFILE_MODE"],
    )
    vertical_profile_strength: FloatProperty(
        name="Сила профиля",
        description="Насколько сильно вертикальный профиль меняет outline между этажами",
        default=DEFAULTS["VERTICAL_PROFILE_STRENGTH"],
        min=0.0,
        max=1.0,
        precision=2,
        subtype="FACTOR",
    )
    floor_bands_enabled: BoolProperty(
        name="Включить межэтажные бордюры",
        description="Строить внешний горизонтальный пояс между этажами по реальному внешнему контуру",
        default=DEFAULTS["FLOOR_BANDS_ENABLED"],
    )
    floor_band_depth: FloatProperty(
        name="Глубина межэтажного бордюра",
        description="Глубина внешнего межэтажного пояса. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["FLOOR_BAND_DEPTH"],
        min=0.10,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_floor_band_depth_changed,
    )
    floor_band_height: FloatProperty(
        name="Высота межэтажного бордюра",
        description="Высота внешнего межэтажного пояса. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["FLOOR_BAND_HEIGHT"],
        min=0.10,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_floor_band_height_changed,
    )
    roof_border_enabled: BoolProperty(
        name="Включить кровельные бордюры",
        description="Строить внешний бордюр по верхнему краю крыши",
        default=DEFAULTS["ROOF_BORDER_ENABLED"],
    )
    roof_border_depth: FloatProperty(
        name="Глубина кровельного бордюра",
        description="Глубина кровельного бордюра. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["ROOF_BORDER_DEPTH"],
        min=0.10,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_roof_border_depth_changed,
    )
    roof_border_height: FloatProperty(
        name="Высота кровельного бордюра",
        description="Высота кровельного бордюра. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["ROOF_BORDER_HEIGHT"],
        min=0.10,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_roof_border_height_changed,
    )

    atlas_enabled: BoolProperty(name="Включить атлас", description="Использовать atlas manifest.json и atlas image для пола", default=DEFAULTS["ATLAS_ENABLED"])
    atlas_manifest_path: StringProperty(name="Путь к manifest.json", description="Путь к atlas manifest.json", default=DEFAULTS["ATLAS_MANIFEST_PATH"], subtype="FILE_PATH")
    atlas_image_path: StringProperty(name="Путь к изображению атласа", description="Необязательный путь к atlas image. Если пусто, будет взят из meta.source_image", default=DEFAULTS["ATLAS_IMAGE_PATH"], subtype="FILE_PATH")
    atlas_include_interior_walls: BoolProperty(name="Включать внутренние стены", description="Совместимое свойство старого атласа. На этом этапе не используется", default=DEFAULTS["ATLAS_INCLUDE_INTERIOR_WALLS"])
    atlas_random_pick: BoolProperty(name="Случайный выбор тайла", description="Брать случайный тайл из категории при отсутствии принудительного id", default=DEFAULTS["ATLAS_RANDOM_PICK"])
    decals_enabled: BoolProperty(
        name="Включить декали",
        description="Генерировать отдельные фасадные decal planes поверх наружных стен",
        default=DEFAULTS["DECALS_ENABLED"],
    )
    decal_manifest_path: StringProperty(
        name="Путь к decal manifest.json",
        description="Путь к JSON-манифесту декалей. Если изображение не указано, оно берётся из meta.source_image",
        default=DEFAULTS["DECAL_MANIFEST_PATH"],
        subtype="FILE_PATH",
    )
    decal_image_path: StringProperty(
        name="Путь к изображению декалей",
        description="Необязательный путь к decal atlas image. Если пусто, берётся из meta.source_image",
        default=DEFAULTS["DECAL_IMAGE_PATH"],
        subtype="FILE_PATH",
    )
    decal_density: FloatProperty(
        name="Плотность подтёков",
        description="Вероятность поставить подтёк в каждом метровом слоте фасада под крышей",
        default=DEFAULTS["DECAL_DENSITY"],
        min=0.0,
        max=1.0,
        precision=2,
        subtype="FACTOR",
    )
    decal_enable_streaks: BoolProperty(
        name="Подтёки под крышей",
        description="Генерировать вертикальные streak decals по верхнему краю наружных стен",
        default=DEFAULTS["DECAL_ENABLE_STREAKS"],
    )

    outer_walls_enabled: BoolProperty(name="Включить внешние стены", description="Строить внешние стены по реальному периметру footprint", default=DEFAULTS["OUTER_WALLS_ENABLED"])
    wall_height: FloatProperty(
        name="Высота стены",
        description="Высота внешней стены. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WALL_HEIGHT"],
        min=0.25,
        soft_max=12.0,
        precision=2,
        step=25,
        update=_on_wall_height_changed,
    )
    wall_module_width: FloatProperty(
        name="Ширина стенового модуля",
        description="Длина одного модульного сегмента стены. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WALL_MODULE_WIDTH"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_wall_module_width_changed,
    )
    wall_thickness: FloatProperty(
        name="Толщина стены",
        description="Толщина внешней стены. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WALL_THICKNESS"],
        min=0.25,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_wall_thickness_changed,
    )
    doors_enabled: BoolProperty(name="Включить двери", description="Строить входную и межкомнатные двери по уже найденным стенам и границам комнат", default=DEFAULTS["DOORS_ENABLED"])
    interior_door_width: FloatProperty(
        name="Ширина межкомнатной",
        description="Ширина межкомнатной двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["INTERIOR_DOOR_WIDTH"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_interior_door_width_changed,
    )
    interior_door_height: FloatProperty(
        name="Высота межкомнатной",
        description="Высота межкомнатной двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["INTERIOR_DOOR_HEIGHT"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_interior_door_height_changed,
    )
    entry_door_width: FloatProperty(
        name="Ширина входной",
        description="Ширина входной двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["ENTRY_DOOR_WIDTH"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_entry_door_width_changed,
    )
    entry_door_height: FloatProperty(
        name="Высота входной",
        description="Высота входной двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["ENTRY_DOOR_HEIGHT"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_entry_door_height_changed,
    )
    door_leaf_thickness: FloatProperty(
        name="Толщина створки",
        description="Толщина дверной створки. Для двери используется отдельный шаг 0.05 м, минимум 0.1 м",
        default=DEFAULTS["DOOR_LEAF_THICKNESS"],
        min=0.1,
        soft_max=1.0,
        precision=2,
        step=5,
        update=_on_door_leaf_thickness_changed,
    )
    door_min_edge_offset: FloatProperty(
        name="Отступ от края",
        description="Минимальный отступ двери от конца подходящего стенового сегмента. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["DOOR_MIN_EDGE_OFFSET"],
        min=0.25,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_door_min_edge_offset_changed,
    )
    door_min_corner_offset: FloatProperty(
        name="Отступ от угла",
        description="Минимальный отступ двери от угла. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["DOOR_MIN_CORNER_OFFSET"],
        min=0.25,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_door_min_corner_offset_changed,
    )
    windows_enabled: BoolProperty(name="Включить окна", description="Строить внешние окна только по наружным стенам", default=DEFAULTS["WINDOWS_ENABLED"])
    window_width: FloatProperty(
        name="Ширина окна",
        description="Ширина окна. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_WIDTH"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_window_width_changed,
    )
    window_height: FloatProperty(
        name="Высота окна",
        description="Высота окна. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_HEIGHT"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_window_height_changed,
    )
    window_sill_height: FloatProperty(
        name="Высота подоконника",
        description="Высота подоконника. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_SILL_HEIGHT"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_window_sill_height_changed,
    )
    window_min_corner_offset: FloatProperty(
        name="Отступ от угла",
        description="Минимальный отступ окна от угла дома. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_MIN_CORNER_OFFSET"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_window_min_corner_offset_changed,
    )
    window_min_door_offset: FloatProperty(
        name="Отступ от двери",
        description="Минимальный отступ окна от входной двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_MIN_DOOR_OFFSET"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_window_min_door_offset_changed,
    )
    window_min_partition_offset: FloatProperty(
        name="Отступ от перегородки",
        description="Минимальный отступ окна от точки примыкания внутренней перегородки. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_MIN_PARTITION_OFFSET"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_window_min_partition_offset_changed,
    )
    window_min_edge_offset: FloatProperty(
        name="Отступ от края фасада",
        description="Минимальный отступ окна от края непрерывного фасадного участка. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["WINDOW_MIN_EDGE_OFFSET"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_window_min_edge_offset_changed,
    )
    stairs_enabled: BoolProperty(
        name="Включить лестницы",
        description="Строить лестницы между этажами для всех этажей, кроме последнего",
        default=DEFAULTS["STAIRS_ENABLED"],
    )
    stair_mode: EnumProperty(
        name="Тип лестницы",
        description="Режим генерации лестницы: внутренняя или внешняя",
        items=STAIR_MODE_ITEMS,
        default=DEFAULTS["STAIR_MODE"],
    )
    generate_stair_nav_checkpoints: BoolProperty(
        name="Nav checkpoints",
        description="Создавать редактируемые контрольные точки навигации для лестниц",
        default=DEFAULTS["GENERATE_STAIR_NAV_CHECKPOINTS"],
    )
    stair_width: FloatProperty(
        name="Ширина лестницы",
        description="Полезная ширина марша. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_WIDTH"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_stair_width_changed,
    )
    stair_landing_size: FloatProperty(
        name="Площадка лестницы",
        description="Размер верхней площадки лестницы. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_LANDING_SIZE"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_stair_landing_size_changed,
    )
    stair_mid_landing_size: FloatProperty(
        name="Промежуточная площадка",
        description="Размер разворотной площадки. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_MID_LANDING_SIZE"],
        min=0.25,
        soft_max=4.0,
        precision=2,
        step=25,
        update=_on_stair_mid_landing_size_changed,
    )
    stair_riser_height: FloatProperty(
        name="Высота подступенка",
        description="Высота одной ступени. Значение снапится к шагу 0.01 м",
        default=DEFAULTS["STAIR_RISER_HEIGHT"],
        min=0.05,
        soft_max=0.3,
        precision=2,
        step=1,
        update=_on_stair_riser_height_changed,
    )
    stair_tread_depth: FloatProperty(
        name="Глубина проступи",
        description="Глубина проступи. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_TREAD_DEPTH"],
        min=0.25,
        soft_max=1.5,
        precision=2,
        step=25,
        update=_on_stair_tread_depth_changed,
    )
    stair_min_free_area: FloatProperty(
        name="Мин. свободная площадь",
        description="Минимум площади, который должен оставаться в комнате после установки лестницы",
        default=DEFAULTS["STAIR_MIN_FREE_AREA"],
        min=1.0,
        soft_max=30.0,
        precision=2,
        step=25,
        update=_on_stair_min_free_area_changed,
    )
    stair_door_clearance: FloatProperty(
        name="Отступ от двери",
        description="Минимальный отступ лестницы от двери. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_DOOR_CLEARANCE"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_stair_door_clearance_changed,
    )
    stair_window_clearance: FloatProperty(
        name="Отступ от окна",
        description="Минимальный отступ лестницы от окна. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["STAIR_WINDOW_CLEARANCE"],
        min=0.25,
        soft_max=3.0,
        precision=2,
        step=25,
        update=_on_stair_window_clearance_changed,
    )
    roof_railing_enabled: BoolProperty(
        name="Включить ограждение на крыше",
        description="Строить ограждение по реальному контуру крыши верхнего этажа",
        default=DEFAULTS["ROOF_RAILING_ENABLED"],
    )
    railing_height: FloatProperty(
        name="Высота ограждения",
        description="Высота ограждения на крыше. Значение квантуется к сетке 0.25 м",
        default=DEFAULTS["RAILING_HEIGHT"],
        min=0.25,
        soft_max=2.0,
        precision=2,
        step=25,
        update=_on_railing_height_changed,
    )
    railing_post_size: FloatProperty(
        name="Толщина стойки",
        description="Сечение вертикальной стойки. Значение снапится к шагу 0.01 м",
        default=DEFAULTS["RAILING_POST_SIZE"],
        min=0.02,
        soft_max=0.3,
        precision=2,
        step=1,
        update=_on_railing_post_size_changed,
    )
    railing_rail_thickness: FloatProperty(
        name="Толщина перекладины",
        description="Толщина перекладины. Значение снапится к шагу 0.01 м",
        default=DEFAULTS["RAILING_RAIL_THICKNESS"],
        min=0.01,
        soft_max=0.2,
        precision=2,
        step=1,
        update=_on_railing_rail_thickness_changed,
    )
    railing_rail_count: IntProperty(
        name="Количество перекладин",
        description="Сколько горизонтальных перекладин строить по высоте",
        default=DEFAULTS["RAILING_RAIL_COUNT"],
        min=1,
        soft_max=6,
    )

    atlas_manifest_json: StringProperty(name="Atlas JSON", default="", options={"HIDDEN"})
    atlas_sync_lock: BoolProperty(name="Atlas Sync Lock", default=False, options={"HIDDEN"})
    wall_sync_lock: BoolProperty(name="Wall Sync Lock", default=False, options={"HIDDEN"})
    door_sync_lock: BoolProperty(name="Door Sync Lock", default=False, options={"HIDDEN"})
    window_sync_lock: BoolProperty(name="Window Sync Lock", default=False, options={"HIDDEN"})
    stair_sync_lock: BoolProperty(name="Stair Sync Lock", default=False, options={"HIDDEN"})
    railing_sync_lock: BoolProperty(name="Railing Sync Lock", default=False, options={"HIDDEN"})
    border_sync_lock: BoolProperty(name="Border Sync Lock", default=False, options={"HIDDEN"})
    atlas_category: EnumProperty(name="Категория", description="Категория тайлов в manifest.json", items=atlas.ATLAS_CATEGORIES, default="floors", update=_on_atlas_category_changed)
    atlas_tile: EnumProperty(name="Тайл", description="Выбранный тайл внутри категории", items=atlas.tile_items, update=_on_atlas_tile_changed)
    atlas_tile_id: StringProperty(name="ID тайла", description="Идентификатор выбранного тайла", default="")
    atlas_x: IntProperty(name="X", default=0, min=0)
    atlas_y: IntProperty(name="Y", default=0, min=0)
    atlas_w: IntProperty(name="W", default=0, min=0)
    atlas_h: IntProperty(name="H", default=0, min=0)
    atlas_tile_width_m: FloatProperty(name="Tile Width (m)", default=1.0, min=0.01)
    atlas_tile_height_m: FloatProperty(name="Tile Height (m)", default=1.0, min=0.01)

    atlas_window_offset_x: FloatProperty(name="Смещение X", default=0.0)
    atlas_window_offset_y: FloatProperty(name="Смещение Y", default=0.0)
    atlas_window_width_scale: FloatProperty(name="Ширина", default=1.0, min=0.01)
    atlas_window_height_scale: FloatProperty(name="Высота", default=1.0, min=0.01)
    atlas_door_offset_x: FloatProperty(name="Смещение X", default=0.0)
    atlas_door_offset_y: FloatProperty(name="Смещение Y", default=0.0)
    atlas_door_width_scale: FloatProperty(name="Ширина", default=1.0, min=0.01)
    atlas_door_height_scale: FloatProperty(name="Высота", default=1.0, min=0.01)


classes = (FloorplanV2Settings,)


def register():
    """Регистрирует `PropertyGroup` и добавляет pointer-свойство в `Scene`.

    Как это работает:
    сначала классы свойств объявляются Blender, после чего в тип сцены
    добавляется `floorplan_ru_v2_settings`. Благодаря этому доступ к настройкам
    появляется из операторов, панелей и остальных частей аддона через контекст.
    """
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.floorplan_ru_v2_settings = PointerProperty(type=FloorplanV2Settings)


def unregister():
    """Удаляет pointer-свойство сцены и снимает регистрацию класса настроек."""
    del bpy.types.Scene.floorplan_ru_v2_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

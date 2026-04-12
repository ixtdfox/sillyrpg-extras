
import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from . import core
from . import atlas_manifest


DEFAULTS = core._DEFAULTS


def _on_atlas_category_changed(self, context):
    atlas_manifest.sync_editor_from_manifest(self)


def _on_atlas_tile_changed(self, context):
    atlas_manifest.sync_editor_from_manifest(self)


def apply_defaults_to_props(props):
    props.delete_old = DEFAULTS["DELETE_OLD"]
    props.collection_name = DEFAULTS["COLLECTION_NAME"]
    props.wall_height = DEFAULTS["WALL_HEIGHT"]
    props.wall_thickness = DEFAULTS["WALL_THICKNESS"]
    props.floor_thickness = DEFAULTS["FLOOR_THICKNESS"]
    props.corridor_width = DEFAULTS["CORRIDOR_WIDTH"]
    props.door_width = DEFAULTS["DOOR_WIDTH"]
    props.entry_door_width = DEFAULTS["ENTRY_DOOR_WIDTH"]
    props.entry_door_thickness = DEFAULTS["ENTRY_DOOR_THICKNESS"]
    props.door_height = DEFAULTS["DOOR_HEIGHT"]
    props.stair_width = DEFAULTS["STAIR_WIDTH"]
    props.stair_landing = DEFAULTS["STAIR_LANDING"]
    props.stair_mid_landing = DEFAULTS["STAIR_MID_LANDING"]
    props.stair_riser = DEFAULTS["STAIR_RISER"]
    props.stair_tread = DEFAULTS["STAIR_TREAD"]
    props.stair_clearance = DEFAULTS["STAIR_CLEARANCE"]
    props.stair_max_parent_occupancy = DEFAULTS["STAIR_MAX_PARENT_OCCUPANCY"]
    props.stair_min_free_area = DEFAULTS["STAIR_MIN_FREE_AREA"]
    props.stair_door_clearance = DEFAULTS["STAIR_DOOR_CLEARANCE"]
    props.stair_window_clearance = DEFAULTS["STAIR_WINDOW_CLEARANCE"]
    props.window_sill_height = DEFAULTS["WINDOW_SILL_HEIGHT"]
    props.window_height = DEFAULTS["WINDOW_HEIGHT"]
    props.window_min_width = DEFAULTS["WINDOW_MIN_WIDTH"]
    props.window_end_margin = DEFAULTS["WINDOW_END_MARGIN"]
    props.window_strip_width = DEFAULTS["WINDOW_STRIP_WIDTH"]
    props.outer_margin = DEFAULTS["OUTER_MARGIN"]
    props.room_gap = DEFAULTS["ROOM_GAP"]
    props.min_room_side = DEFAULTS["MIN_ROOM_SIDE"]
    props.max_aspect = DEFAULTS["MAX_ASPECT"]
    props.text_size = DEFAULTS["TEXT_SIZE"]
    props.post_merge_min_side = DEFAULTS["POST_MERGE_MIN_SIDE"]
    props.post_merge_min_area = DEFAULTS["POST_MERGE_MIN_AREA"]
    props.post_merge_max_aspect = DEFAULTS["POST_MERGE_MAX_ASPECT"]
    props.post_merge_hard_max_aspect = DEFAULTS["POST_MERGE_HARD_MAX_ASPECT"]
    props.post_merge_edge_strip_side = DEFAULTS["POST_MERGE_EDGE_STRIP_SIDE"]
    props.post_merge_sliver_ratio = DEFAULTS["POST_MERGE_SLIVER_RATIO"]
    props.post_merge_min_shared = DEFAULTS["POST_MERGE_MIN_SHARED"]
    props.residual_min_area = DEFAULTS["RESIDUAL_MIN_AREA"]
    props.residual_long_strip_ratio = DEFAULTS["RESIDUAL_LONG_STRIP_RATIO"]
    props.residual_short_side = DEFAULTS["RESIDUAL_SHORT_SIDE"]
    props.residual_corridor_shared_bonus = DEFAULTS["RESIDUAL_CORRIDOR_SHARED_BONUS"]
    props.house_scale = DEFAULTS["HOUSE_SCALE"]
    props.target_room_count = DEFAULTS["TARGET_ROOM_COUNT"]
    props.auto_random_seed = DEFAULTS["AUTO_RANDOM_SEED"]
    props.seed = DEFAULTS["SEED"]
    props.min_floors = DEFAULTS["MIN_FLOORS"]
    props.max_floors = DEFAULTS["MAX_FLOORS"]
    props.building_mode = DEFAULTS["BUILDING_MODE"]
    props.shape_mode = DEFAULTS["SHAPE_MODE"]
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
    props.decal_enable_grime = False
    props.decal_enable_ground_strips = False
    props.decal_enable_cracks = False
    props.decal_enable_corner_dirt = False
    props.decal_enable_edge_dirt = False
    props.debug_log_enabled = DEFAULTS["DEBUG_LOG_ENABLED"]
    props.atlas_manifest_json = ""
    props.atlas_category = "walls"
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
    props.modular_tiles_enabled = DEFAULTS["MODULAR_TILES_ENABLED"]
    props.wall_tile_width = DEFAULTS["WALL_TILE_WIDTH"]
    props.surface_tile_size = DEFAULTS["SURFACE_TILE_SIZE"]
    props.roof_border_enabled = DEFAULTS["ROOF_BORDER_ENABLED"]
    props.roof_border_width = DEFAULTS["ROOF_BORDER_WIDTH"]
    props.roof_border_height = DEFAULTS["ROOF_BORDER_HEIGHT"]
    props.roof_border_tile_category = DEFAULTS["ROOF_BORDER_TILE_CATEGORY"]
    props.roof_border_tile_id = DEFAULTS["ROOF_BORDER_TILE_ID"]
    props.floor_band_enabled = DEFAULTS["FLOOR_BAND_ENABLED"]
    props.floor_band_depth = DEFAULTS["FLOOR_BAND_DEPTH"]
    props.floor_band_height = DEFAULTS["FLOOR_BAND_HEIGHT"]
    props.floor_band_tile_category = DEFAULTS["FLOOR_BAND_TILE_CATEGORY"]
    props.floor_band_tile_id = DEFAULTS["FLOOR_BAND_TILE_ID"]


class FloorplanSettings(bpy.types.PropertyGroup):
    delete_old: BoolProperty(name="Удалять старое", description="Перед генерацией удалить ранее созданные объекты из коллекции", default=DEFAULTS["DELETE_OLD"])
    collection_name: StringProperty(name="Имя коллекции", description="Коллекция Blender, в которую будут складываться все созданные объекты", default=DEFAULTS["COLLECTION_NAME"])

    wall_height: FloatProperty(name="Высота стен", description="Высота стен этажа в метрах", default=DEFAULTS["WALL_HEIGHT"], min=1.5, soft_max=6.0)
    wall_thickness: FloatProperty(name="Толщина стен", description="Толщина наружных и внутренних стен в метрах", default=DEFAULTS["WALL_THICKNESS"], min=0.05, soft_max=1.0)
    floor_thickness: FloatProperty(name="Толщина перекрытия", description="Толщина пола/перекрытия в метрах", default=DEFAULTS["FLOOR_THICKNESS"], min=0.02, soft_max=0.5)
    corridor_width: FloatProperty(name="Ширина коридора", description="Базовая ширина коридора в метрах", default=DEFAULTS["CORRIDOR_WIDTH"], min=0.6, soft_max=4.0)
    door_width: FloatProperty(name="Ширина обычной двери", description="Ширина внутренних дверных проёмов", default=DEFAULTS["DOOR_WIDTH"], min=0.5, soft_max=2.0)
    entry_door_width: FloatProperty(name="Ширина входной двери", description="Ширина уличного дверного проёма", default=DEFAULTS["ENTRY_DOOR_WIDTH"], min=0.5, soft_max=2.0)
    entry_door_thickness: FloatProperty(name="Толщина входной створки", description="Толщина полотна входной двери", default=DEFAULTS["ENTRY_DOOR_THICKNESS"], min=0.01, soft_max=0.2)
    door_height: FloatProperty(name="Высота двери", description="Высота дверных проёмов", default=DEFAULTS["DOOR_HEIGHT"], min=1.5, soft_max=3.0)

    stair_width: FloatProperty(name="Ширина лестницы", description="Полезная ширина марша лестницы", default=DEFAULTS["STAIR_WIDTH"], min=0.6, soft_max=3.0)
    stair_landing: FloatProperty(name="Площадка лестницы", description="Длина разворотной площадки лестницы", default=DEFAULTS["STAIR_LANDING"], min=0.4, soft_max=3.0)
    stair_mid_landing: FloatProperty(name="Средняя площадка", description="Размер центральной площадки для разворотной лестницы", default=DEFAULTS["STAIR_MID_LANDING"], min=0.4, soft_max=4.0)
    stair_riser: FloatProperty(name="Высота подступенка", description="Высота одной ступени", default=DEFAULTS["STAIR_RISER"], min=0.1, soft_max=0.3)
    stair_tread: FloatProperty(name="Глубина проступи", description="Глубина одной ступени", default=DEFAULTS["STAIR_TREAD"], min=0.15, soft_max=0.5)
    stair_clearance: FloatProperty(name="Отступ лестницы", description="Безопасный зазор вокруг лестничного блока", default=DEFAULTS["STAIR_CLEARANCE"], min=0.0, soft_max=1.0)
    stair_max_parent_occupancy: FloatProperty(name="Макс. доля комнаты под лестницу", description="Какую долю площади родительской комнаты разрешено занимать лестнице", default=DEFAULTS["STAIR_MAX_PARENT_OCCUPANCY"], min=0.1, max=1.0)
    stair_min_free_area: FloatProperty(name="Мин. свободная площадь", description="Минимум свободной площади, которая должна остаться после размещения лестницы", default=DEFAULTS["STAIR_MIN_FREE_AREA"], min=0.0, soft_max=30.0)
    stair_door_clearance: FloatProperty(name="Отступ лестницы от двери", description="Минимальный отступ лестницы от дверных проёмов", default=DEFAULTS["STAIR_DOOR_CLEARANCE"], min=0.0, soft_max=2.0)
    stair_window_clearance: FloatProperty(name="Отступ лестницы от окна", description="Минимальный отступ лестницы от окон и входной зоны", default=DEFAULTS["STAIR_WINDOW_CLEARANCE"], min=0.0, soft_max=2.0)

    window_sill_height: FloatProperty(name="Высота подоконника", description="Высота нижней части окна от пола", default=DEFAULTS["WINDOW_SILL_HEIGHT"], min=0.0, soft_max=2.0)
    window_height: FloatProperty(name="Высота окна", description="Высота оконного проёма", default=DEFAULTS["WINDOW_HEIGHT"], min=0.2, soft_max=3.0)
    window_min_width: FloatProperty(name="Мин. ширина окна", description="Минимально допустимая ширина окна", default=DEFAULTS["WINDOW_MIN_WIDTH"], min=1.0, soft_max=6.0, step=100, precision=0)
    window_end_margin: FloatProperty(name="Отступ окна от края", description="Минимальный отступ окна от края стены", default=DEFAULTS["WINDOW_END_MARGIN"], min=0.0, soft_max=2.0)
    window_strip_width: FloatProperty(name="Ширина узкого окна", description="Ширина узких ленточных окон для сервисных помещений", default=DEFAULTS["WINDOW_STRIP_WIDTH"], min=1.0, soft_max=6.0, step=100, precision=0)

    outer_margin: FloatProperty(name="Внешний отступ", description="Отступ комнат от внутренней грани внешней стены. Обычно 0 для плотного примыкания", default=DEFAULTS["OUTER_MARGIN"], min=0.0, soft_max=2.0)
    room_gap: FloatProperty(name="Зазор между комнатами", description="Дополнительный зазор между соседними комнатами", default=DEFAULTS["ROOM_GAP"], min=0.0, soft_max=1.0)
    min_room_side: FloatProperty(name="Мин. сторона комнаты", description="Минимальный размер стороны прямоугольной комнаты", default=DEFAULTS["MIN_ROOM_SIDE"], min=1.0, soft_max=10.0)
    max_aspect: FloatProperty(name="Макс. соотношение сторон", description="Максимально допустимое отношение длинной стороны комнаты к короткой", default=DEFAULTS["MAX_ASPECT"], min=1.0, soft_max=10.0)
    text_size: FloatProperty(name="Размер подписей", description="Размер служебных текстовых подписей в сцене", default=DEFAULTS["TEXT_SIZE"], min=0.0, soft_max=2.0)

    post_merge_min_side: FloatProperty(name="Merge: мин. сторона", description="После генерации слишком узкие комнаты объединяются, если их сторона меньше этого порога", default=DEFAULTS["POST_MERGE_MIN_SIDE"], min=0.1, soft_max=5.0)
    post_merge_min_area: FloatProperty(name="Merge: мин. площадь", description="После генерации слишком маленькие комнаты объединяются, если их площадь меньше этого порога", default=DEFAULTS["POST_MERGE_MIN_AREA"], min=0.1, soft_max=20.0)
    post_merge_max_aspect: FloatProperty(name="Merge: макс. aspect", description="Порог мягкого объединения слишком вытянутых комнат", default=DEFAULTS["POST_MERGE_MAX_ASPECT"], min=1.0, soft_max=20.0)
    post_merge_hard_max_aspect: FloatProperty(name="Merge: жёсткий aspect", description="Порог жёсткого объединения совсем вытянутых комнат", default=DEFAULTS["POST_MERGE_HARD_MAX_ASPECT"], min=1.0, soft_max=50.0)
    post_merge_edge_strip_side: FloatProperty(name="Merge: крайняя полоска", description="Если узкая полоска у внешней стены меньше этого размера, она считается кандидатом на объединение", default=DEFAULTS["POST_MERGE_EDGE_STRIP_SIDE"], min=0.1, soft_max=5.0)
    post_merge_sliver_ratio: FloatProperty(name="Merge: sliver ratio", description="Порог отношения короткой стороны к длинной для определения тонкого огрызка комнаты", default=DEFAULTS["POST_MERGE_SLIVER_RATIO"], min=0.01, max=1.0)
    post_merge_min_shared: FloatProperty(name="Merge: мин. общая грань", description="Минимальная длина общей стены, чтобы комнаты можно было объединить", default=DEFAULTS["POST_MERGE_MIN_SHARED"], min=0.0, soft_max=5.0)

    residual_min_area: FloatProperty(name="Residual: мин. площадь", description="Минимальная площадь остаточного прямоугольника, который стоит перераздать", default=DEFAULTS["RESIDUAL_MIN_AREA"], min=0.0, soft_max=10.0)
    residual_long_strip_ratio: FloatProperty(name="Residual: длинная полоска", description="Если остаток слишком вытянут, он получает повышенный приоритет перераздачи", default=DEFAULTS["RESIDUAL_LONG_STRIP_RATIO"], min=1.0, soft_max=20.0)
    residual_short_side: FloatProperty(name="Residual: короткая сторона", description="Порог короткой стороны для остаточных зон", default=DEFAULTS["RESIDUAL_SHORT_SIDE"], min=0.1, soft_max=5.0)
    residual_corridor_shared_bonus: FloatProperty(name="Residual: бонус коридора", description="Бонус при распределении остаточных зон, если они хорошо примыкают к коридору", default=DEFAULTS["RESIDUAL_CORRIDOR_SHARED_BONUS"], min=0.0, soft_max=50.0)

    house_scale: FloatProperty(name="Масштаб дома", description="Общий масштаб всех комнат. Больше 1.0 делает дом просторнее", default=DEFAULTS["HOUSE_SCALE"], min=0.2, soft_max=5.0)
    target_room_count: IntProperty(name="Целевое число комнат", description="Сколько комнат примерно пытаться разместить в доме", default=DEFAULTS["TARGET_ROOM_COUNT"], min=4, soft_max=20)
    auto_random_seed: BoolProperty(name="Случайный seed", description="Если включено, seed выбирается автоматически при каждом запуске", default=DEFAULTS["AUTO_RANDOM_SEED"])
    seed: IntProperty(name="Seed", description="Фиксированное зерно случайности. Используется, когда случайный seed выключен", default=DEFAULTS["SEED"], min=0)
    min_floors: IntProperty(name="Мин. этажей", description="Минимальное количество этажей", default=DEFAULTS["MIN_FLOORS"], min=1, soft_max=10)
    max_floors: IntProperty(name="Макс. этажей", description="Максимальное количество этажей", default=DEFAULTS["MAX_FLOORS"], min=1, soft_max=10)

    building_mode: EnumProperty(
        name="Режим этажей",
        description="Как верхние этажи наследуют габариты первого этажа",
        items=[
            ("creative", "Творческий", "Верхние этажи могут отличаться по форме и габаритам"),
            ("strict", "Строгий", "Все этажи масштабируются под габариты первого этажа"),
        ],
        default=DEFAULTS["BUILDING_MODE"],
    )
    shape_mode: EnumProperty(
        name="Форма дома",
        description="Базовый тип внешнего контура здания",
        items=[
            ("quad", "Прямоугольник", "Классический прямоугольный дом"),
            ("l", "L-форма", "Дом буквой L"),
            ("u", "U-форма", "Дом буквой U с внутренним двором"),
            ("h", "H-форма", "Дом буквой H"),
            ("t", "T-форма", "Дом буквой T"),
            ("courtyard", "Курдонёр", "Дом с центральным внутренним двором"),
            ("offset", "Смещённый", "Дом из смещённых объёмов"),
        ],
        default=DEFAULTS["SHAPE_MODE"],
    )

    atlas_enabled: BoolProperty(name="Включить атлас", description="После генерации попробовать применить текстурный атлас Stage 1", default=DEFAULTS["ATLAS_ENABLED"])
    atlas_manifest_path: StringProperty(name="Путь к manifest.json", description="Путь к JSON-манифесту атласа. Можно использовать Blender-путь вида //house_atlas.json", default=DEFAULTS["ATLAS_MANIFEST_PATH"], subtype='FILE_PATH')
    atlas_image_path: StringProperty(name="Путь к изображению атласа", description="Необязательный путь к картинке атласа. Если пусто, будет взят из manifest.meta.source_image", default=DEFAULTS["ATLAS_IMAGE_PATH"], subtype='FILE_PATH')
    atlas_include_interior_walls: BoolProperty(name="Атлас для внутренних стен", description="Если включено, атлас будет применяться и к внутренним стенам IW_/SW_", default=DEFAULTS["ATLAS_INCLUDE_INTERIOR_WALLS"])
    atlas_random_pick: BoolProperty(name="Случайный выбор тайла", description="Случайно выбирать регион из подходящей категории атласа", default=DEFAULTS["ATLAS_RANDOM_PICK"])

    atlas_manifest_json: StringProperty(name="Manifest JSON", options={'HIDDEN'})
    atlas_category: EnumProperty(name="Категория тайлов", description="Категория из manifest.json", items=atlas_manifest.category_items, update=_on_atlas_category_changed)
    atlas_tile: EnumProperty(name="Тайл", description="Конкретный тайл внутри выбранной категории", items=atlas_manifest.tile_items, update=_on_atlas_tile_changed)
    atlas_tile_id: StringProperty(name="ID тайла", description="Поле id у выбранного тайла")
    atlas_x: IntProperty(name="x", description="Координата X в атласе", min=0, default=0)
    atlas_y: IntProperty(name="y", description="Координата Y в атласе", min=0, default=0)
    atlas_w: IntProperty(name="w", description="Ширина региона в пикселях", min=0, default=0)
    atlas_h: IntProperty(name="h", description="Высота региона в пикселях", min=0, default=0)
    atlas_tile_width_m: FloatProperty(name="tile_width_m", description="Ширина тайла в метрах", min=0.001, default=1.0)
    atlas_tile_height_m: FloatProperty(name="tile_height_m", description="Высота тайла в метрах", min=0.001, default=1.0)

    atlas_window_offset_x: FloatProperty(name="offset_x", description="Смещение текстуры окна по X из placement.glass.offset_x", default=0.0, soft_min=-5.0, soft_max=5.0)
    atlas_window_offset_y: FloatProperty(name="offset_y", description="Смещение текстуры окна по Y из placement.glass.offset_y", default=0.0, soft_min=-5.0, soft_max=5.0)
    atlas_window_width_scale: FloatProperty(name="width_scale", description="Масштаб ширины оконной текстуры из placement.glass.width_scale", default=1.0, min=0.001, soft_max=5.0)
    atlas_window_height_scale: FloatProperty(name="height_scale", description="Масштаб высоты оконной текстуры из placement.glass.height_scale", default=1.0, min=0.001, soft_max=5.0)

    atlas_door_offset_x: FloatProperty(name="offset_x", description="Смещение текстуры двери по X из placement.wall_doors.offset_x", default=0.0, soft_min=-5.0, soft_max=5.0)
    atlas_door_offset_y: FloatProperty(name="offset_y", description="Смещение текстуры двери по Y из placement.wall_doors.offset_y", default=0.0, soft_min=-5.0, soft_max=5.0)
    atlas_door_width_scale: FloatProperty(name="width_scale", description="Масштаб ширины дверной текстуры из placement.wall_doors.width_scale", default=1.0, min=0.001, soft_max=5.0)
    atlas_door_height_scale: FloatProperty(name="height_scale", description="Масштаб высоты дверной текстуры из placement.wall_doors.height_scale", default=1.0, min=0.001, soft_max=5.0)

    decals_enabled: BoolProperty(name="Включить декали", description="Включить отдельный decal-atlas поверх базовых текстур", default=DEFAULTS["DECALS_ENABLED"])
    decal_manifest_path: StringProperty(name="Путь к decal manifest.json", description="Путь к JSON-манифесту декалей. Можно использовать Blender-путь вида //decal_atlas_v2.json", default=DEFAULTS["DECAL_MANIFEST_PATH"], subtype='FILE_PATH')
    decal_image_path: StringProperty(name="Путь к изображению декалей", description="Необязательный путь к PNG атласу декалей. Если пусто, будет взят из meta.source_image decal manifest.json", default=DEFAULTS["DECAL_IMAGE_PATH"], subtype='FILE_PATH')
    decal_density: FloatProperty(name="Плотность подтёков", description="Вероятность поставить подтёк на каждый 1-метровый фасадный тайл под крышей", default=DEFAULTS["DECAL_DENSITY"], min=0.0, max=1.0, subtype='FACTOR')
    decal_enable_streaks: BoolProperty(name="Подтёки под крышей", description="Ставить вертикальные подтёки только под нижней кромкой крыши", default=DEFAULTS["DECAL_ENABLE_STREAKS"])
    decal_enable_grime: BoolProperty(name="Случайные пятна", description="Устаревшая опция. Не используется в режиме подтёков под крышей", default=DEFAULTS["DECAL_ENABLE_GRIME"], options={'HIDDEN'})
    decal_enable_ground_strips: BoolProperty(name="Полосы грязи у земли", description="Устаревшая опция. Не используется в режиме подтёков под крышей", default=DEFAULTS["DECAL_ENABLE_GROUND_STRIPS"], options={'HIDDEN'})
    decal_enable_cracks: BoolProperty(name="Трещины", description="Устаревшая опция. Не используется в режиме подтёков под крышей", default=DEFAULTS["DECAL_ENABLE_CRACKS"], options={'HIDDEN'})
    decal_enable_corner_dirt: BoolProperty(name="Грязь в углах", description="Устаревшая опция. Не используется в режиме подтёков под крышей", default=DEFAULTS["DECAL_ENABLE_CORNER_DIRT"], options={'HIDDEN'})
    decal_enable_edge_dirt: BoolProperty(name="Грязь по краям", description="Устаревшая опция. Не используется в режиме подтёков под крышей", default=DEFAULTS["DECAL_ENABLE_EDGE_DIRT"], options={'HIDDEN'})
    debug_log_enabled: BoolProperty(name="Debug log", description="Писать подробный лог генерации декалей в консоль и в Blender Text: FloorPlan_Debug_Log", default=DEFAULTS["DEBUG_LOG_ENABLED"])

    modular_tiles_enabled: BoolProperty(name="Модульные 3D-тайлы", description="Собирать стены, полы и крыши из модульных тайлов вместо крупных кусков", default=DEFAULTS["MODULAR_TILES_ENABLED"])
    wall_tile_width: FloatProperty(name="Шаг стены", description="Длина одного стенового тайла вдоль стены", default=DEFAULTS["WALL_TILE_WIDTH"], min=0.1, soft_max=2.0)
    surface_tile_size: FloatProperty(name="Тайл пола/крыши", description="Размер тайла пола и крыши по X/Y", default=DEFAULTS["SURFACE_TILE_SIZE"], min=0.1, soft_max=2.0)
    roof_border_enabled: BoolProperty(name="Бортики по крыше", description="Добавлять по внешнему периметру крыши бортики из 1-метровых тайлов", default=DEFAULTS["ROOF_BORDER_ENABLED"])
    roof_border_width: FloatProperty(name="Толщина бортика", description="Толщина бортика по крыше в метрах", default=DEFAULTS["ROOF_BORDER_WIDTH"], min=0.01, soft_max=1.0)
    roof_border_height: FloatProperty(name="Высота бортика", description="Высота бортика по крыше в метрах", default=DEFAULTS["ROOF_BORDER_HEIGHT"], min=0.01, soft_max=1.0)
    roof_border_tile_category: EnumProperty(name="Категория текстуры бортика", description="Категория тайла из общего atlas manifest.json для бортиков крыши", items=atlas_manifest.ATLAS_CATEGORIES, default=DEFAULTS["ROOF_BORDER_TILE_CATEGORY"])
    roof_border_tile_id: StringProperty(name="ID тайла бортика", description="Какой id тайла использовать для бортиков крыши. Если пусто, будет случайный выбор внутри категории", default=DEFAULTS["ROOF_BORDER_TILE_ID"])
    floor_band_enabled: BoolProperty(name="Межэтажные балки", description="Добавлять горизонтальные балки по внешнему шву между этажами", default=DEFAULTS["FLOOR_BAND_ENABLED"])
    floor_band_depth: FloatProperty(name="Толщина балки", description="Насколько балка выступает от стены наружу, в метрах", default=DEFAULTS["FLOOR_BAND_DEPTH"], min=0.01, soft_max=1.0)
    floor_band_height: FloatProperty(name="Высота балки", description="Высота межэтажной балки в метрах", default=DEFAULTS["FLOOR_BAND_HEIGHT"], min=0.01, soft_max=1.0)
    floor_band_tile_category: EnumProperty(name="Категория текстуры балки", description="Категория тайла из общего atlas manifest.json для межэтажных балок", items=atlas_manifest.ATLAS_CATEGORIES, default=DEFAULTS["FLOOR_BAND_TILE_CATEGORY"])
    floor_band_tile_id: StringProperty(name="ID тайла балки", description="Какой id тайла использовать для межэтажных балок. Если пусто, будет случайный выбор внутри категории", default=DEFAULTS["FLOOR_BAND_TILE_ID"])


classes = (FloorplanSettings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.floorplan_ru_settings = PointerProperty(type=FloorplanSettings)


def unregister():
    if hasattr(bpy.types.Scene, "floorplan_ru_settings"):
        del bpy.types.Scene.floorplan_ru_settings
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

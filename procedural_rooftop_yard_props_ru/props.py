from __future__ import annotations

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import addon
from . import atlas_manifest, furniture_catalog, generator


DEFAULTS = {
    "target_collection_name": "Generated_Rooftop_Yard_Props",
    "seed": 42,
    "generation_mode": "roof",
    "clear_previous_before_generate": True,
    "scale_multiplier": 1.0,
    "detail_level": "MEDIUM",
    "density": 0.8,
    "margin_from_edge": 1.0,
    "spacing": 2.0,
    "avoid_overlaps": True,
    "service_path_width": 1.4,
    "roof_width": 14.0,
    "roof_depth": 10.0,
    "yard_width": 24.0,
    "yard_depth": 20.0,
    "building_width": 10.0,
    "building_depth": 8.0,
    "preview_columns": 5,
    "preview_spacing": 3.2,
    "preview_variants_per_type": 1,
    "atlas_image_path": atlas_manifest.addon_asset_path("rooftop_yard_atlas.png"),
    "manifest_path": atlas_manifest.addon_asset_path("rooftop_yard_manifest.json"),
    "prop_category": "all",
    "room_type": "all",
    "furniture_object_type": "all",
    "furniture_density": 30,
    "furniture_seed": 1,
    "furniture_use_atlas": True,
    "furniture_area_width": 8.0,
    "furniture_area_depth": 6.0,
    "furniture_margin": 0.4,
    "furniture_collision_padding": 0.15,
    "furniture_atlas_image_path": atlas_manifest.addon_asset_path("furniture_atlas.png"),
    "furniture_manifest_path": atlas_manifest.addon_asset_path("furniture_atlas_manifest.json"),
}


def _on_region_changed(self, _context):
    if getattr(self, "manifest_sync_lock", False):
        return
    atlas_manifest.sync_editor_from_manifest(self)


def _on_single_category_changed(self, _context):
    items = generator.PROP_TYPE_ENUM_ITEMS_BY_CATEGORY.get(self.single_category, generator.PROP_TYPE_ENUM_ITEMS)
    if not items:
        return
    valid_ids = {item[0] for item in items}
    if getattr(self, "single_prop_type", "") not in valid_ids:
        self.single_prop_type = items[0][0]


def _on_room_type_changed(self, _context):
    items = furniture_catalog.object_enum_items(self, _context)
    valid_ids = {item[0] for item in items}
    if getattr(self, "furniture_object_type", "all") not in valid_ids:
        self.furniture_object_type = "all"


def apply_defaults_to_props(props):
    props.target_collection_name = DEFAULTS["target_collection_name"]
    props.seed = DEFAULTS["seed"]
    props.generation_mode = DEFAULTS["generation_mode"]
    props.clear_previous_before_generate = DEFAULTS["clear_previous_before_generate"]
    props.scale_multiplier = DEFAULTS["scale_multiplier"]
    props.detail_level = DEFAULTS["detail_level"]
    props.density = DEFAULTS["density"]
    props.margin_from_edge = DEFAULTS["margin_from_edge"]
    props.spacing = DEFAULTS["spacing"]
    props.avoid_overlaps = DEFAULTS["avoid_overlaps"]
    props.service_path_width = DEFAULTS["service_path_width"]
    props.roof_width = DEFAULTS["roof_width"]
    props.roof_depth = DEFAULTS["roof_depth"]
    props.yard_width = DEFAULTS["yard_width"]
    props.yard_depth = DEFAULTS["yard_depth"]
    props.building_width = DEFAULTS["building_width"]
    props.building_depth = DEFAULTS["building_depth"]
    props.preview_columns = DEFAULTS["preview_columns"]
    props.preview_spacing = DEFAULTS["preview_spacing"]
    props.preview_variants_per_type = DEFAULTS["preview_variants_per_type"]
    props.include_preview_labels = True
    props.include_ground_plane = True
    props.cluster_mode = True
    props.keep_service_paths = True
    props.fence_around_yard = True
    props.equipment_zone = True
    props.generator_zone = True
    props.lighting_zone = True
    props.atlas_image_path = DEFAULTS["atlas_image_path"]
    props.manifest_path = DEFAULTS["manifest_path"]
    props.prop_category = DEFAULTS["prop_category"]
    props.room_type = DEFAULTS["room_type"]
    props.furniture_object_type = DEFAULTS["furniture_object_type"]
    props.furniture_density = DEFAULTS["furniture_density"]
    props.furniture_seed = DEFAULTS["furniture_seed"]
    props.furniture_use_atlas = DEFAULTS["furniture_use_atlas"]
    props.furniture_area_width = DEFAULTS["furniture_area_width"]
    props.furniture_area_depth = DEFAULTS["furniture_area_depth"]
    props.furniture_margin = DEFAULTS["furniture_margin"]
    props.furniture_collision_padding = DEFAULTS["furniture_collision_padding"]
    props.furniture_atlas_image_path = DEFAULTS["furniture_atlas_image_path"]
    props.furniture_manifest_path = DEFAULTS["furniture_manifest_path"]
    props.single_category = "roof_power"
    props.single_prop_type = "solar_panel_array"
    props.apply_bevels = True
    props.join_parts = False
    props.enable_solar_panels = True
    props.enable_tanks = True
    props.enable_hvac = True
    props.enable_vents = True
    props.enable_communications = True
    props.enable_warning_systems = True
    props.enable_lighting = True
    props.enable_power_equipment = True
    props.enable_fences = True
    props.enable_access = True
    props.enable_storage = True
    props.enable_surveillance = True
    props.enable_special = True
    props.manifest_json = ""
    props.manifest_sync_lock = False
    props.region_x = 0
    props.region_y = 0
    props.region_w = 128
    props.region_h = 128
    props.atlas_width = 1024
    props.atlas_height = 1024


class RooftopYardPropsSettings(bpy.types.PropertyGroup):
    target_collection_name: StringProperty(name="Имя коллекции", default=DEFAULTS["target_collection_name"])
    seed: IntProperty(name="Seed", default=DEFAULTS["seed"], min=0)
    generation_mode: EnumProperty(
        name="Режим генерации",
        items=[
            ("roof", "Крыша здания", "Генерация объектов на крыше"),
            ("yard", "Придомовая территория", "Генерация объектов вокруг здания"),
            ("roof_yard", "Крыша + территория", "Комбинированная генерация"),
            ("furniture", "Мебель и интерьер", "Генерация мебели и интерьерных объектов"),
            ("selected", "Только выбранные категории", "Работа по включённым категориям"),
        ],
        default=DEFAULTS["generation_mode"],
    )
    prop_category: EnumProperty(
        name="Категория объектов",
        items=[
            ("all", "Все", "Генерировать все категории"),
            ("rooftop", "Крыша", "Крышные объекты"),
            ("yard", "Придомовая территория", "Объекты рядом с домом"),
            ("furniture", "Мебель и интерьер", "Мебель и интерьерные объекты для комнат"),
        ],
        default=DEFAULTS["prop_category"],
    )
    clear_previous_before_generate: BoolProperty(name="Удалять прошлый результат", default=DEFAULTS["clear_previous_before_generate"])
    scale_multiplier: FloatProperty(name="Scale Multiplier", default=DEFAULTS["scale_multiplier"], min=0.25, soft_max=3.0)
    detail_level: EnumProperty(
        name="Детализация",
        items=[("LOW", "Низкая", ""), ("MEDIUM", "Средняя", ""), ("HIGH", "Высокая", "")],
        default=DEFAULTS["detail_level"],
    )
    randomize_each_run: BoolProperty(name="Случайный seed на запуск", default=False)
    apply_bevels: BoolProperty(name="Добавлять bevel", default=True)
    join_parts: BoolProperty(name="Join parts", description="Сейчас используется мягкая сборка через root-object без destructive join", default=False)

    single_category: EnumProperty(
        name="Категория",
        items=generator.CATEGORY_ENUM_ITEMS,
        default="roof_power",
        update=_on_single_category_changed,
    )
    single_prop_type: EnumProperty(name="Тип объекта", items=generator.prop_type_items)

    preview_columns: IntProperty(name="Колонки preview", default=DEFAULTS["preview_columns"], min=1, soft_max=12)
    preview_spacing: FloatProperty(name="Шаг preview", default=DEFAULTS["preview_spacing"], min=1.0, soft_max=8.0)
    preview_variants_per_type: IntProperty(name="Вариантов на тип", default=DEFAULTS["preview_variants_per_type"], min=1, max=5)
    include_preview_labels: BoolProperty(name="Подписи в preview", default=True)
    include_ground_plane: BoolProperty(name="Плоскость под preview", default=True)

    room_type: EnumProperty(
        name="Тип комнаты",
        items=furniture_catalog.ROOM_ENUM_ITEMS,
        default=DEFAULTS["room_type"],
        update=_on_room_type_changed,
    )
    furniture_object_type: EnumProperty(
        name="Тип мебели",
        items=furniture_catalog.FURNITURE_OBJECT_ENUM_ITEMS,
        default=DEFAULTS["furniture_object_type"],
    )
    furniture_density: IntProperty(name="Количество объектов", min=1, max=200, default=DEFAULTS["furniture_density"])
    furniture_seed: IntProperty(name="Seed мебели", default=DEFAULTS["furniture_seed"], min=0)
    furniture_use_atlas: BoolProperty(name="Использовать атлас мебели", default=DEFAULTS["furniture_use_atlas"])
    furniture_area_width: FloatProperty(name="Ширина зоны мебели", default=DEFAULTS["furniture_area_width"], min=1.0, max=100.0)
    furniture_area_depth: FloatProperty(name="Глубина зоны мебели", default=DEFAULTS["furniture_area_depth"], min=1.0, max=100.0)
    furniture_margin: FloatProperty(name="Отступ мебели", default=DEFAULTS["furniture_margin"], min=0.0, max=5.0)
    furniture_collision_padding: FloatProperty(name="Запас коллизий мебели", default=DEFAULTS["furniture_collision_padding"], min=0.0, max=2.0)
    furniture_atlas_image_path: StringProperty(name="Furniture atlas path", default=DEFAULTS["furniture_atlas_image_path"], subtype="FILE_PATH")
    furniture_manifest_path: StringProperty(name="Furniture manifest path", default=DEFAULTS["furniture_manifest_path"], subtype="FILE_PATH")

    roof_width: FloatProperty(name="Ширина крыши", default=DEFAULTS["roof_width"], min=4.0, soft_max=60.0)
    roof_depth: FloatProperty(name="Глубина крыши", default=DEFAULTS["roof_depth"], min=4.0, soft_max=60.0)
    yard_width: FloatProperty(name="Ширина территории", default=DEFAULTS["yard_width"], min=8.0, soft_max=80.0)
    yard_depth: FloatProperty(name="Глубина территории", default=DEFAULTS["yard_depth"], min=8.0, soft_max=80.0)
    building_width: FloatProperty(name="Ширина здания", default=DEFAULTS["building_width"], min=3.0, soft_max=40.0)
    building_depth: FloatProperty(name="Глубина здания", default=DEFAULTS["building_depth"], min=3.0, soft_max=40.0)
    density: FloatProperty(name="Плотность", default=DEFAULTS["density"], min=0.1, max=2.0)
    margin_from_edge: FloatProperty(name="Отступ от края", default=DEFAULTS["margin_from_edge"], min=0.0, soft_max=8.0)
    spacing: FloatProperty(name="Spacing", default=DEFAULTS["spacing"], min=0.1, soft_max=6.0)
    avoid_overlaps: BoolProperty(name="Избегать пересечений", default=DEFAULTS["avoid_overlaps"])
    service_path_width: FloatProperty(name="Ширина сервисного прохода", default=DEFAULTS["service_path_width"], min=0.0, soft_max=5.0)
    keep_service_paths: BoolProperty(name="Оставлять сервисные проходы", default=True)
    cluster_mode: BoolProperty(name="Кластерный режим", default=True)
    fence_around_yard: BoolProperty(name="Забор по периметру участка", default=True)
    equipment_zone: BoolProperty(name="Техническая зона", default=True)
    generator_zone: BoolProperty(name="Зона генераторов", default=True)
    lighting_zone: BoolProperty(name="Зона освещения", default=True)

    enable_solar_panels: BoolProperty(name="Солнечные панели", default=True)
    enable_tanks: BoolProperty(name="Баки/ёмкости", default=True)
    enable_hvac: BoolProperty(name="HVAC/кондиционеры", default=True)
    enable_vents: BoolProperty(name="Вентиляция", default=True)
    enable_communications: BoolProperty(name="Антенны/связь", default=True)
    enable_warning_systems: BoolProperty(name="Сирены/маяки", default=True)
    enable_lighting: BoolProperty(name="Освещение", default=True)
    enable_power_equipment: BoolProperty(name="Электрооборудование", default=True)
    enable_fences: BoolProperty(name="Заборы/ограждения", default=True)
    enable_access: BoolProperty(name="Лестницы/доступ", default=True)
    enable_storage: BoolProperty(name="Ящики/контейнеры", default=True)
    enable_surveillance: BoolProperty(name="Камеры/датчики", default=True)
    enable_special: BoolProperty(name="Спец-объекты", default=True)

    atlas_image_path: StringProperty(name="Atlas image path", default=DEFAULTS["atlas_image_path"], subtype="FILE_PATH")
    manifest_path: StringProperty(name="Manifest path", default=DEFAULTS["manifest_path"], subtype="FILE_PATH")
    manifest_json: StringProperty(name="Manifest JSON", default="", options={"HIDDEN"})
    manifest_sync_lock: BoolProperty(default=False, options={"HIDDEN"})
    manifest_region: EnumProperty(name="Регион", items=atlas_manifest.region_items, update=_on_region_changed)
    region_x: IntProperty(name="X", default=0, min=0)
    region_y: IntProperty(name="Y", default=0, min=0)
    region_w: IntProperty(name="W", default=128, min=1)
    region_h: IntProperty(name="H", default=128, min=1)
    atlas_width: IntProperty(name="Ширина атласа", default=1024, min=1)
    atlas_height: IntProperty(name="Высота атласа", default=1024, min=1)


classes = (RooftopYardPropsSettings,)


def register():
    for cls in classes:
        addon.safe_register_class(cls)
    if hasattr(bpy.types.Scene, "rooftop_yard_props_settings"):
        del bpy.types.Scene.rooftop_yard_props_settings
    bpy.types.Scene.rooftop_yard_props_settings = PointerProperty(type=RooftopYardPropsSettings)
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return
    settings = getattr(scene, "rooftop_yard_props_settings", None)
    if settings is None:
        return
    apply_defaults_to_props(settings)
    if not settings.manifest_json:
        manifest = atlas_manifest.manifest_from_settings(settings, persist_default_manifest=True)
        settings.manifest_json = json.dumps(manifest, ensure_ascii=False)
        atlas_manifest.sync_editor_from_manifest(settings)


def unregister():
    if hasattr(bpy.types.Scene, "rooftop_yard_props_settings"):
        del bpy.types.Scene.rooftop_yard_props_settings
    for cls in reversed(classes):
        addon.safe_unregister_class(cls)

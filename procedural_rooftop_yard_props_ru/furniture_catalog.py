from __future__ import annotations

from dataclasses import dataclass


ROOM_ITEMS = [
    ("all", "Все комнаты", "Смешанный набор мебели для разных комнат"),
    ("living_room", "Гостиная", "Диваны, столы, полки, телевизор, декор"),
    ("bedroom", "Спальня", "Кровать, тумбы, шкафы, лампы"),
    ("kitchen", "Кухня", "Кухонные шкафы, техника, столы"),
    ("bathroom", "Ванная / туалет", "Сантехника, шкафчики, зеркало"),
    ("corridor", "Коридор", "Шкафы, вешалки, обувницы, светильники"),
    ("medical", "Медпункт", "Кушетка, аптечные шкафы, оборудование"),
    ("lab", "Лаборатория", "Рабочие столы, терминалы, контейнеры, анализаторы"),
    ("canteen", "Столовая / зона отдыха", "Столы, стулья, автоматы, диваны"),
    ("storage", "Склад / техпомещение", "Стеллажи, ящики, бочки, инструменты"),
    ("office", "Кабинет / диспетчерская", "Столы, терминалы, кресла, панели управления"),
]

ROOM_LABELS = dict((item[0], item[1]) for item in ROOM_ITEMS)
ROOM_ENUM_ITEMS = tuple(ROOM_ITEMS)

ROOM_COLLECTIONS = {
    "living_room": "LivingRoom",
    "bedroom": "Bedroom",
    "kitchen": "Kitchen",
    "bathroom": "Bathroom",
    "corridor": "Corridor",
    "medical": "Medical",
    "lab": "Lab",
    "canteen": "Canteen",
    "storage": "Storage",
    "office": "Office",
}


@dataclass(frozen=True)
class FurnitureDef:
    object_id: str
    room_type: str
    label: str
    footprint: tuple[float, float]
    weight: float = 1.0
    placement: str = "free"


def _f(object_id: str, room: str, label: str, footprint: tuple[float, float], weight: float = 1.0, placement: str = "free") -> FurnitureDef:
    return FurnitureDef(object_id, room, label, footprint, weight, placement)


FURNITURE_CATALOG: dict[str, list[FurnitureDef]] = {
    "living_room": [
        _f("sofa", "living_room", "Диван", (2.2, 0.9), 1.2, "wall"),
        _f("armchair", "living_room", "Кресло", (0.95, 0.9), 0.9, "free"),
        _f("coffee_table", "living_room", "Журнальный стол", (1.1, 0.65), 0.9, "center"),
        _f("tv_screen", "living_room", "TV / настенный экран", (1.25, 0.22), 0.8, "wall"),
        _f("bookshelf", "living_room", "Книжный шкаф", (1.25, 0.38), 0.8, "wall"),
        _f("small_cabinet", "living_room", "Низкий шкаф", (1.0, 0.42), 0.8, "wall"),
        _f("floor_lamp", "living_room", "Торшер", (0.45, 0.45), 0.5, "corner"),
        _f("wall_shelf", "living_room", "Настенная полка", (1.0, 0.24), 0.6, "wall"),
        _f("rug", "living_room", "Ковер", (1.8, 1.2), 0.6, "center"),
        _f("decor_crate", "living_room", "Декоративный ящик", (0.55, 0.45), 0.6, "free"),
    ],
    "bedroom": [
        _f("bed", "bedroom", "Кровать", (2.1, 1.35), 1.2, "wall"),
        _f("bedside_table", "bedroom", "Прикроватная тумба", (0.48, 0.42), 0.9, "wall"),
        _f("wardrobe", "bedroom", "Шкаф", (1.35, 0.55), 0.9, "wall"),
        _f("dresser", "bedroom", "Комод", (1.05, 0.48), 0.8, "wall"),
        _f("desk_lamp", "bedroom", "Настольная лампа", (0.32, 0.32), 0.5, "free"),
        _f("wall_mirror", "bedroom", "Зеркало", (0.55, 0.12), 0.5, "wall"),
        _f("small_rug", "bedroom", "Малый ковер", (1.25, 0.8), 0.5, "center"),
        _f("storage_trunk", "bedroom", "Сундук", (0.9, 0.45), 0.7, "wall"),
    ],
    "kitchen": [
        _f("fridge", "kitchen", "Холодильник", (0.75, 0.72), 1.0, "wall"),
        _f("kitchen_counter", "kitchen", "Кухонная тумба", (1.45, 0.62), 1.1, "wall"),
        _f("sink_cabinet", "kitchen", "Мойка", (1.1, 0.62), 0.9, "wall"),
        _f("stove", "kitchen", "Плита", (0.72, 0.62), 0.9, "wall"),
        _f("microwave", "kitchen", "Микроволновка", (0.58, 0.42), 0.7, "wall"),
        _f("wall_cabinet", "kitchen", "Навесной шкаф", (1.0, 0.32), 0.8, "wall"),
        _f("dining_table", "kitchen", "Обеденный стол", (1.2, 0.85), 0.8, "center"),
        _f("simple_chair", "kitchen", "Стул", (0.52, 0.52), 1.1, "free"),
        _f("water_machine", "kitchen", "Кулер / автомат", (0.55, 0.5), 0.6, "wall"),
        _f("trash_bin", "kitchen", "Мусорное ведро", (0.42, 0.42), 0.6, "corner"),
    ],
    "bathroom": [
        _f("toilet", "bathroom", "Унитаз", (0.58, 0.75), 1.0, "wall"),
        _f("bath_sink", "bathroom", "Раковина", (0.68, 0.5), 1.0, "wall"),
        _f("shower_cabin", "bathroom", "Душевая кабина", (0.95, 0.95), 0.8, "corner"),
        _f("bathtub", "bathroom", "Ванна", (1.7, 0.78), 0.7, "wall"),
        _f("mirror_cabinet", "bathroom", "Зеркальный шкаф", (0.7, 0.16), 0.7, "wall"),
        _f("towel_rack", "bathroom", "Полотенцесушитель", (0.55, 0.14), 0.6, "wall"),
        _f("bath_trash_bin", "bathroom", "Малое ведро", (0.35, 0.35), 0.5, "corner"),
        _f("washing_machine", "bathroom", "Стиральная машина", (0.68, 0.64), 0.8, "wall"),
    ],
    "corridor": [
        _f("coat_rack", "corridor", "Вешалка", (0.8, 0.3), 0.9, "wall"),
        _f("shoe_cabinet", "corridor", "Обувница", (1.0, 0.35), 0.9, "wall"),
        _f("wall_lamp", "corridor", "Настенный светильник", (0.32, 0.12), 0.7, "wall"),
        _f("bench", "corridor", "Скамья", (1.25, 0.42), 0.8, "wall"),
        _f("wall_terminal", "corridor", "Домофон / терминал", (0.38, 0.12), 0.7, "wall"),
        _f("notice_board", "corridor", "Доска объявлений", (0.9, 0.14), 0.8, "wall"),
        _f("utility_cabinet", "corridor", "Технический шкаф", (0.75, 0.42), 0.8, "wall"),
        _f("wall_pipe", "corridor", "Настенная труба", (1.2, 0.16), 0.6, "wall"),
    ],
    "medical": [
        _f("medical_couch", "medical", "Кушетка", (1.9, 0.72), 1.0, "wall"),
        _f("medical_cabinet", "medical", "Медицинский шкаф", (0.9, 0.45), 1.0, "wall"),
        _f("medicine_fridge", "medical", "Медицинский холодильник", (0.62, 0.62), 0.8, "wall"),
        _f("medical_sink", "medical", "Раковина", (0.72, 0.52), 0.8, "wall"),
        _f("doctor_desk", "medical", "Стол врача", (1.25, 0.72), 0.8, "center"),
        _f("medical_chair", "medical", "Стул врача", (0.52, 0.52), 0.8, "free"),
        _f("exam_lamp", "medical", "Смотровая лампа", (0.55, 0.55), 0.6, "free"),
        _f("privacy_screen", "medical", "Ширма", (1.45, 0.18), 0.7, "free"),
        _f("oxygen_cylinder", "medical", "Кислородный баллон", (0.38, 0.38), 0.6, "wall"),
        _f("health_monitor", "medical", "Монитор пациента", (0.62, 0.48), 0.6, "free"),
        _f("first_aid_box", "medical", "Аптечка", (0.48, 0.18), 0.6, "wall"),
    ],
    "lab": [
        _f("lab_workbench", "lab", "Лабораторный стол", (1.7, 0.72), 1.1, "wall"),
        _f("lab_terminal", "lab", "Компьютерный терминал", (0.9, 0.62), 1.0, "wall"),
        _f("sample_shelf", "lab", "Полка с образцами", (1.2, 0.4), 0.9, "wall"),
        _f("sealed_container", "lab", "Герметичный контейнер", (0.55, 0.55), 0.8, "free"),
        _f("analyzer_device", "lab", "Анализатор", (0.85, 0.58), 0.9, "wall"),
        _f("air_sensor", "lab", "Датчик воздуха", (0.35, 0.35), 0.6, "free"),
        _f("glove_box", "lab", "Бокс с перчатками", (1.15, 0.65), 0.8, "wall"),
        _f("material_safe", "lab", "Сейф материалов", (0.7, 0.55), 0.7, "wall"),
        _f("note_board", "lab", "Доска заметок", (0.9, 0.12), 0.6, "wall"),
        _f("emergency_button", "lab", "Аварийная кнопка", (0.28, 0.12), 0.5, "wall"),
        _f("exhaust_hood", "lab", "Вытяжной шкаф", (1.15, 0.68), 0.8, "wall"),
    ],
    "canteen": [
        _f("large_table", "canteen", "Большой стол", (1.8, 0.9), 1.0, "center"),
        _f("chair_set", "canteen", "Набор стульев", (1.6, 1.2), 0.9, "center"),
        _f("canteen_sofa", "canteen", "Диван зоны отдыха", (1.8, 0.85), 0.7, "wall"),
        _f("vending_machine", "canteen", "Торговый автомат", (0.82, 0.62), 0.8, "wall"),
        _f("water_dispenser", "canteen", "Кулер", (0.52, 0.48), 0.7, "wall"),
        _f("canteen_fridge", "canteen", "Холодильник", (0.72, 0.7), 0.6, "wall"),
        _f("coffee_machine", "canteen", "Кофемашина", (0.55, 0.42), 0.7, "wall"),
        _f("tea_station", "canteen", "Чайная станция", (0.9, 0.5), 0.7, "wall"),
        _f("canteen_microwave", "canteen", "Микроволновка", (0.58, 0.42), 0.6, "wall"),
        _f("communication_terminal", "canteen", "Терминал связи", (0.85, 0.55), 0.6, "wall"),
        _f("music_speaker", "canteen", "Колонка", (0.42, 0.38), 0.5, "wall"),
    ],
    "storage": [
        _f("metal_shelving", "storage", "Металлический стеллаж", (1.45, 0.55), 1.2, "wall"),
        _f("cardboard_boxes", "storage", "Картонные коробки", (0.95, 0.75), 1.1, "free"),
        _f("plastic_crates", "storage", "Пластиковые ящики", (0.9, 0.65), 0.9, "free"),
        _f("barrels", "storage", "Бочки", (0.9, 0.55), 0.8, "free"),
        _f("tool_cabinet", "storage", "Шкаф с инструментами", (0.85, 0.48), 0.8, "wall"),
        _f("utility_workbench", "storage", "Верстак", (1.45, 0.65), 0.8, "wall"),
        _f("ladder", "storage", "Лестница", (0.55, 1.25), 0.7, "wall"),
        _f("spare_pipes", "storage", "Запасные трубы", (1.35, 0.45), 0.8, "wall"),
        _f("cable_spool", "storage", "Катушка кабеля", (0.72, 0.55), 0.7, "free"),
        _f("generator_box", "storage", "Генераторный блок", (1.0, 0.72), 0.7, "wall"),
        _f("cleaning_cabinet", "storage", "Шкаф уборочного инвентаря", (0.82, 0.45), 0.7, "wall"),
    ],
    "office": [
        _f("office_desk", "office", "Рабочий стол", (1.35, 0.72), 1.0, "center"),
        _f("office_chair", "office", "Офисное кресло", (0.58, 0.58), 0.9, "free"),
        _f("file_cabinet", "office", "Картотечный шкаф", (0.62, 0.5), 0.8, "wall"),
        _f("control_console", "office", "Пульт управления", (1.35, 0.62), 0.9, "wall"),
        _f("wall_screen", "office", "Настенный экран", (1.25, 0.18), 0.8, "wall"),
        _f("radio_unit", "office", "Радиостанция", (0.62, 0.45), 0.7, "wall"),
        _f("document_stack", "office", "Стопка документов", (0.42, 0.32), 0.6, "free"),
        _f("map_board", "office", "Карта / план", (1.0, 0.14), 0.7, "wall"),
        _f("table_lamp", "office", "Настольная лампа", (0.34, 0.34), 0.6, "free"),
        _f("archive_shelf", "office", "Архивный стеллаж", (1.25, 0.42), 0.9, "wall"),
    ],
}


ALL_FURNITURE_DEFS = [definition for definitions in FURNITURE_CATALOG.values() for definition in definitions]
FURNITURE_BY_ID = {definition.object_id: definition for definition in ALL_FURNITURE_DEFS}

FURNITURE_OBJECT_ENUM_ITEMS = tuple(
    [("all", "Все объекты комнаты", "Генерировать разные объекты выбранной комнаты")]
    + [(definition.object_id, definition.label, definition.object_id) for definition in ALL_FURNITURE_DEFS]
)


def room_enum_items(_self=None, _context=None):
    return ROOM_ENUM_ITEMS


def object_enum_items(self, _context):
    room_type = getattr(self, "room_type", "all")
    if room_type and room_type != "all":
        return tuple([("all", "Все объекты комнаты", "Генерировать разные объекты выбранной комнаты")] + [
            (definition.object_id, definition.label, definition.object_id)
            for definition in FURNITURE_CATALOG.get(room_type, [])
        ])
    return FURNITURE_OBJECT_ENUM_ITEMS


def definitions_for_room(room_type: str) -> list[FurnitureDef]:
    if room_type == "all":
        return list(ALL_FURNITURE_DEFS)
    return list(FURNITURE_CATALOG.get(room_type, []))


ROOM_ALIASES = {
    "living": "living_room",
    "living_room": "living_room",
    "гостиная": "living_room",
    "зал": "living_room",
    "bedroom": "bedroom",
    "спальня": "bedroom",
    "kitchen": "kitchen",
    "кухня": "kitchen",
    "bathroom": "bathroom",
    "toilet": "bathroom",
    "ванная": "bathroom",
    "туалет": "bathroom",
    "corridor": "corridor",
    "hall": "corridor",
    "коридор": "corridor",
    "medical": "medical",
    "med": "medical",
    "медпункт": "medical",
    "лазарет": "medical",
    "lab": "lab",
    "laboratory": "lab",
    "лаборатория": "lab",
    "canteen": "canteen",
    "dining": "canteen",
    "столовая": "canteen",
    "storage": "storage",
    "utility": "storage",
    "склад": "storage",
    "техпомещение": "storage",
    "office": "office",
    "control": "office",
    "кабинет": "office",
    "диспетчерская": "office",
}


def normalize_room_type(value: str | None, fallback: str = "all") -> str:
    if not value:
        return fallback
    key = str(value).strip().lower().replace(" ", "_")
    for alias, room_type in ROOM_ALIASES.items():
        if alias in key:
            return room_type
    return ROOM_ALIASES.get(key, key if key in FURNITURE_CATALOG or key == "all" else fallback)


def register():
    pass


def unregister():
    pass

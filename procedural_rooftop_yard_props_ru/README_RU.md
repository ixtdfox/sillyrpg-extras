# procedural_rooftop_yard_props_ru

`procedural_rooftop_yard_props_ru` — отдельный Blender addon для генерации low/mid-poly rooftop и yard пропсов: HVAC, солнечных панелей, баков, антенн, прожекторов, генераторов, лестниц, заборов, контейнеров, датчиков и специальных технических объектов.

## Что делает плагин

- Генерирует один выбранный объект.
- Генерирует preview pack всех доступных типов в виде сетки.
- Генерирует набор пропсов на прямоугольной крыше.
- Генерирует техническую придомовую территорию вокруг прямоугольного здания.
- Работает через отдельный atlas texture и отдельный JSON manifest.
- Позволяет обновлять UV на уже сгенерированных объектах без полной регенерации мешей.

## Установка

1. Открой Blender 4.0+.
2. Перейди в `Edit > Preferences > Add-ons > Install...`.
3. Укажи директорию или zip с пакетом `procedural_rooftop_yard_props_ru`.
4. Включи addon `procedural_rooftop_yard_props_ru`.

## Где находится панель

Панель находится в `3D View > Sidebar > Rooftop/Yard RU`.

Название панели: `Процедурные rooftop/yard объекты`.

## Как сгенерировать один объект

1. В секции `Single prop mode` выбери категорию и `Тип объекта`.
2. Настрой `Seed`, `Scale Multiplier`, `Детализация`.
3. Нажми `Сгенерировать объект`.

Объект появится в коллекции `Generated_Rooftop_Yard_Props/Single`.

## Как сгенерировать preview pack

1. Настрой `Колонки preview`, `Шаг preview`, `Вариантов на тип`.
2. Включи нужные категории.
3. Нажми `Сгенерировать набор ассетов`.

Результат появится в коллекции `Generated_Rooftop_Yard_Props/Preview`.

## Как сгенерировать объекты на крыше

1. Настрой `Ширина крыши`, `Глубина крыши`, `Плотность`, `Отступ от края`.
2. Включи нужные категории.
3. При необходимости включи `Оставлять сервисные проходы` и `Кластерный режим`.
4. Нажми `Сгенерировать крышу`.

Результат появится в коллекции `Generated_Rooftop_Yard_Props/Roof`.

## Как сгенерировать придомовую территорию

1. Настрой `Ширина территории`, `Глубина территории`, `Ширина здания`, `Глубина здания`.
2. Включи зоны `Техническая зона`, `Зона генераторов`, `Зона освещения` при необходимости.
3. Нажми `Сгенерировать территорию`.

Результат появится в коллекции `Generated_Rooftop_Yard_Props/Yard`.

## Как устроен atlas manifest

Файл по умолчанию: `assets/rooftop_yard_manifest.json`.

Структура:

```json
{
  "atlas": "rooftop_yard_atlas.png",
  "version": 1,
  "tileSize": 128,
  "atlas_width": 1024,
  "atlas_height": 1024,
  "regions": {
    "metal_light": { "x": 0, "y": 0, "w": 128, "h": 128 },
    "solar_panel": { "x": 0, "y": 128, "w": 256, "h": 128 }
  }
}
```

Каждый mesh-part хранит `atlas_region_name`, поэтому UV можно пересчитать повторно после редактирования manifest.

## Как обновить UV после правки manifest

1. Измени JSON вручную или через встроенный редактор region в панели.
2. Нажми `Сохранить манифест`.
3. Нажми `Обновить UV по манифесту`.

Addon пройдёт по объектам в целевой коллекции и заново применит material + UV без пересборки геометрии.

## Как добавить новый prop type

1. Открой `generator.py`.
2. Добавь новый `PropDef` в `PROP_DEFS`.
3. Привяжи тип к существующему family-builder или добавь новый builder.
4. При необходимости добавь новые atlas region names в manifest.

Минимум для нового типа:

- `prop_type`
- `category`
- `footprint`
- `height`
- `allowed_surfaces`
- builder с узнаваемыми subparts

## Какие custom properties добавляются объектам

На root-объектах и mesh-частях сохраняются:

- `generated_by = "procedural_rooftop_yard_props_ru"`
- `procedural_rooftop_yard = True`
- `prop_type`
- `prop_category`
- `atlas_regions`

На mesh-частях дополнительно:

- `atlas_region_name`

## Ограничения текущей версии

- `Join parts` сейчас оставлен как мягкая совместимость UI и не делает destructive mesh-join, чтобы не ломать live UV update.
- UV обновляются object-by-object; сложные многоматериальные merged-mesh сценарии специально не используются.
- Placeholder atlas входит в пакет только для безопасной загрузки addon-а; под production лучше положить свой atlas PNG.

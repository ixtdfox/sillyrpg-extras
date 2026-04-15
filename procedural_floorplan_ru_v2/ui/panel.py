import bpy


class FLOORPLAN_V2_PT_panel(bpy.types.Panel):
    """Основная боковая панель управления генератором в 3D View."""

    bl_label = "План дома v2"
    bl_idname = "FLOORPLAN_V2_PT_panel_ru"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "План дома v2"

    def draw(self, context):
        """Рисует все блоки интерфейса и связывает их со свойствами сцены.

        Как это работает:
        метод последовательно собирает layout из секций Blender UI: сначала
        кнопки операций, затем общие настройки генерации, потом управление
        атласом и редактор выбранного тайла. Состояние части элементов
        динамически зависит от значений свойств, например от флага включения
        атласа и наличия загруженного manifest.
        """
        layout = self.layout
        props = context.scene.floorplan_ru_v2_settings

        # Верхняя строка запускает основные действия аддона без ухода в подпункты.
        row = layout.row(align=True)
        row.operator("floorplan_ru_v2.generate", icon="HOME")
        row.operator("floorplan_ru_v2.reset_defaults", icon="LOOP_BACK")

        # Базовые числовые и служебные настройки генерации.
        box = layout.box()
        box.label(text="Общее")
        col = box.column(align=True)
        col.prop(props, "delete_old")
        col.prop(props, "randomize_seed_each_build")
        col.prop(props, "collection_name")
        col.prop(props, "seed")
        col.prop(props, "target_room_count")
        col.prop(props, "min_room_side_m")
        col.prop(props, "house_scale")
        col.prop(props, "text_size")

        # Выбор дискретного алгоритма построения footprint.
        box = layout.box()
        box.label(text="Форма дома")
        box.prop(props, "shape_mode")

        box = layout.box()
        box.label(text="Этажность")
        col = box.column(align=True)
        col.prop(props, "story_count")
        col.prop(props, "story_layout_mode")
        col.prop(props, "vertical_profile_mode")
        sub = col.column(align=True)
        sub.enabled = props.vertical_profile_mode != "strict"
        sub.prop(props, "vertical_profile_strength")

        box = layout.box()
        box.label(text="Межэтажные бордюры")
        col = box.column(align=True)
        col.prop(props, "floor_bands_enabled")
        sub = col.column(align=True)
        sub.enabled = props.floor_bands_enabled
        sub.prop(props, "floor_band_depth")
        sub.prop(props, "floor_band_height")

        box = layout.box()
        box.label(text="Кровельные бордюры")
        col = box.column(align=True)
        col.prop(props, "roof_border_enabled")
        sub = col.column(align=True)
        sub.enabled = props.roof_border_enabled
        sub.prop(props, "roof_border_depth")
        sub.prop(props, "roof_border_height")

        # Настройки генерации внешних стен отделены от floor-логики и builders.
        box = layout.box()
        box.label(text="Внешние стены")
        col = box.column(align=True)
        col.prop(props, "outer_walls_enabled")
        sub = col.column(align=True)
        sub.enabled = props.outer_walls_enabled
        sub.prop(props, "wall_height")
        sub.prop(props, "wall_module_width")
        sub.prop(props, "wall_thickness")

        box = layout.box()
        box.label(text="Двери")
        col = box.column(align=True)
        col.prop(props, "doors_enabled")
        sub = col.column(align=True)
        sub.enabled = props.doors_enabled
        sub.prop(props, "interior_door_width")
        sub.prop(props, "interior_door_height")
        sub.prop(props, "entry_door_width")
        sub.prop(props, "entry_door_height")
        sub.prop(props, "door_leaf_thickness")
        sub.prop(props, "door_min_edge_offset")
        sub.prop(props, "door_min_corner_offset")

        box = layout.box()
        box.label(text="Окна")
        col = box.column(align=True)
        col.prop(props, "windows_enabled")
        sub = col.column(align=True)
        sub.enabled = props.windows_enabled
        sub.prop(props, "window_width")
        sub.prop(props, "window_height")
        sub.prop(props, "window_sill_height")
        sub.prop(props, "window_min_corner_offset")
        sub.prop(props, "window_min_door_offset")
        sub.prop(props, "window_min_partition_offset")
        sub.prop(props, "window_min_edge_offset")

        box = layout.box()
        box.label(text="Лестница")
        col = box.column(align=True)
        col.prop(props, "stairs_enabled")
        sub = col.column(align=True)
        sub.enabled = props.stairs_enabled
        sub.prop(props, "stair_mode")
        sub.prop(props, "stair_width")
        sub.prop(props, "stair_landing_size")
        sub.prop(props, "stair_mid_landing_size")
        sub.prop(props, "stair_riser_height")
        sub.prop(props, "stair_tread_depth")
        sub.prop(props, "stair_min_free_area")
        sub.prop(props, "stair_door_clearance")
        sub.prop(props, "stair_window_clearance")

        box = layout.box()
        box.label(text="Ограждение на крыше")
        col = box.column(align=True)
        col.prop(props, "roof_railing_enabled")
        sub = col.column(align=True)
        sub.enabled = props.roof_railing_enabled
        sub.prop(props, "railing_height")
        sub.prop(props, "railing_post_size")
        sub.prop(props, "railing_rail_thickness")
        sub.prop(props, "railing_rail_count")

        # Секция управления атласом и редактированием manifest.json.
        atlas_box = layout.box()
        atlas_box.label(text="Атлас")
        col = atlas_box.column(align=True)
        col.prop(props, "atlas_enabled")
        sub = col.column(align=True)
        sub.enabled = props.atlas_enabled
        sub.prop(props, "atlas_manifest_path")
        sub.prop(props, "atlas_image_path")
        sub.prop(props, "atlas_include_interior_walls")
        sub.prop(props, "atlas_random_pick")

        box = layout.box()
        box.label(text="Декали")
        col = box.column(align=True)
        col.prop(props, "decals_enabled")
        sub = col.column(align=True)
        sub.enabled = props.decals_enabled
        sub.prop(props, "decal_manifest_path")
        sub.prop(props, "decal_image_path")
        sub.prop(props, "decal_density", slider=True)
        sub.prop(props, "decal_enable_streaks")

        row = atlas_box.row(align=True)
        row.operator("floorplan_ru_v2.atlas_load_manifest", icon="FILE_REFRESH")
        row.operator("floorplan_ru_v2.atlas_save_manifest", icon="FILE_TICK")
        atlas_box.operator("floorplan_ru_v2.atlas_apply_existing", icon="MATERIAL")

        placement_box = atlas_box.box()
        placement_box.label(text="Настройки текстур из manifest.json")
        if not props.atlas_manifest_json:
            placement_box.label(text="Сначала укажи путь и нажми 'Загрузить manifest.json'", icon="INFO")

        # Параметры размещения для оконного тайла берутся из блока placement manifest-а.
        win = placement_box.box()
        win.label(text="Окна")
        grid = win.grid_flow(columns=2, align=True)
        grid.prop(props, "atlas_window_offset_x", slider=True)
        grid.prop(props, "atlas_window_offset_y", slider=True)
        grid.prop(props, "atlas_window_width_scale")
        grid.prop(props, "atlas_window_height_scale")

        # Аналогичные настройки для дверных проёмов.
        door = placement_box.box()
        door.label(text="Двери")
        grid = door.grid_flow(columns=2, align=True)
        grid.prop(props, "atlas_door_offset_x", slider=True)
        grid.prop(props, "atlas_door_offset_y", slider=True)
        grid.prop(props, "atlas_door_width_scale")
        grid.prop(props, "atlas_door_height_scale")

        # Редактор конкретного тайла активируется только после загрузки manifest.
        editor = atlas_box.box()
        editor.label(text="Редактор выбранного тайла")
        editor.enabled = bool(props.atlas_manifest_json)
        editor.prop(props, "atlas_category")
        editor.prop(props, "atlas_tile")
        editor.prop(props, "atlas_tile_id")
        grid = editor.grid_flow(columns=2, align=True)
        grid.prop(props, "atlas_x")
        grid.prop(props, "atlas_y")
        grid.prop(props, "atlas_w")
        grid.prop(props, "atlas_h")
        grid.prop(props, "atlas_tile_width_m")
        grid.prop(props, "atlas_tile_height_m")


classes = (FLOORPLAN_V2_PT_panel,)


def register():
    """Регистрирует панель Blender, чтобы она появилась в боковой вкладке."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Снимает регистрацию панели в обратном порядке."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

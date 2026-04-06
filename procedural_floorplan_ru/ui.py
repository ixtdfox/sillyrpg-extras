import bpy


class FLOORPLAN_PT_panel(bpy.types.Panel):
    bl_label = "План дома"
    bl_idname = "FLOORPLAN_PT_panel_ru"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'План дома'

    def draw(self, context):
        layout = self.layout
        props = context.scene.floorplan_ru_settings

        row = layout.row(align=True)
        row.operator("floorplan_ru.generate", icon='HOME')
        row.operator("floorplan_ru.reset_defaults", icon='LOOP_BACK')

        box = layout.box()
        box.label(text="Общее")
        col = box.column(align=True)
        col.prop(props, "delete_old")
        col.prop(props, "collection_name")
        col.prop(props, "auto_random_seed")
        sub = col.column(align=True)
        sub.enabled = not props.auto_random_seed
        sub.prop(props, "seed")
        col.prop(props, "target_room_count")
        col.prop(props, "house_scale")
        col.prop(props, "min_floors")
        col.prop(props, "max_floors")
        col.prop(props, "building_mode")
        col.prop(props, "shape_mode")
        col.prop(props, "text_size")

        box = layout.box()
        box.label(text="Стены, полы, двери")
        col = box.column(align=True)
        for name in ("wall_height", "wall_thickness", "floor_thickness", "corridor_width", "door_width", "entry_door_width", "entry_door_thickness", "door_height"):
            col.prop(props, name)

        mod_box = box.box()
        mod_box.label(text="Модульная геометрия")
        mod_box.prop(props, "modular_tiles_enabled")
        sub = mod_box.column(align=True)
        sub.enabled = props.modular_tiles_enabled
        sub.prop(props, "wall_tile_width")
        sub.prop(props, "surface_tile_size")

        box = layout.box()
        box.label(text="Окна")
        col = box.column(align=True)
        for name in ("window_sill_height", "window_height", "window_min_width", "window_end_margin", "window_strip_width"):
            col.prop(props, name)

        box = layout.box()
        box.label(text="Лестница")
        col = box.column(align=True)
        for name in ("stair_width", "stair_landing", "stair_mid_landing", "stair_riser", "stair_tread", "stair_clearance", "stair_max_parent_occupancy", "stair_min_free_area", "stair_door_clearance", "stair_window_clearance"):
            col.prop(props, name)

        box = layout.box()
        box.label(text="Планировка")
        col = box.column(align=True)
        for name in ("outer_margin", "room_gap", "min_room_side", "max_aspect"):
            col.prop(props, name)

        box = layout.box()
        box.label(text="Слияние плохих комнат")
        col = box.column(align=True)
        for name in ("post_merge_min_side", "post_merge_min_area", "post_merge_max_aspect", "post_merge_hard_max_aspect", "post_merge_edge_strip_side", "post_merge_sliver_ratio", "post_merge_min_shared"):
            col.prop(props, name)

        box = layout.box()
        box.label(text="Остаточные зоны")
        col = box.column(align=True)
        for name in ("residual_min_area", "residual_long_strip_ratio", "residual_short_side", "residual_corridor_shared_bonus"):
            col.prop(props, name)

        box = layout.box()
        box.label(text="Атлас")
        col = box.column(align=True)
        col.prop(props, "atlas_enabled")
        sub = col.column(align=True)
        sub.enabled = props.atlas_enabled
        sub.prop(props, "atlas_manifest_path")
        sub.prop(props, "atlas_image_path")
        sub.prop(props, "atlas_include_interior_walls")
        sub.prop(props, "atlas_random_pick")

        row = box.row(align=True)
        row.operator("floorplan_ru.atlas_load_manifest", icon='FILE_REFRESH')
        row.operator("floorplan_ru.atlas_save_manifest", icon='FILE_TICK')
        box.operator("floorplan_ru.atlas_apply_existing", icon='MATERIAL')

        placement_box = box.box()
        placement_box.label(text="Настройки текстур из manifest.json")
        if not props.atlas_manifest_json:
            placement_box.label(text="Сначала укажи путь и нажми 'Загрузить manifest.json'", icon='INFO')

        win = placement_box.box()
        win.label(text="Окна")
        g = win.grid_flow(columns=2, align=True)
        g.prop(props, "atlas_window_offset_x", slider=True)
        g.prop(props, "atlas_window_offset_y", slider=True)
        g.prop(props, "atlas_window_width_scale")
        g.prop(props, "atlas_window_height_scale")

        door = placement_box.box()
        door.label(text="Двери")
        g = door.grid_flow(columns=2, align=True)
        g.prop(props, "atlas_door_offset_x", slider=True)
        g.prop(props, "atlas_door_offset_y", slider=True)
        g.prop(props, "atlas_door_width_scale")
        g.prop(props, "atlas_door_height_scale")

        editor = box.box()
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


classes = (FLOORPLAN_PT_panel,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

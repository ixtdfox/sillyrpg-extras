import bpy

from . import addon


class RY_PT_panel(bpy.types.Panel):
    bl_label = "Процедурные rooftop/yard объекты"
    bl_idname = "RY_PT_panel_ru"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Rooftop/Yard RU"

    def draw(self, context):
        layout = self.layout
        props = context.scene.rooftop_yard_props_settings

        row = layout.row(align=True)
        row.operator("rooftop_yard_ru.generate_combo", icon="OUTLINER_COLLECTION")
        row.operator("rooftop_yard_ru.reset_defaults", icon="LOOP_BACK")

        ops = layout.box()
        ops.label(text="Операции")
        col = ops.column(align=True)
        col.operator("rooftop_yard_ru.generate_single", icon="MESH_CUBE")
        col.operator("rooftop_yard_ru.generate_preview", icon="ASSET_MANAGER")
        col.operator("rooftop_yard_ru.generate_roof", icon="MOD_BUILD")
        col.operator("rooftop_yard_ru.generate_yard", icon="GRID")
        col.operator("rooftop_yard_ru.generate_furniture", icon="HOME")
        col.operator("rooftop_yard_ru.generate_selected_room_furniture", icon="SNAP_FACE")
        col.operator("rooftop_yard_ru.generate_furniture_catalog_preview", icon="ASSET_MANAGER")
        col.operator("rooftop_yard_ru.clear_generated", icon="TRASH")

        box = layout.box()
        box.label(text="Основное")
        col = box.column(align=True)
        col.prop(props, "generation_mode")
        col.prop(props, "prop_category")
        col.prop(props, "seed")
        col.prop(props, "randomize_each_run")
        col.prop(props, "clear_previous_before_generate")
        col.prop(props, "target_collection_name")
        col.prop(props, "scale_multiplier")
        col.prop(props, "detail_level")
        col.prop(props, "apply_bevels")
        col.prop(props, "join_parts")

        box = layout.box()
        box.label(text="Single prop mode")
        col = box.column(align=True)
        col.prop(props, "single_category")
        col.prop(props, "single_prop_type")

        box = layout.box()
        box.label(text="Мебель и интерьер")
        col = box.column(align=True)
        col.prop(props, "room_type")
        col.prop(props, "furniture_object_type")
        col.prop(props, "furniture_density")
        col.prop(props, "furniture_seed")
        col.prop(props, "furniture_use_atlas")
        row = box.row(align=True)
        row.operator("rooftop_yard_ru.generate_single_furniture", icon="MESH_CUBE")
        row.operator("rooftop_yard_ru.generate_furniture", icon="HOME")
        box.operator("rooftop_yard_ru.generate_selected_room_furniture", icon="SNAP_FACE")
        box.operator("rooftop_yard_ru.generate_furniture_catalog_preview", icon="ASSET_MANAGER")

        box = layout.box()
        box.label(text="Категории")
        col = box.column(align=True)
        col.prop(props, "enable_solar_panels")
        col.prop(props, "enable_tanks")
        col.prop(props, "enable_hvac")
        col.prop(props, "enable_vents")
        col.prop(props, "enable_communications")
        col.prop(props, "enable_warning_systems")
        col.prop(props, "enable_lighting")
        col.prop(props, "enable_power_equipment")
        col.prop(props, "enable_fences")
        col.prop(props, "enable_access")
        col.prop(props, "enable_storage")
        col.prop(props, "enable_surveillance")
        col.prop(props, "enable_special")

        box = layout.box()
        box.label(text="Placement")
        col = box.column(align=True)
        col.prop(props, "roof_width")
        col.prop(props, "roof_depth")
        col.prop(props, "yard_width")
        col.prop(props, "yard_depth")
        col.prop(props, "building_width")
        col.prop(props, "building_depth")
        col.prop(props, "density", slider=True)
        col.prop(props, "margin_from_edge")
        col.prop(props, "spacing")
        col.prop(props, "avoid_overlaps")
        col.prop(props, "service_path_width")
        col.prop(props, "keep_service_paths")
        col.prop(props, "cluster_mode")
        col.prop(props, "fence_around_yard")
        col.prop(props, "equipment_zone")
        col.prop(props, "generator_zone")
        col.prop(props, "lighting_zone")

        box = layout.box()
        box.label(text="Furniture placement")
        col = box.column(align=True)
        col.prop(props, "furniture_area_width")
        col.prop(props, "furniture_area_depth")
        col.prop(props, "furniture_margin")
        col.prop(props, "furniture_collision_padding")

        box = layout.box()
        box.label(text="Asset pack preview")
        col = box.column(align=True)
        col.prop(props, "preview_columns")
        col.prop(props, "preview_spacing")
        col.prop(props, "preview_variants_per_type")
        col.prop(props, "include_preview_labels")
        col.prop(props, "include_ground_plane")

        atlas_box = layout.box()
        atlas_box.label(text="Texture atlas")
        col = atlas_box.column(align=True)
        col.prop(props, "atlas_image_path")
        col.prop(props, "manifest_path")
        col.prop(props, "furniture_atlas_image_path")
        col.prop(props, "furniture_manifest_path")
        row = atlas_box.row(align=True)
        row.operator("rooftop_yard_ru.reload_manifest", icon="FILE_REFRESH")
        row.operator("rooftop_yard_ru.save_manifest", icon="FILE_TICK")
        atlas_box.operator("rooftop_yard_ru.update_uvs", icon="UV")

        editor = atlas_box.box()
        editor.label(text="Редактор region")
        editor.enabled = bool(props.manifest_json)
        editor.prop(props, "manifest_region")
        grid = editor.grid_flow(columns=2, align=True)
        grid.prop(props, "region_x")
        grid.prop(props, "region_y")
        grid.prop(props, "region_w")
        grid.prop(props, "region_h")
        grid.prop(props, "atlas_width")
        grid.prop(props, "atlas_height")


classes = (RY_PT_panel,)


def register():
    for cls in classes:
        addon.safe_register_class(cls)


def unregister():
    for cls in reversed(classes):
        addon.safe_unregister_class(cls)

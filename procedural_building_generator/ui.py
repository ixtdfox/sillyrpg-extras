import bpy


class PB_PT_main_panel(bpy.types.Panel):
    bl_label = "Procedural Building"
    bl_idname = "PB_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Proc Building'

    def draw(self, context):
        layout = self.layout
        s = context.scene.pb_settings

        col = layout.column(align=True)
        col.operator("pb.setup_controllers", icon='EMPTY_AXIS')
        col.operator("pb.build_now", icon='FILE_REFRESH')
        col.operator("pb.clear_generated", icon='TRASH')

        layout.separator()

        box = layout.box()
        box.label(text="Footprint")
        box.prop(s, "width_m")
        box.prop(s, "depth_m")
        box.prop(s, "floors")
        box.prop(s, "room_count")
        box.prop(s, "seed")

        box = layout.box()
        box.label(text="Style")
        box.prop(s, "detail_amount")
        box.prop(s, "balcony_chance")
        box.prop(s, "roof_style")

        box = layout.box()
        box.label(text="Construction")
        box.prop(s, "tile_size")
        box.prop(s, "floor_height")
        box.prop(s, "wall_thickness")
        box.prop(s, "slab_thickness")
        box.prop(s, "door_width")
        box.prop(s, "door_height")
        box.prop(s, "window_sill_h")
        box.prop(s, "window_head_h")

        box = layout.box()
        box.label(text="Stairs")
        box.prop(s, "stairs_width")
        box.prop(s, "stairs_run_step")
        box.prop(s, "stairs_rise_step")
        box.prop(s, "stair_opening_margin")

        box = layout.box()
        box.label(text="Site / Extras")
        box.prop(s, "lot_padding")
        box.prop(s, "parapet_height")
        box.prop(s, "parapet_thickness")
        box.prop(s, "canopy_width")
        box.prop(s, "canopy_depth")
        box.prop(s, "canopy_height")

        box = layout.box()
        box.label(text="Performance")
        box.prop(s, "auto_rebuild")
        box.prop(s, "interactive_preview")
        box.prop(s, "preview_detail_scale")
        box.prop(s, "rebuild_interval_ms")
        box.prop(s, "idle_full_rebuild_ms")


classes = (PB_PT_main_panel,)

import bpy

from .building_shape import BuildingShape, FloorLevel
from .building_style import BuildingStyle


def _active_mode(settings):
    has_any_asset = any((
        settings.window_asset,
        settings.door_asset,
        settings.corner_asset,
        settings.balcony_asset,
        settings.service_wall_asset,
    ))
    if has_any_asset:
        if all((
            settings.window_asset,
            settings.door_asset,
            settings.corner_asset,
            settings.balcony_asset,
            settings.service_wall_asset,
        )):
            return "asset-driven"
        return "hybrid"
    return "primitive"


def _facade_counts(settings):
    shape = BuildingShape.from_settings(settings, fast_mode=False)
    style = BuildingStyle.from_settings(settings, fast_mode=False)
    counts = {face: {} for face in ("front", "back", "left", "right")}

    for floor_idx in range(shape.floors):
        level = FloorLevel(
            floor_index=floor_idx,
            z_floor=floor_idx * settings.floor_height,
            is_ground=(floor_idx == 0),
            is_top=(floor_idx == shape.floors - 1),
        )
        front = style.facade_stack_for_side(level, "front", shape.width_m, shape.tile_size, require_center_entrance=level.is_ground)
        back = style.facade_stack_for_side(level, "back", shape.width_m, shape.tile_size)
        left = style.facade_stack_for_side(level, "left", shape.depth_m, shape.tile_size)
        right = style.facade_stack_for_side(level, "right", shape.depth_m, shape.tile_size)

        for face, stack in (("front", front), ("back", back), ("left", left), ("right", right)):
            for module in stack.slot_modules(shape.tile_size):
                counts[face][module.id] = counts[face].get(module.id, 0) + 1

    return counts


class PB_PT_main_panel(bpy.types.Panel):
    bl_label = "Procedural Building"
    bl_idname = "PB_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Proc Building'

    def draw(self, context):
        layout = self.layout
        s = context.scene.pb_settings

        box = layout.box()
        box.label(text="Shape", icon='MESH_CUBE')
        box.prop(s, "width_m")
        box.prop(s, "depth_m")
        box.prop(s, "floors")
        box.prop(s, "room_count")
        box.prop(s, "seed")

        row = box.row(align=True)
        row.operator("pb.setup_controllers", icon='EMPTY_AXIS')
        row.operator("pb.sync_size_from_handle", icon='CON_CHILDOF')
        box.operator("pb.reset_controllers", icon='LOOP_BACK')

        box = layout.box()
        box.label(text="Style Preset", icon='SHADING_RENDERED')
        box.prop(s, "style_preset")
        box.prop(s, "material_palette")
        box.prop(s, "wall_tint_variation")
        box.prop(s, "dirt_amount")
        box.prop(s, "glass_tint_strength")
        box.prop(s, "accent_color_strength")
        box.prop(s, "detail_amount")
        box.prop(s, "facade_variation")
        box.prop(s, "accent_strength")
        box.prop(s, "balcony_chance")
        box.prop(s, "band_density")
        box.prop(s, "vertical_fins")
        box.prop(s, "entrance_style")
        box.prop(s, "roof_style")
        box.prop(s, "roof_profile")
        box.prop(s, "roof_detail_density")
        box.prop(s, "rooftop_equipment_amount")
        box.prop(s, "skylight_chance")
        box.prop(s, "solar_panel_chance")

        box = layout.box()
        box.label(text="Floor Profiles", icon='SORTSIZE')
        box.prop(s, "floor_height")
        box.prop(s, "slab_thickness")
        box.prop(s, "tile_size")
        box.prop(s, "wall_thickness")
        box.prop(s, "door_width")
        box.prop(s, "door_height")
        box.prop(s, "window_sill_h")
        box.prop(s, "window_head_h")

        style = BuildingStyle.from_settings(s, fast_mode=False)
        profile_col = box.column(align=True)
        profile_col.label(text=f"Ground: {style.ground_profile.name} / glazing {style.ground_profile.glazing_density:.2f}")
        profile_col.label(text=f"Typical: {style.typical_profile.name} / glazing {style.typical_profile.glazing_density:.2f}")
        profile_col.label(text=f"Top: {style.top_profile.name} / glazing {style.top_profile.glazing_density:.2f}")
        profile_col.label(text=f"Rhythm: {style.bay_rhythm} / Entrance: {style.entrance_preference}")
        profile_col.label(text=f"Roof: {style.roof_profile_preference} / Detail: {style.roof_detail_density:.2f}")

        box = layout.box()
        box.label(text="Asset Modules", icon='ASSET_MANAGER')
        for prop, label in (
            ("window_asset", "Window Asset"),
            ("door_asset", "Door Asset"),
            ("corner_asset", "Corner Asset"),
            ("balcony_asset", "Balcony Asset"),
            ("service_wall_asset", "Service Wall Asset"),
        ):
            row = box.row(align=True)
            row.prop(s, prop, text=label)
            clear_op = row.operator("pb.clear_asset_slot", text="", icon='X')
            clear_op.asset_slot = prop

        box.operator("pb.clear_all_assets", icon='TRASH')

        box = layout.box()
        box.label(text="Performance", icon='TIME')
        box.prop(s, "interactive_preview")
        box.prop(s, "preview_detail_scale")
        box.prop(s, "rebuild_interval_ms")
        box.prop(s, "idle_full_rebuild_ms")
        box.prop(s, "auto_rebuild")

        box = layout.box()
        box.label(text="Actions", icon='TOOL_SETTINGS')
        row = box.row(align=True)
        row.operator("pb.rebuild_shape_only", icon='MOD_BUILD')
        row.operator("pb.rebuild_style_only", icon='BRUSH_DATA')
        box.operator("pb.rebuild_full", icon='FILE_REFRESH')
        box.operator(
            "pb.toggle_auto_rebuild",
            text="Pause Auto Rebuild" if s.auto_rebuild else "Resume Auto Rebuild",
            icon='PAUSE' if s.auto_rebuild else 'PLAY',
        )
        box.operator("pb.bake_generated_result", icon='OUTLINER_OB_MESH')
        box.operator("pb.clear_generated", icon='TRASH')

        debug = layout.box()
        debug.label(text="Debug Summary", icon='INFO')
        debug.label(text=f"Preset: {s.style_preset}")
        debug.label(text=f"Mode: {_active_mode(s)}")
        debug.label(text=f"Last rebuild: {s.pb_last_rebuild_quality}")
        debug.label(text=f"Timer: {s.pb_timer_pause_reason}")

        counts = _facade_counts(s)
        for face in ("front", "back", "left", "right"):
            pairs = sorted(counts[face].items(), key=lambda item: (-item[1], item[0]))
            compact = ", ".join(f"{name.replace('Module', '')}:{count}" for name, count in pairs[:3])
            debug.label(text=f"{face.title()}: {compact if compact else 'none'}")


classes = (PB_PT_main_panel,)

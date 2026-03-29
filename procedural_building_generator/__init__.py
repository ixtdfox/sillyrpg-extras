bl_info = {
    "name": "Procedural Building Generator",
    "author": "OpenAI",
    "version": (0, 1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Proc Building",
    "description": "Interactive low-rise procedural building generator with panel controls",
    "category": "Object",
}

import time

import bpy
from bpy.props import PointerProperty

from . import operators, properties, ui
from .generator import BuildingGenerator
from .utils import GENERATOR_TAG, HANDLE_NAME, ROOT_NAME

_LAST_CONTROLLER_SIG = None
_LAST_SHAPE_SIG = None
_LAST_STYLE_SIG = None
_LAST_CHANGE_TS = 0.0
_LAST_REBUILD_TS = 0.0
_LAST_QUALITY = None
_TIMER_INSTALLED = False
_PENDING_FULL_REBUILD = False
_PENDING_SHAPE_REBUILD = False


def read_controller_sig():
    root = bpy.data.objects.get(ROOT_NAME)
    handle = bpy.data.objects.get(HANDLE_NAME)
    if not root or not handle:
        return None
    return (
        round(root.location.x, 4), round(root.location.y, 4), round(root.location.z, 4),
        round(handle.location.x, 4), round(handle.location.y, 4), round(handle.location.z, 4),
    )


def read_shape_sig():
    s = bpy.context.scene.pb_settings
    return (
        round(s.width_m, 4), round(s.depth_m, 4),
        s.floors, s.room_count, s.seed,
        round(s.tile_size, 4), round(s.floor_height, 4),
        round(s.wall_thickness, 4), round(s.slab_thickness, 4),
        round(s.window_sill_h, 4), round(s.window_head_h, 4),
        round(s.door_width, 4), round(s.door_height, 4),
        round(s.stairs_width, 4), round(s.stairs_run_step, 4),
        round(s.stairs_rise_step, 4), round(s.stair_opening_margin, 4),
        round(s.lot_padding, 4),
        round(s.parapet_height, 4), round(s.parapet_thickness, 4),
        round(s.canopy_depth, 4), round(s.canopy_width, 4), round(s.canopy_height, 4),
    )


def read_style_sig():
    s = bpy.context.scene.pb_settings
    return (
        s.seed,
        round(s.detail_amount, 4),
        s.material_palette,
        round(s.wall_tint_variation, 4),
        round(s.dirt_amount, 4),
        round(s.glass_tint_strength, 4),
        round(s.accent_color_strength, 4),
        round(s.facade_variation, 4),
        round(s.accent_strength, 4),
        round(s.balcony_chance, 4),
        round(s.band_density, 4),
        round(s.vertical_fins, 4),
        s.entrance_style,
        s.roof_style,
        s.roof_profile,
        round(s.roof_detail_density, 4),
        s.rooftop_equipment_amount,
        round(s.skylight_chance, 4),
        round(s.solar_panel_chance, 4),
        s.style_preset,
        int(s.interactive_preview),
        round(s.preview_detail_scale, 4),
        s.rebuild_interval_ms,
        s.idle_full_rebuild_ms,
        int(s.auto_rebuild),
        s.facade_module_mode,
        getattr(s.window_asset, "name_full", ""),
        getattr(s.entrance_asset, "name_full", ""),
        getattr(s.corner_asset, "name_full", ""),
        getattr(s.balcony_asset, "name_full", ""),
        getattr(s.rooftop_utility_asset, "name_full", ""),
    )


def active_generated_object_selected():
    obj = bpy.context.view_layer.objects.active
    if obj is None:
        return False
    return bool(obj.get("generated_by") == GENERATOR_TAG)


def timer_pause_reason():
    ctx = bpy.context
    if ctx.mode != 'OBJECT':
        return "non-object mode"
    if active_generated_object_selected():
        return "generated object selected"
    if not ctx.scene.pb_settings.auto_rebuild:
        return "auto rebuild paused"
    return ""


def timer_should_pause():
    return bool(timer_pause_reason())


def proc_building_timer():
    global _LAST_CONTROLLER_SIG, _LAST_SHAPE_SIG, _LAST_STYLE_SIG, _LAST_CHANGE_TS, _LAST_REBUILD_TS, _LAST_QUALITY
    global _PENDING_FULL_REBUILD, _PENDING_SHAPE_REBUILD

    scene = bpy.context.scene
    if not hasattr(scene, "pb_settings"):
        return 0.25

    controller_sig = read_controller_sig()
    shape_sig = read_shape_sig()
    style_sig = read_style_sig()
    if controller_sig is None:
        return 0.25

    now = time.perf_counter()
    s = scene.pb_settings

    controller_changed = controller_sig != _LAST_CONTROLLER_SIG
    shape_changed = shape_sig != _LAST_SHAPE_SIG
    style_changed = style_sig != _LAST_STYLE_SIG
    if controller_changed or shape_changed or style_changed:
        _LAST_CHANGE_TS = now
        _PENDING_FULL_REBUILD = True
        _PENDING_SHAPE_REBUILD = bool(controller_changed or shape_changed)
        if controller_changed or shape_changed:
            s.pb_timer_pause_reason = "preview rebuild completed; full rebuild queued"
        elif style_changed:
            s.pb_timer_pause_reason = "style change queued"

    hard_pause = ""
    if bpy.context.mode != 'OBJECT':
        hard_pause = "non-object mode"
    elif not s.auto_rebuild:
        hard_pause = "auto rebuild paused"

    generated_selected = active_generated_object_selected()
    if hard_pause:
        s.pb_timer_pause_reason = hard_pause
        return 0.12

    time_since_change_ms = (now - _LAST_CHANGE_TS) * 1000.0
    time_since_rebuild_ms = (now - _LAST_REBUILD_TS) * 1000.0

    if time_since_rebuild_ms >= s.rebuild_interval_ms:
        # Fast preview pass while dragging controllers, but don't force it when
        # generated object is selected (selection-safe behavior).
        if (
            s.interactive_preview
            and controller_changed
            and not generated_selected
        ):
            try:
                BuildingGenerator().build("preview", rebuild_shape=True)
                _LAST_REBUILD_TS = now
                _LAST_QUALITY = "preview"
                s.pb_last_rebuild_quality = "preview"
                print("preview rebuild completed; full rebuild queued")
            except Exception as e:
                print("Proc building preview rebuild failed:", e)

        # Always honor queued full rebuild after idle, even if a generated
        # object remains selected from previous output.
        if _PENDING_FULL_REBUILD and time_since_change_ms >= s.idle_full_rebuild_ms:
            try:
                style_only_change = (not _PENDING_SHAPE_REBUILD) and style_changed and not (controller_changed or shape_changed)
                BuildingGenerator().build("full", rebuild_shape=not style_only_change)
                _LAST_CONTROLLER_SIG = controller_sig
                _LAST_SHAPE_SIG = shape_sig
                _LAST_STYLE_SIG = style_sig
                _LAST_REBUILD_TS = now
                _LAST_QUALITY = "full"
                _PENDING_FULL_REBUILD = False
                _PENDING_SHAPE_REBUILD = False
                s.pb_last_rebuild_quality = "full"
                s.pb_timer_pause_reason = "full rebuild executed after idle"
                print("full rebuild executed after idle")
            except Exception as e:
                print("Proc building full rebuild failed:", e)
        elif generated_selected and _PENDING_FULL_REBUILD:
            s.pb_timer_pause_reason = "timer paused because generated object selected, but pending full rebuild preserved"
        elif generated_selected:
            s.pb_timer_pause_reason = "generated object selected"
        elif not _PENDING_FULL_REBUILD:
            s.pb_timer_pause_reason = "running"

    return 0.08 if s.interactive_preview else 0.15


def install_timer():
    global _TIMER_INSTALLED
    if _TIMER_INSTALLED:
        return
    bpy.app.timers.register(proc_building_timer, first_interval=0.15, persistent=True)
    _TIMER_INSTALLED = True


def register():
    for cls in properties.classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pb_settings = PointerProperty(type=properties.PBSettings)

    for cls in operators.classes:
        bpy.utils.register_class(cls)
    for cls in ui.classes:
        bpy.utils.register_class(cls)

    install_timer()


def unregister():
    if hasattr(bpy.types.Scene, "pb_settings"):
        del bpy.types.Scene.pb_settings

    for cls in reversed(ui.classes):
        bpy.utils.unregister_class(cls)
    for cls in reversed(operators.classes):
        bpy.utils.unregister_class(cls)
    for cls in reversed(properties.classes):
        bpy.utils.unregister_class(cls)

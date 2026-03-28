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
_LAST_PROPS_SIG = None
_LAST_CHANGE_TS = 0.0
_LAST_REBUILD_TS = 0.0
_LAST_QUALITY = None
_TIMER_INSTALLED = False


def read_controller_sig():
    root = bpy.data.objects.get(ROOT_NAME)
    handle = bpy.data.objects.get(HANDLE_NAME)
    if not root or not handle:
        return None
    return (
        round(root.location.x, 4), round(root.location.y, 4), round(root.location.z, 4),
        round(handle.location.x, 4), round(handle.location.y, 4), round(handle.location.z, 4),
    )


def read_props_sig():
    s = bpy.context.scene.pb_settings
    return (
        round(s.width_m, 4), round(s.depth_m, 4),
        s.floors, s.room_count, s.seed,
        round(s.detail_amount, 4), round(s.balcony_chance, 4),
        s.roof_style, round(s.tile_size, 4), round(s.floor_height, 4),
        round(s.wall_thickness, 4), round(s.slab_thickness, 4),
        round(s.window_sill_h, 4), round(s.window_head_h, 4),
        round(s.door_width, 4), round(s.door_height, 4),
        round(s.stairs_width, 4), round(s.stairs_run_step, 4),
        round(s.stairs_rise_step, 4), round(s.stair_opening_margin, 4),
        round(s.lot_padding, 4),
        round(s.parapet_height, 4), round(s.parapet_thickness, 4),
        round(s.canopy_depth, 4), round(s.canopy_width, 4), round(s.canopy_height, 4),
        int(s.interactive_preview), round(s.preview_detail_scale, 4),
        s.rebuild_interval_ms, s.idle_full_rebuild_ms, int(s.auto_rebuild),
    )


def active_generated_object_selected():
    obj = bpy.context.view_layer.objects.active
    if obj is None:
        return False
    return bool(obj.get("generated_by") == GENERATOR_TAG)


def timer_should_pause():
    ctx = bpy.context
    if ctx.mode != 'OBJECT':
        return True
    if active_generated_object_selected():
        return True
    if not ctx.scene.pb_settings.auto_rebuild:
        return True
    return False


def proc_building_timer():
    global _LAST_CONTROLLER_SIG, _LAST_PROPS_SIG, _LAST_CHANGE_TS, _LAST_REBUILD_TS, _LAST_QUALITY

    scene = bpy.context.scene
    if not hasattr(scene, "pb_settings"):
        return 0.25

    controller_sig = read_controller_sig()
    props_sig = read_props_sig()
    if controller_sig is None:
        return 0.25

    now = time.perf_counter()
    s = scene.pb_settings

    controller_changed = controller_sig != _LAST_CONTROLLER_SIG
    props_changed = props_sig != _LAST_PROPS_SIG

    if controller_changed or props_changed:
        _LAST_CONTROLLER_SIG = controller_sig
        _LAST_PROPS_SIG = props_sig
        _LAST_CHANGE_TS = now

    if timer_should_pause():
        return 0.12

    time_since_change_ms = (now - _LAST_CHANGE_TS) * 1000.0
    time_since_rebuild_ms = (now - _LAST_REBUILD_TS) * 1000.0

    quality = "full"
    if s.interactive_preview and controller_changed:
        quality = "preview"
    elif s.interactive_preview and time_since_change_ms < s.idle_full_rebuild_ms and _LAST_QUALITY == "preview":
        quality = "preview"

    if time_since_rebuild_ms >= s.rebuild_interval_ms:
        if (controller_changed or props_changed) or (quality != _LAST_QUALITY and time_since_change_ms >= s.rebuild_interval_ms):
            try:
                BuildingGenerator().build(quality)
                _LAST_REBUILD_TS = now
                _LAST_QUALITY = quality
            except Exception as e:
                print("Proc building rebuild failed:", e)

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

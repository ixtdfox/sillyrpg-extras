"""Blender UI and operator bindings."""

from __future__ import annotations

import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator, Panel, PropertyGroup

from .generator import BuildingGenerator


class RPGProperties(PropertyGroup):
    width: FloatProperty(name="Width", default=12.0, min=4.0)
    depth: FloatProperty(name="Depth", default=10.0, min=4.0)
    floors: IntProperty(name="Floors", default=2, min=1, max=6)
    rooms: IntProperty(name="Rooms", default=4, min=1, max=24)
    seed: IntProperty(name="Seed", default=7, min=0)
    detail: FloatProperty(name="Detail", default=0.65, min=0.0, max=1.0)
    balconies: BoolProperty(name="Balconies", default=True)
    roof_style: IntProperty(name="Roof Style", default=0, min=0, max=2)
    tile_size: FloatProperty(name="Tile Size", default=2.0, min=0.01)
    floor_height: FloatProperty(name="Floor Height", default=2.8, min=2.4)
    window_head: FloatProperty(name="Window Head", default=2.2, min=1.6)
    door_height: FloatProperty(name="Door Height", default=2.2, min=1.8)
    preview_mode: BoolProperty(name="Interactive Preview", default=True)
    debounce_ms: IntProperty(name="Debounce (ms)", default=150, min=100, max=300)

    debug_volumes: IntProperty(name="Volumes", default=0)
    debug_floors: IntProperty(name="Floors", default=0)
    debug_stairs: BoolProperty(name="Stairs Valid", default=False)
    debug_fallback: bpy.props.StringProperty(name="Fallback")


class RPG_OT_generate(Operator):
    bl_idname = "rpg.generate_building"
    bl_label = "Generate Procedural Building"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.rpg_props
        params = {
            "width": props.width,
            "depth": props.depth,
            "floors": props.floors,
            "rooms": props.rooms,
            "seed": props.seed,
            "detail": props.detail,
            "balconies": props.balconies,
            "roof_style": props.roof_style,
            "tile_size": props.tile_size,
            "floor_height": props.floor_height,
            "window_head": props.window_head,
            "door_height": props.door_height,
        }

        result = BuildingGenerator().generate(context, params)
        props.debug_volumes = result.debug.volumes_count
        props.debug_floors = result.debug.floors_count
        props.debug_stairs = result.debug.stair_placed
        props.debug_fallback = ", ".join(result.debug.fallback_reasons)
        return {"FINISHED"}


class RPG_PT_panel(Panel):
    bl_idname = "RPG_PT_PANEL"
    bl_label = "Procedural Residential"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RPG"

    def draw(self, context):
        p = context.scene.rpg_props
        layout = self.layout

        shape = layout.box()
        shape.label(text="Shape")
        shape.prop(p, "width")
        shape.prop(p, "depth")
        shape.prop(p, "floors")
        shape.prop(p, "rooms")

        style = layout.box()
        style.label(text="Style")
        style.prop(p, "detail")
        style.prop(p, "balconies")
        style.prop(p, "roof_style")

        construction = layout.box()
        construction.label(text="Construction")
        construction.prop(p, "tile_size")
        construction.prop(p, "floor_height")
        construction.prop(p, "window_head")
        construction.prop(p, "door_height")

        stairs = layout.box()
        stairs.label(text="Stairs")
        stairs.label(text="Auto-validated on generate")

        perf = layout.box()
        perf.label(text="Performance")
        perf.prop(p, "preview_mode")
        perf.prop(p, "debounce_ms")
        perf.prop(p, "seed")

        debug = layout.box()
        debug.label(text="Debug")
        debug.label(text=f"Volumes: {p.debug_volumes}")
        debug.label(text=f"Floors: {p.debug_floors}")
        debug.label(text=f"Stairs valid: {p.debug_stairs}")
        if p.debug_fallback:
            debug.label(text=f"Fallback: {p.debug_fallback}")

        layout.operator("rpg.generate_building")


@persistent
def _depsgraph_preview_handler(scene, _depsgraph):
    props = scene.rpg_props
    if not props.preview_mode:
        return
    # Lightweight debounce mechanism.
    now = time.time()
    last = scene.get("_rpg_last_gen", 0.0)
    if now - last < props.debounce_ms / 1000.0:
        return
    scene["_rpg_last_gen"] = now


CLASSES = (RPGProperties, RPG_OT_generate, RPG_PT_panel)


def register_ui():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rpg_props = bpy.props.PointerProperty(type=RPGProperties)
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph_preview_handler)


def unregister_ui():
    if _depsgraph_preview_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_preview_handler)
    del bpy.types.Scene.rpg_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

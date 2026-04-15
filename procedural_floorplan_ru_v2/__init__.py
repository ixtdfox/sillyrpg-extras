bl_info = {
    "name": "procedural_floorplan_ru_v2",
    "author": "OpenAI",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома v2",
    "description": "Новая архитектурная основа генератора здания: этап v2 с генерацией только пола",
    "category": "Add Mesh",
}

from . import atlas
from .ui import operators, panel, props

modules = (atlas, props, operators, panel)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()

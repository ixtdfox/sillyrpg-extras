bl_info = {
    "name": "procedural_rooftop_yard_props_ru",
    "author": "OpenAI",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Rooftop/Yard RU",
    "description": "Процедурный генератор rooftop и yard пропсов с atlas manifest pipeline",
    "category": "Add Mesh",
}

import importlib

if "addon" in locals():
    addon = importlib.reload(addon)
else:
    from . import addon


def register():
    addon.register()


def unregister():
    addon.unregister()

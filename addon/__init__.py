bl_info = {
    "name": "Procedural Residential Building Generator",
    "author": "Codex",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > RPG",
    "description": "Generates stable low-rise modern residential buildings",
    "category": "Add Mesh",
}

from .ui import register_ui, unregister_ui


def register():
    register_ui()


def unregister():
    unregister_ui()


bl_info = {
    "name": "Процедурный генератор планировки дома [roofcornerfix 9d2f6]",
    "author": "OpenAI",
    "version": (1, 2, 23),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (roofcornerfix 9d2f6: в углу оставлен один общий столб, без двойной стойки)",
    "category": "Add Mesh",
}

from . import props, operators, ui

modules = (props, operators, ui)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()

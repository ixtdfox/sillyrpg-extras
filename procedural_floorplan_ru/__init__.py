
bl_info = {
    "name": "Процедурный генератор планировки дома [floorbandfix 1a4e9]",
    "author": "OpenAI",
    "version": (1, 2, 27),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (floorbandout 3c8f1: FloorBand выступает наружу из-под стены, RoofBorder только на крыше)",
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


bl_info = {
    "name": "Процедурный генератор планировки дома [trim 7ac31]",
    "author": "OpenAI",
    "version": (1, 3, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (trim 7ac31: подтёки только в верхнем ряду стен, 1м ширина, бортики крыши и межэтажные балки)",
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

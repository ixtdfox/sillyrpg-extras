
bl_info = {
    "name": "Процедурный генератор планировки дома [trimcontinue 4be72]",
    "author": "OpenAI",
    "version": (1, 2, 17),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (trimcontinue 4be72: бортики как продолжение стены, балки центрируются на шве, только по внешнему периметру, вровень со стеной)",
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


bl_info = {
    "name": "Процедурный генератор планировки дома [windowdrip 5c1e8]",
    "author": "OpenAI",
    "version": (1, 2, 18),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (windowdrip 5c1e8: исправлены подтёки над окнами, короткие верхние полосы стены больше не отфильтровываются)",
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

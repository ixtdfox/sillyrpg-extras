
bl_info = {
    "name": "Процедурный генератор планировки дома [cornerposts 6d4b2]",
    "author": "OpenAI",
    "version": (1, 2, 28),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > План дома",
    "description": "Генератор планировки дома с русскими настройками и тултипами (cornerposts 6d4b2: добавлены угловые столбы по внешним углам здания для скрытия стыков стен)",
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

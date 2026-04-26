from __future__ import annotations

import importlib

import bpy

if "atlas_manifest" in locals():
    atlas_manifest = importlib.reload(atlas_manifest)
    textures = importlib.reload(textures)
    generator = importlib.reload(generator)
    props = importlib.reload(props)
    operators = importlib.reload(operators)
    ui = importlib.reload(ui)
else:
    from . import atlas_manifest, generator, operators, props, textures, ui

modules = (atlas_manifest, textures, props, operators, ui)
_registered = False


def _operator_rna_identifier(bl_idname: str) -> str:
    prefix, suffix = bl_idname.split(".", 1)
    return f"{prefix.upper()}_OT_{suffix}"


def _registered_class_identifier(cls) -> str:
    if issubclass(cls, bpy.types.Operator):
        return _operator_rna_identifier(cls.bl_idname)
    if issubclass(cls, bpy.types.Panel):
        return getattr(cls, "bl_idname", "") or cls.__name__
    return cls.__name__


def _find_registered_class(cls):
    identifier = _registered_class_identifier(cls)
    for base in cls.__mro__[1:]:
        getter = getattr(base, "bl_rna_get_subclass_py", None)
        if getter is None:
            continue
        try:
            existing = getter(identifier)
        except TypeError:
            existing = getter(identifier, None)
        except Exception:
            existing = None
        if existing is not None:
            return existing
    return None


def safe_register_class(cls) -> None:
    existing = _find_registered_class(cls)
    if existing is cls:
        return
    if existing is not None:
        bpy.utils.unregister_class(existing)
    bpy.utils.register_class(cls)


def safe_unregister_class(cls) -> None:
    existing = _find_registered_class(cls)
    if existing is None:
        return
    bpy.utils.unregister_class(existing)


def register():
    global _registered
    if _registered:
        unregister()
    for module in modules:
        module.register()
    _registered = True


def unregister():
    global _registered
    for module in reversed(modules):
        module.unregister()
    _registered = False

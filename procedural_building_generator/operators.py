import bpy

from .generator import BuildingGenerator
from .utils import (
    COLLECTION_NAME,
    GENERATOR_TAG,
    HANDLE_NAME,
    ROOT_NAME,
    clear_generated_objects,
    ensure_collection,
    ensure_empty,
)


class PB_OT_setup_controllers(bpy.types.Operator):
    bl_idname = "pb.setup_controllers"
    bl_label = "Setup Controllers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.pb_settings
        ensure_empty(ROOT_NAME, 'ARROWS', (0, 0, 0))
        ensure_empty(HANDLE_NAME, 'CUBE', (s.width_m, s.depth_m, 0))
        self.report({'INFO'}, "Controllers created")
        return {'FINISHED'}


class PB_OT_sync_size_from_handle(bpy.types.Operator):
    bl_idname = "pb.sync_size_from_handle"
    bl_label = "Sync Size From Handle"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = bpy.data.objects.get(ROOT_NAME)
        handle = bpy.data.objects.get(HANDLE_NAME)
        if not root or not handle:
            self.report({'WARNING'}, "Create controllers first")
            return {'CANCELLED'}

        s = context.scene.pb_settings
        s.width_m = max(8.0, abs(handle.location.x - root.location.x))
        s.depth_m = max(8.0, abs(handle.location.y - root.location.y))
        self.report({'INFO'}, "Size synced from handle")
        return {'FINISHED'}


class PB_OT_reset_controllers(bpy.types.Operator):
    bl_idname = "pb.reset_controllers"
    bl_label = "Reset Controllers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.pb_settings
        root = ensure_empty(ROOT_NAME, 'ARROWS', (0, 0, 0))
        handle = ensure_empty(HANDLE_NAME, 'CUBE', (s.width_m, s.depth_m, 0))
        root.location = (0.0, 0.0, 0.0)
        handle.location = (s.width_m, s.depth_m, 0.0)
        self.report({'INFO'}, "Controllers reset")
        return {'FINISHED'}


class PB_OT_rebuild_shape_only(bpy.types.Operator):
    bl_idname = "pb.rebuild_shape_only"
    bl_label = "Rebuild Shape Only"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        BuildingGenerator().build("full", rebuild_shape=True)
        self.report({'INFO'}, "Shape rebuilt")
        return {'FINISHED'}


class PB_OT_rebuild_style_only(bpy.types.Operator):
    bl_idname = "pb.rebuild_style_only"
    bl_label = "Rebuild Style Only"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        BuildingGenerator().build("full", rebuild_shape=False)
        self.report({'INFO'}, "Style rebuilt")
        return {'FINISHED'}


class PB_OT_rebuild_full(bpy.types.Operator):
    bl_idname = "pb.rebuild_full"
    bl_label = "Rebuild Full"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        BuildingGenerator().build("full", rebuild_shape=True)
        self.report({'INFO'}, "Building rebuilt")
        return {'FINISHED'}


class PB_OT_build_now(bpy.types.Operator):
    bl_idname = "pb.build_now"
    bl_label = "Build Now"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        BuildingGenerator().build("full")
        self.report({'INFO'}, "Building rebuilt")
        return {'FINISHED'}


class PB_OT_clear_generated(bpy.types.Operator):
    bl_idname = "pb.clear_generated"
    bl_label = "Clear Generated"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clear_generated_objects(ensure_collection(COLLECTION_NAME))
        self.report({'INFO'}, "Generated building cleared")
        return {'FINISHED'}


class PB_OT_toggle_auto_rebuild(bpy.types.Operator):
    bl_idname = "pb.toggle_auto_rebuild"
    bl_label = "Pause / Resume Auto Rebuild"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.pb_settings
        s.auto_rebuild = not s.auto_rebuild
        self.report({'INFO'}, "Auto rebuild resumed" if s.auto_rebuild else "Auto rebuild paused")
        return {'FINISHED'}


class PB_OT_bake_generated_result(bpy.types.Operator):
    bl_idname = "pb.bake_generated_result"
    bl_label = "Bake Generated Result"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        src_col = ensure_collection(COLLECTION_NAME)
        bake_col = bpy.data.collections.get("ProcBuilding_Baked")
        if bake_col is None:
            bake_col = bpy.data.collections.new("ProcBuilding_Baked")
            context.scene.collection.children.link(bake_col)

        baked = 0
        for obj in list(src_col.objects):
            if obj.get("generated_by") != GENERATOR_TAG:
                continue
            baked_obj = obj.copy()
            baked_obj.data = obj.data.copy() if obj.data else None
            baked_obj.animation_data_clear()
            for key in ("generated_by", "pb_asset_instance", "pb_module_id"):
                if key in baked_obj:
                    del baked_obj[key]
            baked_obj.name = f"Baked_{obj.name}"
            bake_col.objects.link(baked_obj)
            baked += 1

        if baked == 0:
            self.report({'WARNING'}, "No generated objects to bake")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Baked {baked} object(s)")
        return {'FINISHED'}


class PB_OT_clear_asset_slot(bpy.types.Operator):
    bl_idname = "pb.clear_asset_slot"
    bl_label = "Clear Assigned Asset"
    bl_options = {'REGISTER', 'UNDO'}

    asset_slot: bpy.props.StringProperty(name="Asset Slot")

    def execute(self, context):
        s = context.scene.pb_settings
        if not hasattr(s, self.asset_slot):
            self.report({'WARNING'}, "Unknown asset slot")
            return {'CANCELLED'}
        setattr(s, self.asset_slot, None)
        self.report({'INFO'}, "Asset slot cleared")
        return {'FINISHED'}


class PB_OT_clear_all_assets(bpy.types.Operator):
    bl_idname = "pb.clear_all_assets"
    bl_label = "Clear All Assigned Assets"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.pb_settings
        s.window_asset = None
        s.entrance_asset = None
        s.corner_asset = None
        s.balcony_asset = None
        s.rooftop_utility_asset = None
        self.report({'INFO'}, "All asset assignments cleared")
        return {'FINISHED'}


classes = (
    PB_OT_setup_controllers,
    PB_OT_sync_size_from_handle,
    PB_OT_reset_controllers,
    PB_OT_rebuild_shape_only,
    PB_OT_rebuild_style_only,
    PB_OT_rebuild_full,
    PB_OT_build_now,
    PB_OT_toggle_auto_rebuild,
    PB_OT_bake_generated_result,
    PB_OT_clear_generated,
    PB_OT_clear_asset_slot,
    PB_OT_clear_all_assets,
)

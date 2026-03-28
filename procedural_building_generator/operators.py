import bpy

from .generator import BuildingGenerator
from .utils import COLLECTION_NAME, HANDLE_NAME, ROOT_NAME, clear_generated_objects, ensure_collection, ensure_empty


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


classes = (
    PB_OT_setup_controllers,
    PB_OT_build_now,
    PB_OT_clear_generated,
)

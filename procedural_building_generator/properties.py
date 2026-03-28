import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


class PBSettings(bpy.types.PropertyGroup):
    facade_module_mode: EnumProperty(
        name="Facade Module Mode",
        items=(
            ("PROCEDURAL_ONLY", "Procedural Only", "Always build procedural facade and rooftop modules"),
            ("HYBRID", "Hybrid", "Use assigned assets where available and procedural fallback otherwise"),
            ("ASSET_PREFERRED", "Asset Preferred", "Prefer assigned assets and only fallback when a slot is unassigned"),
        ),
        default="HYBRID",
    )
    width_m: FloatProperty(name="Width", default=16.0, min=8.0, step=200)
    depth_m: FloatProperty(name="Depth", default=12.0, min=8.0, step=200)
    floors: IntProperty(name="Floors", default=2, min=1, max=3)
    room_count: IntProperty(name="Rooms", default=6, min=1, max=12)
    seed: IntProperty(name="Seed", default=11)
    detail_amount: FloatProperty(name="Detail", default=0.75, min=0.0, max=1.0)
    style_preset: EnumProperty(
        name="Style Preset",
        items=(
            ("SCIENTIST_HOUSING", "Scientist Housing", "Cleaner, lighter housing with high glazing"),
            ("TECHNICIAN_HOUSING", "Technician Housing", "Practical modular housing with balanced solids/windows"),
            ("SECURITY_HOUSING", "Security Housing", "Rigid and more solid housing with reduced balconies"),
            ("SERVICE_RESIDENCE", "Service Residence", "Simple and economical residence with restrained detail"),
        ),
        default="SCIENTIST_HOUSING",
    )
    material_palette: EnumProperty(
        name="Material Palette",
        items=(
            ("PRESET", "Preset Driven", "Use palette values from selected style preset"),
            ("NEUTRAL", "Neutral", "Balanced neutral plaster and trim palette"),
            ("COOL", "Cool", "Slightly cooler concrete and glass tint"),
            ("WARM", "Warm", "Warmer painted concrete and trim tint"),
            ("INDUSTRIAL", "Industrial", "Darker utilitarian tones with restrained accent"),
        ),
        default="PRESET",
    )
    wall_tint_variation: FloatProperty(name="Wall Tint Variation", default=0.28, min=0.0, max=1.0)
    dirt_amount: FloatProperty(name="Wall Dirt Amount", default=0.34, min=0.0, max=1.0)
    glass_tint_strength: FloatProperty(name="Glass Tint Strength", default=0.62, min=0.0, max=1.0)
    accent_color_strength: FloatProperty(name="Accent Color Strength", default=0.72, min=0.0, max=1.0)
    balcony_chance: FloatProperty(name="Balconies", default=0.45, min=0.0, max=1.0)
    facade_variation: FloatProperty(name="Facade Variation", default=0.65, min=0.0, max=1.0)
    accent_strength: FloatProperty(name="Accent Strength", default=0.55, min=0.0, max=1.0)
    entrance_style: EnumProperty(
        name="Entrance Style",
        items=(
            ("RECESSED", "Recessed", "Central recessed entrance with stronger portal reads"),
            ("FLAT", "Flat", "Flush entrance with minimal recess"),
            ("BOLD", "Bold", "Recessed entrance with higher chance of canopy and side frames"),
        ),
        default="RECESSED",
    )
    band_density: FloatProperty(name="Band Density", default=0.5, min=0.0, max=1.0)
    vertical_fins: FloatProperty(name="Vertical Fins", default=0.45, min=0.0, max=1.0)
    roof_style: IntProperty(name="Roof Style", default=1, min=0, max=2)
    roof_profile: EnumProperty(
        name="Roof Profile",
        items=(
            ("FLAT", "Flat", "Plain flat roof profile"),
            ("RAISED_PARAPET", "Raised Parapet", "Flat roof with taller parapet silhouette"),
            ("STEPPED_PARAPET", "Stepped Parapet", "Parapet with stepped edge accents"),
            ("ACCESS_VOLUME", "Access Volume", "Partial rooftop access volume"),
        ),
        default="RAISED_PARAPET",
    )
    roof_detail_density: FloatProperty(name="Roof Detail Density", default=0.55, min=0.0, max=1.0)
    rooftop_equipment_amount: IntProperty(name="Rooftop Equipment", default=5, min=0, max=24)
    skylight_chance: FloatProperty(name="Skylight Chance", default=0.35, min=0.0, max=1.0)
    solar_panel_chance: FloatProperty(name="Solar Panel Chance", default=0.45, min=0.0, max=1.0)
    tile_size: FloatProperty(name="Tile Size", default=2.0, min=1.0)
    floor_height: FloatProperty(name="Floor Height", default=2.8, min=2.2)
    wall_thickness: FloatProperty(name="Wall Thickness", default=0.18, min=0.05)
    slab_thickness: FloatProperty(name="Slab Thickness", default=0.18, min=0.05)
    window_sill_h: FloatProperty(name="Window Sill", default=0.85, min=0.2)
    window_head_h: FloatProperty(name="Window Head", default=2.25, min=1.2)
    door_width: FloatProperty(name="Door Width", default=1.0, min=0.6)
    door_height: FloatProperty(name="Door Height", default=2.1, min=1.6)
    stairs_width: FloatProperty(name="Stairs Width", default=1.4, min=1.0)
    stairs_run_step: FloatProperty(name="Stair Run", default=0.28, min=0.15)
    stairs_rise_step: FloatProperty(name="Stair Rise", default=0.175, min=0.1)
    stair_opening_margin: FloatProperty(name="Opening Margin", default=0.18, min=0.0)
    lot_padding: FloatProperty(name="Lot Padding", default=1.5, min=0.0)
    parapet_height: FloatProperty(name="Parapet Height", default=0.32, min=0.0)
    parapet_thickness: FloatProperty(name="Parapet Thickness", default=0.12, min=0.02)
    canopy_depth: FloatProperty(name="Canopy Depth", default=1.2, min=0.0)
    canopy_width: FloatProperty(name="Canopy Width", default=3.8, min=0.0)
    canopy_height: FloatProperty(name="Canopy Height", default=2.45, min=0.0)
    interactive_preview: BoolProperty(name="Interactive Preview", default=True)
    preview_detail_scale: FloatProperty(name="Preview Detail Scale", default=0.35, min=0.0, max=1.0)
    rebuild_interval_ms: IntProperty(name="Rebuild Interval ms", default=120, min=10, max=1000)
    idle_full_rebuild_ms: IntProperty(name="Idle Full Rebuild ms", default=320, min=50, max=2000)
    auto_rebuild: BoolProperty(name="Auto Rebuild", default=True)
    window_asset: PointerProperty(name="Window Asset", type=bpy.types.Object)
    entrance_asset: PointerProperty(name="Entrance Asset", type=bpy.types.Object)
    corner_asset: PointerProperty(name="Corner Asset", type=bpy.types.Object)
    balcony_asset: PointerProperty(name="Balcony Asset", type=bpy.types.Object)
    rooftop_utility_asset: PointerProperty(name="Rooftop Utility Asset", type=bpy.types.Object)
    pb_last_rebuild_quality: StringProperty(name="Last Rebuild", default="none")
    pb_timer_pause_reason: StringProperty(name="Timer Pause Reason", default="none")


classes = (PBSettings,)

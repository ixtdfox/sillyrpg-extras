"""Top-level generation pipeline for the procedural building addon."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import assembler, materials, shape, stairs, style, validation


@dataclass
class DebugInfo:
    volumes_count: int = 0
    floors_count: int = 1
    stair_placed: bool = False
    fallback_reasons: List[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    objects: List[object]
    debug: DebugInfo


class BuildingGenerator:
    """Coordinates the full generation pipeline."""

    def generate(self, context, params: Dict) -> GenerationResult:
        debug = DebugInfo(floors_count=params.get("floors", 1))
        valid_params = validation.validate_parameters(params, debug.fallback_reasons)

        shape_result = shape.generate_shape(valid_params, debug.fallback_reasons)
        debug.volumes_count = len(shape_result.volumes)

        styled_result = style.apply_style(shape_result, valid_params, debug.fallback_reasons)

        stair_plan = stairs.plan_stairs(styled_result, valid_params, debug.fallback_reasons)
        debug.stair_placed = stair_plan.valid

        built_objects = assembler.assemble(context, styled_result, stair_plan, valid_params)
        materials.apply_materials(built_objects, valid_params)
        assembler.cleanup_meshes(context, built_objects)

        return GenerationResult(objects=built_objects, debug=debug)

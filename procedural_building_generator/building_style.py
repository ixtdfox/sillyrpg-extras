from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class FloorProfile:
    floor_index: int
    z_floor: float
    is_ground: bool
    is_top: bool


@dataclass(frozen=True)
class FacadeModuleDefinition:
    id: str
    category: str
    nominal_width: float
    probability: float
    can_scale: bool
    supports_ground_floor: bool
    supports_typical_floor: bool
    supports_top_floor: bool


@dataclass(frozen=True)
class FacadeStackModule:
    module: FacadeModuleDefinition
    width: float


@dataclass(frozen=True)
class FacadeStack:
    face: str
    side_width: float
    modules: tuple[FacadeStackModule, ...]

    def slot_modules(self, tile_size: float) -> list[FacadeModuleDefinition]:
        slots: list[FacadeModuleDefinition] = []
        for item in self.modules:
            count = max(1, int(round(item.width / tile_size)))
            slots.extend([item.module] * count)
        return slots


@dataclass(frozen=True)
class BuildingStyle:
    seed: int
    side_window_probability: float
    roof_rule: int
    accent_preference: float

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingStyle":
        side_prob = 0.45 if fast_mode else 0.7
        return cls(
            seed=int(settings.seed),
            side_window_probability=side_prob,
            roof_rule=int(settings.roof_style),
            accent_preference=float(settings.detail_amount),
        )

    def facade_stack_for_side(
        self,
        profile: FloorProfile,
        face: str,
        side_width: float,
        tile_size: float,
        require_center_entrance: bool = False,
    ) -> FacadeStack:
        definitions = self._module_definitions(tile_size)
        slots_total = max(1, int(round(side_width / tile_size)))
        center_idx = slots_total // 2
        modules_by_slot: list[FacadeModuleDefinition | None] = [None] * slots_total

        corner = definitions["CornerModule"]
        modules_by_slot[0] = corner
        if slots_total > 1:
            modules_by_slot[-1] = corner

        if require_center_entrance and slots_total >= 3:
            modules_by_slot[center_idx] = definitions["EntranceDoorModule"]

        face_idx = {"front": 0, "back": 1, "left": 2, "right": 3}[face]
        floor_seed = self.seed + profile.floor_index * 10007 + face_idx * 997
        rng = random.Random(floor_seed)

        # Ensure at least one scalable filler so any leftover contiguous space is represented by scalable modules.
        empty_slots = [i for i, mod in enumerate(modules_by_slot) if mod is None]
        if empty_slots:
            anchor_slot = empty_slots[len(empty_slots) // 2]
            filler = self._pick_weighted_module(profile, face, rng, definitions, scalable_only=True)
            modules_by_slot[anchor_slot] = filler

        for idx, module in enumerate(modules_by_slot):
            if module is not None:
                continue
            modules_by_slot[idx] = self._pick_weighted_module(profile, face, rng, definitions)

        resolved = [mod for mod in modules_by_slot if mod is not None]
        assert len(resolved) == slots_total

        stack_modules: list[FacadeStackModule] = []
        run_mod = resolved[0]
        run_len = 1
        for mod in resolved[1:]:
            if mod.id == run_mod.id and mod.can_scale:
                run_len += 1
                continue
            stack_modules.append(FacadeStackModule(module=run_mod, width=run_len * tile_size))
            run_mod = mod
            run_len = 1
        stack_modules.append(FacadeStackModule(module=run_mod, width=run_len * tile_size))

        return FacadeStack(face=face, side_width=side_width, modules=tuple(stack_modules))

    def _pick_weighted_module(self, profile, face, rng, definitions, scalable_only: bool = False) -> FacadeModuleDefinition:
        candidates: list[FacadeModuleDefinition] = []
        for module in definitions.values():
            if scalable_only and not module.can_scale:
                continue
            if module.id in {"CornerModule", "EntranceDoorModule"}:
                continue
            if not self._supports_floor(module, profile):
                continue
            if face in {"left", "right"} and module.id == "StandardWindowModule":
                probability = module.probability * self.side_window_probability
                candidates.append(FacadeModuleDefinition(
                    id=module.id,
                    category=module.category,
                    nominal_width=module.nominal_width,
                    probability=probability,
                    can_scale=module.can_scale,
                    supports_ground_floor=module.supports_ground_floor,
                    supports_typical_floor=module.supports_typical_floor,
                    supports_top_floor=module.supports_top_floor,
                ))
                continue
            candidates.append(module)

        total = sum(max(0.0, m.probability) for m in candidates)
        if total <= 0.0:
            return definitions["SolidWallModule"]

        pick = rng.random() * total
        roll = 0.0
        for module in candidates:
            roll += max(0.0, module.probability)
            if pick <= roll:
                return module
        return candidates[-1]

    def _supports_floor(self, module: FacadeModuleDefinition, profile: FloorProfile) -> bool:
        if profile.is_ground:
            return module.supports_ground_floor
        if profile.is_top:
            return module.supports_top_floor
        return module.supports_typical_floor

    def _module_definitions(self, tile_size: float) -> dict[str, FacadeModuleDefinition]:
        return {
            "SolidWallModule": FacadeModuleDefinition(
                id="SolidWallModule",
                category="wall",
                nominal_width=tile_size,
                probability=0.28,
                can_scale=True,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "StandardWindowModule": FacadeModuleDefinition(
                id="StandardWindowModule",
                category="window",
                nominal_width=tile_size,
                probability=0.45,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "EntranceDoorModule": FacadeModuleDefinition(
                id="EntranceDoorModule",
                category="entry",
                nominal_width=tile_size,
                probability=0.0,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=False,
                supports_top_floor=False,
            ),
            "StairWindowModule": FacadeModuleDefinition(
                id="StairWindowModule",
                category="stair_window",
                nominal_width=tile_size,
                probability=0.08,
                can_scale=False,
                supports_ground_floor=False,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "BalconyModule": FacadeModuleDefinition(
                id="BalconyModule",
                category="balcony",
                nominal_width=tile_size,
                probability=0.06,
                can_scale=False,
                supports_ground_floor=False,
                supports_typical_floor=True,
                supports_top_floor=False,
            ),
            "CornerModule": FacadeModuleDefinition(
                id="CornerModule",
                category="corner",
                nominal_width=tile_size,
                probability=1.0,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "ServiceWallModule": FacadeModuleDefinition(
                id="ServiceWallModule",
                category="service",
                nominal_width=tile_size,
                probability=0.13,
                can_scale=True,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
        }

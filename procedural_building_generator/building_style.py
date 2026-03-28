from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class FloorLevel:
    floor_index: int
    z_floor: float
    is_ground: bool
    is_top: bool


@dataclass(frozen=True)
class FloorProfile:
    name: str
    allowed_facade_modules: tuple[str, ...]
    module_probabilities: dict[str, float]
    glazing_density: float
    balcony_allowance: float
    accent_allowance: float


@dataclass(frozen=True)
class GroundFloorProfile(FloorProfile):
    pass


@dataclass(frozen=True)
class TypicalFloorProfile(FloorProfile):
    pass


@dataclass(frozen=True)
class TopFloorProfile(FloorProfile):
    pass


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
    facade_variation: float
    accent_strength: float
    band_density: float
    vertical_fins: float
    entrance_style: str
    balcony_floor_mask: tuple[bool, ...]
    preset: str
    ground_profile: GroundFloorProfile
    typical_profile: TypicalFloorProfile
    top_profile: TopFloorProfile

    @classmethod
    def from_settings(cls, settings, fast_mode: bool) -> "BuildingStyle":
        side_prob = 0.45 if fast_mode else 0.7
        preset = str(getattr(settings, "style_preset", "SCIENTIST_HOUSING"))
        ground, typical, top = cls._preset_profiles(preset)
        return cls(
            seed=int(settings.seed),
            side_window_probability=side_prob,
            roof_rule=int(settings.roof_style),
            accent_preference=float(settings.detail_amount),
            facade_variation=float(getattr(settings, "facade_variation", settings.detail_amount)),
            accent_strength=float(getattr(settings, "accent_strength", settings.detail_amount)),
            band_density=float(getattr(settings, "band_density", settings.detail_amount)),
            vertical_fins=float(getattr(settings, "vertical_fins", settings.detail_amount)),
            entrance_style=str(getattr(settings, "entrance_style", "RECESSED")),
            balcony_floor_mask=cls._balcony_floor_mask(
                floors=int(settings.floors),
                seed=int(settings.seed),
                density=float(getattr(settings, "facade_variation", settings.detail_amount)),
            ),
            preset=preset,
            ground_profile=ground,
            typical_profile=typical,
            top_profile=top,
        )

    def profile_for_floor(self, floor: FloorLevel) -> FloorProfile:
        if floor.is_ground:
            return self.ground_profile
        if floor.is_top:
            return self.top_profile
        return self.typical_profile

    def facade_stack_for_side(
        self,
        floor: FloorLevel,
        face: str,
        side_width: float,
        tile_size: float,
        require_center_entrance: bool = False,
    ) -> FacadeStack:
        definitions = self._module_definitions(tile_size)
        floor_profile = self.profile_for_floor(floor)
        slots_total = max(1, int(round(side_width / tile_size)))
        center_idx = slots_total // 2
        modules_by_slot: list[FacadeModuleDefinition | None] = [None] * slots_total

        corner = definitions["CornerModule"]
        modules_by_slot[0] = corner
        if slots_total > 1:
            modules_by_slot[-1] = corner

        if require_center_entrance and slots_total >= 3:
            modules_by_slot[center_idx] = definitions["EntranceDoorModule"]
            if face == "front":
                flank = "WideWindowBayModule" if slots_total >= 5 else "NarrowWindowBayModule"
                if center_idx - 1 > 0:
                    modules_by_slot[center_idx - 1] = definitions[flank]
                if center_idx + 1 < slots_total - 1:
                    modules_by_slot[center_idx + 1] = definitions[flank]

        face_idx = {"front": 0, "back": 1, "left": 2, "right": 3}[face]
        floor_seed = self.seed + floor.floor_index * 10007 + face_idx * 997
        rng = random.Random(floor_seed)

        empty_slots = [i for i, mod in enumerate(modules_by_slot) if mod is None]
        if empty_slots:
            anchor_slot = empty_slots[len(empty_slots) // 2]
            filler = self._pick_weighted_module(floor, face, floor_profile, rng, definitions, scalable_only=True)
            modules_by_slot[anchor_slot] = filler

        for idx, module in enumerate(modules_by_slot):
            if module is not None:
                continue
            modules_by_slot[idx] = self._pick_weighted_module(floor, face, floor_profile, rng, definitions)

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

    def _pick_weighted_module(
        self,
        floor: FloorLevel,
        face: str,
        floor_profile: FloorProfile,
        rng,
        definitions,
        scalable_only: bool = False,
    ) -> FacadeModuleDefinition:
        candidates: list[FacadeModuleDefinition] = []
        for module in definitions.values():
            if scalable_only and not module.can_scale:
                continue
            if module.id in {"CornerModule", "EntranceDoorModule"}:
                continue
            if module.id not in floor_profile.allowed_facade_modules:
                continue
            if not self._supports_floor(module, floor):
                continue

            probability = floor_profile.module_probabilities.get(module.id, module.probability)
            probability = self._adjust_probability(module, face, probability, floor_profile, floor)
            if probability <= 0.0:
                continue

            candidates.append(
                FacadeModuleDefinition(
                    id=module.id,
                    category=module.category,
                    nominal_width=module.nominal_width,
                    probability=probability,
                    can_scale=module.can_scale,
                    supports_ground_floor=module.supports_ground_floor,
                    supports_typical_floor=module.supports_typical_floor,
                    supports_top_floor=module.supports_top_floor,
                )
            )

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

    def _adjust_probability(
        self,
        module: FacadeModuleDefinition,
        face: str,
        base_probability: float,
        floor_profile: FloorProfile,
        floor: FloorLevel,
    ) -> float:
        probability = base_probability
        if module.id in {"StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule"}:
            probability *= floor_profile.glazing_density
            if face in {"left", "right"}:
                probability *= self.side_window_probability
            if module.id == "NarrowWindowBayModule":
                probability *= 0.7 + self.facade_variation * 0.9
            elif module.id == "WideWindowBayModule":
                probability *= 0.55 + self.facade_variation * 1.1
        elif module.id == "BalconyModule":
            probability *= floor_profile.balcony_allowance
            if face in {"left", "right"}:
                probability *= 0.45
            if not self._is_balcony_floor_allowed(floor.floor_index):
                probability = 0.0
        elif module.id in {"StairWindowModule", "AccentPanelModule"}:
            probability *= floor_profile.accent_allowance * (0.55 + self.accent_strength * 0.95)
        elif module.id in {"ServiceWallModule", "ServiceBayModule"}:
            probability *= max(0.15, 1.0 - floor_profile.glazing_density * 0.6)
            probability *= 0.8 + (1.0 - self.facade_variation) * 0.6
        elif module.id == "SolidWallBayModule":
            probability *= 0.65 + (1.0 - self.facade_variation) * 0.75
        elif module.id == "RecessedStripModule":
            probability *= 0.4 + self.vertical_fins * 0.9
        if face == "back" and module.id in {"BalconyModule", "WideWindowBayModule"}:
            probability *= 0.6
        return probability

    def _supports_floor(self, module: FacadeModuleDefinition, floor: FloorLevel) -> bool:
        if floor.is_ground:
            return module.supports_ground_floor
        if floor.is_top:
            return module.supports_top_floor
        return module.supports_typical_floor

    @classmethod
    def _preset_profiles(cls, preset: str) -> tuple[GroundFloorProfile, TypicalFloorProfile, TopFloorProfile]:
        presets = {
            "SCIENTIST_HOUSING": cls._make_profiles(
                ground=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "ServiceWallModule", "ServiceBayModule", "StairWindowModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.3, "NarrowWindowBayModule": 0.18, "WideWindowBayModule": 0.07, "ServiceWallModule": 0.13, "ServiceBayModule": 0.08, "StairWindowModule": 0.1, "AccentPanelModule": 0.1, "RecessedStripModule": 0.04},
                    glazing=0.72,
                    balcony=0.05,
                    accent=0.65,
                ),
                typical=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "StairWindowModule", "BalconyModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.32, "NarrowWindowBayModule": 0.18, "WideWindowBayModule": 0.12, "SolidWallModule": 0.1, "SolidWallBayModule": 0.07, "StairWindowModule": 0.08, "BalconyModule": 0.07, "AccentPanelModule": 0.04, "RecessedStripModule": 0.02},
                    glazing=0.86,
                    balcony=0.18,
                    accent=0.52,
                ),
                top=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "BalconyModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.28, "NarrowWindowBayModule": 0.15, "WideWindowBayModule": 0.13, "BalconyModule": 0.18, "AccentPanelModule": 0.12, "SolidWallModule": 0.08, "SolidWallBayModule": 0.06},
                    glazing=0.8,
                    balcony=0.42,
                    accent=0.82,
                ),
            ),
            "TECHNICIAN_HOUSING": cls._make_profiles(
                ground=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "ServiceWallModule", "ServiceBayModule", "EntranceDoorModule", "StairWindowModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.23, "NarrowWindowBayModule": 0.14, "WideWindowBayModule": 0.06, "ServiceWallModule": 0.22, "ServiceBayModule": 0.12, "StairWindowModule": 0.13, "SolidWallModule": 0.1},
                    glazing=0.58,
                    balcony=0.04,
                    accent=0.4,
                ),
                typical=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "StairWindowModule", "BalconyModule", "ServiceWallModule", "ServiceBayModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.28, "NarrowWindowBayModule": 0.16, "WideWindowBayModule": 0.1, "SolidWallModule": 0.11, "SolidWallBayModule": 0.07, "ServiceWallModule": 0.1, "ServiceBayModule": 0.06, "StairWindowModule": 0.07, "BalconyModule": 0.05},
                    glazing=0.74,
                    balcony=0.12,
                    accent=0.35,
                ),
                top=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "StandardWindowModule", "NarrowWindowBayModule", "WideWindowBayModule", "BalconyModule", "ServiceWallModule", "ServiceBayModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.22, "NarrowWindowBayModule": 0.14, "WideWindowBayModule": 0.1, "BalconyModule": 0.16, "ServiceWallModule": 0.16, "ServiceBayModule": 0.08, "AccentPanelModule": 0.08, "SolidWallModule": 0.06},
                    glazing=0.68,
                    balcony=0.28,
                    accent=0.56,
                ),
            ),
            "SECURITY_HOUSING": cls._make_profiles(
                ground=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"ServiceWallModule": 0.3, "ServiceBayModule": 0.14, "SolidWallModule": 0.2, "SolidWallBayModule": 0.12, "StandardWindowModule": 0.14, "NarrowWindowBayModule": 0.06, "AccentPanelModule": 0.04},
                    glazing=0.44,
                    balcony=0.01,
                    accent=0.38,
                ),
                typical=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "StairWindowModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.2, "NarrowWindowBayModule": 0.1, "ServiceWallModule": 0.24, "ServiceBayModule": 0.12, "SolidWallModule": 0.14, "SolidWallBayModule": 0.12, "StairWindowModule": 0.06, "RecessedStripModule": 0.02},
                    glazing=0.57,
                    balcony=0.02,
                    accent=0.22,
                ),
                top=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.17, "NarrowWindowBayModule": 0.1, "ServiceWallModule": 0.24, "ServiceBayModule": 0.13, "SolidWallModule": 0.14, "SolidWallBayModule": 0.1, "AccentPanelModule": 0.08, "RecessedStripModule": 0.04},
                    glazing=0.5,
                    balcony=0.04,
                    accent=0.45,
                ),
            ),
            "SERVICE_BLOCK": cls._make_profiles(
                ground=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"ServiceWallModule": 0.28, "ServiceBayModule": 0.17, "SolidWallModule": 0.2, "SolidWallBayModule": 0.14, "StandardWindowModule": 0.14, "NarrowWindowBayModule": 0.04, "AccentPanelModule": 0.03},
                    glazing=0.46,
                    balcony=0.0,
                    accent=0.32,
                ),
                typical=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "StairWindowModule", "AccentPanelModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.17, "NarrowWindowBayModule": 0.1, "ServiceWallModule": 0.24, "ServiceBayModule": 0.18, "SolidWallModule": 0.12, "SolidWallBayModule": 0.1, "StairWindowModule": 0.06, "AccentPanelModule": 0.02, "RecessedStripModule": 0.01},
                    glazing=0.55,
                    balcony=0.0,
                    accent=0.3,
                ),
                top=dict(
                    allowed=("SolidWallModule", "SolidWallBayModule", "ServiceWallModule", "ServiceBayModule", "StandardWindowModule", "NarrowWindowBayModule", "AccentPanelModule", "BalconyModule", "RecessedStripModule"),
                    probs={"StandardWindowModule": 0.16, "NarrowWindowBayModule": 0.1, "ServiceWallModule": 0.21, "ServiceBayModule": 0.16, "SolidWallModule": 0.13, "SolidWallBayModule": 0.1, "AccentPanelModule": 0.08, "BalconyModule": 0.05, "RecessedStripModule": 0.01},
                    glazing=0.49,
                    balcony=0.14,
                    accent=0.54,
                ),
            ),
        }
        return presets.get(preset, presets["SCIENTIST_HOUSING"])

    @classmethod
    def _make_profiles(cls, ground: dict, typical: dict, top: dict) -> tuple[GroundFloorProfile, TypicalFloorProfile, TopFloorProfile]:
        return (
            GroundFloorProfile(
                name="Ground",
                allowed_facade_modules=tuple(ground["allowed"]),
                module_probabilities=dict(ground["probs"]),
                glazing_density=float(ground["glazing"]),
                balcony_allowance=float(ground["balcony"]),
                accent_allowance=float(ground["accent"]),
            ),
            TypicalFloorProfile(
                name="Typical",
                allowed_facade_modules=tuple(typical["allowed"]),
                module_probabilities=dict(typical["probs"]),
                glazing_density=float(typical["glazing"]),
                balcony_allowance=float(typical["balcony"]),
                accent_allowance=float(typical["accent"]),
            ),
            TopFloorProfile(
                name="Top",
                allowed_facade_modules=tuple(top["allowed"]),
                module_probabilities=dict(top["probs"]),
                glazing_density=float(top["glazing"]),
                balcony_allowance=float(top["balcony"]),
                accent_allowance=float(top["accent"]),
            ),
        )

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
            "NarrowWindowBayModule": FacadeModuleDefinition(
                id="NarrowWindowBayModule",
                category="window_narrow",
                nominal_width=tile_size,
                probability=0.22,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "WideWindowBayModule": FacadeModuleDefinition(
                id="WideWindowBayModule",
                category="window_wide",
                nominal_width=tile_size,
                probability=0.18,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "SolidWallBayModule": FacadeModuleDefinition(
                id="SolidWallBayModule",
                category="wall_solid",
                nominal_width=tile_size,
                probability=0.18,
                can_scale=True,
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
                supports_top_floor=True,
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
            "ServiceBayModule": FacadeModuleDefinition(
                id="ServiceBayModule",
                category="service_bay",
                nominal_width=tile_size,
                probability=0.11,
                can_scale=True,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "AccentPanelModule": FacadeModuleDefinition(
                id="AccentPanelModule",
                category="accent",
                nominal_width=tile_size,
                probability=0.08,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
            "RecessedStripModule": FacadeModuleDefinition(
                id="RecessedStripModule",
                category="vertical_recess",
                nominal_width=tile_size,
                probability=0.07,
                can_scale=False,
                supports_ground_floor=True,
                supports_typical_floor=True,
                supports_top_floor=True,
            ),
        }

    def _is_balcony_floor_allowed(self, floor_index: int) -> bool:
        if not self.balcony_floor_mask:
            return False
        idx = max(0, min(floor_index, len(self.balcony_floor_mask) - 1))
        return self.balcony_floor_mask[idx]

    @staticmethod
    def _balcony_floor_mask(floors: int, seed: int, density: float) -> tuple[bool, ...]:
        floors = max(1, floors)
        rng = random.Random(seed * 3571 + 19)
        mask: list[bool] = []
        for idx in range(floors):
            if idx == 0:
                mask.append(False)
                continue
            if floors == 1:
                mask.append(False)
                continue
            if idx == floors - 1:
                chance = 0.58 + density * 0.28
            else:
                chance = 0.3 + density * 0.45
            mask.append(rng.random() <= chance)
        if floors > 1 and not any(mask[1:]):
            mask[-1] = True
        return tuple(mask)

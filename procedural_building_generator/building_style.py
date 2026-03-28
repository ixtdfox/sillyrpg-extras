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
    face: str
    slot_index: int
    axis: str
    outward_sign: int
    kind: str


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

    def module_for_slot(self, profile: FloorProfile, face: str, slot_index: int, slot_count: int) -> FacadeModuleDefinition:
        axis = "x" if face in {"front", "back"} else "y"
        outward_sign = {"front": +1, "back": -1, "left": -1, "right": +1}[face]

        if face == "front" and profile.is_ground and slot_index == slot_count // 2:
            kind = "entry"
            return FacadeModuleDefinition(face=face, slot_index=slot_index, axis=axis, outward_sign=outward_sign, kind=kind)

        # Stable pseudo-random choice based on style seed and module location.
        face_idx = {"front": 0, "back": 1, "left": 2, "right": 3}[face]
        rng = random.Random(self.seed + profile.floor_index * 10007 + face_idx * 997 + slot_index * 89)

        if face == "front":
            kind = "window" if (slot_index % 2 == 0 or rng.random() < 0.55) else "solid"
        elif face == "back":
            kind = "window" if (slot_index % 2 == 1 or rng.random() < 0.35) else "solid"
        elif face == "left":
            kind = "window" if (slot_index % 2 == 0 and rng.random() < self.side_window_probability) else "solid"
        else:
            kind = "window" if (slot_index % 2 == 1 and rng.random() < self.side_window_probability) else "solid"

        return FacadeModuleDefinition(face=face, slot_index=slot_index, axis=axis, outward_sign=outward_sign, kind=kind)

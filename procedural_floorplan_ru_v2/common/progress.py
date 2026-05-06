from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GenerationProgress:
    """Blocking-operator progress helper for Blender generation tasks."""

    wm: object | None
    total: int
    current: int = 0
    label: str = ""
    operator: object | None = None
    props: object | None = None

    def begin(self, label: str = "", report: bool = False) -> None:
        self.current = 0
        self.label = ""
        if self.wm is not None:
            try:
                self.wm.progress_begin(0, max(1, int(self.total)))
            except Exception:
                pass
        self.update(0, label=label, report=report)

    def step(self, label: str = "", amount: int = 1, report: bool = False) -> None:
        self.update(self.current + amount, label=label, report=report)

    def update(self, value: int | float, label: str = "", report: bool = False) -> None:
        total = max(1, int(self.total))
        clamped = max(0, min(total, int(round(float(value)))))
        label = str(label or self.label)
        label_changed = bool(label) and label != self.label
        self.current = clamped
        self.label = label

        if self.wm is not None:
            try:
                self.wm.progress_update(clamped)
            except Exception:
                pass

        if self.props is not None:
            try:
                self.props.terrain_generation_progress = (float(clamped) / float(total)) * 100.0
                if label:
                    self.props.terrain_generation_status = label
            except Exception:
                pass

        if label_changed:
            print(f"[TerrainProgress] {label}")
        if report and label and self.operator is not None:
            try:
                self.operator.report({"INFO"}, label)
            except Exception:
                pass

    def end(self, label: str = "") -> None:
        if label:
            self.update(self.total, label=label, report=False)
        if self.wm is not None:
            try:
                self.wm.progress_end()
            except Exception:
                pass

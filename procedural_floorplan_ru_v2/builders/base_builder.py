from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBuilder(ABC):
    builder_id = "base"

    def enabled(self, context) -> bool:
        return True

    @abstractmethod
    def build(self, context) -> list:
        raise NotImplementedError

"""Simple batching helper for generated objects."""

from __future__ import annotations


class BuildBatch:
    def __init__(self):
        self.objects = []

    def add(self, obj):
        self.objects.append(obj)

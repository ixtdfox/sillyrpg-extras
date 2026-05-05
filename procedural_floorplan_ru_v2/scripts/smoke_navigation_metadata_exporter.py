from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "metadata" / "navigation_metadata_exporter.py"


def main() -> None:
    tree = ast.parse(EXPORTER.read_text(encoding="utf-8"), filename=str(EXPORTER))
    exporter_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NavigationMetadataExporter"
    )
    methods = {
        node.name
        for node in exporter_class.body
        if isinstance(node, ast.FunctionDef)
    }
    missing = {"_collect_stair_links", "_map_stair_link"} - methods
    assert not missing, f"NavigationMetadataExporter missing methods: {sorted(missing)}"


if __name__ == "__main__":
    main()

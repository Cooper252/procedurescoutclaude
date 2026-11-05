"""Floats must never carry money. Fails if `float` appears in core or ingest code."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKED = [ROOT / "packages" / "core", ROOT / "packages" / "ingest"]
# The parsers mention "float" only in error-message strings, which ast ignores.


def test_no_float_in_money_code() -> None:
    offenders: list[str] = []
    for base in CHECKED:
        for path in base.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if isinstance(node, ast.Name) and node.id == "float":
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
                if isinstance(node, ast.Constant) and type(node.value) is float:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} (float literal)")
    assert offenders == []

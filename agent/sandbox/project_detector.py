"""Detect supported repository runtimes and their validation commands."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ProjectPlan:
    language: str
    install_command: tuple[str, ...] | None
    lint_command: tuple[str, ...] | None
    test_command: tuple[str, ...] | None


def detect_project(root: Path) -> ProjectPlan:
    """Return a conservative validation plan for a cloned repository."""
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        manager = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            manager = "pnpm"
        elif (root / "yarn.lock").is_file():
            manager = "yarn"
        install = (manager, "install", "--frozen-lockfile") if manager != "npm" else (
            "npm",
            "ci" if (root / "package-lock.json").is_file() else "install",
        )
        return ProjectPlan(
            language="javascript",
            install_command=install,
            lint_command=(manager, "run", "lint") if "lint" in scripts else None,
            # Prefer: test → typecheck → build (in that order) as the validation command
            test_command=(
                (manager, "test") if "test" in scripts
                else (manager, "run", "typecheck") if "typecheck" in scripts
                else (manager, "run", "build") if "build" in scripts
                else None
            ),
        )

    return ProjectPlan(
        language="python",
        install_command=None,
        lint_command=None,
        test_command=None,
    )

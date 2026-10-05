"""A throwaway git repo per incident, so the sandbox's git step never touches the phoenix clone."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "*.pyc", ".venv", "venv", ".pytest_cache", ".phoenix", "node_modules"
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def create_workspace(project_dir: Path, root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    suffix = 2
    while target.exists():
        target = root / f"{name}-{suffix}"
        suffix += 1
    shutil.copytree(project_dir, target, ignore=IGNORE)
    _git(target, "init", "-b", "main")
    _git(target, "config", "user.name", "Phoenix")
    _git(target, "config", "user.email", "phoenix@localhost")
    _git(target, "config", "commit.gpgsign", "false")
    _git(target, "add", "-A")
    _git(target, "commit", "-m", "Baseline copy of the failing project")
    return target

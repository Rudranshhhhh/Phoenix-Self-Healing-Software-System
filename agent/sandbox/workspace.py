"""
Phoenix Sandbox — Workspace Manager

Creates and manages isolated temporary copies of the repository for each
incident. The production repository is NEVER modified.

Architecture
------------
Each incident gets its own directory under <sandbox_base>/phoenix/<incident_id>/
containing a full copy of the target repository tree.

    /tmp/phoenix/INC-007/
        sample-app/          ← copy of the repo's sample-app/
        backend/             ← copy of backend/ if needed
        ...

Cleanup is guaranteed via context manager — even if validation raises.

Security
--------
- Only the temporary directory is ever written to.
- os.path.realpath + a containment check prevents symlink-based path traversal.
- Secrets (.env, *.key, *.pem) are never copied into the sandbox.
"""
from __future__ import annotations

import logging
import os
import pathlib
import shutil
import tempfile
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# Patterns excluded when copying the repo into the sandbox.
# This prevents secrets, caches, and Docker artifacts from entering the sandbox.
_EXCLUDE_PATTERNS = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "*.p12",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "dist-ssr",
    "*.local",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "ci-reports",
)


class SandboxWorkspace:
    """
    Manages a temporary isolated copy of the repository for one incident.

    Usage (preferred — guarantees cleanup):
        with SandboxWorkspace.create(repo_root, incident_id, base_dir) as ws:
            patched_file = ws.sandbox_path / "sample-app" / "app.py"
            ...

    Or manually:
        ws = SandboxWorkspace.create_manual(repo_root, incident_id, base_dir)
        try:
            ...
        finally:
            ws.cleanup()
    """

    def __init__(self, sandbox_root: pathlib.Path, repo_root: pathlib.Path) -> None:
        self._sandbox_root = sandbox_root
        self._repo_root = repo_root
        self._cleaned = False

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def sandbox_path(self) -> pathlib.Path:
        """Root of the isolated copy (e.g. /tmp/phoenix/INC-007/)."""
        return self._sandbox_root

    @property
    def repo_root(self) -> pathlib.Path:
        """Path of the original, unmodified repository."""
        return self._repo_root

    # ------------------------------------------------------------------ #
    # Factory methods                                                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(
        cls,
        repo_root: str | pathlib.Path,
        incident_id: str,
        base_dir: str = "",
    ) -> "SandboxWorkspace":
        """
        Create a new temporary workspace by copying the repository.

        Args:
            repo_root:   Absolute path to the repository root to copy.
            incident_id: The incident identifier (used to name the directory).
            base_dir:    Base directory for sandboxes. Empty = OS tmp / phoenix.

        Returns:
            SandboxWorkspace instance ready for use.

        Raises:
            FileNotFoundError: When repo_root does not exist.
            ValueError:        When incident_id is empty.
            OSError:           When the copy fails (permissions, disk full, etc.)
        """
        repo_root = pathlib.Path(repo_root).resolve()
        if not repo_root.exists():
            raise FileNotFoundError(
                f"SandboxWorkspace: repo_root does not exist: {repo_root}"
            )
        if not incident_id.strip():
            raise ValueError("SandboxWorkspace: incident_id must not be empty")

        # Determine base directory
        if base_dir:
            parent = pathlib.Path(base_dir) / "phoenix"
        else:
            parent = pathlib.Path(tempfile.gettempdir()) / "phoenix"

        parent.mkdir(parents=True, exist_ok=True)

        # Each incident gets its own subdirectory.
        # Use mkdtemp to guarantee uniqueness even for repeated runs.
        sandbox_root = pathlib.Path(
            tempfile.mkdtemp(prefix=f"{incident_id}_", dir=str(parent))
        )

        logger.info(
            "SandboxWorkspace: creating sandbox for %s at %s (source: %s)",
            incident_id,
            sandbox_root,
            repo_root,
        )

        # Copy the repository into the sandbox root.
        # We copy contents so sandbox_root itself becomes the repo root.
        _copy_repo(repo_root, sandbox_root)

        logger.info(
            "SandboxWorkspace: sandbox ready (%s)",
            sandbox_root,
        )
        return cls(sandbox_root=sandbox_root, repo_root=repo_root)

    # ------------------------------------------------------------------ #
    # Resolve a path safely inside the sandbox                            #
    # ------------------------------------------------------------------ #

    def resolve_path(self, relative: str) -> pathlib.Path:
        """
        Resolve a relative file path to an absolute path inside the sandbox.

        Raises ValueError if the resolved path escapes the sandbox root
        (path traversal prevention).

        Args:
            relative: A relative path such as "backend/services/incident_service.py"

        Returns:
            Absolute Path inside the sandbox.
        """
        # Reject obvious traversal attempts early
        if ".." in pathlib.PurePosixPath(relative).parts:
            raise ValueError(
                f"SandboxWorkspace: path traversal detected in {relative!r}"
            )

        resolved = (self._sandbox_root / relative).resolve()

        # Strict containment check after symlink resolution
        try:
            resolved.relative_to(self._sandbox_root.resolve())
        except ValueError:
            raise ValueError(
                f"SandboxWorkspace: path {relative!r} escapes sandbox root — rejected"
            )

        return resolved

    # ------------------------------------------------------------------ #
    # Cleanup                                                              #
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """
        Remove the temporary sandbox directory.

        Safe to call multiple times — subsequent calls are no-ops.
        Logs a warning if cleanup fails but does not raise.
        """
        if self._cleaned:
            return
        self._cleaned = True
        try:
            shutil.rmtree(self._sandbox_root, ignore_errors=True)
            logger.info(
                "SandboxWorkspace: cleaned up sandbox at %s",
                self._sandbox_root,
            )
        except Exception as exc:
            logger.warning(
                "SandboxWorkspace: cleanup failed for %s — %s",
                self._sandbox_root,
                exc,
            )

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "SandboxWorkspace":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    def __repr__(self) -> str:
        return (
            f"SandboxWorkspace(sandbox={self._sandbox_root}, "
            f"repo={self._repo_root}, cleaned={self._cleaned})"
        )


# ============================================================================ #
# Context-manager factory (convenience wrapper)                                  #
# ============================================================================ #

@contextmanager
def sandbox_workspace(
    repo_root: str | pathlib.Path,
    incident_id: str,
    base_dir: str = "",
) -> Generator[SandboxWorkspace, None, None]:
    """
    Context manager that creates a SandboxWorkspace and always cleans up.

    Example:
        with sandbox_workspace("/path/to/repo", "INC-007") as ws:
            target = ws.resolve_path("sample-app/app.py")
            ...
        # sandbox is deleted here regardless of success/failure
    """
    ws = SandboxWorkspace.create(
        repo_root=repo_root,
        incident_id=incident_id,
        base_dir=base_dir,
    )
    try:
        yield ws
    finally:
        ws.cleanup()


# ============================================================================ #
# Internal helpers                                                               #
# ============================================================================ #

def _copy_repo(src: pathlib.Path, dest: pathlib.Path) -> None:
    """
    Copy src directory contents into dest.

    Copies each top-level item from src into dest so that dest itself
    becomes the repository root (not dest/src_name/).

    Applies _EXCLUDE_PATTERNS to skip secrets, caches, and virtualenvs.
    Also skips any item whose resolved path is an ancestor of, equal to,
    or descendant of dest — preventing recursive self-copy when the sandbox
    directory is located inside the source tree.
    """
    dest_resolved = dest.resolve()
    copied = 0
    for item in src.iterdir():
        src_item = src / item.name
        dest_item = dest / item.name

        if _should_exclude(item.name):
            logger.debug("SandboxWorkspace: excluding %s", item.name)
            continue

        # Guard: skip if copying src_item would include dest itself
        # (prevents recursive self-copy when sandbox is inside repo)
        try:
            src_item_resolved = src_item.resolve()
            if (
                src_item_resolved == dest_resolved
                or dest_resolved.is_relative_to(src_item_resolved)
                or src_item_resolved.is_relative_to(dest_resolved)
            ):
                logger.debug(
                    "SandboxWorkspace: skipping %s — overlaps with sandbox destination",
                    item.name,
                )
                continue
        except (OSError, ValueError):
            pass

        if src_item.is_dir():
            shutil.copytree(
                src_item,
                dest_item,
                ignore=_EXCLUDE_PATTERNS,
                symlinks=False,
            )
        else:
            shutil.copy2(src_item, dest_item)
        copied += 1

    logger.debug("SandboxWorkspace: copied %d top-level items into sandbox", copied)


def _should_exclude(name: str) -> bool:
    """Return True if the top-level item should be excluded from the sandbox."""
    _EXCLUDED_TOP = {
        ".git",
        ".env",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "dist",
        "htmlcov",
        "ci-reports",
        "__pycache__",
    }
    if name in _EXCLUDED_TOP:
        return True
    # Exclude .env.* variants (but keep .env.example for reference)
    if name.startswith(".env.") and name != ".env.example":
        return True
    # Exclude credential file extensions
    if any(name.endswith(ext) for ext in (".key", ".pem", ".p12", ".pfx")):
        return True
    return False

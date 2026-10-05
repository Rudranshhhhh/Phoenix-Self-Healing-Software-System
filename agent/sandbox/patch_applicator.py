"""
Phoenix Sandbox — Patch Applicator

Takes a PatchResult (list of FilePatch objects produced by the LLM engine)
and applies it to the isolated sandbox copy of the repository.

Safety guarantees
-----------------
1. Files are only modified inside the SandboxWorkspace, never in the
   original repository.
2. Path traversal is rejected via SandboxWorkspace.resolve_path().
3. Files that do not exist inside the sandbox are rejected.
4. Each old_code must appear EXACTLY ONCE in the target file.
   A zero-match means the LLM hallucinated or targeted the wrong file.
   A multi-match means the replacement is ambiguous — both are rejected.
5. old_code and new_code must not be identical (no-op patch is rejected).
6. All patches in a PatchResult are applied atomically — if any single
   FilePatch fails, ALL already-applied patches are rolled back and the
   sandbox is left in its original state.

The applicator never touches the production repository.
"""
from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import Optional

from agent.ai.llm_engine.patch import FilePatch, PatchResult
from agent.sandbox.workspace import SandboxWorkspace

logger = logging.getLogger(__name__)


# ============================================================================ #
# Result type                                                                    #
# ============================================================================ #

@dataclass
class ApplicationResult:
    """Result of applying a PatchResult to the sandbox."""

    success: bool
    applied_files: list[str] = field(default_factory=list)
    failed_file: Optional[str] = None
    error: Optional[str] = None


# ============================================================================ #
# Main function                                                                  #
# ============================================================================ #

def apply_patch(
    patch: PatchResult,
    workspace: SandboxWorkspace,
) -> ApplicationResult:
    """
    Apply all FilePatch objects from a PatchResult to the sandbox workspace.

    Atomic: if any patch fails, ALL previously-applied patches are rolled
    back and the sandbox is returned to its pre-application state.

    Args:
        patch:     The PatchResult from LLMEngine (must not be empty).
        workspace: The SandboxWorkspace that owns the sandbox directory.

    Returns:
        ApplicationResult describing success or failure.
    """
    if patch.is_empty or not patch.patches:
        return ApplicationResult(
            success=False,
            error="PatchResult is empty — nothing to apply.",
        )

    # Keep snapshots for rollback
    originals: dict[str, str] = {}
    applied: list[str] = []

    for fp in patch.patches:
        result = _apply_single(fp, workspace, originals)
        if not result.success:
            # Roll back everything already applied
            _rollback(originals, applied, workspace)
            return ApplicationResult(
                success=False,
                applied_files=applied,
                failed_file=fp.file,
                error=result.error,
            )
        applied.append(fp.file)

    logger.info(
        "PatchApplicator: applied %d patch(es) — %s",
        len(applied),
        ", ".join(applied),
    )
    return ApplicationResult(success=True, applied_files=applied)


# ============================================================================ #
# Internal helpers                                                               #
# ============================================================================ #

def _apply_single(
    fp: FilePatch,
    workspace: SandboxWorkspace,
    originals: dict[str, str],
) -> ApplicationResult:
    """
    Apply one FilePatch to the sandbox.

    Saves the original content in `originals` before modification to enable
    rollback by the caller.
    """
    # ------------------------------------------------------------------ #
    # 1. Normalise the target path and perform containment check          #
    # ------------------------------------------------------------------ #
    try:
        target: pathlib.Path = workspace.resolve_path(fp.file)
    except ValueError as exc:
        return ApplicationResult(
            success=False,
            error=f"Path traversal rejected for {fp.file!r}: {exc}",
        )

    # ------------------------------------------------------------------ #
    # 2. File must exist                                                   #
    # ------------------------------------------------------------------ #
    if not target.exists():
        return ApplicationResult(
            success=False,
            error=f"Target file does not exist in sandbox: {fp.file!r}",
        )

    if not target.is_file():
        return ApplicationResult(
            success=False,
            error=f"Target path is not a file: {fp.file!r}",
        )

    # ------------------------------------------------------------------ #
    # 3. Read current content                                              #
    # ------------------------------------------------------------------ #
    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        return ApplicationResult(
            success=False,
            error=f"Cannot read {fp.file!r}: {exc}",
        )

    # Save for rollback before any modification
    originals[fp.file] = content

    # ------------------------------------------------------------------ #
    # 4. Validate old_code / new_code                                     #
    # ------------------------------------------------------------------ #
    old = fp.old_code
    new = fp.new_code

    if not old.strip():
        return ApplicationResult(
            success=False,
            error=f"old_code is blank in patch for {fp.file!r} — rejected.",
        )

    if not new.strip():
        return ApplicationResult(
            success=False,
            error=f"new_code is blank in patch for {fp.file!r} — rejected.",
        )

    if old.strip() == new.strip():
        return ApplicationResult(
            success=False,
            error=f"old_code and new_code are identical for {fp.file!r} — no-op patch rejected.",
        )

    # ------------------------------------------------------------------ #
    # 5. Count occurrences — must be exactly 1                            #
    # ------------------------------------------------------------------ #
    occurrences = content.count(old)
    if occurrences == 0:
        return ApplicationResult(
            success=False,
            error=(
                f"old_code not found in sandbox copy of {fp.file!r}. "
                f"The file may have been patched already or the LLM targeted "
                f"the wrong snippet. old_code={old.strip()!r:.120}"
            ),
        )
    if occurrences > 1:
        return ApplicationResult(
            success=False,
            error=(
                f"old_code appears {occurrences} times in {fp.file!r} — "
                f"ambiguous replacement rejected. "
                f"old_code={old.strip()!r:.120}"
            ),
        )

    # ------------------------------------------------------------------ #
    # 6. Apply the replacement                                             #
    # ------------------------------------------------------------------ #
    patched = content.replace(old, new, 1)

    try:
        target.write_text(patched, encoding="utf-8")
    except OSError as exc:
        return ApplicationResult(
            success=False,
            error=f"Cannot write patched content to {fp.file!r}: {exc}",
        )

    logger.debug(
        "PatchApplicator: patched %s (%d chars → %d chars)",
        fp.file,
        len(content),
        len(patched),
    )
    return ApplicationResult(success=True, applied_files=[fp.file])


def _rollback(
    originals: dict[str, str],
    applied: list[str],
    workspace: SandboxWorkspace,
) -> None:
    """
    Restore all already-applied files to their original content.

    Called when one FilePatch in a multi-file PatchResult fails, to leave
    the sandbox in a consistent state.
    """
    if not applied:
        return

    logger.warning(
        "PatchApplicator: rolling back %d already-applied patch(es): %s",
        len(applied),
        applied,
    )
    for file_rel in applied:
        original_content = originals.get(file_rel)
        if original_content is None:
            logger.error(
                "PatchApplicator: no snapshot for %s — cannot roll back",
                file_rel,
            )
            continue
        try:
            target = workspace.resolve_path(file_rel)
            target.write_text(original_content, encoding="utf-8")
            logger.debug("PatchApplicator: rolled back %s", file_rel)
        except Exception as exc:
            logger.error(
                "PatchApplicator: rollback of %s failed — %s", file_rel, exc
            )

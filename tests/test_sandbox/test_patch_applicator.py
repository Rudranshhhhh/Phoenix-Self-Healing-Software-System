"""
Phoenix Sandbox Tests — Patch Applicator

Tests for agent/sandbox/patch_applicator.py.
Verifies atomic multi-file application, path traversal prevention,
rollback on failure, and all rejection conditions.

No Docker, no Git, no GitHub — pure filesystem operations.
"""
from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest

from agent.ai.llm_engine.patch import FilePatch, PatchResult
from agent.sandbox.patch_applicator import ApplicationResult, apply_patch
from agent.sandbox.workspace import SandboxWorkspace


# ============================================================================ #
# Helpers                                                                        #
# ============================================================================ #

def _make_workspace(tmp_path: pathlib.Path, files: dict[str, str]) -> SandboxWorkspace:
    """Create a minimal fake SandboxWorkspace with the given files."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    for rel, content in files.items():
        target = sandbox / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    ws = SandboxWorkspace.__new__(SandboxWorkspace)
    ws._sandbox_root = sandbox
    ws._repo_root = sandbox
    ws._cleaned = False
    return ws


def _make_patch(file: str, old: str, new: str) -> PatchResult:
    return PatchResult(
        patches=[FilePatch(file=file, old_code=old, new_code=new)],
        explanation="test patch",
    )


def _make_multi_patch(*triples) -> PatchResult:
    patches = [FilePatch(file=f, old_code=o, new_code=n) for f, o, n in triples]
    return PatchResult(patches=patches, explanation="multi-file test patch")


# ============================================================================ #
# Single-file patch success                                                      #
# ============================================================================ #

class TestApplyPatchSuccess:
    def test_applies_single_file_patch(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1 + 2\n"})
        patch = _make_patch("app.py", "x = 1 + 2", "x = 1 + 3")
        result = apply_patch(patch, ws)
        assert result.success is True
        assert "app.py" in result.applied_files
        assert (ws.sandbox_path / "app.py").read_text() == "x = 1 + 3\n"

    def test_applied_files_listed(self, tmp_path):
        ws = _make_workspace(tmp_path, {"svc.py": "total = count()\n"})
        patch = _make_patch("svc.py", "total = count()", "total = count(severity=s)")
        result = apply_patch(patch, ws)
        assert result.applied_files == ["svc.py"]

    def test_multi_file_patch_applies_all(self, tmp_path):
        ws = _make_workspace(tmp_path, {
            "service.py": "total = repo.count()\n",
            "repo.py": "def count():\n    pass\n",
        })
        patch = _make_multi_patch(
            ("service.py", "total = repo.count()", "total = repo.count(sev=s)"),
            ("repo.py", "def count():", "def count(sev=None):"),
        )
        result = apply_patch(patch, ws)
        assert result.success is True
        assert len(result.applied_files) == 2
        assert "service.py" in result.applied_files
        assert "repo.py" in result.applied_files

    def test_original_repo_not_modified(self, tmp_path):
        """The workspace._repo_root is a different path — verify it is untouched."""
        original_dir = tmp_path / "original"
        original_dir.mkdir()
        (original_dir / "app.py").write_text("x = 1 + 2\n")

        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        (sandbox_dir / "app.py").write_text("x = 1 + 2\n")

        ws = SandboxWorkspace.__new__(SandboxWorkspace)
        ws._sandbox_root = sandbox_dir
        ws._repo_root = original_dir
        ws._cleaned = False

        patch = _make_patch("app.py", "x = 1 + 2", "x = 99")
        apply_patch(patch, ws)

        # Original untouched
        assert (original_dir / "app.py").read_text() == "x = 1 + 2\n"
        # Sandbox changed
        assert (sandbox_dir / "app.py").read_text() == "x = 99\n"


# ============================================================================ #
# Rejection conditions                                                           #
# ============================================================================ #

class TestApplyPatchRejected:
    def test_empty_patch_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\n"})
        empty_patch = PatchResult(patches=[], explanation="no fix")
        result = apply_patch(empty_patch, ws)
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_file_not_found_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"other.py": "x = 1\n"})
        patch = _make_patch("missing.py", "old", "new")
        result = apply_patch(patch, ws)
        assert result.success is False
        assert result.failed_file == "missing.py"
        assert "does not exist" in result.error

    def test_old_code_not_found_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\n"})
        patch = _make_patch("app.py", "x = 999 + totally_wrong", "x = 0")
        result = apply_patch(patch, ws)
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_old_code_duplicate_rejected(self, tmp_path):
        # If old_code appears twice, replacement is ambiguous — reject
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\nx = 1\n"})
        patch = _make_patch("app.py", "x = 1", "x = 2")
        result = apply_patch(patch, ws)
        assert result.success is False
        assert "2 times" in result.error or "ambiguous" in result.error.lower()

    def test_noop_patch_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\n"})
        patch = _make_patch("app.py", "x = 1", "x = 1")  # identical
        result = apply_patch(patch, ws)
        assert result.success is False
        assert "identical" in result.error.lower() or "no-op" in result.error.lower()

    def test_path_traversal_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\n"})
        patch = _make_patch("../../etc/passwd", "root", "hacked")
        result = apply_patch(patch, ws)
        assert result.success is False
        assert result.failed_file == "../../etc/passwd"

    def test_whitespace_only_old_code_rejected(self, tmp_path):
        ws = _make_workspace(tmp_path, {"app.py": "x = 1\n"})
        fp = FilePatch(file="app.py", old_code="   ", new_code="x = 2")
        patch = PatchResult(patches=[fp], explanation="blank old")
        result = apply_patch(patch, ws)
        assert result.success is False
        assert "blank" in result.error.lower() or "old_code is blank" in result.error


# ============================================================================ #
# Atomicity / rollback                                                           #
# ============================================================================ #

class TestApplyPatchRollback:
    def test_rollback_on_second_file_failure(self, tmp_path):
        """
        Multi-file patch: first file applies fine, second fails.
        First file must be rolled back to its original content.
        """
        ws = _make_workspace(tmp_path, {
            "service.py": "total = repo.count()\n",
            "repo.py": "def count():\n    pass\n",
        })
        patch = _make_multi_patch(
            ("service.py", "total = repo.count()", "total = repo.count(sev=s)"),
            ("repo.py", "DOES_NOT_EXIST_IN_FILE", "new code"),  # will fail
        )
        result = apply_patch(patch, ws)
        assert result.success is False
        assert result.failed_file == "repo.py"
        # service.py must be rolled back to original
        assert (ws.sandbox_path / "service.py").read_text() == "total = repo.count()\n"

    def test_no_partial_state_after_failure(self, tmp_path):
        """Three-file patch: fails on file 3, files 1+2 must be restored."""
        ws = _make_workspace(tmp_path, {
            "a.py": "a = 1\n",
            "b.py": "b = 2\n",
            "c.py": "c = 3\n",
        })
        patch = _make_multi_patch(
            ("a.py", "a = 1", "a = 100"),
            ("b.py", "b = 2", "b = 200"),
            ("c.py", "MISSING_CODE", "c = 300"),
        )
        result = apply_patch(patch, ws)
        assert result.success is False
        assert (ws.sandbox_path / "a.py").read_text() == "a = 1\n"
        assert (ws.sandbox_path / "b.py").read_text() == "b = 2\n"
        assert (ws.sandbox_path / "c.py").read_text() == "c = 3\n"

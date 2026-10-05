"""
Phoenix Sandbox Tests — Workspace Manager

Tests for agent/sandbox/workspace.py.
All tests use real filesystem operations in a temp directory.
No Docker, no Git, no GitHub API calls.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from agent.sandbox.workspace import SandboxWorkspace, sandbox_workspace, _should_exclude


# ============================================================================ #
# Helpers                                                                        #
# ============================================================================ #

def _separate_base() -> pathlib.Path:
    """
    Return an OS-level temp directory that is guaranteed to be OUTSIDE
    any pytest tmp_path tree.  Using tmp_path as both the repo root AND
    the sandbox_base would place the sandbox inside the source tree,
    triggering recursive-copy protection.
    """
    d = pathlib.Path(tempfile.mkdtemp(prefix="phoenix_ws_test_"))
    return d


# ============================================================================ #
# Fixtures                                                                       #
# ============================================================================ #

@pytest.fixture()
def simple_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal fake repository structure."""
    (tmp_path / "sample-app").mkdir()
    (tmp_path / "sample-app" / "app.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "sample-app" / "requirements.txt").write_text("flask==3.0.3", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "service.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=abc123", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc", encoding="utf-8")
    return tmp_path


# ============================================================================ #
# SandboxWorkspace.create                                                        #
# ============================================================================ #

class TestSandboxWorkspaceCreate:
    def test_creates_sandbox_directory(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-001", base_dir=str(base))
        try:
            assert ws.sandbox_path.exists()
            assert ws.sandbox_path.is_dir()
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_copies_repo_contents(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-002", base_dir=str(base))
        try:
            assert (ws.sandbox_path / "sample-app" / "app.py").exists()
            assert (ws.sandbox_path / "backend" / "service.py").exists()
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_excludes_dotenv_secrets(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-003", base_dir=str(base))
        try:
            # .env must never appear in the sandbox
            assert not (ws.sandbox_path / ".env").exists()
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_repo_root_unchanged(self, simple_repo):
        """The original repository must not be modified in any way."""
        original_content = (simple_repo / "sample-app" / "app.py").read_text()
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-004", base_dir=str(base))
        try:
            # Mutate the sandbox copy
            (ws.sandbox_path / "sample-app" / "app.py").write_text("CHANGED")
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)
        # Original must be untouched
        assert (simple_repo / "sample-app" / "app.py").read_text() == original_content

    def test_raises_on_missing_repo_root(self):
        with pytest.raises(FileNotFoundError):
            SandboxWorkspace.create("/nonexistent/path/xyz", "INC-005")

    def test_raises_on_empty_incident_id(self, simple_repo):
        with pytest.raises(ValueError, match="incident_id must not be empty"):
            SandboxWorkspace.create(simple_repo, "   ")

    def test_sandbox_path_contains_incident_id(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-TEST", base_dir=str(base))
        try:
            assert "INC-TEST" in str(ws.sandbox_path)
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_unique_sandbox_per_incident(self, simple_repo):
        base = _separate_base()
        ws1 = SandboxWorkspace.create(simple_repo, "INC-A", base_dir=str(base))
        ws2 = SandboxWorkspace.create(simple_repo, "INC-A", base_dir=str(base))
        try:
            assert ws1.sandbox_path != ws2.sandbox_path
        finally:
            ws1.cleanup()
            ws2.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)


# ============================================================================ #
# SandboxWorkspace.resolve_path                                                  #
# ============================================================================ #

class TestResolvePath:
    def test_resolves_valid_relative_path(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-R1", base_dir=str(base))
        try:
            resolved = ws.resolve_path("sample-app/app.py")
            assert resolved.exists()
            assert resolved.is_absolute()
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_rejects_parent_traversal(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-R2", base_dir=str(base))
        try:
            with pytest.raises(ValueError, match="traversal"):
                ws.resolve_path("../../etc/passwd")
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_rejects_dotdot_in_path(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-R3", base_dir=str(base))
        try:
            with pytest.raises(ValueError):
                ws.resolve_path("sample-app/../../../secret")
        finally:
            ws.cleanup()
            import shutil; shutil.rmtree(base, ignore_errors=True)


# ============================================================================ #
# SandboxWorkspace.cleanup                                                       #
# ============================================================================ #

class TestCleanup:
    def test_cleanup_removes_directory(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-C1", base_dir=str(base))
        sandbox_dir = ws.sandbox_path
        ws.cleanup()
        import shutil; shutil.rmtree(base, ignore_errors=True)
        assert not sandbox_dir.exists()

    def test_cleanup_is_idempotent(self, simple_repo):
        base = _separate_base()
        ws = SandboxWorkspace.create(simple_repo, "INC-C2", base_dir=str(base))
        ws.cleanup()
        ws.cleanup()  # second call must not raise
        import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_context_manager_cleans_up_on_success(self, simple_repo):
        base = _separate_base()
        with SandboxWorkspace.create(simple_repo, "INC-CM1", base_dir=str(base)) as ws:
            sandbox_dir = ws.sandbox_path
            assert sandbox_dir.exists()
        import shutil; shutil.rmtree(base, ignore_errors=True)
        assert not sandbox_dir.exists()

    def test_context_manager_cleans_up_on_exception(self, simple_repo):
        base = _separate_base()
        sandbox_dir = None
        with pytest.raises(RuntimeError):
            with SandboxWorkspace.create(
                simple_repo, "INC-CM2", base_dir=str(base)
            ) as ws:
                sandbox_dir = ws.sandbox_path
                raise RuntimeError("simulated failure")
        import shutil; shutil.rmtree(base, ignore_errors=True)
        assert sandbox_dir is not None
        assert not sandbox_dir.exists()


# ============================================================================ #
# sandbox_workspace context manager                                              #
# ============================================================================ #

class TestSandboxWorkspaceContextManager:
    def test_yields_workspace(self, simple_repo):
        base = _separate_base()
        with sandbox_workspace(simple_repo, "INC-CTX1", base_dir=str(base)) as ws:
            assert isinstance(ws, SandboxWorkspace)
            assert (ws.sandbox_path / "sample-app" / "app.py").exists()
        import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_cleans_up_after_yield(self, simple_repo):
        base = _separate_base()
        with sandbox_workspace(simple_repo, "INC-CTX2", base_dir=str(base)) as ws:
            p = ws.sandbox_path
        import shutil; shutil.rmtree(base, ignore_errors=True)
        assert not p.exists()


# ============================================================================ #
# _should_exclude helper                                                         #
# ============================================================================ #

class TestShouldExclude:
    def test_excludes_git(self):
        assert _should_exclude(".git") is True

    def test_excludes_dotenv(self):
        assert _should_exclude(".env") is True

    def test_excludes_dotenv_variants(self):
        assert _should_exclude(".env.production") is True
        assert _should_exclude(".env.local") is True

    def test_keeps_dotenv_example(self):
        assert _should_exclude(".env.example") is False

    def test_excludes_key_files(self):
        assert _should_exclude("private.key") is True
        assert _should_exclude("cert.pem") is True

    def test_keeps_normal_files(self):
        assert _should_exclude("app.py") is False
        assert _should_exclude("requirements.txt") is False
        assert _should_exclude("Dockerfile") is False

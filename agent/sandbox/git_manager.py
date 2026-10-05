"""
Phoenix Sandbox — Git Manager

After successful validation, applies the validated patch to the REAL
repository (not the sandbox), creates a branch, commits, and pushes.

Branch naming convention
------------------------
    phoenix/fix/<INCIDENT_ID>

Examples:
    INC-001  →  phoenix/fix/INC-001
    INC-007  →  phoenix/fix/INC-007
    abc-123  →  phoenix/fix/abc-123

Design principles
-----------------
- NEVER modifies main/master directly.
- Branch is always created from the current HEAD of the base branch.
- Only the specific patched files are staged — unrelated changes are not committed.
- No .env, secrets, or temporary files are ever staged.
- Uses gitpython for reliable cross-platform Git operations.
- Falls back gracefully if the repository is not a Git repo or has no remote.

Security
--------
- Git credentials come from the environment (GIT_USERNAME / GIT_TOKEN) or
  from the system's existing credential helper — never hardcoded.
- The remote URL with embedded credentials is only used transiently for
  the push operation and is not persisted in the repo config.
"""
from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from agent.sandbox.models import GitResult
from agent.ai.llm_engine.patch import PatchResult

logger = logging.getLogger(__name__)

# Files that must never be staged regardless of what the patch targets
_NEVER_STAGE = {
    ".env",
    ".env.local",
    ".env.production",
    "*.key",
    "*.pem",
    "*.p12",
}


def create_branch_and_commit(
    repo_path: str | pathlib.Path,
    incident_id: str,
    patch: PatchResult,
    base_branch: str = "main",
    git_username: str = "",
    git_token: str = "",
    remote_name: str = "origin",
) -> GitResult:
    """
    Create a fix branch, apply the validated patch, commit, and push.

    This operates on the REAL repository (after validation has already
    succeeded in the sandbox). The repo is checked out locally.

    Args:
        repo_path:    Absolute path to the local Git repository root.
        incident_id:  Incident identifier, e.g. "INC-007".
        patch:        The validated PatchResult to apply and commit.
        base_branch:  The branch to base the fix branch on (default: "main").
        git_username: Git username for push auth (reads GIT_USERNAME env var
                      if empty).
        git_token:    Personal access token / password for push auth (reads
                      GITHUB_TOKEN env var if empty).
        remote_name:  The git remote to push to (default: "origin").

    Returns:
        GitResult describing the outcome.
    """
    try:
        import git as gitpython
    except ImportError:
        return GitResult(
            success=False,
            error=(
                "gitpython is not installed. "
                "Run: pip install gitpython==3.1.43"
            ),
        )

    repo_path = pathlib.Path(repo_path).resolve()
    branch_name = _branch_name(incident_id)

    try:
        repo = gitpython.Repo(str(repo_path), search_parent_directories=True)
    except gitpython.exc.InvalidGitRepositoryError:
        return GitResult(
            success=False,
            error=f"Not a Git repository: {repo_path}",
        )

    try:
        # ------------------------------------------------------------------ #
        # 1. Ensure we are on the base branch and it is up-to-date           #
        # ------------------------------------------------------------------ #
        _checkout_base(repo, base_branch)

        # ------------------------------------------------------------------ #
        # 2. Create the fix branch                                            #
        # ------------------------------------------------------------------ #
        if branch_name in [b.name for b in repo.branches]:
            logger.warning(
                "GitManager: branch %r already exists — deleting and recreating",
                branch_name,
            )
            repo.delete_head(branch_name, force=True)

        fix_branch = repo.create_head(branch_name)
        fix_branch.checkout()
        logger.info("GitManager: created and checked out branch %r", branch_name)

        # ------------------------------------------------------------------ #
        # 3. Apply the patch to the real repo working tree                   #
        # ------------------------------------------------------------------ #
        applied = _apply_patch_to_repo(patch, repo_path)
        if not applied:
            return GitResult(
                success=False,
                branch_name=branch_name,
                error="No files were applied — patch may have already been applied.",
            )

        # ------------------------------------------------------------------ #
        # 4. Stage only the patched files                                     #
        # ------------------------------------------------------------------ #
        safe_files = [f for f in applied if not _is_sensitive(f)]
        if not safe_files:
            return GitResult(
                success=False,
                branch_name=branch_name,
                error="All patched files were flagged as sensitive — refusing to stage.",
            )

        repo.index.add(safe_files)
        logger.info("GitManager: staged %d file(s): %s", len(safe_files), safe_files)

        # ------------------------------------------------------------------ #
        # 5. Commit                                                            #
        # ------------------------------------------------------------------ #
        commit_message = _build_commit_message(incident_id, patch)
        commit = repo.index.commit(commit_message)
        logger.info(
            "GitManager: committed %s — %r",
            commit.hexsha[:7],
            commit_message.splitlines()[0],
        )

        # ------------------------------------------------------------------ #
        # 6. Push                                                              #
        # ------------------------------------------------------------------ #
        remote_url = _get_remote_url(repo, remote_name)
        if not remote_url:
            return GitResult(
                success=True,
                branch_name=branch_name,
                commit_sha=commit.hexsha,
                commit_message=commit_message,
                remote_url="",
                error="No remote found — branch was created locally but not pushed.",
            )

        push_url = _build_push_url(remote_url, git_username, git_token)
        push_info = repo.remotes[remote_name].push(
            refspec=f"{branch_name}:{branch_name}",
            force=False,
        )

        # Check push result
        for info in push_info:
            if info.flags & info.ERROR:
                return GitResult(
                    success=False,
                    branch_name=branch_name,
                    commit_sha=commit.hexsha,
                    commit_message=commit_message,
                    error=f"Push failed: {info.summary}",
                )

        logger.info(
            "GitManager: pushed %r to %s/%s",
            branch_name,
            remote_name,
            branch_name,
        )

        return GitResult(
            success=True,
            branch_name=branch_name,
            commit_sha=commit.hexsha,
            commit_message=commit_message,
            remote_url=_strip_credentials(remote_url),
        )

    except Exception as exc:
        logger.exception("GitManager: unexpected error — %s", exc)
        # Try to get back to base branch to leave repo in a clean state
        try:
            repo.heads[base_branch].checkout()
        except Exception:
            pass
        return GitResult(
            success=False,
            branch_name=branch_name,
            error=str(exc),
        )


# ============================================================================ #
# Internal helpers                                                               #
# ============================================================================ #

def _branch_name(incident_id: str) -> str:
    """Build the canonical branch name for an incident."""
    return f"phoenix/fix/{incident_id}"


def _checkout_base(repo, base_branch: str) -> None:
    """Checkout the base branch, creating it from origin if it doesn't exist locally."""
    import git as gitpython

    if base_branch in [h.name for h in repo.heads]:
        repo.heads[base_branch].checkout()
    else:
        # Try to track the remote branch
        try:
            remote_ref = repo.remotes["origin"].refs[base_branch]
            repo.create_head(base_branch, remote_ref).set_tracking_branch(
                remote_ref
            ).checkout()
        except (IndexError, AttributeError, gitpython.exc.GitCommandError):
            logger.warning(
                "GitManager: base branch %r not found locally or on remote — "
                "using current HEAD",
                base_branch,
            )


def _apply_patch_to_repo(
    patch: PatchResult,
    repo_path: pathlib.Path,
) -> list[str]:
    """
    Apply the validated patch to the real repository working tree.

    Returns the list of relative file paths that were successfully modified.
    """
    applied = []
    for fp in patch.patches:
        # Normalise path separators
        rel = fp.file.replace("\\", "/")
        target = repo_path / rel

        if not target.exists():
            logger.error(
                "GitManager: target file %r does not exist in repo — skipping",
                rel,
            )
            continue

        content = target.read_text(encoding="utf-8")
        if fp.old_code not in content:
            logger.warning(
                "GitManager: old_code not found in %r — already patched? Skipping.",
                rel,
            )
            continue

        patched = content.replace(fp.old_code, fp.new_code, 1)
        target.write_text(patched, encoding="utf-8")
        applied.append(rel)
        logger.debug("GitManager: patched %s in real repo", rel)

    return applied


def _build_commit_message(incident_id: str, patch: PatchResult) -> str:
    """
    Build a structured commit message following conventional commits format.

    Format:
        fix(<INCIDENT_ID>): <explanation>

        Patch files: <file1>, <file2>
        Generated by: Phoenix AI
    """
    explanation = patch.explanation or f"resolve {incident_id}"
    # Truncate if LLM gave a very long explanation
    if len(explanation) > 72:
        explanation = explanation[:69] + "..."
    files = ", ".join(fp.file for fp in patch.patches)
    return (
        f"fix({incident_id}): {explanation}\n\n"
        f"Patch files: {files}\n"
        f"Generated by: Phoenix AI self-healing agent\n"
    )


def _get_remote_url(repo, remote_name: str) -> str:
    """Return the remote URL or empty string if remote not configured."""
    try:
        return repo.remotes[remote_name].url
    except (IndexError, AttributeError):
        return ""


def _build_push_url(remote_url: str, username: str, token: str) -> str:
    """
    Inject credentials into the remote URL for the push operation.

    Only modifies HTTPS URLs. SSH URLs are returned unchanged (credentials
    handled by the SSH key).

    Credentials are read from the environment if not passed directly.
    """
    username = username or os.environ.get("GIT_USERNAME", "")
    token = token or os.environ.get("GITHUB_TOKEN", "")

    if not token:
        return remote_url  # rely on system credential helper

    if remote_url.startswith("https://") and username and token:
        # Inject credentials: https://username:token@github.com/...
        without_scheme = remote_url[len("https://"):]
        # Strip any existing credentials
        if "@" in without_scheme:
            without_scheme = without_scheme.split("@", 1)[1]
        return f"https://{username}:{token}@{without_scheme}"

    return remote_url


def _strip_credentials(url: str) -> str:
    """Remove embedded credentials from a URL before logging/storing."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            host_and_path = rest.split("@", 1)[1]
            return f"{scheme}://{host_and_path}"
    return url


def _is_sensitive(file_path: str) -> bool:
    """Return True if a file should never be staged (secrets, env files)."""
    name = pathlib.Path(file_path).name
    if name.startswith(".env"):
        return True
    if any(name.endswith(ext) for ext in (".key", ".pem", ".p12", ".pfx")):
        return True
    return False

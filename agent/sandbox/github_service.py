"""
Phoenix Sandbox — GitHub Pull Request Service

Creates a Pull Request on GitHub after the patch has been validated and
the fix branch has been pushed.

This module uses the GitHub REST API via PyGithub.

If PyGithub is not installed or the GITHUB_TOKEN is not set, the function
degrades gracefully — it returns a PRResult(success=False) with a clear
error message rather than crashing the pipeline.

PR format
---------
Title:
    fix(<incident_id>): automated Phoenix fix

Body:
    ## Phoenix Automated Fix
    ...full structured body with validation table and safety notice...

The PR is always opened from:
    phoenix/fix/<incident_id>  →  main  (or configured base_branch)

The PR is NEVER auto-merged. It must be reviewed and merged by a developer.

Security
--------
- GITHUB_TOKEN is read from the environment; never hardcoded.
- The token has minimal required scope: `repo` (for private repos) or
  `public_repo` (for public repos).
- The token is never logged or embedded in the PR body.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from agent.sandbox.models import GitResult, PRResult, ValidationResult

logger = logging.getLogger(__name__)


def create_pull_request(
    git_result: GitResult,
    validation: ValidationResult,
    incident_id: str,
    repo_full_name: str,
    root_cause: str = "",
    patch_explanation: str = "",
    base_branch: str = "main",
    github_token: str = "",
) -> PRResult:
    """
    Open a GitHub Pull Request for the validated fix branch.

    Args:
        git_result:        The result of the branch+commit+push step.
        validation:        The detailed validation result (used in PR body).
        incident_id:       e.g. "INC-007"
        repo_full_name:    e.g. "myorg/my-repo" (owner/repo format).
        root_cause:        From LLM diagnosis — appears in PR body.
        patch_explanation: From LLM patch — appears in PR body.
        base_branch:       PR target branch (default: "main").
        github_token:      GitHub PAT. Reads GITHUB_TOKEN env var if empty.

    Returns:
        PRResult with success=True and the PR URL, or success=False with
        an error description.
    """
    token = github_token or os.environ.get("GITHUB_TOKEN", "")

    if not token:
        return PRResult(
            success=False,
            error=(
                "GITHUB_TOKEN is not set. "
                "Export GITHUB_TOKEN=<your-pat> to enable PR creation."
            ),
        )

    if not repo_full_name:
        return PRResult(
            success=False,
            error="repo_full_name is required (format: 'owner/repo').",
        )

    if not git_result.success or not git_result.branch_name:
        return PRResult(
            success=False,
            error="Git step did not succeed — cannot create PR without a pushed branch.",
        )

    try:
        from github import Github, GithubException
    except ImportError:
        return PRResult(
            success=False,
            error=(
                "PyGithub is not installed. "
                "Run: pip install PyGithub==2.3.0"
            ),
        )

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_full_name)

        title = _build_pr_title(incident_id)
        body = _build_pr_body(
            incident_id=incident_id,
            root_cause=root_cause,
            patch_explanation=patch_explanation,
            validation=validation,
            git_result=git_result,
        )

        pr = repo.create_pull(
            title=title,
            body=body,
            head=git_result.branch_name,
            base=base_branch,
            draft=False,
        )

        logger.info(
            "GitHubService: PR #%d created — %s",
            pr.number,
            pr.html_url,
        )

        return PRResult(
            success=True,
            pr_number=pr.number,
            pr_url=pr.html_url,
            title=title,
            base_branch=base_branch,
            head_branch=git_result.branch_name,
        )

    except Exception as exc:
        # Catch GitHub API errors, network errors, auth failures, etc.
        error_msg = _format_github_error(exc)
        logger.error("GitHubService: PR creation failed — %s", error_msg)
        return PRResult(
            success=False,
            head_branch=git_result.branch_name,
            error=error_msg,
        )


# ============================================================================ #
# PR body builder                                                                #
# ============================================================================ #

def _build_pr_title(incident_id: str) -> str:
    return f"fix({incident_id}): automated Phoenix fix"


def _build_pr_body(
    incident_id: str,
    root_cause: str,
    patch_explanation: str,
    validation: ValidationResult,
    git_result: GitResult,
) -> str:
    """
    Build the full Pull Request body in GitHub-flavoured Markdown.
    """
    rc = root_cause or "_Root cause not available._"
    explanation = patch_explanation or "_Explanation not available._"
    commit_ref = (
        f"`{git_result.commit_sha[:7]}`" if git_result.commit_sha else "_unknown_"
    )
    branch = git_result.branch_name or "_unknown_"

    validation_table = validation.to_pr_section() if validation else (
        "| Step | Result |\n| :--- | :--- |\n| Validation | ⚠️ N/A |\n"
    )

    return f"""## 🔥 Phoenix Automated Fix

> **This PR was generated automatically by the Phoenix self-healing agent.**
> **A developer MUST review and merge this PR. It will NOT be auto-merged.**

---

### 📋 Incident

| Field | Value |
| :--- | :--- |
| Incident ID | `{incident_id}` |
| Branch | `{branch}` |
| Commit | {commit_ref} |

---

### 🔍 Root Cause

{rc}

---

### 🛠 Proposed Fix

{explanation}

---

### ✅ Validation Results

The patch was tested in an **isolated Docker sandbox** before this PR was created.
No changes were made to the production repository until all checks passed.

{validation_table}

---

### 🔒 Safety

- The patch was applied to a **temporary copy** of the repository.
- It was validated inside an **isolated Docker container** — not on the Phoenix host.
- No secrets or `.env` files were committed.
- This PR targets `main` — it requires **human review** before merging.
- Phoenix does **not** auto-merge PRs.

---

> _Generated by Phoenix AI · Incident `{incident_id}`_
"""


# ============================================================================ #
# Error formatting                                                               #
# ============================================================================ #

def _format_github_error(exc: Exception) -> str:
    """Convert a GitHub API exception into a readable error string."""
    exc_type = type(exc).__name__
    # PyGithub GithubException has .status and .data
    status = getattr(exc, "status", None)
    data = getattr(exc, "data", None)

    if status and data:
        message = data.get("message", str(exc)) if isinstance(data, dict) else str(data)
        errors = data.get("errors", []) if isinstance(data, dict) else []
        if errors:
            details = "; ".join(
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in errors
            )
            return f"GitHub API {status}: {message} — {details}"
        return f"GitHub API {status}: {message}"

    return f"{exc_type}: {exc}"

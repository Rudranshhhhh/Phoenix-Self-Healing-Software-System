"""
Phoenix Future — GitHub Integration Interface Protocol

Defines structural interface agreements for communicating with Git providers.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from pathlib import Path
from agent.events.incident import Incident
from future.code_agent.interfaces.code_agent import Patch, PullRequest


@runtime_checkable
class GitHubIntegration(Protocol):
    """
    Interface contract for Git provider interactions.

    Responsibilities:
    - OAuth authentication.
    - Repository cloning to local sandboxes.
    - Pull request generation.
    """

    def authenticate(self, oauth_token: str) -> None:
        """Set credentials for git API calls."""
        ...

    def clone_repository(self, repo_url: str, dest_dir: Path) -> Path:
        """Clone a remote repository to a temporary workspace directory."""
        ...

    def create_branch(self, branch_name: str) -> None:
        """Create a new branch in the sandbox repo."""
        ...

    def apply_patch(self, patch: Patch) -> bool:
        """Apply diff content onto the target repository workspace."""
        ...

    def commit_and_push(self, commit_message: str) -> None:
        """Commit files in the sandbox workspace and push to remote origin."""
        ...

    def open_pull_request(self, incident: Incident, target_branch: str) -> PullRequest:
        """Open a pull request on the repository host referencing the incident."""
        ...

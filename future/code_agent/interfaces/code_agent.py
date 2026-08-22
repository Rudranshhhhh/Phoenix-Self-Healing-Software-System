"""
Phoenix Future — Code Agent Interface Protocol

Defines structural interface agreements for the planned Phase 3 Code Agent.
This module has zero impact on the runtime agent. It acts as an architectural guide.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class CodeAnalysis:
    """Findings from scanning a cloned repository."""
    vulnerabilities: list[str]
    suggested_fixes: list[str]
    target_files: list[Path]


@dataclass(frozen=True)
class Patch:
    """A generated code diff ready to be applied."""
    target_file: Path
    diff_content: str
    branch_name: str
    commit_message: str


@dataclass(frozen=True)
class PullRequest:
    """PR information returned from Git provider APIs."""
    pr_id: int
    url: str
    title: str


@runtime_checkable
class CodeAgent(Protocol):
    """
    Interface contract for the future AI Code Agent.

    Responsibilities:
    - Analyze cloned repositories for faults or vulnerabilities matching incidents.
    - Generate targeted codebase patch files to fix root causes permanently.
    - Initiate GitHub PR flows to allow engineers to review self-healing patch sets.
    """

    def analyze_repository(self, repo_url: str) -> CodeAnalysis:
        """Scan a repository codebase and return findings."""
        ...

    def generate_patch(self, incident_id: str, analysis: CodeAnalysis) -> Patch:
        """Create a diff payload fixing the root cause of an incident."""
        ...

    def create_pull_request(self, patch: Patch) -> PullRequest:
        """Push a patch diff branch and create a Git pull request."""
        ...

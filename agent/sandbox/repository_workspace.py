"""Temporary authenticated GitHub clones for one incident."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def cloned_repository(
    full_name: str,
    token: str,
    branch: str,
    commit: str,
) -> Iterator[pathlib.Path]:
    """Clone a repository into a unique directory and always remove it."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="phoenix-repo-"))
    askpass = root.parent / f".phoenix-askpass-{root.name}"
    if os.name == "nt":
        askpass.write_text("@echo off\r\necho %PHOENIX_GIT_TOKEN%\r\n", encoding="utf-8")
    else:
        askpass.write_text("#!/bin/sh\nprintf '%s\\n' \"$PHOENIX_GIT_TOKEN\"\n", encoding="utf-8")
        askpass.chmod(0o700)

    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "PHOENIX_GIT_TOKEN": token,
        }
    )
    url = f"https://github.com/{full_name}.git"
    try:
        subprocess.run(
            ["git", "clone", "--branch", branch, url, str(root)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        if commit and commit.lower() not in {"unknown", "latest", "none", "null"}:
            subprocess.run(
                ["git", "checkout", "--detach", commit],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        askpass.unlink(missing_ok=True)

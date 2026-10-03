"""Best-effort code provenance for the run header."""

import functools
import os
import subprocess

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@functools.lru_cache(maxsize=1)
def code_commit():
    """Return {'commit': sha|None, 'dirty': bool|None}. Never raises; unknown stays unknown."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True, timeout=5)
    try:
        sha = git("rev-parse", "HEAD")
        if sha.returncode != 0:
            return {"commit": None, "dirty": None}
        status = git("status", "--porcelain")
        return {"commit": sha.stdout.strip(), "dirty": bool(status.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}

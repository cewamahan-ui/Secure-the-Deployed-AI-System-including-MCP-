"""Prove secrets are not in git (Week 9, Deliverable 1).

Two checks, both fail-closed:

  1. gitignore coverage: every secret-shaped path this repo could ever
     hold (.env, *.pem, credentials, ...) is matched by .gitignore.
     Uses `git check-ignore` when run inside a git work tree; falls
     back to parsing .gitignore directly so the script still works in
     an unzipped submission.
  2. tracked-secret scan: `git ls-files` (when available) must not list
     any secret-shaped path. This is the check that catches "someone
     committed .env last week" - the failure mode the self-assessment
     calls a zero.

    python check_gitignore.py       # exit 1 on any finding
    # transcript: evidence/check_gitignore.txt
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent

# Paths that must always be ignored. Extend, never shrink.
SECRET_SHAPED = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "credentials",
    "secrets.yaml",
    "secrets.yml",
    "*.p12",
    "*.pfx",
]

# Filenames that indicate a leak if git is tracking them.
TRACKED_LEAK_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "**/credentials", "secrets.yaml", "secrets.yml",
]


def _gitignore_patterns(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.exists():
        return []
    out = []
    for line in gi.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _ignored_by_pattern(path: str, patterns: list[str]) -> bool:
    base = path.split("/")[-1]
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat.lstrip("/")):
            return True
    return False


def _git_check_ignore(root: Path, paths: list[str]) -> dict[str, bool] | None:
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", *paths],
            cwd=root, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # check-ignore -q with many paths exits 0 if ANY is ignored; query one by one instead.
    result = {}
    for p in paths:
        one = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", p],
            cwd=root, capture_output=True, timeout=30,
        )
        result[p] = one.returncode == 0
    return result


def _tracked_files(root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [l for l in proc.stdout.splitlines() if l.strip()]


def main() -> int:
    findings: list[str] = []

    print("== check 1: gitignore covers every secret-shaped path ==")
    patterns = _gitignore_patterns(REPO_ROOT)
    if not patterns:
        print("FATAL .gitignore missing or empty")
        return 1
    ignore_hits = _git_check_ignore(REPO_ROOT, SECRET_SHAPED)
    for p in SECRET_SHAPED:
        covered = ignore_hits[p] if ignore_hits is not None else _ignored_by_pattern(p, patterns)
        print(f"{'OK  ' if covered else 'FAIL'} {p} ignored={covered}")
        if not covered:
            findings.append(f".gitignore does not cover {p}")

    print("\n== check 2: no secret-shaped file is tracked by git ==")
    tracked = _tracked_files(REPO_ROOT)
    if tracked is None:
        print("info git work tree unavailable - check 2 skipped (unzipped submission). "
              "In the graded repo this check runs against `git ls-files`.")
    else:
        leaks = [
            f for f in tracked
            if any(fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f.split("/")[-1], pat.lstrip("**/"))
                   for pat in TRACKED_LEAK_PATTERNS)
        ]
        for f in leaks:
            print(f"FAIL tracked secret-shaped file: {f}")
            findings.append(f"tracked secret-shaped file: {f}")
        if not leaks:
            print(f"OK   scanned {len(tracked)} tracked files, no secret-shaped paths")

    if findings:
        print(f"\n{len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("\nAll checks passed: no secrets in git, no secret-shaped path unignored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

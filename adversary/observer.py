"""
adversary/observer.py

Reads the current state of the codebase and recent git changes
to feed context into the adversarial agent.
"""
import subprocess
import sys
import os

# Files the adversary monitors for changes
WATCHED_FILES = ["main.py", "state.py", "agents.py", "database.py", "generate_db.py"]

def get_recent_diff(num_commits: int = 1) -> str:
    """Returns the unified git diff for the last N commits."""
    try:
        result = subprocess.run(
            ["git", "diff", f"HEAD~{num_commits}", "HEAD", "--", *WATCHED_FILES],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return result.stdout or "(No tracked changes found in last commit)"
    except Exception as e:
        return f"(Could not read git diff: {e})"

def get_unstaged_diff() -> str:
    """Returns the diff of uncommitted changes (useful before committing)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--", *WATCHED_FILES],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--", *WATCHED_FILES],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return (result.stdout + staged.stdout) or "(No uncommitted changes detected)"
    except Exception as e:
        return f"(Could not read unstaged diff: {e})"

def run_syntax_check() -> list[str]:
    """Validates Python syntax on all watched files. Returns list of errors."""
    errors = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for file in WATCHED_FILES:
        path = os.path.join(root, file)
        if not os.path.exists(path):
            continue
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append(f"[SYNTAX ERROR] {file}: {result.stderr.strip()}")
    return errors

def summarize_codebase() -> str:
    """Returns function/class signatures from all watched files for context."""
    lines = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for file in WATCHED_FILES:
        path = os.path.join(root, file)
        if not os.path.exists(path):
            continue
        lines.append(f"\n## {file}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    lines.append(f"  {stripped}")
    return "\n".join(lines)

if __name__ == "__main__":
    print("=== Recent Diff ===")
    print(get_unstaged_diff())
    print("\n=== Syntax Check ===")
    errs = run_syntax_check()
    print("\n".join(errs) if errs else "All files passed syntax check.")
    print("\n=== Codebase Summary ===")
    print(summarize_codebase())

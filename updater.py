"""
updater.py

Code-level OTA updater. Runs on every game launch (via wwq.bat / wwq.sh)
to download updated Python source files when a new version is available.

Works for both git-clone and zip-download users.
Does NOT self-update the launcher scripts (wwq.bat/wwq.sh).
"""
import sys
import os
import urllib.request
import urllib.error
import shutil

try:
    from version import VERSION as LOCAL_VERSION
except ImportError:
    LOCAL_VERSION = "0.0.0"

REMOTE_BASE = "https://raw.githubusercontent.com/adityasricharan/wwq/master"
REMOTE_VERSION_URL = f"{REMOTE_BASE}/version.txt"

# Files that get downloaded when a new version is detected
MANAGED_FILES = [
    "main.py",
    "state.py",
    "database.py",
    "agents.py",
    "question_history.py",
    "refresh_db.py",
    "seed_bank.py",
    "updater.py",
    "version.py",
]

TIMEOUT = 5  # seconds


def _fetch_text(url: str) -> str | None:
    """Downloads a URL and returns the text content, or None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return None


def _download_file(url: str, dest: str) -> bool:
    """Downloads a URL to a local path. Returns True on success."""
    try:
        tmp = dest + ".update.tmp"
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            with open(tmp, "wb") as f:
                shutil.copyfileobj(resp, f)
        os.replace(tmp, dest)
        return True
    except Exception as e:
        if os.path.exists(dest + ".update.tmp"):
            os.remove(dest + ".update.tmp")
        return False


def _version_tuple(v: str) -> tuple:
    """Converts '2.4.1' to (2, 4, 1) for comparison."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def run_update_check():
    """
    Checks the remote version and downloads updated files if a newer version exists.
    Prints status messages. Always returns cleanly — never crashes the game.
    """
    root = os.path.dirname(os.path.abspath(__file__))

    # Fetch remote version
    remote_version_str = _fetch_text(REMOTE_VERSION_URL)
    if not remote_version_str:
        print("[UPDATE] Could not reach update server. Continuing with local version.")
        return

    remote = _version_tuple(remote_version_str)
    local = _version_tuple(LOCAL_VERSION)

    if remote <= local:
        # Already up to date — silent
        return

    print(f"[UPDATE] New version available: v{LOCAL_VERSION} → v{remote_version_str}")
    print("[UPDATE] Downloading code updates...")

    success_count = 0
    fail_count = 0
    for filename in MANAGED_FILES:
        url = f"{REMOTE_BASE}/{filename}"
        dest = os.path.join(root, filename)
        if _download_file(url, dest):
            success_count += 1
        else:
            fail_count += 1

    if fail_count == 0:
        print(f"[UPDATE] ✅ Code updated to v{remote_version_str} ({success_count} files).")
    else:
        print(f"[UPDATE] ⚠️  Partial update: {success_count} files updated, {fail_count} failed.")
        print("[UPDATE]    Some features may be out of date. Try again next launch.")


if __name__ == "__main__":
    run_update_check()

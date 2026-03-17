"""
question_history.py

Tracks the global frequency of each question asked across all game sessions.
Used by the database to implement inverse-frequency weighted sampling,
ensuring questions are distributed evenly and hot-spots are eliminated.

Storage format: question_history.json (excluded from git, per-user local state)
"""
import os
import json
import hashlib
import math
from typing import Optional

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_history.json")

# Tuning constants
RECENCY_HALF_LIFE = 7       # Sessions before a recently asked Q regains most of its weight
HARD_COOLDOWN_SESSIONS = 2  # Sessions where a question gets weight=0 after being asked
WEIGHT_FLOOR = 0.01         # Minimum weight — even very overused questions can appear occasionally


def fingerprint(question_text: str) -> str:
    """Returns a short SHA1 hex key for a question — compact, deterministic, collision-resistant."""
    return hashlib.sha1(question_text.strip()[:120].encode("utf-8")).hexdigest()[:16]


def load_history() -> dict:
    """Loads question_history.json from disk. Creates a fresh store if file doesn't exist."""
    if not os.path.exists(HISTORY_FILE):
        return {"version": 1, "total_sessions": 0, "entries": {}}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all expected keys exist (forward compat)
        data.setdefault("version", 1)
        data.setdefault("total_sessions", 0)
        data.setdefault("entries", {})
        return data
    except Exception:
        # Corrupt or missing — start fresh
        return {"version": 1, "total_sessions": 0, "entries": {}}


def save_history(history: dict):
    """Writes the history dict back to disk atomically (write-then-rename)."""
    tmp_path = HISTORY_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, separators=(",", ":"))
        os.replace(tmp_path, HISTORY_FILE)
    except Exception as e:
        print(f"[HISTORY] Warning: could not save question history: {e}")


def start_new_session(history: dict) -> int:
    """Increments the total session counter and returns the new session ID."""
    history["total_sessions"] = history.get("total_sessions", 0) + 1
    return history["total_sessions"]


def record_asked(history: dict, question_text: str):
    """Records that a question was asked in the current session."""
    key = fingerprint(question_text)
    session_id = history.get("total_sessions", 1)
    entries = history.setdefault("entries", {})

    if key not in entries:
        entries[key] = {"global_count": 0, "last_asked_session": 0, "session_history": []}

    entry = entries[key]
    entry["global_count"] = entry.get("global_count", 0) + 1
    entry["last_asked_session"] = session_id

    # Keep a sliding window of the last 10 session IDs when this question was asked
    hist = entry.get("session_history", [])
    hist.append(session_id)
    if len(hist) > 10:
        hist = hist[-10:]
    entry["session_history"] = hist


def compute_weight(entry: Optional[dict], total_sessions: int) -> float:
    """
    Computes the sampling weight for a question given its history entry.

    Returns a float in [WEIGHT_FLOOR, 1.0]:
      - 1.0  → never asked (full probability)
      - ~0.5 → asked 3 times globally
      - ~0.3 → asked 10 times globally
      - 0.0  → asked within the hard cooldown window (too recent)
    """
    if entry is None:
        return 1.0  # Never asked — max weight

    global_count = entry.get("global_count", 0)
    last_asked_session = entry.get("last_asked_session", 0)

    # Hard cooldown: weight=0 for the first HARD_COOLDOWN_SESSIONS after being asked
    sessions_since = total_sessions - last_asked_session
    if sessions_since <= HARD_COOLDOWN_SESSIONS:
        return 0.0

    # Recency factor: exponential ramp-up back to 1.0 as session distance grows
    recency = 1.0 - math.exp(-sessions_since / RECENCY_HALF_LIFE)

    # Global frequency penalty: diminishing returns as count grows
    global_penalty = 1.0 / (1.0 + math.log1p(global_count))

    weight = recency * global_penalty
    return max(WEIGHT_FLOOR, weight)


def get_weights_for_candidates(candidates: list, history: dict) -> list[float]:
    """
    Returns a parallel list of sampling weights for each candidate question.
    Used by LocalKnowledgeBank.get_question() to do weighted random selection.
    """
    total_sessions = history.get("total_sessions", 0)
    entries = history.get("entries", {})
    weights = []
    for q in candidates:
        key = fingerprint(q.question_text)
        entry = entries.get(key)
        weights.append(compute_weight(entry, total_sessions))
    return weights

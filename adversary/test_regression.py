"""
adversary/test_regression.py

Curated pytest regression suite for the WW1 & WW2 Trivia CLI.
Each test guards a specific fragile area documented in known_issues.json.

Run with:   python -m pytest adversary/test_regression.py -v
"""
import sys
import os
import pytest

# Allow importing from the project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ─── Seed Tests ────────────────────────────────────────────────────────────────

from state import generate_seed, decode_seed, DEFAULT_TOPIC

class TestSeedEncoding:
    def test_short_seed_default_topic(self):
        """Default topic should produce a clean 6-char code with no ':' suffix."""
        seed = generate_seed(DEFAULT_TOPIC)
        assert ":" not in seed, "Default topic must NOT append ':' suffix"
        assert len(seed) == 6, f"Seed should be exactly 6 chars, got {len(seed)}"
        assert seed.isupper() or seed.isalnum(), "Seed should be alphanumeric uppercase"

    def test_short_seed_custom_topic(self):
        """Custom topic should produce a 'XXXXXX:Topic' format."""
        seed = generate_seed("Spies")
        assert ":" in seed, "Custom topic seed must contain ':' separator"
        parts = seed.split(":", 1)
        assert len(parts[0]) == 6, "Seed prefix must be 6 characters"
        assert parts[1] == "Spies", "Topic suffix must match exactly"

    def test_seed_roundtrip(self):
        """Encoding and then decoding a seed must return the same values."""
        for topic in [DEFAULT_TOPIC, "Naval Battles", "Spies & Espionage"]:
            seed_code = generate_seed(topic)
            recovered_seed, recovered_topic = decode_seed(seed_code)
            assert recovered_topic == topic, f"Topic mismatch: got '{recovered_topic}', expected '{topic}'"
            assert len(recovered_seed) == 6, "Internal seed should always be 6 chars"

    def test_old_base64_seed_backward_compat(self):
        """Old long base64 seeds must still decode correctly."""
        old_seed = "eyJzIjogIlNHQ0gxTiIsICJ0IjogIkdlbmVyYWwgV1cxIGFuZCBXVzIgSGlzdG9yeSJ9"
        s, t = decode_seed(old_seed)
        assert len(s) == 6, f"Decoded internal seed should be 6 chars, got '{s}'"
        assert "WW" in t or "General" in t, f"Decoded topic looks wrong: '{t}'"

    def test_decode_bare_code(self):
        """A bare 6-char code with no topic should decode to the default topic."""
        _, topic = decode_seed("ABC123")
        assert topic == DEFAULT_TOPIC

# ─── Database Tests ────────────────────────────────────────────────────────────

from database import LocalKnowledgeBank

class TestDatabase:
    @pytest.fixture(scope="class")
    def bank(self):
        b = LocalKnowledgeBank()
        # Tests require the DB to actually load; skip if enc file not present
        if not b._questions:
            pytest.skip("questions.enc not found or failed to decrypt — skipping DB tests")
        return b

    def test_database_loads_and_decrypts(self, bank):
        """The encrypted database must load without errors."""
        assert bank is not None, "LocalKnowledgeBank failed to initialize"

    def test_database_question_count(self, bank):
        """Offline bank must contain a substantial number of questions."""
        count = len(bank._questions)
        assert count > 100, f"Expected >100 questions, got {count}"

    def test_get_question_returns_valid_question(self, bank):
        """get_question must return a well-formed Question object."""
        q = bank.get_question(difficulty=1, random_seed=42, seen_questions=set())
        assert q is not None, "get_question returned None for difficulty=1"
        assert q.question_text, "question_text must not be empty"
        assert q.correct_answer in q.options, "correct_answer must be one of the options"
        assert len(q.options) == 4, f"Expected 4 options, got {len(q.options)}"

    def test_get_question_respects_difficulty(self, bank):
        """get_question must return a question matching the requested difficulty."""
        for diff in [1, 2, 3, 4, 5]:
            q = bank.get_question(difficulty=diff, random_seed=42, seen_questions=set())
            if q:  # Some difficulties may have fewer questions
                assert q.difficulty == diff, f"Requested diff={diff}, got {q.difficulty}"

    def test_no_duplicate_questions_in_session(self, bank):
        """Questions must not repeat within a single session."""
        seen = set()
        for i in range(20):
            q = bank.get_question(difficulty=1, random_seed=i, seen_questions=seen)
            if q is None:
                break
            assert q.question_text not in seen, f"Duplicate question returned at iteration {i}!"
            seen.add(q.question_text)

    def test_seen_questions_not_mutated_by_filter(self, bank):
        """The seen_questions set must not be modified by get_question."""
        seen = {"Some existing question that definitely is not in the bank"}
        original_size = len(seen)
        bank.get_question(difficulty=1, random_seed=99, seen_questions=seen)
        assert len(seen) == original_size, "get_question must not mutate seen_questions"


# ─── Game State Tests ──────────────────────────────────────────────────────────

from state import GameState, QuizConfig

class TestGameState:
    def test_game_state_defaults(self):
        """GameState must initialize with sane defaults."""
        state = GameState(seed="ABC123", config=QuizConfig())
        assert state.score == 0
        assert state.questions_answered == 0
        assert state.current_difficulty == 1
        assert len(state.seen_questions) == 0
        assert len(state.question_history) == 0

    def test_quiz_config_defaults_to_local_bank(self):
        """Default provider must be local_bank (no API key required)."""
        config = QuizConfig()
        assert config.llm_provider == "local_bank"
        assert config.llm_model == "questions.enc"

# ─── Question History & Weighted Sampling Tests ────────────────────────────────

from question_history import (
    fingerprint, load_history, save_history,
    start_new_session, record_asked, compute_weight, get_weights_for_candidates,
    HARD_COOLDOWN_SESSIONS, WEIGHT_FLOOR
)

class TestQuestionHistory:
    def test_fingerprint_is_deterministic(self):
        """Same question text must always produce the same fingerprint."""
        text = "Which country invaded Poland in September 1939?"
        assert fingerprint(text) == fingerprint(text)
        assert fingerprint(text) == fingerprint(text + "   ")  # trailing space trimmed

    def test_fingerprint_is_unique(self):
        """Different question texts must produce different fingerprints."""
        a = fingerprint("Question A about WW1")
        b = fingerprint("Question B about WW2")
        assert a != b

    def test_fresh_question_gets_max_weight(self):
        """A question never asked should get weight 1.0."""
        w = compute_weight(entry=None, total_sessions=10)
        assert w == 1.0

    def test_hard_cooldown_gives_zero_weight(self):
        """A question asked this session or last session must get weight 0.0."""
        for sessions_ago in range(1, HARD_COOLDOWN_SESSIONS + 1):
            entry = {"global_count": 1, "last_asked_session": 10 - sessions_ago + 1, "session_history": []}
            w = compute_weight(entry, total_sessions=10)
            assert w == 0.0, f"Expected 0.0 for sessions_ago={sessions_ago}, got {w}"

    def test_weight_recovers_after_cooldown(self):
        """Weight must be > 0 once outside the hard cooldown window."""
        entry = {"global_count": 1, "last_asked_session": 5, "session_history": []}
        w = compute_weight(entry, total_sessions=10)  # 5 sessions ago
        assert w > 0.0

    def test_global_frequency_lowers_weight(self):
        """More frequently asked questions must have lower weight."""
        entry_fresh = {"global_count": 0, "last_asked_session": 0, "session_history": []}
        entry_used  = {"global_count": 15, "last_asked_session": 0, "session_history": []}
        w_fresh = compute_weight(entry_fresh, total_sessions=10)
        w_used  = compute_weight(entry_used,  total_sessions=10)
        assert w_fresh > w_used, "Frequently asked question must have lower weight"

    def test_weight_floor_respected(self):
        """Weight must never go below WEIGHT_FLOOR (even for very overused questions)."""
        entry = {"global_count": 9999, "last_asked_session": 0, "session_history": []}
        w = compute_weight(entry, total_sessions=10)
        assert w >= WEIGHT_FLOOR

    def test_all_zero_weights_fallback(self):
        """If all candidate weights are 0, database must not crash (fallback to uniform)."""
        history = {"version": 1, "total_sessions": 1, "entries": {}}
        from database import LocalKnowledgeBank
        bank = LocalKnowledgeBank()
        if not bank._questions:
            pytest.skip("questions.enc not available")
        # Force all candidates into hard cooldown by marking them asked this session
        for q in bank._questions[:20]:
            record_asked(history, q.question_text)
        # get_question should still return something without crashing
        q = bank.get_question(difficulty=1, random_seed=42, seen_questions=set(), history=history)
        # May be None if truly exhausted, but must not raise
        assert q is None or hasattr(q, "question_text")


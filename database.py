import os
import json
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

# Secret symmetric key generated specifically for this game instance
DATABASE_DECRYPTION_KEY = b'F13KDlnu_x0tiDfYT0K8SVdEaGgDgUFJUgM-LydsKW0='

class Question(BaseModel):
    question_text: str = Field(description="The text of the quiz question.")
    options: list[str] = Field(description="Exactly 4 multiple-choice options.")
    correct_answer: str = Field(description="The exact correct answer from the options.")
    explanation: str = Field(description="A brief explanation of why the answer is correct.")
    difficulty: int = Field(description="Difficulty level from 1 to 5.")
    topic_tags: list[str] = Field(description="Tags describing the topic.")

class LocalKnowledgeBank:
    def __init__(self, db_path="questions.enc"):
        self.db_path = db_path
        self._questions = []
        self.bank_version = 0  # Set by _load_and_decrypt from the version envelope
        self._load_and_decrypt()


    def _load_and_decrypt(self):
        """Loads and decrypts the knowledge bank into memory."""
        if not os.path.exists(self.db_path):
            print(f"[ERROR] Database file '{self.db_path}' not found. Cannot load offline local bank.")
            return

        try:
            cipher = Fernet(DATABASE_DECRYPTION_KEY)
            with open(self.db_path, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = cipher.decrypt(encrypted_data).decode("utf-8")
            raw = json.loads(decrypted_data)

            # Support both old format (bare list) and new versioned envelope
            if isinstance(raw, dict) and "questions" in raw:
                self.bank_version = raw.get("bank_version", 1)
                questions_list = raw["questions"]
            else:
                # Legacy format — bare list
                self.bank_version = 0
                questions_list = raw

            self._questions = [Question.model_validate(q) for q in questions_list]
        except Exception as e:
            print(f"[ERROR] Failed to decrypt local knowledge bank: {e}")



    def get_question(self, difficulty: int, random_seed: int, topic: str = "General WW1 and WW2 History", seen_questions: set = None, history: dict = None) -> Question:
        """Finds a matching question using difficulty, topic, and inverse-frequency weighted sampling.

        Args:
            difficulty: Target difficulty (1-5).
            random_seed: Deterministic seed for reproducible sessions.
            topic: Topic filter; 'General WW1 and WW2 History' matches all.
            seen_questions: Set of question texts already shown this session.
            history: The global question history dict from question_history.py.
                     If None, falls back to uniform random sampling (no weighting).
        """
        import random
        from question_history import get_weights_for_candidates
        random.seed(random_seed)

        candidates = []
        if seen_questions is None:
            seen_questions = set()

        for q in self._questions:
            if q.question_text in seen_questions:
                continue

            # For Local Bank, "General WW1 and WW2 History" allows everything.
            if topic == "General WW1 and WW2 History":
                if q.difficulty == difficulty:
                    candidates.append(q)
            else:
                # Naive topic matching, fallback to ignoring topic if too strict
                is_match = any(t.lower() in topic.lower() for t in q.topic_tags) or topic.lower() in " ".join(q.topic_tags).lower()
                if is_match and q.difficulty == difficulty:
                    candidates.append(q)

        # If no strict match found, relax constraints
        if not candidates:
            for q in self._questions:
                if q.question_text not in seen_questions:
                    candidates.append(q)

        if not candidates:
            return None  # Out of questions

        # --- Weighted sampling ---
        if history is not None:
            weights = get_weights_for_candidates(candidates, history)
            # If all weights are 0 (everything in hard cooldown), fall back to uniform
            if sum(weights) == 0:
                weights = [1.0] * len(candidates)
            return random.choices(candidates, weights=weights, k=1)[0]
        else:
            # No history provided — uniform fallback (used in tests / first run)
            return random.choice(candidates)

# --- Multi-Bank Management ---
BANKS_DIR = "banks"
INDEX_PATH = os.path.join(BANKS_DIR, "index.json")

def _ensure_banks_index():
    if not os.path.exists(BANKS_DIR):
        os.makedirs(BANKS_DIR)
    
    if not os.path.exists(INDEX_PATH):
        # Create default index pointing to the official root bank
        default_index = {
            "banks": [
                {
                    "id": "official",
                    "name": "Official WW1 & WW2 Bank",
                    "path": "questions.enc",
                    "is_official": True
                }
            ],
            "active_bank_id": "official"
        }
        with open(INDEX_PATH, "w") as f:
            json.dump(default_index, f, indent=2)

def list_available_banks() -> list[dict]:
    """Returns a list of all registered question banks."""
    _ensure_banks_index()
    try:
        with open(INDEX_PATH, "r") as f:
            data = json.load(f)
            return data.get("banks", [])
    except Exception:
        return []

def get_active_bank_info() -> dict:
    _ensure_banks_index()
    try:
        with open(INDEX_PATH, "r") as f:
            data = json.load(f)
            active_id = data.get("active_bank_id", "official")
            for b in data.get("banks", []):
                if b["id"] == active_id:
                    return b
    except Exception:
        pass
    
    return {"id": "official", "name": "Official WW1 & WW2 Bank", "path": "questions.enc"}

active_bank_info = get_active_bank_info()
active_bank = LocalKnowledgeBank(db_path=active_bank_info["path"])

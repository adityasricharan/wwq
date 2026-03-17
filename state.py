import os
import random
import string
from pydantic import BaseModel
from typing import Optional

class QuizConfig(BaseModel):
    topic: str = "General WW1 and WW2 History"
    format: str = "Standard multiple choice"
    max_difficulty: int = 5
    llm_provider: str = "local_bank"
    llm_model: str = "questions.enc"
    
class GameState(BaseModel):
    score: float = 0
    current_difficulty: int = 1
    questions_answered: int = 0
    seed: str
    config: QuizConfig
    override_difficulty: Optional[int] = None
    question_history: list[dict] = []
    seen_questions: set[str] = set()
    game_mode: str = "adaptive"       # "adaptive" | "vs"
    total_questions: int = 20         # Configurable at game start
    vs_question_list: list[str] = []  # Pre-drawn list for vs mode


import hashlib

DEFAULT_TOPIC = "General WW1 and WW2 History"

def generate_seed(topic: str, bank_version: int = 0) -> str:
    """Generates a short, human-readable seed code for VS Mode.
    Format:
      'VS:XXXXXX@vN'          — default topic
      'VS:XXXXXX:Topic@vN'    — custom topic
    The 6-character code is uppercase alphanumeric and easy to share verbally.
    bank_version=0 means unversioned (omits @v suffix).
    """
    seed = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    topic_part = f":{topic}" if topic and topic != DEFAULT_TOPIC else ""
    version_part = f"@v{bank_version}" if bank_version > 0 else ""
    return f"VS:{seed}{topic_part}{version_part}"

def decode_seed(seed_hash: str) -> tuple[str, str, int | None]:
    """Decodes a seed string into (seed, topic, bank_version).

    bank_version is None if the seed predates versioning.
    Handles:
      - New format: 'XXXXXX@v2', 'XXXXXX:Topic@v2'
      - Unversioned: 'XXXXXX', 'XXXXXX:Topic'
      - Old base64 (backward compat)
    """
    # Check if it's likely old base64 format
    if len(seed_hash) > 12 and ':' not in seed_hash and '@' not in seed_hash:
        try:
            import base64, json
            json_str = base64.b64decode(seed_hash.encode('utf-8')).decode('utf-8')
            data = json.loads(json_str)
            return data.get("s", "AAAAAA"), data.get("t", DEFAULT_TOPIC), None
        except Exception:
            pass

    # Strip bank version suffix (@v2) if present
    bank_version: int | None = None
    if '@v' in seed_hash:
        seed_hash, version_str = seed_hash.rsplit('@v', 1)
        try:
            bank_version = int(version_str)
        except ValueError:
            bank_version = None

    # Extract VS prefix if present (it should be for new seeds)
    if seed_hash.upper().startswith("VS:"):
        seed_hash = seed_hash[3:]

    # Parse topic suffix
    if ':' in seed_hash:
        parts = seed_hash.split(':', 1)
        return parts[0].upper(), parts[1], bank_version
    else:
        return seed_hash.upper(), DEFAULT_TOPIC, bank_version


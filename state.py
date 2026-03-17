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

import hashlib

DEFAULT_TOPIC = "General WW1 and WW2 History"

def generate_seed(topic: str) -> str:
    """Generates a short, human-readable seed code.
    Format: 'XXXXXX' for a default topic, or 'XXXXXX:Topic' for a custom topic.
    The 6-character code is uppercase alphanumeric and easy to share verbally.
    """
    seed = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    if topic and topic != DEFAULT_TOPIC:
        return f"{seed}:{topic}"
    return seed

def decode_seed(seed_hash: str) -> tuple[str, str]:
    """Decodes the short seed code back into (seed, topic).

    Handles both new short format ('A3F2C1' or 'A3F2C1:Topic') and
    the old long base64 format for backward compatibility.
    """
    # Check if it's likely old base64 format (long string, no valid 6-char prefix structure)
    if len(seed_hash) > 12 and ':' not in seed_hash:
        try:
            import base64, json
            json_str = base64.b64decode(seed_hash.encode('utf-8')).decode('utf-8')
            data = json.loads(json_str)
            return data.get("s", "AAAAAA"), data.get("t", DEFAULT_TOPIC)
        except Exception:
            pass  # Fall through to short-format parsing

    # New short format
    if ':' in seed_hash:
        parts = seed_hash.split(':', 1)
        return parts[0].upper(), parts[1]
    else:
        return seed_hash.upper(), DEFAULT_TOPIC

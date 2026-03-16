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

import base64
import json

def generate_seed(topic: str) -> str:
    """Generates a base64 encoded hashcode containing the random seed and the quiz config."""
    seed = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    data = {"s": seed, "t": topic}
    json_str = json.dumps(data)
    return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

def decode_seed(seed_hash: str) -> tuple[str, str]:
    """Decodes the hashcode into the random seed and the topic."""
    try:
        json_str = base64.b64decode(seed_hash.encode('utf-8')).decode('utf-8')
        data = json.loads(json_str)
        return data.get("s", "AAAAAA"), data.get("t", "General WW1 and WW2 History")
    except Exception:
        # Fallback if the user just typed a random string instead of a hashcode
        return seed_hash, "General WW1 and WW2 History"

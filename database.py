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
                
            decrypted_data = cipher.decrypt(encrypted_data).decode('utf-8')
            raw_json = json.loads(decrypted_data)
            
            self._questions = [Question.model_validate(q) for q in raw_json]
        except Exception as e:
            print(f"[ERROR] Failed to decrypt local knowledge bank: {e}")

    def get_question(self, difficulty: int, random_seed: int, topic: str = "General WW1 and WW2 History", seen_questions: set = None) -> Question:
        """Finds a matching question based on difficulty and topic using the deterministic random seed."""
        import random
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
            return None # Out of questions
            
        return random.choice(candidates)

# Global Instance
active_bank = LocalKnowledgeBank()

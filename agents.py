import os
import json
from pydantic import BaseModel, Field
try:
    import litellm
except ImportError:
    litellm = None
import ollama

class Question(BaseModel):
    question_text: str = Field(description="The text of the quiz question.")
    options: list[str] = Field(description="Exactly 4 multiple-choice options.")
    correct_answer: str = Field(description="The exact correct answer from the options.")
    explanation: str = Field(description="A brief explanation of why the answer is correct.")

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="True if the question is historically accurate and has only one correct answer.")
    feedback: str = Field(description="Feedback for the Historian if the question is invalid, or a confirmation if valid.")

from typing import Optional

def generate_question(provider: str, model: str, topic: str, format_instructions: str, difficulty: int, random_seed: int, seen_questions: Optional[set] = None, history: Optional[dict] = None) -> Question:
    """Calls the Historian agent to generate a question.
    
    Args:
        history: Global question frequency history from question_history.py.
                 Used to weight the probability of local_bank questions.
    """
    prompt = f"""
    You are 'The Historian', an expert in WW1 and WW2 history.
    Your task is to generate a trivia question with exactly 4 options and 1 correct answer.
    Focus on events, characters, places, timing, and quirky details from history, NOT just military events and numbers.
    The difficulty should be scaled from 1 to 5. The current difficulty is: {difficulty}.
    The user's requested topic/theme is: '{topic}'.
    The user's requested format is: '{format_instructions}'.
    
    Make the question engaging and accurately reflective of the difficulty. A high difficulty should be very obscure.
    Incorporate this random element to ensure variety even with the same difficulty: {random_seed}
    """
    
    if provider == "local_bank":
        from database import active_bank
        # Attempt to pull a question from our curated local bank, with history-weighted sampling
        q = active_bank.get_question(difficulty=difficulty, random_seed=random_seed, topic=topic, seen_questions=seen_questions, history=history)
        if q: return q
        # If we failed to find one, raise error fallback
        raise Exception("Local knowledge bank exhausted or missing.")

    
    if provider == "ollama":
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format=Question.model_json_schema(),
            options={"temperature": 0.8}
        )
        return Question.model_validate_json(response['message']['content'])
    else:
        full_model = f"{provider}/{model}" if provider != "openai" and "/" not in model else model
        response = litellm.completion(
            model=full_model,
            messages=[{"role": "user", "content": prompt}],
            response_format=Question,
            temperature=0.8
        )
        return Question.model_validate_json(response.choices[0].message.content)

def validate_question(provider: str, model: str, question: Question) -> ValidationResult:
    """Calls the Fact Checker agent to validate the question."""
    prompt = f"""
    You are 'The Fact Checker', an expert in WW1 and WW2 history.
    Review the following trivia question for historical accuracy.
    Ensure that exactly ONE option is unequivocally correct and all other options are incorrect.
    
    Question: {question.question_text}
    Options: {', '.join(question.options)}
    Proposed Correct Answer: {question.correct_answer}
    Explanation: {question.explanation}
    """
    
    if provider == "local_bank":
        # Pre-curated local knowledge bank questions don't require external API validation
        return ValidationResult(is_valid=True, feedback="Valid pre-curated question from local bank.")
    
    if provider == "ollama":
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format=ValidationResult.model_json_schema(),
            options={"temperature": 0.2}
        )
        return ValidationResult.model_validate_json(response['message']['content'])
    else:
        full_model = f"{provider}/{model}" if provider != "openai" and "/" not in model else model
        response = litellm.completion(
            model=full_model,
            messages=[{"role": "user", "content": prompt}],
            response_format=ValidationResult,
            temperature=0.2
        )
        return ValidationResult.model_validate_json(response.choices[0].message.content)

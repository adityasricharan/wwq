import os
import json
import asyncio
from pydantic import BaseModel, Field
import litellm
from dotenv import load_dotenv

load_dotenv()

class Question(BaseModel):
    question_text: str = Field(description="The text of the quiz question.")
    options: list[str] = Field(description="Exactly 4 multiple-choice options.")
    correct_answer: str = Field(description="The exact correct answer from the options.")
    explanation: str = Field(description="A brief explanation of why the answer is correct.")
    difficulty: int = Field(description="Difficulty level from 1 to 5.")
    topic_tags: list[str] = Field(description="Tags describing the topic, e.g. ['WW2', 'Naval', 'Pacific']")

class QuestionBatch(BaseModel):
    questions: list[Question] = Field(description="A list of trivia questions.")

sem = asyncio.Semaphore(5)

async def generate_batch(batch_size: int = 20, batch_id: int = 0) -> list[Question]:
    prompt = f"""
    You are an expert World War 1 and World War 2 historian.
    Output a batch of exactly {batch_size} unique, highly accurate trivia questions.
    PRIORITIZE STRICT FACTUAL CORRECTNESS ABOVE ALL ELSE. Do not hallucinate. Verify dates and names mentally before outputting.
    Vary the difficulty wildly across the batch from 1 (very easy/common knowledge) to 5 (extremely obscure historians-only facts).
    Vary the topics (weapons, leaders, dates, politics, espionage, naval battles, air combat, treaties).
    Make sure exactly one option is correct.
    Ensure explanations are concise but highly educational.
    """
    
    async with sem:
        for attempt in range(5):
            try:
                print(f"[{batch_id}] Requesting batch from API...")
                response = await litellm.acompletion(
                    model="gemini/gemini-2.5-flash",
                    messages=[{"role": "user", "content": prompt}],
                    response_format=QuestionBatch,
                    temperature=0.7
                )
                batch = QuestionBatch.model_validate_json(response.choices[0].message.content)
                print(f"[{batch_id}] Success!")
                return batch.questions
            except Exception as e:
                print(f"[{batch_id}] Error (attempt {attempt+1}): {e}")
                await asyncio.sleep(15)
        return []

async def main():
    target_questions = 2048
    batch_size = 40
    
    all_questions = []
    if os.path.exists("questions_raw.json"):
        try:
            with open("questions_raw.json", "r", encoding="utf-8") as f:
                all_questions = json.load(f)
            print(f"Resuming from {len(all_questions)} existing questions.")
        except Exception:
            print("Could not load existing questions, starting fresh.")
            
    if len(all_questions) >= target_questions:
        print("Target question count already reached!")
        return

    questions_needed = target_questions - len(all_questions)
    total_batches = (questions_needed + batch_size - 1) // batch_size
    
    print(f"Starting bulk generation of {questions_needed} more WW1/WW2 questions ({total_batches} batches)...")
    
    tasks = []
    for i in range(total_batches):
        tasks.append(generate_batch(batch_size, i+1))
        
    for f in asyncio.as_completed(tasks):
        batch_qs = await f
        # Deduplication check
        existing_texts = {q['question_text'] for q in all_questions}
        for q in batch_qs:
            q_dict = q.model_dump()
            if q_dict['question_text'] not in existing_texts:
                all_questions.append(q_dict)
                existing_texts.add(q_dict['question_text'])
                
        print(f"Progress: {len(all_questions)}/{target_questions} questions locally saved.")
        
        # Save progressively in case the script crashes after an hour
        with open("questions_raw.json", "w", encoding="utf-8") as f_out:
            json.dump(all_questions, f_out, indent=4)
            
    print(f"Successfully finished generating {len(all_questions)} questions.")

if __name__ == "__main__":
    asyncio.run(main())

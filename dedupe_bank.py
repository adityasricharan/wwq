"""
dedupe_bank.py

Utility script to scan the active offline question bank, identify questions
with semantically identical answers, and replace them with fresh questions
using the Gemini API to ensure the bank size remains exactly the same.

Usage:
    python dedupe_bank.py             # Run full deduplication
    python dedupe_bank.py --dry-run   # Show collisions without modifying
    python dedupe_bank.py --api-key YOUR_KEY  # Pass API key directly
"""
import os
import sys
import json
import asyncio
import argparse
import re
from collections import defaultdict
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import DATABASE_DECRYPTION_KEY, normalize_answer, active_bank_info

load_dotenv()

DB_PATH = active_bank_info["path"]
MAX_CONCURRENT = 3   # Conservative — stay within free tier rate limits
MODEL = "gemini-2.5-flash"


# ── Pydantic models ───────────────────────────────────────────────────────────

class Question(BaseModel):
    question_text: str = Field(description="The text of the quiz question.")
    options: list[str] = Field(description="Exactly 4 multiple-choice options.")
    correct_answer: str = Field(description="The exact correct answer from the options.")
    explanation: str = Field(description="A brief explanation of why the answer is correct.")
    difficulty: int = Field(description="Difficulty level from 1 to 5.")
    topic_tags: list[str] = Field(description="Tags describing the topic.")

class QuestionBatch(BaseModel):
    questions: list[Question] = Field(description="A list of trivia questions.")

class DuplicateDecision(BaseModel):
    is_duplicate: bool = Field(description="True if both answers refer to the exact same historical entity.")
    reasoning: str = Field(description="Brief explanation.")


sem = asyncio.Semaphore(MAX_CONCURRENT)

_client = None

def get_client(api_key: str | None = None):
    global _client
    if _client is None:
        from google import genai
        key = api_key or os.getenv("GOOGLE_API_KEY")
        _client = genai.Client(api_key=key)
    return _client


# ── Phase 1: Decrypt and Group ────────────────────────────────────────────────

def load_bank() -> tuple[list[dict], dict | None]:
    """Returns (questions_list, envelope_dict_or_None)."""
    cipher = Fernet(DATABASE_DECRYPTION_KEY)
    with open(DB_PATH, "rb") as f:
        encrypted = f.read()
    raw = json.loads(cipher.decrypt(encrypted).decode("utf-8"))
    if isinstance(raw, dict) and "questions" in raw:
        return raw["questions"], raw
    return raw, None


def group_by_normalized_answer(questions: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for q in questions:
        norm = normalize_answer(q["correct_answer"])
        groups[norm].append(q)
    return {k: v for k, v in groups.items() if len(v) > 1}


# ── Phase 2: LLM Duplicate Verification ───────────────────────────────────────

def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


async def check_semantic_duplicate(ans1: str, ans2: str, api_key: str | None = None) -> bool:
    """Uses the LLM to verify if two answer strings represent the exact same concept."""
    from google.genai import types as gtypes
    client = get_client(api_key)

    prompt = f"""You are an expert trivia judge.
Analyze these two quiz answers:
  Answer 1: "{ans1}"
  Answer 2: "{ans2}"

Do these two answers refer to the EXACT SAME historical entity, concept, or event?
- YES if they are clearly alternate phrasings (e.g. "George Patton" and "General Patton").
- NO if they are genuinely distinct (e.g. "World War I" vs "World War II").

Return ONLY a valid JSON object:
{{"is_duplicate": true, "reasoning": "brief explanation"}}
"""
    async with sem:
        for attempt in range(3):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=MODEL,
                        contents=prompt,
                        config=gtypes.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                        )
                    )
                )
                decision = DuplicateDecision.model_validate_json(_clean_json(response.text))
                return decision.is_duplicate
            except Exception as e:
                if attempt == 2:
                    print(f"  [warn] Semantic check failed: {e}. Treating as duplicate.")
                await asyncio.sleep(2)
        return True


# ── Phase 3 & 4: Replacement Generation ───────────────────────────────────────

async def generate_replacement(
    topic_tags: list[str],
    difficulty: int,
    existing_texts: set[str],
    existing_answers: set[str],
    api_key: str | None = None
) -> dict | None:
    """Generates one replacement question matching the original topic/difficulty."""
    from google.genai import types as gtypes
    client = get_client(api_key)
    topic_str = ", ".join(topic_tags) if topic_tags else "WW1 and WW2 History"

    prompt = f"""You are an expert WW1 and WW2 trivia historian.
Generate EXACTLY ONE accurate trivia question.

REQUIREMENTS:
- Topic: {topic_str}
- Difficulty: {difficulty} out of 5 (1=easy, 5=extremely obscure)
- Exactly 4 options, exactly 1 correct
- Strict factual accuracy — no hallucination

Return ONLY a JSON object:
{{
  "questions": [
    {{
      "question_text": "...",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "...",
      "explanation": "...",
      "difficulty": {difficulty},
      "topic_tags": ["...", "..."]
    }}
  ]
}}
"""
    async with sem:
        for attempt in range(4):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=MODEL,
                        contents=prompt,
                        config=gtypes.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.75,
                        )
                    )
                )
                batch = QuestionBatch.model_validate_json(_clean_json(response.text))
                if not batch.questions:
                    continue

                q = batch.questions[0]
                n_ans = normalize_answer(q.correct_answer)

                if q.question_text not in existing_texts and n_ans not in existing_answers:
                    existing_texts.add(q.question_text)
                    existing_answers.add(n_ans)
                    return q.model_dump()

            except Exception as e:
                if attempt == 3:
                    print(f"  [warn] Replacement generation failed: {e}")
                await asyncio.sleep(5)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate the active WWQ question bank using Gemini LLM verification."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show collisions without modifying the bank.")
    parser.add_argument("--api-key", type=str, default=None,
                        help="Google API key (overrides .env GOOGLE_API_KEY).")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY not set. Pass --api-key KEY or add it to .env")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"❌ {DB_PATH} not found.")
        sys.exit(1)

    print("=" * 60)
    print(f"  🔍 WWQ Answer Deduplication")
    print(f"  Bank   : {DB_PATH}")
    print(f"  Model  : {MODEL}")
    print("=" * 60)

    # 1. Load and group by normalized answer
    questions, envelope = load_bank()
    print(f"\n📊 Bank contains {len(questions)} questions.")

    groups = group_by_normalized_answer(questions)
    print(f"   Found {len(groups)} normalized answers with 2+ questions.")

    if not groups:
        print("\n✅ Bank is completely clean — no duplicate answers detected!")
        return

    # 2. Fan-out LLM verification of all suspicious pairs
    print(f"\n🤖 Verifying semantic collisions with {MODEL}...")

    verification_tasks = []
    group_meta = []

    for norm_ans, group in groups.items():
        keeper = group[0]
        for duplicate in group[1:]:
            verification_tasks.append(
                check_semantic_duplicate(keeper["correct_answer"], duplicate["correct_answer"], api_key)
            )
            group_meta.append((keeper, duplicate))

    results = await asyncio.gather(*verification_tasks)

    to_delete_indices = set()
    replacement_requests = []

    existing_texts = {q["question_text"] for q in questions}
    existing_answers = {normalize_answer(q["correct_answer"]) for q in questions}

    for is_dup, (keeper, duplicate) in zip(results, group_meta):
        if is_dup:
            print(f"\n   [COLLISION]")
            print(f"   KEEPER : [{keeper.get('difficulty', '?')}] {keeper['question_text'][:75]} → {keeper['correct_answer']}")
            print(f"   DELETE : [{duplicate.get('difficulty', '?')}] {duplicate['question_text'][:75]} → {duplicate['correct_answer']}")

            for i, q in enumerate(questions):
                if q["question_text"] == duplicate["question_text"]:
                    to_delete_indices.add(i)
                    replacement_requests.append((
                        duplicate.get("topic_tags", ["WW1 and WW2 History"]),
                        duplicate.get("difficulty", 2)
                    ))
                    break

    if not to_delete_indices:
        print("\n✅ LLM review confirmed: no genuine semantic duplicates found!")
        return

    print(f"\n🗑️  Verified duplicates queued for deletion: {len(to_delete_indices)}")

    if args.dry_run:
        print("\n[DRY RUN] No changes made to the bank.")
        return

    # 3. Generate replacements
    print(f"\n🤖 Generating {len(replacement_requests)} replacement questions...")

    tasks = [
        generate_replacement(topics, diff, existing_texts, existing_answers, api_key)
        for topics, diff in replacement_requests
    ]

    replacements = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        new_q = await coro
        done += 1
        if new_q:
            replacements.append(new_q)
            print(f"  [{done}/{len(tasks)}] ✅ → {new_q['correct_answer']}")
        else:
            print(f"  [{done}/{len(tasks)}] ❌ Failed to generate unique replacement")

    # 4. Merge
    final_bank = [q for i, q in enumerate(questions) if i not in to_delete_indices]
    final_bank.extend(replacements)

    # 5. Re-encrypt and save
    cipher = Fernet(DATABASE_DECRYPTION_KEY)
    if envelope is not None:
        envelope["questions"] = final_bank
        to_encrypt = json.dumps(envelope, indent=2).encode("utf-8")
    else:
        to_encrypt = json.dumps(final_bank, indent=2).encode("utf-8")

    encrypted = cipher.encrypt(to_encrypt)
    with open(DB_PATH, "wb") as f:
        f.write(encrypted)

    print("\n" + "=" * 60)
    print(f"  Bank size before : {len(questions)}")
    print(f"  Duplicates axed  : {len(to_delete_indices)}")
    print(f"  New replacements : {len(replacements)}")
    print(f"  Bank size after  : {len(final_bank)}")
    print("=" * 60)
    print(f"\n🎉 Done! Bank saved to {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

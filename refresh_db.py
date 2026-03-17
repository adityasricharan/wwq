"""
refresh_db.py

History-driven partial question bank refresh.

Reads question_history.json to identify the most over-used questions,
evicts them from questions.enc, and replaces them with freshly generated
questions from the Gemini API.

Usage:
    python refresh_db.py              # Auto-select up to 200 overused Qs
    python refresh_db.py --count 128  # Custom replacement count
    python refresh_db.py --dry-run    # Show what would be replaced, no changes
    python refresh_db.py --threshold 2 # Min global_count to be eligible (default: 3)
"""
import os
import sys
import json
import asyncio
import argparse
from pydantic import BaseModel, Field
import litellm
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# ── Import from the project modules ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from question_history import load_history, fingerprint, HARD_COOLDOWN_SESSIONS
from database import DATABASE_DECRYPTION_KEY

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_REPLACE_COUNT = 200   # ~10% of a 2046-question bank
MIN_THRESHOLD = 3             # Minimum global_count to be a retirement candidate
BATCH_SIZE = 40
MAX_CONCURRENT = 5
DB_PATH = "questions.enc"

# ── Pydantic models for generation ───────────────────────────────────────────
class Question(BaseModel):
    question_text: str = Field(description="The text of the quiz question.")
    options: list[str] = Field(description="Exactly 4 multiple-choice options.")
    correct_answer: str = Field(description="The exact correct answer from the options.")
    explanation: str = Field(description="A brief explanation of why the answer is correct.")
    difficulty: int = Field(description="Difficulty level from 1 to 5.")
    topic_tags: list[str] = Field(description="Tags describing the topic, e.g. ['WW2', 'Naval', 'Pacific']")

class QuestionBatch(BaseModel):
    questions: list[Question] = Field(description="A list of trivia questions.")

# ── Step 1: Identify which fingerprints to evict ──────────────────────────────
def select_retirement_candidates(history: dict, count: int, threshold: int) -> list[str]:
    """
    Returns a list of question fingerprints to retire, sorted by most-asked first.
    Only selects questions with global_count >= threshold.

    Args:
        history:   The loaded question history dict.
        count:     Maximum number of questions to retire.
        threshold: Minimum global_count to be eligible.
    """
    entries = history.get("entries", {})
    eligible = [
        (fp, entry["global_count"])
        for fp, entry in entries.items()
        if entry.get("global_count", 0) >= threshold
    ]
    # Sort by most asked first
    eligible.sort(key=lambda x: x[1], reverse=True)
    return [fp for fp, _ in eligible[:count]]

# ── Step 2: Decrypt the bank and remove retired questions ─────────────────────
def load_and_evict(retire_fps: set[str]) -> tuple[list[dict], int]:
    """
    Decrypts questions.enc, removes questions matching retire_fps fingerprints.
    Returns (remaining_questions, evicted_count).
    """
    cipher = Fernet(DATABASE_DECRYPTION_KEY)
    with open(DB_PATH, "rb") as f:
        encrypted = f.read()
    raw = json.loads(cipher.decrypt(encrypted).decode("utf-8"))

    remaining = []
    evicted = 0
    for q in raw:
        fp = fingerprint(q.get("question_text", ""))
        if fp in retire_fps:
            evicted += 1
        else:
            remaining.append(q)

    return remaining, evicted

# ── Step 3: Generate replacement questions ────────────────────────────────────
sem = asyncio.Semaphore(MAX_CONCURRENT)

async def generate_batch(batch_size: int, batch_id: int) -> list[dict]:
    prompt = f"""
    You are an expert World War 1 and World War 2 historian.
    Output a batch of exactly {batch_size} unique, highly accurate trivia questions
    for a REFRESH of an existing question bank. These should be FRESH, VARIED, and
    cover different angles from the usual battles and dates — focus on:
    espionage, propaganda, home front, economics, technology, lesser-known leaders,
    aftermath, diplomacy, and cultural impacts.
    PRIORITIZE STRICT FACTUAL CORRECTNESS ABOVE ALL ELSE.
    Vary difficulty from 1 (easy) to 5 (extremely obscure).
    Make sure exactly one option is correct.
    """
    async with sem:
        for attempt in range(5):
            try:
                print(f"  [batch {batch_id}] Requesting {batch_size} fresh questions...")
                response = await litellm.acompletion(
                    model="gemini/gemini-2.5-flash",
                    messages=[{"role": "user", "content": prompt}],
                    response_format=QuestionBatch,
                    temperature=0.85,  # Slightly higher temp for more variety on refresh
                )
                batch = QuestionBatch.model_validate_json(response.choices[0].message.content)
                print(f"  [batch {batch_id}] ✅ Got {len(batch.questions)} questions.")
                return [q.model_dump() for q in batch.questions]
            except Exception as e:
                print(f"  [batch {batch_id}] ❌ Error (attempt {attempt+1}/5): {e}")
                await asyncio.sleep(15)
        return []

async def generate_replacements(count: int, existing_texts: set[str]) -> list[dict]:
    """Generates exactly `count` new unique questions not in existing_texts."""
    total_batches = (count + BATCH_SIZE - 1) // BATCH_SIZE
    tasks = [generate_batch(BATCH_SIZE, i + 1) for i in range(total_batches)]

    new_questions = []
    for coro in asyncio.as_completed(tasks):
        batch = await coro
        for q in batch:
            if q["question_text"] not in existing_texts and len(new_questions) < count:
                new_questions.append(q)
                existing_texts.add(q["question_text"])
        print(f"  Progress: {len(new_questions)}/{count} replacement questions generated...")

    return new_questions

# ── Step 4: Re-encrypt and write the updated bank ────────────────────────────
def encrypt_and_save(questions: list[dict]):
    cipher = Fernet(DATABASE_DECRYPTION_KEY)
    json_bytes = json.dumps(questions, indent=2).encode("utf-8")
    encrypted = cipher.encrypt(json_bytes)
    with open(DB_PATH, "wb") as f:
        f.write(encrypted)
    print(f"\n✅ Saved {len(questions)} questions to {DB_PATH}")

# ── Step 5: Prune retired fingerprints from history ───────────────────────────
def prune_history(history: dict, retired_fps: set[str]):
    """Removes retired fingerprints from history so new questions start clean."""
    entries = history.get("entries", {})
    for fp in retired_fps:
        entries.pop(fp, None)
    history["entries"] = entries

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(
        description="Refresh the WWQ question bank by replacing the most over-used questions."
    )
    parser.add_argument("--count",     type=int, default=DEFAULT_REPLACE_COUNT,
                        help=f"Number of questions to replace (default: {DEFAULT_REPLACE_COUNT})")
    parser.add_argument("--threshold", type=int, default=MIN_THRESHOLD,
                        help=f"Minimum global_count to be eligible for retirement (default: {MIN_THRESHOLD})")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Show which questions would be retired without making changes.")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"❌ {DB_PATH} not found. Run generate_db.py and encrypt_db.py first.")
        sys.exit(1)

    print("=" * 60)
    print(f"  🔄 WWQ Question Bank Refresh")
    print("=" * 60)

    # Load history
    history = load_history()
    total_sessions = history.get("total_sessions", 0)
    total_tracked = len(history.get("entries", {}))
    print(f"\n📊 History: {total_sessions} sessions played, {total_tracked} questions tracked.")

    # Select retirement candidates
    retire_fps = select_retirement_candidates(history, args.count, args.threshold)
    if not retire_fps:
        print(f"\n✅ No questions have been asked ≥{args.threshold} times yet.")
        print("   Bank is still fresh — no refresh needed!")
        return

    print(f"\n🗑️  Retiring {len(retire_fps)} questions (asked ≥{args.threshold}× globally).")

    # Show top 10 most-used for visibility
    entries = history.get("entries", {})
    most_used = sorted(
        [(fp, e.get("global_count", 0)) for fp, e in entries.items()],
        key=lambda x: x[1], reverse=True
    )[:10]
    print(f"\n🔥 Top 10 most-asked question fingerprints:")
    for fp, count in most_used:
        marker = " ← retiring" if fp in retire_fps else ""
        print(f"   {fp}  (asked {count}×){marker}")

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    # Gate API key check AFTER dry-run (dry run doesn't need to call the API)
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ GOOGLE_API_KEY not set in .env. Required to generate replacement questions.")
        sys.exit(1)

    # Evict from bank
    print(f"\n🔓 Decrypting and evicting {len(retire_fps)} questions from {DB_PATH}...")
    retire_fps_set = set(retire_fps)
    remaining_qs, evicted_count = load_and_evict(retire_fps_set)
    print(f"   Evicted {evicted_count} questions. {len(remaining_qs)} remain.")

    actual_replace = min(evicted_count, args.count)

    # Generate replacements
    print(f"\n🤖 Generating {actual_replace} replacement questions via Gemini API...")
    existing_texts = {q["question_text"] for q in remaining_qs}
    new_qs = await generate_replacements(actual_replace, existing_texts)
    print(f"\n✅ Generated {len(new_qs)} replacement questions.")

    # Merge and save
    final_bank = remaining_qs + new_qs
    encrypt_and_save(final_bank)

    # Prune retired entries from history
    prune_history(history, retire_fps_set)
    from question_history import save_history
    save_history(history)
    print(f"📝 Cleared {len(retire_fps_set)} retired entries from question_history.json.")

    # Summary
    print("\n" + "=" * 60)
    print(f"  Bank size before: {evicted_count + len(remaining_qs)}")
    print(f"  Evicted (overused): {evicted_count}")
    print(f"  New replacements:   {len(new_qs)}")
    print(f"  Bank size after:  {len(final_bank)}")
    print("=" * 60)
    print("\n🎉 Refresh complete! Run     python encrypt_db.py     if needed,")
    print("   then push questions.enc to GitHub to distribute the update.")

if __name__ == "__main__":
    asyncio.run(main())

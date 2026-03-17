"""
seed_bank.py

User-friendly CLI to create a custom question bank.

Lets any user build their own themed question bank using any LLM provider/model
and API key, for up to 10,000 questions on custom topics. The official bank is
automatically backed up before any changes so it can always be restored.

Features:
  - API key validation before bulk generation starts
  - Per-error graceful handling: rate limits, auth errors, missing models
  - Rolling progress saves to questions_custom_raw.json (resume-safe)
  - Only replaces questions.enc if enough questions were generated (>= 50)
  - Official bank backup (questions.enc.official) written once and never overwritten

Usage:
  python seed_bank.py                       # Interactive wizard
  python seed_bank.py --count 500 --topics "Cold War, Korean War"
  python seed_bank.py --count 200 --model openai/gpt-4o --api-key sk-...
"""
import os
import sys
import json
import asyncio
import argparse
import time
import shutil

from pydantic import BaseModel, Field
try:
    from litellm import acompletion, AuthenticationError, NotFoundError, RateLimitError
except ImportError:
    acompletion = None  # Handle environments where litellm fails to install
    AuthenticationError = type('AuthenticationError', (Exception,), {}) # Mock exceptions
    NotFoundError = type('NotFoundError', (Exception,), {})
    RateLimitError = type('RateLimitError', (Exception,), {})
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import DATABASE_DECRYPTION_KEY

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_QUESTIONS = 10_000
MIN_VIABLE    = 20       # Minimum questions to actually save the bank
BATCH_SIZE    = 40
MAX_CONCURRENT = 5
DB_PATH         = "questions.enc"
OFFICIAL_BACKUP = "questions.enc.official"
BANKS_DIR       = "banks"
INDEX_PATH      = os.path.join(BANKS_DIR, "index.json")

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

# ── Official bank backup (one-time) ──────────────────────────────────────────
def ensure_official_backup():
    """Backs up questions.enc → questions.enc.official the first time only."""
    if not os.path.exists(OFFICIAL_BACKUP):
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, OFFICIAL_BACKUP)
            print(f"📦 Official bank backed up to {OFFICIAL_BACKUP}")
        else:
            print(f"⚠️  No existing {DB_PATH} to back up. Continuing.")

# ── API validation ────────────────────────────────────────────────────────────
async def validate_api(model: str, api_key: str | None) -> tuple[bool, str]:
    """Makes a cheap single-question test call to validate the key and model."""
    env_key = "OPENAI_API_KEY" if "openai" in model.lower() or model.startswith("gpt") else "GOOGLE_API_KEY"
    if api_key:
        os.environ[env_key] = api_key

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "Reply only with OK."}],
            max_tokens=5,
            timeout=10
        )
        _ = response.choices[0].message.content
        return True, "OK"
    except litellm.AuthenticationError:
        return False, "❌ Invalid API key or unauthorised. Check your key and try again."
    except litellm.NotFoundError:
        return False, f"❌ Model '{model}' not found. Check the model name (e.g. 'gemini/gemini-2.5-flash')."
    except litellm.RateLimitError:
        return False, "⚠️  API key is valid but rate-limited. Wait a moment and retry."
    except Exception as e:
        return False, f"⚠️  Unexpected validation error: {e}"

# ── Async batch generation ────────────────────────────────────────────────────
sem = asyncio.Semaphore(MAX_CONCURRENT)

async def generate_batch(model: str, topics: str, batch_size: int, batch_id: int) -> list[dict]:
    prompt = f"""
    You are an expert historian.
    Generate a batch of exactly {batch_size} unique, factually accurate trivia questions.
    TOPICS: {topics}
    Rules:
    - Vary difficulty from 1 (easy/common knowledge) to 5 (extremely obscure).
    - Exactly one option must be correct.
    - Keep explanations concise but educational.
    - Focus on facts, events, people, places and impacts.
    """
    async with sem:
        for attempt in range(5):
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=QuestionBatch,
                    temperature=0.8,
                )
                batch = QuestionBatch.model_validate_json(response.choices[0].message.content)
                return [q.model_dump() for q in batch.questions]

            except litellm.RateLimitError as e:
                wait = 30 * (attempt + 1)
                print(f"  [batch {batch_id}] ⏳ Rate limit hit. Retrying in {wait}s... ({attempt+1}/5)")
                for remaining in range(wait, 0, -5):
                    print(f"  [batch {batch_id}]    → {remaining}s remaining...", end="\r")
                    await asyncio.sleep(5)
                print()

            except litellm.AuthenticationError:
                print(f"  [batch {batch_id}] ❌ Auth error. API key invalid — aborting.")
                return []   # Signal abort to caller

            except litellm.NotFoundError:
                print(f"  [batch {batch_id}] ❌ Model not found — aborting.")
                return []

            except Exception as e:
                print(f"  [batch {batch_id}] ⚠️  Error (attempt {attempt+1}/5): {type(e).__name__}: {e}")
                await asyncio.sleep(10)

    print(f"  [batch {batch_id}] ❌ Failed after 5 attempts. Skipping batch.")
    return []


async def generate_all(model: str, topics: str, target: int, save_path: str) -> list[dict]:
    """Generates target questions in batches and saves progress incrementally."""
    all_questions: list[dict] = []
    existing_texts: set[str] = set()

    # Resume from prior run if partial save exists
    if os.path.exists(save_path):
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                prior = json.load(f)
            all_questions = prior
            existing_texts = {q["question_text"] for q in prior}
            print(f"  Resuming from {len(all_questions)} previously generated questions.")
        except Exception:
            pass

    needed = target - len(all_questions)
    if needed <= 0:
        print(f"  Already have {len(all_questions)} questions. Nothing more needed.")
        return all_questions

    total_batches = (needed + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"  Generating {needed} questions in {total_batches} batch(es)...")
    tasks = [generate_batch(model, topics, BATCH_SIZE, i + 1) for i in range(total_batches)]

    aborted = False
    for coro in asyncio.as_completed(tasks):
        batch = await coro
        if batch == [] and len(all_questions) < MIN_VIABLE:
            # Empty batch returned on auth/model error — check if we have enough already
            aborted = True

        for q in batch:
            if q["question_text"] not in existing_texts:
                all_questions.append(q)
                existing_texts.add(q["question_text"])

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(all_questions, f, indent=2)
        print(f"  Progress: {len(all_questions)}/{target} questions saved locally...")

        if aborted:
            break

    return all_questions


# ── Encrypt and save the custom bank ─────────────────────────────────────────
def save_custom_bank(questions: list[dict], bank_name: str, topics: str) -> str:
    from database import DATABASE_DECRYPTION_KEY
    import re
    from datetime import datetime
    
    # 1. Generate path
    if not os.path.exists(BANKS_DIR):
        os.makedirs(BANKS_DIR)
        
    slug = re.sub(r'[^a-z0-9]+', '_', bank_name.lower()).strip('_')
    if not slug:
        slug = "custom_bank"
        
    file_path = os.path.join(BANKS_DIR, f"{slug}.enc")
    
    # 2. Encrypt
    cipher = Fernet(DATABASE_DECRYPTION_KEY)
    envelope = {"bank_version": 0, "custom": True, "questions": questions}
    encrypted = cipher.encrypt(json.dumps(envelope).encode("utf-8"))
    with open(file_path, "wb") as f:
        f.write(encrypted)
        
    # 3. Update index.json
    from database import get_active_bank_info, _ensure_banks_index
    _ensure_banks_index()
    
    try:
        with open(INDEX_PATH, "r") as f:
            index_data = json.load(f)
    except Exception:
        index_data = {"banks": [], "active_bank_id": "official"}
    
    # Check if we are updating an existing custom bank
    bank_entry = {
        "id": slug,
        "name": bank_name,
        "path": file_path.replace("\\", "/"),
        "question_count": len(questions),
        "bank_version": 0,
        "is_official": False,
        "topics": topics,
        "created_at": datetime.now().strftime("%Y-%m-%d")
    }
    
    existing_idx = next((i for i, b in enumerate(index_data["banks"]) if b["id"] == slug), None)
    if existing_idx is not None:
        index_data["banks"][existing_idx] = bank_entry
    else:
        index_data["banks"].append(bank_entry)
        
    with open(INDEX_PATH, "w") as f:
        json.dump(index_data, f, indent=2)
        
    return file_path


# ── Interactive wizard helpers ────────────────────────────────────────────────
def prompt(text: str, default: str = "") -> str:
    val = input(f"{text}" + (f" [{default}]" if default else "") + ": ").strip()
    return val if val else default


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(
        description="Create a custom question bank for WWQ."
    )
    parser.add_argument("--count",   type=int,   default=None, help="Number of questions (max 10,000)")
    parser.add_argument("--topics",  type=str,   default=None, help='Topics e.g. "Cold War, Korean War"')
    parser.add_argument("--model",   type=str,   default=None, help="LLM model (e.g. gemini/gemini-2.5-flash)")
    parser.add_argument("--api-key", type=str,   default=None, dest="api_key", help="API key (optional if set in .env)")
    args = parser.parse_args()

    print("=" * 60)
    print("  🏛️  WWQ Custom Question Bank Creator")
    print("=" * 60)
    print("  💡 Recommended models for efficiency:")
    print("     gemini/gemini-2.5-flash  (fast, free tier available)")
    print("     openai/gpt-4o-mini       (cheap, very capable)")
    print("     ollama/qwen2.5:0.5b      (fully local, no key needed)\n")

    # Interactive wizard if flags not fully supplied
    bank_name = prompt("  Bank Name", "My Custom Bank")
    count  = args.count  or int(prompt("  How many questions? (max 10,000)", "500"))
    count  = min(count, MAX_QUESTIONS)
    topics = args.topics or prompt("  Topics (comma-separated)", "WW1 and WW2 History")
    model  = args.model  or prompt("  LLM model", "gemini/gemini-2.5-flash")
    api_key = args.api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY") or \
              prompt("  API key (or press Enter to use .env value)", "")
              
    import re
    slug = re.sub(r'[^a-z0-9]+', '_', bank_name.lower()).strip('_')
    if not slug:
        slug = "custom_bank"
    custom_raw_path = os.path.join(BANKS_DIR, f"{slug}_raw_progress.json")
    if not os.path.exists(BANKS_DIR):
        os.makedirs(BANKS_DIR)

    print(f"\n  ℹ  Generating {count} questions about: {topics}")
    print(f"  ℹ  Using model: {model}")
    print(f"  ℹ  Will map to: banks/{slug}.enc")
    print()

    # Validate API key and model first
    print("🔑 Validating API key and model...")
    ok, msg = await validate_api(model, api_key)
    if not ok:
        print(f"\n{msg}")
        print(f"\n   Your official bank is preserved at {OFFICIAL_BACKUP if os.path.exists(OFFICIAL_BACKUP) else DB_PATH}")
        print("   Restore it via: Settings → Manage Bank → Restore Official")
        sys.exit(1)
    print("  ✅ API key and model validated.\n")

    # Backup official bank (first-time only)
    ensure_official_backup()

    # Generate questions
    print(f"🤖 Generating {count} questions...\n")
    questions = await generate_all(model, topics, count, custom_raw_path)

    if len(questions) < MIN_VIABLE:
        print(f"\n❌ Seeding failed: only {len(questions)} questions generated (minimum {MIN_VIABLE} required).")
        if os.path.exists(custom_raw_path):
            os.remove(custom_raw_path)
        sys.exit(1)

    # Save custom bank
    saved_path = save_custom_bank(questions, bank_name, topics)
    if os.path.exists(custom_raw_path):
        os.remove(custom_raw_path)   # Clean up temp file

    print(f"\n✅ Custom bank '{bank_name}' ({len(questions)} questions) saved to {saved_path}")
    print("📦 Note: The official bank remains safely backed up at questions.enc.official")
    print("\n   To play with this bank, start the game and select it via:")
    print("      Settings → Manage Bank → Select Active Bank")
    print("   To share it with friends, send them the .enc file and place it in their banks/ folder.")


if __name__ == "__main__":
    asyncio.run(main())

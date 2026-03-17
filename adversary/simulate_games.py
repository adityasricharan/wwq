"""
adversary/simulate_games.py

Simulates quiz game sessions locally to generate realistic question history
without requiring a human player. The resulting question_history.json provides
higher-quality data for the refresh_db.py replacement policy than manual play alone.

Skill profiles control the probability of answering correctly per difficulty:
  beginner    — new player, struggles on hard questions
  intermediate — casual player, succeeds on most easy/medium
  expert       — seasoned player, even hard questions answered often
  random       — pure 25% chance (stress-tests the distribution)

Usage:
  python adversary/simulate_games.py --sessions 50 --skill intermediate
  python adversary/simulate_games.py --sessions 200 --skill random
  python adversary/simulate_games.py --sessions 100 --skill expert --dry-run
"""
import sys
import os
import random
import argparse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database import LocalKnowledgeBank
import question_history as qh

# ── Skill profiles: correctness probability per difficulty level ─────────────
SKILL_PROFILES = {
    "beginner":     {1: 0.90, 2: 0.70, 3: 0.40, 4: 0.20, 5: 0.05},
    "intermediate": {1: 0.95, 2: 0.85, 3: 0.65, 4: 0.40, 5: 0.20},
    "expert":       {1: 0.99, 2: 0.95, 3: 0.80, 4: 0.65, 5: 0.45},
    "random":       {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25},
}

QUESTIONS_PER_SESSION = 20
MAX_DIFFICULTY = 5


def simulate_session(bank: LocalKnowledgeBank, history: dict, profile: dict) -> dict:
    """
    Simulates a single quiz session.

    Returns a dict with session stats:
      questions_asked, correct, incorrect, difficulties_seen
    """
    session_id = qh.start_new_session(history)
    seen = set()
    stats = {"asked": 0, "correct": 0, "incorrect": 0, "difficulties": []}

    # Simulate adaptive difficulty like the real game
    current_difficulty = random.randint(1, 3)  # Start at a varied point

    for i in range(QUESTIONS_PER_SESSION):
        seed = random.randint(1, 999999)
        q = bank.get_question(
            difficulty=current_difficulty,
            random_seed=seed,
            seen_questions=seen,
            history=history
        )
        if q is None:
            break

        seen.add(q.question_text)
        qh.record_asked(history, q.question_text)
        stats["asked"] += 1
        stats["difficulties"].append(current_difficulty)

        # Simulate answer based on skill profile
        correct_prob = profile.get(current_difficulty, 0.5)
        answered_correctly = random.random() < correct_prob

        if answered_correctly:
            stats["correct"] += 1
            current_difficulty = min(MAX_DIFFICULTY, current_difficulty + 1)
        else:
            stats["incorrect"] += 1
            current_difficulty = max(1, current_difficulty - 1)

    return stats


def print_report(history: dict, total_sessions: int, skill: str, all_stats: list):
    """Prints a summary report of the simulation run."""
    entries = history.get("entries", {})
    total_tracked = len(entries)
    counts = [e.get("global_count", 0) for e in entries.values()]

    eligible_3plus = sum(1 for c in counts if c >= 3)
    eligible_5plus = sum(1 for c in counts if c >= 5)
    top10 = sorted(counts, reverse=True)[:10]

    total_asked = sum(s["asked"] for s in all_stats)
    total_correct = sum(s["correct"] for s in all_stats)
    accuracy = (total_correct / total_asked * 100) if total_asked > 0 else 0

    print("\n" + "=" * 60)
    print(f"  📊 Simulation Report — {total_sessions} sessions  |  skill: {skill}")
    print("=" * 60)
    print(f"  Questions asked total:     {total_asked}")
    print(f"  Simulated accuracy:        {accuracy:.1f}%")
    print(f"  Unique questions touched:  {total_tracked}")
    print(f"  Questions asked ≥3×:       {eligible_3plus}  ({eligible_3plus/max(total_tracked,1)*100:.1f}% of tracked)")
    print(f"  Questions asked ≥5×:       {eligible_5plus}  ({eligible_5plus/max(total_tracked,1)*100:.1f}% of tracked)")
    print(f"  Top 10 ask counts:         {top10}")
    print("=" * 60)
    print(f"\n💡 Refresh recommendation:")
    if eligible_3plus >= 50:
        print(f"   Run:  python refresh_db.py --count {min(eligible_3plus, 200)} --threshold 3")
    elif eligible_3plus > 0:
        print(f"   Run:  python refresh_db.py --count {eligible_3plus} --threshold 3")
    else:
        print("   Bank is fresh — no refresh needed yet.")


def main():
    parser = argparse.ArgumentParser(
        description="Simulate quiz sessions to populate question_history.json for refresh_db.py"
    )
    parser.add_argument("--sessions", type=int, default=50,
                        help="Number of game sessions to simulate (default: 50)")
    parser.add_argument("--skill", choices=list(SKILL_PROFILES.keys()), default="intermediate",
                        help="Simulated player skill profile (default: intermediate)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show simulation results without saving to question_history.json")
    args = parser.parse_args()

    print(f"🎮 Simulating {args.sessions} sessions at skill level: {args.skill}")

    bank = LocalKnowledgeBank()
    if not bank._questions:
        print("❌ questions.enc not found or empty. Cannot simulate.")
        sys.exit(1)

    print(f"   Bank loaded: {len(bank._questions)} questions")

    history = qh.load_history()
    profile = SKILL_PROFILES[args.skill]
    all_stats = []

    for i in range(args.sessions):
        stats = simulate_session(bank, history, profile)
        all_stats.append(stats)
        if (i + 1) % 10 == 0:
            print(f"   Simulated {i+1}/{args.sessions} sessions...")

    print_report(history, args.sessions, args.skill, all_stats)

    if not args.dry_run:
        qh.save_history(history)
        print(f"\n✅ History saved to question_history.json")
        print("   Run  python refresh_db.py --dry-run  to preview replacements.")
    else:
        print("\n[DRY RUN] History not saved.")


if __name__ == "__main__":
    main()

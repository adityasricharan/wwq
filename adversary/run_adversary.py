"""
adversary/run_adversary.py

Main entry point for the Adversarial QA Agent.
Run this manually or let the pre-commit hook invoke it automatically.

Usage:
  python adversary/run_adversary.py          # Full cycle: analyze + test
  python adversary/run_adversary.py --test   # Regression tests only (no LLM)
  python adversary/run_adversary.py --update # LLM analysis only (no tests)
"""
import sys
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADVERSARY_DIR = os.path.dirname(os.path.abspath(__file__))

def run_regression_tests() -> bool:
    """Runs the pytest regression suite. Returns True if all tests pass."""
    print("\n[ADVERSARY] 🧪 Running regression test suite...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", 
         os.path.join(ADVERSARY_DIR, "test_regression.py"),
         "-v", "--tb=short", "--no-header"],
        cwd=ROOT
    )
    return result.returncode == 0

def run_static_checks() -> bool:
    """Runs syntax validation on all watched files. Returns True if clean."""
    sys.path.insert(0, ADVERSARY_DIR)
    from observer import run_syntax_check
    errors = run_syntax_check()
    if errors:
        print("\n[ADVERSARY] ❌ Syntax errors detected:")
        for e in errors:
            print(f"  {e}")
        return False
    print("[ADVERSARY] ✅ Syntax check passed.")
    return True

def run_llm_analysis():
    """Runs the LLM adversary to update the knowledge base."""
    sys.path.insert(0, ADVERSARY_DIR)
    from observer import get_unstaged_diff, summarize_codebase
    from adversary_agent import analyze_diff_and_update, apply_updates
    
    diff = get_unstaged_diff()
    summary = summarize_codebase()
    
    if "(No uncommitted changes detected)" in diff:
        # Fall back to the last commit's diff
        from observer import get_recent_diff
        diff = get_recent_diff(1)
    
    print("[ADVERSARY] 🤖 Consulting the adversarial agent...")
    analysis = analyze_diff_and_update(diff, summary)
    apply_updates(analysis)

def main():
    args = sys.argv[1:]
    test_only = "--test" in args
    update_only = "--update" in args
    
    print("=" * 60)
    print("  🛡️  WWQ Adversarial QA Agent")
    print("=" * 60)
    
    syntax_ok = run_static_checks()
    if not syntax_ok:
        print("\n[ADVERSARY] 🚫 Aborting: fix syntax errors before proceeding.")
        sys.exit(1)

    if not test_only:
        run_llm_analysis()

    if not update_only:
        tests_ok = run_regression_tests()
        if not tests_ok:
            print("\n[ADVERSARY] 🚫 REGRESSION DETECTED — some tests failed.")
            print("[ADVERSARY] Fix the failing tests before committing.")
            sys.exit(1)
        else:
            print("\n[ADVERSARY] ✅ All regression tests passed. Safe to commit!")

if __name__ == "__main__":
    main()

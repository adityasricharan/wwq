"""
Paranoia Checker — WWQ v2.5.0
Automated invariant checker for the trivia quiz.

Runs tests on structural and logical guarantees of the application without
requiring a human or an API key.

Usage:
  python paranoia_checker.py
  python paranoia_checker.py --fast  (skips network checks)
"""

import os
import sys
import json
import argparse
import time
import importlib
import warnings
from typing import Callable, Any

# Suppress cryptography warnings if any
warnings.filterwarnings("ignore", category=UserWarning, module="cryptography")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Test Runner ───────────────────────────────────────────────────────────
class TestRunner:
    def __init__(self, verbose: bool = False, fast: bool = False):
        self.verbose = verbose
        self.fast = fast
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = []

    def run(self, name: str, func: Callable, tags: list[str] = None):
        if tags is None: tags = []
        if self.fast and "network" in tags:
            print(f"⚠️  SKIP  {name} (network check)")
            self.skipped += 1
            return

        try:
            func()
            print(f"✅ PASS  {name}")
            self.passed += 1
        except AssertionError as e:
            print(f"❌ FAIL  {name}")
            self.errors.append((name, str(e)))
            self.failed += 1
        except Exception as e:
            print(f"💥 ERROR {name}")
            self.errors.append((name, f"Exception: {e}"))
            self.failed += 1

    def report(self):
        print(f"══════════════════════════════════")
        print(f"{self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        if self.failed > 0:
            print("\nFailures:")
            for name, err in self.errors:
                print(f"  - {name}: {err}")
            return False
        return True


# ── The Checks ────────────────────────────────────────────────────────────

def check_import_sanity():
    # Only block built-in structure. Externals like litellm might fail if missing.
    modules = ["main", "agents", "database", "question_history", "state", "seed_bank", "version"]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            if "litellm" not in str(e): # allow litellm import error
                raise AssertionError(f"Failed to import {mod}: {e}")

def check_db_integrity():
    from database import active_bank
    count = len(active_bank._questions)
    assert count > 0, f"Database loaded 0 questions. Expected >0."
    # Verify standard fields exist on the first question
    q0 = active_bank._questions[0]
    assert hasattr(q0, "question_text"), "Question missing question_text"
    assert len(q0.options) == 4, "Question does not have exactly 4 options"
    assert q0.correct_answer in q0.options, "Correct answer not in options"

def check_seed_roundtrip():
    from state import generate_seed, decode_seed
    
    # Check Adaptive mode seed (hidden, no VS format)
    s1 = generate_seed("Cold War", bank_version=1)
    # decode_seed returns a tuple: (seed_hash, topic, version)
    parsed = decode_seed(s1)
    
    # Depending on format (legacy vs current), it could return 2 or 3 items
    if len(parsed) == 3:
        h1, topic1, v1 = parsed
    else:
        h1, topic1 = parsed
        
    assert h1 != 0, f"Failed to roundtrip standard seed: {s1}"
    assert topic1 == "Cold War", f"Failed to roundtrip topic: {topic1}"

    # Check VS mode prefixing
    assert s1.startswith("VS:"), "Seed generation did not prepend VS: for bank_version > 0"
    
def check_vs_determinism():
    import sys
    # Add a mock litellm module for CI environments
    if 'litellm' not in sys.modules:
        import types
        sys.modules['litellm'] = types.ModuleType('litellm')
        sys.modules['litellm.types'] = types.ModuleType('litellm.types')
        sys.modules['litellm.types.utils'] = types.ModuleType('litellm.types.utils')

    from main import draw_vs_questions
    from database import active_bank
    
    seed_str = "VS:A1B2C3@v1"
    
    # Draw 10 questions twice, ensure identical
    list_a = draw_vs_questions(active_bank, seed_str, 10)
    list_b = draw_vs_questions(active_bank, seed_str, 10)
    
    assert len(list_a) == 10, "Did not draw requested number of questions"
    assert list_a == list_b, "VS mode draw is non-deterministic!"
    
    # Different seed should yield different results (most of the time)
    seed_str_2 = "VS:Z9Y8X7@v1"
    list_c = draw_vs_questions(active_bank, seed_str_2, 10)
    assert list_a != list_c, "Different VS seeds yielded identical question lists"

def check_history_integrity():
    import question_history as qh
    import tempfile
    
    with tempfile.TemporaryDirectory() as d:
        test_file = os.path.join(d, "history.json")
        
        # Override the HISTORY_FILE environment temporally
        original_file = qh.HISTORY_FILE
        qh.HISTORY_FILE = test_file
        
        # Mock load/save
        hist = qh.load_history()
        qh.start_new_session(hist) # Just mutated in memory
        hist["total_sessions"] = 5
        qh.save_history(hist)
        
        hist_loaded = qh.load_history()
        assert hist_loaded["total_sessions"] == 5, "Saved history did not match loaded history"
        
        # Restore
        qh.HISTORY_FILE = original_file

def check_bank_index():
    from database import INDEX_PATH, _ensure_banks_index
    _ensure_banks_index()
    assert os.path.exists(INDEX_PATH), "bank/index.json was not created"
    
    with open(INDEX_PATH, "r") as f:
        data = json.load(f)
        
    assert "banks" in data, "No 'banks' key in index"
    assert "active_bank_id" in data, "No 'active_bank_id' in index"
    
    official_found = False
    for b in data["banks"]:
        if b["id"] == "official":
            official_found = True
            assert b["is_official"] is True
    assert official_found, "Official bank missing from index"

def check_version_format():
    import version
    v = version.VERSION
    parts = v.split(".")
    assert len(parts) >= 3, f"VERSION string {v} not valid semver (e.g. 2.5.0)"

def check_ota_reachability():
    import urllib.request
    from main import OTA_URL
    try:
        req = urllib.request.Request(OTA_URL, method="HEAD")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        raise AssertionError(f"OTA endpoint {OTA_URL} unreachable: {e}")

# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Skip network checks")
    parser.add_argument("--verbose", action="store_true", help="Show error tracebacks")
    args = parser.parse_args()

    print(f"🔍 Paranoia Checker\n══════════════════════════════════")
    
    runner = TestRunner(verbose=args.verbose, fast=args.fast)
    
    runner.run("Import sanity", check_import_sanity)
    runner.run("DB integrity", check_db_integrity)
    runner.run("Seed roundtrip", check_seed_roundtrip)
    runner.run("VS mode determinism", check_vs_determinism)
    runner.run("History integrity", check_history_integrity)
    runner.run("Bank index valid", check_bank_index)
    runner.run("Version format", check_version_format)
    runner.run("OTA reachability", check_ota_reachability, tags=["network"])
    
    success = runner.report()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

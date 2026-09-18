"""
One-by-One Difficulty Test Runner for MCP Filesystem Chatbot.

Runs each of the 20 test cases individually across Easy, Medium, Hard, and Extreme tiers,
displaying full debugging trace, tool calls made, model replies, and assertion checks.

Usage:
    python tests/run_difficulty_tests.py
    python tests/run_difficulty_tests.py --category easy
    python tests/run_difficulty_tests.py --category medium
    python tests/run_difficulty_tests.py --category hard
    python tests/run_difficulty_tests.py --category extreme
    python tests/run_difficulty_tests.py --test test_easy_01_create_single_folder
"""

import argparse
import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from tests.test_categories import (
    TestEasyCategory,
    TestMediumCategory,
    TestHardCategory,
    TestExtremeCategory,
)

CATEGORIES = {
    "easy": [
        ("EASY-01: Create Folder", TestEasyCategory, "test_easy_01_create_single_folder"),
        ("EASY-02: Create File", TestEasyCategory, "test_easy_02_create_text_file"),
        ("EASY-03: Read File", TestEasyCategory, "test_easy_03_read_file_content"),
        ("EASY-04: List Workspace", TestEasyCategory, "test_easy_04_list_workspace_root"),
        ("EASY-05: Update File", TestEasyCategory, "test_easy_05_update_file_overwrite"),
    ],
    "medium": [
        ("MED-01: Nested Path Creation", TestMediumCategory, "test_med_01_nested_path_creation"),
        ("MED-02: Terse Note Notation", TestMediumCategory, "test_med_02_terse_note_format"),
        ("MED-03: Append Content", TestMediumCategory, "test_med_03_append_content"),
        ("MED-04: Delete Confirmation", TestMediumCategory, "test_med_04_delete_confirmation_flow"),
        ("MED-05: Compound Action", TestMediumCategory, "test_med_05_compound_action"),
    ],
    "hard": [
        ("HARD-01: Sandbox Traversal Defense", TestHardCategory, "test_hard_01_sandbox_directory_traversal"),
        ("HARD-02: Existing File Handling", TestHardCategory, "test_hard_02_create_existing_file_handling"),
        ("HARD-03: Recursive Directory Deletion", TestHardCategory, "test_hard_03_recursive_folder_deletion"),
        ("HARD-04: Non-existent File Handling", TestHardCategory, "test_hard_04_nonexistent_file_handling"),
        ("HARD-05: Terse Shorthand Command", TestHardCategory, "test_hard_05_terse_shorthand_command"),
    ],
    "extreme": [
        ("EXT-01: Vague Destructive Refusal", TestExtremeCategory, "test_ext_01_vague_destructive_refusal"),
        ("EXT-02: Multi-turn Pronoun Followup", TestExtremeCategory, "test_ext_02_contextual_pronoun_followup"),
        ("EXT-03: Special Characters in Filename", TestExtremeCategory, "test_ext_03_special_characters_filename"),
        ("EXT-04: Complex Project Scaffold", TestExtremeCategory, "test_ext_04_complex_scaffold"),
        ("EXT-05: Disguised Traversal Attack", TestExtremeCategory, "test_ext_05_disguised_traversal_attack"),
    ],
}


async def run_single_test(label: str, test_class, method_name: str) -> bool:
    print(f"\n{'='*70}")
    print(f"▶ RUNNING: [{label}] ({method_name})")
    print(f"{'='*70}")

    instance = test_class()
    instance.setUp()
    start_time = time.time()
    try:
        method = getattr(instance, method_name)
        if asyncio.iscoroutinefunction(method):
            await method()
        else:
            method()
        duration = time.time() - start_time
        print(f"✅ PASSED: [{label}] in {duration:.2f}s")
        return True
    except Exception as exc:
        duration = time.time() - start_time
        print(f"❌ FAILED: [{label}] in {duration:.2f}s")
        print(f"Error: {exc}")
        traceback.print_exc()
        return False
    finally:
        try:
            instance.tearDown()
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser(description="Run 4-tier difficulty tests for MCP Filesystem.")
    parser.add_argument("--category", choices=["easy", "medium", "hard", "extreme", "all"], default="all")
    parser.add_argument("--test", type=str, default=None, help="Run a specific test method name")
    args = parser.parse_args()

    tests_to_run = []
    if args.test:
        found = False
        for cat, items in CATEGORIES.items():
            for label, cls, m in items:
                if m == args.test:
                    tests_to_run.append((cat, label, cls, m))
                    found = True
                    break
        if not found:
            print(f"Error: Test '{args.test}' not found.")
            sys.exit(1)
    else:
        cats = [args.category] if args.category != "all" else ["easy", "medium", "hard", "extreme"]
        for cat in cats:
            for label, cls, m in CATEGORIES[cat]:
                tests_to_run.append((cat, label, cls, m))

    print(f"\n========================================================")
    print(f"   MCP FILESYSTEM CHATBOT - DIFFICULTY TEST RUNNER")
    print(f"   Total Test Cases Selected: {len(tests_to_run)}")
    print(f"========================================================")

    results = []
    current_cat = None
    for cat, label, cls, m in tests_to_run:
        if cat != current_cat:
            current_cat = cat
            print(f"\n\n########################################################")
            print(f"   CATEGORY: {cat.upper()}")
            print(f"########################################################")

        passed = await run_single_test(label, cls, m)
        results.append((cat, label, m, passed))

    # Summary Report
    print(f"\n\n{'='*70}")
    print(f"                TEST EXECUTION SUMMARY REPORT")
    print(f"{'='*70}")
    passed_count = sum(1 for _, _, _, p in results if p)
    total_count = len(results)

    for cat in ["easy", "medium", "hard", "extreme"]:
        cat_results = [r for r in results if r[0] == cat]
        if not cat_results:
            continue
        cat_passed = sum(1 for _, _, _, p in cat_results if p)
        print(f"\n[{cat.upper()}] ({cat_passed}/{len(cat_results)} passed):")
        for _, label, m, p in cat_results:
            status = "✅ PASS" if p else "❌ FAIL"
            print(f"  {status} - {label} ({m})")

    print(f"\n{'-'*70}")
    print(f"OVERALL RESULT: {passed_count}/{total_count} passed ({passed_count/total_count*100:.1f}%)")
    print(f"{'='*70}\n")

    if passed_count != total_count:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

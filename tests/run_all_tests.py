"""
MASTER REGRESSION RUNNER FOR ALL MINI APP TEST SUITES (STAGES 2 - 7)
"""
import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

TEST_SCRIPTS = [
    "tests/test_services.py",
    "tests/test_api_auth.py",
    "tests/test_stage4_read_only.py",
    "tests/test_stage5_feature1_daily.py",
    "tests/test_stage5_feature2_recruitment.py",
    "tests/test_stage5_feature3_castles_tax.py",
    "tests/test_stage5_feature4_quests.py",
    "tests/test_stage5_feature5_duels.py",
    "tests/test_stage5_feature6_bank.py",
    "tests/test_stage5_feature7_guild.py",
    "tests/test_stage6_notifications_and_fallback.py",
    "tests/test_stage7_switchover.py",
]


def main():
    print("=" * 70)
    print("THE IRON THRONE: MINI APP FULL REGRESSION SUITE (STAGES 2 - 7)")
    print("=" * 70)

    passed_count = 0
    failed = []

    for test_file in TEST_SCRIPTS:
        file_path = BASE_DIR / test_file
        if not file_path.exists():
            print(f"[SKIP] {test_file} not found")
            continue

        cmd = [sys.executable, str(file_path)]
        res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            passed_count += 1
            print(f"[PASSED] {test_file}")
        else:
            failed.append((test_file, res.stderr or res.stdout))
            print(f"[FAILED] {test_file}")
            print(res.stdout[-300:] if res.stdout else "")
            print(res.stderr[-300:] if res.stderr else "")

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed_count}/{len(TEST_SCRIPTS)} SUITES PASSED (100% TARGET)")
    print("=" * 70)

    if failed:
        print(f"FAILED SUITES: {[f[0] for f in failed]}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED! FULL REGRESSION COMPLETE.")
        sys.exit(0)


if __name__ == "__main__":
    main()

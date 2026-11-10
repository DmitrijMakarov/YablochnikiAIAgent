"""Acceptance checks for the isolated T8 SYNTHETIC TEST DATA fixture."""

import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/retention-expected"
INPUTS = ROOT / "cases/retention-demo/inputs"
REFERENCE = runpy.run_path(str(FIXTURE / "calculate.py"))


class RetentionFixtureTest(unittest.TestCase):
    def test_generation_reproduces_all_csv_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            regenerated = Path(temporary)
            subprocess.run([sys.executable, str(FIXTURE / "generate.py"), str(regenerated)],
                           check=True)
            for name in ("signups.csv", "events.csv", "coverage.csv"):
                with self.subTest(name=name):
                    self.assertEqual((regenerated / name).read_bytes(), (INPUTS / name).read_bytes())

    def test_reference_matches_frozen_results(self):
        result = subprocess.run([sys.executable, str(FIXTURE / "calculate.py"), str(INPUTS)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout),
                         json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8")))

    def test_partially_mature_and_unobserved_cohorts_do_not_get_headline_rates(self):
        target = date(2026, 8, 12)
        users = [
            {"user_id": "observed", "signup_date": date(2026, 8, 5), "platform": "ios"},
            {"user_id": "too_recent", "signup_date": date(2026, 8, 6), "platform": "ios"},
        ]
        activity = {("observed", target): {"task_completed"}}
        coverage = {(target, "ios"): "complete"}
        score = REFERENCE["retention"]

        partial = score(users, activity, coverage, target, 7)
        self.assertEqual((partial["right_censored"], partial["eligible"]), (1, 1))
        self.assertEqual(partial["eligible_task_rate"], 1)
        self.assertIsNone(partial["headline_task_rate"])

        immature = score(users, activity, coverage, target, 30)
        self.assertEqual((immature["right_censored"], immature["eligible"]), (2, 0))
        self.assertIsNone(immature["eligible_task_rate"])
        self.assertIsNone(immature["headline_task_rate"])

    def test_denominator_uses_registered_users_with_complete_target_day(self):
        signup, target = date(2026, 7, 15), date(2026, 7, 22)
        users = [
            {"user_id": name, "signup_date": signup, "platform": platform}
            for name, platform in (("core", "ios"), ("opened", "ios"),
                                   ("silent", "ios"), ("partial", "android"))
        ]
        activity = {
            ("core", target): {"task_completed", "app_open"},
            ("opened", target): {"app_open", "background_sync"},
            ("silent", date(2026, 7, 21)): {"task_completed"},
            ("partial", target): {"task_completed"},
        }
        coverage = {(target, "ios"): "complete", (target, "android"): "partial"}
        result = REFERENCE["retention"](users, activity, coverage, target, 7)

        self.assertEqual((result["registered"], result["incomplete_telemetry"]), (4, 1))
        self.assertEqual((result["task_completed"], result["app_open"], result["eligible"]),
                         (1, 2, 3))
        self.assertEqual(result["headline_task_rate"], 0.333333)


if __name__ == "__main__":
    unittest.main()

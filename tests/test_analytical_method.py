"""Independent numerical teaching cases, not an execution of the agent's skills.

All inputs are invented here. No case, T8 reference or agent calculation is read.
Fractions keep the decomposition exact; expected totals are hand-checkable.
"""

import unittest
from collections import Counter
from fractions import Fraction as F
from statistics import NormalDist


def decompose(before, after):
    """Base-period-rate decomposition on common, nonempty segment support."""
    if before.keys() != after.keys() or any(n <= 0 for _, n in (*before.values(), *after.values())):
        raise ValueError("common nonempty support required")
    totals = [sum(n for _, n in period.values()) for period in (before, after)]
    rates, weights = [], []
    for period, total in zip((before, after), totals):
        rates.append({s: F(k, n) for s, (k, n) in period.items()})
        weights.append({s: F(n, total) for s, (_, n) in period.items()})
    composition = sum((weights[1][s] - weights[0][s]) * rates[0][s] for s in before)
    within = sum(weights[1][s] * (rates[1][s] - rates[0][s]) for s in before)
    overall = F(sum(k for k, _ in after.values()), totals[1]) - F(
        sum(k for k, _ in before.values()), totals[0])
    return overall, composition, within


def observed_rate(rows, event_names, as_of):
    """Rows: (window_end, coverage, event_names); all windows start at day zero.

    Each row is one registered account; dates are relative days. Immaturity takes
    precedence over telemetry exclusions. Events are already inside the window.
    """
    excluded = Counter()
    numerator = denominator = 0
    for end, coverage, events in rows:
        if end > as_of:
            excluded["immature"] += 1
        elif coverage != "complete":
            excluded["incomplete"] += 1
        else:
            denominator += 1
            numerator += bool(set(events) & event_names)
    return numerator, denominator, F(numerator, denominator) if denominator else None, excluded


class AnalyticalMethodTest(unittest.TestCase):
    def test_composition_shift_without_within_segment_decline(self):
        # Both segment rates stay at 80% and 20%; only their sizes change.
        result = decompose({"A": (32, 40), "B": (2, 10)},
                           {"A": (8, 10), "B": (8, 40)})
        self.assertEqual(result, (F(-36, 100), F(-36, 100), 0))
        self.assertEqual(result[0], result[1] + result[2])

    def test_within_segment_decline_without_composition_shift(self):
        result = decompose({"A": (24, 40), "B": (4, 10)},
                           {"A": (20, 40), "B": (3, 10)})
        self.assertEqual(result, (F(-1, 10), 0, F(-1, 10)))
        self.assertEqual(result[0], result[1] + result[2])

    def test_unknown_segment_is_retained_and_absent_support_is_not_zero(self):
        before = {"known": (9, 10), "unknown": (1, 10)}
        after = {"known": (9, 10), "unknown": (0, 10)}
        self.assertEqual(decompose(before, after), (F(-1, 20), 0, F(-1, 20)))
        for unsupported in ({"known": (9, 10)}, {"known": (9, 10), "unknown": (0, 0)}):
            with self.subTest(after=unsupported), self.assertRaises(ValueError):
                decompose(before, unsupported)

    def test_immaturity_and_incomplete_telemetry_are_separate(self):
        rows = [(4, "complete", ["publish", "publish"]), (4, "complete", []),
                (5, "partial", ["publish"]), (9, "partial", [])]
        k, n, rate, excluded = observed_rate(rows, {"publish"}, as_of=6)
        self.assertEqual((k, n, rate), (1, 2, F(1, 2)))
        self.assertEqual(excluded, {"incomplete": 1, "immature": 1})
        self.assertEqual(n + sum(excluded.values()), len(rows))
        self.assertIsNone(observed_rate(rows, {"publish"}, as_of=3)[2])
        # The observed subgroup's 1/2 is not a full-cohort rate of 1/4.

    def test_undefined_activation_needs_event_sensitivity_and_unknown_group(self):
        # An undocumented legacy "active" flag cannot choose between definitions.
        rows = [(2, "complete", ["draft"]), (2, "complete", ["publish"]),
                (2, "complete", ["draft", "publish"]), (2, "complete", []),
                (2, "partial", []), (2, "unknown", [])]
        draft = observed_rate(rows, {"draft"}, 3)
        published = observed_rate(rows, {"publish"}, 3)
        either = observed_rate(rows, {"draft", "publish"}, 3)
        self.assertEqual((draft[:3], published[:3], either[:3]),
                         ((2, 4, F(1, 2)), (2, 4, F(1, 2)), (3, 4, F(3, 4))))
        # Equal aggregate rates hide different memberships: draft-only / publish-only.
        discordant = sum(("draft" in events) != ("publish" in events)
                         for _, coverage, events in rows if coverage == "complete")
        self.assertEqual(discordant, 2)
        self.assertEqual(either[3]["incomplete"], 2)
        self.assertEqual((either[0], either[1] - either[0], sum(either[3].values())),
                         (3, 1, 2))  # active, inactive, unknown; partial silence is unknown

    def test_endpoints_do_not_establish_period_robustness(self):
        # Same endpoint rates, but two prespecified nonoverlapping blocks differ.
        cohorts = [(12, 40), (20, 40), (16, 40), (8, 40), (4, 40), (12, 40)]
        self.assertEqual(F(*cohorts[0]), F(*cohorts[-1]))
        early = F(sum(k for k, _ in cohorts[:3]), sum(n for _, n in cohorts[:3]))
        late = F(sum(k for k, _ in cohorts[3:]), sum(n for _, n in cohorts[3:]))
        self.assertEqual((early, late, late - early), (F(2, 5), F(1, 5), F(-1, 5)))

    def test_null_power_is_not_probability_of_full_success(self):
        # Illustrative fixed-SE normal model, not a universal sample-size formula.
        # True effect equals a required point-estimate threshold of 0.12.
        sampling = NormalDist(mu=0.12, sigma=0.04)
        critical = NormalDist().inv_cdf(0.975) * 0.04
        null_power = 1 - sampling.cdf(critical) + sampling.cdf(-critical)
        passes_primary_rule = 1 - sampling.cdf(max(critical, 0.12))
        self.assertGreater(null_power, 0.8)
        self.assertEqual(passes_primary_rule, 0.5)
        # Additional conjunctive guardrails cannot increase this probability.

    def test_zero_guardrail_events_can_still_be_inconclusive(self):
        # Exact one-sided 95% upper binomial bound for zero independent events.
        # This is an absolute-risk guardrail, not a two-arm noninferiority test.
        upper_small = 1 - 0.05 ** (1 / 100)
        upper_large = 1 - 0.05 ** (1 / 400)
        allowed_risk = 0.01
        self.assertGreater(upper_small, allowed_risk)
        self.assertLess(upper_large, allowed_risk)


if __name__ == "__main__":
    unittest.main()

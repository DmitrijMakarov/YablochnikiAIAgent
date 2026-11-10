"""Independent reference calculation for SYNTHETIC TEST DATA."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

LABEL = "SYNTHETIC TEST DATA"
BASELINE = ("2026-06-01", "2026-06-08", "2026-06-15")
RECENT = ("2026-06-22", "2026-06-29", "2026-07-06")


def read_csv(directory, name):
    with (directory / name).open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["data_label"] != LABEL:
                raise ValueError(f"Missing synthetic label in {name}")
            yield row


def rate(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def retention(users, activity, coverage, cutoff, age):
    """Count exact UTC return days for registered users with complete target-day telemetry."""
    counts = dict(registered=len(users), right_censored=0, incomplete_telemetry=0,
                  eligible=0, task_completed=0, app_open=0)
    for user in users:
        target = user["signup_date"] + timedelta(days=age)
        if target > cutoff:
            counts["right_censored"] += 1
            continue
        if coverage.get((target, user["platform"])) != "complete":
            counts["incomplete_telemetry"] += 1
            continue
        counts["eligible"] += 1
        events = activity.get((user["user_id"], target), ())
        counts["task_completed"] += "task_completed" in events
        counts["app_open"] += "app_open" in events

    counts["eligible_task_rate"] = rate(counts["task_completed"], counts["eligible"])
    counts["eligible_open_rate"] = rate(counts["app_open"], counts["eligible"])
    # Suppress headline rates for calendar-immature weekly cohorts.
    counts["headline_task_rate"] = (
        None if counts["right_censored"] else counts["eligible_task_rate"]
    )
    return counts


def activation(user, activity, coverage):
    """Classify early creation only if both calendar days are observed."""
    days = [user["signup_date"] + timedelta(days=offset) for offset in (0, 1)]
    if any(coverage.get((day, user["platform"])) != "complete" for day in days):
        return "unobservable"
    if any("task_created" in activity.get((user["user_id"], day), ()) for day in days):
        return "created"
    return "not_created"


def group(users, key):
    groups = defaultdict(list)
    for user in users:
        groups[key(user)].append(user)
    return dict(sorted(groups.items()))


def standardize(early, late):
    """Compare rates using the baseline distribution of eligible users by channel."""
    early_n = sum(s["eligible"] for s in early.values())
    late_n = sum(s["eligible"] for s in late.values())
    early_rate = sum(s["task_completed"] for s in early.values()) / early_n
    late_rate = sum(s["task_completed"] for s in late.values()) / late_n
    fixed_mix_rate = sum(
        (early[channel]["eligible"] / early_n)
        * (late[channel]["task_completed"] / late[channel]["eligible"])
        for channel in early
    )
    return {
        "baseline_rate": round(early_rate, 6),
        "recent_rate": round(late_rate, 6),
        "recent_rate_baseline_mix": round(fixed_mix_rate, 6),
        "total_change_pp": round(100 * (late_rate - early_rate), 4),
        "within_channel_pp": round(100 * (fixed_mix_rate - early_rate), 4),
        "mix_pp": round(100 * (late_rate - fixed_mix_rate), 4),
    }


def calculate(directory):
    users = list(read_csv(directory, "signups.csv"))
    users_by_id = {}
    for user in users:
        user["signup_date"] = date.fromisoformat(user["signup_date"])
        user_id = user["user_id"]
        if user_id in users_by_id:
            raise ValueError(f"Duplicate registration for {user_id}")
        users_by_id[user_id] = user

    coverage = {
        (date.fromisoformat(row["event_date"]), row["platform"]): row["status"]
        for row in read_csv(directory, "coverage.csv")
    }
    cutoff = max(day for day, _ in coverage)
    activity = defaultdict(set)
    seen = {}
    duplicate_rows = 0
    for event in read_csv(directory, "events.csv"):
        day = date.fromisoformat(event["event_date"])
        user_id = event["user_id"]
        event_key = (user_id, day, event["event_type"])
        if event["event_id"] in seen:
            if seen[event["event_id"]] != event_key:
                raise ValueError(f"Conflicting rows for {event['event_id']}")
            duplicate_rows += 1
            continue
        user = users_by_id[user_id]
        if not user["signup_date"] <= day <= cutoff:
            raise ValueError(f"Out-of-range date for {event['event_id']}")
        seen[event["event_id"]] = event_key
        activity[user_id, day].add(event["event_type"])

    for user in users:
        user["channel"] = user["channel"] or "unknown"
        user["activation"] = activation(user, activity, coverage)

    def metrics(cohort):
        return {
            f"d{age}": retention(cohort, activity, coverage, cutoff, age)
            for age in (7, 30)
        }

    def breakdown(cohort, field):
        result = {}
        for value, members in group(cohort, lambda u: u[field]).items():
            activated = sum(u["activation"] == "created" for u in members)
            known = sum(u["activation"] != "unobservable" for u in members)
            result[value] = {
                "activation": {
                    "created": activated, "observable": known, "rate": rate(activated, known),
                },
                **metrics(members),
            }
        return result

    periods = {}
    for name, weeks in (("baseline", BASELINE), ("recent", RECENT)):
        members = [user for user in users if user["cohort_week"] in weeks]
        periods[name] = {
            "weeks": weeks,
            "overall": metrics(members),
            "by_channel": breakdown(members, "channel"),
            "by_platform": breakdown(members, "platform"),
            "by_activation": {
                value: metrics(activated)
                for value, activated in group(members, lambda u: u["activation"]).items()
            },
        }

    return {
        "data_label": LABEL,
        "cutoff_inclusive_utc": cutoff.isoformat(),
        "quality": {
            "registrations": len(users),
            "distinct_event_ids": len(seen),
            "duplicate_event_rows": duplicate_rows,
            "missing_channel": sum(u["channel"] == "unknown" for u in users),
            "missing_stated_goal": sum(not u["stated_goal"] for u in users),
            "missing_legacy_setup_flag": sum(not u["legacy_setup_flag"] for u in users),
            "early_activation_unobservable": Counter(u["activation"] for u in users)["unobservable"],
        },
        "by_week": {
            week: metrics(cohort)
            for week, cohort in group(users, lambda u: u["cohort_week"]).items()
        },
        "matched_periods": periods,
        "channel_standardization": {
            day: standardize(
                {k: v[day] for k, v in periods["baseline"]["by_channel"].items()},
                {k: v[day] for k, v in periods["recent"]["by_channel"].items()},
            )
            for day in ("d7", "d30")
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    print(json.dumps(calculate(args.inputs), indent=2, sort_keys=True))

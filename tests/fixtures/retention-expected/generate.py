"""Generate SYNTHETIC TEST DATA from generation.json and the model below."""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_csv(directory, name, fields, rows, label):
    with (directory / name).open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("data_label", *fields))
        writer.writerows((label, *row) for row in rows)


def generate(directory, params):
    rng = random.Random(params["seed"])
    draw = rng.random
    first = date.fromisoformat(params["first_cohort"])
    end = date.fromisoformat(params["observation_end"])
    partial = {
        (date.fromisoformat(day), platform)
        for platform, days in params["partial_days"].items()
        for day in days
    }
    signups, events, coverage = [], [], []
    for offset in range((end - first).days + 1):
        day = first + timedelta(days=offset)
        for platform in ("android", "ios"):
            status = "partial" if (day, platform) in partial else "complete"
            coverage.append((day, platform, status))

    def emit(user, day, platform, event):
        if (day, platform) in partial and draw() >= params["partial_capture_probability"]:
            return
        # Row-derived IDs remain unique even when the preceding message was duplicated.
        row = (f"e{len(events) + 1:07d}", user, day, event)
        events.append(row)
        if draw() < params["duplicate_probability"]:
            events.append(row)

    for week, volume in enumerate(params["signups_per_week"]):
        cohort = first + timedelta(weeks=week)
        recent = week >= params["recent_from_week_index"]
        paid = params["paid_share_by_week"][week]
        referral = params["referral_share_by_week"][week]
        for _ in range(volume):
            user = f"u{len(signups) + 1:05d}"
            signup = cohort + timedelta(days=int(draw() * 7))
            pick = draw()
            organic_channel, paid_channel, referral_channel = params["channels"]
            channel = organic_channel
            if pick < paid:
                channel = paid_channel
            elif pick < paid + referral:
                channel = referral_channel
            routine = draw() < params["routine_probability"][channel]
            android = draw() < params["android_probability"][channel]
            platform = "android" if android else "ios"

            activation_rate = params["early_task_probability"][channel]
            if recent and android:
                activation_rate += params["recent_android_early_task_delta"]
            early_task = draw() < activation_rate
            configured = early_task and draw() < (0.57 if routine else 0.28)
            legacy_flag = int(draw() < (0.90 if configured else 0.29))
            if draw() < params["legacy_missing_probability"]:
                legacy_flag = ""
            missing_channel = params["channel_missing_probability"]
            if recent and android and channel == paid_channel:
                missing_channel += params["recent_android_paid_channel_missing_extra"]
            recorded_channel = "" if draw() < missing_channel else channel
            goal = "routine" if routine else "one_off"
            if draw() < params["goal_missing_probability"]:
                goal = ""
            signups.append((user, signup, cohort, platform, recorded_channel, goal, legacy_flag))

            if draw() < 0.94:
                emit(user, signup, platform, "app_open")
            if early_task:
                setup_day = signup + timedelta(days=int(draw() < 0.23))
                emit(user, setup_day, platform, "task_created")
                if configured:
                    emit(user, setup_day, platform, "reminder_enabled")

            # A latent individual propensity correlates behavior across days.
            intensity = (draw() - 0.5) * 0.21 + 0.13 * routine + 0.14 * early_task
            if recent and channel == paid_channel:
                intensity += params["recent_paid_engagement_delta"]
            if recent and channel == referral_channel:
                intensity += params["recent_referral_engagement_delta"]
            for age in range(1, (end - signup).days + 1):
                day = signup + timedelta(days=age)
                if draw() < 0.035:
                    emit(user, day, platform, "background_sync")
                weekly_bump = 0.07 if routine and age % 7 == 0 else 0
                use_rate = max(0.025, 0.22 + intensity + weekly_bump - 0.0036 * age)
                if draw() < use_rate:
                    emit(user, day, platform, "app_open")
                    if age >= 2 and draw() < 0.21:
                        emit(user, day, platform, "task_created")
                    if configured and draw() < 0.26:
                        emit(user, day, platform, "reminder_opened")
                    if draw() < (0.78 if routine else 0.60):
                        emit(user, day, platform, "task_completed")
                        if draw() < 0.13:
                            emit(user, day, platform, "task_completed")
                elif draw() < 0.09:
                    emit(user, day, platform, "app_open")

    directory.mkdir(parents=True, exist_ok=True)
    label = params["data_label"]
    write_csv(directory, "signups.csv",
              ("user_id", "signup_date", "cohort_week", "platform", "channel",
               "stated_goal", "legacy_setup_flag"), signups, label)
    write_csv(directory, "events.csv",
              ("event_id", "user_id", "event_date", "event_type"), events, label)
    write_csv(directory, "coverage.csv", ("event_date", "platform", "status"), coverage, label)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--parameters", type=Path, default=ROOT / "generation.json")
    args = parser.parse_args()
    generate(args.output, json.loads(args.parameters.read_text(encoding="utf-8")))

"""Reproduce the T7 metrics from the synthetic paired-task CSV."""
import argparse
import csv
import json
from fractions import Fraction
from math import ceil
from pathlib import Path
from statistics import median


FIELDS = (
    "provenance", "pair_id", "manual_seconds", "csv_seconds", "manual_completed",
    "csv_completed", "csv_conversion_required", "links_lost", "links_substituted",
)


def measure(path):
    reductions = []
    pair_ids = set()
    manual_completed = csv_completed = converted = links_lost = links_substituted = 0
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if tuple(next(reader, ())) != FIELDS:
            raise ValueError("unexpected fixture columns")
        for row in reader:
            provenance, pair, *values = row
            if provenance != "SYNTHETIC TEST FIXTURE" or not pair.strip() or pair in pair_ids:
                raise ValueError(f"invalid provenance or pair ID: {pair}")
            manual_time, csv_time, manual_done, csv_done, conversion, lost, substituted = map(int, values)
            if min(manual_time, csv_time) <= 0 or min(lost, substituted) < 0:
                raise ValueError(f"invalid duration or link count: {pair}")
            if any(flag not in (0, 1) for flag in (manual_done, csv_done, conversion)):
                raise ValueError(f"invalid completion or conversion flag: {pair}")
            pair_ids.add(pair)
            manual_completed += manual_done
            csv_completed += csv_done
            converted += conversion
            links_lost += lost
            links_substituted += substituted
            if manual_done and csv_done:
                reductions.append(Fraction(manual_time - csv_time, manual_time))

    if not pair_ids:
        raise ValueError("no paired tasks")
    pairs = len(pair_ids)
    return {
        "pairs": pairs,
        "completed_pairs": len(reductions),
        "median_reduction_pct": float(100 * median(reductions)) if reductions else None,
        "manual_completed": manual_completed,
        "csv_completed": csv_completed,
        "completion_minimum_fixture": ceil(Fraction(9, 10) * pairs),
        "csv_conversion_required": converted,
        "links_lost": links_lost,
        "links_substituted": links_substituted,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    print(json.dumps(measure(parser.parse_args().csv), indent=2))

"""Produce measured pass/fail outcomes from a small authored CSV test suite."""
import argparse
import csv
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.sources import table_rows

FIXTURES = (
    ("plain", True, "claim,source\r\nOne,report\r\n"),
    ("quoted_comma", True, 'claim,source\r\n"One, two",report\r\n'),
    ("quoted_multiline", True, 'claim,source\r\n"One\r\ntwo",report\r\n'),
    ("escaped_quote", True, 'claim,source\r\n"One ""word""",report\r\n'),
    ("utf8_bom", True, "\ufeffclaim,source\r\nТезис,отчёт\r\n"),
    ("semicolon_export", False, "claim;source\r\nOne;report\r\n"),
    ("ragged_row", False, "claim,source\r\nOne,report,extra\r\n"),
    ("missing_source", False, "claim,source\r\nOne,\r\n"),
)
FIELDS = ("sample", "expected", "observed", "detail")


def classify(path):
    try:
        rows = iter(table_rows(path))
        _, header = next(rows, ("", []))
        if header != ["claim", "source"]:
            return "rejected", "header_mismatch"
        count = 0
        for _, row in rows:
            if len(row) != 2:
                return "rejected", "row_width"
            if not all(value.strip() for value in row):
                return "rejected", "empty_required_field"
            count += 1
        return ("accepted", "schema_ok") if count else ("rejected", "no_rows")
    except (csv.Error, UnicodeError):
        return "rejected", "invalid_csv"


def generate():
    with TemporaryDirectory() as directory:
        for name, accept, sample in FIXTURES:
            path = Path(directory) / f"{name}.csv"
            path.write_bytes(sample.encode("utf-8"))
            observed, detail = classify(path)
            yield dict(sample=name, expected="accepted" if accept else "rejected",
                       observed=observed, detail=detail)


def summarize(path):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if tuple(reader.fieldnames or ()) != FIELDS or len({row["sample"] for row in rows}) != len(rows):
        raise ValueError("unexpected columns or duplicate samples")
    if not rows or any(row["observed"] not in {"accepted", "rejected"} for row in rows):
        raise ValueError("missing or invalid observations")
    counts = Counter(row["observed"] for row in rows)
    mismatches = sum(row["expected"] != row["observed"] for row in rows)
    print(f"samples={len(rows)} accepted={counts['accepted']} rejected={counts['rejected']} "
          f"mismatches={mismatches}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.generate:
        with args.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(generate())
    summarize(args.csv)


if __name__ == "__main__":
    main()

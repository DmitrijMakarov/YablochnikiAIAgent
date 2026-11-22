"""File-backed checkpoints and provenance for an editor-hosted agent."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from .sources import extract, fetch, public_url, read_records, snapshot_text

STEPS = {
    "scope": ("brief.md",),
    "research": ("research.md", "sources.tsv", "claims.tsv"),
    "strategy": ("strategy.md", "quality.md"),
    "decision": ("decisions.md",),
}
SOURCE_FIELDS = (
    "id", "kind", "origin", "accessed_utc", "status", "method", "snapshot", "sha256", "error",
)
CLAIM_FIELDS = ("id", "type", "status", "statement", "source", "locator", "quote", "basis", "scope")
AUDIT_FIELDS = ("id", "verdict", "rationale")
RUN_FIELDS = (
    "step", "attempt", "started_utc", "ended_utc", "seconds", "status", "environment",
    "tool", "input", "outputs", "model", "tokens", "tokens_kind", "cost", "cost_kind",
    "measurement", "human", "detail",
)
SOURCE_ID = re.compile(r"S-\d{3,}@\d+")
CLAIM_ID = re.compile(r"C-\d{3,}")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                            delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def get_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def put_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def table(path, fields):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != list(fields):
            raise ValueError(f"unexpected columns in {path.name}")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"malformed row in {path.name}")
    return rows


def put_table(path, fields, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic(path, buffer.getvalue())


def child(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"path outside permitted folder: {relative}")
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_names(step, value):
    if step == "strategy" and value.get("audit_required"):
        return (*STEPS[step], "audit.tsv")
    return STEPS[step]


def outputs(case, step, value):
    return {name: digest(child(case, name)) for name in output_names(step, value)}


def append_run(case, row):
    path = case / "run.tsv"
    rows = table(path, RUN_FIELDS)
    rows.append(row)
    put_table(path, RUN_FIELDS, rows)


def event(step, attempt, started, status, environment, tool, **details):
    ended = now()
    seconds = (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds()
    row = dict(step=step, attempt=attempt, started_utc=started, status=status,
               environment=environment, tool=tool, tokens_kind="unknown", cost_kind="unknown")
    if status != "started":
        row.update(ended_utc=ended, seconds=f"{max(seconds, 0):.3f}")
    return row | details


def state(case):
    value = get_json(case / "state.json")
    if value.get("schema") != 1:
        raise ValueError("unsupported checkpoint schema")
    return value


def init(case, args):
    case.mkdir(parents=True, exist_ok=True)
    (case / "inputs").mkdir(exist_ok=True)
    for filename, fields in (("run.tsv", RUN_FIELDS), ("sources.tsv", SOURCE_FIELDS),
                             ("claims.tsv", CLAIM_FIELDS)):
        if not (case / filename).exists():
            put_table(case / filename, fields, [])
    if not (case / "brief.md").exists():
        atomic(case / "brief.md", "# Бриф\n\nЗапишите исходный вопрос, цель, ограничения и получателя.\n")
    if not (case / "inputs.json").exists():
        put_json(case / "inputs.json", {"web_requests": 0, "sources": []})
    if not (case / "state.json").exists():
        put_json(case / "state.json", dict(schema=1, status="ready", next="scope",
                                           completed={}, pending=None, reason="", audit_required=True))


def check_completed(case, value):
    for step, committed in value["completed"].items():
        if outputs(case, step, value) != committed:
            raise ValueError(f"completed {step} artifacts changed; use a new revision of the case")


def reconcile(case, value):
    check_completed(case, value)
    pending = value["pending"]
    if not pending:
        return value
    step = pending["step"]
    for row in reversed(table(case / "run.tsv", RUN_FIELDS)):
        if (row["attempt"] == pending["attempt"] and row["step"] == step
                and row["tool"] == "agent" and row["status"] == "ok"):
            try:
                current = outputs(case, step, value)
            except FileNotFoundError as error:
                raise ValueError(f"committed checkpoint artifact is missing: {error.filename}") from error
            if json.loads(row["outputs"]) != current:
                raise ValueError("committed checkpoint artifact changed; inspect before continuing")
            value["completed"][step] = current
            value["pending"] = None
            following = list(STEPS)[list(STEPS).index(step) + 1:]
            value["next"] = following[0] if following else None
            value["status"] = {"strategy": "awaiting_decision", "decision": "decided"}.get(step, "ready")
            value["reason"] = ""
            put_json(case / "state.json", value)
            break
    return value


def begin(case, args):
    value = reconcile(case, state(case))
    if value["status"] == "paused":
        raise ValueError("resume the paused case first")
    if value["next"] != args.step:
        raise ValueError(f"next step is {value['next']}")
    pending = value["pending"]
    if pending:
        raise ValueError("step already open; inspect and reuse the pending attempt")
    pending = dict(step=args.step, attempt=uuid4().hex[:12], started=now(),
                   environment=args.environment, model=args.model, expected=output_names(args.step, value))
    value.update(pending=pending, status="running", reason="")
    put_json(case / "state.json", value)
    append_run(case, event(args.step, pending["attempt"], pending["started"], "started",
                           args.environment, "agent", model=args.model))
    print(json.dumps(pending, ensure_ascii=False))


def check(case, with_strategy=True):
    from .verify import verify

    return verify(case, with_strategy)


def finish(case, args):
    value = reconcile(case, state(case))
    pending = value["pending"]
    if value["status"] != "running" or not pending:
        raise ValueError("no running step to finish")
    step = pending["step"]
    if step == "decision" and not args.human.strip():
        raise ValueError("record the human confirmation with --human")
    if step in {"research", "strategy"}:
        check(case, step == "strategy")
    artifacts = outputs(case, step, value)
    if any(not (case / name).read_text(encoding="utf-8").strip() for name in artifacts):
        raise ValueError("empty checkpoint artifact")
    append_run(case, event(step, pending["attempt"], pending["started"], "ok",
                           pending["environment"], "agent", model=pending["model"],
                           outputs=json.dumps(artifacts), human=args.human, detail=args.note))
    reconcile(case, value)


def pause(case, args):
    value = reconcile(case, state(case))
    if value["status"] in {"awaiting_decision", "decided"}:
        raise ValueError(f"case is already at {value['status']}")
    if value["status"] != "paused":
        value.update(status="paused", reason=args.reason, paused_at=now())
        put_json(case / "state.json", value)


def resume(case, args):
    value = reconcile(case, state(case))
    if value["status"] == "paused":
        pending = value["pending"]
        stamp = now()
        append_run(case, event(pending["step"] if pending else value["next"], uuid4().hex[:12],
                               value["paused_at"], "resumed", args.environment,
                               "checkpoint", detail=value["reason"], ended_utc=stamp))
        value.update(status="running" if pending else "ready", reason="")
        value.pop("paused_at", None)
        put_json(case / "state.json", value)
    print(json.dumps(value, indent=2, ensure_ascii=False))


def ingest(case, args):
    value = state(case)
    pending = value["pending"]
    if value["status"] != "running" or not pending or pending["step"] != "research":
        raise ValueError("open the research step before ingesting sources")
    manifest = get_json(case / "inputs.json")
    matches = [item for item in manifest["sources"] if item["id"] == args.source]
    if len(matches) != 1 or not SOURCE_ID.fullmatch(args.source):
        raise ValueError("source must have one entry in inputs.json and an ID like S-001@1")
    item = matches[0]
    kind = item["kind"]
    url = item.get("url")
    if bool(url) == bool(item.get("path")) or kind not in {"own", "public", "synthetic"}:
        raise ValueError("declare one path or public HTTPS URL and a supported source kind")
    if url:
        public_url(url)
        if kind != "public":
            raise ValueError("web sources must be public")
    elif args.live:
        raise ValueError("--live requires a declared web source")
    origin = url or f"inputs/{item['path']}"
    path = case / "sources.tsv"
    rows = table(path, SOURCE_FIELDS)
    for entry in rows:
        if entry["id"] != args.source:
            continue
        if entry["origin"] != origin or entry["kind"] != kind:
            raise ValueError("source ID already used with different origin or kind; declare a new version")
        if entry["status"] == "available":
            if digest(child(case, entry["snapshot"])) != entry["sha256"]:
                raise ValueError("existing source snapshot changed")
            if not url:
                original = child(child(case, "inputs"), item["path"])
                if entry["method"] != "file:" + digest(original):
                    raise ValueError("local source changed; declare a new source version")
            print(f"reused {args.source} {entry['snapshot']}")
            return
    tool = "web" if url and args.live else "source"
    attempt = uuid4().hex[:12]
    start = now()
    earlier = table(case / "run.tsv", RUN_FIELDS)
    if tool == "web":
        budget = manifest["web_requests"]
        if type(budget) is not int or budget < 0:
            raise ValueError("web_requests must be a nonnegative integer")
        web = [row for row in earlier if row["tool"] == "web" and row["status"] == "started"]
        if len(web) >= budget:
            raise ValueError("web request budget exhausted")
        finished = {row["attempt"] for row in earlier if row["status"] in {"ok", "error"}}
        if any(row["attempt"] not in finished and row["input"] == args.source for row in web):
            raise ValueError("previous web attempt has unknown outcome; inspect the journal before retrying")
    append_run(case, event("research", attempt, start, "started", pending["environment"],
                           tool, input=args.source, detail=origin))
    result = dict(id=args.source, kind=kind, origin=origin, accessed_utc=now(),
                  status="unavailable", method="", snapshot="", sha256="", error="")
    try:
        if tool == "web":
            records = fetch(url)
            result["method"] = "https"
        elif url:
            if not item.get("snapshot") or not item.get("capture_note"):
                raise ValueError("no approved snapshot; use --live if access is allowed")
            capture = child(child(case, "inputs"), item["snapshot"])
            if capture.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("manual web capture exceeds 2 MiB")
            records = read_records(capture)
            result["method"] = "capture: " + item["capture_note"]
        else:
            original = child(child(case, "inputs"), item["path"])
            records = extract(original)
            data = snapshot_text(records)
            result["method"] = "file:" + digest(original)
        if url:
            data = snapshot_text(records)
        relative = f"evidence/{args.source}.jsonl"
        snapshot = child(case, relative)
        atomic(snapshot, data)
        result.update(status="available", snapshot=relative, sha256=digest(snapshot))
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}".replace("\n", " ")[:500]
    put_table(path, SOURCE_FIELDS, [row for row in rows if row["id"] != args.source] + [result])
    available = result["status"] == "available"
    append_run(case, event("research", attempt, start, "ok" if available else "error",
                           pending["environment"], tool, input=args.source,
                           outputs=result["snapshot"], detail=result["error"] or result["method"]))
    print(json.dumps(result, ensure_ascii=False))
    if not available:
        return 1


def validate(case, args):
    check_completed(case, state(case))
    print(json.dumps(check(case, not args.research_only), ensure_ascii=False))


def log(case, args):
    value = state(case)
    pending = value["pending"]
    if args.step:
        if args.step not in value["completed"]:
            raise ValueError("--step must name a completed step")
        committed = json.dumps(value["completed"][args.step])
        pending = next((row for row in reversed(table(case / "run.tsv", RUN_FIELDS))
                        if row["step"] == args.step and row["tool"] == "agent"
                        and row["status"] == "ok" and row["outputs"] == committed), None)
        if not pending:
            raise ValueError("completed step has no matching journal record")
    elif value["status"] != "running" or not pending:
        raise ValueError("no running step; use --step for a completed phase")
    for label in ("tokens", "cost"):
        metric = getattr(args, label)
        if metric and not args.measurement:
            raise ValueError(f"{label} requires --measurement with source and scope")
    details = {name: getattr(args, name) for name in ("input", "outputs", "detail", "human", "measurement")}
    for label in ("tokens", "cost"):
        metric = getattr(args, label)
        details[label + "_kind"], details[label] = metric if metric else ("unknown", "")
    started = args.started or now()
    if datetime.fromisoformat(started) > datetime.now(timezone.utc):
        raise ValueError("action start cannot be in the future")
    if not args.started:
        details["seconds"] = ""
    append_run(case, event(pending["step"], uuid4().hex[:12], started, args.status,
                           pending["environment"], args.tool, model=pending["model"], **details))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("init", init), ("begin", begin), ("finish", finish), ("pause", pause),
                           ("resume", resume), ("ingest", ingest), ("verify", validate), ("log", log)):
        command = commands.add_parser(name)
        command.set_defaults(function=function)
        command.add_argument("case", type=Path)
        if name in {"begin", "resume"}:
            command.add_argument("--environment", default="unknown")
        if name == "begin":
            command.add_argument("step", choices=STEPS)
            command.add_argument("--model", default="unknown")
        if name == "finish":
            command.add_argument("--human", default="")
            command.add_argument("--note", default="")
        if name == "pause":
            command.add_argument("--reason", required=True)
        if name == "ingest":
            command.add_argument("source")
            command.add_argument("--live", action="store_true")
        if name == "verify":
            command.add_argument("--research-only", action="store_true")
        if name == "log":
            command.add_argument("--tool", required=True)
            command.add_argument("--status", choices=("ok", "error", "retry", "unknown"), required=True)
            command.add_argument("--started", help="ISO 8601 timestamp with timezone")
            command.add_argument("--step", choices=STEPS, help="attribute a later observation to a completed step")
            for field in ("input", "outputs", "detail", "human", "measurement"):
                command.add_argument("--" + field, default="")
            for metric in ("tokens", "cost"):
                command.add_argument("--" + metric, nargs=2, metavar=("KIND", "VALUE"))
    args = parser.parse_args()
    for metric in ("tokens", "cost"):
        value = getattr(args, metric, None)
        if value and (value[0] not in {"measured", "estimated"} or not value[1].strip()):
            parser.error(f"--{metric} needs measured or estimated followed by a value")
    try:
        return args.function(args.case.resolve(), args) or 0
    except (OSError, KeyError, TypeError, ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

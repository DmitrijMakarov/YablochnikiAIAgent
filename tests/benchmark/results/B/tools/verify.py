"""Check recorded provenance, citations and the structure of the strategy and audit."""
import re

from .case import (
    AUDIT_FIELDS, CLAIM_FIELDS, CLAIM_ID, SOURCE_FIELDS, SOURCE_ID, child, digest, get_json, state, table,
)
from .sources import public_url, read_records, snapshot_text

HEADINGS = (
    "## Альтернативы", "## Рекомендация", "## Продуктовая стратегия",
    "## Коммуникационная стратегия", "## План проверки",
)
MARKER = re.compile(r"\[\[([^\[\]]+)\]\]")


def normalize(text):
    return " ".join(text.split())


def check_audit(case, claims):
    active = {key for key, row in claims.items() if row["status"] == "active"}
    audited = set()
    for row in table(child(case, "audit.tsv"), AUDIT_FIELDS):
        key = row["id"]
        if key not in active or key in audited:
            raise ValueError(f"audit.tsv: unexpected or duplicate claim: {key}")
        if not row["rationale"].strip():
            raise ValueError(f"audit.tsv: missing rationale for {key}")
        if row["verdict"] == "needs_revision":
            raise ValueError(f"audit.tsv: {key} requires revision")
        expected = "supported" if claims[key]["type"] == "fact" else "bounded"
        if row["verdict"] != expected:
            raise ValueError(f"audit.tsv: invalid verdict for {key}; expected {expected}")
        audited.add(key)
    if missing := active - audited:
        raise ValueError(f"audit.tsv: missing active claims: {', '.join(sorted(missing))}")


def verify(case, with_strategy):
    manifest = get_json(case / "inputs.json")["sources"]
    rows = table(case / "sources.tsv", SOURCE_FIELDS)
    registered = {row["id"]: row for row in rows}
    if len(rows) != len(registered):
        raise ValueError("duplicate registered source")
    expected = {item["id"]: item for item in manifest}
    if len(expected) != len(manifest) or set(expected) != set(registered):
        raise ValueError("record every declared source, including unavailable sources")
    snapshots = {}
    for key, row in registered.items():
        item = expected[key]
        url = item.get("url")
        if bool(url) == bool(item.get("path")):
            raise ValueError(f"declare one path or public HTTPS URL: {key}")
        if url:
            public_url(url)
        origin = url or f"inputs/{item['path']}"
        if (not SOURCE_ID.fullmatch(key) or row["kind"] not in {"own", "public", "synthetic"}
                or row["kind"] != item["kind"] or row["origin"] != origin
                or (url and row["kind"] != "public") or not row["accessed_utc"]):
            raise ValueError(f"source metadata mismatch: {key}")
        if row["status"] == "unavailable" and row["error"]:
            continue
        if row["status"] != "available" or row["snapshot"] != f"evidence/{key}.jsonl":
            raise ValueError(f"invalid source record: {key}")
        path = child(case, row["snapshot"])
        if digest(path) != row["sha256"]:
            raise ValueError(f"snapshot changed: {key}")
        records = read_records(path)
        serialized = snapshot_text(records)
        if not url:
            original = child(child(case, "inputs"), item["path"])
            if row["method"] != "file:" + digest(original):
                raise ValueError(f"local source changed: {key}; keep the original and register a new version")
        elif row["method"] != "https":
            note = item.get("capture_note")
            if not note or row["method"] != "capture: " + note or not item.get("snapshot"):
                raise ValueError(f"capture metadata mismatch: {key}")
            capture = child(child(case, "inputs"), item["snapshot"])
            if capture.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("manual web capture exceeds 2 MiB")
            if snapshot_text(read_records(capture)) != serialized:
                raise ValueError(f"capture changed: {key}; keep the original and register a new version")
        snapshots[key] = {item["locator"]: item["text"] for item in records}

    rows = table(case / "claims.tsv", CLAIM_FIELDS)
    claims = {}
    for row in rows:
        key, kind = row["id"], row["type"]
        if (not CLAIM_ID.fullmatch(key) or key in claims
                or row["status"] not in {"active", "disputed", "superseded", "withdrawn"}
                or not row["statement"].strip() or not row["scope"].strip()):
            raise ValueError(f"invalid claim: {key}")
        basis = row["basis"].split(",") if row["basis"] else []
        if any(ref not in claims for ref in basis):
            raise ValueError(f"{key}: basis must refer to earlier claims")
        if row["status"] == "active" and any(claims[ref]["status"] != "active" for ref in basis):
            raise ValueError(f"{key}: active claim depends on disputed or obsolete claims")
        if kind == "fact":
            source = row["source"]
            if source not in snapshots or registered[source]["kind"] == "synthetic" or basis:
                raise ValueError(f"{key}: fact requires available public or own primary evidence")
            text = snapshots[source].get(row["locator"], "")
            quote = normalize(row["quote"])
            if not quote or quote not in normalize(text):
                raise ValueError(f"{key}: quote not found at {source} {row['locator']}")
        elif kind in {"inference", "hypothesis", "forecast"}:
            if any(row[field] for field in ("source", "locator", "quote")):
                raise ValueError(f"{key}: connect reasoning through basis, not a direct citation")
            if kind in {"inference", "forecast"} and not basis:
                raise ValueError(f"{key}: {kind} requires a basis")
        else:
            raise ValueError(f"{key}: unknown claim type {kind}")
        claims[key] = row

    documents = ["research.md"]
    if with_strategy:
        documents.extend(("strategy.md", "quality.md"))
    for document in documents:
        text = (case / document).read_text(encoding="utf-8")
        refs = set(MARKER.findall(text))
        if not refs or refs - claims.keys():
            raise ValueError(f"{document}: missing or unknown claim markers")
        if document == "strategy.md":
            if any(claims[ref]["status"] != "active" for ref in refs):
                raise ValueError("strategy cites a disputed or obsolete claim as current")
            if not any(claims[ref]["type"] == "fact" for ref in refs):
                raise ValueError("strategy requires at least one cited fact")
            lines = text.splitlines()
            if any(heading not in lines for heading in HEADINGS):
                raise ValueError("strategy missing a required section")
            options = re.findall(r"^### (O-\d+) \[([a-z_]+)\] ", text, flags=re.MULTILINE)
            if (len({key for key, _ in options}) != len(options) or len(options) < 3
                    or not {"status_quo", "close", "change"}.issubset({tag for _, tag in options})):
                raise ValueError("strategy needs distinct status_quo, close and change options")
    audit_structure = "not_requested"
    if with_strategy:
        audit_structure = "legacy_unrecorded"
        if state(case).get("audit_required"):
            check_audit(case, claims)
            audit_structure = "checked"
    return {"sources_available": len(snapshots), "sources_unavailable": len(registered) - len(snapshots),
            "claims": len(claims), "strategy_checked": with_strategy,
            "audit_structure": audit_structure}

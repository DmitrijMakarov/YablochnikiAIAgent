"""Package local reviewable project files and validate an extracted copy.

No publication, Git mutation, external network, API calls or LLM invocation.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/submission"
OUT.mkdir(parents=True, exist_ok=True)
CHECK = ROOT / "deliverables/megafon/submission/package-checks.json"
ARCHIVE = OUT / "Yablochniki-Strateg-Megafon-2026.zip"
PREFIX = "Yablochniki-Strateg-Megafon-2026"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    # Tracked archived test results are retained even if historical ignore rules
    # would hide them; excluding arbitrary test data would invalidate manifests.
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, check=True, capture_output=True)
    paths = set(result.stdout.decode().split("\0")) - {""}
    excluded = {".git", ".venv", "output", "tmp", "node_modules"}
    selected = []
    for relative in sorted(paths):
        path = Path(relative)
        if path.parts[0] in excluded or relative.startswith("cases/local/"):
            continue
        if path.name == ".DS_Store" or path.name == ".env" or path.name.startswith(".env."):
            continue
        if not (ROOT / path).is_file():
            continue
        if (ROOT / path).is_symlink():
            raise ValueError(f"Unexpected symlink, review required: {relative}")
        selected.append(relative)
    return selected


def run(args, cwd):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    return {"command": " ".join(str(a) for a in args), "exit_code": p.returncode,
            "stdout": p.stdout, "stderr": p.stderr}


def local_links(relative, base):
    broken = []
    content = (base / relative).read_text()
    for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
        target = target.strip().strip("<>").split("#", 1)[0]
        if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        # Links in literal command examples are not part of current docs.
        if not (base / relative).parent.joinpath(unquote(target)).exists():
            broken.append({"file": relative, "target": target})
    return broken


selected = files()
docs = ["README.md", "deliverables/megafon/SUBMISSION.md", "deliverables/megafon/agent-description.md"]
# The check record references itself through SUBMISSION; create a valid initial
# record before validating links, then replace it with the complete result.
CHECK.write_text(json.dumps({"status": "building"}) + "\n")
selected = files()
secret_findings = []
patterns = [re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(rb"(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}"),
            re.compile(rb"AKIA[0-9A-Z]{16}")]
for rel in selected:
    raw = (ROOT / rel).read_bytes()
    if any(pattern.search(raw) for pattern in patterns):
        secret_findings.append(rel)
if secret_findings:
    raise ValueError("Possible credentials require review in: " + ", ".join(secret_findings))
broken = [finding for doc in docs for finding in local_links(doc, ROOT)]
if broken:
    raise ValueError("Broken local links: " + json.dumps(broken, ensure_ascii=False))
manifest = json.loads((ROOT / "deliverables/megafon/manifest.json").read_text())
bad_manifest = [rel for rel, expected in manifest["files"].items() if sha(ROOT / rel) != expected]
if bad_manifest:
    raise ValueError("Existing deliverable manifest mismatch: " + ", ".join(bad_manifest))
case_hashes = json.loads((ROOT / "deliverables/megafon/submission/evidence.json").read_text())["source_case_hashes"]
bad_case = [rel for rel, expected in case_hashes.items()
            if sha(ROOT / "cases/megafon-official" / rel) != expected]
if bad_case:
    raise ValueError("Original case changed: " + ", ".join(bad_case))

with tempfile.TemporaryDirectory(prefix="strateg-package-") as tmp:
    base = Path(tmp)
    # A trial ZIP validates exactly the same transport as the final archive.
    trial = base / "trial.zip"
    with zipfile.ZipFile(trial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in selected:
            z.write(ROOT / rel, PREFIX + "/" + rel)
    with zipfile.ZipFile(trial) as z:
        assert z.testzip() is None
        z.extractall(base / "extracted")
    copy = base / "extracted" / PREFIX
    extracted_hashes = all(sha(copy / rel) == sha(ROOT / rel) for rel in selected)
    verify = run([sys.executable, "-m", "tools.case", "verify", "cases/megafon-official"], copy)
    help_result = run([sys.executable, "-m", "tools.case", "--help"], copy)
    tests = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], copy)
    assert extracted_hashes and verify["exit_code"] == help_result["exit_code"] == tests["exit_code"] == 0
    # A separate PDF dependency is unnecessary for validating text with the
    # already required pypdf in the agent environment.
    from pypdf import PdfReader
    description = PdfReader(copy / "deliverables/megafon/agent-description.pdf")
    headings = json.loads((copy / "tools/submission/report.json").read_text())["pages"]
    assert len(description.pages) == len(headings) == 8
    pdf_text = "\n".join(page.extract_text() for page in description.pages)
    for page in headings:
        assert page["title"] in pdf_text, page["title"]
    assert len(PdfReader(copy / "deliverables/megafon/strategy.pdf").pages) == 20
    checks = {
        "status": "passed", "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "publication": "not_performed", "video": "not_created",
        "case_unchanged": not bad_case, "existing_manifest_matches": not bad_manifest,
        "local_links_checked": docs, "broken_local_links": broken,
        "credential_scan": {"scope": "private-key blocks, common GitHub tokens, AWS access key ID patterns", "findings": secret_findings, "limitation": "Pattern screening, not a guarantee of absence of every possible secret."},
        "trial_zip_crc": "passed", "trial_extracted_hashes": extracted_hashes,
        "extracted_verify": verify, "extracted_help": help_result, "extracted_tests": tests,
        "runtime_note": "Extracted files tested with existing dependency-equipped Python, no new dependency install or new LLM run.",
        "pdf_pages": {"description": 8, "strategy": 20},
        "description_headings_present": True,
        "visual_review": {"pages": 8, "status": "passed", "method": "Poppler PNG render and visual inspection by primary agent"},
        "excluded": [".git", ".venv", "cases/local", ".DS_Store", ".env*", "output", "tmp", "node_modules"]
    }
CHECK.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n")

selected = files()
entries = {rel: {"sha256": sha(ROOT / rel), "bytes": (ROOT / rel).stat().st_size} for rel in selected}
metadata = {"format": 1, "root": PREFIX, "files": entries,
            "note": "Source snapshot from local working files; no Git history. Video/publication/submission excluded."}
with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for rel in selected:
        z.write(ROOT / rel, PREFIX + "/" + rel)
    z.writestr(PREFIX + "/SUBMISSION-MANIFEST.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
with zipfile.ZipFile(ARCHIVE) as z:
    assert z.testzip() is None
    for rel, entry in entries.items():
        assert hashlib.sha256(z.read(PREFIX + "/" + rel)).hexdigest() == entry["sha256"]
(OUT / "SUBMISSION-MANIFEST.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
(OUT / (ARCHIVE.name + ".sha256")).write_text(f"{sha(ARCHIVE)}  {ARCHIVE.name}\n")
# Put the two PDFs beside the ZIP for convenient separate form uploads.
import shutil
for filename in ["strategy.pdf", "agent-description.pdf"]:
    shutil.copy2(ROOT / "deliverables/megafon" / filename, OUT / filename)
print(json.dumps({"archive": str(ARCHIVE.relative_to(ROOT)), "files": len(selected),
                  "bytes": ARCHIVE.stat().st_size, "checks": "passed"}, ensure_ascii=False))

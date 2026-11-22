"""Capture real local command output and source excerpts for the submission report."""
from pathlib import Path
import csv
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deliverables/megafon/submission"
OUT.mkdir(parents=True, exist_ok=True)
CASE = ROOT / "cases/megafon-official"


def command(args, cwd=ROOT):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=60)
    return {"command": " ".join(str(a) for a in args), "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def excerpt(path, start, end):
    lines = (ROOT / path).read_text().splitlines()
    return {"path": path, "first_line": start,
            "text": "\n".join(lines[start - 1:end]),
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}


def digest_case():
    return {str(p.relative_to(CASE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(CASE.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts and p.name != ".DS_Store"}


before = digest_case()
verify = command([sys.executable, "-m", "tools.case", "verify", "cases/megafon-official"])
with tempfile.TemporaryDirectory(prefix="strateg-resume-") as tmp:
    destination = Path(tmp) / "case"
    shutil.copytree(CASE, destination, ignore=shutil.ignore_patterns("review", "__pycache__", ".DS_Store"))
    resume = command([sys.executable, "-m", "tools.case", "resume", str(destination), "--environment", "Codex"])
    # Absolute temporary path is irrelevant to the evidence and not portable.
    resume["command"] = "python -m tools.case resume TEMP_COPY/case --environment Codex"
    resume["stdout"] = resume["stdout"].replace(str(destination), "TEMP_COPY/case")
    resume["stderr"] = resume["stderr"].replace(str(destination), "TEMP_COPY/case")
    resume["scope"] = "Новый процесс CLI на временной копии; это не новый чат с LLM."
    resumed_state = json.loads((destination / "state.json").read_text())
tests = command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
with (CASE / "run.tsv").open() as stream:
    journal = list(csv.DictReader(stream, delimiter="\t"))
phases = [{"phase": r["step"], "seconds": float(r["seconds"]),
           "started_utc": r["started_utc"], "ended_utc": r["ended_utc"]}
          for r in journal if r["tool"] == "agent" and r["status"] == "ok" and r["seconds"]]
data = {
    "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "python": sys.version.split()[0], "verify": verify, "resume": resume,
    "resumed_status": resumed_state["status"], "tests": tests,
    "phase_intervals": phases, "phase_seconds_sum": sum(r["seconds"] for r in phases),
    "case_unchanged": before == digest_case(),
    "source_case_hashes": before,
    "panels": [
        {"id": "01-instructions", "title": "Постановка исследование и стратегия", **excerpt("AGENTS.md", 5, 7)},
        {"id": "02-research", "title": "Вопросы которые могут изменить решение", **excerpt("cases/megafon-official/research.md", 5, 12)},
        {"id": "03-options", "title": "Пять альтернатив и условия выбора", **excerpt("cases/megafon-official/strategy.md", 5, 25)},
        {"id": "04-strategy", "title": "Рекомендация и ограничения прогноза", **excerpt("deliverables/megafon/strategy.md", 5, 7)},
        {"id": "05-verify", "title": "Проверка сохранённого кейса", "path": "Фактический stdout CLI", "text": "$ python -m tools.case verify cases/megafon-official\n\n" + verify["stdout"].strip()},
        {"id": "06-resume", "title": "Восстановление состояния в новом процессе", "path": "Временная копия cases/megafon-official", "text": "$ " + resume["command"] + "\n\n" + resume["stdout"].strip() + "\n\nГраница проверки: " + resume["scope"]},
    ],
}
(OUT / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
assert verify["exit_code"] == resume["exit_code"] == tests["exit_code"] == 0, "A required check failed; inspect evidence.json"
assert data["case_unchanged"]
print(json.dumps({"verify": verify["exit_code"], "resume": resume["exit_code"], "tests": tests["exit_code"], "case_unchanged": data["case_unchanged"], "phase_seconds_sum": data["phase_seconds_sum"]}))

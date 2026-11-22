"""Allowlist-only benchmark packaging. No model calls or case execution.

Run from any directory; manifests and exact inventory checks belong to the
operator, never to either participant's workspace.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VERSION = "retention-ab-v1"
INPUT_NAMES = ("product.md", "signups.csv", "events.csv", "coverage.csv",
               "google-tasks.jsonl", "microsoft-to-do.jsonl", "todoist.jsonl")
INSTRUCTIONS = ("AGENTS.md", "playbooks/workflow.md", *(
    f".agents/skills/{name}/SKILL.md" for name in
    ("research-sources", "analyze-data", "build-strategy", "check-evidence")))
COMMON = {
    "SOURCE_BRIEF.md": "cases/retention-demo/brief.md",
    "case/brief.md": "cases/retention-demo/brief.md",
    "case/inputs.json": "cases/retention-demo/inputs.json",
    "requirements.txt": "requirements.txt",
    "START.md": "tests/benchmark/prompts/A.md",
    **{f"case/inputs/{name}": f"cases/retention-demo/inputs/{name}" for name in INPUT_NAMES},
    **{f"tools/{name}.py": f"tools/{name}.py" for name in ("case", "sources", "verify")},
}
CONTRACT_FILES = ("protocol.md", "rubric.md", "recording.md", "prepare.py",
                  "prompts/A.md", "prompts/B.md", "templates/launch.json",
                  "templates/run.json", "templates/events.tsv",
                  "templates/expert-scores.tsv", "templates/automatic-metrics.tsv")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def no_link(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"symbolic link forbidden: {component}")
    return path


def tree(root):
    root = no_link(root)
    files, directories = {}, set()
    for path in sorted(root.rglob("*")):
        no_link(path)
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise ValueError(f"hard link forbidden: {path}")
            files[relative] = {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
        elif path.is_dir():
            directories.add(relative)
        else:
            raise ValueError(f"nonregular entry forbidden: {path}")
    return files, directories


def expected_directories(files):
    return {p.as_posix() for name in files for p in Path(name).parents if p != Path(".")}


def verify(manifest, after_run=False):
    errors, all_inodes = [], set()
    for label, environment in manifest["environments"].items():
        root = Path(environment["path"])
        files, directories = tree(root)
        expected = environment["files"]
        for name, spec in expected.items():
            if after_run and name == "case/brief.md":
                if name not in files:
                    errors.append(f"{label}: missing {name}")
                continue
            actual = files.get(name, {})
            if any(actual.get(key) != spec[key] for key in ("sha256", "bytes")):
                errors.append(f"{label}: missing/changed {name}")
        for name in files.keys() - expected.keys():
            if not (after_run and (name.startswith("case/") or
                                   (name.startswith("tools/__pycache__/") and name.endswith(".pyc")))):
                errors.append(f"{label}: unexpected file {name}")
        for name in directories - expected_directories(expected):
            if not (after_run and (name == "case" or name.startswith("case/") or
                                   name == "tools/__pycache__")):
                errors.append(f"{label}: unexpected directory {name}")
        for name in files:
            stat = (root / name).stat()
            inode = (stat.st_dev, stat.st_ino)
            if inode in all_inodes:
                errors.append(f"{label}: shared inode {name}")
            all_inodes.add(inode)
    common = set(COMMON)
    for name in common:
        a, b = (manifest["environments"][label]["files"][name] for label in ("A", "B"))
        if a["sha256"] != b["sha256"]:
            errors.append(f"unequal common file {name}")
    if errors:
        raise ValueError("\n".join(errors))
    return {"inventory": "passed", "common_files_equal": len(common),
            "symlinks": 0, "hardlinks": 0, "shared_inodes": 0,
            "mode": "after-run" if after_run else "pristine",
            "technical_read_isolation": "NOT_ESTABLISHED"}


def prepare(source, a, b, manifest_path):
    source, a, b, manifest_path = map(no_link, (source, a, b, manifest_path))
    paths = (a, b)
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("workspaces must be independent")
    if any(source == p or source in p.parents or p in source.parents for p in paths):
        raise ValueError("workspaces must be outside repository")
    if any(p.exists() for p in (*paths, manifest_path)):
        raise ValueError("refusing to replace existing workspace or manifest")
    if any(p == manifest_path or p in manifest_path.parents for p in paths):
        raise ValueError("operator manifest must stay outside participant workspaces")
    if (source / "tests/benchmark/prompts/A.md").read_bytes() != (
            source / "tests/benchmark/prompts/B.md").read_bytes():
        raise ValueError("participant prompts must be identical")
    # Read only the explicit allowlist, never recursively copy the repository.
    blobs = {}
    for original in set(COMMON.values()) | set(INSTRUCTIONS):
        path = no_link(source / original)
        if not path.is_file():
            raise ValueError(f"not a regular source file: {path}")
        blobs[original] = path.read_bytes()
    contract = {name: sha(no_link(source / "tests/benchmark" / name).read_bytes())
                for name in CONTRACT_FILES}
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    result = {"schema": 1, "experiment": VERSION,
              "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_commit": commit.stdout.strip() if commit.returncode == 0 else None,
              "version_note": "File SHA-256 values pin instructions including uncommitted edits.",
              "protocol_files_sha256": contract,
              "instruction_version_sha256": sha(json.dumps(
                  {p: sha(blobs[p]) for p in INSTRUCTIONS}, sort_keys=True).encode()),
              "environments": {}}
    created = []
    try:
        for label, root in zip(("A", "B"), paths):
            root.mkdir(parents=True)
            created.append(root)
            mapping = COMMON | ({p: p for p in INSTRUCTIONS} if label == "B" else {})
            files = {}
            for destination, original in sorted(mapping.items()):
                target = root / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blobs[original])
                files[destination] = {"source": original, "sha256": sha(blobs[original]),
                                      "bytes": len(blobs[original])}
            result["environments"][label] = {
                "path": str(root), "files": files,
                "instruction_files": list(INSTRUCTIONS) if label == "B" else [],
                "baseline_note": "Common executable CLI is available but optional in A.",
            }
        result["checks"] = verify(result)
        result["isolation"] = {
            "copied_material": "strict_allowlist_verified",
            "outside_repository": True,
            "read_boundary": "NOT_ESTABLISHED",
            "reason": "Same host account can read repository and other workspace. No OS read jail configured.",
            "global_context": "Must verify app/profile skills, plugins, instructions and prior chat context before launch.",
            "readiness": "prepared_not_strictly_isolated; confirmatory_run_requires_external_boundary",
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        dump(manifest_path, result)
    except Exception:
        for root in created:
            shutil.rmtree(root)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    make.add_argument("--a", type=Path, required=True)
    make.add_argument("--b", type=Path, required=True)
    make.add_argument("--manifest", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("manifest", type=Path)
    check.add_argument("--after-run", action="store_true")
    check.add_argument("--protocol-root", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.source, args.a, args.b, args.manifest)["checks"]
        else:
            manifest = json.loads(args.manifest.read_text())
            for name, digest in manifest["protocol_files_sha256"].items():
                if sha(no_link(args.protocol_root / name).read_bytes()) != digest:
                    raise ValueError(f"registered protocol changed: {name}")
            result = verify(manifest, args.after_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

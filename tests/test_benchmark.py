"""Packaging checks using small invented files; no research or model runs."""

import os
import runpy
import tempfile
import unittest
from pathlib import Path


PACK = runpy.run_path(str(Path(__file__).parent / "benchmark/prepare.py"))


class BenchmarkPackagingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / "source"
        originals = set(PACK["COMMON"].values()) | set(PACK["INSTRUCTIONS"])
        originals |= {f"tests/benchmark/{p}" for p in PACK["CONTRACT_FILES"]}
        for relative in originals:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"synthetic packaging fixture: {relative}\n")
        for label in ("A", "B"):
            (self.source / f"tests/benchmark/prompts/{label}.md").write_text("same neutral prompt\n")
        # Material that must never be picked up by a recursive copy.
        for relative in ("tests/fixtures/secret.txt", "tests/evaluations/secret.txt",
                         "tests/runs/history.txt", ".git/private.txt"):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must remain outside participant copies\n")
        self.a, self.b = self.base / "A", self.base / "B"
        self.record = self.base / "record.json"

    def prepare(self):
        return PACK["prepare"](self.source, self.a, self.b, self.record)

    def test_common_bytes_equal_and_only_b_has_instructions(self):
        manifest = self.prepare()
        for relative in PACK["COMMON"]:
            self.assertEqual((self.a / relative).read_bytes(), (self.b / relative).read_bytes())
        for relative in PACK["INSTRUCTIONS"]:
            self.assertFalse((self.a / relative).exists())
            self.assertEqual((self.b / relative).read_bytes(), (self.source / relative).read_bytes())
        self.assertEqual(len(list(self.a.rglob("*.txt"))), 1)  # requirements only
        self.assertFalse((self.a / ".git").exists())
        self.assertFalse((self.b / "tests").exists())
        self.assertEqual(PACK["verify"](manifest)["technical_read_isolation"], "NOT_ESTABLISHED")

    def test_changed_input_is_detected(self):
        manifest = self.prepare()
        (self.a / "case/inputs/events.csv").write_text("modified\n")
        with self.assertRaisesRegex(ValueError, "missing/changed case/inputs/events.csv"):
            PACK["verify"](manifest)
        self.assertNotEqual((self.a / "case/inputs/events.csv").read_bytes(),
                            (self.b / "case/inputs/events.csv").read_bytes())

    def test_extra_hidden_file_or_empty_directory_is_detected(self):
        manifest = self.prepare()
        for relative, is_directory in ((".hidden", False), ("unexpected", True)):
            path = self.a / relative
            path.mkdir() if is_directory else path.write_text("extra\n")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                PACK["verify"](manifest)
            path.rmdir() if is_directory else path.unlink()

    def test_workspace_symlink_is_rejected(self):
        manifest = self.prepare()
        try:
            (self.a / "outside").symlink_to(self.source, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symbolic link forbidden"):
            PACK["verify"](manifest)

    def test_hardlink_between_copies_is_rejected(self):
        manifest = self.prepare()
        target = self.b / "SOURCE_BRIEF.md"
        target.unlink()
        try:
            os.link(self.a / "SOURCE_BRIEF.md", target)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "hard link forbidden"):
            PACK["verify"](manifest)

    def test_existing_workspaces_are_never_overwritten(self):
        manifest = self.prepare()
        with self.assertRaisesRegex(ValueError, "refusing to replace"):
            self.prepare()
        PACK["verify"](manifest)

    def test_source_symlink_is_rejected_before_copying(self):
        original = self.source / "tools/case.py"
        original.unlink()
        try:
            original.symlink_to(self.source / "tools/sources.py")
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symbolic link forbidden"):
            self.prepare()
        self.assertFalse(self.a.exists())
        self.assertFalse(self.b.exists())

    def test_after_run_allows_outputs_but_protects_original_brief(self):
        manifest = self.prepare()
        (self.a / "case/result.txt").write_text("synthetic output placeholder\n")
        (self.b / "case/brief.md").write_text("working brief additions\n")
        PACK["verify"](manifest, after_run=True)
        with self.assertRaises(ValueError):
            PACK["verify"](manifest)
        (self.a / "SOURCE_BRIEF.md").write_text("changed original\n")
        with self.assertRaisesRegex(ValueError, "SOURCE_BRIEF.md"):
            PACK["verify"](manifest, after_run=True)


if __name__ == "__main__":
    unittest.main()

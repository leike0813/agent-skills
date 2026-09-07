import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class CitationMaterializationTests(unittest.TestCase):
    def run_fix(self, candidate, output):
        return subprocess.run(
            [sys.executable, "-B", "-m", "analysis_runtime.deterministic_core",
             "render_and_validate", "--mode", "fix", "--out-dir", str(output)],
            input=json.dumps(candidate), text=True, capture_output=True,
            env={**os.environ, "PYTHONPATH": str(SCRIPTS)}, check=False,
        )

    def test_invalid_citation_is_rejected_without_overwriting_artifacts(self):
        for citation in (
            {"items": [{"ref_index": 1, "mentions": [{"snippet": "retain me"}]}]},
            {"schema": "citation_analysis_artifact.v1", "items": []},
            None,
        ):
            with self.subTest(citation=citation), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                existing = output / "citation_analysis.json"
                existing.write_text("existing citation evidence", encoding="utf-8")
                result = self.run_fix({"citation_analysis": citation}, output)
                self.assertEqual(result.returncode, 2, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual((payload.get("error") or {}).get("code"), "invalid_citation_artifact")
                self.assertEqual(existing.read_text(encoding="utf-8"), "existing citation evidence")
                self.assertEqual(list(output.iterdir()), [existing])

    def test_valid_canonical_citation_is_preserved(self):
        citation = {
            "schema": "citation_analysis_artifact.v1",
            "meta": {
                "language": "zh-CN",
                "scope": {"section_title": "Introduction", "line_start": 0, "line_end": 0},
                "scope_source": None,
                "scope_decision": {"selection_reason": None, "covered_sections": [],
                                   "fallback_from": None, "fallback_reason": None},
                "mapping_reliability": "normal",
                "reference_extraction": {"status": "completed"},
            },
            "summary": "Preserve this analysis",
            "timeline": {name: {"summary": "", "sourceReferenceIds": []}
                         for name in ("early", "mid", "recent")},
            "items": [],
            "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = self.run_fix({"citation_analysis": citation}, output)
            payload = json.loads(result.stdout)
            self.assertIsNone(payload.get("error"), result.stdout + result.stderr)
            self.assertEqual(json.loads((output / "citation_analysis.json").read_text(encoding="utf-8")), citation)


if __name__ == "__main__":
    unittest.main()

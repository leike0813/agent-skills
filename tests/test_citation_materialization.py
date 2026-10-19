from contextlib import closing
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_runtime import runtime, runtime_db  # noqa: E402


def matching_metadata():
    return {
        "schema": "literature_matching_metadata.v1",
        "key_terms": ["synthetic analysis"],
        "methods": [],
        "problems": [],
        "datasets": [],
        "exclude_terms": [],
    }


class CitationMaterializationTests(unittest.TestCase):
    def prepare_runtime(self, output, *, score_only=False):
        source = output / "source.md"
        source.write_text("# Synthetic paper\nA synthetic finding.\n", encoding="utf-8")
        paths = runtime.initialize_runtime(
            working_dir=output, db_path=runtime.default_db_path(output),
            output_dir=output, source_path=source, language="en-US",
            model="synthetic", score_only=score_only,
        )
        runtime.persist_default_templates(db_path=paths.db_path, runtime_paths=paths, language="en-US")
        score = {
            "schema": "literature_score.v1", "rubric_id": "synthetic.v1",
            "paper_type": "empirical", "paper_type_reason": "Synthetic experiment.",
            "overall_score": 60, "confidence": 0.8, "confidence_adjusted_score": 48,
            "dimensions": [{
                "dimension_key": key, "name": key,
                "configured_weight": 1 / 6, "effective_weight": 1 / 6,
                "raw_score": 6, "applicable_max_score": 10,
                "score": 60, "confidence": 0.8, "summary": "Synthetic evidence.",
                "criteria": [{"criterion_key": key, "name": key, "status": "scored",
                              "score": 6, "max_score": 10, "reason": "Synthetic evidence.", "evidence": []}],
            } for key in ("methodological_rigor", "evidence_completeness", "reproducibility",
                          "innovation_signals", "research_impact_potential", "writing_quality")],
        }
        with closing(runtime_db.connect_db(paths.db_path)) as connection:
            runtime_db.store_source_document(connection, doc_key="normalized_source",
                                             content=source.read_text(encoding="utf-8"), metadata={})
            runtime_db.store_literature_matching_metadata(connection, matching_metadata())
            runtime_db.store_literature_score(connection, score)
            runtime_db.store_citation_timeline(connection, {
                key: {"summary": "", "ref_indexes": []} for key in ("early", "mid", "recent")
            })
            runtime_db.store_citation_summary(connection, "Synthetic citation summary.")
            for action in ("persist_literature_score", "prepare_citation_workset",
                           "persist_citation_semantics", "persist_citation_timeline", "persist_citation_summary"):
                runtime_db.store_action_receipt(connection, action_name=action, stage="stage_6_citation")
            connection.commit()
        return paths

    def run_finalize(self, paths):
        # Release setup connections retained by SQLite cycles before Windows removes the temporary DB.
        gc.collect()
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "run_analysis.py"),
             "finalize_outputs", "--db-path", str(paths.db_path)],
            text=True, encoding="utf-8", capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
        )

    def test_finalize_outputs_renders_full_artifacts_and_matching_result_mirror(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare_runtime(Path(directory))
            result = self.run_finalize(paths)
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(payload.get("error"))
            for key in ("digest_path", "references_path", "citation_analysis_path",
                        "literature_matching_metadata_path", "literature_score_path"):
                self.assertTrue(payload[key], key)
                self.assertTrue(Path(payload[key]).is_file(), key)
            self.assertEqual(json.loads(Path(payload["literature_matching_metadata_path"]).read_text(encoding="utf-8")), matching_metadata())
            self.assertEqual(json.loads(paths.result_json_path.read_text(encoding="utf-8")), payload)

    def test_finalize_outputs_rejects_invalid_matching_metadata(self):
        valid = matching_metadata()
        invalid_cases = {
            "missing": {key: value for key, value in valid.items() if key != "methods"},
            "wrong_schema": {**valid, "schema": "synthesis.literature_matching_metadata.v1"},
            "wrong_type": {**valid, "methods": "synthetic"},
            "wrong_item_type": {**valid, "methods": [1]},
            "unknown": {**valid, "unexpected": True},
            "wrapper": {"literature_matching_metadata": valid},
            **{f"oversized_{key}": {**valid, key: ["synthetic"] * (limit + 1)}
               for key, limit in (("key_terms", 12), ("methods", 8), ("problems", 8),
                                  ("datasets", 8), ("exclude_terms", 6))},
        }
        for name, metadata in invalid_cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                paths = self.prepare_runtime(Path(directory))
                with closing(runtime_db.connect_db(paths.db_path)) as connection:
                    runtime_db.store_literature_matching_metadata(connection, metadata)
                    connection.commit()
                result = self.run_finalize(paths)
                payload = json.loads(result.stdout)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(payload["error"]["code"], "citation_report_failed")
                self.assertFalse(payload["literature_matching_metadata_path"])
                self.assertFalse((paths.output_dir / "literature_matching_metadata.json").exists())

    def test_finalize_outputs_preserves_score_only_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare_runtime(Path(directory), score_only=True)
            result = self.run_finalize(paths)
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(payload.get("error"))
            self.assertEqual(json.loads(Path(payload["literature_score_path"]).read_text(encoding="utf-8"))["schema"], "literature_score.v1")
            self.assertEqual(payload["literature_matching_metadata_path"], "")

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

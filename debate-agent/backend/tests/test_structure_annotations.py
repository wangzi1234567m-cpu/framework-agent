import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "annotate_structure.py"
spec = importlib.util.spec_from_file_location("structure_annotations", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StructureAnnotationTests(unittest.TestCase):
    def test_quotes_and_argument_boundaries_preserve_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.md"
            content = "# Motion\n\n## 【论点1】Claim\n\nBecause process.\n\n## Defense\n\nResponse.\n"
            path.write_text(content, encoding="utf-8")
            sample = module.annotate(path)
            self.assertEqual(path.read_text(encoding="utf-8"), content)
            units = sample["units"]
            self.assertEqual(units[1]["type"], "CLAIM")
            self.assertEqual(units[1]["argument_ref"], units[2]["argument_ref"])
            self.assertIsNone(units[-1]["argument_ref"])
            for unit in units:
                loc = unit["locator"]
                self.assertEqual(unit["text"], "\n".join(content.splitlines()[loc["start"] - 1:loc["end"]]))
                self.assertEqual(unit["review"]["status"], "PENDING")
            output = Path(directory) / "output"
            output.mkdir()
            (output / f'{sample["sample_id"]}.json').write_text(json.dumps(sample), encoding="utf-8")
            (output / "structure-v1.json").write_text('{"rules":[]}', encoding="utf-8")
            module.validate(Path(directory), output)
            path.write_text(content + "Changed", encoding="utf-8")
            with self.assertRaises(AssertionError):
                module.validate(Path(directory), output)

    def test_method_manifests_resolve_to_rule_sources(self):
        knowledge = SCRIPT.parents[1] / "knowledge"
        rules = {rule["rule_id"]: rule for rule in json.loads(
            (knowledge / "rules" / "structure-v1.json").read_text(encoding="utf-8"))["rules"]}
        samples = {sample["sample_id"] for sample in json.loads(
            (knowledge / "samples" / "index.json").read_text(encoding="utf-8"))["samples"]}
        for name in ("topic-analysis", "framework-building"):
            manifest = json.loads((knowledge / "skills" / name / "0.1.0" / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["rule_ids"])
            self.assertTrue(manifest["source_sample_ids"])
            self.assertTrue(set(manifest["source_sample_ids"]) <= samples)
            for rule_id in manifest["rule_ids"]:
                self.assertIn(rule_id, rules)
                self.assertTrue({support["sample_id"] for support in rules[rule_id]["support"]}
                                <= set(manifest["source_sample_ids"]))

    def test_rubric_weights_and_aesthetic_separation(self):
        rubric = json.loads((SCRIPT.parents[1] / "knowledge" / "evals" / "rubric.json").read_text(encoding="utf-8"))
        dimensions = {dimension["key"] for dimension in rubric["dimensions"]}
        groups = rubric["aggregation"]["weights"]
        self.assertAlmostEqual(sum(group["weight"] for group in groups), 1)
        included = {key for group in groups for key in group["dims"]}
        self.assertTrue(included <= dimensions)
        self.assertFalse(set(rubric["aesthetics"]["dims"]) & included)
        topic = next(d for d in rubric["dimensions"] if d["key"] == "topic_and_criteria")
        self.assertEqual(set(topic["anchors"]), {"1", "3", "5"})

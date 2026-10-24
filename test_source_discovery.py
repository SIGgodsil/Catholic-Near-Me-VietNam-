import csv
import tempfile
import unittest
from pathlib import Path

from source_discovery import build_candidates, main


class SourceDiscoveryTests(unittest.TestCase):
    def test_empty_feature_collection_has_no_rows(self):
        self.assertEqual(build_candidates({"type": "FeatureCollection", "features": []}), [])

    def test_features_without_names_are_skipped(self):
        document = {
            "features": [
                {"id": "node/1", "properties": {}},
                {"id": "node/2", "properties": {"name": "  "}},
            ]
        }
        self.assertEqual(build_candidates(document), [])

    def test_missing_features_array_is_rejected_clearly(self):
        with self.assertRaisesRegex(ValueError, "features"):
            build_candidates({"type": "FeatureCollection"})

    def test_named_feature_needs_manual_search_and_never_gets_a_url(self):
        rows = build_candidates({
            "features": [{"id": "way/42", "properties": {"name": "Nhà thờ Mẫu"}}]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["osm_type"], "way")
        self.assertEqual(rows[0]["osm_id"], "42")
        self.assertIn("giờ lễ giáo xứ giáo phận TP.HCM", rows[0]["search_query"])
        self.assertEqual(rows[0]["source_url"], "")
        self.assertEqual(rows[0]["verification_status"], "needs_search")

    def test_cli_empty_file_writes_headers_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "empty.geojson"
            output_path = root / "source_candidates.csv"
            input_path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            self.assertEqual(main([str(input_path), "--output", str(output_path)]), 0)
            with output_path.open(encoding="utf-8-sig", newline="") as output_file:
                self.assertEqual(list(csv.DictReader(output_file)), [])

    def test_cli_reports_a_missing_input_file(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.geojson"
            self.assertEqual(main([str(missing_path)]), 2)


if __name__ == "__main__":
    unittest.main()

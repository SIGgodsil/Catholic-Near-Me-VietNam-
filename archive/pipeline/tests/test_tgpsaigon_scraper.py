import unittest

from tgpsaigon_scraper import (
    deduplicate_parishes,
    make_parish_record,
    normalize_url,
    parse_parishes,
)


class TGPSaigonScraperTests(unittest.TestCase):
    def test_normalizes_relative_and_absolute_urls(self):
        self.assertEqual(
            normalize_url("/gioi-thieu-giao-xu/gx-a"),
            "https://tgpsaigon.net/gioi-thieu-giao-xu/gx-a",
        )
        self.assertEqual(
            normalize_url("https://example.com/gx-a"),
            "https://example.com/gx-a",
        )

    def test_builds_record_with_source_listed_status(self):
        row = make_parish_record(" Bình An ", "12", " Xứ A ", " Địa chỉ A ", "/gx-a")
        self.assertEqual(row, {
            "deanery_name": "Bình An",
            "deanery_id": "12",
            "parish_name": "Xứ A",
            "parish_address": "Địa chỉ A",
            "parish_url": "https://tgpsaigon.net/gx-a",
            "verification_status": "source_listed",
        })

    def test_deduplicates_by_case_insensitive_deanery_and_parish_name(self):
        first = make_parish_record("Bình An", "1", "Xứ A", "Địa chỉ A", "/a")
        duplicate = make_parish_record("BÌNH AN", "1", "xứ a", "Địa chỉ khác", "/b")
        other_deanery = make_parish_record("Tân Định", "2", "Xứ A", "Địa chỉ A", "/a")
        self.assertEqual(deduplicate_parishes([first, duplicate, other_deanery]), [first, other_deanery])

    def test_parses_name_and_address_from_third_cell(self):
        html = """<table><tbody><tr><td>1</td><td class="parishname">
        <a href="/gx-a">Xứ A</a></td><td>Địa chỉ A</td></tr></tbody></table>"""
        rows = parse_parishes(html, "Bình An", "12")
        self.assertEqual(rows[0]["parish_name"], "Xứ A")
        self.assertEqual(rows[0]["parish_address"], "Địa chỉ A")
        self.assertEqual(rows[0]["deanery_id"], "12")


if __name__ == "__main__":
    unittest.main()

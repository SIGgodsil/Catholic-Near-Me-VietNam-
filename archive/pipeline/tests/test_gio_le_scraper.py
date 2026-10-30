import unittest

from tgpsaigon_mass_scraper import extract_row, parse_mass_rows


def make_row(name="An Binh", href="/giao-xu/an-binh"):
    day_cells = [
        "<td><p>06:00</p><p>07:30</p></td>",
        "<td></td>",
        "<td><p>18:00</p></td>",
        "<td></td>",
        "<td><p>05:30</p></td>",
        "<td></td>",
        "<td><p>17:30</p></td>",
    ]
    return (
        '<tr class="mass-time-detail"><td>1</td>'
        f'<td><a href="{href}">{name}</a></td>{"".join(day_cells)}</tr>'
    )


class MassScraperTests(unittest.TestCase):
    def test_extracts_ordered_times_and_normalized_days(self):
        records, blanks, issues = extract_row(make_row())
        self.assertEqual([r["day_of_week"] for r in records[:2]], ["Sunday", "Sunday"])
        self.assertEqual([r["mass_time"] for r in records[:2]], ["06:00", "07:30"])
        self.assertEqual(records[2]["day_of_week"], "Tuesday")
        self.assertEqual(records[0]["parish_url"], "https://tgpsaigon.net/giao-xu/an-binh")
        self.assertEqual(records[0]["verification_status"], "source_listed")
        self.assertEqual(blanks, 3)
        self.assertEqual(issues, [])

    def test_skips_duplicate_parish_and_url_and_reports_duplicate_name(self):
        records, _, issues = parse_mass_rows([make_row(), make_row(), make_row(href="/other")])
        self.assertEqual(len(records), 10)
        self.assertTrue(any("duplicate parish and URL skipped" in issue for issue in issues))
        self.assertTrue(any("different URL" in issue for issue in issues))

    def test_preserves_but_reports_unrecognized_time_and_external_url(self):
        html = make_row(href="https://example.org/parish").replace("06:00", "6pm")
        records, _, issues = extract_row(html)
        self.assertEqual(records[0]["mass_time"], "6pm")
        self.assertTrue(any("Unrecognized time format" in issue for issue in issues))
        self.assertTrue(any("Unusual parish URL" in issue for issue in issues))

    def test_no_mass_is_a_separate_non_time_record(self):
        html = make_row(name="T&#7855;c R&#7895;i").replace(
            "<td></td>", "<td><p>Kh&#244;ng c&#243; l&#7877;</p></td>", 1
        )
        records, blanks, issues = extract_row(html)
        no_mass = [record for record in records if record["verification_status"] == "no_mass"]
        self.assertEqual(len(no_mass), 1)
        self.assertEqual(no_mass[0]["parish_name"], "Tắc Rỗi")
        self.assertEqual(no_mass[0]["day_of_week"], "Monday")
        self.assertEqual(no_mass[0]["mass_time"], "")
        self.assertEqual(sum(record["verification_status"] == "source_listed" for record in records), 5)
        self.assertEqual(blanks, 2)
        self.assertFalse(any("Unrecognized time format" in issue for issue in issues))

    def test_removes_backticks_around_mass_time(self):
        records, _, issues = extract_row(make_row().replace("06:00", "`06:00`", 1))
        self.assertEqual(records[0]["mass_time"], "06:00")
        self.assertEqual(issues, [])

    def test_normalizes_period_separator_to_colon(self):
        records, _, issues = extract_row(make_row().replace("06:00", "19.00", 1))
        self.assertEqual(records[0]["mass_time"], "19:00")
        self.assertEqual(issues, [])

    def test_removes_english_mass_note_after_time(self):
        records, _, issues = extract_row(
            make_row().replace("06:00", "16:30 ti&#7871;ng Anh", 1)
        )
        self.assertEqual(records[0]["mass_time"], "16:30")
        self.assertEqual(issues, [])

    def test_row_failure_does_not_stop_other_rows(self):
        records, _, issues = parse_mass_rows(["<tr class='wrong'></tr>", make_row()])
        self.assertEqual(len(records), 5)
        self.assertTrue(any("Row 1" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()

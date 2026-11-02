import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lead_quality
import lead_search
import lead_store
from sources import gosom

SETTINGS = lead_search.load_settings()
QUALITY = SETTINGS["lead_quality"]


def maps_row(**fields):
    row = {
        "title": "Captain Bakery",
        "place_id": "ChIJ1",
        "address": "1559 W 33rd St, Chicago",
        "review_rating": 4.8,
        "review_count": 174,
        "phone": "+1 312-791-0888",
        "web_site": "",
        "open_hours": {"Monday": ["Closed"], "Friday": ["7 AM–5:30 PM"]},
        "category": "Coffee shop",
        "latitude": 41.8,
        "longitude": -87.6,
        "link": "https://maps.example/1",
        "emails": None,
        "status": "",
        "description": "",
    }
    row.update(fields)
    return row


class LeadFromRow(unittest.TestCase):
    def test_fields_match_what_the_rest_of_the_tool_reads(self):
        lead = gosom.lead_from_row(maps_row(), QUALITY)
        self.assertEqual(lead["rating"], 4.8)
        self.assertEqual(lead["category"], "coffee_shop")
        self.assertEqual(lead["website"], "")
        self.assertEqual(lead["opening_hours"], "Monday Closed; Friday 7 AM–5:30 PM")

    def test_a_facebook_page_is_a_contact_and_not_a_website(self):
        lead = gosom.lead_from_row(maps_row(web_site="https://www.facebook.com/captainbakery"), QUALITY)
        self.assertEqual(lead["website"], "")
        self.assertEqual(lead["facebook"], "https://www.facebook.com/captainbakery")

    def test_a_business_without_reviews_has_no_rating(self):
        lead = gosom.lead_from_row(maps_row(review_count=0, review_rating=0), QUALITY)
        self.assertIsNone(lead["rating"])
        self.assertEqual(lead["review_count"], 0)


class CleanEmails(unittest.TestCase):
    def test_junk_goes_and_real_addresses_stay(self):
        found = [
            "user@domain.com",
            "13e49d785d8d4f828038b6136f3b48ba@sentry.io",
            "ninfo@jenniveesbakery.com",
            "hendrickxbakery@gmail.com",
            "logo@2x.png",
            "Hello@GoodAmbler.com",
            "hello@goodambler.com",
        ]
        self.assertEqual(
            lead_quality.clean_emails(found, QUALITY),
            ["info@jenniveesbakery.com", "hendrickxbakery@gmail.com", "hello@goodambler.com"],
        )


class Chains(unittest.TestCase):
    def test_repeated_names_and_known_chains_are_marked(self):
        leads = [{"name": "The Bakehouse - {}".format(area)} for area in ("North", "South", "West")]
        leads += [{"name": "Starbucks"}, {"name": "Captain Bakery"}]
        marked = lead_quality.mark_chains(leads, QUALITY)
        self.assertEqual([lead["chain"] for lead in marked], ["yes", "yes", "yes", "yes", ""])


class Search(unittest.TestCase):
    def test_closed_businesses_drop_and_the_limit_keeps_the_best(self):
        rows = [
            maps_row(place_id="a", title="Has site", web_site="https://a.example", phone="1"),
            maps_row(place_id="b", title="Gone", status="Permanently closed"),
            maps_row(place_id="c", title="Best"),
        ]
        settings = {"gosom": dict(SETTINGS["gosom"], executable="gosom", work_dir="x"), "lead_quality": QUALITY}
        with mock.patch.object(gosom, "_run", return_value=rows):
            found = gosom.search("bakery Chicago", 1, settings)
        self.assertEqual([lead["name"] for lead in found["leads"]], ["Best"])
        self.assertEqual(found["closed_dropped"], 1)

    def test_nothing_found_is_an_error_so_the_fallback_runs(self):
        settings = {"gosom": dict(SETTINGS["gosom"], executable="gosom", work_dir="x"), "lead_quality": QUALITY}
        with mock.patch.object(gosom, "_run", return_value=[]):
            with self.assertRaises(gosom.SourceError):
                gosom.search("bakery Chicago", 5, settings)

    def test_results_file_is_read_line_by_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.json"
            path.write_text('{"title": "One"}\nnot json\n{"title": "Two"}\n', encoding="utf-8")
            self.assertEqual([row["title"] for row in gosom._read_rows(path)], ["One", "Two"])

    def test_a_process_that_never_exits_is_ended_once_its_log_says_done(self):
        hang = "import time; print('scrapemate exited', flush=True); time.sleep(60)"
        options = dict(
            SETTINGS["gosom"],
            launcher=[],
            executable=sys.executable,
            poll_seconds=0.05,
            exit_grace_seconds=0.2,
            stop_command=[],
        )
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "run"
            with mock.patch.object(gosom, "build_command", return_value=[sys.executable, "-c", hang]):
                started = time.monotonic()
                self.assertEqual(gosom._run("bakery", options, target, False, None), [])
            self.assertLess(time.monotonic() - started, 15)

    def test_emails_are_asked_for_only_when_wanted(self):
        options = dict(SETTINGS["gosom"], executable="gosom")
        self.assertIn("-email", gosom.build_command(options, True))
        self.assertNotIn("-email", gosom.build_command(options, False))


class Merge(unittest.TestCase):
    def lead(self, place_id, phone, website=""):
        return {"place_id": place_id, "name": "Same", "score": 60, "phone": phone, "website": website}

    def test_a_new_source_replaces_the_old_row_of_the_same_phone(self):
        old = {"osm:node/1": {"place_id": "osm:node/1", "name": "Same", "phone": "+1-773-764-8877", "status": "contacted"}}
        rows = lead_store.merge([self.lead("ChIJ1", "(773) 764-8877", "https://same.example")], old)
        self.assertEqual([row["place_id"] for row in rows], ["ChIJ1"])
        self.assertEqual(rows[0]["status"], "contacted")
        self.assertEqual(rows[0]["website"], "https://same.example")


class Candidates(unittest.TestCase):
    def test_quality_rules(self):
        opts = {"min_rating": 4.0, "min_reviews": 20}
        self.assertTrue(lead_quality.meets_quality({"rating": 4.5, "review_count": 100}, opts))
        self.assertTrue(lead_quality.meets_quality({"rating": "", "review_count": ""}, opts))
        self.assertTrue(lead_quality.meets_quality({"rating": None, "review_count": None}, opts))
        self.assertFalse(lead_quality.meets_quality({"rating": 3.9, "review_count": 100}, opts))
        self.assertFalse(lead_quality.meets_quality({"rating": "", "review_count": 0}, opts))
        self.assertFalse(lead_quality.meets_quality({"rating": 4.5, "review_count": 100, "chain": "yes"}, opts))


if __name__ == "__main__":
    unittest.main()

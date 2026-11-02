import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import build_brief
import check_site
import lead_search
import pricing
from sources import gosom

SETTINGS = lead_search.load_settings()
PRICES = SETTINGS["outreach"]["pricing"]


class Quote(unittest.TestCase):
    def test_trade_sets_the_price(self):
        self.assertEqual(pricing.quote({"category": "bakery"}, "", PRICES), 350)
        self.assertEqual(pricing.quote({"category": "dentist"}, "", PRICES), 650)

    def test_a_trade_inside_a_longer_category_counts(self):
        self.assertEqual(pricing.quote({"category": "chinese_bakery"}, "", PRICES), 350)

    def test_the_search_trade_is_used_when_the_lead_has_no_category(self):
        self.assertEqual(pricing.quote({"category": ""}, "dentist", PRICES), 650)

    def test_many_reviews_raise_it(self):
        self.assertEqual(pricing.quote({"category": "bakery", "review_count": 349}, "", PRICES), 400)
        self.assertEqual(pricing.quote({"category": "bakery", "review_count": "1240"}, "", PRICES), 450)

    def test_it_stays_inside_the_limits(self):
        self.assertEqual(pricing.quote({"category": "lawyer", "review_count": 5000}, "", PRICES), 700)
        self.assertGreaterEqual(pricing.quote({"category": "kiosk"}, "", PRICES), 300)


class Description(unittest.TestCase):
    row = {
        "description": "Traditional Chinese sweet shop, featuring buns & mochi.",
        "status": "Chinese bakery for pastries",
        "user_reviews": [{"Description": "The egg tarts\nare great"}, {"Description": ""}, {"Description": "x" * 900}],
    }

    def test_gosom_keeps_both_descriptions(self):
        self.assertEqual(
            gosom._description(self.row),
            "Traditional Chinese sweet shop, featuring buns & mochi. Chinese bakery for pastries",
        )

    def test_review_notes_are_short_and_single_line(self):
        notes = gosom._review_notes(self.row, SETTINGS["gosom"]).split(" | ")
        self.assertEqual(notes[0], "The egg tarts are great")
        self.assertEqual(len(notes), 2)
        self.assertLessEqual(len(notes[1]), SETTINGS["gosom"]["review_characters"])

    def test_the_photo_search_comes_from_the_description(self):
        query = autopilot.description_query("Traditional Chinese sweet shop, featuring buns", SETTINGS)
        self.assertEqual(query, "traditional chinese sweet shop")

    def test_the_description_is_searched_first(self):
        plan = {"queries": {"hero": ["bread"], "background": ["linen"]}}
        autopilot._lead_with_description(plan, {"description": "Chinese bakery"}, SETTINGS)
        self.assertEqual(plan["queries"]["hero"], ["chinese bakery", "bread"])
        self.assertEqual(plan["queries"]["background"], ["linen"])

    def test_the_brief_carries_what_is_known(self):
        lead = {"category": "chinese_bakery", "description": "Sweet shop", "review_notes": "Egg tarts | Pineapple buns"}
        text = build_brief._known_about(lead)
        self.assertIn("Listed as: chinese bakery", text)
        self.assertIn("  - Pineapple buns", text)

    def test_nothing_known_says_so(self):
        self.assertEqual(build_brief._known_about({}), "- Nothing beyond the table above.")


class VisibleNotes(unittest.TestCase):
    def page(self, body):
        return "<html lang='en'><head><title>t</title></head><body>{}</body></html>".format(body)

    def check(self, body):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder) / "site"
            site.mkdir()
            (site / "index.html").write_text(self.page(body), encoding="utf-8")
            return check_site.check(folder)[1]

    def test_a_bracketed_note_fails(self):
        self.assertTrue(any("[Owner: list your pastries]" in item for item in self.check("<p>[Owner: list your pastries]</p>")))

    def test_comments_for_the_owner_pass(self):
        self.assertFalse(any("Visible note" in item for item in self.check("<p>Fine</p><!-- [add a story] -->")))


class OnlineContact(unittest.TestCase):
    opts = {"only_without_website": True, "require_online_contact": True}

    def fit(self, found):
        from unittest import mock

        with mock.patch.object(autopilot.contacts, "lookup", return_value=found):
            with mock.patch.object(autopilot.lead_store, "update_fields"):
                check = autopilot.contact_check("file.csv", self.opts, SETTINGS, {"name": "Chicago"})
                return check({"place_id": "a", "name": "Shop", "website": ""})

    def test_nothing_found_online_skips_the_business(self):
        self.assertFalse(self.fit({}))

    def test_a_facebook_page_is_enough(self):
        self.assertTrue(self.fit({"facebook": "https://www.facebook.com/shop/"}))

    def test_a_search_that_did_not_run_rejects_nobody(self):
        self.assertTrue(self.fit(None))


if __name__ == "__main__":
    unittest.main()

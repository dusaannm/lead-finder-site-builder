import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import contacts
import lead_search
import usage

SETTINGS = lead_search.load_settings()
QUALITY = SETTINGS["lead_quality"]


class ProfileLink(unittest.TestCase):
    def test_pages_are_kept_and_posts_are_not(self):
        self.assertEqual(
            contacts.profile_link("https://m.facebook.com/alegrebakery/posts/123"),
            ("facebook", "https://www.facebook.com/alegrebakery/"),
        )
        self.assertEqual(contacts.profile_link("https://www.instagram.com/p/abc/"), ("", ""))
        self.assertEqual(contacts.profile_link("https://www.facebook.com/sharer.php?u=x"), ("", ""))
        self.assertEqual(contacts.profile_link("https://example.com/facebook"), ("", ""))


class ContactsInHtml(unittest.TestCase):
    def test_reads_mail_links_text_and_profiles(self):
        html = """<a href="mailto:Hello@Shop.com?subject=Hi">write</a>
        <p>or info@shop.com, not user@domain.com</p>
        <a href="https://www.instagram.com/shop/">ig</a>
        <a href="https://www.facebook.com/sharer.php?u=1">share</a>"""
        found = contacts.contacts_in_html(html, QUALITY)
        self.assertEqual(found["emails"], ["hello@shop.com", "info@shop.com"])
        self.assertEqual(found["instagram"], "https://www.instagram.com/shop/")
        self.assertNotIn("facebook", found)


class ReadSite(unittest.TestCase):
    def test_stops_at_the_first_page_with_an_email(self):
        pages = {"https://shop.com": "<p>nothing here</p>", "https://shop.com/contact": "<p>a@gmail.com b@shop.com</p>"}
        asked = []

        def page(url, options):
            asked.append(url)
            return pages.get(url, "")

        with mock.patch.object(contacts, "_page_html", side_effect=page):
            found = contacts.read_site("https://shop.com", SETTINGS)
        self.assertEqual(found["emails"], ["b@shop.com", "a@gmail.com"])
        self.assertEqual(asked, ["https://shop.com", "https://shop.com/contact"])


class ReadResults(unittest.TestCase):
    lead = {"name": "Captain Bakery, Inc.", "address": "1559 W 33rd St"}

    def test_official_site_profile_and_email(self):
        results = [
            {"url": "https://www.yellowpages.com/x/captain-bakery", "title": "Captain Bakery", "description": ""},
            {"url": "https://captainbakerychicago.com/menu", "title": "Captain Bakery Menu", "description": "Fresh bread"},
            {
                "url": "https://www.facebook.com/captainbakery/about",
                "title": "Captain Bakery | Chicago",
                "description": "Write to captainbakery@gmail.com",
            },
        ]
        found = contacts.read_results(self.lead, results, SETTINGS)
        self.assertEqual(found["website"], "https://captainbakerychicago.com/")
        self.assertEqual(found["facebook"], "https://www.facebook.com/captainbakery/")
        self.assertEqual(found["email"], "captainbakery@gmail.com")

    def test_a_directory_subdomain_is_not_the_business_website(self):
        results = [{"url": "https://captain-bakery.wheree.com/", "title": "Captain Bakery reviews", "description": ""}]
        self.assertEqual(contacts.read_results(self.lead, results, SETTINGS), {})

    def test_a_country_domain_with_two_parts_is_read_correctly(self):
        results = [{"url": "https://www.captainbakery.co.uk/", "title": "Captain Bakery", "description": ""}]
        found = contacts.read_results(self.lead, results, SETTINGS)
        self.assertEqual(found["website"], "https://www.captainbakery.co.uk/")

    def test_a_result_about_another_business_gives_nothing(self):
        results = [
            {
                "url": "https://www.facebook.com/otherbakery",
                "title": "Other Bakery",
                "description": "hello@otherbakery.com",
            }
        ]
        self.assertEqual(contacts.read_results(self.lead, results, SETTINGS), {})


class Lookup(unittest.TestCase):
    lead = {"place_id": "a", "name": "Captain Bakery", "website": ""}
    settings = dict(SETTINGS, contacts=dict(SETTINGS["contacts"], search_pause_seconds=0))

    def test_second_lookup_reads_the_cache_and_spends_nothing(self):
        results = [{"url": "https://www.instagram.com/captainbakery/", "title": "Captain Bakery", "description": ""}]
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(contacts, "web_search", return_value=results) as search:
                first = contacts.lookup(self.lead, self.settings, root, "key", "Chicago", "us")
                second = contacts.lookup(self.lead, self.settings, root, "key", "Chicago", "us")
            self.assertEqual(search.call_count, 1)
            self.assertEqual(first, second)
            self.assertEqual(usage.read(root, contacts.USAGE_NAME)["calls"], 1)

    def test_the_monthly_limit_holds(self):
        options = dict(self.settings["contacts"], monthly_search_limit=1)
        settings = dict(SETTINGS, contacts=options)
        with tempfile.TemporaryDirectory() as root, mock.patch.object(contacts, "web_search", return_value=[]) as search:
            contacts.lookup({"place_id": "a", "name": "One"}, settings, root, "key")
            contacts.lookup({"place_id": "b", "name": "Two"}, settings, root, "key")
        self.assertEqual(search.call_count, 1)

    def test_without_a_key_nothing_is_spent(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(contacts, "web_search") as search:
            self.assertEqual(contacts.lookup(self.lead, SETTINGS, root, ""), {})
        search.assert_not_called()

    def test_a_failed_search_is_not_remembered(self):
        error = contacts.requests.ConnectionError("down")
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(contacts, "web_search", side_effect=error):
                self.assertEqual(contacts.lookup(self.lead, self.settings, root, "key"), {})
            self.assertEqual(usage.read(root, contacts.USAGE_NAME)["calls"], 0)


class FirecrawlRequest(unittest.TestCase):
    def test_request_and_reply_shape(self):
        reply = mock.Mock()
        reply.json.return_value = {"data": {"web": [{"url": "https://a.example", "title": "A"}]}}
        with mock.patch.object(contacts.requests, "post", return_value=reply) as post:
            found = contacts.web_search("query", "key", SETTINGS["contacts"], "us")
        self.assertEqual(found[0]["title"], "A")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer key")
        self.assertEqual(post.call_args.kwargs["json"]["country"], "US")


class ContactCheck(unittest.TestCase):
    opts = {"only_without_website": True}

    def row(self):
        return {"place_id": "a", "name": "Captain Bakery", "website": "", "email": ""}

    def test_a_found_website_rejects_the_lead_and_is_saved(self):
        with mock.patch.object(autopilot.contacts, "lookup", return_value={"website": "https://x.example/"}):
            with mock.patch.object(autopilot.lead_store, "update_fields") as saved:
                check = autopilot.contact_check("file.csv", self.opts, SETTINGS, {"name": "Chicago"})
                self.assertFalse(check(self.row()))
        saved.assert_called_once()

    def test_a_found_email_keeps_the_lead_and_fills_it(self):
        row = self.row()
        with mock.patch.object(autopilot.contacts, "lookup", return_value={"email": "a@b.example"}):
            with mock.patch.object(autopilot.lead_store, "update_fields"):
                check = autopilot.contact_check("file.csv", self.opts, SETTINGS, {"name": "Chicago"})
                self.assertTrue(check(row))
        self.assertEqual(row["email"], "a@b.example")


if __name__ == "__main__":
    unittest.main()

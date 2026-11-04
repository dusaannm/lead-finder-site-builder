import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lead_search
import mailer
import outreach_log

SETTINGS = lead_search.load_settings()
EASTERN = {"offset": -5, "rule": "us", "label": "NY, USA"}
TODAY = date(2026, 11, 4)


def settings():
    copied = json.loads(json.dumps(SETTINGS))
    copied["outreach"].update(sender_name="Dusan Milenkovic", postal_address="Street 1, Belgrade, Serbia", follow_up_days=4)
    copied["mailer"].update(signature_extra="Clyx Studio", first_day=15, daily_step=5, daily_most=40, follow_up=True)
    copied["mailer"].update(send_from_hour=9, send_until_hour=17, weekdays_only=True)
    copied["publish"]["address"] = ""
    return copied


def site(place_id="p1", stage="ready", **changes):
    draft = "Subject: A website for Bakery\n\nHi,\n\nI made it: https://demos.pages.dev/bakery/\n\nDusan Milenkovic\nStreet 1, Belgrade, Serbia"
    return dict(
        {
            "place_id": place_id,
            "name": "Bakery " + place_id,
            "address": "1 Main St, Albany, NY 12207, United States",
            "country_code": "us",
            "stage": stage,
            "live_url": "https://demos.pages.dev/bakery/",
            "live_public": True,
            "built_at": "2026-11-01T10:00:00",
            "brief_at": "2026-11-01T09:00:00",
            "messages": [{"title": "Email", "text": draft}],
        },
        **changes,
    )


def gathered(*sites, emails=None):
    emails = emails or {}
    return {
        "sites": list(sites),
        "businesses": {item["place_id"]: {"email": emails.get(item["place_id"], item["place_id"] + "@shop.com")} for item in sites},
    }


def sent_row(place_id="p1", kind=mailer.FIRST, on="2026-10-30T15:00:00", answer=""):
    return {
        "place_id": place_id,
        "name": "Bakery " + place_id,
        "email": place_id + "@shop.com",
        "kind": kind,
        "subject": "A website for Bakery",
        "message_id": "<{}-{}@clyxstudio.com>".format(place_id, kind),
        "sent_at": on,
        "answer": answer,
        "answer_at": "",
    }


class Limits(unittest.TestCase):
    def test_the_daily_limit_grows_with_every_day_that_sent(self):
        options = settings()["mailer"]
        self.assertEqual(mailer.daily_cap([], options, TODAY), 15)
        rows = [sent_row(on="2026-11-02T10:00:00"), sent_row("p2", on="2026-11-03T10:00:00"), sent_row("p3", on="2026-11-03T11:00:00")]
        self.assertEqual(mailer.daily_cap(rows, options, TODAY), 25)
        many = [sent_row(str(day), on="2026-10-{:02d}T10:00:00".format(day)) for day in range(1, 20)]
        self.assertEqual(mailer.daily_cap(many, options, TODAY), 40)

    def test_only_todays_emails_count_against_today(self):
        rows = [sent_row(on="2026-11-04T09:00:00"), sent_row("p2", on="2026-11-03T09:00:00")]
        self.assertEqual(mailer.sent_today(rows, TODAY), 1)


class TheirTime(unittest.TestCase):
    options = settings()["mailer"]

    def test_new_york_is_in_hours_after_its_clocks_move(self):
        summer = datetime(2026, 7, 15, 13, 30, tzinfo=timezone.utc)
        winter = datetime(2026, 1, 15, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(mailer.local_time(EASTERN, summer).hour, 9)
        self.assertTrue(mailer.in_window(EASTERN, summer, self.options))
        self.assertFalse(mailer.in_window(EASTERN, winter, self.options))

    def test_arizona_keeps_its_clock(self):
        arizona = {"offset": -7, "rule": "", "label": "AZ, USA"}
        self.assertEqual(mailer.local_time(arizona, datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc)).hour, 9)

    def test_europe_moves_its_clocks_on_the_last_sunday_of_march(self):
        berlin = {"offset": 1, "rule": "eu", "label": "DE"}
        self.assertEqual(mailer.local_time(berlin, datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)).hour, 1)
        self.assertEqual(mailer.local_time(berlin, datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)).hour, 3)

    def test_nothing_goes_out_on_their_weekend(self):
        saturday = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(mailer.in_window(EASTERN, saturday, self.options))

    def test_the_place_comes_from_the_state_or_the_country(self):
        chosen = settings()
        self.assertEqual(mailer.place_of(site(), chosen)["offset"], -5)
        texas = site(address="1 Main St, Austin, TX 78701, United States", country_code="")
        self.assertEqual(mailer.place_of(texas, chosen)["offset"], -6)
        lisbon = site(address="Rua 1, 1100-001 Lisboa, Portugal", country_code="")
        self.assertEqual(mailer.place_of(lisbon, chosen)["offset"], 0)
        self.assertIsNone(mailer.place_of(site(address="Somewhere", country_code=""), chosen))


class Queue(unittest.TestCase):
    def test_a_ready_live_site_with_an_email_is_queued_once(self):
        chosen = settings()
        found = mailer.queue(gathered(site(), site("p2")), [], set(), chosen, TODAY)
        self.assertEqual([item["place_id"] for item in found], ["p1", "p2"])
        self.assertEqual(found[0]["subject"], "A website for Bakery")
        self.assertIn("Dusan Milenkovic\nClyx Studio\nStreet 1", found[0]["body"])

    def test_contacted_mailed_skipped_and_unreachable_sites_are_left_out(self):
        chosen = settings()
        sites = [site("p1", stage="contacted"), site("p2"), site("p3"), site("p4", live_public=False), site("p5")]
        found = mailer.queue(gathered(*sites, emails={"p5": "call us"}), [sent_row("p2", on="2026-11-04T09:00:00")], {"p3"}, chosen, TODAY)
        self.assertEqual(found, [])

    def test_two_businesses_with_one_address_get_one_email(self):
        found = mailer.queue(gathered(site("p1"), site("p2"), emails={"p1": "same@shop.com", "p2": "Same@shop.com"}), [], set(), settings(), TODAY)
        self.assertEqual(len(found), 1)

    def test_the_follow_up_waits_its_days_and_stops_at_an_answer(self):
        chosen = settings()
        early = mailer.queue(gathered(site("p1", stage="contacted")), [sent_row(on="2026-11-02T10:00:00")], set(), chosen, TODAY)
        due = mailer.queue(gathered(site("p1", stage="contacted")), [sent_row(on="2026-10-30T10:00:00")], set(), chosen, TODAY)
        answered = mailer.queue(gathered(site("p1", stage="contacted")), [sent_row(answer="replied")], set(), chosen, TODAY)
        twice = mailer.queue(gathered(site("p1", stage="contacted")), [sent_row(), sent_row(kind=mailer.FOLLOW_UP)], set(), chosen, TODAY)
        self.assertEqual((early, answered, twice), ([], [], []))
        self.assertEqual(due[0]["kind"], mailer.FOLLOW_UP)
        self.assertEqual(due[0]["subject"], "Re: A website for Bakery")
        self.assertEqual(due[0]["replying_to"], "<p1-first@clyxstudio.com>")
        self.assertIn("Street 1, Belgrade, Serbia", due[0]["body"])

    def test_the_own_domain_replaces_the_pages_address(self):
        chosen = settings()
        chosen["publish"]["address"] = "https://demo.clyxstudio.com/"
        found = mailer.queue(gathered(site()), [], set(), chosen, TODAY)
        self.assertIn("https://demo.clyxstudio.com/bakery/", found[0]["body"])
        self.assertNotIn("pages.dev", found[0]["body"])


class Answers(unittest.TestCase):
    options = settings()["mailer"]
    rows = [sent_row(), sent_row(kind=mailer.FOLLOW_UP)]

    def message(self, text, sender="p1@shop.com", references=()):
        return {"from_email": sender, "text": text, "references": list(references)}

    def test_a_reply_is_matched_by_its_thread(self):
        kind, row = mailer.classify(self.message("Sounds good, call me", "owner@other.com", ["<p1-follow_up@clyxstudio.com>"]), self.rows, self.options)
        self.assertEqual((kind, row["kind"]), (mailer.REPLIED, mailer.FIRST))

    def test_a_no_is_an_opt_out(self):
        self.assertEqual(mailer.classify(self.message("No."), self.rows, self.options)[0], mailer.OPTED_OUT)
        self.assertEqual(mailer.classify(self.message("Not interested, thanks"), self.rows, self.options)[0], mailer.OPTED_OUT)

    def test_quoted_text_does_not_count(self):
        text = "Yes please, how do we start?\n\nOn Tue, Dusan wrote:\n> If you would rather not, say unsubscribe"
        self.assertEqual(mailer.classify(self.message(text), self.rows, self.options)[0], mailer.REPLIED)

    def test_a_bounce_names_the_address_it_could_not_reach(self):
        bounce = self.message("Delivery to p1@shop.com failed permanently.", "mailer-daemon@zoho.eu")
        self.assertEqual(mailer.classify(bounce, self.rows, self.options)[0], mailer.BOUNCED)
        stranger = self.message("Hello", "someone@else.com")
        self.assertEqual(mailer.classify(stranger, self.rows, self.options), (mailer.OTHER, None))

    def test_an_answer_is_written_once_and_a_no_wins(self):
        rows = [sent_row()]
        items = [
            {"from_email": "p1@shop.com", "text": "Tell me more", "references": [], "date": "2026-11-04T10:00:00"},
            {"from_email": "p1@shop.com", "text": "Actually no thanks", "references": [], "date": "2026-11-04T11:00:00"},
        ]
        changes = mailer._apply_answers(items, rows, self.options)
        self.assertEqual(rows[0]["answer"], mailer.OPTED_OUT)
        self.assertEqual(changes, [("p1", "replied"), ("p1", "declined")])


class Sending(unittest.TestCase):
    def test_a_sent_email_is_logged_and_marks_the_business_contacted(self):
        with tempfile.TemporaryDirectory() as folder:
            chosen = settings()
            item = mailer.queue(gathered(site()), [], set(), chosen, TODAY)[0]
            with mock.patch.object(mailer, "credentials", return_value=("dusan@clyxstudio.com", "x")), mock.patch.object(
                mailer, "deliver"
            ) as deliver:
                mailer.send(item, chosen, folder)
            message = deliver.call_args[0][0]
            self.assertEqual(message["To"], "p1@shop.com")
            self.assertIn("unsubscribe", message["List-Unsubscribe"])
            self.assertEqual(mailer.load_log(folder)[0]["message_id"], message["Message-ID"])
            self.assertEqual(outreach_log.load(folder)[0]["channel"], "email")

    def test_the_next_email_waits_for_their_hours_unless_sent_now(self):
        with tempfile.TemporaryDirectory() as folder:
            chosen = settings()
            night = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)
            with mock.patch.object(mailer.dashboard, "gather", return_value=gathered(site())):
                waiting, note = mailer.next_email(chosen, folder, TODAY, night)
                mailer.set_control(folder, send_now=TODAY.isoformat())
                now, _ = mailer.next_email(chosen, folder, TODAY, night)
            self.assertIsNone(waiting)
            self.assertIn("Waiting", note)
            self.assertEqual(now["place_id"], "p1")

    def test_the_next_email_stops_at_the_daily_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            chosen = settings()
            chosen["mailer"]["first_day"] = 1
            mailer._save_log([sent_row("p9", on="2026-11-04T08:00:00")], folder)
            with mock.patch.object(mailer.dashboard, "gather", return_value=gathered(site())):
                item, note = mailer.next_email(chosen, folder, TODAY, datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc))
            self.assertIsNone(item)
            self.assertIn("Today's 1 emails are sent", note)

    def test_sending_is_off_until_it_is_turned_on(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(mailer.wanted(folder, TODAY))
            mailer.set_control(folder, on=True)
            self.assertTrue(mailer.wanted(folder, TODAY))
            with mock.patch.object(mailer, "is_set_up", return_value=False), mock.patch.object(mailer.subprocess, "Popen") as popen:
                self.assertFalse(mailer.ensure_worker(settings(), folder))
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

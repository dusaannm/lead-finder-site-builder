import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import dashboard
import lead_search
import night_shift
import shift_control

SETTINGS = lead_search.load_settings()


class Cards(unittest.TestCase):
    def test_the_card_is_the_first_screen_of_the_page(self):
        with tempfile.TemporaryDirectory() as folder:
            screens = Path(folder) / "screens"
            screens.mkdir()
            Image.new("RGB", (1920, 1200), "white").save(screens / "desktop.png")
            card = dashboard.card_picture(folder, SETTINGS)
            with Image.open(card) as image:
                self.assertEqual(image.size, (640, 400))

    def test_without_a_page_photo_a_stock_picture_is_used(self):
        with tempfile.TemporaryDirectory() as folder:
            hero = Path(folder) / "assets" / "hero"
            hero.mkdir(parents=True)
            Image.new("RGB", (10, 10)).save(hero / "one.jpg")
            self.assertEqual(dashboard.card_picture(folder, SETTINGS).name, "one.jpg")


class Counts(unittest.TestCase):
    def test_a_phone_is_not_an_online_contact(self):
        self.assertFalse(dashboard._is_reachable({"phone": "+1 555", "email": " "}))
        self.assertTrue(dashboard._is_reachable({"instagram": "https://www.instagram.com/x/"}))


class Publishing(unittest.TestCase):
    def test_a_run_publishes_nothing_when_publishing_is_off(self):
        settings = json.loads(json.dumps(SETTINGS))
        settings["autopilot"]["deploy"] = False
        with mock.patch.object(autopilot.publish_site, "publish") as publish:
            self.assertEqual(autopilot.publish_finished(settings), [])
        publish.assert_not_called()

    def test_a_run_publishes_what_it_finished(self):
        settings = json.loads(json.dumps(SETTINGS))
        settings["autopilot"]["deploy"] = True
        site = {"name": "A"}
        with mock.patch.object(autopilot.publish_site, "is_set_up", return_value=True), mock.patch.object(
            autopilot.publish_site, "unpublished_sites", return_value=[site]
        ), mock.patch.object(autopilot.publish_site, "publish", return_value={"a": site}) as publish:
            self.assertEqual(autopilot.publish_finished(settings), [site])
        publish.assert_called_once()


class Cities(unittest.TestCase):
    opts = autopilot.options(SETTINGS)

    def test_every_state_and_every_eu_country_is_in_the_list(self):
        states = {city["state"] for city in autopilot.cities_in("us", self.opts)}
        countries = {city["country"] for city in autopilot.cities_in("europe", self.opts)}
        self.assertEqual(len(states), 51)
        self.assertEqual(len(countries), 28)

    def test_both_regions_together_are_the_whole_list(self):
        self.assertEqual(
            len(autopilot.cities_in("both", self.opts)),
            len(autopilot.cities_in("us", self.opts)) + len(autopilot.cities_in("europe", self.opts)),
        )

    def test_cities_with_the_same_name_are_searched_apart(self):
        maine = {"name": "Portland", "state": "Maine"}
        oregon = {"name": "Portland", "state": "Oregon"}
        self.assertEqual(autopilot.search_text("barber", maine), "barber Portland Maine")
        self.assertNotEqual(night_shift.pair_key(maine, "barber"), night_shift.pair_key(oregon, "barber"))


class Stopping(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "a wrapper process is how Claude Code starts on Windows")
    def test_a_builder_behind_a_wrapper_ends_too(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "pid.txt"
            child = "import os,time;open(r'{}','w').write(str(os.getpid()));time.sleep(60)".format(marker)
            process = subprocess.Popen(["cmd", "/c", sys.executable, "-c", child])
            while not (marker.exists() and marker.read_text()):
                time.sleep(0.05)
            autopilot._end(process)
            time.sleep(0.3)
            self.assertFalse(shift_control.is_alive(int(marker.read_text())))


class Currency(unittest.TestCase):
    def test_the_builder_gets_the_currency_of_the_city_chosen_before_it(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = json.loads(json.dumps(SETTINGS))
            answers = Path(folder) / "answers.json"
            lead = {"place_id": "p", "name": "Kvety", "category": "florist"}
            stock = Path(folder) / "stock"
            stock.mkdir()
            (stock / "sources.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(autopilot.build_brief, "find_lead", return_value=(lead, None)), mock.patch.object(
                autopilot, "answers_file", return_value=answers
            ), mock.patch.object(autopilot, "stock_folder", return_value=stock), mock.patch.object(
                autopilot, "save_reference_photo", return_value=""
            ):
                autopilot.prepare("p", {"name": "Prague", "country": "Czechia", "language": "Czech", "currency": "€"}, "florist", settings)
                again = autopilot.prepare("p", settings=settings)
            self.assertTrue(again["price"].startswith("€"))


class Autopilot(unittest.TestCase):
    def test_the_count_comes_from_the_latest_run_only(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "data" / "autopilot" / "night.log"
            log.parent.mkdir(parents=True)
            log.write_text(
                "1 Shift starts: a\n2 3 built this search, 3 tonight, 3 published.\n"
                "3 Shift ends: b\n4 Shift starts: c\n5 2 built this search, 2 tonight, 2 published.\n",
                encoding="utf-8",
            )
            lines = shift_control.latest_lines(folder)
            self.assertEqual(len(lines), 2)
            self.assertEqual(shift_control.built_so_far(lines), 2)

    def test_the_way_it_ended_is_read_from_the_log(self):
        self.assertEqual(shift_control.how_it_ended([]), "")
        self.assertEqual(shift_control.how_it_ended(["Shift starts: a"]), "crashed")
        self.assertEqual(shift_control.how_it_ended(["The weekly Claude limit reached", "Shift ends: x"]), "weekly_limit")
        self.assertEqual(shift_control.how_it_ended(["Stop file found.", "Shift ends: x"]), "by_hand")

    def test_a_second_start_is_refused_while_it_is_on(self):
        with tempfile.TemporaryDirectory() as folder:
            record = Path(folder) / "data" / "autopilot" / "shift.json"
            record.parent.mkdir(parents=True)
            record.write_text(json.dumps({"pid": 1}), encoding="utf-8")
            with mock.patch.object(shift_control, "is_alive", return_value=True):
                with self.assertRaises(shift_control.ShiftError):
                    shift_control.start("us", SETTINGS, folder)

    def test_an_unknown_region_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(shift_control.ShiftError):
                shift_control.start("mars", SETTINGS, folder)

    def test_no_limits_keeps_searching_until_the_stop_file(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = json.loads(json.dumps(SETTINGS))
            settings["night"]["pause_minutes"] = 0
            searches = []

            def one_search(settings, opts, say, stop_event, rng=None):
                searches.append(1)
                if len(searches) == 3:
                    night_shift.stop_file(folder).touch()
                    stop_event.set()
                return mock.Mock(state={"candidates": [], "source": "gosom"})

            stop_path = Path(folder) / "data" / "autopilot" / "STOP"
            stop_path.parent.mkdir(parents=True)
            with mock.patch.object(night_shift, "ROOT", Path(folder)), mock.patch.object(
                night_shift, "_one_search", one_search
            ), mock.patch.object(night_shift, "_publish", return_value=0), mock.patch.object(night_shift.ready_list, "write"):
                built, _ = night_shift.shift(0, 0, settings, lambda text: None)
            self.assertEqual((built, len(searches)), (0, 3))


if __name__ == "__main__":
    unittest.main()

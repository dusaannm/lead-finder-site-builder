import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import dashboard
import lead_search
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


class Batches(unittest.TestCase):
    def test_the_count_comes_from_the_latest_batch_only(self):
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

    def test_a_second_batch_is_refused_while_one_goes(self):
        with tempfile.TemporaryDirectory() as folder:
            record = Path(folder) / "data" / "autopilot" / "shift.json"
            record.parent.mkdir(parents=True)
            record.write_text(json.dumps({"pid": 1}), encoding="utf-8")
            with mock.patch.object(shift_control, "is_alive", return_value=True):
                with self.assertRaises(shift_control.ShiftError):
                    shift_control.start(1, 1, SETTINGS, folder)

    def test_a_bad_number_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(shift_control.ShiftError):
                shift_control.start("many", 1, SETTINGS, folder)


if __name__ == "__main__":
    unittest.main()

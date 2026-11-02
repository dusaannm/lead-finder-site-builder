import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import night_shift
import publish_site

OPTIONS = {"demo_note": "Demo by {sender} for {name}."}
PAGE = "<html><head><title>t</title></head><body class='x'><img src=\"../assets/hero/a.jpg\"></body></html>"


class Stage(unittest.TestCase):
    def build(self, root):
        folder = Path(root) / "Shop"
        (folder / "site").mkdir(parents=True)
        (folder / "assets" / "hero").mkdir(parents=True)
        (folder / "site" / "index.html").write_text(PAGE, encoding="utf-8")
        (folder / "site" / "style.css").write_text("a{background:url(../assets/hero/b.jpg)}", encoding="utf-8")
        (folder / "assets" / "hero" / "a.jpg").write_bytes(b"a")
        (folder / "assets" / "hero" / "b.jpg").write_bytes(b"b")
        (folder / "assets" / "hero" / "unused.jpg").write_bytes(b"c")
        (folder / "assets" / "sources.json").write_text("{}", encoding="utf-8")
        (folder / "brief.md").write_text("private", encoding="utf-8")
        (folder / "outreach.md").write_text("private", encoding="utf-8")
        return folder

    def test_only_the_site_and_its_photographs_are_published(self):
        with tempfile.TemporaryDirectory() as root:
            folder = self.build(root)
            target = Path(root) / "out" / "shop"
            publish_site.stage(folder, target, "Shop", "Dusan", OPTIONS)
            names = sorted(str(path.relative_to(target)).replace("\\", "/") for path in target.rglob("*") if path.is_file())
            page = (target / "index.html").read_text(encoding="utf-8")
            style = (target / "style.css").read_text(encoding="utf-8")
        self.assertEqual(names, ["assets/hero/a.jpg", "assets/hero/b.jpg", "index.html", "style.css"])
        self.assertIn('src="assets/hero/a.jpg"', page)
        self.assertIn("url(assets/hero/b.jpg)", style)

    def test_a_demo_says_so_and_stays_out_of_search(self):
        page = publish_site.demo_marked(PAGE, "A & B", "Dusan", OPTIONS)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page)
        self.assertIn("Demo by Dusan for A &amp; B.", page)
        self.assertLess(page.index("<body"), page.index("Demo by"))

    def test_the_link_lands_in_the_messages(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "outreach.md"
            path.write_text("See [link to the demo site] now", encoding="utf-8")
            publish_site.fill_link(root, "https://demo.example/shop/")
            self.assertEqual(path.read_text(encoding="utf-8"), "See https://demo.example/shop/ now")

    def test_slugs_stay_web_safe(self):
        self.assertEqual(publish_site.slug_for("Cuenca’s Bakery", "Chicago"), "cuenca-s-bakery-chicago")


class NextPair(unittest.TestCase):
    opts = {
        "cities_from": "us",
        "cities": [{"name": "Chicago", "country": "United States"}, {"name": "Paris", "country": "France"}],
        "trades": ["bakery", "plumber"],
    }

    def test_a_tried_search_is_not_repeated(self):
        city, trade = night_shift.next_pair(self.opts, ["bakery-chicago"])
        self.assertEqual((city["name"], trade), ("Chicago", "plumber"))

    def test_when_all_are_tried_it_starts_again(self):
        self.assertEqual(night_shift.next_pair(self.opts, ["bakery-chicago", "plumber-chicago"])[0]["name"], "Chicago")


class PlanLimits(unittest.TestCase):
    options = {"stop_at_weekly": 0.6, "pause_at_five_hour": 0.85, "after_reset_seconds": 120}

    def test_low_usage_goes_on(self):
        levels = {"five_hour": {"utilization": 0.5}, "seven_day": {"utilization": 0.3}}
        self.assertEqual(night_shift.plan_verdict(levels, self.options), ("go", 0))

    def test_the_week_ends_the_shift(self):
        levels = {"five_hour": {"utilization": 0.1}, "seven_day": {"utilization": 0.6}}
        self.assertEqual(night_shift.plan_verdict(levels, self.options)[0], "stop")

    def test_the_five_hour_limit_waits_for_its_reset(self):
        levels = {"five_hour": {"utilization": 0.9, "resetsAt": 1000}, "seven_day": {"utilization": 0.3}}
        self.assertEqual(night_shift.plan_verdict(levels, self.options, now=400), ("wait", 720))

    def test_unknown_usage_goes_on(self):
        self.assertEqual(night_shift.plan_verdict({}, self.options), ("go", 0))


class ReadySites(unittest.TestCase):
    def test_only_finished_sites_go_out(self):
        run = mock.Mock(
            state={
                "candidates": [
                    {"place_id": "a", "name": "A", "city": "X", "country_code": "us", "folder": "f", "state": "done"},
                    {"place_id": "b", "name": "B", "city": "X", "folder": "g", "state": "attention"},
                ]
            }
        )
        self.assertEqual([site["place_id"] for site in night_shift._ready_sites(run)], ["a"])


if __name__ == "__main__":
    unittest.main()

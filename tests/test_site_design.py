import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import add_fonts
import autopilot
import build_brief
import check_site
import lead_search
import screenshot_site
from sources import gosom

SETTINGS = lead_search.load_settings()
PAGE = """<!doctype html><html lang="en"><head><title>T</title>
<meta name="description" content="d"><meta name="viewport" content="width=device-width">
<script type="application/ld+json">{{}}</script></head><body><h1>Name</h1>{body}</body></html>"""


def problems_of(body):
    with tempfile.TemporaryDirectory() as folder:
        site = Path(folder) / "site"
        site.mkdir()
        (site / "index.html").write_text(PAGE.format(body=body), encoding="utf-8")
        return check_site.check(folder)[1]


class Check(unittest.TestCase):
    def test_a_clean_page_passes(self):
        self.assertEqual(problems_of("<h2>Canelé worth crossing town for</h2>"), [])

    def test_a_demo_notice_of_its_own_is_refused(self):
        self.assertTrue(problems_of("<p>This is a demo site made for Name.</p>"))

    def test_a_template_heading_is_refused(self):
        self.assertTrue(problems_of("<h2>Gallery</h2>"))

    def test_a_hidden_heading_is_fine(self):
        self.assertEqual(problems_of('<h2 class="visually-hidden">Gallery</h2>'), [])

    def test_the_reference_photograph_never_goes_on_the_page(self):
        self.assertTrue(problems_of('<img src="../reference/place.jpg" alt="x">'))


class Fonts(unittest.TestCase):
    def test_every_weight_gets_a_face(self):
        font = {"id": "x", "name": "X", "weights": [400, 700]}
        text = add_fonts.font_faces([font])
        self.assertIn('url("fonts/x-400.woff2")', text)
        self.assertIn("font-weight: 700", text)

    def test_every_library_entry_is_complete(self):
        for font in SETTINGS["fonts"]["library"]:
            self.assertIn(font["role"], ("display", "body", "accent"))
            self.assertTrue(font["weights"] and font["fallback"] and font["feel"])

    def test_an_unknown_font_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "brief.md").write_text("x", encoding="utf-8")
            with self.assertRaises(add_fonts.FontError):
                add_fonts.add(folder, ["no-such-font"], SETTINGS)


class Design(unittest.TestCase):
    def test_recent_directions_are_not_offered_again(self):
        recent = [{"design_direction": item["name"]} for item in SETTINGS["design"]["directions"][:8]]
        names = {item["name"] for item in autopilot.design_options("place", recent, SETTINGS)}
        self.assertFalse(names & {item["design_direction"] for item in recent})

    def test_a_recent_display_font_is_not_offered_again(self):
        recent = [{"display_font": "fraunces"}]
        offered = autopilot.font_options("place", recent, SETTINGS)
        self.assertNotIn("fraunces", [font["id"] for font in offered])
        self.assertEqual({font["role"] for font in offered}, set(SETTINGS["design"]["fonts_offered"]))

    def test_businesses_get_different_font_shortlists(self):
        lists = {tuple(font["id"] for font in autopilot.font_options(name, [], SETTINGS)) for name in "abc"}
        self.assertEqual(len(lists), 3)

    def test_every_direction_is_offered_when_all_were_used(self):
        recent = [{"design_direction": item["name"]} for item in SETTINGS["design"]["directions"]]
        self.assertTrue(autopilot.design_options("place", recent, SETTINGS))

    def test_the_main_action_prefers_what_was_chosen(self):
        self.assertEqual(build_brief._primary_action({"order_link": "x"}, {"primary_action": "Directions"}), "Directions")
        self.assertIn("https://o.example", build_brief._primary_action({"order_link": "https://o.example"}, {}))

    def test_the_concept_names_the_direction(self):
        name = SETTINGS["design"]["directions"][0]
        text = build_brief._concept({"concept": "A parcel.", "design_direction": name["name"]}, SETTINGS)
        self.assertIn("A parcel.", text)
        self.assertIn(name["how"], text)


class GosomFields(unittest.TestCase):
    def test_the_first_real_ordering_link_is_kept(self):
        row = {"order_online": [{"link": ""}, {"link": "https://o.example"}]}
        self.assertEqual(gosom._order_link(row), "https://o.example")
        self.assertEqual(gosom._order_link({}), "")


class Screens(unittest.TestCase):
    def test_tiles_cover_the_page_up_to_the_limit(self):
        self.assertEqual(screenshot_site.tile_offsets(1700, 800, 12), [0, 800, 1600])
        self.assertEqual(screenshot_site.tile_offsets(100, 800, 12), [0])
        self.assertEqual(len(screenshot_site.tile_offsets(99999, 800, 12)), 12)

    def test_linux_paths_are_rewritten_for_the_browser(self):
        path = Path("D:/sites/A B/site/index.html")
        if path.drive:
            url = screenshot_site.page_url(path, {"linux_paths": True}, 800)
            self.assertEqual(url, "file:///mnt/d/sites/A%20B/site/index.html#800")


if __name__ == "__main__":
    unittest.main()

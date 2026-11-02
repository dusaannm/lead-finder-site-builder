import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import lead_search
from sources import overpass


class EditRule(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows paths")
    def test_windows_drive_becomes_a_lowercase_folder(self):
        self.assertEqual(autopilot._edit_rule("D:\\Sites\\Demo"), "Edit(//d/Sites/Demo/**)")

    @unittest.skipIf(os.name == "nt", "POSIX paths")
    def test_posix_path_stays_absolute(self):
        self.assertTrue(autopilot._edit_rule("/tmp").startswith("Edit(//"))


class BuilderCommand(unittest.TestCase):
    def test_prompt_never_travels_as_an_argument(self):
        settings = lead_search.load_settings()
        opts = autopilot.options(settings)
        command = autopilot.builder_command("claude", opts, settings)
        self.assertEqual(command[:2], ["claude", "-p"])
        self.assertIn("--allowedTools", command)
        self.assertFalse(any("\n" in part for part in command))


class PromptThroughStandardInput(unittest.TestCase):
    def test_a_long_multiline_prompt_arrives_whole(self):
        prompt = "first line\n" + "second line with \"quotes\" and ščćžđ\n" * 200
        echo = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "build.log"
            outcome = autopilot.run_builder([sys.executable, "-c", echo], log, 30, cwd=folder, prompt=prompt)
            received = autopilot.stream_path(log).read_text(encoding="utf-8")
        self.assertEqual(received.replace("\r\n", "\n"), prompt)
        self.assertFalse(outcome["timed_out"])


class ResultLimit(unittest.TestCase):
    def test_limit_keeps_the_leads_that_can_be_contacted(self):
        elements = [
            {"type": "node", "id": 1, "tags": {"name": "Has site", "website": "a.example", "phone": "1"}},
            {"type": "node", "id": 2, "tags": {"name": "No phone"}},
            {"type": "node", "id": 3, "tags": {"name": "Best", "phone": "2"}},
        ]
        place = {"term": "bakery", "name": "Town"}
        with mock.patch.object(overpass, "_geocode", return_value={"area_id": 1, "name": "Town"}), mock.patch.object(
            overpass, "_send_query", return_value={"elements": elements}
        ), mock.patch.object(overpass.time, "sleep"):
            found = overpass.search("bakery Town", 2, {"osm_categories": {}}, place=place)
        self.assertEqual([lead["name"] for lead in found["leads"]], ["Best", "No phone"])
        self.assertEqual(found["total_found"], 3)


if __name__ == "__main__":
    unittest.main()

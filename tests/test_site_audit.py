import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lead_search
import site_audit

SETTINGS = lead_search.load_settings()


def answered(status):
    response = mock.Mock()
    response.status_code = status
    return response


class Unreachable(unittest.TestCase):
    def audit(self, **behaviour):
        with mock.patch.object(site_audit.requests, "get", **behaviour):
            return site_audit.audit("https://shop.example", SETTINGS)

    def test_a_site_that_refuses_a_script_is_not_called_dead(self):
        report = self.audit(return_value=answered(403))
        self.assertTrue(report["unverified"])
        self.assertIsNone(report["score"])
        self.assertEqual(report["problems"], [])

    def test_a_dropped_connection_is_not_called_dead(self):
        report = self.audit(side_effect=requests.ConnectionError("Remote end closed connection"))
        self.assertTrue(report["unverified"])

    def test_a_missing_domain_is_dead(self):
        report = self.audit(side_effect=requests.ConnectionError("NameResolutionError: getaddrinfo failed"))
        self.assertNotIn("unverified", report)
        self.assertEqual(report["score"], 0)
        self.assertEqual(report["problems"], [SETTINGS["audit"]["messages"]["unreachable"]])

    def test_a_page_that_is_gone_is_dead(self):
        report = self.audit(return_value=answered(404))
        self.assertEqual(report["score"], 0)


class LeadsWithUnverifiedSites(unittest.TestCase):
    def test_they_are_neither_scored_nor_marked_poor(self):
        leads = [{"website": "https://shop.example"}]
        report = {"score": None, "problems": [], "unverified": True}
        with mock.patch.object(lead_search.site_audit, "audit_many", return_value={"https://shop.example": report}):
            lead_search._audit_websites(leads, SETTINGS)
        self.assertNotIn("website_is_poor", leads[0])
        self.assertNotIn("website_score", leads[0])


if __name__ == "__main__":
    unittest.main()

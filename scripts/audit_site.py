import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lead_search
import site_audit


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Scores an existing website from 0 to 100.")
    parser.add_argument("url", help="For example: example.com")
    arguments = parser.parse_args()

    settings = lead_search.load_settings()
    result = site_audit.audit(arguments.url, settings)

    print("\n{}".format(result["url"]))
    if result.get("unverified"):
        print("Not checked: the site refused this script, which does not mean it is down.\n")
        return

    print("Score: {} of 100".format(result["score"]))

    if result["status_code"]:
        print("HTTP status: {}".format(result["status_code"]))
    if result["load_seconds"] is not None:
        print("Load time: {} s".format(result["load_seconds"]))

    if not result["problems"]:
        print("\nNo problems found. This one is a hard sell.\n")
        return

    print("\nProblems you can quote to the owner:\n")
    for number, problem in enumerate(result["problems"], start=1):
        print("  {}. {}".format(number, problem))
    print()


if __name__ == "__main__":
    main()

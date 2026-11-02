import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contacts
import lead_search
import lead_store

ROOT = lead_search.ROOT


def wrong_profiles(row, options):
    return [
        column
        for column in contacts.PROFILE_HOSTS.values()
        if "/" in (row.get(column) or "") and not contacts.is_their_profile(row, row[column], options)
    ]


def clean_file(path, options, apply):
    rows = lead_store.load_rows(path)
    removed = []
    for row in rows:
        for column in wrong_profiles(row, options):
            removed.append((row["name"], row[column]))
            row[column] = ""
    if removed and apply:
        lead_store.save(path, rows)
    return removed


def clean_cache(root, options):
    path = lead_store.data_dir(root) / contacts.CACHE_FILE
    if not path.exists():
        return
    cache = json.loads(path.read_text(encoding="utf-8"))
    for entry in cache.values():
        for column in contacts.PROFILE_HOSTS.values():
            if column in entry and not contacts.profile_link(entry[column])[0]:
                del entry[column]
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Removes Instagram and Facebook links that do not belong to the business they were saved for."
    )
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    options = lead_search.load_settings()["contacts"]
    removed = []
    for path in sorted(lead_store.data_dir(ROOT).glob("leads_*.csv")):
        removed.extend(clean_file(path, options, arguments.apply))
    if arguments.apply:
        clean_cache(ROOT, options)
    for name, link in sorted(set(removed)):
        print("{} | {}".format(name, link))
    print("{} {} links.".format("Removed" if arguments.apply else "Would remove", len(set(removed))))


if __name__ == "__main__":
    main()

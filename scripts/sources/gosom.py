import json
import subprocess
import time
from pathlib import Path

import lead_quality
import lead_store

QUERY_FILE = "queries.txt"
RESULTS_FILE = "results.json"
OUTPUT_LOG = "gosom.log"
FINISHED_MESSAGE = b"scrapemate exited"
LOG_TAIL_BYTES = 2000
WEEK = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class SourceError(Exception):
    pass


def build_command(options, with_emails):
    command = list(options["launcher"]) + [
        options["executable"],
        "-input",
        QUERY_FILE,
        "-results",
        RESULTS_FILE,
        "-json",
        "-depth",
        str(options["depth"]),
        "-c",
        str(options["concurrency"]),
        "-lang",
        options["language"],
        "-exit-on-inactivity",
        "{}m".format(options["inactivity_minutes"]),
    ]
    return command + ["-email"] if with_emails else command


def _hours_text(hours):
    days = [
        "{} {}".format(day, ", ".join(hours[day]).replace(" ", " "))
        for day in WEEK
        if (hours or {}).get(day)
    ]
    return "; ".join(days)


def _category(row):
    return (row.get("category") or "").strip().lower().replace(" ", "_")


def _map_pin(row):
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if not latitude or not longitude:
        return ""
    return "https://www.google.com/maps/search/?api=1&query={},{}".format(latitude, longitude)


def lead_from_row(row, quality):
    name = (row.get("title") or "").strip()
    place_id = (row.get("place_id") or "").strip()
    if not name or not place_id:
        return None
    reviews = row.get("review_count") or 0
    emails = lead_quality.clean_emails(row.get("emails"), quality)
    lead = {
        "place_id": place_id,
        "name": name,
        "address": (row.get("address") or "").strip(),
        "rating": row.get("review_rating") if reviews else None,
        "review_count": reviews,
        "phone": (row.get("phone") or "").strip(),
        "opening_hours": _hours_text(row.get("open_hours")),
        "email": emails[0] if emails else "",
        "instagram": "",
        "facebook": "",
        "google_maps_link": row.get("link") or "",
        "map_pin": _map_pin(row),
        "category": _category(row),
    }
    lead.update(lead_quality.split_website(row.get("web_site"), quality))
    return lead


def _read_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _finished(log_path):
    with open(log_path, "rb") as log:
        log.seek(max(0, log_path.stat().st_size - LOG_TAIL_BYTES))
        return FINISHED_MESSAGE in log.read()


def _stop(process, options):
    try:
        process.wait(timeout=options["exit_grace_seconds"])
        return
    except subprocess.TimeoutExpired:
        pass
    if options["stop_command"]:
        subprocess.run(options["stop_command"], stdin=subprocess.DEVNULL, capture_output=True)
    process.terminate()
    try:
        process.wait(timeout=options["exit_grace_seconds"])
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run(query_text, options, folder, with_emails, on_event):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / QUERY_FILE).write_text(query_text + "\n", encoding="utf-8")
    (folder / RESULTS_FILE).unlink(missing_ok=True)
    if on_event:
        on_event("Searching Google Maps through gosom, this takes a few minutes")
    deadline = time.monotonic() + options["timeout_minutes"] * 60
    log_path = folder / OUTPUT_LOG
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                build_command(options, with_emails),
                cwd=str(folder),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
            while process.poll() is None and not _finished(log_path) and time.monotonic() < deadline:
                time.sleep(options["poll_seconds"])
            if process.poll() is None and not _finished(log_path) and on_event:
                on_event("gosom ran past its time limit, keeping what it found")
            _stop(process, options)
    except OSError as error:
        raise SourceError("gosom could not be started: {}".format(error))
    return _read_rows(folder / RESULTS_FILE)


def search(query, limit, settings, on_event=None, place=None, with_emails=True):
    options = settings["gosom"]
    quality = settings["lead_quality"]
    if not options["executable"] or not options["work_dir"]:
        raise SourceError("gosom.executable and gosom.work_dir are not set in config.local.yaml.")

    query_text = "{} in {}".format(place["term"], place["name"]) if place else query
    folder = Path(options["work_dir"]).expanduser() / lead_store.to_slug(query_text)
    rows = _run(query_text, options, folder, with_emails and options["extract_emails"], on_event)
    if not rows:
        raise SourceError(
            "gosom found nothing for '{}'. Google may be refusing the search; {} says why.".format(
                query_text, folder / OUTPUT_LOG
            )
        )

    leads = {}
    closed = 0
    for row in rows:
        if lead_quality.is_closed("{} {}".format(row.get("status"), row.get("description")), quality):
            closed += 1
            continue
        lead = lead_from_row(row, quality)
        if lead:
            leads.setdefault(lead["place_id"], lead)

    found = list(leads.values())
    country =(place or {}).get("country_code") or (rows[0].get("complete_address") or {}).get("country") or ""
    return {
        "leads": sorted(found, key=lead_quality.promise)[:limit],
        "total_found": len(found),
        "term": (place or {}).get("term", ""),
        "place": (place or {}).get("name", ""),
        "country": country.lower(),
        "closed_dropped": closed,
        "calls": 0,
    }

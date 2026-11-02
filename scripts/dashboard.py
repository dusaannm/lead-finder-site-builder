import re
import sys
from datetime import date, datetime
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autopilot
import build_brief
import check_site
import lead_search
import lead_store
import outreach_log
import publish_site

ROOT = lead_search.ROOT
BRIEF_FACT = re.compile(r"^\|\s*(Name|Address|place_id)\s*\|\s*(.*?)\s*\|\s*$")
PLACEHOLDERS = {"", "not listed", "not available", "none"}
CONTACTED = {"contacted", "declined", "accepted"}
THUMBNAIL_FOLDERS = ["hero", "interior", "gallery", "background"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ONLINE_CONTACTS = ("email", "instagram", "facebook")
PAGE_PHOTO = "screens/desktop.png"
CARD_PICTURE = "screens/card.jpg"
RUN_WORDS = {
    "searching": "Searching",
    "building": "Building",
    "done": "Finished",
    "failed": "Failed",
    "stopped": "Stopped",
    "interrupted": "Interrupted",
}


def _stamp(path):
    return datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")


def search_label(file_name):
    return re.sub(r"^leads_|\.csv$", "", file_name).replace("-", " ")


def lead_files(root):
    folder = lead_store.data_dir(root)
    files = [(folder / name, lead_store.load_rows(folder / name)) for name in lead_store.list_files(root)]
    return [(path, rows) for path, rows in files if rows]


def businesses(files):
    known = {}
    for _, rows in files:
        for row in rows:
            earlier = known.get(row["place_id"])
            if earlier is None or (row.get("status_changed_at") or "") > (earlier.get("status_changed_at") or ""):
                known[row["place_id"]] = row
    return known


def run_states(runner, root):
    folder = autopilot.runs_folder(root)
    if not folder.exists():
        return []
    states = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        run = autopilot.load_run(path.stem, runner, root)
        if run:
            states.append(run.snapshot())
    return states


def brief_facts(folder):
    try:
        lines = (Path(folder) / "brief.md").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    facts = {}
    for line in lines:
        match = BRIEF_FACT.match(line)
        if match and match.group(1) not in facts and match.group(2).lower() not in PLACEHOLDERS:
            facts[match.group(1)] = match.group(2)
    return facts


def site_folders(settings):
    base = build_brief.output_dir(settings)
    if not base.is_dir():
        return []
    return [path for path in base.iterdir() if path.is_dir() and (path / "brief.md").is_file()]


def thumbnail(folder):
    assets = Path(folder) / "assets"
    for name in THUMBNAIL_FOLDERS:
        images = sorted(path for path in (assets / name).glob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
        if images:
            return images[0]
    return None


def card_picture(folder, settings):
    sheet = Path(folder) / PAGE_PHOTO
    if not sheet.is_file():
        return thumbnail(folder)
    card = Path(folder) / CARD_PICTURE
    if not card.is_file() or card.stat().st_mtime < sheet.stat().st_mtime:
        view = settings["screenshots"]["views"]["desktop"]
        height = round(view["height"] * view["tile_width"] / view["width"])
        with Image.open(sheet) as image:
            image.crop((0, 0, view["tile_width"], height)).convert("RGB").save(
                card, quality=settings["dashboard"]["card_quality"]
            )
    return card


def _is_reachable(lead):
    return any((lead.get(column) or "").strip() for column in ONLINE_CONTACTS)


def _home_relative(folder):
    home = str(Path.home())
    return "~" + str(folder)[len(home):] if str(folder).startswith(home) else str(folder)


def _city(address):
    return address.rsplit(",", 1)[-1].strip() if "," in address else ""


def _sent_to(log, place_id):
    return [
        {"channel": item["channel"], "on": item["sent_at"], "response": item.get("response", "")}
        for item in log
        if place_id and item["place_id"] == place_id and item.get("sent_at")
    ]


def _stage(status, sent, messages_at, built_at):
    responses = {item["response"] for item in sent}
    if status == "accepted" or "interested" in responses:
        return "accepted"
    if status == "declined" or "declined" in responses:
        return "declined"
    if sent or status == "contacted":
        return "contacted"
    if messages_at:
        return "ready"
    if built_at:
        return "built"
    return "brief"


def site(folder, settings, known, log, country_codes, manifest):
    facts = brief_facts(folder)
    place_id = facts.get("place_id", "")
    lead = known.get(place_id, {})
    name = lead.get("name") or facts.get("Name") or folder.name
    address = lead.get("address") or facts.get("Address", "")
    page = check_site.entry_page(folder)
    published = manifest.get(place_id, {})
    found = autopilot.messages(folder)
    written = [item for item in found if item["text"]]
    sent = _sent_to(log, place_id)
    times = {
        "brief_at": _stamp(folder / "brief.md"),
        "built_at": _stamp(page) if page else "",
        "published_at": (published.get("published_at") or _stamp(folder / "brief.md")) if published.get("url") else "",
        "messages_at": _stamp(folder / autopilot.MESSAGES_FILE) if written else "",
    }
    candidate = dict(lead, name=name, city=_city(address), country_code=country_codes.get(place_id, ""))
    picture = card_picture(folder, settings)
    return dict(
        times,
        name=name,
        address=address,
        folder=str(folder),
        folder_label=_home_relative(folder),
        thumbnail=autopilot.site_url(picture, settings) if picture else "",
        place_id=place_id,
        status=lead.get("status", ""),
        stage=_stage(lead.get("status", ""), sent, times["messages_at"], times["built_at"]),
        site_url=autopilot.site_url(page, settings) if page else "",
        live_url=published.get("url", ""),
        live_public=bool(published.get("url")),
        reachable=_is_reachable(lead),
        messages=written,
        contacts=autopilot.contact_links(candidate, written, settings),
        sent=sent,
        updated=max(value for value in times.values() if value),
    )


def gather(settings=None, runner=None, root=None):
    settings = settings or lead_search.load_settings()
    root = root or ROOT
    files = lead_files(root)
    known = businesses(files)
    log = outreach_log.load(root)
    runs = run_states(runner, root)
    country_codes = {
        candidate["place_id"]: candidate.get("country_code", "")
        for state in reversed(runs)
        for candidate in state.get("candidates", [])
    }
    manifest = publish_site.load_manifest(root)
    sites = [site(folder, settings, known, log, country_codes, manifest) for folder in site_folders(settings)]
    sites.sort(key=lambda item: item["updated"], reverse=True)
    return {"settings": settings, "files": files, "businesses": known, "log": log, "runs": runs, "sites": sites}


def _event(at, kind, title, detail="", **target):
    return dict({"at": at, "kind": kind, "title": title, "detail": detail}, **target)


def _count(number, one, many):
    return "{} {}".format(number, one if number == 1 else many)


def _search_events(files):
    found = []
    for path, rows in files:
        label = search_label(path.name)
        without = sum(1 for row in rows if not (row.get("website") or "").strip())
        found.append(_event(
            _stamp(path), "search", "Searched {}".format(label),
            "{}, {} without a website".format(_count(len(rows), "business", "businesses"), without),
            view="leads", file=path.name,
        ))
        for row in rows:
            if not row.get("status_changed_at"):
                continue
            title = (
                "Marked {} as {}".format(row["name"], row["status"]) if row.get("status")
                else "Cleared the status of {}".format(row["name"])
            )
            found.append(_event(row["status_changed_at"], "status", title, label, view="leads", file=path.name))
    return found


def _run_events(runs):
    found = []
    for state in runs:
        candidates = state.get("candidates", [])
        built = sum(1 for candidate in candidates if candidate.get("state") in ("done", "attention"))
        word = RUN_WORDS.get(state.get("state"), state.get("state", ""))
        if state.get("state") in ("failed", "stopped", "interrupted"):
            detail = "{}. {}".format(word, state.get("message") or "").strip()
        else:
            detail = "{}, {} of {} built from {} found".format(
                word, built, _count(len(candidates), "site", "sites"), state.get("found") or 0
            )
        found.append(_event(
            state.get("started", ""), "autopilot", "Autopilot: {}".format(state.get("query", "")), detail,
            view="autopilot", run=state.get("id", ""),
        ))
    return found


def _site_events(sites):
    found = []
    for item in sites:
        name = item["name"]
        found.append(_event(item["brief_at"], "brief", "Wrote the brief for {}".format(name), item["folder_label"], view="sites"))
        if item["built_at"]:
            found.append(_event(item["built_at"], "site", "Built the site for {}".format(name), "", view="sites"))
        if item["published_at"]:
            found.append(_event(
                item["published_at"], "publish", "Published {}".format(name), item["live_url"],
                view="sites", href=item["live_url"],
            ))
        if item["messages_at"]:
            found.append(_event(item["messages_at"], "messages", "Drafted the messages for {}".format(name), "", view="sites"))
    return found


def _outreach_events(log):
    found = []
    for item in log:
        if item.get("sent_at"):
            found.append(_event(
                item["sent_at"], "sent", "Sent {} a message".format(item["name"]), "Over {}".format(item["channel"]),
                view="sites",
            ))
        if item.get("response") and item.get("response_at"):
            found.append(_event(
                item["response_at"], "reply", "{} answered: {}".format(item["name"], item["response"]), "", view="sites",
            ))
    return found


def _order(event):
    return event["at"] if len(event["at"]) > len("YYYY-MM-DD") else event["at"] + "T23:59:59"


def history(gathered):
    found = (
        _search_events(gathered["files"])
        + _run_events(gathered["runs"])
        + _site_events(gathered["sites"])
        + _outreach_events(gathered["log"])
    )
    found.sort(key=_order, reverse=True)
    return found


def _attention(gathered, today):
    known = gathered["businesses"]
    items = []
    for item in gathered["log"]:
        status = known.get(item["place_id"], {}).get("status", "")
        due = item.get("follow_up_due") or ""
        if item.get("sent_at") and not item.get("response") and due and due <= today and status not in ("declined", "accepted"):
            items.append({
                "kind": "follow_up",
                "title": "Follow up with {}".format(item["name"]),
                "detail": "Sent over {} on {}. The follow-up was due {}.".format(item["channel"], item["sent_at"], due),
                "view": "sites",
            })
    for item in gathered["sites"]:
        if item["stage"] == "ready" and item["reachable"]:
            items.append({
                "kind": "ready",
                "title": "Send the messages to {}".format(item["name"]),
                "detail": "The site and the messages are ready.",
                "view": "sites",
            })
        if item["live_url"] and not item["live_public"]:
            items.append({
                "kind": "publish",
                "title": "Publish {} again".format(item["name"]),
                "detail": "Its address did not open after the last publish.",
                "view": "sites",
            })
        if item["stage"] == "brief":
            items.append({
                "kind": "build",
                "title": "Build the site for {}".format(item["name"]),
                "detail": "The brief is written, the site is not.",
                "view": "sites",
            })
    return items


def overview(gathered, runner=None):
    known = gathered["businesses"]
    log = gathered["log"]
    sites = gathered["sites"]
    contacted = {item["place_id"] for item in log if item.get("sent_at")}
    contacted |= {place_id for place_id, row in known.items() if row.get("status") in CONTACTED}
    accepted = {place_id for place_id, row in known.items() if row.get("status") == "accepted"}
    accepted |= {item["place_id"] for item in log if item.get("response") == "interested"}
    runs = gathered["runs"]
    latest = runs[0] if runs else None
    recent = gathered["settings"]["dashboard"]["recent_events"]
    return {
        "counts": {
            "searches": len(gathered["files"]),
            "businesses": len(known),
            "without_website": sum(1 for row in known.values() if not (row.get("website") or "").strip()),
            "with_website": sum(1 for row in known.values() if (row.get("website") or "").strip()),
            "ready": sum(1 for item in sites if item["stage"] == "ready" and item["reachable"]),
            "phone_only": sum(1 for item in sites if item["stage"] == "ready" and not item["reachable"]),
            "briefs": len(sites),
            "sites": sum(1 for item in sites if item["built_at"]),
            "live": sum(1 for item in sites if item["live_url"] and item["live_public"]),
            "contacted": len(contacted),
            "accepted": len(accepted),
        },
        "attention": _attention(gathered, date.today().isoformat()),
        "recent": history(gathered)[:recent],
        "latest_run": latest and {
            "id": latest.get("id", ""),
            "query": latest.get("query", ""),
            "state": latest.get("state", ""),
            "message": latest.get("message", ""),
            "started": latest.get("started", ""),
            "sites": len(latest.get("candidates", [])),
            "built": sum(1 for candidate in latest.get("candidates", []) if candidate.get("state") in ("done", "attention")),
            "running": bool(runner is not None and runner.busy() and runner.run_id == latest.get("id")),
        },
    }


def record_send(place_id, channel, settings=None, root=None):
    settings = settings or lead_search.load_settings()
    root = root or ROOT
    folder = next((path for path in site_folders(settings) if place_id and brief_facts(path).get("place_id") == place_id), None)
    if folder is None:
        raise outreach_log.OutreachError("No site folder belongs to that business.")
    lead = businesses(lead_files(root)).get(place_id, {})
    name = lead.get("name") or brief_facts(folder).get("Name") or folder.name
    return outreach_log.record_send(root, place_id, name, channel, settings)

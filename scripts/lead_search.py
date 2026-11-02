import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contacts
import lead_quality
import lead_store
import scoring
import site_audit
import usage
from sources import google_places, gosom, overpass

ROOT = Path(__file__).resolve().parent.parent


class SearchError(Exception):
    pass


def merge_settings(base, override):
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_settings(base[key], value)
        else:
            base[key] = value
    return base


def load_settings():
    path = ROOT / "config.yaml"
    if not path.exists():
        raise SearchError("config.yaml is missing from the project folder.")

    settings = yaml.safe_load(path.read_text(encoding="utf-8"))

    personal = ROOT / "config.local.yaml"
    if personal.exists():
        merge_settings(settings, yaml.safe_load(personal.read_text(encoding="utf-8")))

    return settings


def google_key():
    load_dotenv(ROOT / ".env")
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


def search_key():
    load_dotenv(ROOT / ".env")
    return (os.getenv("FIRECRAWL_API_KEY") or "").strip()


def gosom_enabled(settings=None):
    settings = settings or load_settings()
    return bool(settings["gosom"]["enabled"])


def usage_summary(settings=None):
    settings = settings or load_settings()
    limit = settings["protection"]["monthly_call_limit"]
    return {"used": usage.read(ROOT)["calls"], "limit": limit}


def _country_of(lead, settings, hint=""):
    if hint:
        return hint.lower()
    names = settings["contact_search"]["country_names"]
    tail = (lead.get("address") or "").split(",")[-1].strip().lower()
    return names.get(tail, "")


def _add_contact_search(leads, settings, place="", country=""):
    options = settings["contact_search"]
    for lead in leads:
        template = options["by_country"].get(_country_of(lead, settings, country), options["default"])
        lead["contact_search"] = template.format(
            name=quote_plus(lead.get("name", "")),
            place=quote_plus(place or lead.get("address", "")),
        )
    return leads


def _audit_websites(leads, settings, on_event=None):
    options = settings["audit"]
    urls = [lead["website"] for lead in leads if (lead.get("website") or "").strip()]
    if not urls:
        return 0

    if on_event:
        on_event("Checking {} existing websites".format(len(urls)))

    reports = site_audit.audit_many(urls, settings)

    for lead in leads:
        report = reports.get(lead.get("website") or "")
        if not report or report.get("unverified"):
            continue
        lead["website_score"] = report["score"]
        lead["website_problems"] = report["problems"]
        lead["website_is_poor"] = report["score"] < options["poor_website_below"]

    return len(urls)


def _call_guard(monthly_limit):
    def before_call():
        if usage.read(ROOT)["calls"] >= monthly_limit:
            raise google_places.LimitReached(
                "Monthly limit of {} calls reached. The counter lives in data/usage.json.".format(monthly_limit)
            )
        usage.record_call(ROOT)

    return before_call


def _from_openstreetmap(query, limit, settings, on_event, place):
    try:
        result = overpass.search(query, limit, settings, on_event, place)
    except overpass.SourceError as error:
        raise SearchError(str(error))
    result["source"] = "openstreetmap"
    return result


def _from_gosom(query, limit, settings, on_event, place, with_emails, required):
    try:
        result = gosom.search(query, limit, settings, on_event, place, with_emails)
    except gosom.SourceError as error:
        if required:
            raise SearchError(str(error))
        if on_event:
            on_event("{} Falling back to OpenStreetMap.".format(error))
        return _from_openstreetmap(query, limit, settings, on_event, place)
    result["source"] = "gosom"
    return result


def run_search(query, limit=None, source="auto", on_event=None, audit=None, place=None):
    query = (query or "").strip()
    if not query:
        raise SearchError("The search is empty.")

    settings = load_settings()
    if limit is None:
        limit = settings["search"]["default_limit"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise SearchError("The limit has to be a whole number of at least 1, not {}.".format(limit))
    api_key = google_key()

    if source == "google" and not api_key:
        raise SearchError("Google was requested but GOOGLE_MAPS_API_KEY is empty in .env.")

    if source == "gosom" and not gosom_enabled(settings):
        raise SearchError("gosom was requested but gosom.enabled is off in config.local.yaml.")

    run_audit = settings["audit"]["enabled"] if audit is None else audit
    use_gosom = source == "gosom" or (source == "auto" and gosom_enabled(settings))
    use_google = not use_gosom and (source == "google" or (source == "auto" and api_key))

    if use_gosom:
        result = _from_gosom(query, limit, settings, on_event, place, run_audit, source == "gosom")
    elif use_google:
        monthly_limit = settings["protection"]["monthly_call_limit"]
        if usage.remaining(ROOT, monthly_limit) == 0:
            raise SearchError(
                "All {} calls for this month are used up. The counter resets on the first of the "
                "month, or change protection.monthly_call_limit in config.yaml.".format(monthly_limit)
            )
        try:
            result = google_places.search(query, limit, settings, api_key, _call_guard(monthly_limit))
        except (google_places.SourceError, google_places.LimitReached) as error:
            raise SearchError(str(error))
        result["source"] = "google"
    else:
        result = _from_openstreetmap(query, limit, settings, on_event, place)

    leads = result["leads"]
    if not leads:
        result.update({"rows": [], "path": None, "previous": None, "without_website": 0})
        return result

    leads = _add_contact_search(leads, settings, result.get("place", ""), result.get("country", ""))

    leads = lead_quality.mark_chains(leads, settings["lead_quality"])

    audited = _audit_websites(leads, settings, on_event) if run_audit else 0
    emails_from_sites = contacts.read_sites(leads, settings, on_event) if run_audit else 0

    leads = scoring.add_scores(leads, settings)

    previous = lead_store.find_previous(ROOT, query)
    rows = lead_store.merge(leads, lead_store.load(previous))
    try:
        path = lead_store.save(lead_store.output_path(ROOT, query), rows)
    except lead_store.FileLocked as error:
        raise SearchError(str(error))

    result.update(
        {
            "rows": rows,
            "path": path,
            "previous": previous.name if previous else None,
            "without_website": sum(1 for lead in leads if not (lead.get("website") or "").strip()),
            "audited": audited,
            "emails_from_sites": emails_from_sites,
            "poor_websites": sum(1 for lead in leads if lead.get("website_is_poor")),
            "query": query,
            "limit": limit,
        }
    )
    return result

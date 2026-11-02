import re
from collections import Counter
from urllib.parse import urlparse

import lead_store

EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
HASHED_MAILBOX = re.compile(r"^[0-9a-f]{24,}$")
LOCATION_SUFFIX = re.compile(r"\s+[-–—|]\s+.*$")
PROFILE_COLUMNS = {"instagram.com": "instagram", "facebook.com": "facebook", "fb.com": "facebook"}


def promise(lead):
    return bool(lead.get("website")), not lead.get("phone")


def _host(url):
    text = (url or "").strip()
    parsed = urlparse(text if "//" in text else "//" + text)
    return (parsed.hostname or "").lower().removeprefix("www.")


def _within(host, domains):
    return next((domain for domain in domains if host == domain or host.endswith("." + domain)), "")


def split_website(url, options):
    url = (url or "").strip()
    domain = _within(_host(url), options["not_a_website"])
    if not domain:
        return {"website": url}
    profile = PROFILE_COLUMNS.get(domain)
    return {"website": "", profile: url} if profile else {"website": ""}


def _repaired(address, options):
    mailbox, _, domain = address.partition("@")
    if mailbox.startswith("n") and mailbox[1:] in options["escaped_email_roles"]:
        return "{}@{}".format(mailbox[1:], domain)
    return address


def clean_emails(values, options):
    cleaned = []
    for value in values or []:
        address = _repaired(str(value).strip().lower(), options)
        mailbox, _, domain = address.partition("@")
        if not EMAIL.match(address) or HASHED_MAILBOX.match(mailbox):
            continue
        if _within(domain, options["junk_email_domains"]) or address.endswith(tuple(options["junk_email_endings"])):
            continue
        if address not in cleaned:
            cleaned.append(address)
    return cleaned


def _number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _given(value):
    return value is not None and str(value).strip() != ""


def meets_quality(lead, options):
    if (lead.get("chain") or "").strip():
        return False
    rating, reviews = lead.get("rating"), lead.get("review_count")
    if _given(rating) and _number(rating) < options["min_rating"]:
        return False
    return not _given(reviews) or _number(reviews) >= options["min_reviews"]


def is_closed(text, options):
    lowered = (text or "").lower()
    return any(words in lowered for words in options["closed_words"])


def _chain_key(name):
    return lead_store.to_slug(LOCATION_SUFFIX.sub("", name or ""), "")


def mark_chains(leads, options):
    known = {_chain_key(name) for name in options["chains"]}
    locations = Counter(_chain_key(lead.get("name")) for lead in leads)
    for lead in leads:
        key = _chain_key(lead.get("name"))
        lead["chain"] = "yes" if key in known or locations[key] >= options["chain_min_locations"] else ""
    return leads

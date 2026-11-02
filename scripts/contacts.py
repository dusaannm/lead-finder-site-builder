import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import lead_quality
import lead_store
import site_audit
import usage

CACHE_FILE = "contact_cache.json"
USAGE_NAME = "search_usage"
EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PROFILE_HOSTS = {"facebook.com": "facebook", "instagram.com": "instagram"}
SECOND_LEVEL_SUFFIXES = {"co", "com", "org", "net", "ac", "gov"}
NOT_A_PROFILE = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "groups",
    "people",
    "public",
    "sharer",
    "sharer.php",
    "share",
    "share.php",
    "watch",
    "photo.php",
    "events",
    "login",
    "hashtag",
    "tr",
    "popular",
    "fb-answers",
    "directory",
    "marketplace",
}


def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")


def _matching_domain(host, domains):
    return next((domain for domain in domains if host == domain or host.endswith("." + domain)), "")


def profile_link(url):
    domain = _matching_domain(_host(url), PROFILE_HOSTS)
    if not domain:
        return "", ""
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts or parts[0].lower() in NOT_A_PROFILE or parts == ["pages"]:
        return "", ""
    kept = parts[:3] if parts[0].lower() == "pages" else parts[:1]
    return PROFILE_HOSTS[domain], "https://www.{}/{}/".format(domain, "/".join(kept))


def _compact(text, generic_words=()):
    words = [word for word in lead_store.to_slug(text or "", "").split("-") if word not in generic_words]
    return "".join(words)


def _distinctive_words(lead, options):
    address = lead_store.to_slug(lead.get("address") or "", "").split("-")
    skipped = set(options["generic_name_words"]) | set(options["trade_name_words"]) | set(address)
    words = lead_store.to_slug(lead.get("name") or "", "").split("-")
    return [word.rstrip("s") for word in words if word not in skipped and len(word) >= options["min_name_word"]]


def is_their_profile(lead, url, options):
    column, profile = profile_link(url)
    if not column:
        return False
    handle = _compact(urlparse(profile).path)
    if handle.isdigit():
        return True
    whole_name = _compact(lead.get("name"), options["generic_name_words"])
    return whole_name in handle or any(word in handle for word in _distinctive_words(lead, options))


def _own_mail_first(emails, site_host):
    return sorted(emails, key=lambda address: not address.endswith("@" + site_host))


def _page_html(url, options):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": site_audit.USER_AGENT},
            timeout=options["timeout_seconds"],
            allow_redirects=True,
        )
    except requests.RequestException:
        return ""
    if response.status_code >= 400 or "html" not in response.headers.get("Content-Type", "").lower():
        return ""
    return response.text[: options["max_page_chars"]]


def contacts_in_html(html, quality):
    soup = BeautifulSoup(html, "html.parser")
    links = [tag["href"] for tag in soup.find_all("a", href=True)]
    mailed = [link.split(":", 1)[1].split("?")[0] for link in links if link.lower().startswith("mailto:")]
    found = {"emails": lead_quality.clean_emails(mailed + EMAIL_IN_TEXT.findall(soup.get_text(" ")), quality)}
    for link in links:
        column, profile = profile_link(link)
        if column:
            found.setdefault(column, profile)
    return found


def read_site(url, settings):
    options = settings["contacts"]
    home = site_audit.normalise_url(url)
    collected = {"emails": []}
    for page in [home] + [urljoin(home, path) for path in options["contact_paths"]]:
        html = _page_html(page, options)
        if not html:
            continue
        found = contacts_in_html(html, settings["lead_quality"])
        for key, value in found.items():
            if key == "emails":
                collected["emails"].extend(item for item in value if item not in collected["emails"])
            else:
                collected.setdefault(key, value)
        if collected["emails"]:
            break
    collected["emails"] = _own_mail_first(collected["emails"], _host(home))
    return collected


def _fill(lead, column, value):
    if value and not (lead.get(column) or "").strip():
        lead[column] = value


def read_sites(leads, settings, on_event=None):
    wanted = [
        lead
        for lead in leads
        if (lead.get("website") or "").strip() and lead.get("website_is_poor") and not (lead.get("email") or "").strip()
    ]
    if not wanted:
        return 0
    if on_event:
        on_event("Reading {} websites for a way to reach them".format(len(wanted)))
    with ThreadPoolExecutor(max_workers=settings["contacts"]["workers"]) as pool:
        found = list(pool.map(lambda lead: read_site(lead["website"], settings), wanted))
    for lead, contact in zip(wanted, found):
        _fill(lead, "email", contact["emails"][0] if contact["emails"] else "")
        _fill(lead, "facebook", contact.get("facebook"))
        _fill(lead, "instagram", contact.get("instagram"))
    return sum(1 for contact in found if contact["emails"])


def _domain_label(host):
    labels = host.split(".")
    if len(labels) > 2 and labels[-2] in SECOND_LEVEL_SUFFIXES:
        return labels[-3]
    return labels[-2] if len(labels) > 1 else labels[0]


def _is_official(url, name_key, options, quality):
    host = _host(url)
    blocked = options["directory_hosts"] + quality["not_a_website"]
    if not host or _matching_domain(host, blocked):
        return False
    return len(name_key) >= options["min_name_match"] and name_key in _compact(_domain_label(host))


def read_results(lead, results, settings):
    options = settings["contacts"]
    quality = settings["lead_quality"]
    name_key = _compact(lead.get("name"), options["generic_name_words"])
    found = {}
    emails = []
    for result in results:
        url = result.get("url") or ""
        title = result.get("title") or ""
        snippets = " ".join([result.get("description") or ""] + list(result.get("extra_snippets") or []))
        if name_key not in _compact("{} {}".format(title, snippets)):
            continue
        if _is_official(url, name_key, options, quality):
            found.setdefault("website", "{}://{}/".format(urlparse(url).scheme, urlparse(url).netloc))
        column, profile = profile_link(url)
        if column and is_their_profile(lead, url, options):
            found.setdefault(column, profile)
        emails.extend(EMAIL_IN_TEXT.findall(snippets))
    cleaned = lead_quality.clean_emails(emails, quality)
    if cleaned:
        found["email"] = cleaned[0]
    return found


def web_search(query, api_key, options, country=""):
    payload = {"query": query, "limit": options["results_per_search"]}
    if country:
        payload["country"] = country.upper()
    response = requests.post(
        options["search_url"],
        json=payload,
        headers={"Authorization": "Bearer {}".format(api_key)},
        timeout=options["search_timeout_seconds"],
    )
    response.raise_for_status()
    return (response.json().get("data") or {}).get("web") or []


def _cache_path(root):
    return lead_store.data_dir(root) / CACHE_FILE


def _load_cache(root):
    path = _cache_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _save_cache(root, cache):
    path = _cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_fresh(entry, options):
    if not entry:
        return False
    return date.fromisoformat(entry["checked"]) >= date.today() - timedelta(days=options["cache_days"])


def lookup(lead, settings, root, api_key, place="", country=""):
    options = settings["contacts"]
    cache = _load_cache(root)
    entry = cache.get(lead["place_id"])
    if _is_fresh(entry, options):
        return {
            column: value
            for column, value in entry.items()
            if column != "checked" and (column not in PROFILE_HOSTS.values() or is_their_profile(lead, value, options))
        }
    if not api_key or not options["enabled"]:
        return None
    if not usage.remaining(root, options["monthly_search_limit"], USAGE_NAME):
        return None

    query ='"{}" {}'.format(lead.get("name"), place or lead.get("address") or "").strip()
    try:
        results = web_search(query, api_key, options, country)
    except (requests.RequestException, ValueError):
        return None
    usage.record_call(root, USAGE_NAME)
    found = read_results(lead, results, settings)
    cache[lead["place_id"]] = dict(found, checked=date.today().isoformat())
    _save_cache(root, cache)
    time.sleep(options["search_pause_seconds"])
    return found

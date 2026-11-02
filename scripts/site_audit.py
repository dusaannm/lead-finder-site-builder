import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 lead-finder-site-builder/0.1"
)

VERSIONED_PLATFORMS = {
    "wordpress": ("WordPress", 6),
    "joomla": ("Joomla", 4),
    "drupal": ("Drupal", 9),
}

ABANDONED_PLATFORMS = {
    "frontpage": "Microsoft FrontPage",
    "dreamweaver": "Adobe Dreamweaver",
    "sitebuilder": "an old site builder",
}

TEMPLATE_PLATFORMS = {
    "wix": "Wix",
    "weebly": "Weebly",
    "blogger": "Blogger",
    "squarespace": "Squarespace",
}

REFUSING_STATUSES = {401, 403, 406, 429, 503}
DOMAIN_MISSING_WORDS = ("NameResolutionError", "getaddrinfo failed", "Name or service not known")

VERSION_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?")

YEAR_PATTERN = re.compile(
    r"(?:©|\(c\)|copyright)\s*[^0-9]{0,12}((?:19|20)\d{2})"
    r"(?:\s*[-–—]\s*(?:((?:19|20)\d{2})|(present|today|danas)))?",
    re.IGNORECASE,
)


def normalise_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def _attempts(url):
    if (url or "").strip().startswith(("http://", "https://")):
        return [url]
    secure = normalise_url(url)
    return [secure, secure.replace("https://", "http://", 1)]


def _domain_missing(error):
    return any(words in str(error) for words in DOMAIN_MISSING_WORDS)


def _fetch(url, options):
    certainly_dead = True
    for candidate in _attempts(url):
        try:
            response = requests.get(
                candidate,
                headers={"User-Agent": USER_AGENT},
                timeout=options["timeout_seconds"],
                allow_redirects=True,
            )
            if response.status_code < 400:
                return response, False
            if response.status_code in REFUSING_STATUSES:
                certainly_dead = False
        except requests.RequestException as error:
            if not _domain_missing(error):
                certainly_dead = False
    return None, certainly_dead


def _message(settings, key, **values):
    template = settings["audit"]["messages"][key]
    return template.format(**values)


def _footer_year(soup):
    footer = soup.find("footer")
    text = footer.get_text(" ", strip=True) if footer else soup.get_text(" ", strip=True)[-2000:]
    match = YEAR_PATTERN.search(text)
    if not match:
        return None
    if match.group(3):
        return datetime.now(timezone.utc).year
    return int(match.group(2) or match.group(1))


def _header_year(response):
    stamp = response.headers.get("Last-Modified")
    if not stamp:
        return None
    try:
        return parsedate_to_datetime(stamp).year
    except (TypeError, ValueError):
        return None


def _detect_platform(soup):
    tag = soup.find("meta", attrs={"name": re.compile("^generator$", re.IGNORECASE)})
    content = (tag.get("content") or "").lower() if tag else ""
    if not content:
        return None, None

    for marker, label in ABANDONED_PLATFORMS.items():
        if marker in content:
            return "dated_platform", label

    for marker, (label, supported_major) in VERSIONED_PLATFORMS.items():
        if marker not in content:
            continue
        match = VERSION_PATTERN.search(content)
        if not match:
            return None, None
        major = int(match.group(1))
        if major < supported_major:
            return "dated_platform", "{} {}".format(label, match.group(0))
        return None, None

    for marker, label in TEMPLATE_PLATFORMS.items():
        if marker in content:
            return "template_platform", label

    return None, None


def audit(url, settings):
    options = settings["audit"]
    penalties = options["penalties"]
    target = normalise_url(url)

    result = {
        "url": target,
        "score": 0,
        "problems": [],
        "load_seconds": None,
        "status_code": None,
        "reachable": False,
    }

    if not target:
        return result

    response, certainly_dead = _fetch(url, options)
    if response is None and not certainly_dead:
        result["score"] = None
        result["unverified"] = True
        return result
    if response is None:
        result["problems"].append(_message(settings, "unreachable"))
        return result

    result["url"] = response.url
    result["status_code"] = response.status_code
    result["load_seconds"] = round(response.elapsed.total_seconds(), 1)
    result["reachable"] = True
    score = 100
    soup = BeautifulSoup(response.text, "html.parser")

    if not response.url.lower().startswith("https://"):
        score -= penalties["no_https"]
        result["problems"].append(_message(settings, "no_https"))

    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)}):
        score -= penalties["no_viewport"]
        result["problems"].append(_message(settings, "no_viewport"))

    seconds = result["load_seconds"]
    if seconds is not None and seconds >= options["very_slow_seconds"]:
        score -= penalties["very_slow"]
        result["problems"].append(_message(settings, "very_slow", seconds=seconds))
    elif seconds is not None and seconds >= options["slow_seconds"]:
        score -= penalties["slow"]
        result["problems"].append(_message(settings, "slow", seconds=seconds))

    year = _footer_year(soup) or _header_year(response)
    current_year = datetime.now(timezone.utc).year
    if year and year <= current_year - options["stale_after_years"]:
        score -= penalties["stale_year"]
        result["problems"].append(_message(settings, "stale_year", year=year))

    title = soup.find("title")
    if not title or not title.get_text(strip=True):
        score -= penalties["no_title"]
        result["problems"].append(_message(settings, "no_title"))

    description = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if not description or not (description.get("content") or "").strip():
        score -= penalties["no_description"]
        result["problems"].append(_message(settings, "no_description"))

    problem_key, platform = _detect_platform(soup)
    if problem_key:
        score -= penalties[problem_key]
        result["problems"].append(_message(settings, problem_key, platform=platform))

    result["score"] = max(0, min(100, score))
    return result


def audit_many(urls, settings, on_progress=None):
    unique = [url for url in dict.fromkeys(urls) if url]
    if not unique:
        return {}

    results = {}
    done = 0

    with ThreadPoolExecutor(max_workers=settings["audit"]["workers"]) as pool:
        for url, outcome in zip(unique, pool.map(lambda item: audit(item, settings), unique)):
            results[url] = outcome
            done += 1
            if on_progress:
                on_progress(done, len(unique))

    return results

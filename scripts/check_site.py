import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

ENTRY_PAGES = ("site/dist/index.html", "site/index.html")
TEXT_SUFFIXES = {".html", ".css", ".js", ".mjs", ".astro", ".jsx", ".tsx", ".vue", ".svelte"}
SKIPPED_FOLDERS = {"node_modules", ".astro", ".git"}
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+?)['\"]?\s*\)")
FILLER_TEXT = re.compile(r"lorem\s+ipsum", re.IGNORECASE)
BRACKETED_NOTE = re.compile(r"\[[A-Za-z][^\]]*\]")
NOT_A_FILE = ("#", "data:", "mailto:", "tel:", "javascript:", "sms:", "whatsapp:", "viber:")


def entry_page(folder):
    for relative in ENTRY_PAGES:
        page = Path(folder) / relative
        if page.is_file():
            return page
    return None


def _is_external(reference):
    parsed = urlparse(reference)
    return bool(parsed.scheme and parsed.scheme not in ("file",)) or reference.startswith("//")


def _local_target(reference, containing_file, site_root):
    reference = (reference or "").strip()
    if not reference or reference.lower().startswith(NOT_A_FILE) or _is_external(reference):
        return None
    path = unquote(urlparse(reference).path)
    if not path:
        return None
    if path.startswith("/"):
        return site_root / path.lstrip("/")
    return containing_file.parent / path


def _srcset_urls(value):
    return [part.strip().split()[0] for part in (value or "").split(",") if part.strip()]


def _references(soup):
    found = []
    for tag in soup.find_all(["img", "source", "video", "audio", "track"]):
        for attribute in ("src", "poster"):
            if tag.get(attribute):
                found.append((tag.name, tag[attribute]))
        found.extend((tag.name, url) for url in _srcset_urls(tag.get("srcset")))
    for tag in soup.find_all("script", src=True):
        found.append(("script", tag["src"]))
    for tag in soup.find_all("link", href=True):
        found.append(("link", tag["href"]))
    for tag in soup.find_all(style=True):
        found.extend(("style", url) for url in CSS_URL.findall(tag["style"]))
    for tag in soup.find_all("style"):
        found.extend(("style", url) for url in CSS_URL.findall(tag.get_text()))
    return found


def _site_files(site_folder):
    for path in sorted(site_folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            if not SKIPPED_FOLDERS.intersection(path.relative_to(site_folder).parts):
                yield path


def _head_problems(soup):
    problems = []
    html = soup.find("html")
    if not html or not (html.get("lang") or "").strip():
        problems.append("<html> has no lang attribute.")
    title = soup.find("title")
    if not title or not title.get_text(strip=True):
        problems.append("The page has no <title>.")
    description = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if not description or not (description.get("content") or "").strip():
        problems.append('The page has no <meta name="description">.')
    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)}):
        problems.append('The page has no <meta name="viewport">.')
    headings = soup.find_all("h1")
    if len(headings) != 1:
        problems.append("The page has {} <h1> elements instead of exactly one.".format(len(headings)))
    return problems


def _structured_data_problems(soup):
    blocks = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not blocks:
        return ["The page has no JSON-LD LocalBusiness data."]
    problems = []
    for block in blocks:
        try:
            json.loads(block.get_text())
        except ValueError:
            problems.append("A JSON-LD block is not valid JSON.")
    return problems


def _image_problems(soup):
    problems = []
    for image in soup.find_all("img"):
        if not (image.get("alt") or "").strip():
            problems.append("<img src=\"{}\"> has no alt text.".format(image.get("src", "")))
        if _is_external(image.get("src", "")):
            problems.append("<img src=\"{}\"> is hotlinked from another server.".format(image["src"]))
    for tag in soup.find_all(["script", "link"]):
        reference = tag.get("src") or tag.get("href") or ""
        loads_code = tag.name == "script" or "stylesheet" in (tag.get("rel") or [])
        if loads_code and _is_external(reference):
            problems.append("{} is loaded from another server: {}".format(tag.name, reference))
    return problems


def _missing_files(page, soup, site_root):
    problems = []
    checked = set()
    for kind, reference in _references(soup):
        target = _local_target(reference, page, site_root)
        if target and target not in checked:
            checked.add(target)
            if not target.exists():
                problems.append("{} points at {}, which does not exist.".format(kind, reference))
    for stylesheet in site_root.rglob("*.css"):
        if SKIPPED_FOLDERS.intersection(stylesheet.relative_to(site_root).parts):
            continue
        for reference in CSS_URL.findall(stylesheet.read_text(encoding="utf-8", errors="replace")):
            target = _local_target(reference, stylesheet, site_root)
            if target and target not in checked:
                checked.add(target)
                if not target.exists():
                    problems.append("{} points at {}, which does not exist.".format(stylesheet.name, reference))
    return problems


def _visible_notes(soup):
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    return ['Visible note left on the page: "{}"'.format(note) for note in BRACKETED_NOTE.findall(soup.get_text(" "))]


def check(folder):
    folder = Path(folder).expanduser()
    page = entry_page(folder)
    if page is None:
        return None, ["site/index.html does not exist, and neither does a built site/dist/index.html."]

    soup = BeautifulSoup(page.read_text(encoding="utf-8", errors="replace"), "html.parser")
    site_root = page.parent
    problems = _head_problems(soup) + _structured_data_problems(soup) + _image_problems(soup)
    problems += _missing_files(page, soup, site_root)
    problems += _visible_notes(soup)

    for path in _site_files(folder / "site"):
        if FILLER_TEXT.search(path.read_text(encoding="utf-8", errors="replace")):
            problems.append("{} still holds lorem ipsum.".format(path.relative_to(folder)))

    return page, problems


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Checks a built site against the rules every brief carries.")
    parser.add_argument("folder", help="The business folder that holds brief.md and site/")
    arguments = parser.parse_args()

    page, problems = check(arguments.folder)
    if not problems:
        print("\n{} passes every check.\n".format(page))
        return

    print("\n{} problems in {}:\n".format(len(problems), page or Path(arguments.folder) / "site"))
    for number, problem in enumerate(problems, start=1):
        print("  {}. {}".format(number, problem))
    print()
    raise SystemExit(1)


if __name__ == "__main__":
    main()

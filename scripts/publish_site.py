import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_site
import lead_search
import lead_store

ROOT = lead_search.ROOT
PROJECTS_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/pages/projects"
LINK_PLACEHOLDER = "[link to the demo site]"
MESSAGES_FILE = "outreach.md"
ASSET_LINK = re.compile(r"\.\./assets/([^\"'()\s>]+)")
TEXT_SUFFIXES = {".html", ".css", ".js", ".mjs"}
NOT_PUBLISHED = shutil.ignore_patterns("node_modules", ".git", ".astro", "README.md", "package*.json")
HEADERS_FILE = "/*\n  X-Robots-Tag: noindex, nofollow\n"
BAR_STYLE = (
    "position:relative;z-index:2147483647;margin:0;padding:8px 12px;background:#111;color:#fff;"
    "font:13px/1.4 system-ui,sans-serif;text-align:center"
)


class PublishError(Exception):
    pass


def credentials():
    load_dotenv(ROOT / ".env")
    token = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not token or not account:
        raise PublishError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID have to be in .env.")
    return token, account


def is_set_up(settings):
    try:
        credentials()
    except PublishError:
        return False
    return bool(settings["publish"]["enabled"])


def manifest_path(root=None):
    return lead_store.data_dir(root or ROOT) / "autopilot" / "published.json"


def load_manifest(root=None):
    path = manifest_path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(manifest, root=None):
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def slug_for(name, city):
    return lead_store.to_slug("{} {}".format(name, city), "site")


def demo_marked(page, name, sender, options):
    note = options["demo_note"].format(name=name, sender=sender or "a local web developer")
    bar = '<p style="{}">{}</p>'.format(BAR_STYLE, html.escape(note))
    robots = '<meta name="robots" content="noindex, nofollow">'
    page = re.sub(r"<head([^>]*)>", lambda match: match.group(0) + "\n" + robots, page, count=1, flags=re.IGNORECASE)
    return re.sub(r"<body([^>]*)>", lambda match: match.group(0) + "\n" + bar, page, count=1, flags=re.IGNORECASE)


def _copy_asset(folder, target, relative):
    source = Path(folder) / "assets" / unquote(relative)
    if source.is_file():
        destination = target / "assets" / unquote(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def stage(folder, target, name, sender, options):
    page = check_site.entry_page(folder)
    if page is None:
        raise PublishError("{} has no built site.".format(folder))
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(page.parent, target, ignore=NOT_PUBLISHED)

    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        links = set(ASSET_LINK.findall(text))
        if not links:
            continue
        for relative in links:
            _copy_asset(folder, target, relative)
        path.write_text(text.replace("../assets/", "assets/"), encoding="utf-8")

    index = target / "index.html"
    index.write_text(
        demo_marked(index.read_text(encoding="utf-8", errors="replace"), name, sender, options), encoding="utf-8"
    )


def project_host(token, account, name):
    url = PROJECTS_URL.format(account=account)
    headers = {"Authorization": "Bearer {}".format(token)}
    found = requests.get("{}/{}".format(url, name), headers=headers, timeout=30)
    if found.status_code == 404 or (found.status_code == 400 and "not found" in found.text.lower()):
        found = requests.post(url, headers=headers, json={"name": name, "production_branch": "main"}, timeout=30)
    if found.status_code >= 400:
        details = "; ".join(item.get("message", "") for item in found.json().get("errors", []))
        raise PublishError("Cloudflare refused the project ({}): {}".format(found.status_code, details))
    return found.json()["result"]["subdomain"]


def deploy_command(pages_dir, options):
    return [
        "node",
        options["wrangler"],
        "pages",
        "deploy",
        str(pages_dir),
        "--project-name",
        options["project"],
        "--branch",
        "main",
        "--commit-dirty=true",
    ]


def _deploy(pages_dir, token, account, options):
    environment = dict(
        os.environ,
        CLOUDFLARE_API_TOKEN=token,
        CLOUDFLARE_ACCOUNT_ID=account,
        WRANGLER_SEND_METRICS="false",
        npm_config_cache=options["cache_dir"],
        XDG_CONFIG_HOME=options["cache_dir"],
        WRANGLER_LOG_PATH=options["cache_dir"],
    )
    log_path = Path(pages_dir).parent / "wrangler.log"
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            finished = subprocess.run(
                deploy_command(pages_dir, options),
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=options["timeout_minutes"] * 60,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublishError("The upload to Cloudflare did not finish: {}".format(type(error).__name__))
    if finished.returncode:
        raise PublishError("The upload to Cloudflare failed, {} says why.".format(log_path))


def fill_link(folder, url):
    path = Path(folder) / MESSAGES_FILE
    if path.exists():
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(LINK_PLACEHOLDER, url), encoding="utf-8")


def public_url(host, slug, options):
    address = (options.get("address") or "").strip().rstrip("/")
    return "{}/{}/".format(address or "https://" + host, slug)


def publish(sites, settings, root=None):
    options = settings["publish"]
    if not options["enabled"]:
        return {}
    token, account = credentials()
    host = project_host(token, account, options["project"])
    pages_dir = Path(options["pages_dir"]).expanduser()
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "_headers").write_text(HEADERS_FILE, encoding="utf-8")

    sender = settings["outreach"]["sender_name"]
    staged = {}
    for site in sites:
        slug = slug_for(site["name"], site.get("city", ""))
        stage(site["folder"], pages_dir / slug, site["name"], sender, options)
        staged[site["place_id"]] = dict(
            site, slug=slug, url=public_url(host, slug, options), published_at=datetime.now().isoformat(timespec="seconds")
        )
    if not staged:
        return {}

    _deploy(pages_dir, token, account, options)
    manifest = load_manifest(root)
    manifest.update(staged)
    _save_manifest(manifest, root)
    for site in staged.values():
        fill_link(site["folder"], site["url"])
    return staged


def finished_sites(root=None):
    sites = {}
    for path in sorted((lead_store.data_dir(root or ROOT) / "autopilot" / "runs").glob("*.json")):
        for candidate in json.loads(path.read_text(encoding="utf-8")).get("candidates", []):
            if candidate.get("state") == "done" and candidate.get("folder"):
                sites[candidate["place_id"]] = {
                    "place_id": candidate["place_id"],
                    "name": candidate["name"],
                    "city": candidate.get("city", ""),
                    "country_code": candidate.get("country_code", ""),
                    "folder": candidate["folder"],
                }
    return list(sites.values())


def unpublished_sites(root=None):
    published = load_manifest(root)
    return [
        site
        for site in finished_sites(root)
        if site["place_id"] not in published and not check_site.check(site["folder"])[1]
    ]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Publishes finished demo sites to Cloudflare Pages.")
    parser.parse_args()

    settings = lead_search.load_settings()
    try:
        done = publish(unpublished_sites(), settings)
    except PublishError as error:
        print("\nERROR: {}\n".format(error))
        raise SystemExit(1)
    for site in done.values():
        print("{}: {}".format(site["name"], site["url"]))
    print("\nPublished {} sites.\n".format(len(done)))


if __name__ == "__main__":
    main()

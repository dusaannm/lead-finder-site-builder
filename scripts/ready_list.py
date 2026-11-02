import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autopilot
import build_brief
import lead_search
import outreach_log
import publish_site

ROOT = lead_search.ROOT
READY_FILE = "_ready.html"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ready to contact</title>
<style>
:root {{ color-scheme: light dark; --line: #8884; --muted: #888; }}
body {{ margin: 0 auto; max-width: 860px; padding: 24px 16px; font: 15px/1.5 system-ui, sans-serif; }}
h1 {{ margin: 0 0 4px; font-size: 24px; }}
h2 {{ margin: 0; font-size: 18px; }}
article {{ border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-top: 16px; }}
.meta, .empty {{ color: var(--muted); margin: 2px 0 10px; }}
.demo {{ font-weight: 600; }}
.links {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }}
.links a {{ border: 1px solid var(--line); border-radius: 6px; padding: 3px 9px; text-decoration: none; }}
details {{ border-top: 1px solid var(--line); padding: 8px 0 0; margin-top: 8px; }}
summary {{ cursor: pointer; font-weight: 600; }}
textarea {{ box-sizing: border-box; width: 100%; min-height: 150px; margin-top: 8px; font: inherit; }}
button {{ margin-top: 6px; padding: 5px 12px; font: inherit; cursor: pointer; }}
</style>
</head>
<body>
<h1>Ready to contact</h1>
<p class="meta">{count} businesses. Read each message, send it yourself, then press I sent it on the Autopilot tab.</p>
{cards}
<script>
document.querySelectorAll("button[data-copy]").forEach((button) => {{
  button.addEventListener("click", async () => {{
    const text = button.previousElementSibling.value;
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
  }});
}});
</script>
</body>
</html>
"""


def _message_block(message):
    return (
        "<details><summary>{title}</summary><textarea readonly>{text}</textarea>"
        '<button type="button" data-copy>Copy</button></details>'
    ).format(title=html.escape(message["title"]), text=html.escape(message["text"]))


def _card(site, settings):
    try:
        row, _ = build_brief.find_lead(site["place_id"])
    except build_brief.BriefError:
        row = {}
    found = autopilot.messages(site["folder"])
    candidate = dict(row, name=site["name"], city=site.get("city", ""), country_code=site.get("country_code", ""))
    links = [
        '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(html.escape(link["href"], True), html.escape(link["label"]))
        for link in autopilot.contact_links(candidate, found, settings)
    ]
    facts = [
        (row.get("category") or "").replace("_", " "),
        site.get("city", ""),
        "{} stars, {} reviews".format(row["rating"], row.get("review_count")) if row.get("rating") else "",
    ]
    url = site.get("url", "")
    demo = '<a class="demo" href="{0}" target="_blank" rel="noopener">{0}</a>'.format(html.escape(url, True))
    return (
        '<article><h2>{name}</h2><p class="meta">{facts}</p>{demo}'
        '<div class="links">{links}</div>{messages}</article>'
    ).format(
        name=html.escape(site["name"]),
        facts=html.escape(" · ".join(fact for fact in facts if fact)),
        demo=demo if url else '<p class="meta">Built, not published yet.</p>',
        links="".join(links),
        messages="".join(_message_block(message) for message in found),
    )


def waiting_sites(root=None):
    contacted = {row["place_id"] for row in outreach_log.load(root or ROOT)}
    sites = publish_site.unpublished_sites(root) + list(publish_site.load_manifest(root).values())
    return [site for site in reversed(sites) if site["place_id"] not in contacted]


def write(settings=None, root=None):
    settings = settings or lead_search.load_settings()
    sites = waiting_sites(root)
    cards = "".join(_card(site, settings) for site in sites)
    path = build_brief.output_dir(settings) / READY_FILE
    empty = '<p class="empty">Nothing is waiting.</p>'
    path.write_text(PAGE.format(count=len(sites), cards=cards or empty), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(write())

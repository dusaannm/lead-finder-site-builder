import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_tools
import lead_search
import lead_store

PEXELS_SEARCH = "https://api.pexels.com/v1/search"
PIXABAY_SEARCH = "https://pixabay.com/api/"
ROOT = lead_search.ROOT


class StockPhotoError(Exception):
    pass


def _provider():
    load_dotenv(ROOT / ".env")
    for name, variable in (("Pexels", "PEXELS_API_KEY"), ("Pixabay", "PIXABAY_API_KEY")):
        key = (os.getenv(variable) or "").strip()
        if key:
            return name, key
    raise StockPhotoError("PEXELS_API_KEY and PIXABAY_API_KEY are both empty in .env.")


def _search_pexels(query, key, options):
    try:
        response = requests.get(
            PEXELS_SEARCH,
            headers={"Authorization": key},
            params={
                "query": query,
                "per_page": options["search_results"],
                "orientation": "landscape",
                "size": "large",
            },
            timeout=30,
        )
        if response.status_code == 401:
            raise StockPhotoError("Pexels rejected the key. Check PEXELS_API_KEY in .env.")
        if response.status_code == 429:
            raise StockPhotoError("Pexels rate limit reached (200 calls per hour). Wait and retry.")
        response.raise_for_status()
    except requests.RequestException as error:
        raise StockPhotoError("Pexels did not respond: {}".format(error))

    return response.json().get("photos", [])


def _photo_from_pixabay(hit):
    user = hit.get("user") or "Pixabay"
    return {
        "id": hit["id"],
        "width": hit.get("imageWidth", 0),
        "height": hit.get("imageHeight", 1),
        "alt": hit.get("tags") or "",
        "url": hit.get("pageURL") or "",
        "photographer": user,
        "photographer_url": "https://pixabay.com/users/{}-{}/".format(user, hit.get("user_id", "")),
        "src": {"large": hit["largeImageURL"], "original": hit["largeImageURL"]},
    }


def _cache_file(query):
    return lead_store.data_dir(ROOT) / "stock_searches" / "{}.json".format(lead_store.to_slug(query))


def _cached_hits(query, options):
    path = _cache_file(query)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if time.time() - record["saved"] > options["search_cache_hours"] * 3600:
        return None
    return record["hits"]


def _remember_hits(query, hits):
    path = _cache_file(query)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"saved": time.time(), "hits": hits}, ensure_ascii=False), encoding="utf-8")


def _search_pixabay(query, key, options):
    hits = _cached_hits(query, options)
    if hits is None:
        try:
            response = requests.get(
                PIXABAY_SEARCH,
                params={
                    "key": key,
                    "q": query,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "safesearch": "true",
                    "per_page": options["search_results"],
                },
                timeout=30,
            )
            if response.status_code in (400, 401, 403):
                raise StockPhotoError("Pixabay refused the search. Check PIXABAY_API_KEY in .env.")
            if response.status_code == 429:
                raise StockPhotoError("Pixabay rate limit reached. Wait a minute and retry.")
            response.raise_for_status()
        except requests.RequestException as error:
            raise StockPhotoError("Pixabay did not respond: {}".format(type(error).__name__))
        hits = response.json().get("hits", [])
        _remember_hits(query, hits)
    return [_photo_from_pixabay(hit) for hit in hits if hit.get("largeImageURL")]


SEARCHES = {"Pexels": _search_pexels, "Pixabay": _search_pixabay}
LICENCES = {
    "Pexels": "Pexels licence, free for commercial use, attribution appreciated",
    "Pixabay": "Pixabay Content License, free for commercial use, attribution not required",
}


def _acceptable(photo, options):
    if photo.get("width", 0) < options["min_source_width"]:
        return False
    if not image_tools.is_landscape(photo.get("width", 0), photo.get("height", 1)):
        return False
    description = (photo.get("alt") or "").lower()
    return not any(word in description for word in options["skip_alt_keywords"])


def _download(photo, destination):
    url = photo["src"].get("large2x") or photo["src"].get("large") or photo["src"]["original"]
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def _room_left(taken_for_purpose, collected, options):
    return taken_for_purpose < options["per_purpose"] and len(collected) < options["max_total"]


def _take_next(candidates, query, purpose, out_dir, seen_ids, options, provider):
    for photo in candidates:
        if photo["id"] in seen_ids or not _acceptable(photo, options):
            continue

        target = out_dir / purpose / "{}_{}.jpg".format(purpose, photo["id"])
        try:
            _download(photo, target)
        except requests.RequestException:
            continue

        width, height = image_tools.dimensions(target)
        seen_ids.add(photo["id"])
        return {
            "file": str(target.relative_to(out_dir)).replace("\\", "/"),
            "purpose": purpose,
            "query": query,
            "width": width,
            "height": height,
            "description": photo.get("alt") or "",
            "source": provider,
            "source_url": photo["url"],
            "photographer": photo["photographer"],
            "photographer_url": photo["photographer_url"],
            "licence": LICENCES[provider],
        }
    return None


def collect(plan, out_dir, settings, on_event=None):
    options = settings["stock_photos"]
    provider, key = _provider()
    out_dir = Path(out_dir)

    collected = []
    seen_ids = set()

    for purpose, queries in plan["queries"].items():
        (out_dir / purpose).mkdir(parents=True, exist_ok=True)
        taken_for_purpose = 0
        candidates = {}
        exhausted = set()

        while _room_left(taken_for_purpose, collected, options) and len(exhausted) < len(set(queries)):
            for query in queries:
                if not _room_left(taken_for_purpose, collected, options):
                    break
                if query in exhausted:
                    continue
                if query not in candidates:
                    if on_event:
                        on_event('searching "{}" for {}'.format(query, purpose))
                    candidates[query] = iter(SEARCHES[provider](query, key, options))

                photo = _take_next(candidates[query], query, purpose, out_dir, seen_ids, options, provider)
                if photo is None:
                    exhausted.add(query)
                    continue
                collected.append(photo)
                taken_for_purpose += 1

    sources = {
        "business": plan.get("business", ""),
        "source": provider,
        "photos": collected,
    }
    (out_dir / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return collected


def _plan_named(plans, category):
    wanted = lead_store.to_slug(category or "", "")
    for name, queries in plans.items():
        if wanted and name != "default" and lead_store.to_slug(name, "") == wanted:
            return queries
    return None


def plan_for_category(category, settings, business="", note=""):
    plans = settings["stock_photos"]["plans"]
    key = (category or "").strip().lower()
    queries = _plan_named(plans, category)
    matched = bool(queries)

    if not matched:
        label = key.replace("_", " ") or "local business"
        queries = {
            purpose: [text.format(category=label) for text in terms]
            for purpose, terms in plans["default"].items()
        }
    else:
        queries = {purpose: list(terms) for purpose, terms in queries.items()}

    words = (note or "").replace(",", " ").split()
    if words:
        most = settings["stock_photos"]["note_max_words"]
        if len(words) > most:
            raise StockPhotoError(
                "--note is searched as one more term for hero and interior, so it takes at most {} "
                "words and got {}. A long sentence matches pictures by stray words and loses the "
                "trade. Keep what a photo search would use, such as \"exposed brick industrial\".".format(
                    most, len(words)
                )
            )
        label = key.replace("_", " ") or "local business"
        for purpose in ("hero", "interior"):
            if purpose in queries:
                queries[purpose].append("{} {}".format(" ".join(words), label))

    return {"business": business, "category": category, "matched": matched, "queries": queries}


def _plan_from_arguments(arguments, settings):
    if arguments.plan:
        path = Path(arguments.plan)
        if not path.exists():
            raise StockPhotoError("Plan file {} does not exist.".format(path))
        return json.loads(path.read_text(encoding="utf-8"))

    if arguments.category:
        return plan_for_category(
            arguments.category, settings, arguments.business or "", arguments.note or ""
        )

    if not arguments.query:
        raise StockPhotoError("Give --category, or --plan, or at least one --query.")

    return {"business": arguments.business or "", "queries": {arguments.purpose: arguments.query}}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Downloads free stock photographs for a business, grouped by where they go on the site."
    )
    parser.add_argument("--plan", help="JSON file holding the business name and one query list per purpose")
    parser.add_argument("--category", help="Trade of the business, which picks a ready query plan from config.yaml")
    parser.add_argument(
        "--note",
        help=(
            "A few English words about how the place looks, at most stock_photos.note_max_words, "
            "searched as one more term for hero and interior"
        ),
    )
    parser.add_argument("--query", action="append", help="A single search term, repeatable")
    parser.add_argument("--purpose", default="gallery", help="Where the --query photos belong on the site")
    parser.add_argument("--business", help="Business name, used for the output folder")
    parser.add_argument(
        "--out", help="Output folder, defaults to assets/stock/<business>, or assets/stock/unnamed without --business"
    )
    arguments = parser.parse_args()

    try:
        settings = lead_search.load_settings()
        plan = _plan_from_arguments(arguments, settings)
        business = (plan.get("business") or "").strip()
        out_dir = Path(arguments.out) if arguments.out else ROOT / "assets" / "stock" / lead_store.to_slug(business, "unnamed")

        print("\nBusiness: {}".format(business or "not given"))
        if plan.get("category"):
            fit = "ready plan" if plan.get("matched") else "generic plan, no entry in config.yaml"
            print("Trade: {} ({})".format(plan["category"], fit))
        print("Folder: {}\n".format(out_dir))

        collected = collect(plan, out_dir, settings, on_event=lambda message: print("  " + message))
    except StockPhotoError as error:
        print("\nERROR: {}\n".format(error))
        raise SystemExit(1)

    if not collected:
        print("\nNothing matched the filters. Try broader search terms.\n")
        return

    print("\nDownloaded {} photographs:\n".format(len(collected)))
    for photo in collected:
        print("  {:<28} {:>5}x{:<5} {}".format(
            photo["file"], photo["width"], photo["height"], photo["photographer"]
        ))
    print("\nCredits written to {}\n".format(out_dir / "sources.json"))


if __name__ == "__main__":
    main()

import csv
import hashlib
import re
import unicodedata
from pathlib import Path

COLUMNS = [
    "score",
    "name",
    "category",
    "address",
    "rating",
    "review_count",
    "website",
    "website_score",
    "website_problems",
    "phone",
    "opening_hours",
    "google_maps_link",
    "map_pin",
    "contact_search",
    "place_id",
    "status",
    "email",
    "instagram",
    "facebook",
    "chain",
    "description",
    "review_notes",
]

CONTACT_FIELDS = ["email", "instagram", "facebook"]

STATUSES = ["", "contacted", "declined", "accepted"]

PHONE_DIGITS_COMPARED = 9

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e",
    "ж": "z", "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj",
    "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c",
    "џ": "dz", "ш": "s", "ѓ": "gj", "ќ": "kj", "ѕ": "dz", "й": "j", "ы": "y",
    "э": "e", "ю": "ju", "я": "ja", "щ": "sc", "ъ": "", "ь": "", "ё": "e",
    "є": "je", "і": "i", "ї": "ji", "ґ": "g", "ў": "u",
}


class FileLocked(Exception):
    pass


def to_slug(text, fallback="search"):
    lowered = unicodedata.normalize("NFC", text).lower().replace("đ", "dj")
    transliterated = "".join(CYRILLIC_TO_LATIN.get(char, char) for char in lowered)
    decomposed = unicodedata.normalize("NFKD", transliterated)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    if any(char.isalnum() and not char.isascii() for char in plain):
        digest = hashlib.sha1(lowered.strip().encode("utf-8")).hexdigest()[:8]
        return "{}-{}".format(slug or fallback, digest)
    return slug or fallback


def data_dir(root):
    return Path(root) / "data"


def output_path(root, query):
    return data_dir(root) / "leads_{}.csv".format(to_slug(query))


def find_previous(root, query):
    folder = data_dir(root)
    if not folder.exists():
        return None
    current = output_path(root, query)
    return current if current.exists() else None


def list_files(root):
    folder = data_dir(root)
    if not folder.exists():
        return []
    files = sorted(folder.glob("leads_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.name for path in files]


def load(path):
    if not path or not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return {row["place_id"]: row for row in csv.DictReader(handle) if row.get("place_id")}


def load_rows(path):
    if not path or not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.DictReader(handle) if row.get("place_id")]


def _as_number(value, fallback):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def _row_ranking_key(row):
    return -_as_number(row.get("score"), 0), _as_number(row.get("website_score"), -1)


def _phone_key(value):
    digits = re.sub(r"\D", "", value or "")
    return digits[-PHONE_DIGITS_COMPARED:] if len(digits) >= PHONE_DIGITS_COMPARED else ""


def _retire_duplicates(merged, new_leads):
    owners = {_phone_key(lead.get("phone")): lead["place_id"] for lead in new_leads}
    owners.pop("", None)
    for place_id, row in list(merged.items()):
        owner = owners.get(_phone_key(row.get("phone")))
        if not owner or owner == place_id:
            continue
        del merged[place_id]
        if row.get("status") and owner not in merged:
            merged[owner] = {column: "" for column in COLUMNS}
            merged[owner]["status"] = row["status"]


def merge(new_leads, existing_rows):
    merged = {}

    for place_id, row in existing_rows.items():
        merged[place_id] = {column: row.get(column, "") for column in COLUMNS}

    _retire_duplicates(merged, new_leads)

    for lead in new_leads:
        place_id = lead["place_id"]
        row = merged.get(place_id, {column: "" for column in COLUMNS})
        previous_status = row.get("status", "")
        row.update(
            {
                "score": lead["score"],
                "name": lead.get("name", ""),
                "category": lead.get("category", ""),
                "address": lead.get("address") or row.get("address", ""),
                "rating": row.get("rating", "") if lead.get("rating") is None else lead["rating"],
                "review_count": row.get("review_count", "") if lead.get("review_count") is None else lead["review_count"],
                "website": lead.get("website", ""),
                "phone": lead.get("phone") or row.get("phone", ""),
                "opening_hours": lead.get("opening_hours") or row.get("opening_hours", ""),
                "google_maps_link": lead.get("google_maps_link", ""),
                "map_pin": lead.get("map_pin", ""),
                "contact_search": lead.get("contact_search", ""),
                "place_id": place_id,
                "status": previous_status,
                "chain": lead.get("chain", ""),
                "description": lead.get("description") or row.get("description", ""),
                "review_notes": lead.get("review_notes") or row.get("review_notes", ""),
            }
        )
        for column in CONTACT_FIELDS:
            row[column] = (lead.get(column) or "").strip() or row.get(column, "")

        if not (lead.get("website") or "").strip():
            row["website_score"] = ""
            row["website_problems"] = ""
        elif lead.get("website_score") is not None:
            row["website_score"] = lead["website_score"]
            row["website_problems"] = "; ".join(lead.get("website_problems") or [])

        merged[place_id] = row

    rows = list(merged.values())
    rows.sort(key=_row_ranking_key)
    return rows


def save(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        raise FileLocked(
            "{} is open in another program, most likely Excel. Close it and try again.".format(path.name)
        )
    return path


TYPED_FIELDS = ["address", "phone", "opening_hours", "rating", "review_count"]


def update_fields(path, place_id, fields):
    rows = load_rows(path)
    changed = False
    for row in rows:
        if row["place_id"] == place_id:
            for column, value in fields.items():
                if column in COLUMNS:
                    row[column] = value
                    changed = True
    if changed:
        save(path, rows)
    return changed


def update_status(path, place_id, status):
    rows = load_rows(path)
    changed = False
    for row in rows:
        if row["place_id"] == place_id:
            row["status"] = status
            changed = True
    if changed:
        save(path, rows)
    return changed

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

COLUMNS = [
    "place_id",
    "name",
    "channel",
    "sent_at",
    "response",
    "response_at",
    "follow_up_due",
    "notes",
]

RESPONSES = ["", "interested", "declined", "no answer", "replied"]


class OutreachError(Exception):
    pass


def log_path(root):
    return Path(root) / "data" / "outreach.csv"


def load(root):
    path = log_path(root)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.DictReader(handle) if row.get("place_id")]


def save(root, rows):
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        raise OutreachError("outreach.csv is open in another program, most likely Excel. Close it and try again.")
    return path


def record_send(root, place_id, name, channel, settings, sent_at=None, notes=""):
    if channel not in settings["outreach"]["channels"]:
        raise OutreachError(
            "'{}' is not one of the channels in config.yaml: {}".format(
                channel, ", ".join(settings["outreach"]["channels"])
            )
        )

    sent = sent_at or date.today().isoformat()
    due = (datetime.fromisoformat(sent) + timedelta(days=settings["outreach"]["follow_up_days"])).date()

    rows = load(root)
    for row in rows:
        if row["place_id"] == place_id and row["channel"] == channel:
            row.update({"sent_at": sent, "follow_up_due": due.isoformat(), "notes": notes or row["notes"]})
            save(root, rows)
            return row

    row = {
        "place_id": place_id,
        "name": name,
        "channel": channel,
        "sent_at": sent,
        "response": "",
        "response_at": "",
        "follow_up_due": due.isoformat(),
        "notes": notes,
    }
    rows.append(row)
    save(root, rows)
    return row


def record_response(root, place_id, response, notes=""):
    if response not in RESPONSES:
        raise OutreachError("'{}' is not one of: {}".format(response, ", ".join(filter(None, RESPONSES))))

    rows = load(root)
    touched = []
    for row in rows:
        if row["place_id"] != place_id:
            continue
        row["response"] = response
        row["response_at"] = date.today().isoformat()
        row["follow_up_due"] = ""
        if notes:
            row["notes"] = notes
        touched.append(row)

    if not touched:
        raise OutreachError("No outreach logged for place_id {}.".format(place_id))

    save(root, rows)
    return touched


def due_for_follow_up(root, on=None):
    today = on or date.today()
    due = []
    for row in load(root):
        if row["response"] or not row["follow_up_due"]:
            continue
        if date.fromisoformat(row["follow_up_due"]) <= today:
            waiting = (today - date.fromisoformat(row["sent_at"])).days
            due.append(dict(row, days_waiting=waiting))
    return sorted(due, key=lambda row: row["days_waiting"], reverse=True)


def summary(root):
    rows = load(root)
    return {
        "total": len(rows),
        "awaiting": sum(1 for row in rows if not row["response"]),
        "interested": sum(1 for row in rows if row["response"] == "interested"),
        "declined": sum(1 for row in rows if row["response"] == "declined"),
    }

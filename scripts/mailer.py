import argparse
import csv
import email
import imaplib
import json
import os
import random
import re
import smtplib
import ssl
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr, parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autopilot
import dashboard
import lead_search
import lead_store
import outreach_log
import shift_control

ROOT = lead_search.ROOT
USER_ENV = "ZOHO_SMTP_USER"
PASSWORD_ENV = "ZOHO_SMTP_PASSWORD"
LOG_COLUMNS = ["place_id", "name", "email", "kind", "subject", "message_id", "sent_at", "answer", "answer_at"]
FIRST = "first"
FOLLOW_UP = "follow_up"
REPLIED = "replied"
OPTED_OUT = "opted_out"
BOUNCED = "bounced"
OTHER = "other"
EMAIL_TITLE = "email"
LEFT_ALONE = {"declined", "accepted"}
ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
US_STATE = re.compile(r",\s*([A-Z]{2})\s+\d{5}")
QUOTE_START = re.compile(r"^(on .+wrote:|-+ ?original message ?-+|from: )", re.IGNORECASE)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LOCK_WAIT_SECONDS = 30
LOCK_STALE_SECONDS = 300


class MailError(Exception):
    pass


def _folder(root=None):
    return lead_store.data_dir(root or ROOT) / "mailer"


def log_path(root=None):
    return lead_store.data_dir(root or ROOT) / "mail_log.csv"


def _control_path(root=None):
    return _folder(root) / "control.json"


def _status_path(root=None):
    return _folder(root) / "status.json"


def _worker_path(root=None):
    return _folder(root) / "worker.json"


def _inbox_path(root=None):
    return _folder(root) / "inbox.json"


def _skipped_path(root=None):
    return _folder(root) / "skipped.json"


def _activity_path(root=None):
    return _folder(root) / "mailer.log"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path, empty):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def _locked(root=None):
    path = _folder(root) / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise MailError("The mail files are busy. Try again in a moment.")
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(handle)
        path.unlink(missing_ok=True)


def load_log(root=None):
    path = log_path(root)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [dict(dict.fromkeys(LOG_COLUMNS, ""), **row) for row in csv.DictReader(handle) if row.get("place_id")]


def _save_log(rows, root=None):
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(temporary, path)
    except PermissionError:
        raise MailError("mail_log.csv is open in another program, most likely Excel. Close it.")


def credentials():
    load_dotenv(ROOT / ".env")
    return (os.getenv(USER_ENV) or "").strip(), (os.getenv(PASSWORD_ENV) or "").strip()


def is_set_up(settings):
    user, password = credentials()
    options = settings["mailer"]
    return bool(user and password and options["smtp_host"] and options["imap_host"])


def _nth_sunday(year, month, nth):
    if nth > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _at_utc(day, hours):
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=hours)


def summer_time(rule, standard, moment):
    if rule == "us":
        start = _at_utc(_nth_sunday(moment.year, 3, 2), 2 - standard)
        end = _at_utc(_nth_sunday(moment.year, 11, 1), 1 - standard)
        return start <= moment < end
    if rule == "eu":
        return _at_utc(_nth_sunday(moment.year, 3, -1), 1) <= moment < _at_utc(_nth_sunday(moment.year, 10, -1), 1)
    return False


def place_of(site, settings):
    zones = settings["mailer"]["time_zones"]
    address = (site.get("address") or "").strip()
    code = (site.get("country_code") or "").lower()
    if not code:
        countries = {city["country"]: city["code"] for city in settings["autopilot"]["cities"] if city.get("country") and city.get("code")}
        country = address.rsplit(",", 1)[-1].strip()
        code = "us" if country in ("United States", "USA") else countries.get(country, "")
    if code == "us":
        state = US_STATE.search(address)
        abbreviation = state.group(1) if state else ""
        if abbreviation not in zones["us_states"]:
            return None
        rule = "" if abbreviation in zones["no_summer_time"] else "us"
        return {"offset": zones["us_states"][abbreviation], "rule": rule, "label": abbreviation + ", USA"}
    if code in zones["countries"]:
        return {"offset": zones["countries"][code], "rule": "eu", "label": code.upper()}
    return None


def local_time(place, moment):
    if not place:
        return moment.astimezone()
    offset = place["offset"] + (1 if summer_time(place["rule"], place["offset"], moment) else 0)
    return moment.astimezone(timezone(timedelta(hours=offset)))


def in_window(place, moment, options):
    here = local_time(place, moment)
    if options["weekdays_only"] and here.weekday() >= 5:
        return False
    return options["send_from_hour"] <= here.hour < options["send_until_hour"]


def _sent_on(row):
    return datetime.fromisoformat(row["sent_at"]).date()


def daily_cap(rows, options, today):
    earlier = {_sent_on(row) for row in rows if row["sent_at"] and _sent_on(row) < today}
    return min(options["daily_most"], options["first_day"] + options["daily_step"] * len(earlier))


def sent_today(rows, today):
    return sum(1 for row in rows if row["sent_at"] and _sent_on(row) == today)


def first_address(value):
    for part in re.split(r"[;,\s]+", value or ""):
        if ADDRESS.fullmatch(part):
            return part.lower()
    return ""


def moved_link(text, live_url, settings):
    address = (settings["publish"].get("address") or "").strip().rstrip("/")
    origin = re.match(r"https?://[^/]+", live_url or "")
    return text.replace(origin.group(0), address) if address and origin else text


def signature(settings, with_address=False):
    outreach = settings["outreach"]
    parts = [outreach["sender_name"], settings["mailer"]["signature_extra"]]
    if with_address:
        parts.append(outreach["postal_address"])
    return "\n".join(part for part in parts if part)


def signed(body, settings):
    extra = settings["mailer"]["signature_extra"]
    name = settings["outreach"]["sender_name"]
    if not extra or extra in body:
        return body
    lines = body.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if name and lines[index].strip() == name:
            lines.insert(index + 1, extra)
            return "\n".join(lines)
    return body.rstrip() + "\n\n" + extra


def _email_draft(site):
    text = next((item["text"] for item in site["messages"] if item["title"].lower() == EMAIL_TITLE), "")
    return autopilot._email_parts(text)


def _first_email(site, address, settings):
    subject, body = _email_draft(site)
    if not subject or not body:
        return None
    return {
        "kind": FIRST,
        "place_id": site["place_id"],
        "name": site["name"],
        "email": address,
        "subject": subject,
        "body": signed(moved_link(body, site["live_url"], settings), settings),
        "place": place_of(site, settings),
        "replying_to": "",
    }


def _follow_up(row, site, settings):
    link = moved_link(site["live_url"], site["live_url"], settings)
    body = settings["mailer"]["follow_up_text"].format(
        name=row["name"], link=link, signature=signature(settings, with_address=True)
    )
    subject = row["subject"] if row["subject"].lower().startswith("re:") else "Re: " + row["subject"]
    return {
        "kind": FOLLOW_UP,
        "place_id": row["place_id"],
        "name": row["name"],
        "email": row["email"],
        "subject": subject,
        "body": body.strip(),
        "place": place_of(site, settings),
        "replying_to": row["message_id"],
    }


def queue(gathered, rows, skipped, settings, today):
    sites = {site["place_id"]: site for site in gathered["sites"] if site["place_id"]}
    used = {row["email"] for row in rows} | {row["place_id"] for row in rows}
    answered = {row["place_id"] for row in rows if row["answer"]}
    followed = {row["place_id"] for row in rows if row["kind"] == FOLLOW_UP}

    follow_ups = []
    if settings["mailer"]["follow_up"]:
        wait = timedelta(days=settings["outreach"]["follow_up_days"])
        for row in rows:
            site = sites.get(row["place_id"])
            if row["kind"] != FIRST or not site or row["place_id"] in answered | followed | skipped:
                continue
            if site["stage"] in LEFT_ALONE or _sent_on(row) + wait > today:
                continue
            follow_ups.append(_follow_up(row, site, settings))

    firsts = []
    for site in sorted(sites.values(), key=lambda item: item["built_at"] or item["brief_at"]):
        lead = gathered["businesses"].get(site["place_id"], {})
        address = first_address(lead.get("email"))
        if site["stage"] != "ready" or not (site["live_url"] and site["live_public"]):
            continue
        if not address or address in used or site["place_id"] in used | skipped:
            continue
        item = _first_email(site, address, settings)
        if item:
            firsts.append(item)
            used.add(address)
    return follow_ups + firsts


def build_message(item, settings, user):
    message = EmailMessage()
    message["From"] = formataddr((settings["outreach"]["sender_name"], user))
    message["To"] = item["email"]
    message["Subject"] = item["subject"]
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=user.rsplit("@", 1)[-1])
    message["List-Unsubscribe"] = "<mailto:{}?subject=unsubscribe>".format(user)
    if item.get("replying_to"):
        message["In-Reply-To"] = item["replying_to"]
        message["References"] = item.get("references") or item["replying_to"]
    message.set_content(item["body"])
    return message


def deliver(message, settings):
    user, password = credentials()
    options = settings["mailer"]
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(options["smtp_host"], options["smtp_port"], context=context, timeout=options["timeout_seconds"]) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)


def send(item, settings, root=None):
    user, _ = credentials()
    message = build_message(item, settings, user)
    deliver(message, settings)
    row = {
        "place_id": item["place_id"],
        "name": item["name"],
        "email": item["email"],
        "kind": item["kind"],
        "subject": item["subject"],
        "message_id": message["Message-ID"],
        "sent_at": _now(),
        "answer": "",
        "answer_at": "",
    }
    with _locked(root):
        rows = load_log(root)
        rows.append(row)
        _save_log(rows, root)
    if item["kind"] == FIRST:
        try:
            outreach_log.record_send(root or ROOT, item["place_id"], item["name"], "email", settings)
        except outreach_log.OutreachError:
            pass
    return row


def _header(value):
    try:
        return str(make_header(decode_header(value or ""))).strip()
    except (UnicodeDecodeError, LookupError):
        return (value or "").strip()


def _part_text(part):
    payload = part.get_payload(decode=True) or b""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _body_text(message):
    parts = [part for part in message.walk() if not part.is_multipart() and part.get_content_disposition() != "attachment"]
    plain = next((part for part in parts if part.get_content_type() == "text/plain"), None)
    if plain is not None:
        return _part_text(plain).strip()
    html = next((part for part in parts if part.get_content_type() == "text/html"), None)
    if html is None:
        return ""
    return BeautifulSoup(_part_text(html), "html.parser").get_text("\n").strip()


def _stamp(value):
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def parse(raw, uid, options):
    message = email.message_from_bytes(raw)
    name, sender = parseaddr(_header(message.get("From")))
    references = re.findall(r"<[^>]+>", " ".join(filter(None, [message.get("In-Reply-To"), message.get("References")])))
    return {
        "uid": uid,
        "from_name": name,
        "from_email": sender.lower(),
        "subject": _header(message.get("Subject")),
        "date": _stamp(message.get("Date")),
        "message_id": (message.get("Message-ID") or "").strip(),
        "references": references,
        "text": re.sub(r"\n{3,}", "\n\n", _body_text(message))[: options["text_kept"]],
    }


def new_part(text):
    kept = []
    for line in (text or "").splitlines():
        if line.startswith(">") or QUOTE_START.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def classify(item, rows, options):
    firsts = {row["email"]: row for row in rows if row["kind"] == FIRST}
    if any(word in item["from_email"] for word in options["bounce_senders"]):
        for found in ADDRESS.finditer(item["text"]):
            row = firsts.get(found.group(0).lower())
            if row:
                return BOUNCED, row
        return OTHER, None
    by_id = {row["message_id"]: row for row in rows if row["message_id"]}
    row = next((by_id[reference] for reference in item["references"] if reference in by_id), None)
    row = row or firsts.get(item["from_email"])
    if not row:
        return OTHER, None
    row = firsts.get(row["email"], row)
    words = new_part(item["text"]).lower()
    whole = words.strip(" .!\n")
    if whole in options["opt_out_whole"] or any(
        re.search(r"\b{}\b".format(re.escape(word)), words) for word in options["opt_out_words"]
    ):
        return OPTED_OUT, row
    return REPLIED, row


def _imap_since(day):
    return "{:02d}-{}-{}".format(day.day, MONTHS[day.month - 1], day.year)


def fetch_inbox(settings, known):
    options = settings["mailer"]
    user, password = credentials()
    imap = imaplib.IMAP4_SSL(
        options["imap_host"], options["imap_port"], ssl_context=ssl.create_default_context(), timeout=options["timeout_seconds"]
    )
    try:
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        since = _imap_since(date.today() - timedelta(days=options["inbox_days"]))
        _, found = imap.uid("search", None, "SINCE", since)
        uids = [uid.decode() for uid in (found[0] or b"").split()][-options["inbox_kept"]:]
        fetched = []
        for uid in uids:
            if uid in known:
                fetched.append(known[uid])
                continue
            _, parts = imap.uid("fetch", uid, "(BODY.PEEK[])")
            raw = next((part[1] for part in parts if isinstance(part, tuple)), b"")
            if raw:
                fetched.append(parse(raw, uid, options))
        return fetched
    finally:
        try:
            imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


def _apply_answers(items, rows, options):
    changes = []
    firsts = {row["place_id"]: row for row in rows if row["kind"] == FIRST}
    for item in sorted(items, key=lambda entry: entry["date"]):
        kind, row = classify(item, rows, options)
        item["kind"] = kind
        item["place_id"] = row["place_id"] if row else ""
        item["business"] = row["name"] if row else ""
        first = firsts.get(item["place_id"])
        if not first or kind == OTHER:
            continue
        if not first["answer"] or (first["answer"] == REPLIED and kind == OPTED_OUT):
            first["answer"] = kind
            first["answer_at"] = item["date"] or _now()
            if kind != BOUNCED:
                changes.append((first["place_id"], "declined" if kind == OPTED_OUT else "replied"))
    return changes


def check_inbox(settings, root=None):
    previous = _read_json(_inbox_path(root), {}).get("messages", [])
    known = {item["uid"]: item for item in previous}
    items = fetch_inbox(settings, known)
    with _locked(root):
        rows = load_log(root)
        changes = _apply_answers(items, rows, settings["mailer"])
        if changes:
            _save_log(rows, root)
        items.sort(key=lambda entry: entry["date"], reverse=True)
        _write_json(_inbox_path(root), {"checked_at": _now(), "messages": items})
    for place_id, response in changes:
        try:
            outreach_log.record_response(root or ROOT, place_id, response)
        except outreach_log.OutreachError:
            pass
    return items


def reply(uid, text, settings, root=None):
    text = (text or "").strip()
    if not text:
        raise MailError("Write the answer first.")
    item = next((entry for entry in _read_json(_inbox_path(root), {}).get("messages", []) if entry["uid"] == uid), None)
    if not item:
        raise MailError("That message is no longer in the inbox. Check the inbox again.")
    user, _ = credentials()
    subject = item["subject"] if item["subject"].lower().startswith("re:") else "Re: " + item["subject"]
    references = " ".join(item["references"] + ([item["message_id"]] if item["message_id"] else []))
    message = build_message(
        {
            "email": item["from_email"],
            "subject": subject,
            "body": text + "\n\n" + signature(settings),
            "replying_to": item["message_id"],
            "references": references,
        },
        settings,
        user,
    )
    deliver(message, settings)
    with _locked(root):
        inbox = _read_json(_inbox_path(root), {"messages": []})
        for entry in inbox["messages"]:
            if entry["uid"] == uid:
                entry["answered_at"] = _now()
        _write_json(_inbox_path(root), inbox)


def control(root=None):
    return dict({"on": False, "send_now": ""}, **_read_json(_control_path(root), {}))


def set_control(root=None, **changes):
    with _locked(root):
        current = control(root)
        current.update(changes)
        _write_json(_control_path(root), current)
    return current


def start_now(root=None):
    return set_control(root, send_now=date.today().isoformat())


def skipped(root=None):
    return set(_read_json(_skipped_path(root), []))


def skip(place_id, root=None):
    with _locked(root):
        _write_json(_skipped_path(root), sorted(skipped(root) | {place_id}))


def wanted(root=None, today=None):
    current = control(root)
    return bool(current["on"] or current["send_now"] == (today or date.today()).isoformat())


def worker_alive(settings, root=None):
    record = _read_json(_worker_path(root), {})
    if not record.get("pid") or not shift_control.is_alive(record["pid"]):
        return False
    beat = max(_read_json(_status_path(root), {}).get("beat") or "", record.get("started") or "")
    if not beat:
        return False
    return (datetime.now() - datetime.fromisoformat(beat)).total_seconds() < settings["mailer"]["heartbeat_seconds"]


def _hold_worker_lock(root=None):
    path = _folder(root) / "worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def ensure_worker(settings, root=None):
    if not is_set_up(settings) or not wanted(root) or worker_alive(settings, root):
        return False
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "run"],
        cwd=str(root or ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    _write_json(_worker_path(root), {"pid": process.pid, "started": _now()})
    return True


def next_email(settings, root=None, today=None, moment=None, sent_here=()):
    options = settings["mailer"]
    today = today or date.today()
    rows = load_log(root)
    cap = daily_cap(rows, options, today)
    if sent_today(rows, today) >= cap:
        return None, "Today's {} emails are sent. More go out tomorrow.".format(cap)
    items = [
        item
        for item in queue(dashboard.gather(settings, root=root or ROOT), rows, skipped(root), settings, today)
        if (item["place_id"], item["kind"]) not in sent_here
    ]
    if not items:
        return None, "Nothing left to send. New sites with an email join the queue on their own."
    right_away = control(root)["send_now"] == today.isoformat()
    moment = moment or datetime.now(timezone.utc)
    ready = [item for item in items if right_away or in_window(item["place"], moment, options)]
    if not ready:
        return None, "Waiting for {} to {} on a weekday in the businesses' own time.".format(
            options["send_from_hour"], options["send_until_hour"]
        )
    return ready[0], ""


def _beat(root, note, next_at):
    _write_json(_status_path(root), {"beat": _now(), "note": note, "next_at": next_at})


def work(root=None, say=print):
    sent_here = set()
    next_send = next_inbox = 0.0
    note = next_at = ""
    _beat(root, "Starting.", "")
    while True:
        settings = lead_search.load_settings()
        options = settings["mailer"]
        if not wanted(root):
            break
        if time.monotonic() >= next_inbox:
            try:
                check_inbox(settings, root)
            except (OSError, imaplib.IMAP4.error, MailError) as error:
                say("Could not read the inbox: {}".format(error))
            next_inbox = time.monotonic() + options["inbox_minutes"] * 60
        if time.monotonic() >= next_send:
            wait = options["idle_minutes"] * 60
            try:
                item, note = next_email(settings, root, sent_here=sent_here)
            except Exception as error:
                item, note = None, "Could not build the queue: {}".format(error)
                say(note)
            if item:
                try:
                    send(item, settings, root)
                except (smtplib.SMTPException, OSError, MailError) as error:
                    note = "Sending to {} failed: {}".format(item["email"], error)
                    wait = options["retry_minutes"] * 60
                else:
                    sent_here.add((item["place_id"], item["kind"]))
                    note = "Sent {} to {}.".format("the follow-up" if item["kind"] == FOLLOW_UP else "the first email", item["name"])
                    wait = random.uniform(options["gap_minutes_least"], options["gap_minutes_most"]) * 60
                say(note)
            elif not control(root)["on"]:
                set_control(root, send_now="")
            next_send = time.monotonic() + wait
            next_at = (datetime.now() + timedelta(seconds=wait)).isoformat(timespec="seconds") if item else ""
        _beat(root, note, next_at)
        time.sleep(options["tick_seconds"])
    _beat(root, "Sending is off.", "")


def _queue_view(item, moment):
    here = local_time(item["place"], moment)
    return {
        "kind": item["kind"],
        "place_id": item["place_id"],
        "name": item["name"],
        "email": item["email"],
        "subject": item["subject"],
        "body": item["body"],
        "where": item["place"]["label"] if item["place"] else "",
        "their_time": here.strftime("%a %H:%M") if item["place"] else "",
    }


def overview(settings, root=None, gathered=None):
    options = settings["mailer"]
    today = date.today()
    rows = load_log(root)
    gathered = gathered or dashboard.gather(settings, root=root or ROOT)
    items = queue(gathered, rows, skipped(root), settings, today)
    moment = datetime.now(timezone.utc)
    current = control(root)
    status = _read_json(_status_path(root), {})
    inbox = _read_json(_inbox_path(root), {})
    firsts = [row for row in rows if row["kind"] == FIRST]
    mailed = {row["place_id"] for row in rows}
    without_email = [
        site for site in gathered["sites"]
        if site["stage"] == "ready" and site["place_id"] not in mailed
        and not first_address(gathered["businesses"].get(site["place_id"], {}).get("email"))
    ]
    working = worker_alive(settings, root)
    user, _ = credentials()
    return {
        "set_up": is_set_up(settings),
        "sender": user,
        "on": current["on"],
        "sending_now": current["send_now"] == today.isoformat(),
        "working": working,
        "note": status.get("note", "") if working else "",
        "next_at": status.get("next_at", "") if working else "",
        "today": sent_today(rows, today),
        "cap": daily_cap(rows, options, today),
        "most": options["daily_most"],
        "hours": [options["send_from_hour"], options["send_until_hour"]],
        "weekdays_only": options["weekdays_only"],
        "demo_address": settings["publish"].get("address") or "",
        "counts": {
            "queue": sum(1 for item in items if item["kind"] == FIRST),
            "follow_ups": sum(1 for item in items if item["kind"] == FOLLOW_UP),
            "sent": len(firsts),
            "waiting": sum(1 for row in firsts if not row["answer"]),
            "replied": sum(1 for row in firsts if row["answer"] == REPLIED),
            "opted_out": sum(1 for row in firsts if row["answer"] == OPTED_OUT),
            "bounced": sum(1 for row in firsts if row["answer"] == BOUNCED),
            "without_email": len(without_email),
        },
        "queue": [_queue_view(item, moment) for item in items[: options["shown_in_queue"]]],
        "sent": sorted(rows, key=lambda row: row["sent_at"], reverse=True)[: options["shown_sent"]],
        "inbox": inbox.get("messages", []),
        "checked_at": inbox.get("checked_at", ""),
    }


def _say_to(root):
    path = _activity_path(root)

    def say(text):
        line = "{} {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text)
        print(line)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    return say


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    parser = argparse.ArgumentParser(description="Sends the drafted emails of finished sites and reads the answers.")
    parser.add_argument("action", choices=["run", "queue", "inbox", "login"])
    arguments = parser.parse_args()
    settings = lead_search.load_settings()
    if not is_set_up(settings):
        print("\nSet {} and {} in .env, and mailer.smtp_host and mailer.imap_host in config.local.yaml.\n".format(USER_ENV, PASSWORD_ENV))
        raise SystemExit(1)

    if arguments.action == "run":
        held = _hold_worker_lock()
        if held is None:
            print("\nAnother mailer is already running.\n")
            return
        say = _say_to(ROOT)
        _write_json(_worker_path(), {"pid": os.getpid(), "started": _now()})
        say("Mailer starts.")
        work(say=say)
        say("Mailer stops.")
    elif arguments.action == "queue":
        for item in queue(dashboard.gather(settings), load_log(), skipped(), settings, date.today()):
            print("{:<10} {:<40} {}".format(item["kind"], item["name"][:40], item["email"]))
    elif arguments.action == "inbox":
        for item in check_inbox(settings):
            print("{:<9} {:<19} {:<35} {}".format(item["kind"], item["date"], item["from_email"][:35], item["subject"][:60]))
    else:
        user, password = credentials()
        options = settings["mailer"]
        with smtplib.SMTP_SSL(options["smtp_host"], options["smtp_port"], context=ssl.create_default_context(), timeout=options["timeout_seconds"]) as smtp:
            smtp.login(user, password)
        print("\nThe mailbox {} accepts the login. Nothing was sent.\n".format(user))


if __name__ == "__main__":
    main()

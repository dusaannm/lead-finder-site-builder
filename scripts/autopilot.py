import argparse
import ctypes
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, quote_plus, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_brief
import check_site
import contacts
import find_stock_photos
import lead_quality
import lead_search
import lead_store
import outreach_log
import pricing

ROOT = lead_search.ROOT
CODE = Path(__file__).resolve().parent.parent
COMMAND_FILE = "commands/autopilot.md"
MESSAGES_FILE = "outreach.md"
MESSAGE_HEADINGS = ["Email", "Viber or WhatsApp", "Instagram"]
CHECK_PROMPT = "Reply with the single word OK."
DESKTOP_COPIES = "Library/Application Support/Claude/claude-code"
POLL_SECONDS = 1.0
STOP_POLL_SECONDS = 0.3
SKIPPED_EVENT = '{"type":"user"'
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

REGIONS = {
    "us": "United States",
    "english": "English-speaking countries",
    "europe": "Europe",
    "world": "Anywhere in the list",
}

STACKS = {
    "plain": {"name": "Plain HTML, CSS and JavaScript", "needs_a_build": False},
    "astro": {"name": "Astro, built to static files", "needs_a_build": True},
    "vite": {"name": "Vite, built to static files", "needs_a_build": True},
}

SITE_FLAGS = ["faq", "careers", "show_reviews", "animations", "ai_media"]
SEARCH_FLAGS = ["only_without_website", "require_phone"]
BUILDER_FIELDS = ["command", "model", "timeout_minutes", "parallel"]
ACTIVE_STATES = {"searching", "building"}

UNATTENDED = """You are running unattended. The autopilot in the lead-finder browser page
started you, nobody reads this session while it runs, and nobody will answer a
question. Never ask one: wherever the instructions below would ask, take the
default they name.

`{{venv python}}` is `{python}` here. Only these work: reading any file, writing
files inside {output} and inside {scratch}, and running `{python} scripts/...`.
Everything else is refused, so do not try other commands. There is no browser
and no web access.
"""


class AutopilotError(Exception):
    pass


def settings_file(root=None):
    return lead_store.data_dir(root or ROOT) / "autopilot_settings.json"


def _read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def options(settings=None, root=None):
    settings = settings or lead_search.load_settings()
    merged = json.loads(json.dumps(settings["autopilot"]))
    return lead_search.merge_settings(merged, _read_json(settings_file(root)))


def _whole(value, low, high, label):
    if isinstance(value, bool):
        raise AutopilotError("{} has to be a whole number.".format(label))
    try:
        number = int(str(value).strip())
    except ValueError:
        raise AutopilotError("{} has to be a whole number, not {}.".format(label, value))
    if not low <= number <= high:
        raise AutopilotError("{} has to be between {} and {}, not {}.".format(label, low, high, number))
    return number


def _flag(value, label):
    if not isinstance(value, bool):
        raise AutopilotError("{} has to be on or off.".format(label))
    return value


def _text(value, longest, label, required=False):
    if not isinstance(value, str):
        raise AutopilotError("{} has to be text.".format(label))
    value = value.strip()
    if required and not value:
        raise AutopilotError("{} cannot be empty.".format(label))
    if len(value) > longest:
        raise AutopilotError("{} can be at most {} characters.".format(label, longest))
    return value


def _trades(value):
    if not isinstance(value, list):
        raise AutopilotError("The trades have to be a list.")
    cleaned = []
    for item in value:
        trade = _text(item, 40, "A trade", required=True)
        if trade.lower() not in [known.lower() for known in cleaned]:
            cleaned.append(trade)
    if not cleaned:
        raise AutopilotError("Pick at least one trade for the random choice.")
    return cleaned


def clean(payload, current):
    payload = payload or {}
    result = json.loads(json.dumps(current))

    if "sites_per_run" in payload:
        result["sites_per_run"] = _whole(payload["sites_per_run"], 1, 10, "Sites per run")
    if "search_limit" in payload:
        result["search_limit"] = _whole(payload["search_limit"], 10, 500, "Businesses to look through")
    for key in SEARCH_FLAGS:
        if key in payload:
            result[key] = _flag(payload[key], key)
    if "cities_from" in payload:
        if payload["cities_from"] not in REGIONS:
            raise AutopilotError("Random cities come from one of: {}.".format(", ".join(REGIONS)))
        result["cities_from"] = payload["cities_from"]
    if "trades" in payload:
        result["trades"] = _trades(payload["trades"])

    site = payload.get("site") or {}
    for key in SITE_FLAGS:
        if key in site:
            result["site"][key] = _flag(site[key], key)
    if "language" in site:
        result["site"]["language"] = _text(site["language"], 40, "The site language", required=True)
    if "stack" in site:
        if site["stack"] not in STACKS:
            raise AutopilotError("The stack is one of: {}.".format(", ".join(STACKS)))
        result["site"]["stack"] = site["stack"]
    if "style" in site:
        result["site"]["style"] = _text(site["style"], 300, "The style note")

    builder = payload.get("builder") or {}
    if "command" in builder:
        result["builder"]["command"] = _text(builder["command"], 500, "The Claude Code command")
    if "model" in builder:
        result["builder"]["model"] = _text(builder["model"], 100, "The model")
    if "timeout_minutes" in builder:
        result["builder"]["timeout_minutes"] = _whole(builder["timeout_minutes"], 5, 240, "The time limit")
    if "parallel" in builder:
        result["builder"]["parallel"] = _whole(builder["parallel"], 1, 5, "Sites built at the same time")

    return result


def save(payload, settings=None, root=None):
    cleaned = clean(payload, options(settings, root))
    stored = {
        "sites_per_run": cleaned["sites_per_run"],
        "search_limit": cleaned["search_limit"],
        "cities_from": cleaned["cities_from"],
        "trades": cleaned["trades"],
        "site": cleaned["site"],
        "builder": {key: cleaned["builder"][key] for key in BUILDER_FIELDS},
    }
    stored.update({key: cleaned[key] for key in SEARCH_FLAGS})
    _write_json(settings_file(root), stored)
    return cleaned


def cities_in(region, opts):
    every = [dict(city) for city in opts["cities"]]
    if region == "us":
        return [city for city in every if city["country"] == "United States"]
    if region == "english":
        return [city for city in every if city["language"] == "English"]
    if region == "europe":
        return [city for city in every if city["region"] == "europe"]
    return every


def random_city(opts, rng=None):
    pool = cities_in(opts["cities_from"], opts)
    if not pool:
        raise AutopilotError("autopilot.cities in config.yaml has no city for {}.".format(opts["cities_from"]))
    return (rng or random).choice(pool)


def resolve_city(text, opts):
    wanted = lead_store.to_slug(text or "", "")
    if not wanted:
        raise AutopilotError("Type a city, or pick a random one.")
    for city in opts["cities"]:
        names = [city["name"]] + list(city.get("aliases") or [])
        if any(lead_store.to_slug(name, "") == wanted for name in names):
            return dict(city)
    return {"name": text.strip(), "country": "", "language": "", "region": ""}


def pick_trade(text, opts, rng=None):
    text = (text or "").strip()
    if text:
        return text
    if not opts["trades"]:
        raise AutopilotError("Name a trade, or pick some for the random choice in the settings.")
    return (rng or random).choice(opts["trades"])


def site_language(city, opts):
    chosen = opts["site"]["language"].strip()
    if chosen.lower() != "city":
        return chosen
    return (city or {}).get("language") or ""


def project_folder(name, settings):
    return build_brief.output_dir(settings) / build_brief.folder_name(name)


def _number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _known_facts(row):
    return sum(1 for column in ("address", "opening_hours") if (row.get(column) or "").strip())


def contact_check(path, opts, settings, city):
    api_key = lead_search.search_key()
    searches_left = [settings["contacts"]["max_searches_per_run"]]

    def still_a_fit(row):
        if searches_left[0] < 1:
            return True
        searches_left[0] -= 1
        found = contacts.lookup(row, settings, ROOT, api_key, city.get("name", ""), city.get("code", ""))
        if found is None:
            return True
        new = {column: value for column, value in found.items() if value and not (row.get(column) or "").strip()}
        if new:
            row.update(new)
            lead_store.update_fields(path, row["place_id"], new)
        if opts["only_without_website"] and (row.get("website") or "").strip():
            return False
        return not opts["require_online_contact"] or _reachable_online(row)

    return still_a_fit


def _reachable_online(row):
    return any((row.get(column) or "").strip() for column in ("email", "facebook", "instagram"))


def choose_candidates(rows, opts, settings, root=None, still_a_fit=None):
    contacted = {row["place_id"] for row in outreach_log.load(root or ROOT)}
    ordered = sorted(
        rows, key=lambda row: (-_number(row.get("score")), -_known_facts(row), (row.get("name") or "").lower())
    )
    chosen = []
    folders = set()
    for row in ordered:
        folder = build_brief.folder_name(row.get("name") or "")
        if (row.get("status") or "").strip() or row["place_id"] in contacted or folder in folders:
            continue
        if opts["only_without_website"] and (row.get("website") or "").strip():
            continue
        if opts["require_phone"] and not (row.get("phone") or "").strip():
            continue
        if not lead_quality.meets_quality(row, opts):
            continue
        if (project_folder(row.get("name") or "", settings) / "brief.md").exists():
            continue
        if still_a_fit is not None and not still_a_fit(row):
            continue
        chosen.append(row)
        folders.add(folder)
        if len(chosen) >= opts["sites_per_run"]:
            break
    return chosen


def answers_file(place_id, root=None):
    slug = lead_store.to_slug(place_id, "lead")
    return lead_store.data_dir(root or ROOT) / "autopilot" / "answers" / "{}.json".format(slug)


def stock_folder(name, root=None):
    return (root or ROOT) / "assets" / "stock" / lead_store.to_slug(name, "unnamed")


def _photo_count(folder):
    return len(_read_json(Path(folder) / "sources.json").get("photos", []))


def prepare(place_id, city=None, trade="", settings=None, collect=None, on_event=None):
    settings = settings or lead_search.load_settings()
    opts = options(settings)
    lead, _ = build_brief.find_lead(place_id)
    path = answers_file(lead["place_id"])
    previous = _read_json(path)
    if city is None:
        city = {"name": previous.get("city", ""), "country": previous.get("country", ""), "language": ""}
        city["language"] = previous.get("language", "") if opts["site"]["language"].lower() == "city" else ""

    folder = stock_folder(lead["name"])
    if not (folder / "sources.json").exists():
        try:
            plan = _photo_plan(lead.get("category") or "", trade, lead["name"], settings)
            _lead_with_description(plan, lead, settings)
            (collect or find_stock_photos.collect)(plan, folder, settings, on_event)
        except find_stock_photos.StockPhotoError as error:
            raise AutopilotError(str(error))

    stack = STACKS[opts["site"]["stack"]]
    answers = {key: opts["site"][key] for key in SITE_FLAGS}
    answers["show_reviews"] = answers["show_reviews"] and bool(str(lead.get("rating") or "").strip())
    answers.update(
        {
            "stack": stack["name"],
            "stack_needs_a_build": stack["needs_a_build"],
            "stack_reason": "Chosen in the autopilot settings.",
        }
    )
    language = site_language(city, opts)
    if language:
        answers["language"] = language
    if opts["site"]["style"].strip():
        answers["style"] = opts["site"]["style"].strip()
    if city.get("name"):
        answers["city"] = city["name"]
    if city.get("country"):
        answers["country"] = city["country"]
    _write_json(path, answers)

    return {
        "place_id": lead["place_id"],
        "name": lead["name"],
        "category": lead.get("category", ""),
        "city": city.get("name", ""),
        "country": city.get("country", ""),
        "language": language,
        "answers_file": str(path),
        "stock_folder": str(folder),
        "stock_photos": _photo_count(folder),
        "project_folder": str(project_folder(lead["name"], settings)),
        "stack_needs_a_build": stack["needs_a_build"],
        "description": lead.get("description", ""),
        "review_notes": lead.get("review_notes", ""),
        "sender_name": settings["outreach"]["sender_name"],
        "sender_about": settings["outreach"]["sender_about"],
        "postal_address": settings["outreach"]["postal_address"],
        "portfolio_links": settings["outreach"]["portfolio_links"],
        "price": "{}{}".format(
            settings["outreach"]["pricing"]["currency"],
            pricing.quote(lead, trade, settings["outreach"]["pricing"]),
        ),
        "offer_includes": settings["outreach"]["offer_includes"],
    }


def description_query(text, settings):
    options = settings["stock_photos"]
    words = re.findall(r"[a-z]+", (text or "").lower())
    kept = [word for word in words if word not in options["description_skip_words"]]
    return " ".join(kept[: options["note_max_words"]])


def _lead_with_description(plan, lead, settings):
    query = description_query(lead.get("description"), settings)
    if not query:
        return
    for purpose in ("hero", "gallery", "interior"):
        if purpose in plan["queries"]:
            plan["queries"][purpose].insert(0, query)


def _photo_plan(category, trade, name, settings):
    plan = find_stock_photos.plan_for_category(category or trade, settings, name)
    if plan["matched"] or not trade:
        return plan
    words = category.replace("_", " ").replace(";", " ").split()
    note = " ".join(words) if len(words) <= settings["stock_photos"]["note_max_words"] else ""
    fallback = find_stock_photos.plan_for_category(trade, settings, name, note)
    return fallback if fallback["matched"] else plan


def drop_photos(place_id, files):
    lead, _ = build_brief.find_lead(place_id)
    folder = stock_folder(lead["name"]).resolve()
    removed = []
    for name in files:
        target = (folder / name).resolve()
        if folder not in target.parents or not target.is_file():
            raise AutopilotError("{} is not a photograph in {}.".format(name, folder))
        target.unlink()
        removed.append(str(target.relative_to(folder)).replace("\\", "/"))
    return removed


def _version_key(path, base):
    parts = path.relative_to(base).parts[0].split(".")
    return tuple(int(part) if part.isdigit() else 0 for part in parts)


def find_builder(opts):
    configured = (opts["builder"]["command"] or "").strip()
    if configured:
        expanded = Path(configured).expanduser()
        if expanded.is_file():
            return str(expanded)
        return shutil.which(configured)

    on_path = shutil.which("claude")
    if on_path:
        return on_path
    home = Path.home()
    for candidate in (home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude"):
        if candidate.is_file():
            return str(candidate)
    base = home / DESKTOP_COPIES
    copies = sorted(
        base.glob("*/*/claude.app/Contents/MacOS/claude"), key=lambda path: _version_key(path, base), reverse=True
    )
    return str(copies[0]) if copies else None


def venv_python():
    windows = CODE / "venv" / "Scripts" / "python.exe"
    return "venv/Scripts/python.exe" if windows.exists() else "venv/bin/python"


def _scratch_folder(root=None):
    return lead_store.data_dir(root or ROOT) / "autopilot"


def _command_text():
    text = (CODE / COMMAND_FILE).read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def render_prompt(place_id, settings, root=None):
    header = UNATTENDED.format(
        python=venv_python(),
        output=build_brief.output_dir(settings),
        scratch=_scratch_folder(root),
    )
    body = _command_text().replace("$ARGUMENTS", place_id).replace("$1", place_id)
    return "{}\n{}\n".format(header, body)


def _edit_rule(folder):
    resolved = Path(folder).resolve()
    drive = resolved.drive.rstrip(":").lower()
    path = resolved.as_posix()[len(resolved.drive):]
    return "Edit(//{}/**)".format("{}{}".format(drive, path).lstrip("/"))


def builder_command(executable, opts, settings, needs_a_build=False, root=None):
    output = build_brief.output_dir(settings)
    allowed = [
        "Read",
        "Glob",
        "Grep",
        "Bash({} scripts/*)".format(venv_python()),
        _edit_rule(output),
        _edit_rule(_scratch_folder(root)),
    ]
    if needs_a_build:
        allowed += ["Bash(npm *)", "Bash(npx *)"]
    command = [executable, "-p", "--permission-mode", "dontAsk", "--allowedTools"] + allowed
    command += ["--add-dir", str(Path(output).resolve()), "--output-format", "stream-json", "--verbose"]
    model = (opts["builder"]["model"] or "").strip()
    if model:
        command += ["--model", model]
    effort = (opts["builder"]["effort"] or "").strip()
    if effort:
        command += ["--effort", effort]
    return command


def _parse_reply(text):
    text = (text or "").strip()
    try:
        whole = json.loads(text)
    except ValueError:
        whole = None
    if isinstance(whole, dict):
        return whole
    final = None
    for line in text.splitlines():
        if line.startswith(SKIPPED_EVENT):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and (event.get("type") == "result" or "is_error" in event):
            final = event
    return final or {"is_error": True, "result": text[-500:] or "Claude Code printed nothing."}


def _reply_facts(reply):
    return {
        "models": sorted((reply.get("modelUsage") or {}).keys()),
        "session_id": reply.get("session_id") or "",
        "turns": reply.get("num_turns") or 0,
        "minutes": round((reply.get("duration_ms") or 0) / 60000, 1),
    }


def stream_path(log_path):
    return Path(log_path).with_suffix(".jsonl")


def _step_text(block):
    name = block.get("name", "")
    given = block.get("input") or {}
    if given.get("description"):
        return str(given["description"])
    target = Path(str(given.get("file_path") or given.get("path") or "")).name
    if name in ("Write", "Edit") and target:
        return "Writing {}".format(target)
    if name == "Read" and target:
        return "Reading {}".format(target)
    if name == "Bash":
        return "Running {}".format(str(given.get("command", ""))[:80])
    return name


def activity(log_path):
    found = {"model": "", "now": "", "steps": 0, "limits": None}
    path = stream_path(log_path)
    if not path.exists():
        return found
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(SKIPPED_EVENT):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind, subtype = event.get("type"), event.get("subtype")
            if kind == "system" and subtype == "init":
                found["model"] = event.get("model") or found["model"]
            elif kind == "system" and subtype == "task_summary" and event.get("detail"):
                found["now"] = str(event["detail"])
            elif kind == "rate_limit_event":
                found["limits"] = event.get("rate_limit_info")
            elif kind == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        found["steps"] += 1
                        found["now"] = _step_text(block)
    return found


PLAN_WINDOWS = [("five_hour", "five-hour"), ("seven_day", "weekly")]


def plan_usage(limits):
    windows = (limits or {}).get("unifiedWindows") or {}
    parts = []
    for key, label in PLAN_WINDOWS:
        window = windows.get(key) or {}
        if window.get("utilization") is None:
            continue
        text = "{}% of the {} limit".format(round(window["utilization"] * 100), label)
        if key == "five_hour" and window.get("resetsAt"):
            text += ", which resets at {}".format(datetime.fromtimestamp(window["resetsAt"]).strftime("%H:%M"))
        parts.append(text)
    return "Claude plan used: {}.".format("; ".join(parts)) if parts else ""


def _not_logged_in(reply):
    words = str(reply.get("result") or "").lower()
    return bool(reply.get("is_error")) and ("not logged in" in words or "/login" in words or "invalid api key" in words)


def _end(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def prompt_path(log_path):
    return Path(log_path).with_suffix(".prompt.txt")


def run_builder(command, log_path, timeout_seconds, stop_event=None, cwd=None, prompt=""):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    reply_path = stream_path(log_path)
    prompt_file = prompt_path(log_path)
    prompt_file.write_text(prompt, encoding="utf-8")
    started = time.monotonic()
    ending = ""

    with open(reply_path, "w", encoding="utf-8") as reply_file, open(log_path, "w", encoding="utf-8") as log, open(
        prompt_file, "rb"
    ) as prompt_input:
        try:
            process = subprocess.Popen(
                command, cwd=str(cwd or CODE), stdout=reply_file, stderr=log, stdin=prompt_input
            )
        except OSError as error:
            return {
                "ok": False,
                "result": "Claude Code could not be started: {}".format(error),
                "not_logged_in": False,
                "timed_out": False,
                "stopped": False,
            }
        while process.poll() is None:
            if stop_event is not None and stop_event.is_set():
                ending = "stopped"
            elif time.monotonic() - started > timeout_seconds:
                ending = "timed_out"
            if ending:
                _end(process)
                break
            time.sleep(POLL_SECONDS)

    reply = _parse_reply(reply_path.read_text(encoding="utf-8", errors="replace"))
    outcome = {
        "ok": not ending and process.returncode == 0 and not reply.get("is_error"),
        "result": str(reply.get("result") or ""),
        "not_logged_in": _not_logged_in(reply),
        "timed_out": ending == "timed_out",
        "stopped": ending == "stopped",
    }
    outcome.update(_reply_facts(reply))
    return outcome


def check_builder(opts, settings=None):
    executable = find_builder(opts)
    if not executable:
        return {
            "state": "missing",
            "path": "",
            "message": "No Claude Code was found on this computer.",
        }
    command = [executable, "-p", CHECK_PROMPT, "--permission-mode", "dontAsk", "--output-format", "json"]
    command += ["--no-session-persistence"]
    if (opts["builder"]["model"] or "").strip():
        command += ["--model", opts["builder"]["model"].strip()]
    seconds = opts["builder"]["check_timeout_seconds"]
    try:
        finished = subprocess.run(
            command, cwd=str(CODE), capture_output=True, text=True, timeout=seconds, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        return {"state": "error", "path": executable, "message": "Claude Code did not answer within {} seconds.".format(seconds)}
    except OSError as error:
        return {"state": "error", "path": executable, "message": "Claude Code could not be started: {}".format(error)}

    reply = _parse_reply(finished.stdout)
    if _not_logged_in(reply):
        return {
            "state": "logged_out",
            "path": executable,
            "message": "Claude Code was found but is not logged in.",
        }
    if reply.get("is_error") or finished.returncode:
        detail = str(reply.get("result") or finished.stderr or "no reply").strip()[-300:]
        return {"state": "error", "path": executable, "message": "Claude Code answered with an error: {}".format(detail)}
    models = _reply_facts(reply)["models"]
    answered = " with {}".format(", ".join(models)) if models else ""
    return {
        "state": "ready",
        "path": executable,
        "models": models,
        "message": "Claude Code is logged in and answering{}.".format(answered),
    }


def messages(folder):
    path = Path(folder) / MESSAGES_FILE
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            found.append({"title": line[3:].strip(), "lines": []})
        elif found:
            found[-1]["lines"].append(line)
    return [{"title": item["title"], "text": "\n".join(item["lines"]).strip()} for item in found]


def verify_project(folder):
    folder = Path(folder)
    if not (folder / "brief.md").exists():
        return ["brief.md was never written."]
    _, problems = check_site.check(folder)
    written = {item["title"].lower() for item in messages(folder) if item["text"]}
    missing = [heading for heading in MESSAGE_HEADINGS if heading.lower() not in written]
    if missing:
        problems.append("{} has no {} message.".format(MESSAGES_FILE, " or ".join(missing)))
    return problems


def runs_folder(root=None):
    return _scratch_folder(root) / "runs"


def _now():
    return datetime.now().isoformat(timespec="seconds")


class Run:
    def __init__(self, state, root=None):
        self.state = state
        self.path = runs_folder(root) / "{}.json".format(state["id"])
        self.lock = threading.RLock()

    def save(self):
        with self.lock:
            _write_json(self.path, self.state)

    def update(self, **fields):
        with self.lock:
            self.state.update(fields)
            self.save()
            return self.state

    def change(self, candidate, **fields):
        with self.lock:
            candidate.update(fields)
            self.save()

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))


def new_run(city, trade, root=None):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = stamp
    number = 2
    while (runs_folder(root) / "{}.json".format(run_id)).exists():
        run_id = "{}-{}".format(stamp, number)
        number += 1
    run = Run(
        {
            "id": run_id,
            "started": _now(),
            "finished": "",
            "city": city,
            "trade": trade,
            "query": "{} {}".format(trade, city["name"]),
            "state": "searching",
            "message": "",
            "builder": "",
            "builder_problem": "",
            "leads_file": "",
            "found": 0,
            "candidates": [],
        },
        root,
    )
    run.save()
    return run


CONTACT_COLUMNS = ["phone", "email", "instagram", "facebook", "website", "google_maps_link", "contact_search"]


def _candidate(row, city=None):
    city = city or {}
    return {
        "place_id": row["place_id"],
        "name": row.get("name", ""),
        "address": row.get("address", ""),
        "city": city.get("name", ""),
        "country_code": city.get("code", ""),
        **{column: row.get(column, "") for column in CONTACT_COLUMNS},
        "score": row.get("score", ""),
        "state": "waiting",
        "folder": "",
        "photos": 0,
        "problems": [],
        "summary": "",
        "log": "",
        "command": "/autopilot {}".format(row["place_id"]),
        "sent": [],
    }


def _build_one(candidate, run, settings, opts, stop_event, build):
    log = runs_folder() / run.state["id"] / "{}.log".format(lead_store.to_slug(candidate["place_id"], "lead"))
    run.change(candidate, state="building", log=str(log), started=_now())
    build_brief.output_dir(settings).mkdir(parents=True, exist_ok=True)

    prompt = render_prompt(candidate["place_id"], settings)
    needs_a_build = STACKS[opts["site"]["stack"]]["needs_a_build"]
    command = builder_command(run.state["builder"], opts, settings, needs_a_build)
    outcome = build(command, log, opts["builder"]["timeout_minutes"] * 60, stop_event, prompt=prompt)

    found = activity(log)
    facts = {
        "models": outcome.get("models") or ([found["model"]] if found["model"] else []),
        "session_id": outcome.get("session_id") or "",
        "turns": outcome.get("turns") or 0,
        "minutes": outcome.get("minutes") or 0,
        "steps": found["steps"],
        "limits": found["limits"],
        "finished": _now(),
    }
    if outcome["not_logged_in"]:
        run.update(builder_problem="Claude Code is not logged in, so this run stopped building.")
        run.change(candidate, state="paste", **facts)
    elif outcome["stopped"]:
        run.change(candidate, state="stopped", **facts)
    else:
        problems = verify_project(candidate["folder"])
        if outcome["timed_out"]:
            minutes = opts["builder"]["timeout_minutes"]
            problems.insert(0, "Claude Code ran past the {} minute limit and was stopped.".format(minutes))
        elif not outcome["ok"]:
            problems.insert(0, "Claude Code ended with an error: {}".format(outcome["result"][:300]))
        run.change(
            candidate,
            state="attention" if problems else "done",
            problems=problems,
            summary=outcome["result"][:800],
            **facts
        )


def _work_on(candidate, run, settings, opts, stop_event, collect, build, building, say):
    if stop_event.is_set():
        run.change(candidate, state="stopped")
        return
    run.change(candidate, state="photos")
    say("{}: downloading photographs".format(candidate["name"]))
    try:
        prepared = prepare(candidate["place_id"], run.state["city"], run.state["trade"], settings, collect)
    except (AutopilotError, build_brief.BriefError) as error:
        run.change(candidate, state="failed", problems=[str(error)])
        say("{}: failed".format(candidate["name"]))
        return
    run.change(candidate, folder=prepared["project_folder"], photos=prepared["stock_photos"])

    if stop_event.is_set():
        run.change(candidate, state="stopped")
    elif not building or not run.state["builder"] or run.state["builder_problem"]:
        run.change(candidate, state="paste")
    else:
        say("{}: building".format(candidate["name"]))
        _build_one(candidate, run, settings, opts, stop_event, build)
    say("{}: {}".format(candidate["name"], candidate["state"]))


def _guarded_work(candidate, run, *arguments):
    try:
        _work_on(candidate, run, *arguments)
    except Exception as error:
        run.change(candidate, state="failed", problems=["Unexpected failure: {}".format(error)])


def _search_or_stop(call, stop_event):
    outcome = {}

    def work():
        try:
            outcome["result"] = call()
        except lead_search.SearchError as error:
            outcome["error"] = str(error)
        except Exception as error:
            outcome["error"] = "Unexpected failure while searching: {}".format(error)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        if stop_event.wait(STOP_POLL_SECONDS):
            return None
    return outcome


class WindowsAwake:
    def __init__(self):
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

    def terminate(self):
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def _keep_awake(opts):
    if opts.get("keep_awake") and os.name == "nt":
        return WindowsAwake()
    tool = shutil.which("caffeinate") if opts.get("keep_awake") else None
    if not tool:
        return None
    try:
        return subprocess.Popen(
            [tool, "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


def execute(run, settings, stop_event, search=None, collect=None, build=None, building=True, report=None):
    opts = options(settings)
    awake = _keep_awake(opts)
    try:
        return _execute(
            run, settings, opts, stop_event, search, collect, build or run_builder, building, report or (lambda text: None)
        )
    finally:
        if awake is not None:
            awake.terminate()


def _execute(run, settings, opts, stop_event, search, collect, build, building, say):
    state = run.state
    city = state["city"]
    run.update(state="searching", message="Searching for {} in {}.".format(state["trade"], city["name"]))
    say(state["message"])

    def call():
        return (search or lead_search.run_search)(
            state["query"],
            limit=opts["search_limit"],
            audit=not opts["only_without_website"],
            place={
                "term": state["trade"],
                "name": city["name"],
                "lookup": city.get("area") or city["name"],
                "country_code": city.get("code", ""),
            },
        )

    found = _search_or_stop(call, stop_event)
    if found is None:
        message = (
            "Stopped during the search. A search already sent to the server still finishes on its own, "
            "and its businesses appear on the Leads tab."
        )
        say(message)
        return run.update(state="stopped", message=message, finished=_now())
    if "error" in found:
        say(found["error"])
        return run.update(state="failed", message=found["error"], finished=_now())

    result = found["result"]
    rows = result.get("rows") or []
    still_a_fit = contact_check(result["path"], opts, settings, city) if result.get("path") else None
    chosen = choose_candidates(rows, opts, settings, still_a_fit=still_a_fit)
    builder =(find_builder(opts) or "") if building else ""
    run.update(
        leads_file=result["path"].name if result.get("path") else "",
        found=len(rows),
        builder=builder,
        candidates=[_candidate(row, city) for row in chosen],
    )
    if not chosen:
        message = (
            "Found {} businesses for {}, and none of them fits the settings: not contacted yet, not built "
            "before{}{}.".format(
                len(rows),
                state["query"],
                ", without a website" if opts["only_without_website"] else "",
                ", with a phone number" if opts["require_phone"] else "",
            )
        )
        say(message)
        return run.update(state="done", message=message, finished=_now())

    workers = max(1, min(opts["builder"]["parallel"], len(chosen)))
    run.update(
        state="building",
        message="Picked {} of {} businesses, building {} at a time.".format(len(chosen), len(rows), workers),
    )
    say(state["message"])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = [
            pool.submit(_guarded_work, candidate, run, settings, opts, stop_event, collect, build, building, say)
            for candidate in state["candidates"]
        ]
        for job in jobs:
            job.result()

    for candidate in state["candidates"]:
        if candidate["state"] in ("waiting", "photos", "building"):
            run.change(candidate, state="stopped")
    stopped = stop_event.is_set()
    return run.update(
        state="stopped" if stopped else "done",
        message=_outcome(state["candidates"], len(rows)),
        finished=_now(),
    )


OUTCOME_WORDS = [
    ("done", "built"),
    ("attention", "with problems to look at"),
    ("paste", "waiting for the command to be pasted"),
    ("failed", "could not be prepared"),
    ("stopped", "stopped"),
]


def _outcome(candidates, found):
    counts = [
        "{} {}".format(sum(1 for item in candidates if item["state"] == state), words)
        for state, words in OUTCOME_WORDS
        if any(item["state"] == state for item in candidates)
    ]
    return "Picked {} of {} businesses: {}.".format(len(candidates), found, ", ".join(counts))


class Runner:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.run_id = ""
        self.run = None

    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, city_text="", random_pick=False, trade_text="", settings=None, **hooks):
        with self.lock:
            if self.busy():
                raise AutopilotError("A run is already going. Stop it, or wait for it to finish.")
            settings = settings or lead_search.load_settings()
            opts = options(settings)
            city = random_city(opts) if random_pick else resolve_city(city_text, opts)
            run = new_run(city, pick_trade(trade_text, opts))
            self.stop_event = threading.Event()
            self.run_id = run.state["id"]
            self.run = run
            self.thread = threading.Thread(target=self._guarded, args=(run, settings, hooks), daemon=True)
            self.thread.start()
            return run.state

    def _guarded(self, run, settings, hooks):
        try:
            execute(run, settings, self.stop_event, **hooks)
        except Exception as error:
            run.update(state="failed", message="Unexpected failure: {}".format(error), finished=_now())

    def stop(self):
        if not self.busy():
            return False
        self.stop_event.set()
        return True

    def wait(self, seconds=None):
        if self.thread is not None:
            self.thread.join(seconds)

    def live(self, run_id):
        if self.busy() and self.run_id == run_id:
            return self.run
        return None


def load_run(run_id, runner=None, root=None):
    if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        return None
    live = runner.live(run_id) if runner is not None else None
    if live is not None:
        return live
    run = Run({"id": run_id}, root)
    if not run.path.exists():
        return None
    run.state = _read_json(run.path)
    if run.state.get("state") in ACTIVE_STATES:
        for candidate in run.state.get("candidates", []):
            if candidate["state"] in ("waiting", "photos", "building"):
                candidate["state"] = "stopped"
        run.update(state="interrupted", message="The page was closed or restarted while this run was going.")
    return run


def list_runs(runner=None, root=None, limit=20):
    folder = runs_folder(root)
    if not folder.exists():
        return []
    found = []
    for path in sorted(folder.glob("*.json"), reverse=True)[:limit]:
        run = load_run(path.stem, runner, root)
        if run:
            found.append(
                {key: run.state.get(key) for key in ("id", "started", "query", "state", "found")}
                | {"sites": len(run.state.get("candidates", []))}
            )
    return found


def _site_url(page, settings):
    base = build_brief.output_dir(settings).resolve()
    relative = Path(page).resolve().relative_to(base).as_posix()
    return "/sites/" + quote(relative)


def _phone_parts(phone):
    return re.split(r"[;,/]", phone or "")[0].strip()


def phone_digits(phone, country_code, settings):
    options = settings["contact_links"]
    first = _phone_parts(phone)
    digits = re.sub(r"\D", "", first)
    if not digits:
        return ""
    if first.startswith("+"):
        return digits
    if first.startswith("00"):
        return digits[2:]
    calling = options["calling_codes"].get(country_code or "")
    if not calling:
        return ""
    if calling == "1" and len(digits) == 11 and digits.startswith("1"):
        return digits
    national = digits if country_code in options["keep_leading_zero"] else digits.lstrip("0")
    return calling + national


def _profile(value, site):
    value = (value or "").strip()
    if not value:
        return "", ""
    if value.lower().startswith(("http://", "https://")) or "{}.com".format(site) in value.lower():
        url = value if value.lower().startswith("http") else "https://" + value
        handle = urlparse(url).path.strip("/").split("/")[0]
        return url, handle
    handle = value.lstrip("@").strip("/")
    return "https://www.{}.com/{}/".format(site, quote(handle)), handle


def _email_parts(text):
    lines = (text or "").splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def _web_address(value):
    value = (value or "").strip()
    if not value:
        return ""
    url = value if re.match(r"^[a-z][a-z0-9+.-]*:", value, re.IGNORECASE) else "https://" + value
    parsed = urlparse(url)
    return url if parsed.scheme in ("http", "https") and "." in parsed.netloc else ""


def _search_link(name, city, words):
    query = '"{}" {} {}'.format(name, city, words).replace("  ", " ")
    return "https://www.google.com/search?q=" + quote_plus(query)


def contact_links(candidate, found, settings):
    texts = {item["title"].lower(): item["text"] for item in found}
    links = []
    phone = _phone_parts(candidate.get("phone"))
    digits = phone_digits(phone, candidate.get("country_code"), settings)
    if phone:
        dial = "+" + digits if digits else re.sub(r"[^\d+]", "", phone)
        links.append(("call", "Call {}".format(phone), "tel:" + dial))
    if digits:
        chat = texts.get("viber or whatsapp", "")
        links.append(("message", "WhatsApp", "https://wa.me/{}{}".format(digits, "?text=" + quote(chat, safe="") if chat else "")))
        links.append(("message", "Viber", "viber://chat?number=%2B{}".format(digits)))

    email = re.split(r"[;,]", candidate.get("email") or "")[0].strip()
    if email:
        subject, body = _email_parts(texts.get("email", ""))
        query = "subject={}&body={}".format(quote(subject, safe=""), quote(body, safe="")) if subject or body else ""
        links.append(("email", "Email {}".format(email), "mailto:{}{}".format(email, "?" + query if query else "")))

    instagram, handle = _profile(candidate.get("instagram"), "instagram")
    if instagram:
        links.append(("social", "Instagram", instagram))
        if handle:
            links.append(("message", "Instagram DM", "https://ig.me/m/{}".format(quote(handle))))
    facebook, _ = _profile(candidate.get("facebook"), "facebook")
    if facebook:
        links.append(("social", "Facebook", facebook))
    website = _web_address(candidate.get("website"))
    if website:
        links.append(("web", "Website", website))
    if candidate.get("google_maps_link"):
        links.append(("web", "Google Maps", candidate["google_maps_link"]))

    name, city = candidate.get("name", ""), candidate.get("city", "")
    if not email:
        links.append(("search", "Find their email", _search_link(name, city, "email")))
    if not instagram:
        links.append(("search", "Find their Instagram", _search_link(name, city, "instagram")))
    if not facebook:
        links.append(("search", "Find their Facebook", _search_link(name, city, "facebook")))
    if candidate.get("contact_search"):
        links.append(("search", "Owner search", candidate["contact_search"]))
    return [{"kind": kind, "label": label, "href": href} for kind, label, href in links]


def _refresh_contacts(candidate):
    try:
        row, _ = build_brief.find_lead(candidate["place_id"])
    except build_brief.BriefError:
        return
    for column in CONTACT_COLUMNS:
        if (row.get(column) or "").strip():
            candidate[column] = row[column]


def _resume_command(session_id, opts):
    if not session_id:
        return ""
    on_path = shutil.which("claude") or (Path.home() / ".local" / "bin" / "claude").is_file()
    program = "claude" if on_path else '"{}"'.format(find_builder(opts) or "claude")
    separator = ";" if os.name == "nt" else "&&"
    return 'cd "{}" {} {} --resume {}'.format(CODE, separator, program, session_id)


def view(run, settings=None):
    settings = settings or lead_search.load_settings()
    opts = options(settings)
    state = run.snapshot()
    latest = (None, "")
    for candidate in state.get("candidates", []):
        folder = Path(candidate["folder"]) if candidate["folder"] else None
        found = messages(folder) if folder else []
        page = check_site.entry_page(folder) if folder else None
        candidate["messages"] = found
        candidate["site_url"] = _site_url(page, settings) if page else ""
        if candidate["state"] in ("paste", "stopped") and found and page:
            candidate["problems"] = verify_project(folder)
            candidate["state"] = "attention" if candidate["problems"] else "done"
        if candidate["state"] == "building" and candidate.get("log"):
            candidate["activity"] = activity(candidate["log"])
            if candidate["activity"]["limits"]:
                latest = (candidate["activity"]["limits"], "9999")
        elif candidate.get("limits") and candidate.get("finished", "") > latest[1]:
            latest = (candidate["limits"], candidate["finished"])
        _refresh_contacts(candidate)
        candidate["contacts"] = contact_links(candidate, found, settings)
        candidate["resume"] = _resume_command(candidate.get("session_id"), opts)
    state["plan_usage"] = plan_usage(latest[0])
    return state


def mark_sent(run, place_id, channel, settings=None):
    settings = settings or lead_search.load_settings()
    candidate = next((item for item in run.state.get("candidates", []) if item["place_id"] == place_id), None)
    if candidate is None:
        raise AutopilotError("That business is not part of this run.")
    try:
        row = outreach_log.record_send(ROOT, place_id, candidate["name"], channel, settings)
    except outreach_log.OutreachError as error:
        raise AutopilotError(str(error))
    run.change(candidate, sent=candidate.get("sent", []) + [{"channel": channel, "on": row["sent_at"]}])
    return row


def _print_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Runs a city start to finish with the saved autopilot settings.")
    commands = parser.add_subparsers(dest="action", required=True)

    commands.add_parser("settings", help="Print the autopilot settings in force")

    prepare_command = commands.add_parser("prepare", help="Download the stock photographs and write the answers")
    prepare_command.add_argument("place_id", help="The place_id, or the business name")
    prepare_command.add_argument("--city", help="The city the lead is in, when the answers do not say yet")
    prepare_command.add_argument("--trade", default="", help="Trade to search photographs for when the lead has none")

    drop_command = commands.add_parser("drop-photo", help="Remove stock photographs that do not belong")
    drop_command.add_argument("place_id", help="The place_id, or the business name")
    drop_command.add_argument("files", nargs="+", help="Paths as sources.json writes them, such as hero/hero_1.jpg")

    run_command = commands.add_parser("run", help="Search a city and build the best candidates")
    where = run_command.add_mutually_exclusive_group(required=True)
    where.add_argument("--city", help="The city to search")
    where.add_argument("--random", action="store_true", help="Pick a random city from autopilot.cities")
    run_command.add_argument("--trade", default="", help="The trade, or a random one from the settings")
    run_command.add_argument(
        "--no-build", action="store_true", help="Stop after the photographs and print the command for each lead"
    )

    commands.add_parser("check-builder", help="Ask Claude Code for one word to see whether it can build")
    arguments = parser.parse_args()

    try:
        settings = lead_search.load_settings()
        opts = options(settings)
        if arguments.action == "settings":
            _print_json({key: value for key, value in opts.items() if key != "cities"})
        elif arguments.action == "prepare":
            city = resolve_city(arguments.city, opts) if arguments.city else None
            _print_json(prepare(arguments.place_id, city, arguments.trade, settings))
        elif arguments.action == "drop-photo":
            _print_json({"removed": drop_photos(arguments.place_id, arguments.files)})
        elif arguments.action == "check-builder":
            _print_json(check_builder(opts, settings))
        else:
            city = random_city(opts) if arguments.random else resolve_city(arguments.city, opts)
            run = new_run(city, pick_trade(arguments.trade, opts))
            print("\n{} ({})\n".format(run.state["query"], city.get("country") or "country not in the list"))
            execute(run, settings, threading.Event(), building=not arguments.no_build, report=lambda text: print("  " + text))
            for candidate in run.state["candidates"]:
                print("\n{}: {}".format(candidate["name"], candidate["state"]))
                if candidate["folder"]:
                    print("  folder: {}".format(candidate["folder"]))
                if candidate["state"] == "paste":
                    print("  paste into Claude Code: {}".format(candidate["command"]))
                for problem in candidate["problems"]:
                    print("  - {}".format(problem))
            print()
    except (AutopilotError, build_brief.BriefError, lead_search.SearchError) as error:
        print("\nERROR: {}\n".format(error))
        raise SystemExit(1)


if __name__ == "__main__":
    main()

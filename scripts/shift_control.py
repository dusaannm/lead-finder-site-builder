import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autopilot
import lead_search
import night_shift

ROOT = lead_search.ROOT
RECORD_FILE = "shift.json"
LOG_FILE = "night.log"
LIVE_RUNS = 5
SHIFT_START = "Shift starts:"
SHIFT_END = "Shift ends:"
WEEKLY_END = "weekly Claude limit"
STOPPED_BY_HAND = "Stop file found"
BUILT_SO_FAR = re.compile(r"built this search, (\d+) tonight")
TIME_STAMP = re.compile(r"^\d\d:\d\d:\d\d ")


class ShiftError(Exception):
    pass


def _record_path(root=None):
    return night_shift.stop_file(root).parent / RECORD_FILE


def _load_record(root=None):
    path = _record_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def is_alive(pid):
    if os.name == "nt":
        found = subprocess.run(["tasklist", "/FI", "PID eq {}".format(pid), "/NH"], capture_output=True, text=True)
        return str(pid) in found.stdout and "python" in found.stdout.lower()
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def latest_lines(root=None):
    path = night_shift.stop_file(root).parent / LOG_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    starts = [number for number, line in enumerate(lines) if SHIFT_START in line]
    return lines[starts[-1]:] if starts else []


def _log_says_it_ended(record, lines, root=None):
    if not lines or SHIFT_END not in lines[-1] or not record.get("started"):
        return False
    written = (night_shift.stop_file(root).parent / LOG_FILE).stat().st_mtime
    return written >= datetime.fromisoformat(record["started"]).timestamp()


def built_so_far(lines):
    counts = [int(match.group(1)) for match in map(BUILT_SO_FAR.search, lines) if match]
    return counts[-1] if counts else 0


def how_it_ended(lines):
    if not any(SHIFT_END in line for line in lines):
        return "crashed" if lines else ""
    if any(WEEKLY_END in line for line in lines):
        return "weekly_limit"
    return "by_hand" if any(STOPPED_BY_HAND in line for line in lines) else "finished"


def plan_levels(root=None):
    folder = autopilot.runs_folder(root)
    paths = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if folder.exists() else []
    for path in paths[:LIVE_RUNS]:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for candidate in reversed(state.get("candidates", [])):
            windows = (candidate.get("limits") or {}).get("unifiedWindows")
            if windows:
                return {name: (windows.get(name) or {}).get("utilization") for name in ("five_hour", "seven_day")}
    return {}


def _city_counts(settings):
    opts = autopilot.options(settings)
    return {region: len(autopilot.cities_in(region, opts)) for region in autopilot.REGIONS}


def _chosen_region(record, settings):
    chosen = record.get("region") or settings["autopilot"]["cities_from"]
    return chosen if chosen in autopilot.REGIONS else "us"


def status(settings=None, root=None):
    settings = settings or lead_search.load_settings()
    record = _load_record(root)
    lines = latest_lines(root) if record else []
    running = bool(record.get("pid")) and is_alive(record["pid"]) and not _log_says_it_ended(record, lines, root)
    return {
        "running": running,
        "stopping": running and night_shift.stop_file(root).exists(),
        "region": _chosen_region(record, settings),
        "regions": list(autopilot.REGIONS.items()),
        "cities": _city_counts(settings),
        "started": record.get("started", ""),
        "built": built_so_far(lines),
        "ended": "" if running else how_it_ended(lines),
        "now": TIME_STAMP.sub("", lines[-1]) if lines and SHIFT_END not in lines[-1] else "",
        "log": lines[-settings["dashboard"]["shift_log_lines"]:],
        "levels": plan_levels(root),
        "stop_at_weekly": settings["night"]["stop_at_weekly"],
        "pause_at_five_hour": settings["night"]["pause_at_five_hour"],
    }


def start(region, settings=None, root=None):
    if region not in autopilot.REGIONS:
        raise ShiftError("Choose USA, Europe or both.")
    if status(settings, root)["running"]:
        raise ShiftError("The autopilot is already on.")
    night_shift.stop_file(root).unlink(missing_ok=True)
    script = Path(__file__).resolve().parent / "night_shift.py"
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(script), "--sites", "0", "--hours", "0", "--region", region],
        cwd=str(root or ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    path = _record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"pid": process.pid, "region": region, "started": datetime.now().isoformat(timespec="seconds")}
    path.write_text(json.dumps(record), encoding="utf-8")
    return record


def stop(root=None):
    if not status(root=root)["running"]:
        return False
    night_shift.stop_file(root).touch()
    return True

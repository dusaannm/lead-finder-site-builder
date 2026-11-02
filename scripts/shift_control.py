import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lead_search
import night_shift

ROOT = lead_search.ROOT
RECORD_FILE = "shift.json"
LOG_FILE = "night.log"
SHIFT_START = "Shift starts:"
SHIFT_END = "Shift ends:"
BUILT_SO_FAR = re.compile(r"built this search, (\d+) tonight")


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
        return str(pid) in found.stdout
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


def built_so_far(lines):
    counts = [int(match.group(1)) for match in map(BUILT_SO_FAR.search, lines) if match]
    return counts[-1] if counts else 0


def status(settings=None, root=None):
    settings = settings or lead_search.load_settings()
    record = _load_record(root)
    running = bool(record.get("pid")) and is_alive(record["pid"])
    lines = latest_lines(root) if record else []
    return {
        "running": running,
        "stopping": running and night_shift.stop_file(root).exists(),
        "sites": record.get("sites", 0),
        "hours": record.get("hours", 0),
        "started": record.get("started", ""),
        "built": built_so_far(lines),
        "ended": any(SHIFT_END in line for line in lines),
        "log": lines[-settings["dashboard"]["shift_log_lines"]:],
        "default_sites": settings["night"]["max_sites"],
        "default_hours": settings["night"]["hours"],
    }


def _whole(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ShiftError("{} has to be a number.".format(label))
    if number <= 0:
        raise ShiftError("{} has to be above zero.".format(label))
    return number


def start(sites, hours, settings=None, root=None):
    if status(settings, root)["running"]:
        raise ShiftError("A batch is already going.")
    script = Path(__file__).resolve().parent / "night_shift.py"
    wanted = int(_whole(sites, "The number of sites"))
    limit = _whole(hours, "The number of hours")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(script), "--sites", str(wanted), "--hours", str(limit)],
        cwd=str(root or ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    path = _record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "pid": process.pid,
        "sites": wanted,
        "hours": limit,
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    return record


def stop(root=None):
    if not status(root=root)["running"]:
        return False
    night_shift.stop_file(root).touch()
    return True

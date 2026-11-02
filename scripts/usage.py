import json
from datetime import datetime
from pathlib import Path


def _usage_path(root, name):
    return Path(root) / "data" / "{}.json".format(name)


def _current_month():
    return datetime.now().strftime("%Y-%m")


def read(root, name="usage"):
    path = _usage_path(root, name)
    month = _current_month()
    if not path.exists():
        return {"month": month, "calls": 0}
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("month") != month:
        return {"month": month, "calls": 0}
    return {"month": month, "calls": int(record.get("calls", 0))}


def remaining(root, monthly_limit, name="usage"):
    return max(0, monthly_limit - read(root, name)["calls"])


def record_call(root, name="usage"):
    record = read(root, name)
    record["calls"] += 1
    path = _usage_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record["calls"]

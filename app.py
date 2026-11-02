import sys
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

import autopilot
import build_brief
import dashboard
import lead_search
import lead_store
import ready_list
import shift_control
import outreach_log

app = Flask(__name__)
RUNNER = autopilot.Runner()


def _safe_file(name):
    if not name:
        return None
    candidate = (lead_store.data_dir(ROOT) / name).resolve()
    if candidate.parent != lead_store.data_dir(ROOT).resolve():
        return None
    if not candidate.name.startswith("leads_") or candidate.suffix != ".csv":
        return None
    if not candidate.exists():
        return None
    return candidate


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/usage")
def usage():
    settings = lead_search.load_settings()
    summary = lead_search.usage_summary(settings)
    summary["has_google_key"] = bool(lead_search.google_key())
    summary["gosom"] = lead_search.gosom_enabled()
    summary["has_builder"] = bool(autopilot.find_builder(autopilot.options(settings)))
    summary["has_publishing"] = autopilot.publish_site.is_set_up(settings)
    return jsonify(summary)


@app.get("/api/overview")
def overview():
    return jsonify(dict(dashboard.overview(dashboard.gather(runner=RUNNER), RUNNER), autopilot=shift_control.status()))


@app.get("/api/history")
def history():
    return jsonify({"events": dashboard.history(dashboard.gather(runner=RUNNER))})


@app.get("/api/sites")
def sites():
    settings = lead_search.load_settings()
    return jsonify({
        "sites": dashboard.gather(settings, RUNNER)["sites"],
        "channels": settings["outreach"]["channels"],
    })


@app.post("/api/sites/sent")
def site_sent():
    payload = request.get_json(silent=True) or {}
    try:
        row = dashboard.record_send(payload.get("place_id") or "", payload.get("channel") or "")
    except outreach_log.OutreachError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"sent_at": row["sent_at"], "follow_up_due": row["follow_up_due"]})


@app.get("/api/settings")
def page_settings():
    settings = lead_search.load_settings()
    return jsonify(
        {
            "default_limit": settings["search"]["default_limit"],
            "poor_website_below": settings["audit"]["poor_website_below"],
        }
    )


@app.get("/api/files")
def files():
    return jsonify({"files": lead_store.list_files(ROOT)})


@app.get("/api/leads")
def leads():
    path = _safe_file(request.args.get("file"))
    if not path:
        return jsonify({"error": "Unknown file."}), 404
    return jsonify({"file": path.name, "rows": lead_store.load_rows(path)})


@app.post("/api/search")
def search():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    limit = payload.get("limit")

    if not query:
        return jsonify({"error": "Enter a search first."}), 400

    if limit in (None, ""):
        limit = None
    else:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return jsonify({"error": "The limit has to be a whole number."}), 400
        if limit < 1:
            return jsonify({"error": "The limit has to be at least 1."}), 400

    try:
        result = lead_search.run_search(query, limit=limit)
    except lead_search.SearchError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        return jsonify({"error": "Unexpected failure: {}".format(error)}), 500

    if not result["leads"]:
        return jsonify({"error": "No results. Try a different term or place."}), 404

    return jsonify(
        {
            "file": result["path"].name,
            "source": result["source"],
            "found": len(result["leads"]),
            "without_website": result["without_website"],
            "merged_with": result.get("previous"),
            "calls": result.get("calls", 0),
        }
    )


@app.post("/api/status")
def status():
    payload = request.get_json(silent=True) or {}
    path = _safe_file(payload.get("file"))
    place_id = payload.get("place_id")
    new_status = payload.get("status", "")

    if not path or not place_id:
        return jsonify({"error": "Unknown file or business."}), 404
    if new_status not in lead_store.STATUSES:
        return jsonify({"error": "Unknown status."}), 400

    try:
        saved = lead_store.update_status(path, place_id, new_status)
    except lead_store.FileLocked as error:
        return jsonify({"error": str(error)}), 409

    if not saved:
        return jsonify({"error": "Business not found in this file."}), 404

    return jsonify({"saved": True})


@app.get("/api/export")
def export():
    path = _safe_file(request.args.get("file"))
    if not path:
        return jsonify({"error": "Unknown file."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


def _autopilot_page_data():
    settings = lead_search.load_settings()
    opts = autopilot.options(settings)
    return {
        "settings": {key: value for key, value in opts.items() if key != "cities"},
        "cities": opts["cities"],
        "regions": list(autopilot.REGIONS.items()),
        "stacks": [[key, stack["name"]] for key, stack in autopilot.STACKS.items()],
        "efforts": list(autopilot.EFFORTS.items()),
        "has_publishing": autopilot.publish_site.is_set_up(settings),
        "trades": opts["trade_options"],
        "builder": autopilot.find_builder(opts) or "",
        "sender_name": settings["outreach"]["sender_name"],
        "sender_about": settings["outreach"]["sender_about"],
        "portfolio_links": len(settings["outreach"]["portfolio_links"] or []),
        "channels": settings["outreach"]["channels"],
        "default_language": settings["brief"]["default_language"],
        "running": RUNNER.run_id if RUNNER.busy() else "",
    }


@app.get("/api/autopilot")
def autopilot_page():
    return jsonify(_autopilot_page_data())


@app.post("/api/autopilot/settings")
def autopilot_settings():
    try:
        autopilot.save(request.get_json(silent=True) or {})
    except autopilot.AutopilotError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(_autopilot_page_data())


@app.post("/api/autopilot/check")
def autopilot_check():
    opts = autopilot.options()
    return jsonify(autopilot.check_builder(opts))


@app.post("/api/autopilot/start")
def autopilot_start():
    payload = request.get_json(silent=True) or {}
    if shift_control.status()["running"]:
        return jsonify({"error": "The autopilot is on. Stop it first."}), 409
    try:
        state = RUNNER.start(
            city_text=payload.get("city") or "",
            random_pick=bool(payload.get("random")),
            trade_text=payload.get("trade") or "",
        )
    except autopilot.AutopilotError as error:
        return jsonify({"error": str(error)}), 409 if RUNNER.busy() else 400
    return jsonify({"id": state["id"]})


@app.get("/api/shift")
def shift_status():
    return jsonify(shift_control.status())


@app.post("/api/shift/start")
def shift_start():
    payload = request.get_json(silent=True) or {}
    if RUNNER.busy():
        return jsonify({"error": "A run is going. Stop it, or wait for it to finish."}), 409
    try:
        shift_control.start(payload.get("region"))
    except shift_control.ShiftError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(shift_control.status())


@app.post("/api/shift/stop")
def shift_stop():
    return jsonify({"stopping": shift_control.stop()})


@app.post("/api/autopilot/stop")
def autopilot_stop():
    return jsonify({"stopping": RUNNER.stop()})


@app.get("/api/autopilot/runs")
def autopilot_runs():
    return jsonify({"runs": autopilot.list_runs(RUNNER), "running": RUNNER.run_id if RUNNER.busy() else ""})


@app.get("/api/autopilot/runs/<run_id>")
def autopilot_run(run_id):
    run = autopilot.load_run(run_id, RUNNER)
    if not run:
        return jsonify({"error": "Unknown run."}), 404
    return jsonify(autopilot.view(run))


@app.post("/api/autopilot/runs/<run_id>/sent")
def autopilot_sent(run_id):
    run = autopilot.load_run(run_id, RUNNER)
    if not run:
        return jsonify({"error": "Unknown run."}), 404
    payload = request.get_json(silent=True) or {}
    try:
        row = autopilot.mark_sent(run, payload.get("place_id") or "", payload.get("channel") or "")
    except autopilot.AutopilotError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"sent_at": row["sent_at"], "follow_up_due": row["follow_up_due"]})


@app.get("/ready")
def ready():
    return send_file(ready_list.write())


@app.get("/sites/<path:relative>")
def built_site(relative):
    base = build_brief.output_dir(lead_search.load_settings()).resolve()
    target = (base / relative).resolve()
    if base not in target.parents or not target.is_file():
        abort(404)
    project = base / target.relative_to(base).parts[0]
    if not (project / "brief.md").is_file():
        abort(404)
    return send_file(target)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

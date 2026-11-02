import argparse
import json
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autopilot
import lead_search
import lead_store
import publish_site
import ready_list

ROOT = lead_search.ROOT


def _shift_folder(root=None):
    return lead_store.data_dir(root or ROOT) / "autopilot"


def stop_file(root=None):
    return _shift_folder(root) / "STOP"


def _tried_file(root=None):
    return _shift_folder(root) / "tried_searches.json"


def load_tried(root=None):
    path = _tried_file(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _remember(key, root=None):
    tried = load_tried(root)
    tried.append(key)
    path = _tried_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tried, ensure_ascii=False, indent=2), encoding="utf-8")


def pair_key(city, trade):
    return lead_store.to_slug(autopilot.search_text(trade, city), "search")


def next_pair(opts, tried, rng=None):
    pairs = [(city, trade) for city in autopilot.cities_in(opts["cities_from"], opts) for trade in opts["trades"]]
    fresh = [pair for pair in pairs if pair_key(*pair) not in tried]
    return (rng or random).choice(fresh or pairs)


def plan_levels(run):
    newest = {}
    for candidate in run.state.get("candidates", []):
        windows = (candidate.get("limits") or {}).get("unifiedWindows")
        if windows:
            newest = windows
    return newest


def plan_verdict(levels, options, now=None):
    weekly = (levels.get("seven_day") or {}).get("utilization")
    if weekly is not None and weekly >= options["stop_at_weekly"]:
        return "stop", 0
    five_hour = levels.get("five_hour") or {}
    if five_hour.get("utilization") is not None and five_hour["utilization"] >= options["pause_at_five_hour"]:
        return "wait", max(0, five_hour.get("resetsAt", 0) - (now or time.time())) + options["after_reset_seconds"]
    return "go", 0


def _ready_sites(run):
    return [
        {
            "place_id": candidate["place_id"],
            "name": candidate["name"],
            "city": candidate.get("city", ""),
            "country_code": candidate.get("country_code", ""),
            "folder": candidate["folder"],
        }
        for candidate in run.state.get("candidates", [])
        if candidate["state"] == "done"
    ]


def _pause(seconds, say, root=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop_file(root).exists():
            say("Stop file found.")
            return False
        time.sleep(min(autopilot.STOP_POLL_SECONDS, max(0, deadline - time.monotonic())))
    return True


def _watch_for_stop(stop_event, root=None):
    while not stop_event.wait(autopilot.STOP_POLL_SECONDS):
        if stop_file(root).exists():
            stop_event.set()


def _publish(settings, say):
    sites = publish_site.unpublished_sites()
    if not sites:
        return 0
    try:
        return len(publish_site.publish(sites, settings))
    except (publish_site.PublishError, OSError, ValueError) as error:
        say("Publishing failed, the sites stay on this computer: {}".format(error))
        return 0


def _one_search(settings, opts, say, stop_event, rng=None):
    city, trade = next_pair(opts, load_tried(), rng)
    _remember(pair_key(city, trade))
    run = autopilot.new_run(city, trade)
    place = ", ".join(part for part in (city["name"], city.get("state") or city.get("country")) if part)
    say("Searching {} in {}.".format(trade, place))
    autopilot.execute(run, settings, stop_event, report=say)
    return run


def shift(hours, most_sites, settings, say, rng=None):
    options = settings["night"]
    settings["autopilot"]["keep_awake"] = False
    opts = autopilot.options(settings)
    endless = not hours and not most_sites
    deadline = time.monotonic() + hours * 3600 if hours else float("inf")
    most_sites = most_sites or float("inf")
    built = published = quiet = 0
    stop_event = threading.Event()
    threading.Thread(target=_watch_for_stop, args=(stop_event,), daemon=True).start()

    while time.monotonic() < deadline and built < most_sites:
        if stop_file().exists():
            say("Stop file found.")
            break
        settings["autopilot"]["sites_per_run"] = min(opts["sites_per_run"], most_sites - built)
        try:
            run = _one_search(settings, opts, say, stop_event, rng)
        except Exception as error:
            say("This search failed: {}".format(error))
            quiet += 1
        else:
            done = len(_ready_sites(run))
            built += done
            published += _publish(settings, say)
            ready_list.write(settings)
            quiet = 0 if run.state.get("source") == "gosom" else quiet + 1
            say("{} built this search, {} tonight, {} published.".format(done, built, published))

            verdict, seconds = plan_verdict(plan_levels(run), options)
            if verdict == "stop":
                say("The weekly Claude limit reached the level set in night.stop_at_weekly.")
                break
            if verdict == "wait":
                say("Waiting {} minutes for the five hour limit to reset.".format(round(seconds / 60)))
                if not _pause(seconds, say):
                    break

        if stop_event.is_set():
            say("Stop file found.")
            break
        if quiet >= options["give_up_after_failures"]:
            if not endless:
                say("Google Maps searches kept failing, so the shift stops here.")
                break
            say("Google Maps searches keep failing, so the next one is in {} minutes.".format(options["blocked_pause_minutes"]))
            quiet = 0
            if not _pause(options["blocked_pause_minutes"] * 60, say):
                break
            continue
        if built < most_sites:
            say("Next search in {} minutes.".format(options["pause_minutes"]))
            if not _pause(options["pause_minutes"] * 60, say):
                break

    return built, published


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    settings = lead_search.load_settings()
    parser = argparse.ArgumentParser(
        description="Searches, picks, builds and publishes until the time or the site limit. It never sends anything."
    )
    parser.add_argument("--hours", type=float, default=settings["night"]["hours"], help="0 means no time limit")
    parser.add_argument("--sites", type=int, default=settings["night"]["max_sites"], help="0 means no limit on sites")
    parser.add_argument("--region", choices=list(autopilot.REGIONS), help="Where the cities come from")
    arguments = parser.parse_args()
    if arguments.region:
        settings["autopilot"]["cities_from"] = arguments.region

    log_path = _shift_folder() / "night.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stop_file().unlink(missing_ok=True)

    def say(text):
        line = "{} {}".format(datetime.now().strftime("%H:%M:%S"), text)
        print(line)
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    awake = autopilot._keep_awake({"keep_awake": True})
    say("Shift starts: {} sites, {} hours, cities from {}.".format(
        arguments.sites or "any number of", arguments.hours or "any number of", settings["autopilot"]["cities_from"]
    ))
    try:
        built, published = shift(arguments.hours, arguments.sites, settings, say)
    finally:
        if awake is not None:
            awake.terminate()
    say("Shift ends: {} sites built, {} published. See {}.".format(built, published, ready_list.write(settings)))


if __name__ == "__main__":
    main()

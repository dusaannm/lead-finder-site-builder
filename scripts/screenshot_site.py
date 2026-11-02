import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_site
import lead_search

SHOT_PAGE = "_screenshot.html"
SHEET_PAGE = "_screenshot_sheet.html"
SHOT_FOLDER = "screens"
FULL_HEIGHT = re.compile(rb'data-full-height="(\d+)"')
SCROLLER = """<script>
addEventListener("load", function () {
  var page = document.documentElement;
  scrollTo({ top: Number(location.hash.slice(1)), behavior: "instant" });
  page.dataset.fullHeight = page.scrollHeight;
});
</script>
"""


SHEET = """<!doctype html>
<style>
html, body {{ margin: 0; background: #fff; }}
body {{ display: flex; flex-wrap: wrap; width: {width}px; }}
iframe {{ display: block; border: 0; }}
</style>
{frames}
"""


class ScreenshotError(Exception):
    pass


def browser_path(path, options):
    resolved = Path(path).resolve()
    if not options["linux_paths"]:
        return str(resolved)
    return "/mnt/{}{}".format(resolved.drive.rstrip(":").lower(), resolved.as_posix()[len(resolved.drive) :])


def page_url(path, options, offset):
    resolved = Path(path).resolve()
    base = "file://{}".format(quote(browser_path(path, options))) if options["linux_paths"] else resolved.as_uri()
    return "{}#{}".format(base, offset)


def tile_offsets(full_height, view_height, most):
    count = max(1, min(most, -(-full_height // view_height)))
    return [view_height * number for number in range(count)]


def _run(arguments, options):
    command = list(options["launcher"]) + [options["executable"]] + list(options["flags"]) + arguments
    try:
        return subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, timeout=options["timeout_seconds"])
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScreenshotError("The browser did not finish: {}".format(type(error).__name__))


def _window(view):
    return "--window-size={},{}".format(view["width"], view["height"])


def _full_height(page, view, options):
    finished = _run([_window(view), "--dump-dom", page_url(page, options, 0)], options)
    found = FULL_HEIGHT.search(finished.stdout)
    if not found:
        raise ScreenshotError("The browser could not open {}.".format(page))
    return int(found.group(1))


def sheet_page(page_name, view, offsets):
    columns = min(view["columns"], len(offsets))
    frames = "".join(
        '<iframe src="{}#{}" width="{}" height="{}"></iframe>'.format(page_name, offset, view["width"], view["height"])
        for offset in offsets
    )
    return SHEET.format(width=view["width"] * columns, frames=frames), columns


def _shoot(page, name, view, folder, options):
    offsets = tile_offsets(_full_height(page, view, options), view["height"], options["max_tiles"])
    text, columns = sheet_page(page.name, view, offsets)
    rows = -(-len(offsets) // columns)
    sheet = page.parent / SHEET_PAGE
    target = folder / "{}.png".format(name)
    target.unlink(missing_ok=True)
    sheet.write_text(text, encoding="utf-8")
    try:
        size = {"width": view["width"] * columns, "height": view["height"] * rows}
        _run([_window(size), "--screenshot={}".format(browser_path(target, options)), page_url(sheet, options, 0)], options)
    finally:
        sheet.unlink(missing_ok=True)
    if not target.is_file():
        raise ScreenshotError("The browser wrote no screenshot of {}.".format(page))
    with Image.open(target) as whole:
        scale = view["tile_width"] / view["width"]
        smaller = whole.convert("RGB").resize((round(whole.width * scale), round(whole.height * scale)))
    smaller.save(target)
    return target


def take(folder, settings):
    options = settings["screenshots"]
    if not options["executable"]:
        raise ScreenshotError("screenshots.executable is not set, so nobody can look at this site here.")
    folder = Path(folder).expanduser()
    entry = check_site.entry_page(folder)
    if entry is None:
        raise ScreenshotError("{} has no built site.".format(folder))

    shot_page = entry.parent / SHOT_PAGE
    shots = folder / SHOT_FOLDER
    shots.mkdir(exist_ok=True)
    shot_page.write_text(entry.read_text(encoding="utf-8", errors="replace") + SCROLLER, encoding="utf-8")
    try:
        return [_shoot(shot_page, name, view, shots, options) for name, view in options["views"].items()]
    finally:
        shot_page.unlink(missing_ok=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Photographs a built site from top to bottom at phone and desktop width, one contact sheet for each."
    )
    parser.add_argument("folder", help="The business folder that holds site/")
    arguments = parser.parse_args()

    try:
        paths = take(arguments.folder, lead_search.load_settings())
    except ScreenshotError as error:
        print("\nERROR: {}\n".format(error))
        raise SystemExit(1)

    print("\nOpen these and look at them:\n")
    for path in paths:
        print("  {}".format(path))
    print()


if __name__ == "__main__":
    main()

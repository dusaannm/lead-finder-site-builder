import argparse
import shutil
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lead_search
import lead_store

ROOT = lead_search.ROOT
FONT_FOLDER = "fonts"
STYLESHEET = "fonts.css"
FONT_FACE = """@font-face {{
  font-family: "{name}";
  src: url("{folder}/{file}") format("woff2");
  font-weight: {weight};
  font-style: normal;
  font-display: swap;
}}
"""


class FontError(Exception):
    pass


def library_dir(root=None):
    return lead_store.data_dir(root or ROOT) / FONT_FOLDER


def catalogue(settings):
    return {font["id"]: font for font in settings["fonts"]["library"]}


def _file_name(font_id, weight):
    return "{}-{}.woff2".format(font_id, weight)


def _cached(font, weight, options, root=None):
    path = library_dir(root) / _file_name(font["id"], weight)
    if path.is_file():
        return path
    url = options["url"].format(family=font["id"], weight=weight)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        raise FontError("{} could not be downloaded: {}".format(url, type(error).__name__))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def font_faces(fonts):
    return "".join(
        FONT_FACE.format(name=font["name"], folder=FONT_FOLDER, file=_file_name(font["id"], weight), weight=weight)
        for font in fonts
        for weight in font["weights"]
    )


def add(folder, font_ids, settings, root=None):
    folder = Path(folder).expanduser()
    if not (folder / "brief.md").is_file():
        raise FontError("{} holds no brief.md, so it is not a business folder.".format(folder))

    known = catalogue(settings)
    unknown = [font_id for font_id in font_ids if font_id not in known]
    if unknown:
        raise FontError("{} not in fonts.library in config.yaml.".format(", ".join(unknown)))

    fonts = [known[font_id] for font_id in font_ids]
    target = folder / "site" / FONT_FOLDER
    target.mkdir(parents=True, exist_ok=True)
    for font in fonts:
        for weight in font["weights"]:
            shutil.copy2(_cached(font, weight, settings["fonts"], root), target / _file_name(font["id"], weight))
    (folder / "site" / STYLESHEET).write_text(font_faces(fonts), encoding="utf-8")
    return fonts


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Puts open licence typefaces into site/fonts/ of a business folder and writes site/fonts.css."
    )
    parser.add_argument("folder", help="The business folder that holds brief.md")
    parser.add_argument("fonts", nargs="+", help="Font ids from fonts.library in config.yaml")
    arguments = parser.parse_args()

    try:
        fonts = add(arguments.folder, arguments.fonts, lead_search.load_settings())
    except FontError as error:
        print("\nERROR: {}\n".format(error))
        raise SystemExit(1)

    print('\nLoad them from index.html, before style.css:\n\n  <link rel="stylesheet" href="{}">\n'.format(STYLESHEET))
    for font in fonts:
        print('  font-family: "{}", {}; weights {}'.format(font["name"], font["fallback"], ", ".join(map(str, font["weights"]))))
    print()


if __name__ == "__main__":
    main()

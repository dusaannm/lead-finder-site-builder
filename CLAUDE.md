# lead-finder-site-builder

Finds local businesses that have no website or a bad one, ranks them as
prospects, then prepares everything needed to send them a finished demo site
and a message.

This file is the briefing for whoever works on this repository. It is written
for Claude Code, which reads it automatically at the start of a session. If you
work with a different assistant, hand it the contents of this file first. It is
plain English and nothing in it is specific to one tool.

## Run things with the virtual environment

Never a bare `python`. Always the copy inside `venv`, which lands in a different
folder depending on the platform:

- macOS and Linux: `venv/bin/python`
- Windows: `venv/Scripts/python.exe`

The same clone gets used on both, so nothing in this repository hardcodes either
one. Commands here and under `commands/` are written as `{venv python}`. Look at
which of the two paths actually exists in the project folder and run that one,
rather than guessing from the platform you think you are on.

```
{venv python} scripts/find_leads.py "picerija Novi Sad"
{venv python} scripts/audit_site.py example.com
{venv python} app.py
```

Substitute a `{...}` before running the command, never after. A shell reads `<`
and `>` as redirection, so pasting a placeholder written that way empties the
file named on the right of the `>` before reporting that the command does not
exist. Braces cannot do that, which is why they are the ones used here.

`run` and `run.bat` in the project root do that same resolution for a person
typing by hand: `./run scripts/find_leads.py "picerija Novi Sad"` on macOS and
Linux, `run.bat` in its place on Windows, written `.\run.bat` in PowerShell.
That is the form the README documents, because a person types it thirty times a
day.

Keep using `{venv python}` in instructions like these. A ZIP download of the
repository loses the flag that makes `run` executable, and an interpreter path
cannot lose anything.

Never start `app.py` with a plain shell command when a preview tool is
available.

## The rule the architecture rests on

Anything that gives the same answer every time, meaning searching, filtering,
scoring, downloading, moving files and reading colours, is a Python script. The
model is used only where judgement is required: describing what a place looks
like, choosing sections for a trade, writing copy, writing the outreach message.

This is why `find_stock_photos.py` is handed a query plan instead of inventing
search terms, and why `sort_assets.py` refuses to move anything until the
categories are filled in.

## Code conventions

- No comments anywhere in the code, and no explanatory headers at the top of
  files. Names carry the meaning. When a name cannot, that is the signal to
  rename or to split the function, not to explain it.
- Everything is written in English: identifiers, config keys, CSV columns,
  printed output, the browser interface, and the docs.
- Every tunable number lives in `config.yaml`, never inline in a script.
- Anything personal to one user, such as their name and their portfolio links,
  belongs in `config.local.yaml`. That file is gitignored and merged over
  `config.yaml` when settings load, so `config.yaml` can stay public and ship
  with those fields empty.
- The autopilot settings the browser saves go to `data/autopilot_settings.json`
  and are laid over `autopilot` in `config.yaml` and `config.local.yaml`. Read
  them through `scripts/autopilot.py settings`, never by opening one file.
- Secrets come from `.env` through `python-dotenv` and are never printed.
- No heavy dependencies. `requests`, `beautifulsoup4`, `python-dotenv`,
  `flask`, `PyYAML` and `Pillow` are the whole list.
- The browser interface is plain HTML, CSS and JavaScript. No component
  libraries.

## Data

CSV files under `data/` are the database. `place_id` is the key that survives
across searches, which is what lets a rerun refresh the data while keeping what
the user typed by hand: the `status`, and the address, phone, opening hours,
rating and review count where the source has none. An empty incoming value
never overwrites one of those, nor an email, Instagram or Facebook an earlier
search found. Never reorder or rename CSV columns without migrating existing
files; a new column goes at the end, where older files simply lack it.

`data/`, `.env`, `config.local.yaml` and `assets/` never get committed.

## Building a website for a lead

`/build-brief <place_id or business name>` prepares a folder in
`brief.output_dir` from `config.yaml`, or on the Desktop when that is empty:

```
<Business>/
├── brief.md      the full instruction for the site, self contained
├── assets/       the photographs, every one listed in brief.md
└── site/         empty, this is where the website goes
```

When asked to build the site, read that folder's `brief.md` and follow the
"Build prompt" section in it literally. `/build-site <folder>` does this.

`/autopilot <place_id or business name>` does both, then drafts the messages
into `outreach.md` in the same folder, without asking anything: the answers come
from the autopilot settings. The Autopilot tab in the browser starts it for each
business it picks, as Claude Code in print mode with an allow-list of reading
files, writing in the output folder and `data/autopilot`, and running
`scripts/*.py`. Keep `commands/autopilot.md` working inside that list: no other
shell command, no web access, `scripts/autopilot.py drop-photo` instead of
deleting files by hand, and `scripts/add_gsap.py` instead of fetching GSAP.
`scripts/check_site.py` is the check it runs when no browser is there to look
with. Several businesses build at once, `autopilot.builder.parallel` of them,
so anything a run writes outside its own business folder goes through
`Run.change` in `scripts/autopilot.py`, which holds the lock.

The stack is decided per business and written into the brief. Plain HTML, CSS
and JavaScript is the default and the right answer for most one page local
business sites, because the folder can be sent as is and opened by double
clicking. A framework is fine when the site actually needs one, as long as it
builds to a static bundle that runs on any host with no server behind it.

Whatever the stack, the site is mobile first, and it is never called finished
until it has been served and looked at in a browser at 360px and at desktop
width.

## Git

Work on a branch per phase, open a pull request, then merge it. Commit messages
in English. Do not add co-author trailers.

## Boundaries that are deliberate, do not remove them

- The tool never sends a message anywhere and holds no credentials for any
  messaging account. It only drafts. The autopilot included: a message is
  logged as sent only when the person presses the button that says so.
- Site images come from Pexels or Pixabay, whichever has a key in `.env`, chosen
  by trade from `stock_photos.plans` in `config.yaml`, or from the client.
- The monthly Google call limit in `config.yaml` stays below the free tier.
- The only thing that reads Google Maps in bulk is `scripts/sources/gosom.py`,
  which the owner of this fork turned on knowingly in `config.local.yaml` and
  which stays off in `config.yaml`. It runs slowly, on one connection, with no
  proxies and no way around a block. When Google refuses, the search falls back
  to OpenStreetMap. Nothing scrapes CompanyWall; the tool generates links a
  human clicks. During `/build-brief` the assistant may open the listing of the
  one lead being built and read it the way a person would, never the listings
  of a whole search.

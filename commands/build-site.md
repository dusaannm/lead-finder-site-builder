---
description: Build the website for a prepared brief folder
argument-hint: <folder or business name>
allowed-tools: Bash, Read, Write, Edit, Glob
---

Build the website described by the brief in `$1`.

`$1` may be a full path, or just the business name, in which case look for a
folder with that name in `brief.output_dir` from `config.yaml`, which a
`config.local.yaml` may override. Look on the Desktop when that setting is
empty.

`{venv python}` below is the Python inside `venv`: `venv/bin/python` on macOS and
Linux, `venv/Scripts/python.exe` on Windows. Check which of the two exists in the
project folder and use that one. Never a bare `python`.

Substitute every `{...}` before running a command. Never paste one into a shell
as it stands.

## 1. Read the brief

Read `$1/brief.md` in full before writing anything. The section named
**Build prompt** is the instruction and it stands on its own — follow it
literally rather than substituting your own preferences.

The **Images** section of that brief lists every photograph: the path to use,
where on the page it belongs, whether it is stock or the business's own, and
what it shows. That list is the authority. Do not read a folder name and infer
from it, and do not use a file the list does not mention.

Use the descriptions to place images sensibly beyond that: do not put an oven
photograph in a team section.

## 2. Build

Write the site into `$1/site/`, in the stack the brief names. For plain HTML
that is `index.html`, `style.css` and `script.js`; for a stack with a build step
it is whatever that stack needs, set up inside `site/`.

Hard rules, repeated because they are the ones most often broken:

- The stack is whatever `brief.md` says under **Build prompt**. Do not quietly
  swap it. Whatever it is, the production build must end up as a static bundle
  that runs on any host with no server behind it.
- Image paths are relative, `../assets/` followed by the path the brief gives.
- Every visible word is in the language the brief names.
- No lorem ipsum. Write real copy for this business.
- Never invent reviews, staff names or prices. The address, phone and opening
  hours are real wherever the brief's table gives them, so use them exactly;
  where it says "not listed", treat that one as unknown too. The page has to
  read as finished: no bracketed notes, no "Owner:" text and no empty slots.
  Write around what is unknown or leave it out, and list what the owner could
  add in an HTML comment at the bottom of `index.html`.
- `<title>`, `<meta name="description">` and `<meta name="viewport">` are
  mandatory.
- When the brief asks for GSAP, get local copies of `gsap.min.js` and
  `ScrollTrigger.min.js` into `site/vendor/` and load them from there, never
  from a CDN:

  ```
  {venv python} scripts/add_gsap.py "{brief folder}"
  ```

## 3. Serve it and look at it

This step is not optional. Never say a site is finished without having opened
it.

First let the script catch what a script can, given the full path of the
folder that holds `brief.md`:

```
{venv python} scripts/check_site.py "{brief folder}"
```

It checks the title, the description, the viewport, a single `<h1>`, the
JSON-LD, every image path and alt text, and that no lorem ipsum or bracketed
note is left, no demo notice of its own, no template headings. Fix
what it lists, then open the site, because no script can tell whether it looks
right.

Where `screenshots.executable` is set, this shows the whole page at phone and
desktop width in `screens/phone.png` and `screens/desktop.png`:

```
{venv python} scripts/screenshot_site.py "{brief folder}"
```

Serve it through whatever local preview your tools offer. In Claude Code that
is an entry in `.claude/launch.json` started with the preview tool. For a plain
HTML site it is a static file server rooted at the brief folder, so `../assets/`
resolves; for a framework it is that stack's dev command.

Then look at it at 360px wide before anything else, then at desktop width. Read
the browser console for errors. Confirm every image actually loads rather than
assuming the paths are right.

Fix what you find, re-check, then screenshot both widths and show them.

Leave the server running so they can click around, and tell them the address.

To put it online for the owner to see, publish it on Cloudflare Pages. This
needs `CLOUDFLARE_API_TOKEN` in `.env`, as section 5 of `SETUP.md` explains:

```
{venv python} scripts/publish_site.py
```

It publishes every finished site that is not online yet and prints each public
address, which also replaces the demo link in that site's `outreach.md`.

## 4. Report

Say which files you wrote, list what the owner could still add, and give one
sentence on what this site does better than whatever the business has
now.

Do not write the outreach message here. That is `/draft-outreach`.

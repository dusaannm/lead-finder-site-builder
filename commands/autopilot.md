---
description: Build one lead start to finish with the saved autopilot settings, asking nothing
argument-hint: <place_id or business name>
allowed-tools: Bash, Read, Write, Edit, Glob
---

Take the lead that `$1` names from a row in a search result to a finished demo
site and three drafted messages, using the autopilot settings saved on the
Settings page of the browser. Ask nothing. Every answer `/build-brief` would
ask for is already in those settings, and every other decision below names its
default.

`{venv python}` below is the Python inside `venv`: `venv/bin/python` on macOS and
Linux, `venv/Scripts/python.exe` on Windows. Check which of the two exists in the
project folder and use that one. Never a bare `python`.

Substitute every `{...}` before running a command. Never paste one into a shell
as it stands.

Never send anything and never log anything as sent. The person reads the
messages and sends them.

## 1. Prepare

```
{venv python} scripts/autopilot.py prepare "$1"
```

It finds the lead, downloads its stock photographs unless they are already
there, and writes the answers from the settings into a file. It prints JSON
naming that `answers_file`, the `stock_folder`, the `project_folder`, the city,
the site language, what is known about the business, the sender, the price, what
the price includes, and the portfolio links.

## 2. Check the photographs

Read every `description` in `sources.json` in the stock folder against the
trade and against what is known about this business, then open every hero and
interior photograph and look at it. Remove each one that plainly shows another
kind of business or food this place does not sell, or another business's name or
logo on a window, a cup or a board:

```
{venv python} scripts/autopilot.py drop-photo "$1" {file} {file}
```

`{file}` is the path as `sources.json` writes it, such as `hero/hero_123.jpg`.
Do not search again. One photograph fewer is fine; somebody else's sign in
front of the owner is not.

## 3. Write the brief

Read the answers file and add what only judgement can give. Leave every value
already in it exactly as it is.

- `sections`, `seo_keywords`, `trade` and, when the file has none, `style`,
  exactly as step 4 of `commands/build-brief.md` describes them, but shaped by
  the `description` and `review_notes` step 1 printed: `trade` says what this
  place really is, such as "Chinese bakery", and `style` is a look that fits it
  and differs from the usual look of the trade. Leave out any section that would
  only exist to be filled in later.
- `language`, when the file has none: the language most people in that city
  speak.
- `city`, when the file has none, read from the lead's address or its Maps link.

Then:

```
{venv python} scripts/build_brief.py "$1" --answers {answers_file} --stock {stock_folder}
```

## 4. Build the site

Follow steps 1 and 2 of `commands/build-site.md` for the project folder: read
`brief.md` and build exactly what its **Build prompt** asks for.

When the brief asks for GSAP and ScrollTrigger, get the local copies first:

```
{venv python} scripts/add_gsap.py {project_folder}
```

It puts `gsap.min.js` and `ScrollTrigger.min.js` in `site/vendor/` and prints
the two script tags to load them with. Load them from there and never open
those files: they are minified and only fill the session.

For a stack with a build step, install and build from the project folder with
`npm --prefix {project_folder}/site install` and
`npm --prefix {project_folder}/site run build`, so the finished bundle lands in
`site/dist/`.

Then check it:

```
{venv python} scripts/check_site.py {project_folder}
```

Fix every problem it lists and run it again until it passes. When you also
have a browser preview tool, serve the site and look at it at 360px and at
desktop width, as step 3 of `commands/build-site.md` describes. Without one,
the check is the last word, and the person looks at the site in the browser
page afterwards.

## 5. Draft the messages

Write the three versions exactly as step 3 of `commands/draft-outreach.md`
describes, in the site language, using the sender, the postal address, the price
and what it includes, all as step 1 printed them, plus every portfolio link when
there are any. Where the sender name is empty, sign with `[your name]` rather
than inventing one. Write the demo link as exactly `[link to the demo site]`,
which is replaced when the site is published.

Save them to `outreach.md` in the project folder under exactly these three
headings, so the browser page can show each one with a copy button:

```
## Email
## Viber or WhatsApp
## Instagram
```

The email starts with its `Subject:` line.

## 6. Report

One short paragraph: the folder, whether the check passed, what the owner could
still add, and that the messages are in `outreach.md`.

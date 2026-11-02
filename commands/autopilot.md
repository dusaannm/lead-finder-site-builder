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
the price includes, and the portfolio links. It also prints `reference_photo`,
`order_link`, `design_options`, `recent_designs_in_this_trade` and `fonts`.

## 2. Find the idea

Before anything else, work out what makes this one business different.

Read `description` and `review_notes` closely: what people order, what they
praise, how they talk about the place, who goes there. When `reference_photo` is
not empty, open that file and look at it for the real colours, materials and
mood of the place. It is only for you to look at. It never goes on the site.

Then write one or two sentences of `concept`: the idea this site is built on. A
good one borrows its form from something real in this business's world, the way
a coffee shop called Courier becomes a parcel with labels and stamps. "Warm and
welcoming" is not an idea.

Choose from what step 1 printed:

- `design_direction`: the `name` of the one entry in `design_options` that suits
  this place best. Those are the directions not used lately in this trade.
- `display_font` and `body_font`: an `id` each from `fonts`, role `display` and
  role `body`. Add `accent_font`, role `accent`, only if the idea needs it. Choose
  by `feel` to suit this place, from these only. They differ for every business.
- `primary_action`: the one thing a customer of this business really does next.
  People do not phone a cafe: send them to directions, or to `order_link` when
  there is one, and write the button label. A locksmith or a plumber is a call. A
  bakery may be ordering a cake by phone, when reviews mention cakes.

## 3. Check the photographs

Search for what this place really sells, in two to four English terms a photo
search would understand, such as `cuban pastries`:

```
{venv python} scripts/autopilot.py add-photos "$1" "{term}" "{term}"
```

Read every `description` in `sources.json` in the stock folder against the
trade and against what is known about this business, then open every hero and
interior photograph and look at it. Remove each one that plainly shows another
kind of business or food this place does not sell, or another business's name or
logo on a window, a cup or a board:

```
{venv python} scripts/autopilot.py drop-photo "$1" {file} {file}
```

`{file}` is the path as `sources.json` writes it, such as `hero/hero_123.jpg`.
One photograph fewer is fine; somebody else's sign in front of the owner is not.

## 4. Write the brief

Read the answers file and add what only judgement can give. Leave every value
already in it exactly as it is.

- `concept`, `design_direction`, `display_font`, `body_font`, `accent_font` when
  there is one, and `primary_action`, from step 2.
- `sections`, `seo_keywords`, `trade` and, when the file has none, `style`,
  exactly as step 4 of `commands/build-brief.md` describes them, but shaped by
  the `description` and `review_notes` step 1 printed: `trade` says what this
  place really is, such as "Chinese bakery", and `style` follows from the concept
  and differs from the usual look of the trade. Choose sections for this business
  instead of the usual list, and leave out any that would only exist to be filled
  in later. Name them for what they hold, in this business's words.
- `language`, when the file has none: the language most people in that city
  speak.
- `city`, when the file has none, read from the lead's address or its Maps link.

Then:

```
{venv python} scripts/build_brief.py "$1" --answers {answers_file} --stock {stock_folder}
```

## 5. Build the site

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

Fix every problem it lists and run it again until it passes.

## 6. Look at it

```
{venv python} scripts/screenshot_site.py {project_folder}
```

It photographs the page from top to bottom, one screen after another, into
`screens/phone.png` and `screens/desktop.png` in the project folder. Open both
and look at them as a stranger would. Does it look like a designer made it for
this business, or could it be a template with the name swapped? Is the idea of
the site visible at a glance? Does any text break, overflow or sit unreadably on
a picture? Is anything missing, empty or hidden?

Fix what you find, in the code, then run the screenshots again and look once
more. Two rounds are enough. If the script reports an error, say so in the report
and continue.

## 7. Draft the messages

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

## 8. Report

One short paragraph: the folder, whether the check passed, the concept, what the
owner could still add, and that the messages are in `outreach.md`.

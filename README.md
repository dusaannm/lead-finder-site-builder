# lead-finder-site-builder

Most prospecting tools stop at a list of businesses. This one carries a single
business all the way to a finished website and a written message you can send.

## What problem this solves

Plenty of small local businesses have no website at all, or one that was built
years ago and no longer works on a phone. They are good customers for anyone who
builds websites, but finding them takes hours of walking around a city, looking
things up, and writing notes.

This tool does that part for you. You type what you are looking for and where,
for example `bakery Novi Sad`, and it returns a ranked list of businesses,
putting the ones that need a website most at the top. From there it will check
what they already have, gather photographs you are legally allowed to use, write
a full instruction for the website, and draft the message you send the owner.

You still make every real decision. The tool prepares the work.

## The six steps

```
find  ->  rank  ->  check the old site  ->  gather photos  ->  build  ->  write
```

**1. Find.** You search for a trade and a place. The tool asks either Google or
OpenStreetMap and brings back local businesses, including the one thing that
matters most: whether they have a website.

**2. Rank.** Every business gets a score. No website is worth 50 points. A
website that exists but is in bad shape is worth 30. A rating of 4.3 or more
adds 20. Fifty or more reviews add 20, twenty or more add 10, and fewer than ten
take 30 away. Having a phone number adds 10.

The idea behind those numbers: a business with 200 reviews and a 4.6 rating that
has no website is clearly doing well but is invisible online, and that is the
ideal person to approach. A business with six reviews is either brand new or on
its way out, and is not worth your afternoon.

Every one of those numbers lives in `config.yaml` and you can change them
without touching any code.

**3. Check the old site.** For every business that already has a website, the
tool opens it and scores it from 0 to 100. It looks at whether the site opens at
all, whether it has a security certificate, whether it adapts to a phone screen,
how long it takes to load, how many years since it was last touched, what it was
built with, and whether it has the basics that search engines need.

Each problem it finds comes back as a plain sentence you can put straight into a
message, for example "the site does not adapt to phones, and around 70% of
people look you up on a phone".

A bad site scores lower than 60, which adds 30 points to that business and moves
it up your list. So the ranking covers both people who have nothing and people
who have something broken.

**4. Gather photographs.** Once the tool knows the trade, for example a pizzeria
or a dentist, it already knows what to look for. `config.yaml` holds a ready set
of searches for each trade, split by where the photographs belong on the page:
the image at the top, the gallery, section backgrounds, the interior.

Those searches go to Pexels, whose photographs are free to use commercially, so
they can go straight onto a demo site. Every folder gets a `sources.json` naming
the photographer and linking the original.

Nothing has to be described and no account is needed beyond the Pexels key. If
you do want the images closer to one particular place, you can add a few search
words such as "exposed brick industrial", which run as one more search, after
the ready ones, for the image at the top and the interior. A whole sentence is
refused, because it
matches pictures by stray words and loses the trade. Skipping that is the
normal case.

The searches for each spot on the page take turns: the first photograph comes
from the first search, the second from the second, and round again. Every search
lands in the set, and one that brings back the wrong kind of place costs one
photograph instead of all of them.

Stock is the floor, not the ceiling. A business with no website still has a
Google Maps listing and usually an Instagram page, so you can save a few of
their own photographs into a folder and hand it over as well. Those are sorted
by what is in them, mapped to where they belong on the page, and they take that
place from the stock ones: their storefront becomes the image at the top and
the stock one is dropped, while stock keeps the backgrounds nobody photographs
for themselves. A logo among them also sets the palette.

**5. Build.** It writes a folder, on your Desktop unless you point it somewhere
else, containing everything the website needs: the business details, the visual
direction, the list of sections, search keywords for that trade and city, the
photographs, and a complete instruction for building the site. Then the site
gets built into that folder.

**6. Write.** It drafts three versions of the outreach message, one for email,
a shorter one for Viber or WhatsApp, and a very short one for an Instagram
message. It records who you contacted and reminds you who has not answered after
four days.

It does not send anything. See "Things it will not do" below.

There are two ways through those six steps, and both stay available. By hand,
you pick each business from the table and answer a few questions about it
before its site is built. With the
[autopilot](#autopilot-one-city-start-to-finish), you type a city or let it
pick one, and it runs every step on its own with answers you set once, until
all that is left is reading the message and sending it.

## Requirements

Python 3.9 or newer. Nothing else. There is no database to install, no server
to configure, and no account you must have before you can try it.

Python 3.9 is what macOS still ships, and it works with one cosmetic cost:
`requests` prints a `urllib3 ... LibreSSL` warning above every command. The
warning is harmless, and it disappears if you install a current Python from
python.org or Homebrew and build the `venv` with that one instead.

## Installing it

Open a terminal and run these four commands, on macOS and Linux:

```bash
git clone https://github.com/andrijaivankovic/lead-finder-site-builder.git
cd lead-finder-site-builder
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

On Windows the first two are the same and the last two differ, because the
launcher there is called `python` and the private copy lands in a different
folder. These two work in both Command Prompt and PowerShell:

```
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

### What `venv` is, and why every command starts with it

Python programs rely on libraries, which are pieces of code other people wrote
and shared. This project uses six of them.

Installing libraries the ordinary way puts them in one shared pile for your whole
computer. That works until two projects need different versions of the same
library, at which point one of them breaks and the reason is not obvious. It also
does not stay still: libraries change on purpose, and code written against one
version can stop running on the next. The problem rarely bites today. It bites a
year from now, when you come back to a project that used to work.

The third command, `python3 -m venv venv`, creates a folder called `venv` inside
this project holding its own private copy of Python and its own libraries.
Nothing outside that folder is touched, and nothing outside it can break what is
inside. Together with `requirements.txt`, which lists the exact libraries this
project needs, it is what makes the project still run next year.

The trade is that you have to point at that private copy on purpose, rather than
typing a plain `python`. Typing plain `python` would reach for the shared pile,
which does not have this project's libraries, and you would see an error saying
a module could not be found. On macOS it usually fails one step earlier, with
`command not found`, because there is no `python` on the system at all, only
`python3`. The `run` launcher below does that pointing for you.

`venv` is part of Python itself, so there is nothing extra to install. Other
tools do the same job more comfortably, `uv` and `poetry` among them, but each is
a separate program you would have to install first, and this project would rather
run on a plain Python and nothing else.

It also makes removing the project simple. Delete the folder and it is gone.
Nothing was ever installed anywhere else on your computer.

### The `run` launcher

`run` hands whatever you type after it to the Python inside `venv`, so you do
not have to write that path out every time. You can now run a search:

```bash
./run scripts/find_leads.py "bakery Novi Sad"
```

On Windows the launcher is `run.bat`. Command Prompt finds it in the current
folder on its own. PowerShell, like macOS and Linux, deliberately does not, so
there it needs `.\` in front:

```
run.bat scripts/find_leads.py "bakery Novi Sad"
.\run.bat scripts/find_leads.py "bakery Novi Sad"
```

The first line is for Command Prompt, the second for PowerShell, and every
`./run` command further down changes the same way. If you would rather see what
is happening, this is the same command on macOS and Linux:

```
venv/bin/python scripts/find_leads.py "bakery Novi Sad"
```

Both work. If `./run` says `permission denied`, you downloaded a ZIP rather
than cloning, and a ZIP drops the flag that marks a file runnable: run
`chmod +x run` once, or type `sh run` instead.

The search above needs no account and no key, using OpenStreetMap. Read on if
you want the better data.

## Adding your API keys

Two services can be connected. Neither is required to start.

**Pexels** provides the photographs. It is free, has no paid tier, and never
asks for a card.

**Google Places** provides better business data, in particular ratings and
review counts, which two of the five ranking rules depend on. Without it the
tool uses OpenStreetMap, which is free but has no ratings, so the ordering is
rougher.

Create the file that holds your keys:

```bash
cp .env.example .env
```

Open `.env` in any text editor and paste your keys after the equals signs. The
file is ignored by Git and will never be uploaded anywhere.

[SETUP.md](SETUP.md) walks through creating both accounts, click by click,
including the quota that protects you from being charged. Read the Google
section before running anything against Google.

## Searching Google Maps through gosom

[gosom](https://github.com/gosom/google-maps-scraper) reads Google Maps without
an API key, so it gives ratings, review counts and a website field where Google
billing is not available. Automated reading of Google Maps may break Google's
terms, and Google can refuse a connection, so it is off by default and the
decision is yours.

On Windows its own build fails on the Chrome it starts, so run the Linux build
inside WSL. Put the binary in the distribution and turn it on in
`config.local.yaml`:

```yaml
gosom:
  enabled: true
  launcher: ["wsl", "-d", "Ubuntu-24.04", "--", "env", "DISABLE_TELEMETRY=1"]
  executable: "/home/you/gosom"
  work_dir: "D:/lead-finder-data/gosom"
  stop_command: ["wsl", "-d", "Ubuntu-24.04", "--", "pkill", "-9", "-f", "/home/you/gosom|ms-playwright"]
```

gosom can stay running after it finishes, so `stop_command` ends it once its
log says the work is done. Searches then use it first, and OpenStreetMap takes over if it finds nothing.
`--source gosom` asks for it alone. A website field that is really a Facebook
or Instagram page counts as no website and is kept as a contact. Businesses
marked closed are dropped, chains are marked in the `chain` column, and the
autopilot skips chains and anything under `autopilot.min_rating` or
`autopilot.min_reviews`. A rerun replaces an older row with the same phone
number, so a business found by both sources appears once.

## Finding a way to reach each business

Every search looks for contacts in two ways.

For a business with a poor website, it reads the home page and the contact and
about pages from `contacts.contact_paths`, and keeps emails and Instagram and
Facebook links. This needs no key.

For a business with no website, the autopilot runs one web search through
[Firecrawl](https://www.firecrawl.dev/), once `FIRECRAWL_API_KEY` is in `.env`.
It happens only for a business the autopilot is about to build, so a plain
search spends nothing. A result counts only when it names the business. A domain
carrying the business's name turns it into a business with a website, which is
the check that catches a wrong "no website", and the autopilot moves on to the
next one. Answers are kept in `data/contact_cache.json` for
`contacts.cache_days`. Calls stop at `contacts.max_searches_per_run` per run and
`contacts.monthly_search_limit` per month, counted in `data/search_usage.json`
and set below the free plan. Facebook and Instagram are never opened by the
tool: only the search result is read.

A website that refuses a script, with a 403 or a dropped connection, is not
called dead. It stays unaudited, because Cloudflare answers that way for sites
that work fine, and telling an owner their working site is down loses the deal.

## Publishing and the night shift

With `publish.enabled` on and `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`
in `.env`, finished sites go to one Cloudflare Pages project, each at
`/business-name-city/`. The upload holds only the site and the photographs it
uses, never `brief.md` or `outreach.md`. Every page carries `noindex` and a bar
saying it is a demo and not the official website, and the link replaces
`[link to the demo site]` in the messages. `scripts/publish_site.py` publishes
what is waiting.

`scripts/night_shift.py` repeats search, pick, build and publish with a new city
and trade each time, until `night.hours` or `night.max_sites`. It pauses
`night.pause_minutes` between searches, waits for the five hour Claude limit at
`night.pause_at_five_hour`, ends at `night.stop_at_weekly`, and gives up after
`night.give_up_after_failures` failed searches. It keeps the computer awake.
Stop it with Ctrl-C, or by creating `data/autopilot/STOP`.

It never sends anything. `http://localhost:5000/ready` lists what is waiting,
with the demo link, the ways to reach each business and the messages.

## Adding your details for the outreach messages

The messages say who you are, sign off with your name, and link to websites you
have built, when you have any. Put those in `config.yaml`, under `outreach`:

```yaml
outreach:
  sender_name: "Your Name"
  sender_about: "a computer science student from Serbia"
  postal_address: ""
  portfolio_links:
    - url: "https://a-site-you-built.example/"
      what: "cafe, warm and quiet, one page"
```

Every link in that list goes into every message. The `what` line decides the
order they appear in, so a grill owner reads the grill site before the bakery,
and it doubles as the label next to each link. With an empty list, the message
leaves previous work out.

The message also states a one time price. `scripts/pricing.py` works it out from
`outreach.pricing`: a price for the trade, a little more for a business with many
reviews, kept between `floor` and `ceiling`. `outreach.offer_includes` says what
the price covers. Cold email to the United States needs a postal address, so
fill in `postal_address` before sending any.

Those two are yours rather than the project's, so there is a second place for
them: create `config.local.yaml` next to `config.yaml` and put them there
instead. It is laid over the public settings when the tool starts and is
ignored by Git, so a `git pull` never collides with your name and a push never
carries it.

If you will never update this project or share the folder, `config.yaml` is
fine and this file is not needed. [SETUP.md](SETUP.md#3-your-own-details)
covers it in full.

## Using it

### Searching from the terminal

```bash
./run scripts/find_leads.py "bakery Novi Sad"
./run scripts/find_leads.py "dentist Berlin" --limit 60
```

Add `--no-audit` to skip checking existing websites, which makes a search much
faster when you only want to see whether a place is worth searching at all.

The first words name the kind of business and the last ones the place. Without
a Google key, the kind is looked up in `osm_categories` in `config.yaml`, and it
does not matter whether you type it in Latin or Cyrillic, or with or without
č, ć, š, ž and đ: `pekara`, `пекара` and `kafić` each find every bakery or cafe
in that place. A word that is not on the list searches business names instead.

### Checking one website on its own

```bash
./run scripts/audit_site.py example.com
```

You get a score out of 100 and a list of problems written as sentences you can
quote to the owner.

### The table in your browser

```bash
./run app.py
```

Then open `http://localhost:5000`. This runs entirely on your own computer.
Nothing is published and no one else can reach it.

On macOS, port 5000 is also where AirPlay Receiver listens. If the page refuses
to load, or starting it fails with `Address already in use`, turn AirPlay
Receiver off in System Settings, under General, AirDrop & Handoff.

The page has three tabs. **Leads** is the table described here, and
**Autopilot** and **Settings** are covered
[further down](#autopilot-one-city-start-to-finish).

The Leads tab shows your results as a table you can sort by clicking any
column. You can filter to businesses without a website, set a minimum rating or
review count, and set a status on each row, which is saved the moment you
choose it.
Each row links to the business on the map, to its website if it has one, and to
a search for its owner: the CompanyWall register for a business in Serbia, a
plain web search anywhere else. `contact_search` in `config.yaml` holds both.

### Preparing a website

The commands below are Claude Code commands. You type them in a Claude Code
session opened inside this folder.

They live in `commands/`, which Claude Code does not read on its own, so link
them into `.claude/commands/` once after cloning. From the project folder on
macOS and Linux:

```bash
mkdir -p .claude/commands
for f in commands/*.md; do ln -s "../../$f" .claude/commands/; done
```

That folder is ignored by Git. Because these are links and not copies, an
update that changes a command changes it here too. Open a new session
afterwards so the commands are picked up.

On Windows a link needs Developer Mode or an administrator prompt. Without
either, copy the files instead, and copy them again after each update:

```
mkdir .claude\commands
copy commands\*.md .claude\commands\
```

`.claude-plugin/plugin.json` describes the same folder as a Claude Code plugin:
its name, version, author and licence. Nothing above depends on it. It only
matters if the project is ever installed as a plugin, in which case Claude Code
reads the commands from `commands/` itself and the link step is not needed.

```
/build-brief <place_id or business name>
```

Looks the business up on the map and on its social pages, asks you a handful of
questions about it, including the colours it already uses and whether you have
gathered any of its own photographs, collects what is missing from Pexels, and
creates a folder containing `brief.md`, an `assets` folder, and an empty `site`
folder.

That folder lands on your Desktop. To keep client work somewhere else, set
`brief.output_dir`, in `config.local.yaml` if the path is personal to you, as
[SETUP.md](SETUP.md#3-your-own-details) explains:

```yaml
brief:
  output_dir: "~/Developer/sites"
```

The `~` is expanded, and the folder is created if it does not exist.

```
/build-site "Business Name"
```

Reads that brief, builds the website into `site`, then serves it and checks it
at phone width and desktop width before telling you it is done.

```
/draft-outreach <place_id or name>
```

Shows you who is overdue a follow up, then writes the three versions of the
message for the business you named.

The button labelled "Create brief" next to each row in the browser copies the
first command for you, already filled in with the right business.

```
/autopilot <place_id or business name>
```

Does all three for one business without asking anything, using the answers
saved on the Settings page. The autopilot below runs it for you; you only type
it yourself when the autopilot asks you to paste it.

### Autopilot: one city, start to finish

The **Autopilot** tab does the whole job for a city:

1. You type a city, or press **Random city**, and optionally a trade. Leave the
   trade empty and it picks one from the trades ticked in the settings.
2. It searches that city, and takes the best few businesses that fit the
   settings: not contacted before, not built before, by default without a
   website and with a phone number to send the message to.
3. For each one it downloads stock photographs, then has Claude Code write the
   brief, build the site, check it, and draft the three messages, all with the
   answers from the **Settings** tab instead of questions. Several businesses
   are built at the same time, three by default.
4. Each business then shows a link that opens its site, the folder it is in,
   the three messages with a copy button each, and the ways to reach it.
5. You read the message, send it from your own account, and press **I sent it**
   with the channel you used. That logs it exactly as `outreach.py --sent` does,
   so the follow up reminder works the same.

**Stop** ends a run at any point, the search included. A search already sent
to the map server still finishes on its own, and its businesses appear on the
Leads tab.

The manual way stays exactly as it was. The Leads tab, the questions
`/build-brief` asks and the other commands are untouched by any of this.

**Random cities** come from `autopilot.cities` in `config.yaml`: cities whose
urban area holds about a million people or more, each with its country and the
language its sites are written in. The Settings tab says whether the random
choice comes from the United States, from English-speaking countries, from
Europe or from the whole list. You can also type any city by hand; one the list
does not know gets its site language decided while the brief is written.

**The Settings tab** holds the answers `/build-brief` would otherwise ask for:
the FAQ and careers sections, the rating, the animations, AI images, the site
language and the stack, plus how many sites a run makes, how many of them are
built at the same time, and what counts as a fit. They are saved to
`data/autopilot_settings.json` on your computer and laid over the defaults in
`config.yaml`. The page shows your sender name and how many portfolio links the
messages carry, which still come from `config.local.yaml`.

**Claude Code has to be logged in for the building.** The searching and the
photographs are plain Python, but the brief, the site and the messages need
judgement, so the page starts Claude Code for each business in the background.
It looks for it on its own, including the copy inside the Claude desktop app.
Log it in once: open Terminal, run `claude`, or the path the Settings page
shows, type `/login`, and follow the browser. **Check Claude Code** on the
Settings page then tells you whether it answers.
[SETUP.md](SETUP.md#4-claude-code-for-the-autopilot) walks through it.

Until it does, a run stops after the photographs and shows one command per
business, `/autopilot` followed by its `place_id`. Paste it into a Claude Code
session in this folder and it does the rest without asking, and the page picks
up the site and the messages when it is done.

What Claude Code may do while it runs on its own is fixed in advance: read
files, write inside the folder the sites go into and inside `data/autopilot`,
and run this project's Python scripts. Everything else is refused, and it has
no web access. That is why `scripts/add_gsap.py` brings in a local copy of GSAP
when the animations are on. Each site it builds goes through
`scripts/check_site.py`, which checks the title, the description, the viewport,
one `<h1>`, the structured data, every image path and alt text, and that no
lorem ipsum is left.

**Watching it work.** While a site is being built, its card shows what Claude
Code is doing at that moment, the step count and the model. Once it is done,
the card says which model built it, how many minutes of work it took, and gives
the command that opens that Claude Code session in a terminal, so you can keep
working on the site there, for example to change the colours. These sessions do
not show in the Claude desktop app's sidebar, which only lists sessions the app
started itself. The run also shows how much of your Claude plan's five-hour and
weekly limits is used.

**Reaching the business.** Under the messages, each business lists every way
to contact it that is known: a phone call, WhatsApp with the short message
already typed in, Viber, an email link with the subject and text filled in, and
its Instagram, Facebook, website and Google Maps listing. The email, Instagram
and Facebook come from OpenStreetMap, which has them for some businesses. Where
one is missing, a link searches the web for it. Every link only opens the app;
nothing is sent until you press send there yourself.

While a run is going on a Mac or on Windows, the computer is kept awake, so a
locked screen does not stall it. Closing a laptop lid can still put it to sleep.

**What a run costs.** Each site is one full Claude Code session, which comes
out of your Claude plan's usage the same way typing the commands yourself
would, and takes several minutes. Building several at once uses no more in
total, it only uses it sooner, so a plan near its five-hour limit can run out
in the middle of a run. **Sites per run** and **Sites built at the same time**
on the Settings page keep that in hand. Pexels costs four to eight calls per
business, as always.

The same runs from a terminal:

```bash
./run scripts/autopilot.py run --random
./run scripts/autopilot.py run --city Chicago --trade bakery
./run scripts/autopilot.py run --random --no-build
```

`--no-build` stops after the photographs and prints the `/autopilot` command
for each business, which is what happens anyway when Claude Code is not
logged in.

### Keeping track of who you contacted

Nothing is recorded when a message is drafted, because drafting is not sending.
Once you have actually sent one, record it:

```bash
./run scripts/outreach.py --sent "Business Name" --channel email
```

The business can be given by its name or by its `place_id`. If two businesses
share the name, the command says so and asks for the `place_id` instead.
`--channel` is one of `email`, `viber`, `whatsapp` or `instagram`, the list kept
in `outreach.channels` in `config.yaml`.

When a reply comes in:

```bash
./run scripts/outreach.py --answered "Business Name" --response interested
```

`--response` is `interested`, `declined` or `"no answer"`. To list everyone who
has not replied within `outreach.follow_up_days` of being contacted, four days
by default:

```bash
./run scripts/outreach.py --due
```

The record lives in `data/outreach.csv`.

## Where your results are kept

Every search writes a file into the `data` folder, named after what you
searched for, for example `data/leads_bakery-novi-sad.csv`. Cyrillic is spelled
out in Latin for the name, so `пекара Нови Сад` and `pekara Novi Sad` are the
same search and share one file.

The last three columns, `email`, `instagram` and `facebook`, are filled from
OpenStreetMap where the map has them. Files from before those columns existed
still open, and gain them the next time they are saved.

That file is the database. There is no database.

A `.csv` file is a plain table that opens in Excel, in Google Sheets, or in any
text editor. Run the same search again a month later and the tool updates the
existing file rather than replacing it: business details are refreshed, and
anything you typed by hand is left exactly as you wrote it. That covers the
status, and the address, phone, opening hours, rating and review count where
the source has none of its own to offer.

### What `place_id` is

Every business in your results carries a `place_id`. That is the identifier the
data source uses for that one particular business. From Google it looks like
`ChIJN1t_tDeuEmsRUsoyG83frY4`. From OpenStreetMap it looks like
`osm:node/4031258789`.

It exists because names are not reliable. Three businesses in the same city can
all be called Caribic. The same business can be spelled two different ways a
month apart, because a volunteer corrected the map. Addresses are often missing
altogether.

The identifier is what lets the tool run the same search again next month and
recognise that a row is the same business as before, so it can refresh the score
while leaving what you typed by hand exactly as it was. Without it, a business
whose name had been corrected would come back as a second row and you would
contact the same owner twice.

You never have to type it or read it. You only copy it when a command asks for
one, and the "Create brief" button next to each row does that for you.

### Why a plain file instead of a real database

A database is worth its complexity when several people write to it at once, when
there are hundreds of thousands of records, or when you need to ask complicated
questions of the data. None of that applies here. You are one person, on one
computer, with a few thousand rows at most.

What a plain file gives you instead:

- You can open it and read it. When something looks wrong, you see it with your
  own eyes rather than needing a program to look for you.
- You can edit it by hand. The status column is meant to be typed into, and a
  spreadsheet is the natural place to do that.
- Backing up is copying a file. Sending your results to someone is sending a
  file.
- There is nothing to install, nothing to start, and nothing to migrate when a
  column is added.

The honest drawbacks: if you leave the file open in Excel, Windows locks it and
the tool cannot write, so it will tell you to close Excel and try again. And
everything in the file is text, so the code converts numbers on the way in and
out.

If this ever grows past ten thousand businesses, or two people start using it at
once, a database becomes the right answer. Until then it would be solving a
problem you do not have.

## Costs and staying inside the free allowance

Pexels is free with no card involved.

Google is different and deserves care. Google will not answer at all until you
have added a card, and there is no way around that. What protects you is a
quota.

The tool asks Google for phone numbers, ratings and review counts. Those are
Google's more expensive fields, which puts each search in the tier with the
smallest free monthly allowance, around 1,000 calls per month. This project
therefore stops itself at 900 calls per month, counted in `data/usage.json`.

That counter is your second line of defence, not your first. Set a daily quota
in the Google Cloud Console as well, following
[SETUP.md](SETUP.md#2-google-cloud--places-api-new). Only the quota can actually
refuse a call. The counter in this tool can only stop this tool, and a budget
alert emails you without stopping anything.

For scale, one search that pulls its full results costs 3 calls and returns up to
60 businesses, so 900 calls is roughly 300 full searches a month.

## Things it will not do, on purpose

**It never sends a message.** It writes drafts, and you send them yourself from
your own account. The project holds no password, token or login for email,
Viber, WhatsApp or Instagram, and it should never be given one. You log a
message as sent after you have actually sent it. The autopilot is no exception:
it stops at the drafted message, and only your **I sent it** logs anything.

**Google's photographs never end up on a website you build.** Those pictures
belong to the owners and the customers who took them. The tool never downloads
them at all: to see what a place looks like, it gives you a link to open, the
same as everywhere else. Every image that goes on a site comes from Pexels or
from the client.

**Nothing is scraped by default.** The company register never is, and the tool
builds links for a human to click. The one exception is gosom, below, which
reads Google Maps and stays off until you turn it on yourself.

**Google's terms allow their data to be kept for 30 days at most**, with one
exception: the `place_id`, the identifier of a business, may be kept forever.
Treat the files in `data` as a working copy, not an archive.

## Using it with something other than Claude Code

Most of this project has nothing to do with any assistant.

Every Python script is an ordinary command line program. Searching, ranking,
checking websites, downloading photographs, sorting images, the record of who
you contacted, and the whole browser interface all run on their own. You can use
them from a plain terminal with no assistant at all.

What remains are the places where judgement is needed: describing what a place
looks like, saying what is in a photograph the owner took, writing the website,
and writing the message. Those are the Claude Code commands. The autopilot runs
everything else on its own, and with `--no-build` it needs no assistant at all.

If you use a different assistant, `CLAUDE.md` in this folder holds the project
rules, and the files under `commands` hold the procedures. Both are plain
English. Hand them to your assistant and it can follow them.

## Licence

MIT. See [LICENSE](LICENSE).

Photographs downloaded from Pexels through this tool stay under the Pexels
licence. Each such folder ships a `sources.json` naming the photographer and
linking the page the photograph came from. Photographs a business supplies
remain theirs.

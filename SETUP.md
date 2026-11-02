# SETUP — accounts and API keys

This guide walks through everything you need before the tool works. It is
written for someone opening the Google Cloud Console for the first time.

Keys go into a `.env` file and nowhere else. That file never reaches GitHub.

There are two accounts to make, Pexels and Google Cloud, then one file holding
your own details, one optional login for the autopilot, and one optional token
for publishing the sites. Start with Pexels, which takes two minutes and
carries no risk at all.

---

## Terms used throughout

- **API** — the door one program knocks on to ask another program for data.
  This tool asks Google for "pizzerias in Novi Sad" through an API.
- **API key** — a long string that proves the request is yours. Treat it like a
  password: whoever holds it spends on your account.
- **`.env` file** — a plain text file holding your keys. The program reads it,
  and `.gitignore` keeps it off GitHub.
- **Quota** — a ceiling on how many calls per day you are allowed. Once hit,
  Google rejects further calls instead of billing you.
- **Billing account** — your card, linked to Google.

---

## 1. Pexels — photos for the generated sites

### What it does

Pexels hosts free photographs under a licence that allows commercial use
without mandatory attribution, so those images can go straight onto a client
demo site.

**Without it:** demo sites have no images, or you hunt for them by hand for
every business. Google's own photographs are not an alternative: they belong to
the owners and the customers who took them, and this tool never fetches them at
all. What it does give you is a link to the listing, to open and look at.

The business's own photographs are the other way in, and the better one. Save a
few from their Instagram or Facebook page into a folder and `/build-brief` will
take them, falling back to Pexels only for what they did not supply.

### Cost

Free, no card anywhere. Limits are 200 calls per hour and 20,000 per month.
One business consumes four to eight: one search per purpose, and a second for
any purpose the first did not fill. No paid tier exists, so accidental charges
are not possible.

### Steps

1. Open **https://www.pexels.com/join/** and register.
2. Open **https://www.pexels.com/api/** and click **"Get Started"**.
3. Fill the short form:
   - **Project Category** → whichever honestly describes your use. Demo sites
     sent to businesses you hope to win as clients are commercial work, not
     personal use.
   - **Explain briefly how and where you want to integrate our photos** →
     `Finds stock photos for demo websites I build for local businesses.`
   - **URL** → optional, leave it empty if you have no site yet
4. Tick the terms checkbox and click **"Generate API Key"**.
5. The key appears immediately and stays available at
   **https://www.pexels.com/api/key/**.

### Where it goes

In `.env`, on the line `PEXELS_API_KEY=`. If that file does not exist yet,
[Creating the `.env` file](#creating-the-env-file) at the end of section 2 shows
how.

---

## 2. Google Cloud — Places API (New)

The longest part, and the only one that carries any cost risk. Read it through
before clicking.

### What it does

Places API is the richer source of business data: name, address, rating, review
count, phone, and most importantly **whether the business has a website**. The
ratings and review counts are what make the ranking fine grained.

**Without it:** the tool falls back to OpenStreetMap, which is free and needs
no key, but has no ratings and no review counts. Two of the five scoring rules
stop working, so you cannot tell a bakery with 300 reviews and a 4.7 rating
(an ideal client) from one with 4 reviews (probably dead).

### Cost

**Partly free, and this needs care.**

Google requires a linked card before it allows any Maps Platform call. There is
no way around that. However:

- A free monthly allowance resets on the first of each month.
- Google bills by **the most expensive field you request**. This tool asks for
  phone, rating and review count, which are Enterprise-tier fields, so each
  Text Search call lands in the tier with the smallest free allowance —
  **1,000 calls per month**.
- The limit inside the tool is therefore **900 calls**, deliberately below it.

In practice: one call returns up to 20 businesses, and Google caps a single
query at three pages, so one fully paginated search costs 3 calls and returns
up to 60 businesses. 900 calls is roughly 300 such searches per month.

> Google changes these numbers from time to time. Check the current figures at
> **https://mapsplatform.google.com/pricing/**

### Three independent brakes

1. **A quota in the Cloud Console** (steps 7 and 8) — Google physically refuses
   calls past the ceiling. This is the only brake that actually stops spending.
2. **The counter in this tool** — tracked in `data/usage.json`, stops at 900.
3. **A budget alert** (step 9) — ⚠️ **emails you, stops nothing.** Never rely
   on it alone.

### Steps

**1. Open the console** — **https://console.cloud.google.com/**, sign in, and
accept the Terms of Service with **"AGREE AND CONTINUE"**.

If you are blocked with *Google Cloud access blocked*, Google now requires
2-step verification on the account. Click **"Enable MFA"**, turn on 2-Step
Verification, wait two minutes, and refresh.

**2. Create a project** (a drawer holding your key and quotas)
- Top bar, project dropdown left of the search box → **"NEW PROJECT"**
- **Project name:** `lead-finder-site-builder`, organization left as
  `No organization`
- **"CREATE"**, wait 10–20 seconds
- Reopen the dropdown and **select `lead-finder-site-builder`**. Confirm its name
  shows in the top bar before continuing.

**3. Link a card**
- ☰ **Navigation menu** → **"Billing"** → **"LINK A BILLING ACCOUNT"** →
  **"CREATE BILLING ACCOUNT"**
- Country, then **Account type: Individual**
- Name, address, card. Google places a verification hold of about one unit of
  currency and releases it within days. It is not a charge.
- **"START MY FREE TRIAL"** / **"SUBMIT AND ENABLE BILLING"**

If the payment step offers only *Profile type: Organization*, or shows *Cannot
create another individual profile for the same country*, do not fill in the
Organization form. An organization profile is a business profile, and Google
does not let the type be changed once the profile exists.

That screen can mean self-serve billing is not available for your country at
all, and no browser, profile or account change gets past it. For Serbia, Google
Cloud Support confirmed exactly this in September 2026: an account there has to
be set up through an authorised Google Cloud partner or reseller, listed by
region in the Google Cloud Partner Directory.

Nothing in this tool stops working in the meantime. Leave `GOOGLE_MAPS_API_KEY`
empty and searches run on OpenStreetMap.

**4. Enable the API** — ⚠️ two similar names exist
- ☰ → **"APIs & Services"** → **"Library"** → search `Places API`
- Open the card reading exactly **"Places API (New)"**, not the older
  **"Places API"**
- Click **"ENABLE"**

**5. Create the key**
- ☰ → **"APIs & Services"** → **"Credentials"**
- **"+ CREATE CREDENTIALS"** → **"API key"**
- Copy it into `.env` right away, then click **"Edit API key"**

**6. Restrict the key**
- **Name:** `lead-finder-key`
- **Application restrictions:** leave **"None"**. *IP addresses* looks safer but
  a home IP changes and the script would break every other day.
- **API restrictions:** **"Restrict key"** → tick **only "Places API (New)"**,
  so a leaked key cannot reach any other Google service
- **"SAVE"**

**7. Set the quota — the most important step here**

Everything else is convenience. This is the only thing standing between you and
a bill if code loops and fires 50,000 calls.

- ☰ → **"Google Maps Platform"** → **"Quotas"**
  (direct link: **https://console.cloud.google.com/google/maps-apis/quotas**)
- **API** dropdown → **"Places API (New)"**
- **"Quotas"** tab → find a row containing **"per day"**, preferring one that
  mentions **Text Search**
- Tick it, click the **pencil**, enter **`29`**, **"SAVE"**

29 per day allows 9 fully paginated searches daily. Even in a 31 day month that
is at most 899 calls, below the tool's own 900 and below Google's free 1,000, so
the quota holds on its own even if the counter in this tool is lost or bypassed.

**8. If that screen will not let you edit**
- ☰ → **"APIs & Services"** → **"Enabled APIs & services"** →
  **"Places API (New)"** → **"Quotas & System Limits"**
- Filter for `per day`, tick the row, pencil, `29`, **SAVE**

**9. Budget alert**
- ☰ → **"Billing"** → **"Budgets & alerts"** → **"CREATE BUDGET"**
- Name `lead-finder-alarm`, project `lead-finder-site-builder`
- **Budget type:** *Specified amount*, **Target amount:** `1`
- Thresholds 50/90/100%, email to your account, **"FINISH"**

### Where it goes

In `.env`, on the line `GOOGLE_MAPS_API_KEY=`

### Creating the `.env` file

From the project folder, on macOS and Linux:

```bash
cp .env.example .env
open -e .env
```

`open -e` is macOS. On Linux use whatever editor you have, for example
`nano .env`.

On Windows, in PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Paste the keys after the `=` signs, no quotes and no spaces:

```
GOOGLE_MAPS_API_KEY=AIzaSyC3xK9...
PEXELS_API_KEY=563492ad6f91...
```

`.env` is already in `.gitignore`. The Google key is not required to start;
without it the tool runs on OpenStreetMap.

---

## 3. Your own details

The two keys above are what the tool needs. This last part is what it needs to
write in your name.

### What it is

`config.yaml` holds the project's settings and is public. Two of them are
yours rather than the project's: the name the outreach messages sign off with,
and the links to work you have built. It ships with both empty.

`config.local.yaml` is a file you create, in the project folder, next to
`config.yaml`. Anything in it is laid over the public settings when the tool
starts. It is in `.gitignore`, so it never leaves your computer.

### What goes in it

Only what you are changing. Everything else keeps the public value.

```yaml
outreach:
  sender_name: "Your Name"
  portfolio_links:
    - url: "https://a-site-you-built.example/"
      what: "cafe, warm and quiet, one page"
    - url: "https://another.example/"
      what: "grill house, dark, big photographs"

brief:
  default_language: "Serbian"
  output_dir: "~/Sites"
```

The `what` line is read, not decoration: it orders the links so the closest
trade goes first, and labels each one in the message.

### Do you need it

If you cloned this once and will never update it or share it, no. Put your
details straight into `config.yaml` and nothing will go wrong.

You want it the moment either of these becomes true:

- **You run `git pull` to get improvements.** With your name inside
  `config.yaml`, a pull that touches that file stops and asks you to deal with
  your own edit first. With a local file, pulls never touch what is yours.
- **You fork, push, or hand the folder to someone.** `config.yaml` is tracked
  by Git, so your name, your links and your paths travel with it.

Both files may exist at once. The local one wins wherever they overlap.

---

## 4. Claude Code for the autopilot

Optional. Skip it and the autopilot still searches, picks the businesses and
downloads the photographs, then hands you one command per business to paste into
Claude Code.

### What it is for

The autopilot in the browser builds each site by starting Claude Code in the
background, with no window and nobody answering questions. That works only when
Claude Code on this computer is logged in to your Claude account. The Claude
desktop app being logged in is not enough: the copy the autopilot starts keeps
its own login.

### Steps

1. Open the browser page, go to **Settings**, and look under **Claude Code**. It
   says where Claude Code was found. On a Mac with the Claude desktop app it
   usually finds the copy inside the app, with a long path ending in
   `claude.app/Contents/MacOS/claude`.
2. If nothing was found, install Claude Code for the terminal from
   **https://claude.com/claude-code**, then reload the page.
3. Open Terminal and run that path in quotes, or just `claude` if you installed
   it. It opens an interactive session.
4. Type `/login` and follow the browser that opens. Then type `/exit`.
5. Back on the Settings page, press **Check Claude Code**. It asks Claude Code
   for one word, which uses a very small part of your Claude usage, and says
   whether it is ready.

### Cost

Nothing extra to sign up for. Every site the autopilot builds is a full Claude
Code session counted against your Claude plan, the same as typing the commands
yourself, so **Sites per run** on the Settings page is the number to keep an
eye on.

---

## 5. Cloudflare Pages for publishing the sites

Optional. Skip it and every site stays on your computer, and the messages carry
no link to it.

### What it does

Each finished site goes online at an address such as
`golden-crust-chicago.pages.dev`, and that address goes into the messages, so
the owner opens the demo with one tap. Every business gets its own Pages
project, and publishing again after a change keeps the same address.

### Cost

Free, and Cloudflare's free plan carries no non-commercial clause, so demo
sites for businesses you hope to win as clients are fine on it. The limits that
matter here: 100 projects per account, 20,000 files per site and 25 MiB per
file. One business is one project, so after a hundred of them, delete the
projects of businesses that said no, in the dashboard under **Workers &
Pages**.

### Steps

1. Sign up at **https://dash.cloudflare.com/sign-up**.
2. Open **https://dash.cloudflare.com/profile/api-tokens** and click **Create
   Token**, then **Create Custom Token**.
3. **Token name:** `lead-finder`.
4. **Permissions:** *Account*, *Cloudflare Pages*, *Edit*.
5. **Account Resources:** *Include*, then your account.
6. **Continue to summary**, then **Create Token**, and copy it straight away.
   Cloudflare shows it once.
7. Paste it into `.env` after `CLOUDFLARE_API_TOKEN=`.
8. Leave `CLOUDFLARE_ACCOUNT_ID=` empty: the script finds the account on its own
   when the token sees only one. If it says it sees several, copy the **Account
   ID** shown on the right of **Workers & Pages** into that line.

The **Publishing** panel on the Settings page then says the token is set.

### Who can open the sites

Everyone. Pages publishes with no login in front of the site. A brand new
project's address can take a minute or two to start answering, so the script
waits for it, and when it still does not open in time, publishing the same
folder again a few minutes later picks it up.

---
description: Draft the three outreach messages for one lead
argument-hint: <place_id or business name>
allowed-tools: Bash, Read, Glob
---

Draft the messages for `$1`. You write them. You never send them, and this
project holds no credentials for any messaging account. That is deliberate.

`{venv python}` below is the Python inside `venv`: `venv/bin/python` on macOS and
Linux, `venv/Scripts/python.exe` on Windows. Check which of the two exists in the
project folder and use that one. Never a bare `python`.

Substitute every `{...}` before running a command. Never paste one into a shell
as it stands.

## 1. Show what is outstanding first

```
{venv python} scripts/outreach.py --due
```

Report anyone waiting on a follow up before anything else, oldest first. If
`$1` is empty, stop there — the list was the point.

## 2. Gather the material

```
{venv python} scripts/build_brief.py "$1" --info
```

Read the business folder if it exists. It is named after the business and sits
in `brief.output_dir` from `config.yaml`, which a `config.local.yaml` may
override, or on the Desktop when that is empty. From it, read `brief.md` for the
style, the sections and what the photographs show, and `site/` to see whether
the site is actually built. Never claim a site is ready when `site/` is empty.

The brief marks each photograph as stock or the business's own. That decides
what the message may say about them, so read it before writing point 4 below.

Read `outreach.sender_name` and `outreach.portfolio_links` from `config.yaml`,
which a `config.local.yaml` may override. Those two are personal, so that is
where they usually are, and `config.yaml` ships them empty. Read both files
before deciding either is missing.

If the sender name really is empty, say so and ask, rather than signing with a
made up name. If there are no portfolio links, leave previous work out of the
message altogether: never apologise for it, and never invent any.

Send every link in the list, in all three versions. Do not drop one for being
off trade and do not hold any back.

Each entry carries a `what` describing the kind of business it was built for.
That decides the order, not whether a link is sent: put the closest one to this
prospect first, so a grill owner reads the grill site before the bakery. Where
there is room, label each link with its `what` so the reader can tell them apart
without opening all of them.

## 3. Write three versions

All three in the language the brief names under **Site language**.

Every version must carry these things:

1. **Who is writing.** The sender is `outreach.sender_name`, described by
   `outreach.sender_about`. Say it in the opening words, in plain language, so
   nobody wonders who this is. In the email, sign with the full name. In the two
   short versions, sign with the first name only.
2. **One concrete detail about that specific business.** What they are known
   for, the products customers mention, the neighbourhood. `brief.md` holds these
   under "What is known about the business". Name the real thing, such as their
   egg tarts, and never quote a customer. Generic praise reads as a mail merge
   and gets deleted.
3. **The site already exists and costs nothing to look at**, with the link
   written exactly as `[link to the demo site]`. It is built, and looking at it
   commits them to nothing.
4. **The offer, in one plain sentence.** State the price and what it includes.
   The price comes from `scripts/autopilot.py prepare`, or from
   `outreach.pricing` in `config.yaml` when you draft by hand, and the contents
   from `outreach.offer_includes`. It is a one time price. Do not offer a
   discount, and do not write that they have to pay for looking.
5. **Links to previous work**, all of `outreach.portfolio_links`, only when
   there are any.
6. **That the stock photographs are temporary** and get swapped for their own as
   soon as they say they are interested. Never let them think a stock room is
   theirs. `brief.md` marks every photograph as either stock or the client's
   own: when the site uses their own, say that you used their pictures instead,
   and drop this point altogether when none of the images are stock.

The email also ends with a way out, one short line such as "If you would rather
not hear from me again, just say so and I won't write again", followed by
`outreach.postal_address` when that is filled in.

Tone: a student who builds sites, writing to a person. Relaxed, direct, no
corporate vocabulary, no "dear sir or madam", no "revolutionise your online
presence", no emoji storm. Short sentences. It should read like it was typed
once, not generated.

Never invent facts about the business: no fake compliments about food you have
not eaten, no numbers, no claims about their revenue or their competitors.

**Email** — subject line plus five to eight sentences. Enough room to explain
why they got the message.

**Viber or WhatsApp** — three or four sentences. No subject, no greeting
ceremony. Assume it is read on a phone between two other things.

**Instagram DM** — two or three sentences at most. The first line has to survive
being shown as a preview.

Those counts are the prose. The links sit under it as their own list and do not
count against them, which is what keeps a short message short while still
carrying all of them.

Print all three plainly so they can be copied.

## 4. Offer to log it

Do not log anything on your own, because writing a message is not sending it.
Tell them that once they have actually sent it, this records it and sets the
follow up:

```
{venv python} scripts/outreach.py --sent "{place_id}" --channel email
```

`--channel` is one of `outreach.channels` in `config.yaml`, which by default is
`email`, `viber`, `whatsapp` and `instagram`. The business can be given by its
name instead of its place_id, as long as no other business shares that name.

And when a reply arrives:

```
{venv python} scripts/outreach.py --answered "{place_id}" --response interested
```

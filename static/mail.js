const MAIL_POLL_MS = 15000;

const ANSWER_TAGS = {
  "": ["Waiting", "wait"],
  replied: ["Replied", "good"],
  opted_out: ["Said no", "bad"],
  bounced: ["Bounced", "bad"],
};

const INBOX_TAGS = {
  replied: ["Reply", "good"],
  opted_out: ["Said no", "bad"],
  bounced: ["Bounced", "bad"],
};

const KIND_LABELS = {
  first: "First email",
  follow_up: "Follow-up",
};

const mail = {
  on: false,
  open: new Set(),
  drafts: new Map(),
  timer: null,
};

const mailParts = {
  panel: document.getElementById("mailer"),
  title: document.getElementById("mail-title"),
  line: document.getElementById("mail-line"),
  now: document.getElementById("mail-now"),
  toggle: document.getElementById("mail-toggle"),
  today: document.getElementById("mail-today"),
  todayBar: document.getElementById("mail-today-bar"),
  next: document.getElementById("mail-next"),
  queued: document.getElementById("mail-queued"),
  answers: document.getElementById("mail-answers"),
  setup: document.getElementById("mail-setup"),
  inbox: document.getElementById("mail-inbox"),
  checked: document.getElementById("mail-checked"),
  check: document.getElementById("mail-check"),
  queue: document.getElementById("mail-queue"),
  queueNote: document.getElementById("mail-queue-note"),
  sent: document.getElementById("mail-sent"),
  sentNote: document.getElementById("mail-sent-note"),
  navReplies: document.getElementById("nav-replies"),
};

function postJson(url, body) {
  return requestJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function tag(label, tone) {
  return element("span", "mail-tag tone-" + tone, label);
}

function waitingReplies(data) {
  return data.inbox.filter((item) => item.kind === "replied" && !item.answered_at).length;
}

function sendingHours(data) {
  const days = data.weekdays_only ? "Monday to Friday" : "every day";
  return data.hours[0] + ":00 to " + data.hours[1] + ":00 in each business's own time, " + days;
}

function mailLine(data) {
  if (!data.set_up) return "The mailbox is not set up.";
  if (data.note) return data.note;
  if (data.sending_now) return "Sending now, up to today's limit, whatever the time is over there.";
  if (data.on) return "On. Emails go out " + sendingHours(data) + ".";
  return "Off. Turn it on and the drafted emails go out " + sendingHours(data) + ".";
}

function renderMailPanel(data) {
  const active = data.on || data.sending_now;
  mail.on = data.on;
  mailParts.panel.classList.toggle("is-on", active);
  mailParts.title.textContent = data.on ? "Automatic sending is on" : "Automatic sending is off";
  mailParts.line.textContent = mailLine(data);
  mailParts.toggle.textContent = data.on ? "Turn off" : "Turn on";
  mailParts.toggle.classList.toggle("is-stop", data.on);
  mailParts.toggle.disabled = !data.set_up;
  mailParts.now.disabled = !data.set_up || data.sending_now || data.today >= data.cap;
  mailParts.now.textContent = data.sending_now ? "Sending now" : "Send now";
  mailParts.today.textContent = data.today + " of " + data.cap;
  mailParts.todayBar.style.width = Math.min(100, Math.round((data.today / Math.max(1, data.cap)) * 100)) + "%";
  mailParts.next.textContent = data.next_at ? whenLabel(data.next_at) : active ? "Waiting" : "Off";
  mailParts.queued.textContent = data.counts.queue + (data.counts.follow_ups ? " + " + count(data.counts.follow_ups, "follow-up", "follow-ups") : "");
  mailParts.answers.textContent = data.counts.replied + " of " + data.counts.sent;

  const problems = [];
  if (!data.set_up) problems.push("Add ZOHO_SMTP_USER and ZOHO_SMTP_PASSWORD to .env, and the mail servers to config.local.yaml.");
  if (data.counts.without_email) {
    problems.push(count(data.counts.without_email, "ready site has", "ready sites have") + " no email address, so they stay on the Sites page for Viber, WhatsApp or Instagram.");
  }
  if (!data.demo_address) problems.push("The links still point to pages.dev. Set publish.address once your own demo domain works.");
  mailParts.setup.hidden = !problems.length;
  mailParts.setup.textContent = problems.join(" ");
}

function expandable(entry, key, head, detail) {
  const opened = mail.open.has(key);
  detail.hidden = !opened;
  head.setAttribute("aria-expanded", String(opened));
  head.addEventListener("click", () => {
    const open = detail.hidden;
    detail.hidden = !open;
    head.setAttribute("aria-expanded", String(open));
    if (open) {
      mail.open.add(key);
    } else {
      mail.open.delete(key);
    }
  });
  entry.append(head, detail);
  return entry;
}

function mailHead(title, lines, tags, when) {
  const head = element("button", "mail-head");
  head.type = "button";
  const text = element("span", "mail-text");
  text.append(element("strong", "", title));
  lines.filter(Boolean).forEach((line) => text.append(element("span", "", line)));
  const side = element("span", "mail-side");
  tags.forEach((item) => side.append(item));
  if (when) side.append(element("time", "mail-when", when));
  head.append(text, side);
  return head;
}

function replyBox(item) {
  const box = element("div", "mail-reply");
  const field = element("textarea");
  field.rows = 5;
  field.placeholder = "Write your answer. Your name and Clyx Studio go under it.";
  field.value = mail.drafts.get(item.uid) || "";
  field.addEventListener("input", () => mail.drafts.set(item.uid, field.value));
  const row = element("div", "mail-reply-row");
  const button = element("button", "", item.answered_at ? "Send another answer" : "Send answer");
  button.type = "button";
  const note = element("span", "status-line", item.answered_at ? "You answered " + whenLabel(item.answered_at) + "." : "");
  button.addEventListener("click", async () => {
    button.disabled = true;
    say(note, "Sending.");
    try {
      const data = await postJson("/api/mail/reply", { uid: item.uid, text: field.value });
      mail.drafts.delete(item.uid);
      renderMail(data);
    } catch (error) {
      say(note, error.message, true);
      button.disabled = false;
    }
  });
  row.append(button, note);
  box.append(field, row);
  return box;
}

function inboxEntry(item) {
  const entry = element("li", "mail-entry" + (item.kind === "replied" && !item.answered_at ? " is-new" : ""));
  const label = INBOX_TAGS[item.kind];
  const tags = label ? [tag(label[0], label[1])] : [];
  if (item.answered_at) tags.push(tag("Answered", "wait"));
  const head = mailHead(
    item.from_name || item.from_email,
    [item.business ? item.business + " · " + item.subject : item.subject],
    tags,
    whenLabel(item.date)
  );
  const detail = element("div", "mail-detail");
  detail.append(element("p", "hint", item.from_email), element("pre", "mail-body", item.text || "No text."));
  if (item.kind !== "bounced" && item.from_email) detail.append(replyBox(item));
  return expandable(entry, "in-" + item.uid, head, detail);
}

function queueEntry(item) {
  const entry = element("li", "mail-entry");
  const where = item.where ? item.where + (item.their_time ? ", " + item.their_time + " there" : "") : "";
  const head = mailHead(item.name, [item.email, where], [tag(KIND_LABELS[item.kind] || item.kind, item.kind === "first" ? "blue" : "wait")], "");
  const detail = element("div", "mail-detail");
  detail.append(element("p", "mail-subject", item.subject), element("pre", "mail-body", item.body));
  const row = element("div", "mail-reply-row");
  const skip = element("button", "secondary", "Do not send this one");
  skip.type = "button";
  const note = element("span", "status-line");
  skip.addEventListener("click", async () => {
    skip.disabled = true;
    try {
      renderMail(await postJson("/api/mail/skip", { place_id: item.place_id }));
    } catch (error) {
      say(note, error.message, true);
      skip.disabled = false;
    }
  });
  row.append(skip, note);
  detail.append(row);
  return expandable(entry, "queue-" + item.place_id + item.kind, head, detail);
}

function sentEntry(row) {
  const entry = element("li", "mail-entry mail-sent");
  const answer = ANSWER_TAGS[row.answer] || ANSWER_TAGS[""];
  const line = element("div", "mail-head is-static");
  const text = element("span", "mail-text");
  text.append(element("strong", "", row.name), element("span", "", row.email + " · " + (KIND_LABELS[row.kind] || row.kind)));
  const side = element("span", "mail-side");
  side.append(tag(row.kind === "first" ? answer[0] : "Sent", row.kind === "first" ? answer[1] : "wait"), element("time", "mail-when", whenLabel(row.sent_at)));
  line.append(text, side);
  entry.append(line);
  return entry;
}

function emptyItem(text) {
  return element("li", "attention-empty", text);
}

function renderMail(data) {
  renderMailPanel(data);
  const replies = waitingReplies(data);
  mailParts.navReplies.textContent = String(replies);
  mailParts.navReplies.hidden = !replies;

  mailParts.checked.textContent = data.checked_at ? "Checked " + whenLabel(data.checked_at) : "Not checked yet";
  mailParts.inbox.replaceChildren(...(data.inbox.length ? data.inbox.map(inboxEntry) : [emptyItem("No mail in the last 30 days.")]));

  mailParts.queueNote.textContent = count(data.counts.queue + data.counts.follow_ups, "email", "emails");
  mailParts.queue.replaceChildren(
    ...(data.queue.length ? data.queue.map(queueEntry) : [emptyItem("Nothing to send. Finished sites with an email join on their own.")])
  );

  const parts = [count(data.counts.sent, "business", "businesses")];
  if (data.counts.opted_out) parts.push(data.counts.opted_out + " said no");
  if (data.counts.bounced) parts.push(data.counts.bounced + " bounced");
  mailParts.sentNote.textContent = parts.join(", ");
  mailParts.sent.replaceChildren(...(data.sent.length ? data.sent.map(sentEntry) : [emptyItem("Nothing sent yet.")]));

  clearTimeout(mail.timer);
  if (board.view === "mail") mail.timer = setTimeout(() => loadMail(true), MAIL_POLL_MS);
}

async function loadMail(quietly) {
  const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#view-mail textarea");
  if (quietly && typing) {
    clearTimeout(mail.timer);
    mail.timer = setTimeout(() => loadMail(true), MAIL_POLL_MS);
    return;
  }
  try {
    renderMail(await requestJson("/api/mail"));
  } catch (error) {
    if (!quietly) mailParts.line.textContent = error.message;
  }
}

async function mailButton(button, url, body) {
  button.disabled = true;
  try {
    renderMail(await postJson(url, body));
  } catch (error) {
    mailParts.line.textContent = error.message;
    button.disabled = false;
  }
}

mailParts.toggle.addEventListener("click", () => {
  mailButton(mailParts.toggle, "/api/mail/switch", { on: !mail.on });
});
mailParts.now.addEventListener("click", () => mailButton(mailParts.now, "/api/mail/send-now"));
mailParts.check.addEventListener("click", async () => {
  mailParts.checked.textContent = "Checking.";
  await mailButton(mailParts.check, "/api/mail/check");
  mailParts.check.disabled = false;
});

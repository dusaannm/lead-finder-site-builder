const VIEWS = ["leads", "autopilot", "settings"];
const ACTIVE_RUN_STATES = ["searching", "building"];
const POLL_ACTIVE_MS = 3000;
const POLL_WAITING_MS = 10000;

const CANDIDATE_TEXT = {
  waiting: "Waiting its turn.",
  photos: "Downloading stock photographs.",
  building: "Claude Code is writing the brief, the site and the messages.",
  paste: "Photographs are ready. Paste this into Claude Code: it builds the site and writes the messages without asking anything, and this page shows them once it is done.",
  done: "Built and checked. Read the messages, send one, then mark it here.",
  attention: "Built, with problems to look at before sending anything:",
  failed: "Could not be prepared:",
  stopped: "Stopped before it was built.",
};

const LINKS_IN_PLACE = ["call", "email"];

const STATE_TAGS = {
  paste: "to paste",
  attention: "check it",
};

const autopilot = {
  data: null,
  runId: "",
  pollTimer: null,
};

const parts = {
  tabs: document.querySelectorAll(".tab"),
  form: document.getElementById("autopilot-form"),
  city: document.getElementById("autopilot-city"),
  random: document.getElementById("autopilot-random"),
  trade: document.getElementById("autopilot-trade"),
  start: document.getElementById("autopilot-start"),
  cityList: document.getElementById("autopilot-cities"),
  tradeList: document.getElementById("autopilot-trades"),
  status: document.getElementById("autopilot-status"),
  builderNote: document.getElementById("autopilot-builder"),
  runPanel: document.getElementById("run-panel"),
  runTitle: document.getElementById("run-title"),
  runMessage: document.getElementById("run-message"),
  runUsage: document.getElementById("run-usage"),
  runStop: document.getElementById("run-stop"),
  runCandidates: document.getElementById("run-candidates"),
  runSelect: document.getElementById("run-select"),
  settingsForm: document.getElementById("settings-form"),
  citiesFrom: document.getElementById("set-cities-from"),
  sites: document.getElementById("set-sites"),
  searchLimit: document.getElementById("set-search-limit"),
  noWebsite: document.getElementById("set-no-website"),
  phone: document.getElementById("set-phone"),
  online: document.getElementById("set-online"),
  rated: document.getElementById("set-rated"),
  minRating: document.getElementById("set-min-rating"),
  minReviews: document.getElementById("set-min-reviews"),
  trades: document.getElementById("set-trades"),
  faq: document.getElementById("set-faq"),
  careers: document.getElementById("set-careers"),
  reviews: document.getElementById("set-reviews"),
  animations: document.getElementById("set-animations"),
  ai: document.getElementById("set-ai"),
  language: document.getElementById("set-language"),
  stack: document.getElementById("set-stack"),
  style: document.getElementById("set-style"),
  command: document.getElementById("set-command"),
  model: document.getElementById("set-model"),
  timeout: document.getElementById("set-timeout"),
  parallel: document.getElementById("set-parallel"),
  builderState: document.getElementById("builder-state"),
  builderCheck: document.getElementById("builder-check"),
  senderState: document.getElementById("sender-state"),
  settingsStatus: document.getElementById("settings-status"),
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function say(target, text, isError) {
  target.textContent = text || "";
  target.classList.toggle("error", Boolean(isError));
}

async function copyText(text, button) {
  let copied = false;
  try {
    await navigator.clipboard.writeText(text);
    copied = true;
  } catch (error) {
    copied = legacyCopy(text);
  }
  const original = button.textContent;
  button.textContent = copied ? "Copied" : "Select and copy it";
  button.classList.toggle("copied", copied);
  setTimeout(() => {
    button.textContent = original;
    button.classList.remove("copied");
  }, 1600);
}

function showView(name) {
  const chosen = VIEWS.includes(name) ? name : "leads";
  VIEWS.forEach((view) => {
    document.getElementById("view-" + view).hidden = view !== chosen;
  });
  parts.tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === chosen);
    tab.setAttribute("aria-selected", String(tab.dataset.view === chosen));
  });
  if (chosen !== "leads" && !autopilot.data) {
    loadAutopilot();
  }
}

function fillOptions(select, entries, chosen) {
  select.innerHTML = "";
  entries.forEach(([value, label]) => {
    const option = element("option", "", label);
    option.value = value;
    select.append(option);
  });
  select.value = chosen;
}

function languageChoices(data) {
  const names = new Set(["English", data.default_language]);
  data.cities.forEach((city) => names.add(city.language));
  const current = data.settings.site.language;
  if (current.toLowerCase() !== "city") names.add(current);
  const sorted = [...names].filter(Boolean).sort();
  return [["city", "The city's own language"]].concat(sorted.map((name) => [name, name]));
}

function renderTrades(data) {
  parts.trades.innerHTML = "";
  const chosen = data.settings.trades.map((trade) => trade.toLowerCase());
  const every = [...new Set(data.trades.concat(data.settings.trades))].sort();
  every.forEach((trade) => {
    const label = element("label", "control checkbox");
    const box = element("input");
    box.type = "checkbox";
    box.value = trade;
    box.checked = chosen.includes(trade.toLowerCase());
    label.append(box, element("span", "", trade));
    parts.trades.append(label);
  });
}

function builderNote(data) {
  if (data.builder) {
    return "Sites are built by Claude Code at " + data.builder + ". If a run stops at the photographs, check it on the Settings page.";
  }
  return "No Claude Code was found, so each run stops after the photographs and gives you one command per business to paste into Claude Code.";
}

function senderNote(data) {
  const who = data.sender_about ? ", " + data.sender_about : "";
  const name = data.sender_name ? "Messages are signed " + data.sender_name + who : "No sender name is set, so messages are signed [your name]";
  const links = data.portfolio_links === 1 ? "1 portfolio link" : data.portfolio_links + " portfolio links";
  return name + ", with " + links + ". Both live in config.local.yaml under outreach.";
}

function renderSettings(data) {
  const settings = data.settings;
  fillOptions(parts.citiesFrom, Object.entries(data.regions), settings.cities_from);
  parts.sites.value = settings.sites_per_run;
  parts.searchLimit.value = settings.search_limit;
  parts.noWebsite.checked = settings.only_without_website;
  parts.phone.checked = settings.require_phone;
  parts.online.checked = settings.require_online_contact;
  parts.rated.checked = settings.only_rated;
  parts.minRating.value = settings.min_rating;
  parts.minReviews.value = settings.min_reviews;
  renderTrades(data);
  parts.faq.checked = settings.site.faq;
  parts.careers.checked = settings.site.careers;
  parts.reviews.checked = settings.site.show_reviews;
  parts.animations.checked = settings.site.animations;
  parts.ai.checked = settings.site.ai_media;
  fillOptions(parts.language, languageChoices(data), settings.site.language.toLowerCase() === "city" ? "city" : settings.site.language);
  fillOptions(parts.stack, Object.entries(data.stacks), settings.site.stack);
  parts.style.value = settings.site.style;
  parts.command.value = settings.builder.command;
  parts.model.value = settings.builder.model;
  parts.timeout.value = settings.builder.timeout_minutes;
  parts.parallel.value = settings.builder.parallel;
  parts.builderState.textContent = data.builder ? "Found at " + data.builder + "." : "Not found on this computer.";
  parts.senderState.textContent = senderNote(data);
}

function renderAutopilotForm(data) {
  parts.cityList.innerHTML = "";
  data.cities.forEach((city) => {
    const option = element("option");
    option.value = city.name;
    option.label = city.country + ", " + city.language;
    parts.cityList.append(option);
  });
  parts.tradeList.innerHTML = "";
  data.trades.forEach((trade) => {
    const option = element("option");
    option.value = trade;
    parts.tradeList.append(option);
  });
  parts.builderNote.textContent = builderNote(data);
}

async function loadAutopilot() {
  try {
    autopilot.data = await requestJson("/api/autopilot");
    renderSettings(autopilot.data);
    renderAutopilotForm(autopilot.data);
    await loadRuns(autopilot.data.running);
  } catch (error) {
    say(parts.status, error.message, true);
  }
}

function citiesFromSetting() {
  const data = autopilot.data;
  const region = data.settings.cities_from;
  return data.cities.filter((city) => {
    if (region === "us") return city.country === "United States";
    if (region === "english") return city.language === "English";
    if (region === "europe") return city.region === "europe";
    return true;
  });
}

function pickRandomCity() {
  const pool = citiesFromSetting();
  if (!pool.length) {
    say(parts.status, "The city list has nothing for this setting.", true);
    return;
  }
  const city = pool[Math.floor(Math.random() * pool.length)];
  parts.city.value = city.name;
  say(parts.status, city.name + ", " + city.country + ". Sites in " + siteLanguageFor(city) + ".");
}

function siteLanguageFor(city) {
  const chosen = autopilot.data.settings.site.language;
  if (chosen.toLowerCase() !== "city") return chosen;
  return city ? city.language : "the language spoken there";
}

function knownCity(text) {
  const wanted = text.trim().toLowerCase();
  return autopilot.data.cities.find((city) =>
    [city.name].concat(city.aliases || []).some((name) => name.toLowerCase() === wanted)
  );
}

async function startRun(event) {
  event.preventDefault();
  if (!autopilot.data) await loadAutopilot();
  const city = parts.city.value.trim();
  if (!city) {
    say(parts.status, "Type a city, or press Random city.", true);
    return;
  }
  parts.start.disabled = true;
  say(parts.status, "Starting.");
  try {
    const data = await requestJson("/api/autopilot/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city, trade: parts.trade.value.trim() }),
    });
    const match = knownCity(city);
    const fixed = autopilot.data.settings.site.language.toLowerCase() !== "city";
    say(
      parts.status,
      match || fixed
        ? "Sites in " + siteLanguageFor(match) + "."
        : city + " is not in the city list, so the site language is decided while each brief is written."
    );
    await loadRuns(data.id);
  } catch (error) {
    say(parts.status, error.message, true);
  } finally {
    parts.start.disabled = false;
  }
}

async function loadRuns(preferred) {
  const data = await requestJson("/api/autopilot/runs");
  parts.runSelect.innerHTML = "";
  if (!data.runs.length) {
    parts.runSelect.append(element("option", "", "no runs yet"));
    parts.runSelect.disabled = true;
    parts.runPanel.hidden = true;
    return;
  }
  parts.runSelect.disabled = false;
  data.runs.forEach((run) => {
    const option = element("option", "", runLabel(run));
    option.value = run.id;
    parts.runSelect.append(option);
  });
  const chosen = preferred || data.running || data.runs[0].id;
  parts.runSelect.value = chosen;
  await showRun(chosen);
}

function runLabel(run) {
  return run.started.replace("T", " ") + " · " + run.query + " · " + run.state;
}

function schedulePoll(run) {
  clearTimeout(autopilot.pollTimer);
  const active = ACTIVE_RUN_STATES.includes(run.state);
  const waiting = run.candidates.some((candidate) => candidate.state === "paste");
  const delay = active ? POLL_ACTIVE_MS : waiting ? POLL_WAITING_MS : 0;
  if (delay) {
    autopilot.pollTimer = setTimeout(() => showRun(run.id, true), delay);
  }
}

async function showRun(runId, quietly) {
  autopilot.runId = runId;
  try {
    const run = await requestJson("/api/autopilot/runs/" + encodeURIComponent(runId));
    if (run.id !== autopilot.runId) return;
    renderRun(run);
    schedulePoll(run);
  } catch (error) {
    if (!quietly) say(parts.status, error.message, true);
  }
}

function runTitle(run) {
  const city = run.city.country ? run.city.name + ", " + run.city.country : run.city.name;
  return run.trade + " in " + city;
}

function renderRun(run) {
  parts.runPanel.hidden = false;
  parts.runTitle.textContent = runTitle(run);
  const builderProblem = run.builder_problem ? " " + run.builder_problem + " Check it on the Settings page." : "";
  const label = run.state.charAt(0).toUpperCase() + run.state.slice(1);
  parts.runMessage.textContent = label + " · " + (run.message || "") + builderProblem;
  parts.runUsage.textContent = run.plan_usage || "";
  parts.runStop.hidden = !ACTIVE_RUN_STATES.includes(run.state);
  if (parts.runStop.hidden) {
    parts.runStop.disabled = false;
    parts.runStop.textContent = "Stop";
  }
  const listed = [...parts.runSelect.options].find((option) => option.value === run.id);
  if (listed) listed.textContent = runLabel(run);
  renderCards(run);
}

function renderCards(run) {
  const shown = [...parts.runCandidates.children];
  const sameList =
    shown.length === run.candidates.length &&
    shown.every((node, index) => node.dataset.key === run.id + " " + run.candidates[index].place_id);
  if (!sameList) {
    parts.runCandidates.innerHTML = "";
    run.candidates.forEach((candidate) => parts.runCandidates.append(candidateCard(run, candidate)));
    return;
  }
  run.candidates.forEach((candidate, index) => {
    if (shown[index].dataset.signature !== JSON.stringify(candidate)) {
      shown[index].replaceWith(candidateCard(run, candidate));
    }
  });
}

function candidateCard(run, candidate) {
  const card = element("article", "candidate state-" + candidate.state);
  card.dataset.key = run.id + " " + candidate.place_id;
  card.dataset.signature = JSON.stringify(candidate);

  const head = element("div", "candidate-head");
  const who = element("div");
  who.append(element("strong", "", candidate.name));
  const facts = [candidate.address, candidate.phone].filter(Boolean).join(" · ");
  if (facts) who.append(element("span", "candidate-facts", facts));
  head.append(who, element("span", "tag state-tag", STATE_TAGS[candidate.state] || candidate.state));
  card.append(head);

  card.append(element("p", "hint", CANDIDATE_TEXT[candidate.state] || ""));
  const work = workLine(candidate);
  if (work) card.append(element("p", "work-line", work));

  if (candidate.problems && candidate.problems.length) {
    const list = element("ul", "problems");
    candidate.problems.forEach((problem) => list.append(element("li", "", problem)));
    card.append(list);
  }

  if (candidate.state === "paste") {
    card.append(commandRow(candidate.command));
  }

  const links = element("div", "candidate-links");
  if (candidate.site_url) {
    const open = element("a", "", "Open the site");
    open.href = candidate.site_url;
    open.target = "_blank";
    open.rel = "noopener";
    links.append(open);
  }
  if (candidate.folder) {
    links.append(element("code", "", candidate.folder));
  }
  if (links.children.length) card.append(links);

  if (candidate.resume) {
    card.append(element("p", "field-label", "Open this Claude Code session in a terminal"));
    card.append(commandRow(candidate.resume));
  }

  if (candidate.contacts && candidate.contacts.length) {
    card.append(contactBlock(candidate.contacts));
  }

  if (candidate.messages && candidate.messages.length) {
    candidate.messages.forEach((message) => card.append(messageBlock(message)));
    card.append(sentRow(run, candidate));
  }
  return card;
}

function workLine(candidate) {
  const live = candidate.activity;
  if (candidate.state === "building" && live) {
    const steps = live.steps === 1 ? "1 step" : live.steps + " steps";
    const model = live.model ? " · " + live.model : "";
    return (live.now ? "Now: " + live.now + " · " : "Starting · ") + steps + " so far" + model;
  }
  if (candidate.models && candidate.models.length) {
    const minutes = candidate.minutes ? " in " + candidate.minutes + " min of work" : "";
    const steps = candidate.steps ? ", " + candidate.steps + " steps" : "";
    return "Built by " + candidate.models.join(", ") + minutes + steps + ".";
  }
  return "";
}

function contactBlock(contacts) {
  const block = element("div", "contacts");
  block.append(element("p", "field-label", "Reach them"));
  const list = element("div", "contact-links");
  contacts.forEach((contact) => {
    const link = element("a", "contact contact-" + contact.kind, contact.label);
    link.href = contact.href;
    if (!LINKS_IN_PLACE.includes(contact.kind) && !contact.href.startsWith("viber:")) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    list.append(link);
  });
  block.append(list);
  return block;
}

function commandRow(command) {
  const line = element("div", "command-row");
  const field = element("input", "command-field");
  field.type = "text";
  field.readOnly = true;
  field.value = command;
  const button = element("button", "secondary", "Copy");
  button.type = "button";
  button.addEventListener("click", () => copyText(command, button));
  line.append(field, button);
  return line;
}

function messageBlock(message) {
  const block = element("div", "message");
  const head = element("div", "message-head");
  const button = element("button", "secondary", "Copy");
  button.type = "button";
  button.addEventListener("click", () => copyText(message.text, button));
  head.append(element("span", "", message.title), button);
  const text = element("textarea");
  text.readOnly = true;
  text.value = message.text;
  text.rows = Math.min(14, Math.max(3, message.text.split("\n").length + 1));
  block.append(head, text);
  return block;
}

function sentRow(run, candidate) {
  const line = element("div", "sent-row");
  const select = element("select");
  autopilot.data.channels.forEach((channel) => {
    const option = element("option", "", channel);
    option.value = channel;
    select.append(option);
  });
  const button = element("button", "secondary", "I sent it");
  button.type = "button";
  const note = element("span", "hint");
  const sent = (candidate.sent || []).map((item) => item.channel + " on " + item.on);
  note.textContent = sent.length ? "Logged: " + sent.join(", ") : "Nothing is logged until you say it was sent.";
  button.addEventListener("click", async () => {
    try {
      const data = await requestJson("/api/autopilot/runs/" + encodeURIComponent(run.id) + "/sent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ place_id: candidate.place_id, channel: select.value }),
      });
      note.textContent = "Logged over " + select.value + " on " + data.sent_at + ". Follow up due " + data.follow_up_due + ".";
    } catch (error) {
      note.textContent = error.message;
    }
  });
  line.append(select, button, note);
  return line;
}

function settingsPayload() {
  return {
    cities_from: parts.citiesFrom.value,
    sites_per_run: parts.sites.value,
    search_limit: parts.searchLimit.value,
    only_without_website: parts.noWebsite.checked,
    require_phone: parts.phone.checked,
    require_online_contact: parts.online.checked,
    only_rated: parts.rated.checked,
    min_rating: parts.minRating.value,
    min_reviews: parts.minReviews.value,
    trades: [...parts.trades.querySelectorAll("input:checked")].map((box) => box.value),
    site: {
      faq: parts.faq.checked,
      careers: parts.careers.checked,
      show_reviews: parts.reviews.checked,
      animations: parts.animations.checked,
      ai_media: parts.ai.checked,
      language: parts.language.value,
      stack: parts.stack.value,
      style: parts.style.value,
    },
    builder: {
      command: parts.command.value,
      model: parts.model.value,
      timeout_minutes: parts.timeout.value,
      parallel: parts.parallel.value,
    },
  };
}

async function saveSettings(event) {
  event.preventDefault();
  say(parts.settingsStatus, "Saving.");
  try {
    autopilot.data = await requestJson("/api/autopilot/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settingsPayload()),
    });
    renderSettings(autopilot.data);
    renderAutopilotForm(autopilot.data);
    say(parts.settingsStatus, "Saved. The next run uses these.");
  } catch (error) {
    say(parts.settingsStatus, error.message, true);
  }
}

function builderAdvice(result) {
  if (result.state === "ready") return result.message;
  if (result.state === "logged_out") {
    return result.message + " Open Terminal, run \"" + result.path + "\" once, log in with /login, then check again.";
  }
  if (result.state === "missing") {
    return result.message + " Install Claude Code for the terminal and log in once, or fill in the command above. Until then a run stops after the photographs and gives you a command to paste.";
  }
  return result.message;
}

async function checkBuilder() {
  parts.builderCheck.disabled = true;
  parts.builderState.textContent = "Asking Claude Code for one word. This uses a little of your Claude usage.";
  try {
    const result = await requestJson("/api/autopilot/check", { method: "POST" });
    parts.builderState.textContent = builderAdvice(result);
  } catch (error) {
    parts.builderState.textContent = error.message;
  } finally {
    parts.builderCheck.disabled = false;
  }
}

async function stopRun() {
  parts.runStop.disabled = true;
  parts.runStop.textContent = "Stopping";
  try {
    await requestJson("/api/autopilot/stop", { method: "POST" });
    setTimeout(() => showRun(autopilot.runId), 800);
  } catch (error) {
    say(parts.status, error.message, true);
    parts.runStop.disabled = false;
    parts.runStop.textContent = "Stop";
  }
}

parts.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    history.replaceState(null, "", "#" + tab.dataset.view);
    showView(tab.dataset.view);
  });
});
parts.form.addEventListener("submit", startRun);
parts.random.addEventListener("click", async () => {
  if (!autopilot.data) await loadAutopilot();
  pickRandomCity();
});
parts.runSelect.addEventListener("change", () => showRun(parts.runSelect.value));
parts.runStop.addEventListener("click", stopRun);
parts.settingsForm.addEventListener("submit", saveSettings);
parts.builderCheck.addEventListener("click", checkBuilder);
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));

showView(location.hash.slice(1));

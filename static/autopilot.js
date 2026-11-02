const ACTIVE_RUN_STATES = ["searching", "building"];
const POLL_ACTIVE_MS = 3000;
const POLL_WAITING_MS = 10000;

const CANDIDATE_TEXT = {
  waiting: "Waiting its turn.",
  photos: "Downloading stock photographs.",
  building: "Claude Code is writing the brief, the site and the messages.",
  paste: "Photographs are ready. Paste this into Claude Code: it builds the site and writes the messages without asking anything, and this page shows them once it is done.",
  done: "Built and checked. Its messages are on the Sites page.",
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
  loading: null,
};

const parts = {
  runPanel: document.getElementById("run-panel"),
  runTitle: document.getElementById("run-title"),
  runMessage: document.getElementById("run-message"),
  runUsage: document.getElementById("run-usage"),
  runCandidates: document.getElementById("run-candidates"),
  runSelect: document.getElementById("run-select"),
  settingsForm: document.getElementById("settings-form"),
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
  effort: document.getElementById("set-effort"),
  deploy: document.getElementById("set-deploy"),
  deployState: document.getElementById("deploy-state"),
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

function senderNote(data) {
  const who = data.sender_about ? ", " + data.sender_about : "";
  const name = data.sender_name ? "Messages are signed " + data.sender_name + who : "No sender name is set, so messages are signed [your name]";
  const links = data.portfolio_links === 1 ? "1 portfolio link" : data.portfolio_links + " portfolio links";
  return name + ", with " + links + ". Both live in config.local.yaml under outreach.";
}

function renderSettings(data) {
  const settings = data.settings;
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
  fillOptions(parts.stack, data.stacks, settings.site.stack);
  parts.style.value = settings.site.style;
  parts.command.value = settings.builder.command;
  parts.model.value = settings.builder.model;
  fillOptions(parts.effort, data.efforts, settings.builder.effort || "");
  parts.deploy.checked = settings.deploy;
  parts.deployState.textContent = data.has_publishing
    ? "CLOUDFLARE_API_TOKEN is set in .env."
    : "CLOUDFLARE_API_TOKEN is not set in .env, so nothing is published yet. Section 5 of SETUP.md shows how to get one.";
  parts.timeout.value = settings.builder.timeout_minutes;
  parts.parallel.value = settings.builder.parallel;
  parts.builderState.textContent = data.builder ? "Found at " + data.builder + "." : "Not found on this computer.";
  parts.senderState.textContent = senderNote(data);
}

function ensureAutopilot() {
  if (autopilot.data) return Promise.resolve();
  if (!autopilot.loading) {
    autopilot.loading = loadAutopilot().finally(() => {
      autopilot.loading = null;
    });
  }
  return autopilot.loading;
}

async function loadAutopilot() {
  try {
    autopilot.data = await requestJson("/api/autopilot");
    renderSettings(autopilot.data);
    await loadRuns(autopilot.data.running);
  } catch (error) {
    parts.runPanel.hidden = false;
    parts.runMessage.textContent = error.message;
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
    if (!quietly) parts.runMessage.textContent = error.message;
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
  if (candidate.live_url) {
    const live = element("a", "live-link", "Live at " + candidate.live_url.replace(/^https:\/\//, ""));
    live.href = candidate.live_url;
    live.target = "_blank";
    live.rel = "noopener";
    links.append(live);
    if (!candidate.live_public) {
      links.append(element("span", "problems", "This address did not open yet, so it is not in the messages. Publish it again in a few minutes."));
    }
  }
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
    const names = Object.fromEntries(autopilot.data.efforts);
    const effort = candidate.effort ? " at " + (names[candidate.effort] || candidate.effort).toLowerCase() + " effort" : "";
    const minutes = candidate.minutes ? " in " + candidate.minutes + " min of work" : "";
    const steps = candidate.steps ? ", " + candidate.steps + " steps" : "";
    return "Built by " + candidate.models.join(", ") + effort + minutes + steps + ".";
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

function settingsPayload() {
  return {
    sites_per_run: parts.sites.value,
    search_limit: parts.searchLimit.value,
    only_without_website: parts.noWebsite.checked,
    require_phone: parts.phone.checked,
    require_online_contact: parts.online.checked,
    only_rated: parts.rated.checked,
    min_rating: parts.minRating.value,
    min_reviews: parts.minReviews.value,
    deploy: parts.deploy.checked,
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
      effort: parts.effort.value,
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
    say(parts.settingsStatus, "Saved. The next search uses these.");
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

parts.runSelect.addEventListener("change", () => showRun(parts.runSelect.value));
parts.settingsForm.addEventListener("submit", saveSettings);
parts.builderCheck.addEventListener("click", checkBuilder);

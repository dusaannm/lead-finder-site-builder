const VIEW_TITLES = {
  overview: ["Overview", "Turn it on and it finds, builds and publishes on its own."],
  sites: ["Sites", "Open a site, copy the message, send it, mark it."],
  leads: ["Leads", "Every business found, and a search of your own."],
  autopilot: ["Activity", "What the autopilot is doing and everything it has done."],
  settings: ["Settings", "What the autopilot looks for."],
};

const ICON_PATHS = {
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  zap: '<path d="M13 2.5L4.5 13.5h6.5l-1 8 8.5-11h-6.5z"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.3 2.4 3.5 5.3 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.3-3.5-8.5s1.2-6.1 3.5-8.5z"/>',
  file: '<path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/><path d="M14 3.5V8h4.5M9 13h6M9 16.5h4"/>',
  layout: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9h17M9.5 9v10.5"/>',
  send: '<path d="M20.5 3.5L10 14M20.5 3.5l-6.5 17-4-6.5-6.5-4z"/>',
  pencil: '<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="M13 7l4 4"/>',
  reply: '<path d="M9 14.5L4.5 10 9 5.5"/><path d="M4.5 10h9a6 6 0 0 1 6 6v3.5"/>',
  flag: '<path d="M5.5 20.5v-16M5.5 4.5h11l-2 4 2 4h-11"/>',
  check: '<path d="M5 12.5l4.5 4.5 9.5-10"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5L11 13M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="0.8"/>',
};

const EVENT_ICONS = {
  search: "search",
  status: "flag",
  autopilot: "zap",
  brief: "file",
  site: "layout",
  publish: "globe",
  messages: "pencil",
  sent: "send",
  reply: "reply",
};

const EVENT_GROUPS = {
  all: [],
  searches: ["search", "status"],
  autopilot: ["autopilot"],
  sites: ["brief", "site", "publish"],
  messages: ["messages", "sent", "reply"],
};

const ATTENTION_ICONS = {
  follow_up: "reply",
  ready: "send",
  publish: "globe",
  build: "layout",
};

const ATTENTION_SHOWN = 6;
const OVERVIEW_POLL_MS = 20000;

const STAGE_LABELS = {
  brief: "Brief ready",
  built: "Site built",
  ready: "Ready to send",
  contacted: "Contacted",
  declined: "Declined",
  accepted: "Accepted",
};

const CONTACTED_STAGES = ["contacted", "declined", "accepted"];

const SITE_FILTERS = {
  all: () => true,
  ready: (site) => site.stage === "ready" && site.reachable,
  live: (site) => Boolean(site.live_url && site.live_public),
  contacted: (site) => CONTACTED_STAGES.includes(site.stage),
  phone: (site) => site.stage === "ready" && !site.reachable,
  unbuilt: (site) => site.stage === "brief",
};

const board = {
  view: "",
  sites: [],
  channels: [],
  siteFilter: "ready",
  events: [],
  eventFilter: "all",
  open: new Set(),
  watchTimer: null,
  shiftTimer: null,
  region: "",
};

const shell = {
  tabs: document.querySelectorAll(".tab"),
  title: document.getElementById("view-title"),
  subtitle: document.getElementById("view-subtitle"),
  kpis: document.getElementById("overview-kpis"),
  pipeline: document.getElementById("overview-pipeline"),
  attention: document.getElementById("overview-attention"),
  attentionCount: document.getElementById("attention-count"),
  recent: document.getElementById("overview-recent"),
  navReady: document.getElementById("nav-ready"),
  navRunning: document.getElementById("nav-running"),
  sitesFilter: document.getElementById("sites-filter"),
  sitesSearch: document.getElementById("sites-search"),
  sitesList: document.getElementById("sites-list"),
  sitesEmpty: document.getElementById("sites-empty"),
  historyFilter: document.getElementById("history-filter"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  pilot: document.getElementById("pilot"),
  pilotTitle: document.getElementById("pilot-title"),
  pilotLine: document.getElementById("pilot-line"),
  pilotRegion: document.getElementById("pilot-region"),
  pilotToggle: document.getElementById("pilot-toggle"),
  pilotCities: document.getElementById("pilot-cities"),
  pilotBuilt: document.getElementById("pilot-built"),
  pilotFive: document.getElementById("pilot-five"),
  pilotFiveBar: document.getElementById("pilot-five-bar"),
  pilotWeekly: document.getElementById("pilot-weekly"),
  pilotWeeklyBar: document.getElementById("pilot-weekly-bar"),
  pilotWeeklyLabel: document.getElementById("pilot-weekly-label"),
  liveState: document.getElementById("live-state"),
  shiftLog: document.getElementById("shift-log"),
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  svg.innerHTML = ICON_PATHS[name] || "";
  return svg;
}

function count(number, one, many) {
  return number.toLocaleString("en-US") + " " + (number === 1 ? one : many);
}

function parseStamp(text) {
  if (!text) return null;
  const parsed = new Date(text.length === 10 ? text + "T00:00:00" : text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function dayKey(date) {
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()].map((part) => String(part).padStart(2, "0")).join("-");
}

function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (dayKey(date) === dayKey(today)) return "Today";
  if (dayKey(date) === dayKey(yesterday)) return "Yesterday";
  const options = { weekday: "long", day: "numeric", month: "long" };
  if (date.getFullYear() !== today.getFullYear()) options.year = "numeric";
  return date.toLocaleDateString("en-GB", options);
}

function clockLabel(text) {
  const date = parseStamp(text);
  if (!date || text.length === 10) return "";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function whenLabel(text) {
  const date = parseStamp(text);
  if (!date) return "";
  const day = dayLabel(date);
  const short = day === "Today" || day === "Yesterday" ? day : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const clock = clockLabel(text);
  return clock ? short + ", " + clock : short;
}

function showView(name) {
  const chosen = VIEW_TITLES[name] ? name : "overview";
  if (board.view && board.view !== chosen) window.scrollTo(0, 0);
  board.view = chosen;
  Object.keys(VIEW_TITLES).forEach((view) => {
    document.getElementById("view-" + view).hidden = view !== chosen;
  });
  shell.tabs.forEach((tab) => {
    const active = tab.dataset.view === chosen;
    tab.classList.toggle("active", active);
    if (active) {
      tab.setAttribute("aria-current", "page");
    } else {
      tab.removeAttribute("aria-current");
    }
  });
  shell.title.textContent = VIEW_TITLES[chosen][0];
  shell.subtitle.textContent = VIEW_TITLES[chosen][1];
  document.title = VIEW_TITLES[chosen][0] + " · Lead Finder";
  if (chosen === "overview") loadOverview();
  if (chosen === "sites") loadSites();
  if (chosen === "autopilot") loadHistory();
  if (chosen === "autopilot" || chosen === "settings") ensureAutopilot();
  if (chosen === "overview" || chosen === "autopilot") loadPilot();
}

function goTo(view) {
  history.replaceState(null, "", "#" + view);
  showView(view);
}

async function openSearch(file) {
  goTo("leads");
  if (![...elements.fileSelect.options].some((option) => option.value === file)) return;
  elements.fileSelect.value = file;
  try {
    await loadLeads(file);
  } catch (error) {
    setMessage(error.message, true);
  }
}

async function openRun(runId) {
  goTo("autopilot");
  await ensureAutopilot();
  if (![...parts.runSelect.options].some((option) => option.value === runId)) return;
  parts.runSelect.value = runId;
  await showRun(runId);
}

function updateNav(data) {
  const ready = data.attention.filter((item) => item.kind === "ready").length;
  const running = data.autopilot.running;
  shell.navReady.textContent = String(ready);
  shell.navReady.hidden = !ready;
  shell.navRunning.hidden = !running;
  clearTimeout(board.watchTimer);
  if (running) {
    board.watchTimer = setTimeout(() => (board.view === "overview" ? loadOverview() : refreshNav()), OVERVIEW_POLL_MS);
  }
}

function refreshNav() {
  requestJson("/api/overview").then(updateNav).catch(() => {});
}

async function loadOverview() {
  try {
    const data = await requestJson("/api/overview");
    renderKpis(data.counts);
    renderPipeline(data.counts);
    renderAttention(data.attention);
    renderEvents(shell.recent, data.recent, true);
    updateNav(data);
  } catch (error) {
    shell.attention.replaceChildren(element("li", "attention-empty", error.message));
  }
}

function kpiCard(label, value, foot, iconName, tone) {
  const card = element("article", "kpi tone-" + tone);
  const head = element("div", "kpi-head");
  const badge = element("span", "kpi-icon");
  badge.append(icon(iconName));
  head.append(element("span", "kpi-label", label), badge);
  card.append(head, element("strong", "kpi-value", value.toLocaleString("en-US")), element("span", "kpi-foot", foot));
  return card;
}

function renderKpis(counts) {
  const share = counts.businesses ? Math.round((counts.without_website / counts.businesses) * 100) : 0;
  const withShare = counts.businesses ? 100 - share : 0;
  shell.kpis.replaceChildren(
    kpiCard("Businesses found", counts.businesses, "In " + count(counts.searches, "saved search", "saved searches"), "search", "blue"),
    kpiCard("Without a website", counts.without_website, share + "% of everything found", "target", "green"),
    kpiCard("With a website", counts.with_website, withShare + "% of everything found", "globe", "blue"),
    kpiCard("Sites built", counts.sites, counts.live + " live", "layout", "blue"),
    kpiCard("Ready to send", counts.ready, counts.phone_only + " more have only a phone", "pencil", "green"),
    kpiCard("Contacted", counts.contacted, counts.accepted + " accepted", "send", "green")
  );
}

function renderPipeline(counts) {
  const steps = [
    ["Found", counts.businesses, "blue"],
    ["Without a website", counts.without_website, "blue"],
    ["Brief written", counts.briefs, "blue"],
    ["Site built", counts.sites, "blue"],
    ["Contacted", counts.contacted, "green"],
    ["Accepted", counts.accepted, "green"],
  ];
  const most = Math.max(1, ...steps.map((step) => step[1]));
  shell.pipeline.replaceChildren(
    ...steps.map(([label, value, tone]) => {
      const line = element("div", "pipeline-row");
      const track = element("div", "pipeline-track");
      const fill = element("span", "pipeline-fill tone-" + tone);
      fill.style.width = value ? Math.max(1.5, (value / most) * 100) + "%" : "0";
      track.append(fill);
      line.append(element("span", "pipeline-label", label), track, element("strong", "pipeline-value", value.toLocaleString("en-US")));
      return line;
    })
  );
}

function renderAttention(items) {
  shell.attentionCount.textContent = String(items.length);
  shell.attentionCount.hidden = !items.length;
  if (!items.length) {
    const calm = element("li", "attention-empty");
    calm.append(icon("check"), element("span", "", "Nothing is waiting on you."));
    shell.attention.replaceChildren(calm);
    return;
  }
  const shown = items.slice(0, ATTENTION_SHOWN).map((item) => {
    const entry = element("li");
    const button = element("button", "attention-item kind-" + item.kind);
    button.type = "button";
    const badge = element("span", "attention-icon");
    badge.append(icon(ATTENTION_ICONS[item.kind] || "arrow"));
    const text = element("span", "attention-text");
    text.append(element("strong", "", item.title), element("span", "", item.detail));
    button.append(badge, text, icon("arrow"));
    button.addEventListener("click", () => goTo(item.view));
    entry.append(button);
    return entry;
  });
  if (items.length > ATTENTION_SHOWN) {
    shown.push(element("li", "attention-more", count(items.length - ATTENTION_SHOWN, "more thing", "more things") + " on the Sites page."));
  }
  shell.attention.replaceChildren(...shown);
}

function followEvent(event) {
  if (event.file) return openSearch(event.file);
  if (event.run) return openRun(event.run);
  return goTo(event.view);
}

function eventEntry(event, withDay) {
  const entry = element("li", "event kind-" + event.kind);
  const opens = Boolean(event.href || event.view);
  const line = element(event.href ? "a" : opens ? "button" : "div", "event-row");
  if (event.href) {
    line.href = event.href;
    line.target = "_blank";
    line.rel = "noopener noreferrer";
  } else if (opens) {
    line.type = "button";
    line.addEventListener("click", () => followEvent(event));
  }
  const badge = element("span", "event-icon");
  badge.append(icon(EVENT_ICONS[event.kind] || "clock"));
  const body = element("span", "event-body");
  body.append(element("span", "event-title", event.title));
  if (event.detail) body.append(element("span", "event-detail", event.detail));
  const when = element("time", "event-time", withDay ? whenLabel(event.at) : clockLabel(event.at));
  when.dateTime = event.at;
  line.append(badge, body, when);
  entry.append(line);
  return entry;
}

function renderEvents(list, events, withDay) {
  if (!events.length) {
    list.replaceChildren(element("li", "attention-empty", "Nothing yet. Run a search to start."));
    return;
  }
  list.replaceChildren(...events.map((event) => eventEntry(event, withDay)));
}

function markFilter(group, chosen, counter) {
  group.querySelectorAll("button").forEach((button) => {
    const active = button.dataset.filter === chosen;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.querySelector("span").textContent = counter(button.dataset.filter);
  });
}

async function loadHistory() {
  try {
    const data = await requestJson("/api/history");
    board.events = data.events;
    renderHistory();
  } catch (error) {
    shell.historyList.replaceChildren();
    shell.historyEmpty.hidden = false;
    shell.historyEmpty.textContent = error.message;
  }
}

function inGroup(event, group) {
  const kinds = EVENT_GROUPS[group];
  return !kinds.length || kinds.includes(event.kind);
}

function renderHistory() {
  markFilter(shell.historyFilter, board.eventFilter, (group) => board.events.filter((event) => inGroup(event, group)).length);
  const shown = board.events.filter((event) => inGroup(event, board.eventFilter));
  const days = new Map();
  shown.forEach((event) => {
    const date = parseStamp(event.at);
    const key = date ? dayKey(date) : "";
    if (!days.has(key)) days.set(key, { date, events: [] });
    days.get(key).events.push(event);
  });
  shell.historyList.replaceChildren(
    ...[...days.values()].map(({ date, events }) => {
      const section = element("section", "card day");
      const head = element("div", "day-head");
      head.append(element("h2", "", date ? dayLabel(date) : "Undated"), element("span", "card-note", count(events.length, "entry", "entries")));
      const list = element("ol", "timeline");
      events.forEach((event) => list.append(eventEntry(event, false)));
      section.append(head, list);
      return section;
    })
  );
  shell.historyEmpty.hidden = shown.length > 0;
  shell.historyEmpty.textContent = board.events.length
    ? "Nothing of this kind yet."
    : "Nothing yet. Your searches, sites and messages show up here.";
}

async function loadSites() {
  try {
    const data = await requestJson("/api/sites");
    board.sites = data.sites;
    board.channels = data.channels;
    renderSites();
  } catch (error) {
    shell.sitesList.replaceChildren();
    shell.sitesEmpty.hidden = false;
    shell.sitesEmpty.textContent = error.message;
  }
}

function renderSites() {
  markFilter(shell.sitesFilter, board.siteFilter, (name) => board.sites.filter(SITE_FILTERS[name]).length);
  const wanted = shell.sitesSearch.value.trim().toLowerCase();
  const shown = board.sites
    .filter(SITE_FILTERS[board.siteFilter])
    .filter((site) => !wanted || (site.name + " " + site.address).toLowerCase().includes(wanted));
  shell.sitesList.replaceChildren(...shown.map(siteCard));
  shell.sitesEmpty.hidden = shown.length > 0;
  shell.sitesEmpty.textContent = board.sites.length
    ? "No site matches."
    : "No sites yet. Create a brief from the Leads page, or start the autopilot.";
}

function siteSteps(site) {
  const contacted = CONTACTED_STAGES.includes(site.stage);
  const steps = [
    ["Brief", site.brief_at],
    ["Site", site.built_at],
    ["Live", site.live_url && site.live_public ? site.published_at || "yes" : ""],
    ["Messages", site.messages_at],
    ["Sent", site.sent.length ? site.sent[0].on : contacted ? "yes" : ""],
  ];
  const list = element("ol", "steps");
  steps.forEach(([label, done]) => {
    const step = element("li", done ? "step done" : "step");
    step.append(element("span", "step-bar"), element("span", "step-label", label));
    step.title = done ? label + (done === "yes" ? "" : ": " + whenLabel(done)) : label + ": not yet";
    list.append(step);
  });
  return list;
}

function linkButton(href, label, iconName, className) {
  const link = element("a", "button " + className);
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.append(icon(iconName), element("span", "", label));
  return link;
}

function nextCommand(site) {
  if (site.stage === "brief") {
    return { label: "Copy the build command", command: '/build-site "' + site.folder + '"' };
  }
  if (site.stage === "built" && site.place_id) {
    return { label: "Copy the message command", command: "/draft-outreach " + site.place_id };
  }
  return null;
}

function siteActions(site) {
  const line = element("div", "site-actions");
  if (site.live_url && site.live_public) line.append(linkButton(site.live_url, "Live site", "globe", "live"));
  if (site.site_url) line.append(linkButton(site.site_url, "Preview", "external", "secondary"));
  const next = nextCommand(site);
  if (next) {
    const button = element("button", "secondary", next.label);
    button.type = "button";
    button.title = next.command + "\nPaste it into Claude Code.";
    button.addEventListener("click", () => copyText(next.command, button));
    line.append(button);
  }
  return line;
}

function siteSentRow(site) {
  const line = element("div", "sent-row");
  const select = element("select");
  board.channels.forEach((channel) => {
    const option = element("option", "", channel);
    option.value = channel;
    select.append(option);
  });
  const button = element("button", "secondary", "I sent it");
  button.type = "button";
  const note = element("span", "hint");
  const logged = site.sent.map((item) => item.channel + " on " + item.on);
  note.textContent = logged.length ? "Logged: " + logged.join(", ") : "Nothing is logged until you say it was sent.";
  if (!site.place_id) {
    button.disabled = true;
    note.textContent = "This brief names no place_id, so a send cannot be logged for it.";
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await requestJson("/api/sites/sent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ place_id: site.place_id, channel: select.value }),
      });
      await loadSites();
      refreshNav();
    } catch (error) {
      note.textContent = error.message;
      button.disabled = false;
    }
  });
  line.append(select, button, note);
  return line;
}

function siteDetail(site, card) {
  const toggle = element("button", "site-toggle");
  toggle.type = "button";
  const detail = element("div", "site-detail");
  const opened = board.open.has(site.folder);
  detail.hidden = !opened;
  toggle.setAttribute("aria-expanded", String(opened));
  toggle.append(element("span", "", site.messages.length ? "Messages and contacts" : "Contacts"), icon("chevron"));
  toggle.addEventListener("click", () => {
    const open = detail.hidden;
    detail.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) {
      board.open.add(site.folder);
    } else {
      board.open.delete(site.folder);
    }
  });
  if (site.contacts.length) detail.append(contactBlock(site.contacts));
  site.messages.forEach((message) => detail.append(messageBlock(message)));
  if (site.messages.length) detail.append(siteSentRow(site));
  card.append(toggle, detail);
}

function siteCard(site) {
  const card = element("article", "card site-card stage-" + site.stage);
  const cover = element(site.site_url ? "a" : "div", "site-cover");
  if (site.site_url) {
    cover.href = site.site_url;
    cover.target = "_blank";
    cover.rel = "noopener noreferrer";
  }
  if (site.thumbnail) {
    const picture = element("img");
    picture.src = site.thumbnail;
    picture.alt = "";
    picture.loading = "lazy";
    cover.append(picture);
  } else {
    cover.append(element("span", "site-initial", site.name.charAt(0).toUpperCase()));
  }
  const phoneOnly = site.stage === "ready" && !site.reachable;
  cover.append(element("span", "stage-tag stage-" + site.stage, phoneOnly ? "Phone only" : STAGE_LABELS[site.stage] || site.stage));
  card.append(cover);

  const body = element("div", "site-body");
  const title = element("div", "site-title");
  title.append(element("h3", "", site.name));
  if (site.address) title.append(element("p", "site-address", site.address));
  body.append(title, siteSteps(site));
  if (site.live_url && !site.live_public) {
    body.append(element("p", "site-warning", "Published, but the address did not open yet. Publish it again in a few minutes."));
  }
  body.append(siteActions(site));
  card.append(body);

  if (site.messages.length || site.contacts.length) siteDetail(site, card);
  const folder = element("p", "site-folder", site.folder_label);
  folder.title = site.folder;
  card.append(folder);
  return card;
}

function percent(share) {
  return share === null || share === undefined ? "Not known yet" : Math.round(share * 100) + "%";
}

function fillBar(bar, share) {
  bar.style.width = Math.min(100, Math.round((share || 0) * 100)) + "%";
}

function pilotLine(data) {
  const sites = count(data.built, "site", "sites");
  if (data.stopping) return "Stopping the work in progress.";
  if (data.running) return data.now || "Starting.";
  if (data.ended === "weekly_limit") return "It stopped on its own at the weekly Claude limit, after " + sites + ".";
  if (data.ended === "crashed") return "It stopped unexpectedly after " + sites + ". Start it again.";
  if (data.ended) return "It built " + sites + " in the last run.";
  return "It searches, builds and publishes until you stop it. Nothing is ever sent.";
}

function renderRegions(data) {
  const chosen = board.region || data.region;
  const buttons = data.regions.map(([value, label]) => {
    const button = element("button", value === chosen ? "active" : "", label);
    button.type = "button";
    button.disabled = data.running;
    button.addEventListener("click", () => {
      board.region = value;
      renderPilot(data);
    });
    return button;
  });
  shell.pilotRegion.replaceChildren(...buttons);
  return chosen;
}

function renderPilot(data) {
  const chosen = renderRegions(data);
  const levels = data.levels || {};
  shell.pilot.classList.toggle("is-on", data.running);
  shell.pilotTitle.textContent = data.running ? "Autopilot is on" : "Autopilot is off";
  shell.pilotLine.textContent = pilotLine(data);
  shell.pilotToggle.textContent = data.stopping ? "Stopping" : data.running ? "Stop" : "Start";
  shell.pilotToggle.classList.toggle("is-stop", data.running);
  shell.pilotToggle.disabled = data.stopping;
  shell.pilotCities.textContent = data.cities[chosen].toLocaleString("en-US");
  shell.pilotBuilt.textContent = data.built;
  shell.pilotFive.textContent = percent(levels.five_hour);
  shell.pilotWeekly.textContent = percent(levels.seven_day);
  shell.pilotWeeklyLabel.textContent = "Weekly limit, stops at " + percent(data.stop_at_weekly);
  fillBar(shell.pilotFiveBar, levels.five_hour);
  fillBar(shell.pilotWeeklyBar, levels.seven_day);
  shell.liveState.textContent = data.running ? "Autopilot is on" : "Autopilot is off";
  shell.shiftLog.textContent = data.log.join("\n") || "Nothing has run yet. Start the autopilot on the Overview page.";
  shell.pilotToggle.onclick = () => togglePilot(data.running, chosen);
  clearTimeout(board.shiftTimer);
  if (data.running && ["overview", "autopilot"].includes(board.view)) {
    board.shiftTimer = setTimeout(loadPilot, POLL_ACTIVE_MS);
  }
}

async function loadPilot() {
  try {
    renderPilot(await requestJson("/api/shift"));
  } catch (error) {
    shell.pilotLine.textContent = error.message;
  }
}

async function togglePilot(running, region) {
  shell.pilotToggle.disabled = true;
  try {
    await requestJson(running ? "/api/shift/stop" : "/api/shift/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region }),
    });
    await loadPilot();
    refreshNav();
  } catch (error) {
    shell.pilotLine.textContent = error.message;
    shell.pilotToggle.disabled = false;
  }
}

shell.tabs.forEach((tab) => {
  tab.addEventListener("click", () => goTo(tab.dataset.view));
});
shell.sitesFilter.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  board.siteFilter = button.dataset.filter;
  renderSites();
});
shell.historyFilter.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  board.eventFilter = button.dataset.filter;
  renderHistory();
});
shell.sitesSearch.addEventListener("input", renderSites);
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));

showView(location.hash.slice(1));
if (board.view !== "overview") refreshNav();

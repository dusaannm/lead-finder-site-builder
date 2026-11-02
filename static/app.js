const STATUS_LABELS = {
  "": "Not contacted",
  contacted: "Contacted",
  declined: "Declined",
  accepted: "Accepted",
};

const NUMERIC_COLUMNS = ["score", "rating", "review_count", "website_score"];

const state = {
  file: null,
  rows: [],
  sortColumn: "score",
  sortAscending: false,
  poorWebsiteBelow: null,
};

const elements = {
  form: document.getElementById("search-form"),
  query: document.getElementById("query"),
  limit: document.getElementById("limit"),
  searchButton: document.getElementById("search-button"),
  searchStatus: document.getElementById("search-status"),
  fileSelect: document.getElementById("file-select"),
  onlyNoWebsite: document.getElementById("only-no-website"),
  minRating: document.getElementById("min-rating"),
  minReviews: document.getElementById("min-reviews"),
  exportButton: document.getElementById("export-button"),
  resultCount: document.getElementById("result-count"),
  body: document.getElementById("leads-body"),
  empty: document.getElementById("empty-message"),
  usage: document.getElementById("usage"),
  overlay: document.getElementById("overlay"),
};

function setMessage(text, isError) {
  elements.searchStatus.textContent = text || "";
  elements.searchStatus.classList.toggle("error", Boolean(isError));
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

function systemRow(label, value, fine) {
  const line = document.createElement("div");
  line.className = "system-row";
  const dot = document.createElement("span");
  dot.className = "dot " + (fine ? "dot-on" : "dot-off");
  const name = document.createElement("span");
  name.className = "system-label";
  name.textContent = label;
  const shown = document.createElement("strong");
  shown.textContent = value;
  line.append(dot, name, shown);
  return line;
}

async function loadUsage() {
  try {
    const data = await requestJson("/api/usage");
    const source = data.gosom ? "Google Maps through gosom" : data.has_google_key ? "Google Places" : "OpenStreetMap";
    const rows = [systemRow("Search source", source, true)];
    if (data.has_google_key && !data.gosom) {
      rows.push(systemRow("Google calls this month", data.used + " of " + data.limit, data.used < data.limit));
    }
    rows.push(
      systemRow("Claude Code", data.has_builder ? "Ready" : "Not found", data.has_builder),
      systemRow("Cloudflare Pages", data.has_publishing ? "Connected" : "Not set up", data.has_publishing)
    );
    elements.usage.replaceChildren(...rows);
  } catch (error) {
    elements.usage.textContent = "";
  }
}

async function loadSettings() {
  const data = await requestJson("/api/settings");
  state.poorWebsiteBelow = data.poor_website_below;
  elements.limit.placeholder = String(data.default_limit);
}

async function loadFiles(preferred) {
  const data = await requestJson("/api/files");
  elements.fileSelect.innerHTML = "";

  if (!data.files.length) {
    const option = document.createElement("option");
    option.textContent = "no saved searches";
    elements.fileSelect.append(option);
    elements.fileSelect.disabled = true;
    return;
  }

  elements.fileSelect.disabled = false;
  data.files.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name.replace(/^leads_/, "").replace(/\.csv$/, "");
    elements.fileSelect.append(option);
  });

  const chosen = preferred && data.files.includes(preferred) ? preferred : data.files[0];
  elements.fileSelect.value = chosen;
  await loadLeads(chosen);
}

async function loadLeads(file) {
  const data = await requestJson("/api/leads?file=" + encodeURIComponent(file));
  state.file = data.file;
  state.rows = data.rows;
  render();
}

function toNumber(value) {
  const parsed = parseFloat(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function visibleRows() {
  const minRating = toNumber(elements.minRating.value);
  const minReviews = toNumber(elements.minReviews.value);

  let rows = state.rows.filter((row) => {
    if (elements.onlyNoWebsite.checked && (row.website || "").trim()) {
      return false;
    }
    if (minRating !== null && (toNumber(row.rating) === null || toNumber(row.rating) < minRating)) {
      return false;
    }
    if (minReviews !== null && (toNumber(row.review_count) === null || toNumber(row.review_count) < minReviews)) {
      return false;
    }
    return true;
  });

  const column = state.sortColumn;
  const direction = state.sortAscending ? 1 : -1;

  rows.sort((left, right) => {
    if (NUMERIC_COLUMNS.includes(column)) {
      const a = toNumber(left[column]);
      const b = toNumber(right[column]);
      if (a === null && b === null) return 0;
      if (a === null) return 1;
      if (b === null) return -1;
      return (a - b) * direction;
    }
    return String(left[column] || "").localeCompare(String(right[column] || "")) * direction;
  });

  return rows;
}

function linkElement(href, label) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.textContent = label;
  return anchor;
}

function websiteHref(value) {
  const text = (value || "").trim();
  if (!text) {
    return null;
  }
  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(text) ? text : "https://" + text;
  try {
    const url = new URL(candidate);
    const webScheme = url.protocol === "http:" || url.protocol === "https:";
    const realHost = /^[^.]+(\.[^.]+)+$/.test(url.hostname);
    return webScheme && realHost ? url.href : null;
  } catch (error) {
    return null;
  }
}

function profileHref(value, site) {
  const text = (value || "").trim();
  if (!text) return null;
  if (/^https?:\/\//i.test(text) || text.toLowerCase().includes(site + ".com")) {
    return websiteHref(text);
  }
  return "https://www." + site + ".com/" + encodeURIComponent(text.replace(/^@/, "").replace(/\/+$/, "")) + "/";
}

function statusSelect(row) {
  const select = document.createElement("select");
  Object.entries(STATUS_LABELS).forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  });
  select.value = row.status || "";

  select.addEventListener("change", async () => {
    try {
      await requestJson("/api/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: state.file, place_id: row.place_id, status: select.value }),
      });
      row.status = select.value;
      select.classList.add("saved");
      setTimeout(() => select.classList.remove("saved"), 1200);
    } catch (error) {
      setMessage(error.message, true);
      select.value = row.status || "";
    }
  });

  return select;
}

function legacyCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-1000px";
  document.body.append(area);
  area.select();

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (error) {
    copied = false;
  }

  area.remove();
  return copied;
}

async function copyBriefCommand(row, button) {
  const command = "/build-brief " + row.place_id;
  const original = button.textContent;
  let copied = false;

  try {
    await navigator.clipboard.writeText(command);
    copied = true;
  } catch (error) {
    copied = legacyCopy(command);
  }

  showCommand(command, copied);

  if (copied) {
    button.textContent = "Copied";
    button.classList.add("copied");
    setTimeout(() => {
      button.textContent = original;
      button.classList.remove("copied");
    }, 1600);
  }
}

function showCommand(command, copied) {
  elements.searchStatus.textContent = "";
  elements.searchStatus.classList.remove("error");

  const label = document.createElement("span");
  label.textContent = copied
    ? "Copied. Paste it into Claude Code:"
    : "Select this and copy it into Claude Code:";

  const field = document.createElement("input");
  field.type = "text";
  field.readOnly = true;
  field.value = command;
  field.className = "command-field";

  elements.searchStatus.append(label, field);
  field.focus();
  field.select();
}

function bandThresholds(rows) {
  const distinct = [...new Set(rows.map((row) => parseInt(row.score, 10)))]
    .filter((value) => !Number.isNaN(value))
    .sort((a, b) => b - a);
  return { high: distinct[0], mid: distinct[1] };
}

function scoreBand(score, thresholds) {
  const value = parseInt(score, 10);
  if (Number.isNaN(value)) return "";
  if (value === thresholds.high) return "band-high";
  if (value === thresholds.mid) return "band-mid";
  return "";
}

function buildRow(row, thresholds) {
  const tr = document.createElement("tr");
  tr.className = scoreBand(row.score, thresholds);

  const score = document.createElement("td");
  score.className = "score";
  score.textContent = row.score;
  tr.append(score);

  const name = document.createElement("td");
  name.className = "name";
  name.textContent = row.name;
  tr.append(name);

  const address = document.createElement("td");
  address.className = "address";
  address.textContent = row.address || "—";
  tr.append(address);

  const rating = document.createElement("td");
  rating.className = "numeric";
  rating.textContent = row.rating || "—";
  tr.append(rating);

  const reviews = document.createElement("td");
  reviews.className = "numeric";
  reviews.textContent = row.review_count || "—";
  tr.append(reviews);

  const website = document.createElement("td");
  const badge = document.createElement("span");
  const hasWebsite = Boolean((row.website || "").trim());
  badge.className = "tag " + (hasWebsite ? "has-site" : "no-site");
  badge.textContent = hasWebsite ? "has website" : "no website";
  website.append(badge);
  tr.append(website);

  const siteScore = document.createElement("td");
  siteScore.className = "numeric site-score";
  if (row.website_score === "" || row.website_score === undefined) {
    siteScore.textContent = "—";
  } else {
    const value = parseInt(row.website_score, 10);
    siteScore.textContent = value;
    if (state.poorWebsiteBelow !== null) {
      siteScore.classList.add(value < state.poorWebsiteBelow ? "poor" : "fine");
    }
    if (row.website_problems) {
      siteScore.title = row.website_problems.split("; ").join("\n");
      siteScore.classList.add("has-detail");
    }
  }
  tr.append(siteScore);

  const phone = document.createElement("td");
  phone.className = "phone";
  phone.textContent = row.phone || "—";
  tr.append(phone);

  const hours = document.createElement("td");
  hours.className = "hours";
  hours.textContent = row.opening_hours || "—";
  tr.append(hours);

  const links = document.createElement("td");
  links.className = "links";
  if (row.google_maps_link) {
    links.append(linkElement(row.google_maps_link, "maps"));
  }
  if (row.map_pin) {
    links.append(linkElement(row.map_pin, "pin"));
  }
  const websiteLink = websiteHref(row.website);
  if (websiteLink) {
    links.append(linkElement(websiteLink, "site"));
  }
  const email = (row.email || "").split(/[;,]/)[0].trim();
  if (email) {
    const mail = linkElement("mailto:" + email, "mail");
    mail.removeAttribute("target");
    links.append(mail);
  }
  [["instagram", row.instagram], ["facebook", row.facebook]].forEach(([site, value]) => {
    const href = profileHref(value, site);
    if (href) links.append(linkElement(href, site));
  });
  if (row.contact_search) {
    links.append(linkElement(row.contact_search, "contact"));
  }
  tr.append(links);

  const status = document.createElement("td");
  status.append(statusSelect(row));
  tr.append(status);

  const brief = document.createElement("td");
  const briefButton = document.createElement("button");
  briefButton.type = "button";
  briefButton.className = "secondary";
  briefButton.textContent = "Create brief";
  briefButton.title = "Copies the command, then paste it into Claude Code";
  briefButton.addEventListener("click", () => copyBriefCommand(row, briefButton));
  brief.append(briefButton);
  tr.append(brief);

  return tr;
}

function render() {
  const rows = visibleRows();
  const thresholds = bandThresholds(rows);
  elements.body.innerHTML = "";
  rows.forEach((row) => elements.body.append(buildRow(row, thresholds)));

  const withoutWebsite = rows.filter((row) => !(row.website || "").trim()).length;
  elements.resultCount.textContent = state.file
    ? rows.length + " of " + state.rows.length + " shown · " + withoutWebsite + " without a website"
    : "";

  elements.empty.hidden = rows.length > 0;
  if (!rows.length) {
    if (state.rows.length) {
      elements.empty.textContent = "No business matches these filters.";
    } else {
      elements.empty.innerHTML =
        "Search a trade and a city to start. Try <code>picerija Novi Sad</code>.";
    }
  }

  document.querySelectorAll("th.sortable").forEach((header) => {
    header.classList.remove("sorted-asc", "sorted-desc");
    if (header.dataset.sort === state.sortColumn) {
      header.classList.add(state.sortAscending ? "sorted-asc" : "sorted-desc");
    }
  });
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = elements.query.value.trim();
  if (!query) {
    setMessage("Enter a search first.", true);
    return;
  }

  elements.overlay.hidden = false;
  elements.searchButton.disabled = true;
  setMessage("");

  try {
    const body = { query };
    if (elements.limit.value) {
      body.limit = parseInt(elements.limit.value, 10);
    }
    const data = await requestJson("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    let message =
      "Found " + data.found + " businesses, " + data.without_website + " without a website. " +
      "Source: " + data.source + ".";
    if (data.merged_with) {
      message += " Merged with the earlier file, what you typed by hand was kept.";
    }
    setMessage(message);

    await loadFiles(data.file);
    await loadUsage();
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    elements.overlay.hidden = true;
    elements.searchButton.disabled = false;
  }
});

elements.fileSelect.addEventListener("change", async () => {
  try {
    await loadLeads(elements.fileSelect.value);
    setMessage("");
  } catch (error) {
    setMessage(error.message, true);
  }
});

[elements.onlyNoWebsite, elements.minRating, elements.minReviews].forEach((control) => {
  control.addEventListener("input", render);
});

document.querySelectorAll("th.sortable").forEach((header) => {
  header.addEventListener("click", () => {
    const column = header.dataset.sort;
    if (state.sortColumn === column) {
      state.sortAscending = !state.sortAscending;
    } else {
      state.sortColumn = column;
      state.sortAscending = !NUMERIC_COLUMNS.includes(column);
    }
    render();
  });
});

elements.exportButton.addEventListener("click", () => {
  if (state.file) {
    window.location.href = "/api/export?file=" + encodeURIComponent(state.file);
  }
});

loadUsage();
loadSettings()
  .catch((error) => setMessage(error.message, true))
  .then(() => loadFiles())
  .catch((error) => setMessage(error.message, true));

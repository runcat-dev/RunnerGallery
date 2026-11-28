const KNOWN_TAGS = ["animal", "dog", "object", "mechanism", "fitness"];
const TABS = ["monochrome", "color"];
const DEFAULT_TAB = "monochrome";

const state = {
  language: detectLanguage(),
  tab: DEFAULT_TAB,
  tags: new Set(),
  runners: [],
  statusKey: "loading",
};

function localized(key, replacements) {
  return translate(state.language, key, replacements);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return response.json();
}

function localizedDisplayName(runner) {
  return runner.displayName[state.language] ?? runner.displayName[DEFAULT_LANGUAGE];
}

function createRunnerCard(runner) {
  const card = document.createElement("article");
  card.className = "runner-card";
  const name = localizedDisplayName(runner);

  const preview = document.createElement("div");
  preview.className = "runner-preview";
  const previewImage = document.createElement("img");
  previewImage.src = `./runners/${runner.name}/preview.png`;
  previewImage.alt = localized("previewAlt", { name });
  previewImage.loading = "lazy";
  preview.appendChild(previewImage);

  const displayName = document.createElement("p");
  displayName.className = "runner-name";
  displayName.textContent = name;

  const author = document.createElement("p");
  author.className = "runner-author";
  author.textContent = localized("byAuthor", { author: runner.author });

  const downloadLink = document.createElement("a");
  downloadLink.className = "download-button";
  downloadLink.href = `./runners/${runner.name}/${runner.name}-frames.zip`;
  downloadLink.setAttribute("download", "");
  downloadLink.textContent = localized("download");

  card.append(preview, displayName, author, downloadLink);
  return card;
}

function setUpLanguageSelect() {
  const select = document.getElementById("language-select");
  select.replaceChildren(
    ...LANGUAGES.map(({ code, label }) => {
      const option = document.createElement("option");
      option.value = code;
      option.lang = code;
      option.textContent = label;
      return option;
    }),
  );
  select.addEventListener("change", () => {
    state.language = select.value;
    writeLanguageToQuery();
    applyLanguage();
    if (state.runners.length > 0) render();
  });
}

function writeLanguageToQuery() {
  const params = new URLSearchParams(window.location.search);
  params.set("lang", state.language);
  history.replaceState(null, "", `${window.location.pathname}?${params}${window.location.hash}`);
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  document.getElementById("language-select").value = state.language;
  for (const element of document.querySelectorAll("[data-i18n]")) {
    element.textContent = localized(element.dataset.i18n);
  }
  for (const element of document.querySelectorAll("[data-i18n-title]")) {
    element.title = localized(element.dataset.i18nTitle);
  }
  for (const element of document.querySelectorAll("[data-i18n-aria-label]")) {
    element.setAttribute("aria-label", localized(element.dataset.i18nAriaLabel));
  }
  renderContributeMessage();
  renderStatus();
}

function renderContributeMessage() {
  const message = document.getElementById("contribute-message");
  const link = document.getElementById("contribute-link");
  const [before, after = ""] = localized("contribute").split("{link}");
  message.replaceChildren(before, link, after);
}

function renderStatus() {
  const statusElement = document.getElementById("gallery-status");
  statusElement.hidden = state.statusKey === null;
  if (state.statusKey !== null) {
    statusElement.textContent = localized(state.statusKey);
  }
}

async function loadGallery() {
  const filtersElement = document.getElementById("filters");

  let runnerNames;
  try {
    const manifest = await fetchJson("./runners/manifest.json");
    runnerNames = manifest.runners;
  } catch {
    state.statusKey = "loadFailed";
    renderStatus();
    return;
  }

  const metadataResults = await Promise.allSettled(
    runnerNames.map((runnerName) =>
      fetchJson(`./runners/${runnerName}/metadata.json`).then((metadata) => ({
        name: runnerName,
        ...metadata,
      })),
    ),
  );

  state.runners = metadataResults
    .filter((result) => result.status === "fulfilled")
    .map((result) => result.value);

  if (state.runners.length === 0) {
    state.statusKey = "noRunners";
    renderStatus();
    return;
  }

  filtersElement.hidden = false;
  readStateFromHash();
  render();
  window.addEventListener("hashchange", () => {
    readStateFromHash();
    render();
  });
}

function readStateFromHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const tab = params.get("tab");
  state.tab = TABS.includes(tab) ? tab : DEFAULT_TAB;
  state.tags = new Set();
  const raw = params.get("tags");
  if (raw) {
    for (const tag of raw.split(",")) {
      if (KNOWN_TAGS.includes(tag)) state.tags.add(tag);
    }
  }
}

function writeStateToHash() {
  const params = new URLSearchParams();
  if (state.tab !== DEFAULT_TAB) params.set("tab", state.tab);
  if (state.tags.size > 0) params.set("tags", [...state.tags].join(","));
  const encoded = params.toString();
  const target = encoded ? `#${encoded}` : "";
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const next = `${window.location.pathname}${window.location.search}${target}`;
  if (current !== next) {
    history.replaceState(null, "", next);
  }
}

function isVisible(runner) {
  if (runner.type !== state.tab) return false;
  if (state.tags.size === 0) return true;
  return runner.tags.some((tag) => state.tags.has(tag));
}

function render() {
  renderTabs();
  renderTagChips();
  renderGrid();
  writeStateToHash();
}

function renderTabs() {
  const container = document.getElementById("tabs");
  container.replaceChildren();
  for (const type of TABS) {
    const count = state.runners.filter((runner) => runner.type === type).length;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab" + (state.tab === type ? " active" : "");
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", state.tab === type ? "true" : "false");
    button.textContent = `${localized(`type.${type}`)} (${count})`;
    button.addEventListener("click", () => {
      if (state.tab === type) return;
      state.tab = type;
      render();
    });
    container.appendChild(button);
  }
}

function renderTagChips() {
  const container = document.getElementById("tag-chips");
  container.replaceChildren();
  const runnersInTab = state.runners.filter((runner) => runner.type === state.tab);
  for (const tag of KNOWN_TAGS) {
    const count = runnersInTab.filter((runner) => runner.tags.includes(tag)).length;
    const isActive = state.tags.has(tag);
    if (count === 0 && !isActive) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip" + (isActive ? " active" : "");
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
    button.textContent = `${localized(`tag.${tag}`)} (${count})`;
    button.addEventListener("click", () => {
      if (isActive) state.tags.delete(tag);
      else state.tags.add(tag);
      render();
    });
    container.appendChild(button);
  }
  if (state.tags.size > 0) {
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "chip chip-clear";
    clearButton.textContent = localized("clear");
    clearButton.addEventListener("click", () => {
      state.tags.clear();
      render();
    });
    container.appendChild(clearButton);
  }
}

function renderGrid() {
  const grid = document.getElementById("runner-grid");
  const shown = state.runners.filter(isVisible);
  grid.replaceChildren(...shown.map(createRunnerCard));
  state.statusKey = shown.length === 0 ? "noMatch" : null;
  renderStatus();
}

setUpLanguageSelect();
applyLanguage();
loadGallery();

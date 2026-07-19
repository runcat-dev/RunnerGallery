const KNOWN_TAGS = ["animal", "dog", "object", "mechanism", "fitness"];
const TABS = [
  { type: "monochrome", label: "Monochrome" },
  { type: "color", label: "Color" },
];
const DEFAULT_TAB = "monochrome";

const state = {
  tab: DEFAULT_TAB,
  tags: new Set(),
  runners: [],
};

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return response.json();
}

function createRunnerCard(runner) {
  const card = document.createElement("article");
  card.className = "runner-card";

  const preview = document.createElement("div");
  preview.className = "runner-preview";
  const previewImage = document.createElement("img");
  previewImage.src = `./runners/${runner.name}/preview.png`;
  previewImage.alt = `${runner.displayName} animation preview`;
  previewImage.loading = "lazy";
  preview.appendChild(previewImage);

  const displayName = document.createElement("p");
  displayName.className = "runner-name";
  displayName.textContent = runner.displayName;

  const author = document.createElement("p");
  author.className = "runner-author";
  author.textContent = `by ${runner.author}`;

  const downloadLink = document.createElement("a");
  downloadLink.className = "download-button";
  downloadLink.href = `./runners/${runner.name}/${runner.name}-frames.zip`;
  downloadLink.setAttribute("download", "");
  downloadLink.textContent = "Download";

  card.append(preview, displayName, author, downloadLink);
  return card;
}

async function loadGallery() {
  const statusElement = document.getElementById("gallery-status");
  const filtersElement = document.getElementById("filters");

  let runnerNames;
  try {
    const manifest = await fetchJson("./runners/manifest.json");
    runnerNames = manifest.runners;
  } catch {
    statusElement.textContent = "Failed to load the runner list. Please reload the page.";
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
    statusElement.textContent = "No runners available yet.";
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
  state.tab = TABS.some((entry) => entry.type === tab) ? tab : DEFAULT_TAB;
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
  for (const { type, label } of TABS) {
    const count = state.runners.filter((runner) => runner.type === type).length;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab" + (state.tab === type ? " active" : "");
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", state.tab === type ? "true" : "false");
    button.textContent = `${label} (${count})`;
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
    button.textContent = `${tag} (${count})`;
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
    clearButton.textContent = "Clear";
    clearButton.addEventListener("click", () => {
      state.tags.clear();
      render();
    });
    container.appendChild(clearButton);
  }
}

function renderGrid() {
  const grid = document.getElementById("runner-grid");
  const statusElement = document.getElementById("gallery-status");
  const shown = state.runners.filter(isVisible);
  grid.replaceChildren(...shown.map(createRunnerCard));
  if (shown.length === 0) {
    statusElement.hidden = false;
    statusElement.textContent = "No runners match the current filters.";
  } else {
    statusElement.hidden = true;
  }
}

loadGallery();

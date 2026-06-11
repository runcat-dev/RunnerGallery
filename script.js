async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return response.json();
}

function createRunnerCard(runnerName, metadata) {
  const card = document.createElement("article");
  card.className = "runner-card";

  const preview = document.createElement("div");
  preview.className = "runner-preview";
  const previewImage = document.createElement("img");
  previewImage.src = `./runners/${runnerName}/preview.gif`;
  previewImage.alt = `${metadata.displayName} animation preview`;
  previewImage.loading = "lazy";
  preview.appendChild(previewImage);

  const displayName = document.createElement("p");
  displayName.className = "runner-name";
  displayName.textContent = metadata.displayName;

  const author = document.createElement("p");
  author.className = "runner-author";
  author.textContent = `by ${metadata.author}`;

  const downloadLink = document.createElement("a");
  downloadLink.className = "download-button";
  downloadLink.href = `./runners/${runnerName}/${runnerName}-frames.zip`;
  downloadLink.setAttribute("download", "");
  downloadLink.textContent = "Download";

  card.append(preview, displayName, author, downloadLink);
  return card;
}

async function loadGallery() {
  const galleryStatus = document.getElementById("gallery-status");
  const runnerGrid = document.getElementById("runner-grid");

  let runnerNames;
  try {
    const manifest = await fetchJson("./runners/manifest.json");
    runnerNames = manifest.runners;
  } catch {
    galleryStatus.textContent = "Failed to load the runner list. Please reload the page.";
    return;
  }

  const metadataResults = await Promise.allSettled(
    runnerNames.map((runnerName) => fetchJson(`./runners/${runnerName}/metadata.json`))
  );

  const cards = [];
  metadataResults.forEach((result, index) => {
    if (result.status === "fulfilled") {
      cards.push(createRunnerCard(runnerNames[index], result.value));
    }
  });

  if (cards.length === 0) {
    galleryStatus.textContent = "No runners available yet.";
    return;
  }

  galleryStatus.hidden = true;
  runnerGrid.append(...cards);
}

loadGallery();

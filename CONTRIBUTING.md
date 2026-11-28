# Contributing to Runner Gallery

Thank you for your interest in sharing your custom runner!
This repository distributes custom runner resources for [RunCat Neo](https://runcat-dev.github.io/RunCatNeo/), browsable at <https://runcat-dev.github.io/RunnerGallery/>.

## How to Add a Runner

### 1. Choose a runner name

Use a lowercase, hyphen-separated name (e.g., `welsh-corgi`). This name is used for the directory and file names.

### 2. Prepare the files

Place the following files in `runners/<runner-name>/`:

```
runners/
└── <runner-name>/
    ├── frames/
    │   ├── <runner-name>-frame-0.png
    │   ├── <runner-name>-frame-1.png
    │   └── ...
    ├── metadata.json
    └── preview.png
```

#### `frames/`

The animation frames, committed as individual PNG files.
Do not zip them; the gallery builds the downloadable zip from these files and `metadata.json`.

Frame requirements:

- Format: PNG, not interlaced
- File name: `<runner-name>-frame-<N>.png`, numbered consecutively from `0`
- Count: between 2 and 30 frames
- Height: exactly 36px
- Width: between 10px and 100px
- All frames must have the same size
- A transparent background is recommended
- `frames/` must contain nothing but the frames — no Finder-generated files such as `.DS_Store` or `._*`

#### `metadata.json`

```json
{
  "author": "Your Name (YourGitHubID)",
  "displayName": {
    "en": "Rabbit",
    "de": "Kaninchen",
    "es": "Conejo",
    "fr": "Lapin",
    "ja": "ウサギ",
    "ko": "토끼",
    "ru": "Кролик",
    "vi": "Thỏ",
    "zh-Hans": "兔子",
    "zh-Hant": "兔子"
  },
  "type": "monochrome",
  "tags": ["animal"]
}
```

`displayName` is the runner's name in every language the gallery supports, keyed by language code.
All ten languages are required: `en`, `de`, `es`, `fr`, `ja`, `ko`, `ru`, `vi`, `zh-Hans`, and `zh-Hant`.
If you are not fluent in some of them, a machine translation is fine.

`type` must be one of:

- `monochrome` — grayscale or single-color runners
- `color` — runners that use more than one hue

`tags` is a list of tags, chosen from this closed set:

| tag | meaning |
|---|---|
| `animal` | Any living creature, including fictional ones (excludes human-shaped characters) |
| `dog` | Dogs. Requires `animal` as well |
| `object` | Inanimate objects, tools, geometric shapes |
| `mechanism` | Moving mechanical devices. Requires `object` as well |
| `fitness` | Exercise or workout-themed runners |

Guidelines:

- A runner PR may only use tags from the table above. If nothing fits, use an empty array `[]`.
- Human-shaped characters do not receive `animal`.
- Prefer fewer tags when unsure. Extra tags can always be added later.
- A new tag must be proposed in its own PR, separate from any runner PR. That PR updates this table, `KNOWN_TAGS` in both `.github/scripts/validate_runners.py` and `script.js`, and the tag's label for every language in `i18n.js`.

#### `preview.png`

An animated PNG (APNG) used for the gallery preview:

- Format: APNG, not interlaced (a static PNG will not animate in the gallery)
- Height: 36px
- Width: at most 100px

### 3. Update the manifest

Add your runner name to `runners/manifest.json`. Keep the list sorted alphabetically. CI enforces this.

```json
{
  "runners": [
    "beagle",
    "your-runner-name"
  ]
}
```

### 4. Check your runner locally

Every Pull Request is automatically checked: `frames/` must contain nothing but your frames, and every image must be a genuine, fully decodable PNG.
You can run exactly the same checks yourself before pushing, so that you do not have to wait for CI:

```sh
pip install -r .github/scripts/requirements.txt
python3 .github/scripts/validate_runners.py --all
```

Anything it reports tells you which file is at fault and what to change.

### 5. Open a Pull Request

Add only one runner per Pull Request.
If you want to add several runners, open a separate Pull Request for each one.
A Pull Request that bundles multiple runners cannot be reviewed and will be closed.

1. Fork this repository and create a branch.
2. Commit your runner files and the manifest change.
3. Open a Pull Request and fill in the template, including the checklist.

## Licensing and Originality

- By submitting a runner, you agree that it will be distributed under this repository's [Apache-2.0 license](LICENSE).
- The runner must be your original work, or you must hold the rights to it.
- Runners containing third-party intellectual property (e.g., Pokémon, Mario, or other copyrighted/trademarked characters) cannot be accepted, even as fan art.
- Classic RunCat runners are revived only by the maintainer, who adjusts every frame again before adding them to the gallery.
  Please do not submit them yourself; to ask for one, open a [Runner Request](https://github.com/runcat-dev/RunnerGallery/issues/new?template=runner-request.yml) instead.

## Previewing the Site Locally

The gallery page loads `runners/manifest.json` with `fetch()`, which does not work over `file://`. Run a local server from the repository root instead:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000/> in your browser.

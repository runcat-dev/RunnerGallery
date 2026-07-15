# Contributing to Runner Gallery

Thank you for your interest in sharing your custom runner!
This repository distributes custom runner resources for [RunCat Neo](https://runcat-dev.github.io/RunCatNeo/), browsable at <https://runcat-dev.github.io/RunnerGallery/>.

## How to Add a Runner

### 1. Choose a runner name

Use a lowercase, hyphen-separated name (e.g., `welsh-corgi`). This name is used for the directory and file names.

### 2. Prepare the files

Place the following three files in `runners/<runner-name>/`:

```
runners/
└── <runner-name>/
    ├── <runner-name>-frames.zip
    ├── metadata.json
    └── preview.png
```

#### `<runner-name>-frames.zip`

A zip archive of a `<runner-name>-frames/` directory containing the animation frames:

```
<runner-name>-frames/
├── <runner-name>-frame-0.png
├── <runner-name>-frame-1.png
└── ...
```

Frame requirements:

- Format: PNG
- Height: exactly 36px
- Width: between 10px and 100px
- All frames must have the same size
- A transparent background is recommended
- Avoid including Finder-generated files such as `.DS_Store`, `__MACOSX/`, and `._*` in the zip

Tip for macOS users — creating the zip from the command line avoids Finder-generated junk:

```sh
zip -r <runner-name>-frames.zip <runner-name>-frames -x "*.DS_Store" "__MACOSX/*"
```

#### `metadata.json`

```json
{
  "author": "Your Name (YourGitHubID)",
  "displayName": "Display Name"
}
```

#### `preview.png`

An animated PNG (APNG) used for the gallery preview:

- Format: APNG (a static PNG will not animate in the gallery)
- Height: 36px
- Width: at most 100px

### 3. Update the manifest

Add your runner name to `runners/manifest.json`, following the existing ordering of the list:

```json
{
  "runners": [
    "beagle",
    "your-runner-name"
  ]
}
```

### 4. Open a Pull Request

1. Fork this repository and create a branch.
2. Commit your runner files and the manifest change.
3. Open a Pull Request and fill in the template, including the checklist.

## Licensing and Originality

- By submitting a runner, you agree that it will be distributed under this repository's [Apache-2.0 license](LICENSE).
- The runner must be your original work, or you must hold the rights to it.
- Runners containing third-party intellectual property (e.g., Pokémon, Mario, or other copyrighted/trademarked characters) cannot be accepted, even as fan art.

## Previewing the Site Locally

The gallery page loads `runners/manifest.json` with `fetch()`, which does not work over `file://`. Run a local server from the repository root instead:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000/> in your browser.

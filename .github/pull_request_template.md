# Pull Request

## Type of Change

- [ ] Add a new runner
- [ ] Fix or improve an existing runner
- [ ] Other (site, docs, tooling)

## Runner Summary

<!-- For runner changes: the runner name and a short description of the character/animation. -->

## Checklist for Adding a Runner

- [ ] All frames are PNG files with a height of exactly 36px, a width between 10px and 100px, and all frames share the same size.
- [ ] The runner is my original work, or I hold the rights to it, and I consent to its distribution under this repository's license (Apache-2.0).
- [ ] The runner does NOT contain third-party intellectual property (e.g., Pokémon, Mario, or other copyrighted/trademarked characters).
- [ ] Files are placed at `runners/<runner-name>/` as `<runner-name>-frames.zip`, `metadata.json`, and `preview.png`.
- [ ] `runners/manifest.json` includes the new runner name, following the existing ordering of the list.
- [ ] `metadata.json` contains the correct `displayName` and `author`.
- [ ] `preview.png` is an animated PNG (APNG), 36px tall, at most 100px wide, and animates correctly.
- [ ] I have read [CONTRIBUTING.md](https://github.com/runcat-dev/RunnerGallery/blob/main/CONTRIBUTING.md) and followed the steps described there.

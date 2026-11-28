#!/usr/bin/env python3
"""Assemble the GitHub Pages site into `_site/`, including each runner's
downloadable zip.

A runner's zip is generated rather than committed so that `metadata.json`
and `frames/` stay the only source of truth. Every zip holds the runner's
`metadata.json` byte for byte, followed by `frames/<name>-frame-N.png` in
frame order, and is built deterministically: the same inputs always produce
the same bytes.

Frames are taken from the git index, the same list `validate_runners.py`
checks, so an untracked file in a local checkout never reaches a zip. Run
`validate_runners.py` first; this script trusts its inputs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

OUTPUT_DIRECTORY = "_site"
STATIC_FILES = ("index.html", "script.js", "style.css", "i18n.js")
MANIFEST_PATH = "runners/manifest.json"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REGULAR_FILE_ATTRIBUTES = 0o100644 << 16


def tracked_frame_paths(root: Path, name: str) -> list[Path]:
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", f"runners/{name}/frames"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    frame_re = re.compile(rf"runners/{re.escape(name)}/frames/{re.escape(name)}-frame-(0|[1-9][0-9]*)\.png")
    frames: dict[int, Path] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8")
        match = frame_re.fullmatch(path)
        if match is None:
            raise SystemExit(f"`{path}` is not a frame file. Run validate_runners.py first.")
        frames[int(match.group(1))] = root / path
    return [frames[index] for index in sorted(frames)]


def add_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = REGULAR_FILE_ATTRIBUTES
    archive.writestr(entry, data)


def build_runner_zip(root: Path, name: str, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w") as archive:
        add_entry(archive, "metadata.json", (root / "runners" / name / "metadata.json").read_bytes())
        for frame in tracked_frame_paths(root, name):
            add_entry(archive, f"frames/{frame.name}", frame.read_bytes())


def build_site(root: Path) -> list[str]:
    output = root / OUTPUT_DIRECTORY
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    for filename in STATIC_FILES:
        shutil.copy2(root / filename, output / filename)

    (output / "runners").mkdir()
    shutil.copy2(root / MANIFEST_PATH, output / MANIFEST_PATH)

    names = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["runners"]
    for name in names:
        source = root / "runners" / name
        destination = output / "runners" / name
        destination.mkdir()
        shutil.copy2(source / "metadata.json", destination / "metadata.json")
        shutil.copy2(source / "preview.png", destination / "preview.png")
        build_runner_zip(root, name, destination / f"{name}.zip")
    return names


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    names = build_site(root)
    print(f"Built {len(names)} runners into {root / OUTPUT_DIRECTORY}")


if __name__ == "__main__":
    main()

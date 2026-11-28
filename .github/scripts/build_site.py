#!/usr/bin/env python3
"""Assemble the GitHub Pages site, including each runner's downloadable zip.

A runner's zip is generated rather than committed so that `metadata.json`
and `frames/` stay the only source of truth. Every zip holds the runner's
`metadata.json` byte for byte, followed by `frames/<name>-frame-N.png` in
frame order, and is built deterministically: the same inputs always produce
the same bytes.

Run `validate_runners.py` first; this script trusts its inputs.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

STATIC_FILES = ("index.html", "script.js", "style.css", "i18n.js")
MANIFEST_PATH = "runners/manifest.json"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REGULAR_FILE_ATTRIBUTES = 0o100644 << 16


def frame_index(path: Path) -> int:
    match = re.search(r"-frame-(\d+)\.png$", path.name)
    if match is None:
        raise ValueError(f"{path} is not a frame file")
    return int(match.group(1))


def add_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = REGULAR_FILE_ATTRIBUTES
    archive.writestr(entry, data)


def build_runner_zip(runner_directory: Path, destination: Path) -> None:
    frames = sorted((runner_directory / "frames").glob("*.png"), key=frame_index)
    with zipfile.ZipFile(destination, "w") as archive:
        add_entry(archive, "metadata.json", (runner_directory / "metadata.json").read_bytes())
        for frame in frames:
            add_entry(archive, f"frames/{frame.name}", frame.read_bytes())


def build_site(root: Path, output: Path) -> list[str]:
    if root.is_relative_to(output):
        raise SystemExit(f"Refusing to build into {output}, which contains the repository.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

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
        build_runner_zip(source, destination / f"{name}.zip")
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble the GitHub Pages site.")
    parser.add_argument("output", nargs="?", default="_site", help="output directory (default: _site)")
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    output = Path(arguments.output).resolve()
    names = build_site(root, output)
    print(f"Built {len(names)} runners into {output}")


if __name__ == "__main__":
    main()

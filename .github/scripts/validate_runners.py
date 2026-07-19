#!/usr/bin/env python3
"""Validate contributor-submitted runner assets.

Runs read-only against the git index. See CONTRIBUTING.md for the rules this
enforces. The security-relevant part is that every byte of every distributed
zip is proven to belong to a well-formed PNG: the archive may contain nothing
but PNG files, and each PNG must consist entirely of CRC-valid chunks ending at
IEND with no trailing bytes. That leaves nowhere to hide a payload.
"""

from __future__ import annotations

import argparse
import binascii
import io
import json
import os
import re
import struct
import subprocess
import sys
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = 1_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)

MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 8 * 1024 * 1024
MAX_ENTRY_UNCOMPRESSED = 1 * 1024 * 1024
MAX_ENTRIES = 64
MAX_RATIO = 200
MAX_PNG_BYTES = 512 * 1024
MAX_TEXT_CHUNK_BYTES = 4 * 1024
MAX_JSON_BYTES = 4 * 1024
MAX_ENTRY_NAME_LENGTH = 200
MAX_METADATA_VALUE_LENGTH = 100
MAX_REPORTED_UNEXPECTED = 3

FRAME_HEIGHT = 36
MIN_WIDTH = 10
MAX_WIDTH = 100
MIN_FRAMES = 2

RUNNER_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EOCD_SIGNATURE = b"PK\x05\x06"
EOCD_SIZE = 22

ZIP_REGULAR_FILE = 0o100000
ZIP_DIRECTORY = 0o040000
ZIP_SYMLINK = 0o120000
ZIP_FORMAT_MASK = 0o170000

DOS_HIDDEN = 0x02
DOS_SYSTEM = 0x04

REZIP_COMMAND = '`zip -r {name}-frames.zip {name}-frames -x "*.DS_Store" "__MACOSX/*"`'
REZIP_HINT = "Re-create the zip from the terminal: " + REZIP_COMMAND

# Phrased so that one reason reads correctly for either a single entry or many
# ("`x` is macOS Finder metadata" / "`x`, `y` are macOS Finder metadata").
JUNK_REASONS = {
    "__MACOSX": "macOS Finder metadata. " + REZIP_HINT,
    ".DS_Store": "macOS Finder metadata. " + REZIP_HINT,
    "Thumbs.db": "Windows Explorer thumbnail cache data. Delete it and re-create the zip.",
    "desktop.ini": "Windows folder-settings data. Delete it and re-create the zip.",
}
APPLEDOUBLE_REASON = "macOS AppleDouble metadata. " + REZIP_HINT
HIDDEN_REASON = "hidden. The archive must contain only the frame PNGs."

EXPECTED_FILES = ("{name}-frames.zip", "metadata.json", "preview.png")
METADATA_KEYS = {"author", "displayName", "type", "tags"}
METADATA_STRING_KEYS = {"author", "displayName", "type"}
RUNNER_TYPES = ("monochrome", "color")
KNOWN_TAGS = ("animal", "dog", "object", "mechanism", "fitness")
TAG_HIERARCHY = {"dog": "animal", "mechanism": "object"}
TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_TAGS = 8


class PngError(Exception):
    pass


@dataclass
class Problem:
    runner: str | None
    file: str
    message: str


@dataclass
class Report:
    problems: list[Problem] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    internal_error: bool = False

    def error(self, runner: str | None, file: str, message: str) -> None:
        self.problems.append(Problem(runner, file, message))

    @property
    def failed(self) -> bool:
        return bool(self.problems)

    def runners_with_errors(self) -> list[str]:
        names: list[str] = []
        for problem in self.problems:
            if problem.runner not in names:
                names.append(problem.runner)
        return names


def run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def git_tracked(root: Path) -> dict[str, str]:
    """Map every tracked path under runners/ to its git mode.

    The git index rather than the filesystem, so that gitignored local junk
    (the maintainer has untracked .DS_Store files) never produces a finding,
    and so that what is validated is exactly what is committed. The mode comes
    along for free and reveals symlinks (120000) and exec bits (100755).
    """
    output = run_git(root, "ls-files", "-s", "-z", "--", "runners")
    tracked = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        info, _, path = record.partition(b"\t")
        mode = info.split(b" ", 1)[0].decode("ascii")
        tracked[path.decode("utf-8", "surrogateescape")] = mode
    return tracked


def changed_runners(root: Path, base_sha: str) -> set[str]:
    output = run_git(root, "diff", "--name-only", "-z", base_sha, "HEAD")
    names = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", "surrogateescape")
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "runners":
            names.add(parts[1])
    return names


def runner_names_on_disk(tracked: dict[str, str]) -> list[str]:
    names = set()
    for path in tracked:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "runners":
            names.add(parts[1])
    return sorted(names)


def check_entry_name(raw: str) -> str | None:
    if "\x00" in raw:
        return "contains a NUL byte"
    if not raw.isascii():
        return "contains non-ASCII characters"
    if "\\" in raw:
        return "contains a backslash (a Windows-style path separator)"
    if raw.startswith("/"):
        return "is an absolute path"
    if len(raw) > 1 and raw[1] == ":":
        return "contains a drive letter"
    parts = raw.rstrip("/").split("/")
    if any(part == ".." for part in parts):
        return "escapes the archive root (`..`)"
    if any(part in ("", ".") for part in parts):
        return "contains an empty or `.` path component"
    if len(raw) > MAX_ENTRY_NAME_LENGTH:
        return "is unreasonably long"
    return None


def check_zip_container(data: bytes, runner: str, path: str, report: Report) -> bool:
    index = data.rfind(EOCD_SIGNATURE)
    if index < 0 or len(data) - index < EOCD_SIZE:
        report.error(
            runner, path, "Not a valid zip archive (no end-of-central-directory record)."
        )
        return False

    cd_size, cd_offset = struct.unpack_from("<II", data, index + 12)
    (comment_length,) = struct.unpack_from("<H", data, index + 20)
    ok = True

    if comment_length:
        report.error(runner, path, "The zip has an archive comment. " + REZIP_HINT.format(name=runner))
        ok = False

    trailing = len(data) - (index + EOCD_SIZE + comment_length)
    if trailing:
        report.error(
            runner,
            path,
            f"{trailing} bytes of data follow the end of the zip archive. A zip must "
            "end at its central directory; extra bytes are how payloads get smuggled "
            "into an otherwise valid archive.",
        )
        ok = False

    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        report.error(
            runner,
            path,
            "This is a Zip64 archive. A runner frame archive should be a few tens of kilobytes.",
        )
        ok = False
    elif cd_offset + cd_size != index:
        report.error(
            runner,
            path,
            "The central directory is not where the archive header says it is, so data "
            "appears to be prepended to the zip (a self-extracting stub?).",
        )
        ok = False

    return ok


def check_entry_metadata(entry: zipfile.ZipInfo, runner: str, path: str, report: Report) -> bool:
    ok = True
    name = entry.filename

    if entry.flag_bits & 0x1 or entry.flag_bits & 0x40:
        report.error(runner, path, f"`{name}` is encrypted. Runner archives must not be password-protected.")
        ok = False

    if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        report.error(
            runner,
            path,
            f"`{name}` uses compression method {entry.compress_type}; only stored and deflate are accepted.",
        )
        ok = False

    is_directory = name.endswith("/")
    mode = entry.external_attr >> 16

    if mode:
        # A zero format field means the writer only recorded permission bits
        # (Python's zipfile.writestr does exactly this). Extractors treat that
        # as a regular file, so only reject a format that is present and wrong.
        file_format = mode & ZIP_FORMAT_MASK
        if file_format and file_format not in (ZIP_REGULAR_FILE, ZIP_DIRECTORY):
            kind = "symbolic link" if file_format == ZIP_SYMLINK else "special file"
            report.error(runner, path, f"`{name}` is a {kind}. Only regular PNG files are allowed.")
            ok = False
        if mode & 0o7000:
            report.error(runner, path, f"`{name}` has setuid, setgid, or sticky bits set.")
            ok = False
        if not is_directory and mode & 0o111:
            report.error(runner, path, f"`{name}` has the executable bit set. Image files must not be executable.")
            ok = False
    else:
        dos_attributes = entry.external_attr & 0xFF
        if dos_attributes & DOS_HIDDEN:
            report.error(runner, path, f"`{name}` is marked hidden.")
            ok = False
        if dos_attributes & DOS_SYSTEM:
            report.error(runner, path, f"`{name}` is marked as a system file.")
            ok = False

    return ok


def walk_png_chunks(data: bytes) -> list[tuple[str, int, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("it does not start with the PNG signature (this is not a PNG file)")

    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[str, int, bytes]] = []
    seen_iend = False

    while offset < len(data):
        if seen_iend:
            raise PngError(
                f"{len(data) - offset} bytes of data follow the IEND chunk; a PNG must end at IEND"
            )
        if len(data) - offset < 12:
            raise PngError("a chunk header is truncated")

        (length,) = struct.unpack_from(">I", data, offset)
        chunk_type = data[offset + 4 : offset + 8]
        if not chunk_type.isalpha():
            raise PngError("a chunk type is not four ASCII letters")
        if length > MAX_PNG_BYTES:
            raise PngError(f"chunk {chunk_type.decode()} declares an implausible length ({length} bytes)")

        end = offset + 12 + length
        if end > len(data):
            raise PngError(f"chunk {chunk_type.decode()} runs past the end of the file")

        payload = data[offset + 8 : offset + 8 + length]
        (expected_crc,) = struct.unpack_from(">I", data, offset + 8 + length)
        if binascii.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise PngError(
                f"chunk {chunk_type.decode()} has a CRC mismatch (the file is corrupt or was tampered with)"
            )

        chunks.append((chunk_type.decode("ascii"), length, payload))
        if chunk_type == b"IEND":
            seen_iend = True
        offset = end

    if not seen_iend:
        raise PngError("it has no IEND chunk (the file is truncated)")
    if chunks[0][0] != "IHDR":
        raise PngError("its first chunk is not IHDR")
    return chunks


def check_png(
    data: bytes,
    *,
    label: str,
    path: str,
    runner: str | None,
    report: Report,
    require_apng: bool,
) -> tuple[int, int] | None:
    if len(data) > MAX_PNG_BYTES:
        report.error(
            runner,
            path,
            f"{label} is {len(data)} bytes, far larger than a 36px-tall image should ever be.",
        )
        return None

    try:
        chunks = walk_png_chunks(data)
    except PngError as error:
        report.error(runner, path, f"{label} is not a well-formed PNG: {error}.")
        return None

    types = [chunk_type for chunk_type, _, _ in chunks]
    header = chunks[0][2]
    if len(header) < 13:
        report.error(runner, path, f"{label} has a truncated IHDR chunk.")
        return None
    width, height, _, _, _, _, interlace = struct.unpack_from(">IIBBBBB", header, 0)

    # Adam7 pointlessly interlaces an image this small, and Pillow cannot decode
    # the frames of an interlaced APNG at all, so it would also cost us the
    # full-decode check that proves the file is really an image. The IHDR is
    # CRC-verified, so the size is still worth reporting against.
    if interlace:
        report.error(
            runner,
            path,
            f"{label} uses Adam7 interlacing, which is not supported. Re-export it without "
            'interlacing (in most tools this is the default, or an "interlaced" checkbox to '
            "leave unticked).",
        )
        return width, height

    for chunk_type, length, _ in chunks:
        if chunk_type in ("tEXt", "zTXt", "iTXt") and length > MAX_TEXT_CHUNK_BYTES:
            report.error(
                runner,
                path,
                f"{label} has a {length}-byte `{chunk_type}` metadata chunk, which is implausibly "
                "large for a runner image and a common place to hide a payload. Strip the metadata "
                "and export it again.",
            )

    if require_apng:
        if "acTL" not in types:
            report.error(
                runner,
                path,
                f"{label} is a static PNG, not an APNG (it has no `acTL` chunk), so it will not "
                "animate in the gallery.",
            )
        elif "IDAT" in types and types.index("acTL") > types.index("IDAT"):
            report.error(runner, path, f"{label} has its `acTL` chunk after `IDAT`, which is not a valid APNG.")

    # Force every pixel of every frame through zlib and libpng. A file that
    # merely has valid chunk framing still has to survive this to be an image.
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            for index in range(getattr(image, "n_frames", 1)):
                image.seek(index)
                image.load()
    except Exception as error:
        report.error(runner, path, f"{label} could not be decoded as an image ({error}).")
        return None

    return width, height


def classify_unexpected_entry(name: str, runner: str) -> str:
    """The reason an entry is rejected, phrased so several entries sharing a
    reason can be reported together. Contributors hit these in batches — a zip
    carries one `._x` per frame — so one message per reason beats one per file.
    """
    base = name.rstrip("/").split("/")[-1]
    top = name.split("/")[0]
    for junk, reason in JUNK_REASONS.items():
        if base == junk or top == junk:
            return reason.format(name=runner)
    if base.startswith("._"):
        return APPLEDOUBLE_REASON.format(name=runner)
    if base.startswith("."):
        return HIDDEN_REASON
    return f"not allowed here. The archive must contain only `{runner}-frames/{runner}-frame-N.png` files."


def report_unexpected_entries(runner: str, path: str, grouped: dict[str, list[str]], report: Report) -> None:
    for reason, names in grouped.items():
        shown = ", ".join(f"`{entry}`" for entry in names[:MAX_REPORTED_UNEXPECTED])
        remainder = len(names) - MAX_REPORTED_UNEXPECTED
        if remainder > 0:
            shown += f" and {remainder} more"
        verb = "is" if len(names) == 1 else "are"
        report.error(runner, path, f"{shown} {verb} {reason}")


def validate_zip(root: Path, name: str, report: Report) -> None:
    path = f"runners/{name}/{name}-frames.zip"
    data = (root / path).read_bytes()

    if len(data) > MAX_ZIP_BYTES:
        report.error(
            name,
            path,
            f"The zip is {len(data)} bytes. Runner frame archives are a few tens of kilobytes; "
            "this is implausibly large.",
        )
        return

    if not check_zip_container(data, name, path, report):
        return

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        report.error(name, path, f"The zip could not be opened: {error}.")
        return

    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        report.error(name, path, f"The zip has {len(entries)} entries; at most {MAX_ENTRIES} are allowed.")
        return

    root_directory = f"{name}-frames/"
    frame_re = re.compile(rf"^{re.escape(name)}-frame-(\d+)\.png$")

    # Reported as one message rather than as an unexpected-entry error per file,
    # which for a 30-frame runner would bury the actual problem.
    if not any(entry.filename.startswith(root_directory) for entry in entries):
        report.error(
            name,
            path,
            f"The zip has no `{root_directory}` directory; its {len(entries)} entries sit at the "
            f"root of the archive. Zip the `{root_directory}` directory itself, not its contents: "
            + REZIP_COMMAND.format(name=name),
        )
        return

    frames: dict[int, tuple[str, bytes]] = {}
    total_uncompressed = 0
    top_levels: set[str] = set()
    unexpected: dict[str, list[str]] = {}
    entries_ok = True

    for entry in entries:
        entry_name = entry.filename

        name_problem = check_entry_name(entry_name)
        if name_problem is not None:
            report.error(name, path, f"The zip entry `{entry_name}` {name_problem}.")
            entries_ok = False
            continue

        if not check_entry_metadata(entry, name, path, report):
            entries_ok = False
            continue

        top_levels.add(entry_name.split("/")[0])

        if entry_name == root_directory:
            continue

        base = entry_name[len(root_directory) :] if entry_name.startswith(root_directory) else None
        match = frame_re.match(base) if base else None

        if match is None:
            unexpected.setdefault(classify_unexpected_entry(entry_name, name), []).append(entry_name)
            entries_ok = False
            continue

        if entry.file_size > MAX_ENTRY_UNCOMPRESSED:
            report.error(name, path, f"`{entry_name}` expands to {entry.file_size} bytes, which is implausibly large.")
            entries_ok = False
            continue

        ratio = entry.file_size / max(entry.compress_size, 1)
        if ratio > MAX_RATIO:
            report.error(
                name,
                path,
                f"`{entry_name}` has a compression ratio of {ratio:.0f}:1, which suggests a zip bomb.",
            )
            entries_ok = False
            continue

        try:
            blob = archive.read(entry)
        except Exception as error:
            report.error(name, path, f"`{entry_name}` could not be extracted: {error}.")
            entries_ok = False
            continue

        # The local header can lie about file_size; this is what actually caps a bomb.
        if len(blob) != entry.file_size:
            report.error(
                name,
                path,
                f"`{entry_name}` expanded to {len(blob)} bytes but the zip header declares "
                f"{entry.file_size}. The archive is malformed.",
            )
            entries_ok = False
            continue

        total_uncompressed += len(blob)
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
            report.error(name, path, "The zip expands to more than 8 MB in total, which suggests a zip bomb.")
            return

        index = int(match.group(1))
        if index in frames:
            report.error(
                name,
                path,
                f"`{entry_name}` and `{root_directory}{frames[index][0]}` are both frame {index}.",
            )
            entries_ok = False
            continue
        frames[index] = (base, blob)

    report_unexpected_entries(name, path, unexpected, report)

    if len(top_levels) > 1:
        listed = sorted(top_levels)[:MAX_REPORTED_UNEXPECTED]
        suffix = ", ..." if len(top_levels) > MAX_REPORTED_UNEXPECTED else ""
        report.error(
            name,
            path,
            f"The zip has {len(top_levels)} top-level entries ("
            + ", ".join(f"`{top}`" for top in listed)
            + suffix
            + f"). It must contain a single `{root_directory}` directory.",
        )
        return

    if not entries_ok:
        return

    if len(frames) < MIN_FRAMES:
        report.error(
            name,
            path,
            f"The zip contains {len(frames)} frame(s). A runner animation needs at least {MIN_FRAMES}.",
        )
        return

    expected_indices = set(range(len(frames)))
    if set(frames) != expected_indices:
        missing = sorted(expected_indices - set(frames))
        extra = sorted(set(frames) - expected_indices)
        details = []
        if missing:
            details.append("missing " + ", ".join(f"`{name}-frame-{i}.png`" for i in missing))
        if extra:
            details.append("unexpected " + ", ".join(f"`{name}-frame-{i}.png`" for i in extra))
        report.error(
            name,
            path,
            f"Frames must be numbered consecutively from 0 to {len(frames) - 1}, but the archive has "
            + " and ".join(details)
            + ".",
        )
        return

    sizes: dict[tuple[int, int], str] = {}
    for index in sorted(frames):
        base, blob = frames[index]
        size = check_png(
            blob,
            label=f"Frame `{base}`",
            path=path,
            runner=name,
            report=report,
            require_apng=False,
        )
        if size is None:
            continue
        width, height = size
        if height != FRAME_HEIGHT:
            report.error(
                name,
                path,
                f"Frame `{base}` is {width}x{height}. Every frame must be exactly {FRAME_HEIGHT}px tall.",
            )
        if not MIN_WIDTH <= width <= MAX_WIDTH:
            report.error(
                name,
                path,
                f"Frame `{base}` is {width}px wide. Frames must be between {MIN_WIDTH}px and {MAX_WIDTH}px wide.",
            )
        sizes.setdefault(size, base)

    if len(sizes) > 1:
        listed = ", ".join(f"{w}x{h} (e.g. `{base}`)" for (w, h), base in sorted(sizes.items()))
        report.error(name, path, f"Frames have different sizes: {listed}. All frames must share one size.")


def validate_metadata(root: Path, name: str, report: Report) -> None:
    path = f"runners/{name}/metadata.json"
    raw = (root / path).read_bytes()

    if len(raw) > MAX_JSON_BYTES:
        report.error(name, path, f"The file is {len(raw)} bytes; `metadata.json` should be a few lines of JSON.")
        return

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        report.error(name, path, f"The file is not valid UTF-8: {error}.")
        return

    try:
        metadata = json.loads(text)
    except json.JSONDecodeError as error:
        report.error(name, path, f"The file is not valid JSON: line {error.lineno} column {error.colno}: {error.msg}.")
        return

    if not isinstance(metadata, dict):
        report.error(name, path, "The top level must be a JSON object.")
        return

    keys = set(metadata)
    missing = METADATA_KEYS - keys
    unexpected = keys - METADATA_KEYS
    if missing:
        report.error(name, path, "Missing required key(s): " + ", ".join(f"`{key}`" for key in sorted(missing)) + ".")
    if unexpected:
        allowed = ", ".join(f"`{key}`" for key in sorted(METADATA_KEYS))
        report.error(
            name,
            path,
            "Unexpected key(s): "
            + ", ".join(f"`{key}`" for key in sorted(unexpected))
            + f". Only {allowed} are used.",
        )

    for key in sorted(METADATA_STRING_KEYS & keys):
        value = metadata[key]
        if not isinstance(value, str):
            report.error(name, path, f"`{key}` must be a string.")
            continue
        if not value.strip():
            report.error(name, path, f"`{key}` must not be empty.")
            continue
        if len(value) > MAX_METADATA_VALUE_LENGTH:
            report.error(name, path, f"`{key}` is {len(value)} characters; at most {MAX_METADATA_VALUE_LENGTH} are allowed.")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            report.error(name, path, f"`{key}` contains control characters.")

    if "type" in keys and isinstance(metadata["type"], str) and metadata["type"] not in RUNNER_TYPES:
        allowed = " or ".join(f'"{value}"' for value in RUNNER_TYPES)
        report.error(name, path, f"`type` must be {allowed}.")

    if "tags" in keys:
        validate_tags(metadata["tags"], name, path, report)


def validate_tags(tags: object, name: str, path: str, report: Report) -> None:
    if not isinstance(tags, list):
        report.error(name, path, "`tags` must be an array of strings.")
        return
    if len(tags) > MAX_TAGS:
        report.error(name, path, f"`tags` has {len(tags)} entries; at most {MAX_TAGS} are allowed.")

    seen: set[str] = set()
    valid_tags: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            report.error(name, path, "`tags` entries must be strings.")
            continue
        if not TAG_RE.match(tag):
            report.error(name, path, f"`{tag}` is not a valid tag. Use lowercase letters, digits, and hyphens.")
            continue
        if tag not in KNOWN_TAGS:
            allowed = ", ".join(f"`{value}`" for value in KNOWN_TAGS)
            report.error(name, path, f"`{tag}` is not a known tag. Known tags: {allowed}.")
            continue
        if tag in seen:
            report.error(name, path, f"`{tag}` is listed more than once in `tags`.")
            continue
        seen.add(tag)
        valid_tags.add(tag)

    for child, parent in TAG_HIERARCHY.items():
        if child in valid_tags and parent not in valid_tags:
            report.error(name, path, f"`tags` includes `{child}` but is missing its parent tag `{parent}`.")


def validate_preview(root: Path, name: str, report: Report) -> None:
    path = f"runners/{name}/preview.png"
    data = (root / path).read_bytes()
    size = check_png(
        data,
        label="`preview.png`",
        path=path,
        runner=name,
        report=report,
        require_apng=True,
    )
    if size is None:
        return
    width, height = size
    if height != FRAME_HEIGHT:
        report.error(name, path, f"`preview.png` is {width}x{height}. It must be exactly {FRAME_HEIGHT}px tall.")
    if width > MAX_WIDTH:
        report.error(name, path, f"`preview.png` is {width}px wide. It must be at most {MAX_WIDTH}px wide.")


def validate_directory_contents(name: str, tracked: dict[str, str], report: Report) -> set[str]:
    prefix = f"runners/{name}/"
    present: set[str] = set()
    directory_path = f"runners/{name}"

    for path, mode in tracked.items():
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix) :]
        if "/" in relative:
            report.error(
                name,
                path,
                f"`{relative}` is inside a subdirectory. A runner directory holds exactly three files, flat.",
            )
            continue
        present.add(relative)
        if mode == "120000":
            report.error(name, path, f"`{relative}` is committed as a symbolic link. It must be a regular file.")
        elif mode == "100755":
            report.error(name, path, f"`{relative}` is committed with the executable bit set. Run `chmod 644` on it.")
        elif mode != "100644":
            report.error(name, path, f"`{relative}` has an unexpected git mode ({mode}). It must be a regular file.")

    expected = {template.format(name=name) for template in EXPECTED_FILES}
    missing = expected - present
    unexpected = present - expected

    if "preview.gif" in unexpected and "preview.png" in missing:
        report.error(
            name,
            f"{prefix}preview.gif",
            "The gallery renders `preview.png` and does not support GIF. Convert your animation to an "
            "animated PNG named `preview.png`, for example with "
            "`ffmpeg -i preview.gif -plays 0 -f apng preview.png`.",
        )
        missing.discard("preview.png")
        unexpected.discard("preview.gif")

    for filename in sorted(missing):
        report.error(name, f"{prefix}{filename}", f"`{filename}` is missing. " + describe_expected(name, filename))
    for filename in sorted(unexpected):
        report.error(
            name,
            f"{prefix}{filename}",
            f"`{filename}` does not belong here. A runner directory contains exactly "
            f"`{name}-frames.zip`, `metadata.json`, and `preview.png`.",
        )

    if not present:
        report.error(name, directory_path, "The runner directory is empty.")

    return present


def describe_expected(name: str, filename: str) -> str:
    if filename == "metadata.json":
        return (
            'It holds the runner\'s `author`, `displayName`, `type`, and `tags`, e.g. '
            '`{"author": "Your Name (YourGitHubID)", "displayName": "Display Name", '
            '"type": "monochrome", "tags": ["animal"]}`.'
        )
    if filename == "preview.png":
        return "Every runner needs an animated PNG preview, 36px tall and at most 100px wide."
    return f"It holds the animation frames as `{name}-frames/{name}-frame-N.png`."


def validate_runner(root: Path, name: str, tracked: dict[str, str], report: Report) -> None:
    report.checked.append(name)

    if not RUNNER_NAME_RE.match(name):
        report.error(
            name,
            f"runners/{name}",
            f"`{name}` is not a valid runner name. Use lowercase letters, digits, and hyphens, "
            "e.g. `welsh-corgi`.",
        )
        return

    present = validate_directory_contents(name, tracked, report)

    if f"{name}-frames.zip" in present:
        validate_zip(root, name, report)
    if "metadata.json" in present:
        validate_metadata(root, name, report)
    if "preview.png" in present:
        validate_preview(root, name, report)


def validate_manifest(root: Path, tracked: dict[str, str], report: Report) -> None:
    """Always checked in full, for every run.

    Reading the manifest and listing directories costs nothing (no archive is
    opened), and manifest/directory correspondence is inherently global: a PR
    that reorders the list can drop an entry for a runner it never touched.
    A name listed with a broken directory is silently dropped from the gallery
    by script.js, which is the failure this whole check exists to catch.
    """
    path = "runners/manifest.json"
    if path not in tracked:
        report.error(None, path, "`runners/manifest.json` is missing.")
        return

    raw = (root / path).read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        report.error(None, path, f"The file is {len(raw)} bytes, which is far larger than expected.")
        return

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        report.error(None, path, f"The file is not valid JSON: {error}.")
        return

    if not isinstance(manifest, dict) or set(manifest) != {"runners"}:
        report.error(None, path, 'The file must be a JSON object with exactly one key, `runners`.')
        return

    listed = manifest["runners"]
    if not isinstance(listed, list) or not all(isinstance(item, str) for item in listed):
        report.error(None, path, "`runners` must be a list of strings.")
        return

    seen: set[str] = set()
    for item in listed:
        if not RUNNER_NAME_RE.match(item):
            report.error(
                None,
                path,
                f"`{item}` is not a valid runner name. Use lowercase letters, digits, and hyphens.",
            )
        if item in seen:
            report.error(None, path, f"`{item}` is listed more than once.")
        seen.add(item)

    if listed != sorted(listed):
        for index, (actual, expected) in enumerate(zip(listed, sorted(listed))):
            if actual != expected:
                report.error(
                    None,
                    path,
                    f"`runners` must be sorted alphabetically. `{actual}` at position {index} "
                    f"should be `{expected}`.",
                )
                break

    on_disk = set(runner_names_on_disk(tracked))

    for item in sorted(seen - on_disk):
        report.error(
            None,
            path,
            f"`{item}` is listed in the manifest but `runners/{item}/` does not exist. The gallery "
            "would silently skip it.",
        )
    for item in sorted(on_disk - seen):
        report.error(
            None,
            path,
            f"`runners/{item}/` exists but `{item}` is not listed in the manifest, so it will not "
            "appear in the gallery.",
        )


def validate(root: Path, targets: set[str] | None) -> Report:
    report = Report()
    tracked = git_tracked(root)

    validate_manifest(root, tracked, report)

    names = runner_names_on_disk(tracked)
    if targets is not None:
        names = [name for name in names if name in targets]

    for name in names:
        try:
            validate_runner(root, name, tracked, report)
        except Exception as error:
            report.internal_error = True
            report.error(
                name,
                f"runners/{name}",
                f"Internal error while validating this runner: {error!r}. This is a CI problem, "
                "not a problem with your pull request.",
            )

    return report


def escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(value: str) -> str:
    return escape_data(value).replace(":", "%3A").replace(",", "%2C")


def emit_annotations(report: Report) -> None:
    for problem in report.problems:
        title = f"Runner: {problem.runner}" if problem.runner else "Runner validation"
        print(
            f"::error file={escape_property(problem.file)},"
            f"title={escape_property(title)}::{escape_data(problem.message)}"
        )


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def emit_step_summary(report: Report, out) -> None:
    out.write("## Runner validation\n\n")

    if not report.problems:
        if not report.checked:
            out.write("✅ No runner was changed by this pull request; only the manifest was checked.\n")
            return
        passed = plural(len(report.checked), "runner")
        out.write(f"✅ **{passed} passed** — archive contents, PNG integrity, and spec conformance.\n\n")
        out.write("<details><summary>What was checked</summary>\n\n")
        out.write(
            "- Each `*-frames.zip` contains only PNG frames under a single `<name>-frames/` directory — "
            "no symlinks, no executables, no encrypted or Finder-generated entries, and no data appended "
            "to the archive.\n"
            "- Every PNG was fully decoded and proven to consist entirely of valid PNG chunks with correct "
            "CRCs, ending at `IEND` with no trailing bytes. There is nowhere in these files for an "
            "executable payload to hide.\n"
            "- Every frame is exactly 36px tall, 10–100px wide, and all frames in an archive share one size.\n"
            "- `metadata.json`, `preview.png` (an APNG), and `manifest.json` match each runner directory.\n"
        )
        out.write("\n</details>\n")
        return

    failed = [name for name in report.runners_with_errors() if name]
    out.write(
        f"❌ **{plural(len(report.problems), 'problem')} in {plural(len(failed), 'runner')}** — "
        f"{len(report.checked) - len(failed)} of {plural(len(report.checked), 'checked runner')} passed.\n\n"
    )

    grouped: dict[str | None, list[Problem]] = {}
    for problem in report.problems:
        grouped.setdefault(problem.runner, []).append(problem)

    for runner in sorted(grouped, key=lambda value: (value is not None, value or "")):
        heading = f"`{runner}`" if runner else "Repository"
        out.write(f"### {heading}\n\n")
        out.write("| File | Problem |\n| --- | --- |\n")
        for problem in grouped[runner]:
            message = problem.message.replace("|", "\\|")
            out.write(f"| `{problem.file}` | {message} |\n")
        out.write("\n")

    out.write("---\n\n")
    out.write("Each problem is also annotated on the relevant file in the **Files changed** tab.\n")
    out.write(
        "See [CONTRIBUTING.md](https://github.com/runcat-dev/RunnerGallery/blob/main/CONTRIBUTING.md) "
        "for the full requirements.\n"
    )
    out.write("You can run these checks yourself before pushing:\n\n")
    out.write("```sh\npip install -r .github/scripts/requirements.txt\npython3 .github/scripts/validate_runners.py --all\n```\n")


def emit_human(report: Report) -> None:
    if not report.problems:
        if report.checked:
            print(f"OK: {plural(len(report.checked), 'runner')} passed: {', '.join(report.checked)}")
        else:
            print("No runner was changed; only the manifest was checked.")
        return

    grouped: dict[str | None, list[Problem]] = {}
    for problem in report.problems:
        grouped.setdefault(problem.runner, []).append(problem)

    for runner in sorted(grouped, key=lambda value: (value is not None, value or "")):
        print(f"\n{runner or 'repository'}:")
        for problem in grouped[runner]:
            print(f"  {problem.file}")
            print(f"      {problem.message}")

    print(f"\n{plural(len(report.problems), 'problem')} found.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate runner assets.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="validate every runner")
    group.add_argument("--changed-since", metavar="BASE_SHA", help="validate runners touched since BASE_SHA")
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[2]

    try:
        targets = None if arguments.all else changed_runners(root, arguments.changed_since)
        report = validate(root, targets)
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.decode("utf-8", "replace").strip()
        print(f"Failed to run git: {stderr}", file=sys.stderr)
        return 2

    in_actions = bool(os.environ.get("GITHUB_ACTIONS"))
    if in_actions:
        emit_annotations(report)
    # Always in the log too, so that a run which validated nothing at all reads
    # as such instead of as a silent pass.
    emit_human(report)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as out:
            emit_step_summary(report, out)
    elif in_actions:
        emit_step_summary(report, sys.stdout)

    if report.internal_error:
        return 2
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Copy license files into a Cue runtime's licenses/ directory.

Wheels that omit a license file use an exact-version override. A third-party
distribution with neither a wheel file nor a matching override fails the build.
Copying these texts is not a legal opinion.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

LICENSE_NAME = re.compile(
    r"(?i)^(license|licence|copying|notice|copyright|unlicense)([._-].*)?$"
)
FIRST_PARTY = {"iina-cue"}
# Wheels that ship no license file. soynlp's upstream LICENSE is LGPL-3.0;
# COPYING is GPL-3.0 because that LGPL text says to include the GPL as well.
OVERRIDES = {
    "cython": ("3.3.0", (("apache-2.0.txt", "LICENSE"),)),
    "dynet38": ("2.2", (("apache-2.0.txt", "LICENSE"),)),
    "flatbuffers": ("25.12.19", (("apache-2.0.txt", "LICENSE"),)),
    "litert-lm-api": ("0.17.1", (("apache-2.0.txt", "LICENSE"),)),
    "sentencepiece": ("0.2.2", (("apache-2.0.txt", "LICENSE"),)),
    "soynlp": ("0.0.493", (("soynlp/LICENSE", "LICENSE"), ("gpl-3.0.txt", "COPYING"))),
    "tokenizers": ("0.23.2", (("apache-2.0.txt", "LICENSE"),)),
}
FFMPEG_LICENSE = "LGPL version 2.1 or later"


@dataclass(frozen=True)
class Packed:
    name: str
    version: str
    source: str


def fail(message: str) -> None:
    print(f"collect-licenses: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_text(path: Path, needle: str) -> None:
    if not path.is_file() or path.is_symlink():
        fail(f"missing {path}")
    text = path.read_text(errors="replace")
    if needle not in text:
        fail(f"{path} does not contain {needle!r}")


def is_license_filename(name: str) -> bool:
    return LICENSE_NAME.fullmatch(name) is not None


def site_packages(prefix: Path) -> Path:
    matches = sorted(
        path for path in prefix.glob("lib/python3.*/site-packages") if path.is_dir()
    )
    if len(matches) != 1:
        fail(f"{prefix} does not contain exactly one lib/python3.*/site-packages")
    return matches[0]


def dist_info_directory(dist: importlib.metadata.Distribution, site: Path) -> Path:
    site_resolved = site.resolve()
    for entry in dist.files or []:
        parts = Path(str(entry)).parts
        if ".." in parts:
            continue
        for index, part in enumerate(parts):
            if not part.endswith(".dist-info"):
                continue
            candidate = site.joinpath(*parts[: index + 1]).resolve()
            if candidate.is_dir() and site_resolved in candidate.parents:
                return candidate
    private = getattr(dist, "_path", None)
    if private is not None:
        candidate = Path(str(private)).resolve()
        if candidate.name.endswith(".dist-info") and site_resolved in candidate.parents:
            return candidate
    name = dist.metadata["Name"] or "(unnamed)"
    fail(f"cannot find dist-info for {name}")
    raise AssertionError


def readable_file(path: Path, root: Path) -> Path:
    if path.is_symlink():
        resolved = path.resolve()
        if root.resolve() not in resolved.parents:
            fail(f"license symlink escapes {root}: {path}")
        path = resolved
    if not path.is_file():
        fail(f"license path is not a file: {path}")
    if path.stat().st_size == 0 or not path.read_bytes().strip():
        fail(f"empty license file: {path}")
    return path


def declared_license_files(dist_info: Path) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    license_dir = dist_info / "licenses"
    if license_dir.is_dir():
        for path in sorted(license_dir.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            file = readable_file(path, dist_info)
            found.append((file, file.resolve().relative_to(dist_info.resolve())))
    for path in sorted(dist_info.iterdir()):
        if path.name == "licenses" or not is_license_filename(path.name):
            continue
        if not path.is_file() and not path.is_symlink():
            continue
        file = readable_file(path, dist_info)
        found.append((file, Path(path.name)))
    return found


def record_license_files(dist: importlib.metadata.Distribution, site: Path) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    site_resolved = site.resolve()
    for entry in dist.files or []:
        relative = Path(str(entry))
        if ".." in relative.parts or not is_license_filename(relative.name):
            continue
        candidate = site.joinpath(relative)
        if not candidate.exists() and not candidate.is_symlink():
            continue
        file = readable_file(candidate, site)
        if site_resolved not in file.resolve().parents:
            fail(f"license file escapes site-packages: {relative}")
        found.append((file, file.resolve().relative_to(site_resolved)))
    return found


def copy_bytes(source: Path, dest: Path) -> None:
    if dest.exists() or dest.is_symlink():
        fail(f"duplicate license destination {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    if not data.strip():
        fail(f"empty license file: {source}")
    dest.write_bytes(data)


def prepare_output(output: Path, project: Path) -> Path:
    if output.name != "licenses":
        fail("output directory must be named licenses")
    if output.exists() and output.is_symlink():
        fail("output path is a symlink")
    resolved = output.resolve()
    overrides = (project / "third_party" / "license-overrides").resolve()
    if resolved == project.resolve() or resolved == Path(resolved.anchor):
        fail(f"refusing to replace {resolved}")
    if resolved == overrides or overrides in resolved.parents or resolved in overrides.parents:
        fail(f"refusing to replace {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)
    return resolved


def model_needles(project: Path) -> dict[str, str]:
    manifest = json.loads((project / "models" / "manifest.json").read_text())
    # Optional larger speech models are downloaded only when the user chooses one,
    # but the runtime that can download them carries their notices too.
    assets = {asset["name"]: asset for asset in manifest["assets"] + manifest.get("optional_assets", [])}
    try:
        gemma = assets["gemma"]["revision"]
        gemma_e4b = assets["gemma-e4b"]["revision"]
        gemma_12b = assets["gemma-12b"]["revision"]
        aligner = assets["aligner"]["revision"]
    except KeyError as error:
        fail(f"models/manifest.json is missing {error}")
    return {
        "gemma-4-e2b": gemma,
        "gemma-4-e4b": gemma_e4b,
        "gemma-4-12b": gemma_12b,
        "qwen3-forced-aligner-0.6b": "Qwen/Qwen3-ForcedAligner-0.6B",
        "qwen3-forced-aligner-0.6b-4bit": aligner,
    }


def copy_models(project: Path, output: Path, apache: Path) -> None:
    root = project / "third_party" / "license-overrides" / "models"
    for name, needle in model_needles(project).items():
        source = root / name / "SOURCE.txt"
        require_text(source, needle)
        require_text(source, "apache-2.0")
        destination = output / "models" / name
        destination.mkdir(parents=True)
        copy_bytes(source, destination / "SOURCE.txt")
        copy_bytes(apache, destination / "LICENSE")


def copy_ffmpeg(ffmpeg_root: Path, output: Path) -> None:
    copying = ffmpeg_root / "COPYING.LGPLv2.1"
    record_path = ffmpeg_root / "build-record.txt"
    require_text(copying, "GNU LESSER GENERAL PUBLIC LICENSE")
    if not record_path.is_file() or record_path.is_symlink():
        fail(f"missing {record_path}")
    fields: dict[str, str] = {}
    for line_number, raw in enumerate(record_path.read_text().splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        key, separator, value = raw.partition("=")
        if not separator or not key or key in fields:
            fail(f"unreadable ffmpeg build record line {line_number}")
        fields[key] = value
    missing = {"source_url", "sha256", "version", "license", "configure_flags"} - fields.keys()
    if missing:
        fail("ffmpeg build record is missing " + ", ".join(sorted(missing)))
    if fields["license"] != FFMPEG_LICENSE:
        fail(f"ffmpeg license is {fields['license']!r}, expected {FFMPEG_LICENSE!r}")
    if not re.fullmatch(r"[0-9a-f]{64}", fields["sha256"]):
        fail("ffmpeg sha256 is not 64 hex characters")
    if not fields["source_url"].startswith("https://ffmpeg.org/releases/ffmpeg-") or not fields["source_url"].endswith(".tar.xz"):
        fail("ffmpeg source_url is not an ffmpeg.org release tarball")
    flags = set(fields["configure_flags"].split())
    if "--disable-gpl" not in flags or "--disable-nonfree" not in flags:
        fail("ffmpeg configure flags do not disable GPL and nonfree")
    if "--enable-gpl" in flags or "--enable-nonfree" in flags:
        fail("ffmpeg configure flags enable GPL or nonfree")
    destination = output / "ffmpeg"
    destination.mkdir(parents=True)
    copy_bytes(copying, destination / "COPYING.LGPLv2.1")
    copy_bytes(record_path, destination / "build-record.txt")


def copy_vad(vad_root: Path, output: Path) -> None:
    license_path = vad_root / "LICENSE"
    source = vad_root / "SOURCE.txt"
    require_text(license_path, "MIT License")
    require_text(license_path, "Silero Team")
    require_text(source, "silero_vad-6.2.3-py3-none-any.whl")
    require_text(source, "sha256=")
    destination = output / "models" / "silero-vad"
    destination.mkdir(parents=True)
    copy_bytes(license_path, destination / "LICENSE")
    copy_bytes(source, destination / "SOURCE.txt")


def collect(prefix: Path, output: Path, project: Path, ffmpeg_root: Path | None,
            vad_root: Path | None = None) -> list[Packed]:
    project = project.resolve()
    prefix = prefix.resolve()
    overrides = project / "third_party" / "license-overrides"
    apache = overrides / "apache-2.0.txt"
    require_text(apache, "Apache License")
    require_text(overrides / "gpl-3.0.txt", "GNU GENERAL PUBLIC LICENSE")
    require_text(overrides / "mpl-2.0.txt", "Mozilla Public License")
    require_text(overrides / "soynlp" / "LICENSE", "LESSER GENERAL PUBLIC LICENSE")
    require_text(project / "THIRD_PARTY_NOTICES.md", "not legal advice")
    output = prepare_output(output, project)
    copy_bytes(project / "THIRD_PARTY_NOTICES.md", output / "THIRD_PARTY_NOTICES.md")
    (output / "common").mkdir()
    copy_bytes(overrides / "mpl-2.0.txt", output / "common" / "MPL-2.0.txt")
    site = site_packages(prefix)
    python_license = site.parent / "LICENSE.txt"
    require_text(python_license, "Python")
    (output / "python").mkdir()
    copy_bytes(python_license, output / "python" / "LICENSE.txt")
    copy_models(project, output, apache)
    if ffmpeg_root is not None:
        copy_ffmpeg(ffmpeg_root, output)
    if vad_root is not None:
        copy_vad(vad_root, output)

    packed: list[Packed] = []
    seen: set[str] = set()
    distributions = list(importlib.metadata.distributions(path=[str(site)]))
    if not distributions:
        fail(f"no distributions installed in {site}")
    for dist in distributions:
        name = (dist.metadata["Name"] or "").strip()
        version = (dist.version or "").strip()
        if not name or not version:
            fail("installed distribution is missing a name or version")
        key = name.casefold()
        if key in seen:
            fail(f"duplicate distribution {name}")
        seen.add(key)
        info = dist_info_directory(dist, site)
        destination = output / "packages" / key
        destination.mkdir(parents=True)
        if key in FIRST_PARTY:
            note = destination / "FIRST_PARTY.txt"
            note.write_text(
                "This directory is the Cue helper package (iina-cue) built from this repository.\n"
                "It is first-party code, not a third-party distribution.\n"
                "This repository does not ship a project license file.\n"
                "This note is not a license and does not grant any rights.\n"
            )
            packed.append(Packed(key, version, "first-party"))
            continue
        files = declared_license_files(info)
        source = "wheel"
        if not files:
            files = record_license_files(dist, site)
        if not files:
            override = OVERRIDES.get(key)
            if override is None:
                fail(f"{name} {version} has no recoverable license file")
            override_version, copies = override
            if version != override_version:
                fail(
                    f"{name} {version} has no license file in the wheel, "
                    f"and the override is for {override_version}"
                )
            source = "override"
            for relative, dest_name in copies:
                if "/" in dest_name or dest_name in {"", ".", ".."}:
                    fail(f"unsafe override destination for {name}")
                copy_bytes(overrides / relative, destination / dest_name)
        else:
            for file, relative in files:
                if ".." in relative.parts:
                    fail(f"unsafe license path for {name}")
                copy_bytes(file, destination / relative)
        copied = [path for path in destination.rglob("*") if path.is_file() and is_license_filename(path.name)]
        if not copied:
            fail(f"{name} {version} produced no license file")
        packed.append(Packed(key, version, source))
    lines = ["# name version source"]
    for item in sorted(packed, key=lambda item: item.name):
        if any(character.isspace() for character in f"{item.name}{item.version}{item.source}"):
            fail(f"unexpected whitespace in license index for {item.name}")
        lines.append(f"{item.name} {item.version} {item.source}")
    (output / "index.txt").write_text("\n".join(lines) + "\n")
    return packed


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="collect_licenses")
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--ffmpeg-root", type=Path)
    parser.add_argument("--vad-root", type=Path)
    args = parser.parse_args(argv)
    collect(args.prefix, args.output, args.project, args.ffmpeg_root, args.vad_root)


if __name__ == "__main__":
    main(sys.argv[1:])

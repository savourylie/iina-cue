import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "collect_licenses.py"
FFMPEG_RECORD = """\
source_url=https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz
sha256=733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1
version=7.1.1
license=LGPL version 2.1 or later
configure_flags=--prefix=/cue-ffmpeg --disable-autodetect --disable-gpl --disable-nonfree
"""


def make_prefix(tmp, packages):
    prefix = tmp / "prefix"
    lib = prefix / "lib" / "python3.12"
    site = lib / "site-packages"
    site.mkdir(parents=True)
    (lib / "LICENSE.txt").write_text("Python license text\n")
    for name, version, license_text in packages:
        normalized = re.sub(r"[-_.]+", "_", name).lower()
        info = site / f"{normalized}-{version}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        if license_text is not None:
            (info / "licenses").mkdir()
            (info / "licenses" / "LICENSE").write_text(license_text)
    return prefix


def run(prefix, output, ffmpeg=None):
    command = [
        sys.executable,
        str(SCRIPT),
        "--prefix",
        str(prefix),
        "--output",
        str(output),
        "--project",
        str(ROOT),
    ]
    if ffmpeg is not None:
        command.extend(["--ffmpeg-root", str(ffmpeg)])
    return subprocess.run(command, check=False, capture_output=True, text=True)


def index_rows(output):
    rows = []
    for line in (output / "index.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(tuple(line.split()))
    return rows


def test_wheel_license_is_copied_for_every_distribution(tmp_path):
    prefix = make_prefix(tmp_path, [("Widget", "1.2.3", "widget license\n")])
    output = tmp_path / "licenses"
    result = run(prefix, output)
    assert result.returncode == 0, result.stderr
    assert index_rows(output) == [("widget", "1.2.3", "wheel")]
    assert (output / "packages" / "widget" / "licenses" / "LICENSE").read_text() == "widget license\n"
    assert "Python license text" in (output / "python" / "LICENSE.txt").read_text()
    assert "Apache License" in (output / "models" / "gemma-4-e2b" / "LICENSE").read_text()
    assert "b3ca0d2f076785a8f4b2219ddbd2bdb99954eae1" in (output / "models" / "gemma-4-e2b" / "SOURCE.txt").read_text()
    assert "2f652af86ae0c73fe189b9429225c908ce4bf020" in (output / "models" / "qwen3-forced-aligner-0.6b-4bit" / "SOURCE.txt").read_text()
    assert (output / "THIRD_PARTY_NOTICES.md").read_text() == (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    assert "Mozilla Public License" in (output / "common" / "MPL-2.0.txt").read_text()


def test_removed_license_file_fails_the_build(tmp_path):
    prefix = make_prefix(tmp_path, [("widget", "1", "widget license\n")])
    first = run(prefix, tmp_path / "licenses")
    assert first.returncode == 0, first.stderr
    license_file = next((prefix / "lib").rglob("LICENSE"))
    license_file.unlink()
    second = run(prefix, tmp_path / "again" / "licenses")
    assert second.returncode != 0
    assert "widget" in second.stderr
    assert "no recoverable license file" in second.stderr


def test_soynlp_override_copies_lgpl_and_gpl(tmp_path):
    prefix = make_prefix(tmp_path, [("soynlp", "0.0.493", None)])
    output = tmp_path / "licenses"
    result = run(prefix, output)
    assert result.returncode == 0, result.stderr
    license_text = (output / "packages" / "soynlp" / "LICENSE").read_text()
    copying = (output / "packages" / "soynlp" / "COPYING").read_text()
    assert "LESSER GENERAL PUBLIC LICENSE" in license_text
    assert "Copyright (C) 2019 lovit" in license_text
    assert "How to Apply These Terms to Your New Programs" not in license_text
    assert "How to Apply These Terms to Your New Programs" in copying
    assert index_rows(output) == [("soynlp", "0.0.493", "override")]


def test_soynlp_wheel_license_wins_over_override(tmp_path):
    prefix = make_prefix(tmp_path, [("soynlp", "0.0.493", "wheel license\n")])
    output = tmp_path / "licenses"
    result = run(prefix, output)
    assert result.returncode == 0, result.stderr
    assert (output / "packages" / "soynlp" / "licenses" / "LICENSE").read_text() == "wheel license\n"
    assert not (output / "packages" / "soynlp" / "COPYING").exists()
    assert index_rows(output) == [("soynlp", "0.0.493", "wheel")]


def test_override_version_mismatch_fails(tmp_path):
    prefix = make_prefix(tmp_path, [("soynlp", "0.0.999", None)])
    result = run(prefix, tmp_path / "licenses")
    assert result.returncode != 0
    assert "0.0.999" in result.stderr
    assert "0.0.493" in result.stderr


def test_first_party_package_is_not_a_license_grant(tmp_path):
    prefix = make_prefix(tmp_path, [("iina-cue", "0.1.0", None)])
    output = tmp_path / "licenses"
    result = run(prefix, output)
    assert result.returncode == 0, result.stderr
    note = (output / "packages" / "iina-cue" / "FIRST_PARTY.txt").read_text()
    assert "not a license" in note
    assert "does not grant" in note
    names = [path.name for path in (output / "packages" / "iina-cue").iterdir()]
    assert names == ["FIRST_PARTY.txt"]
    assert index_rows(output) == [("iina-cue", "0.1.0", "first-party")]


def test_ffmpeg_license_record_and_rejected_gpl_build(tmp_path):
    prefix = make_prefix(tmp_path, [("widget", "1", "widget license\n")])
    ffmpeg = tmp_path / "ffmpeg"
    (ffmpeg / "bin").mkdir(parents=True)
    (ffmpeg / "COPYING.LGPLv2.1").write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1\n")
    (ffmpeg / "build-record.txt").write_text(FFMPEG_RECORD)
    output = tmp_path / "licenses"
    result = run(prefix, output, ffmpeg)
    assert result.returncode == 0, result.stderr
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (output / "ffmpeg" / "COPYING.LGPLv2.1").read_text()
    assert "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1" in (output / "ffmpeg" / "build-record.txt").read_text()
    (ffmpeg / "build-record.txt").write_text(FFMPEG_RECORD.replace("--disable-gpl", "--enable-gpl"))
    rejected = run(prefix, tmp_path / "rejected" / "licenses", ffmpeg)
    assert rejected.returncode != 0
    assert "GPL" in rejected.stderr


def test_notices_name_apache_gemma_qwen_and_lgpl_obligations():
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    script = (ROOT / "scripts" / "build-ffmpeg").read_text()
    sha = re.search(r"FFMPEG_SHA256=([0-9a-f]{64})", script).group(1)
    assert sha in notice
    assert "not legal advice" in notice
    assert "Apache License, Version 2.0" in notice
    assert "gemma-4-E2B" in notice
    assert "Qwen3-ForcedAligner" in notice
    assert "ai.google.dev/gemma/terms does not describe this artifact" in notice
    assert "soynlp" in notice
    assert "LGPL-2.1 section 6" in notice
    assert "does not ship the FFmpeg source tree" in notice
    assert "UNKNOWN" in notice

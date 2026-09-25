import importlib.machinery
import importlib.util
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release-runtime"


def load():
    name = "release_runtime"
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPT))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def compile_c(path: Path, minimum: str, kind: str) -> None:
    command = ["clang", "-arch", "arm64", f"-mmacosx-version-min={minimum}"]
    if kind == "library":
        command.append("-dynamiclib")
        source = b"int f(void){return 1;}\n"
    elif kind == "bundle":
        command.extend(["-bundle", "-undefined", "dynamic_lookup"])
        source = b"int f(void){return 1;}\n"
    elif kind == "executable":
        source = b"int main(void){return 0;}\n"
    else:
        raise AssertionError(kind)
    command.extend(["-o", str(path), "-x", "c", "-"])
    subprocess.run(command, input=source, check=True)


def test_helper_version_matches_bootstrap():
    assert load().helper_version(ROOT) == "0.1.6"


def test_defaults_match_the_notarization_trial():
    module = load()
    assert module.DEFAULT_PROFILE == "cue-notary"
    assert module.DEFAULT_IDENTITY == "Developer ID Application: Calvin Ku (92QTH3YBHM)"


def test_script_does_not_accept_apple_credentials():
    text = SCRIPT.read_text()
    for flag in ("--password", "--apple-id", "--key-id", "--issuer", "--entitlements"):
        assert flag not in text


def test_development_certificate_is_refused():
    module = load()
    with pytest.raises(module.ReleaseError, match="Developer ID"):
        module.require_developer_id("Apple Development: Example (TEAM)")


def test_signing_order_is_libraries_then_executables(tmp_path):
    module = load()
    compile_c(tmp_path / "main-bin", "12.0", "executable")
    compile_c(tmp_path / "libfirst.dylib", "14.0", "library")
    compile_c(tmp_path / "plugin.so", "11.0", "bundle")
    items = module.scan_runtime(tmp_path)
    kinds = [item.kind for item in items]
    assert kinds == ["library", "library", "executable"]
    assert [item.path.name for item in items] == ["libfirst.dylib", "plugin.so", "main-bin"]
    assert module.highest_minimum(items) == "14.0"
    assert items[0].minos_text == "14.0"
    assert items[2].minos_text == "12.0"


def test_minimum_matches_vtool(tmp_path):
    module = load()
    binary = tmp_path / "tool"
    compile_c(binary, "12.1", "executable")
    info = module.inspect_macho(binary)
    output = subprocess.check_output(["vtool", "-show-build", str(binary)], text=True)
    reported = next(line.split()[1] for line in output.splitlines() if line.strip().startswith("minos "))
    assert info is not None
    assert info.minos_text == reported == "12.1"
    assert info.kind == "executable"


def test_fat_header_uses_the_arm64_slice(tmp_path):
    module = load()
    thin = tmp_path / "thin"
    compile_c(thin, "12.0", "executable")
    payload = thin.read_bytes()
    offset = 4096
    blob = struct.pack(">II", 0xCAFEBABE, 1)
    blob += struct.pack(">IIIII", 0x0100000C, 0, offset, len(payload), 14)
    blob += b"\x00" * (offset - len(blob))
    blob += payload
    fat = tmp_path / "fat"
    fat.write_bytes(blob)
    info = module.inspect_macho(fat)
    assert info is not None
    assert info.kind == "executable"
    assert info.minos_text == "12.0"


def test_non_arm64_fat_is_rejected(tmp_path):
    module = load()
    path = tmp_path / "intel"
    path.write_bytes(struct.pack(">II", 0xCAFEBABE, 1) + struct.pack(">IIIII", 0x01000007, 0, 4096, 32, 12))
    with pytest.raises(module.ReleaseError, match="arm64"):
        module.inspect_macho(path)


def test_truncated_macho_is_rejected(tmp_path):
    module = load()
    path = tmp_path / "short"
    path.write_bytes(struct.pack("<I", 0xFEEDFACF) + b"\x00" * 10)
    with pytest.raises(module.ReleaseError, match="truncated"):
        module.inspect_macho(path)


def test_ordinary_file_is_not_a_macho(tmp_path):
    path = tmp_path / "readme.txt"
    path.write_text("not a binary\n")
    assert load().inspect_macho(path) is None


def test_symlink_outside_the_runtime_fails(tmp_path):
    module = load()
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "escape").symlink_to("/etc/passwd")
    with pytest.raises(module.ReleaseError, match="outside"):
        module.scan_runtime(root)


def test_internal_symlink_and_hardlink_are_signed_once(tmp_path):
    module = load()
    root = tmp_path / "tree"
    root.mkdir()
    library = root / "lib.dylib"
    compile_c(library, "11.0", "library")
    (root / "alias.dylib").symlink_to("lib.dylib")
    os.link(library, root / "again.dylib")
    items = module.scan_runtime(root)
    assert len(items) == 1
    assert items[0].path.stat().st_ino == library.stat().st_ino


def test_sign_command_has_hardened_runtime_and_no_entitlements():
    module = load()
    command = module.sign_command("Developer ID Application: Example (TEAMID)", Path("/tmp/lib.so"))
    assert command[:6] == [
        "codesign",
        "--force",
        "--sign",
        "Developer ID Application: Example (TEAMID)",
        "--options",
        "runtime",
    ]
    assert "--timestamp" in command
    assert "--entitlements" not in command
    joined = " ".join(command)
    assert "--password" not in joined
    assert "--apple-id" not in joined


def test_notary_command_uses_only_the_keychain_profile():
    command = load().notary_submit_command(Path("runtime.zip"), "cue-notary", "120m")
    assert command[:4] == ["xcrun", "notarytool", "submit", "runtime.zip"]
    assert "--keychain-profile" in command
    assert "cue-notary" in command
    assert "--wait" in command
    assert "--output-format" in command
    assert "json" in command
    for flag in ("--apple-id", "--password", "--key", "--key-id", "--issuer"):
        assert flag not in command


def test_gatekeeper_command_matches_the_ticket():
    command = load().gatekeeper_command(Path("python3.12"))
    assert command == [
        "spctl",
        "-a",
        "-t",
        "open",
        "--context",
        "context:primary-signature",
        "-vv",
        "python3.12",
    ]


def test_notary_json_can_follow_a_progress_line():
    payload = load().parse_notary_result(
        'Uploading\n{"status": "Accepted", "id": "792075c1-9579-40ef-b102-eaa7c652f90d"}\n'
    )
    assert payload["status"] == "Accepted"


def test_notarization_must_be_accepted():
    module = load()
    assert module.require_accepted({"status": "Accepted", "id": "792075c1-9579-40ef-b102-eaa7c652f90d"}) == (
        "792075c1-9579-40ef-b102-eaa7c652f90d"
    )
    with pytest.raises(module.ReleaseError, match="Accepted"):
        module.require_accepted({"status": "Invalid", "id": "792075c1-9579-40ef-b102-eaa7c652f90d"})
    with pytest.raises(module.ReleaseError, match="Accepted"):
        module.require_accepted({"status": "In Progress", "id": "792075c1-9579-40ef-b102-eaa7c652f90d"})


def test_log_errors_fail_and_warnings_do_not():
    module = load()
    assert module.require_clean_log({"status": "Accepted", "issues": None}) == []
    warnings = module.require_clean_log(
        {"status": "Accepted", "issues": [{"severity": "warning", "message": "test archive"}]}
    )
    assert warnings[0]["message"] == "test archive"
    with pytest.raises(module.ReleaseError, match="errors"):
        module.require_clean_log(
            {"status": "Accepted", "issues": [{"severity": "error", "message": "signature invalid"}]}
        )
    with pytest.raises(module.ReleaseError, match="Accepted"):
        module.require_clean_log({"status": "Invalid", "issues": None})


def test_manifest_has_the_release_fields_and_no_download_url(tmp_path):
    module = load()
    archive = tmp_path / "runtime-0.1.5.tar.xz"
    archive.write_bytes(b"signed-archive")
    digest = module.file_sha256(archive)
    payload = module.manifest_document(
        version="0.1.5",
        filename=archive.name,
        size=archive.stat().st_size,
        sha256=digest,
        minimum_macos="27.0",
        submission_id="792075c1-9579-40ef-b102-eaa7c652f90d",
        profile="cue-notary",
        log_name="runtime-0.1.5.notarization-log.json",
        stapled=False,
    )
    assert payload["version"] == "0.1.5"
    assert payload["size"] == len(b"signed-archive")
    assert payload["sha256"] == digest
    assert payload["minimum_macos"] == "27.0"
    assert payload["architecture"] == "arm64"
    assert payload["notarization"]["status"] == "Accepted"
    assert payload["notarization"]["profile"] == "cue-notary"
    assert payload["notarization"]["stapled"] is False
    assert "url" not in payload
    assert "url" not in json.dumps(payload)


def test_cli_refuses_a_runtime_without_license_notices(tmp_path):
    version = load().helper_version(ROOT)
    runtime = tmp_path / f"runtime-{version}"
    runtime.mkdir()
    (runtime / "VERSION").write_text(f"{version}\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--runtime", str(runtime)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "licenses/THIRD_PARTY_NOTICES.md" in result.stderr
    assert "notarytool" not in result.stderr

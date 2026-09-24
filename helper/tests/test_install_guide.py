from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "install-cue.md").read_text()
README = (ROOT / "README.md").read_text()
DEVELOPER = (ROOT / "docs" / "install.md").read_text()


def test_user_guide_covers_both_install_routes_without_terminal():
    assert "Double-click" in GUIDE
    assert "Install from GitHub" in GUIDE
    assert "```" not in GUIDE
    assert "scripts/" not in GUIDE
    assert "can execute other programs or applications that can harm your computer" in GUIDE
    assert "file-system" in GUIDE
    assert "127.0.0.1" in GUIDE
    assert "notarized by Apple" in GUIDE
    assert "macOS 27.0" in GUIDE
    assert "16 GB" in GUIDE
    assert "3.8 GB" in GUIDE
    assert "10 to 30 minutes" in GUIDE
    assert "unsupported Mac" in GUIDE
    assert "not enough free disk space" in GUIDE
    assert "interrupted download" in GUIDE
    assert "remove Cue completely" in GUIDE


def test_developer_steps_stay_separate_and_the_readme_keeps_its_prose():
    assert "scripts/setup-dev" in DEVELOPER or "scripts/setup-dev" in README
    assert "目前已包含" in README
    assert "55.8 秒" in README
    assert "docs/install-cue.md" in README
    user = README.split("## 檔案", 1)[0]
    assert "scripts/setup-dev" not in user

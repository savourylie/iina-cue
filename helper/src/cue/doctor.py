from __future__ import annotations
import importlib.metadata
import json
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
from .core import CueError
from .media import binary

def _ffmpeg_version() -> str:
    try:
        reported = command([binary("ffmpeg"), "-version"])
    except CueError:
        return "unavailable"
    return (reported or "unavailable").splitlines()[0]

def command(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired): return None

def doctor(models: Path) -> dict:
    versions = {}
    for name in ("litert-lm-api", "mlx", "mlx-audio", "numpy", "lingua-language-detector", "transformers", "soundfile"):
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name] = None
    iina = Path("/Applications/IINA.app/Contents/Info.plist")
    version = plistlib.loads(iina.read_bytes()).get("CFBundleShortVersionString") if iina.exists() else None
    gpu_info = command(["system_profiler", "SPDisplaysDataType", "-json"])
    gpu = json.loads(gpu_info).get("SPDisplaysDataType", []) if gpu_info else []
    hw_info = command(["system_profiler", "SPHardwareDataType", "-json"])
    hw = json.loads(hw_info).get("SPHardwareDataType", [{}])[0] if hw_info else {}
    return {"platform": platform.system(), "architecture": platform.machine(), "macos": platform.mac_ver()[0],
            "chip": command(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"]) or hw.get("chip_type"),
            "ram_bytes": command(["/usr/sbin/sysctl", "-n", "hw.memsize"]), "ram_label": hw.get("physical_memory"),
            "gpu": [{"model": g.get("sppci_model"), "cores": g.get("sppci_cores")} for g in gpu],
            "python": sys.version.split()[0], "iina": version,
            "embedded_mpv": "not_run: inspect mpv-version through smoke plugin",
            "ffmpeg": _ffmpeg_version(),
            "packages": versions,
            "model_assets": {"gemma": (models/"gemma/gemma-4-E2B-it.litertlm").is_file(), "aligner": (models/"aligner/model.safetensors").is_file()},
            "free_disk_bytes": shutil.disk_usage(models.parent if models.parent.exists() else Path.cwd()).free,
            "live_inference": "not_run", "telemetry": False}

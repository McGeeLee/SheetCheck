"""Verify this installed environment and its exact wheelhouse without networking.

Run from the repository root with the new environment's Python. This check is
installation evidence, not a substitute for the full tests or offline UI test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from zipfile import ZipFile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def verify(wheelhouse: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        raise SystemExit("Run from the SheetCheck project directory.")
    if sys.prefix == sys.base_prefix:
        raise SystemExit("A virtual environment is required.")

    lock = root / "requirements.lock"
    locked = {}
    for line in lock.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if not match:
            raise SystemExit("Unexpected lock syntax; do not silently ignore requirements.")
        name, version, digest = match.groups()
        name = canonical(name)
        if name in locked:
            raise SystemExit("Duplicate locked dependency.")
        locked[name] = {"version": version, "sha256": digest}

    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename

    supported_tags = set(sys_tags())
    wheels = {}
    for path in sorted(wheelhouse.glob("*.whl")):
        name, version, _, tags = parse_wheel_filename(path.name)
        name = canonical(name)
        if name in wheels or name not in locked:
            raise SystemExit("Duplicate or unlocked wheel in the wheelhouse.")
        with ZipFile(path) as package:
            entries = [item for item in package.namelist()
                       if item.count("/") == 1 and item.endswith(".dist-info/METADATA")]
            if len(entries) != 1:
                raise SystemExit("Wheel metadata must be unambiguous.")
            info = BytesParser().parsebytes(package.read(entries[0]))
        if canonical(info["Name"]) != name or info["Version"] != str(version):
            raise SystemExit("Wheel filename and metadata disagree.")
        if locked[name] != {"version": str(version), "sha256": sha256(path)}:
            raise SystemExit("Wheel differs from the lock.")
        if not tags.intersection(supported_tags):
            raise SystemExit("Wheel is not compatible with this interpreter/platform.")
        wheels[name] = {**locked[name], "filename": path.name, "bytes": path.stat().st_size,
                        "tags": sorted(str(tag) for tag in tags)}
    if wheels.keys() != locked.keys():
        raise SystemExit("Wheelhouse is incomplete.")

    installed = {canonical(dist.metadata["Name"]): dist.version for dist in metadata.distributions()}
    if set(installed) != set(locked) | {"sheetcheck"}:
        raise SystemExit("Unexpected or missing installed distributions.")
    for name, requirement in locked.items():
        if installed[name] != requirement["version"]:
            raise SystemExit("Installed version differs from lock.")

    import sheetcheck
    from sheetcheck.models import APP_VERSION, RULES_VERSION

    core_imports_streamlit = "streamlit" in sys.modules
    if core_imports_streamlit:
        raise SystemExit("Core import unexpectedly imports the UI framework.")
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    if installed["sheetcheck"] != APP_VERSION or project["version"] != APP_VERSION:
        raise SystemExit("Application versions disagree.")
    import streamlit.config as config

    expected_config = {
        "server.address": "127.0.0.1", "server.port": 8501,
        "server.headless": True, "server.maxUploadSize": 10,
        "server.enableCORS": True, "server.enableXsrfProtection": True,
        "server.allowedHosts": ["127.0.0.1", "localhost"],
        "server.enableStaticServing": False, "server.fileWatcherType": "none",
        "browser.serverAddress": "127.0.0.1", "browser.gatherUsageStats": False,
        "client.showErrorDetails": "none", "client.toolbarMode": "minimal",
        "client.disableDataExport": True, "logger.level": "error",
        "theme.font": "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        "theme.headingFont": "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        "theme.codeFont": "SFMono-Regular, Consolas, monospace",
    }
    actual_config = {key: config.get_option(key) for key in expected_config}
    if actual_config != expected_config:
        raise SystemExit("Effective Streamlit configuration differs from the local contract.")
    pip_check = subprocess.run([sys.executable, "-m", "pip", "check"],
                               capture_output=True, text=True, check=True)
    hardware = {}
    if sys.platform == "darwin":
        for field in ("hw.model", "machdep.cpu.brand_string", "hw.ncpu", "hw.memsize"):
            command = subprocess.run(["/usr/sbin/sysctl", "-n", field],
                                     capture_output=True, text=True)
            hardware[field] = command.stdout.strip() if command.returncode == 0 else "unavailable"
    paths = [root / "app.py", root / "pyproject.toml", lock, root / ".streamlit/config.toml"]
    paths += sorted((root / "sheetcheck").glob("*.py"))
    paths += sorted((root / "scripts").glob("*.py"))
    paths += sorted((root / "tests").glob("*.py"))
    paths += sorted(path for path in (root / "samples").glob("*") if path.is_file())
    source_hashes = {str(path.relative_to(root)): sha256(path) for path in paths}
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS", "scope": "install, wheel hashes, effective config and source snapshot only",
        "application_version": APP_VERSION, "rules_version": RULES_VERSION,
        "python": sys.version, "python_executable": sys.executable,
        "base_python_executable": sys._base_executable, "python3_12_on_PATH": shutil.which("python3.12"),
        "platform": platform.platform(), "machine": platform.machine(), "hardware": hardware,
        "venv_config": (Path(sys.prefix) / "pyvenv.cfg").read_text(),
        "lock_sha256": sha256(lock), "wheelhouse": str(wheelhouse.resolve()),
        "locked_wheel_count": len(wheels), "wheels": wheels,
        "installed_distributions": dict(sorted(installed.items())),
        "module_location": sheetcheck.__file__, "core_imports_streamlit": core_imports_streamlit,
        "pip_check": pip_check.stdout.strip(), "effective_streamlit_config": actual_config,
        "source_snapshot_sha256": hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
        "source_snapshot_files": source_hashes,
        "compatibility_claim": f"CPython {platform.python_version()}, {platform.platform()} only; no other platform tested by this run",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = verify(args.wheelhouse)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(f"PASS: {evidence['locked_wheel_count']} wheel hashes, installed versions, pip check and local configuration")
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()

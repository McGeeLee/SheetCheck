"""Package the reviewed local project and fictional acceptance evidence.

Uses only the standard library, never executes packaged content or accesses the
network. Run after final documents are frozen. Recheck this allowlist before
adding any real business data to these directories.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import tomllib
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
EVIDENCE_PREFIX = {"1.0.0": "m4", "1.1.0": "v1.1", "1.1.1": "v1.1.1", "1.1.2": "v1.1.2"}.get(PROJECT_VERSION)
if EVIDENCE_PREFIX is None:
    raise SystemExit("Review this delivery allowlist for the new version first.")
MANIFEST = Path(f"docs/{EVIDENCE_PREFIX}-delivery-manifest.json")
RECEIPT = Path(f"docs/{EVIDENCE_PREFIX}-package-verification.json")
FILES = (
    "README.md", "README.en.md", "CHANGELOG.md", ".gitignore",
    "app.py", "pyproject.toml", "requirements.lock",
)
DIRECTORIES = (
    ".streamlit", "sheetcheck", "tests", "samples", "scripts", "docs",
    "outputs/m3", "outputs/m4",
    "outputs/01a1697b-f428-7902-ad2b-de29c9d339f8",
)
if PROJECT_VERSION in {"1.1.0", "1.1.1", "1.1.2"}:
    DIRECTORIES += ("outputs/v1.1",)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reject_symlink_path(path: Path) -> None:
    """Reject pre-existing links, including dangling links and parent links."""
    relative = path.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlinked delivery path: {current.relative_to(ROOT)}")


def write_json(path: Path, data: dict) -> None:
    reject_symlink_path(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def excluded(path: Path) -> bool:
    return (
        path in (MANIFEST, RECEIPT)
        or path.name == ".DS_Store"
        or path.suffix == ".pyc"
        or any(part in ("__pycache__", ".pytest_cache", "build", "dist")
               or part.startswith(".venv") or part.endswith(".egg-info")
               for part in path.parts)
    )


def reviewed_files() -> list[Path]:
    paths = [ROOT / item for item in FILES]
    for name in DIRECTORIES:
        directory = ROOT / name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Missing or symlinked delivery directory: {name}")
        paths.extend(directory.rglob("*"))
    selected = []
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        if excluded(relative):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinks are not packaged: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Missing or non-regular file: {relative}")
        selected.append(relative)
    return selected


def main() -> None:
    if Path.cwd().resolve() != ROOT:
        raise SystemExit("Run from the SheetCheck project directory.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if version != PROJECT_VERSION:
        raise SystemExit("Review this delivery allowlist for the new version first.")
    release_record = Path(f"docs/{EVIDENCE_PREFIX}-release-status.json")
    reject_symlink_path(ROOT / release_record)
    release = json.loads((ROOT / release_record).read_text(encoding="utf-8"))
    if release["application_version"] != version or type(release["v1_complete"]) is not bool:
        raise SystemExit("Release version or completion metadata is inconsistent.")
    for path in (ROOT / MANIFEST, ROOT / RECEIPT, ROOT / "deliveries"):
        reject_symlink_path(path)
    selected = reviewed_files()
    metadata = {
        path.as_posix(): {"bytes": (ROOT / path).stat().st_size, "sha256": digest(ROOT / path)}
        for path in selected
    }
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "application_version": version,
        "release_status": release["status"],
        "v1_complete": release["v1_complete"],
        "scope": "Reviewed project files and fictional acceptance artifacts, including local platform wheels",
        "excluded_self_references": [MANIFEST.as_posix(), RECEIPT.as_posix(), "deliveries/"],
        "excluded_runtime_artifacts": ["virtual environments", "caches", "symlinks", "FFmpeg", "system fonts"],
        "file_count": len(metadata),
        "total_uncompressed_bytes": sum(item["bytes"] for item in metadata.values()),
        "files": metadata,
    }
    write_json(ROOT / MANIFEST, manifest)
    packaged = selected + [MANIFEST]
    expected = {**metadata, MANIFEST.as_posix(): {
        "bytes": (ROOT / MANIFEST).stat().st_size, "sha256": digest(ROOT / MANIFEST)}}
    output_dir = ROOT / "deliveries"
    output_dir.mkdir(exist_ok=True)
    basename = f"SheetCheck-{version}"
    output = output_dir / f"{basename}.zip"
    temporary = output_dir / f".{basename}.zip.tmp"
    checksum = output.with_suffix(".zip.sha256")
    for path in (output, temporary, checksum):
        reject_symlink_path(path)
    if temporary.exists():
        raise SystemExit("A prior temporary package exists; inspect it before retrying.")
    owned_temporary = False
    try:
        with ZipFile(temporary, "x") as archive:
            owned_temporary = True
            for relative in packaged:
                content = (ROOT / relative).read_bytes()
                info = expected[relative.as_posix()]
                if len(content) != info["bytes"] or hashlib.sha256(content).hexdigest() != info["sha256"]:
                    raise ValueError(f"Source changed while packaging: {relative}")
                member = ZipInfo(f"{basename}/{relative.as_posix()}", (2026, 10, 24, 0, 0, 0))
                member.create_system = 3
                member.external_attr = (stat.S_IFREG | 0o644) << 16
                member.compress_type = ZIP_STORED if relative.suffix in {".whl", ".xlsx", ".mp4", ".png", ".jpg"} else ZIP_DEFLATED
                archive.writestr(member, content)
        with ZipFile(temporary) as archive:
            names = archive.namelist()
            wanted = {f"{basename}/{path}" for path in expected}
            if len(names) != len(set(names)) or set(names) != wanted:
                raise ValueError("Unexpected or duplicate archive members.")
            if archive.testzip() is not None:
                raise ValueError("Archive CRC verification failed.")
            for relative, item in expected.items():
                content = archive.read(f"{basename}/{relative}")
                if len(content) != item["bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
                    raise ValueError(f"Archive content differs: {relative}")
            # All names above are our exact, relative allowlisted members.
            with tempfile.TemporaryDirectory(prefix="sheetcheck-package-") as directory:
                archive.extractall(directory)
                extracted = Path(directory) / basename
                for relative, item in expected.items():
                    path = extracted / relative
                    if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                        raise ValueError(f"Extracted content differs: {relative}")
                if not (extracted / ".streamlit/config.toml").is_file():
                    raise ValueError("Hidden Streamlit configuration missing.")
        for relative, item in expected.items():
            if digest(ROOT / relative) != item["sha256"]:
                raise ValueError(f"Source changed during verification: {relative}")
        os.replace(temporary, output)
    finally:
        if owned_temporary:
            temporary.unlink(missing_ok=True)
    package_hash = digest(output)
    reject_symlink_path(checksum)
    checksum.write_text(f"{package_hash}  {output.name}\n", encoding="ascii")
    receipt = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "application_version": version,
        "package": str(output.relative_to(ROOT)),
        "package_bytes": output.stat().st_size,
        "package_sha256": package_hash,
        "manifest": MANIFEST.as_posix(),
        "manifest_sha256": digest(ROOT / MANIFEST),
        "manifested_files": len(metadata),
        "archive_members_including_manifest": len(packaged),
        "checks": ["exact member allowlist", "unique relative member names", "CRC",
                   "every archived file SHA-256", "fresh extraction SHA-256",
                   "hidden configuration present", "source unchanged while packaging"],
        "application_tests": "Not rerun from extraction; see this version's local test and environment records.",
        "blueprint_v1_complete": release["v1_complete"],
        "release_status": release["status"],
        "release_status_record": release_record.as_posix(),
        "scope": "Package integrity only. Does not erase known acceptance limitations.",
    }
    write_json(ROOT / RECEIPT, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

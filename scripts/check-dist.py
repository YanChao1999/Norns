"""Fail unless dist/ ships the same Control Room docker compose serves from Vite."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ui_assets import control_room_bundle_errors  # noqa: E402


def _texts_from_zip(archive: zipfile.ZipFile) -> list[str]:
    texts: list[str] = []
    for name in archive.namelist():
        if "/norns/web/" not in f"/{name}" and not name.startswith("norns/web/"):
            continue
        if name.endswith("/") or Path(name).suffix.lower() not in {".html", ".js", ".css"}:
            continue
        texts.append(archive.read(name).decode("utf-8", errors="ignore"))
    return texts


def _texts_from_tar(archive: tarfile.TarFile) -> list[str]:
    texts: list[str] = []
    for member in archive.getmembers():
        name = member.name
        if "/norns/web/" not in f"/{name}":
            continue
        if not member.isfile() or Path(name).suffix.lower() not in {".html", ".js", ".css"}:
            continue
        extracted = archive.extractfile(member)
        if extracted is None:
            continue
        texts.append(extracted.read().decode("utf-8", errors="ignore"))
    return texts


def archive_control_room_errors(texts: list[str]) -> list[str]:
    if not any("color-scheme: dark" in text or ".login-page" in text for text in texts):
        return ["archive is missing Control Room CSS"]
    return control_room_bundle_errors(texts)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    wheels = sorted(root.glob("*.whl"))
    sdists = sorted(root.glob("*.tar.gz"))
    if not wheels:
        print(f"No wheel in {root}", file=sys.stderr)
        return 1
    if not sdists:
        print(f"No sdist in {root}", file=sys.stderr)
        return 1
    wheel = wheels[-1]
    if not wheel.name.startswith("norns_ide-"):
        print(f"Expected norns_ide-*.whl (PyPI name norns-ide); got {wheel.name}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        wheel_texts = _texts_from_zip(archive)
    if not any(name.endswith("norns/web/index.html") for name in names):
        print("Wheel is missing norns/web/index.html", file=sys.stderr)
        return 1
    if not any(name.endswith(".css") and "norns/web/" in name for name in names):
        print("Wheel is missing Control Room CSS (docker compose Vite would show a styled login)", file=sys.stderr)
        return 1
    errors = archive_control_room_errors(wheel_texts)
    if errors:
        print("Wheel UI does not match docker compose Control Room: " + "; ".join(errors), file=sys.stderr)
        return 1
    with tarfile.open(sdists[-1], "r:gz") as archive:
        sdist_names = archive.getnames()
        sdist_texts = _texts_from_tar(archive)
    if not any(name.endswith("norns/web/index.html") for name in sdist_names):
        print("Sdist is missing norns/web/index.html", file=sys.stderr)
        return 1
    if not any(name.endswith(".css") and "/norns/web/" in f"/{name}" for name in sdist_names):
        print("Sdist is missing Control Room CSS", file=sys.stderr)
        return 1
    errors = archive_control_room_errors(sdist_texts)
    if errors:
        print("Sdist UI does not match docker compose Control Room: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"OK {wheel.name} and {sdists[-1].name} match the docker compose Control Room UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

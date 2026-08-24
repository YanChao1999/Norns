"""Fail unless dist/ has a valid norns-ide wheel that includes the Control Room UI."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


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
    if not any(name.endswith("norns/web/index.html") for name in names):
        print("Wheel is missing norns/web/index.html", file=sys.stderr)
        return 1
    with tarfile.open(sdists[-1], "r:gz") as archive:
        sdist_names = archive.getnames()
    if not any(name.endswith("norns/web/index.html") for name in sdist_names):
        print("Sdist is missing norns/web/index.html", file=sys.stderr)
        return 1
    print(f"OK {wheel.name} and {sdists[-1].name} include the Control Room UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

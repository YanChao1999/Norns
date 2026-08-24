from __future__ import annotations

import argparse
import sys
from pathlib import Path

from norns import __version__
from norns.home import apply_config, default_home, init_home


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="norns",
        description="Norns local IDE — install once, configure locally, run in an Electron window.",
    )
    parser.add_argument("--version", action="version", version=f"norns {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create a local Norns home and config.toml")
    init_parser.add_argument("--home", type=Path, default=None, help="Override NORNS_HOME (default ~/.norns)")
    init_parser.add_argument("--force", action="store_true", help="Replace config.toml and delete norns.db")

    run_parser = sub.add_parser("run", help="Start the local IDE in an Electron window")
    run_parser.add_argument("--home", type=Path, default=None)
    run_parser.add_argument("--host", default=None)
    run_parser.add_argument("--port", type=int, default=None)
    run_parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run the local server without opening a desktop window",
    )

    args = parser.parse_args(argv)
    home = (args.home or default_home()).expanduser().resolve()

    if args.command == "init":
        try:
            path, password = init_home(home, force=args.force)
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Initialized Norns home at {home}")
        print(f"Config: {path}")
        print(f"Admin password: {password}")
        print("Edit config.toml, then run: norns run")
        return 0

    if args.command == "run":
        try:
            runtime = apply_config(home, host=args.host, port=args.port)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        from norns.desktop import run_ide

        return run_ide(host=runtime["host"], port=int(runtime["port"]), open_window=not args.no_window)

    parser.print_help()
    return 2

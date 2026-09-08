from __future__ import annotations

import os
import secrets
import tomllib
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULT_PORT = 8765


def default_home() -> Path:
    override = os.environ.get("NORNS_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".norns").resolve()


def config_path(home: Path) -> Path:
    return home / "config.toml"


def sqlite_url(db_path: Path) -> str:
    return "sqlite+aiosqlite:///" + db_path.resolve().as_posix()


def init_home(home: Path, *, force: bool = False) -> tuple[Path, str]:
    home.mkdir(parents=True, exist_ok=True)
    path = config_path(home)
    if path.exists() and not force:
        raise FileExistsError(
            f"Norns is already initialized at {home}. Use --force to replace config.toml and norns.db."
        )
    if force:
        for name in ("norns.db", "norns.db-wal", "norns.db-shm"):
            db_path = home / name
            if db_path.exists():
                db_path.unlink()
    secret_key = secrets.token_urlsafe(32)
    encryption_key = Fernet.generate_key().decode()
    admin_password = secrets.token_urlsafe(12)
    path.write_text(
        "\n".join(
            [
                "# Norns local IDE configuration",
                "[server]",
                'host = "127.0.0.1"',
                f"port = {DEFAULT_PORT}",
                "",
                "[auth]",
                'admin_username = "admin"',
                f'admin_password = "{admin_password}"',
                f'secret_key = "{secret_key}"',
                f'encryption_key = "{encryption_key}"',
                "",
                "[queue]",
                'backend = "inline"',
                "",
                "[sandbox]",
                "# directory = copy only (default; isolation by convention).",
                "# docker = copy + hardened container (bind copy only, cap-drop ALL, read-only rootfs).",
                "# none = shared path. Later: microvm / gvisor + policy layer (reserved stubs).",
                "# Allowlist the sandbox plugin on a column Agent for MCP tools (sandbox_run, …).",
                'backend = "directory"',
                '# image = "public.ecr.aws/docker/library/python:3.12-slim"',
                "",
                "[openai]",
                'api_key = ""',
                'base_url = "https://api.openai.com/v1"',
                'default_model = "gpt-4o"',
                "",
                "[cursor]",
                'api_key = ""',
                'base_url = "https://api.cursor.com/v1"',
                'default_model = "auto"',
                "",
                "[deepseek]",
                'api_key = ""',
                'base_url = "https://api.deepseek.com/v1"',
                'default_model = "deepseek-v4-flash"',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path, admin_password


def load_config(home: Path) -> dict:
    path = config_path(home)
    if not path.is_file():
        raise FileNotFoundError(f"No Norns config at {path}. Run: norns init")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def apply_config(home: Path, *, host: str | None = None, port: int | None = None) -> dict:
    data = load_config(home)
    server = data.get("server", {})
    auth = data.get("auth", {})
    queue = data.get("queue", {})
    sandbox = data.get("sandbox", {})
    openai = data.get("openai", {})
    cursor = data.get("cursor", {})
    deepseek = data.get("deepseek", {})
    resolved_host = host or str(server.get("host", "127.0.0.1"))
    resolved_port = port or int(server.get("port", DEFAULT_PORT))
    db_path = home / "norns.db"
    os.environ["DATABASE_URL"] = sqlite_url(db_path)
    os.environ["QUEUE_BACKEND"] = str(queue.get("backend", "inline"))
    os.environ["SANDBOX_BACKEND"] = str(sandbox.get("backend", "directory"))
    sandbox_root = str(sandbox.get("root", "") or "").strip()
    if sandbox_root:
        os.environ["NORNS_SANDBOX_ROOT"] = sandbox_root
    else:
        os.environ["NORNS_SANDBOX_ROOT"] = str((home / "sandboxes").resolve())
    sandbox_image = str(sandbox.get("image", "") or "").strip()
    if sandbox_image:
        os.environ["NORNS_SANDBOX_IMAGE"] = sandbox_image
    os.environ["SECRET_KEY"] = str(auth.get("secret_key", ""))
    os.environ["ENCRYPTION_KEY"] = str(auth.get("encryption_key", ""))
    os.environ["ADMIN_USERNAME"] = str(auth.get("admin_username", "admin"))
    os.environ["ADMIN_PASSWORD"] = str(auth.get("admin_password", "admin"))
    os.environ["OPENAI_API_KEY"] = str(openai.get("api_key", ""))
    os.environ["OPENAI_BASE_URL"] = str(openai.get("base_url", "https://api.openai.com/v1"))
    os.environ["DEFAULT_MODEL"] = str(openai.get("default_model", "gpt-4o"))
    os.environ["CURSOR_API_KEY"] = str(cursor.get("api_key", ""))
    os.environ["CURSOR_BASE_URL"] = str(cursor.get("base_url", "https://api.cursor.com/v1"))
    os.environ["CURSOR_DEFAULT_MODEL"] = str(cursor.get("default_model", "auto"))
    os.environ["DEEPSEEK_API_KEY"] = str(deepseek.get("api_key", ""))
    os.environ["DEEPSEEK_BASE_URL"] = str(deepseek.get("base_url", "https://api.deepseek.com/v1"))
    os.environ["DEEPSEEK_DEFAULT_MODEL"] = str(deepseek.get("default_model", "deepseek-v4-flash"))
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["NORNS_ENV"] = "local"
    os.environ["CORS_ORIGINS"] = f"http://{resolved_host}:{resolved_port}"
    os.environ["NORNS_HOME"] = str(home)
    return {"host": resolved_host, "port": resolved_port, "home": home}

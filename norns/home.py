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
                "[openai]",
                'api_key = ""',
                'base_url = "https://api.openai.com/v1"',
                'default_model = "gpt-4o"',
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
    openai = data.get("openai", {})
    resolved_host = host or str(server.get("host", "127.0.0.1"))
    resolved_port = port or int(server.get("port", DEFAULT_PORT))
    db_path = home / "norns.db"
    os.environ["DATABASE_URL"] = sqlite_url(db_path)
    os.environ["QUEUE_BACKEND"] = str(queue.get("backend", "inline"))
    os.environ["SECRET_KEY"] = str(auth.get("secret_key", ""))
    os.environ["ENCRYPTION_KEY"] = str(auth.get("encryption_key", ""))
    os.environ["ADMIN_USERNAME"] = str(auth.get("admin_username", "admin"))
    os.environ["ADMIN_PASSWORD"] = str(auth.get("admin_password", "admin"))
    os.environ["OPENAI_API_KEY"] = str(openai.get("api_key", ""))
    os.environ["OPENAI_BASE_URL"] = str(openai.get("base_url", "https://api.openai.com/v1"))
    os.environ["DEFAULT_MODEL"] = str(openai.get("default_model", "gpt-4o"))
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["NORNS_ENV"] = "local"
    os.environ["CORS_ORIGINS"] = f"http://{resolved_host}:{resolved_port}"
    os.environ["NORNS_HOME"] = str(home)
    return {"host": resolved_host, "port": resolved_port, "home": home}

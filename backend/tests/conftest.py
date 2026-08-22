from __future__ import annotations

import os
import secrets

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(32))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

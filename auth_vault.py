"""Dashboard login + local vault for camera credentials (no Docker master key)."""

from __future__ import annotations

import base64
import json
import os
import threading
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

AUTH_FILE_NAME = "auth.json"
MIN_PASSWORD_LEN = 8
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass
class AuthRecord:
    password_hash: str
    vault_salt_b64: str


class AuthVault:
    """
    Login password verifies access (argon2).
    Same password derives a Fernet key (PBKDF2) to encrypt camera secrets.
    No separate Docker/env master key — unlock is passphrase-only.
    """

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.auth_path = os.path.join(data_dir, AUTH_FILE_NAME)
        self._lock = threading.RLock()
        self._record: Optional[AuthRecord] = None
        self._fernet: Optional[Fernet] = None
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.auth_path):
            self._record = None
            return
        try:
            with open(self.auth_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self._record = AuthRecord(
                password_hash=str(raw["password_hash"]),
                vault_salt_b64=str(raw["vault_salt"]),
            )
        except Exception:  # noqa: BLE001
            self._record = None

    def _save_record(self, record: AuthRecord) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        payload = {
            "password_hash": record.password_hash,
            "vault_salt": record.vault_salt_b64,
        }
        with open(self.auth_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        try:
            os.chmod(self.auth_path, 0o600)
        except OSError:
            pass
        self._record = record

    @property
    def is_setup(self) -> bool:
        return self._record is not None

    @property
    def unlocked(self) -> bool:
        with self._lock:
            return self._fernet is not None

    def _derive_fernet(self, password: str, salt: bytes) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=390000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
        return Fernet(key)

    def setup(self, password: str) -> Tuple[bool, str]:
        if self.is_setup:
            return False, "Dashboard password is already configured"
        if len(password or "") < MIN_PASSWORD_LEN:
            return False, f"Password must be at least {MIN_PASSWORD_LEN} characters"
        salt = os.urandom(16)
        record = AuthRecord(
            password_hash=_ph.hash(password),
            vault_salt_b64=base64.urlsafe_b64encode(salt).decode("ascii"),
        )
        with self._lock:
            self._save_record(record)
            self._fernet = self._derive_fernet(password, salt)
        return True, "Dashboard password created"

    def unlock(self, password: str) -> Tuple[bool, str]:
        if not self._record:
            return False, "Dashboard password not set — complete setup first"
        try:
            _ph.verify(self._record.password_hash, password)
        except VerifyMismatchError:
            return False, "Invalid password"
        if _ph.check_needs_rehash(self._record.password_hash):
            self._record.password_hash = _ph.hash(password)
            self._save_record(self._record)
        salt = base64.urlsafe_b64decode(self._record.vault_salt_b64.encode("ascii"))
        with self._lock:
            self._fernet = self._derive_fernet(password, salt)
        return True, "Unlocked"

    def lock(self) -> None:
        with self._lock:
            self._fernet = None

    def encrypt(self, plaintext: str) -> str:
        with self._lock:
            if not self._fernet:
                raise RuntimeError("Vault is locked")
            token = self._fernet.encrypt((plaintext or "").encode("utf-8"))
            return token.decode("ascii")

    def decrypt(self, token: str) -> str:
        with self._lock:
            if not self._fernet:
                raise RuntimeError("Vault is locked")
            try:
                return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken as exc:
                raise RuntimeError("Failed to decrypt secret") from exc

    def change_password(self, current: str, new: str) -> Tuple[bool, str, Optional[Fernet]]:
        """
        Verify current, return old fernet so caller can re-encrypt secrets
        under the new key. Leaves vault unlocked with the new key on success.
        """
        if not self._record:
            return False, "Dashboard password not set", None
        if len(new or "") < MIN_PASSWORD_LEN:
            return False, f"New password must be at least {MIN_PASSWORD_LEN} characters", None
        try:
            _ph.verify(self._record.password_hash, current)
        except VerifyMismatchError:
            return False, "Current password is incorrect", None

        old_salt = base64.urlsafe_b64decode(self._record.vault_salt_b64.encode("ascii"))
        old_fernet = self._derive_fernet(current, old_salt)
        new_salt = os.urandom(16)
        new_fernet = self._derive_fernet(new, new_salt)
        record = AuthRecord(
            password_hash=_ph.hash(new),
            vault_salt_b64=base64.urlsafe_b64encode(new_salt).decode("ascii"),
        )
        with self._lock:
            self._save_record(record)
            self._fernet = new_fernet
        return True, "Password updated", old_fernet


def strip_rtsp_auth(url: str) -> str:
    """Remove username/password from an RTSP URL for safe on-disk storage."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return url
        host = parsed.hostname
        netloc = host
        if parsed.port:
            netloc = f"{host}:{parsed.port}"
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
    except Exception:  # noqa: BLE001
        return url


def redact_rtsp_url(url: str) -> str:
    """Short preview safe for API responses."""
    cleaned = strip_rtsp_auth(url or "")
    if len(cleaned) > 48:
        return cleaned[:48] + "…"
    return cleaned

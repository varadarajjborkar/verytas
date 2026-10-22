"""Per-agent Ed25519 signatures on everything an agent writes (X.800 digital
signature + data integrity).

Each agent role gets its own key, created on first use and kept outside the
repo with 0600 permissions. A finding is signed over its canonical content; the
runtime verifies before persisting and the API can re-verify on read, so a
finding edited directly in the database no longer verifies.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from verytas.security.audit import canonical

_ROLE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")


class AgentKeyring:
    def __init__(self, keys_dir: Path) -> None:
        self.keys_dir = keys_dir
        self._private: dict[str, Ed25519PrivateKey] = {}

    def _key(self, role: str, *, create: bool = True) -> Ed25519PrivateKey | None:
        if not _ROLE.match(role):
            raise ValueError(f"invalid agent role {role!r}")
        if role in self._private:
            return self._private[role]
        path = self.keys_dir / f"{role}.pem"
        if not path.exists() and not create:
            return None
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError(f"{path} is not an Ed25519 key")
        else:
            key = Ed25519PrivateKey.generate()
            self.keys_dir.mkdir(parents=True, exist_ok=True)
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(pem)
        self._private[role] = key
        return key

    def public_key(self, role: str) -> Ed25519PublicKey | None:
        key = self._key(role, create=False)
        return key.public_key() if key else None

    def sign(self, role: str, payload: dict[str, Any]) -> str:
        key = self._key(role)
        assert key is not None  # create=True always returns a key
        sig = key.sign(canonical(payload))
        return f"ed25519:{role}:{base64.b64encode(sig).decode()}"

    def verify(self, signature: str, payload: dict[str, Any]) -> bool:
        """Never creates key material: an unknown role simply fails verification."""
        try:
            scheme, role, b64 = signature.split(":", 2)
            if scheme != "ed25519":
                return False
            public = self.public_key(role)
            if public is None:
                return False
            public.verify(base64.b64decode(b64), canonical(payload))
            return True
        except (ValueError, InvalidSignature):
            return False

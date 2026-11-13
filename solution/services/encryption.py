
import hashlib
import hmac
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from solution.config import DATA_DIR, KEY_PATH, PHONE_HMAC_CONTEXT


class PIISecurity:
    """Encrypt PII and generate deterministic hashes for phone lookup."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._initialize_key()

        key = KEY_PATH.read_bytes()
        self.cipher = Fernet(key)

        self.lookup_key = hmac.new(
            key,
            PHONE_HMAC_CONTEXT,
            hashlib.sha256
        ).digest()

    def _initialize_key(self):
        """Create a persistent encryption key only if one does not exist."""
        if not KEY_PATH.exists():
            key = Fernet.generate_key()
            try:
                with KEY_PATH.open("xb") as key_file:
                    key_file.write(key)
            except FileExistsError:
                pass

    def encrypt(self, value):
        """Encrypt a non-empty string."""
        if value is None:
            return None

        return self.cipher.encrypt(
            str(value).encode("utf-8")
        ).decode("utf-8")

    def decrypt(self, encrypted_value):
        """Decrypt an encrypted string."""
        if encrypted_value is None:
            return None

        try:
            return self.cipher.decrypt(
                encrypted_value.encode("utf-8")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt PII value.") from exc

    def phone_hash(self, canonical_phone):
        """Generate a deterministic HMAC for phone-based lead matching."""
        if not canonical_phone:
            raise ValueError("Phone number cannot be empty.")

        return hmac.new(
            self.lookup_key,
            canonical_phone.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

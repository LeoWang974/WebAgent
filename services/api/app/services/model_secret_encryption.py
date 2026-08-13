import binascii
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

MODEL_SECRET_PREFIX = "enc:v1"


class ModelSecretError(RuntimeError):
    """Base error for model credential encryption without secret disclosure."""


class ModelSecretConfigurationError(ModelSecretError):
    """Raised when the configured keyring cannot encrypt or decrypt credentials."""


class ModelSecretDecryptionError(ModelSecretError):
    """Raised when a stored credential cannot be decrypted by the configured keyring."""


@dataclass(frozen=True)
class SecretRotationResult:
    value: str | None
    changed: bool


class ModelSecretCipher:
    def __init__(self, active_key: str | None, previous_keys: list[str] | None = None) -> None:
        self._active_key = self._normalize_key(active_key)
        self._active_key_id: str | None = None
        self._keyring: dict[str, Fernet] = {}

        for key in [self._active_key, *(previous_keys or [])]:
            normalized = self._normalize_key(key)
            if not normalized:
                continue
            try:
                encoded_key = normalized.encode("ascii")
                fernet = Fernet(encoded_key)
            except (binascii.Error, TypeError, ValueError) as error:
                raise ModelSecretConfigurationError(
                    "MODEL_CONFIG_ENCRYPTION_KEY contains an invalid Fernet key."
                ) from error
            key_id = self._key_id(normalized)
            self._keyring[key_id] = fernet
            if normalized == self._active_key:
                self._active_key_id = key_id

    @property
    def active_key_id(self) -> str | None:
        return self._active_key_id

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        return bool(value and value.startswith(f"{MODEL_SECRET_PREFIX}:"))

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        self._reject_unknown_envelope(value)
        if self.is_encrypted(value):
            return self.rotate(value).value
        fernet = self._active_fernet()
        token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{MODEL_SECRET_PREFIX}:{self._active_key_id}:{token}"

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        self._reject_unknown_envelope(value)
        if not self.is_encrypted(value):
            return value

        key_id, token = self._parse_envelope(value)
        fernet = self._keyring.get(key_id)
        if fernet is None:
            raise ModelSecretDecryptionError(
                "Stored model credential requires an encryption key that is not configured."
            )
        try:
            return fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as error:
            raise ModelSecretDecryptionError(
                "Stored model credential is invalid or has been tampered with."
            ) from error

    def rotate(self, value: str | None) -> SecretRotationResult:
        if not value:
            return SecretRotationResult(value=None, changed=False)
        if not self._active_key_id:
            raise ModelSecretConfigurationError(
                "MODEL_CONFIG_ENCRYPTION_KEY is required to store model credentials."
            )
        if self.is_encrypted(value):
            key_id, _token = self._parse_envelope(value)
            if key_id == self._active_key_id:
                self.decrypt(value)
                return SecretRotationResult(value=value, changed=False)

        plaintext = self.decrypt(value)
        return SecretRotationResult(value=self.encrypt(plaintext), changed=True)

    def _active_fernet(self) -> Fernet:
        if not self._active_key_id:
            raise ModelSecretConfigurationError(
                "MODEL_CONFIG_ENCRYPTION_KEY is required to store model credentials."
            )
        return self._keyring[self._active_key_id]

    @staticmethod
    def _normalize_key(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @staticmethod
    def _key_id(key: str) -> str:
        return hashlib.sha256(key.encode("ascii")).hexdigest()[:16]

    @staticmethod
    def _parse_envelope(value: str) -> tuple[str, str]:
        parts = value.split(":", 3)
        if len(parts) != 4 or parts[0] != "enc" or parts[1] != "v1":
            raise ModelSecretDecryptionError("Stored model credential has an unknown format.")
        key_id, token = parts[2], parts[3]
        if not key_id or not token:
            raise ModelSecretDecryptionError("Stored model credential has an invalid envelope.")
        return key_id, token

    @staticmethod
    def _reject_unknown_envelope(value: str) -> None:
        if value.startswith("enc:") and not value.startswith(f"{MODEL_SECRET_PREFIX}:"):
            raise ModelSecretDecryptionError("Stored model credential has an unknown format.")


def _configured_previous_keys() -> list[str]:
    return [
        value.strip()
        for value in settings.model_config_encryption_previous_keys.split(",")
        if value.strip()
    ]


def model_secret_cipher() -> ModelSecretCipher:
    return ModelSecretCipher(
        settings.model_config_encryption_key,
        _configured_previous_keys(),
    )


def encrypt_model_secret(value: str | None) -> str | None:
    return model_secret_cipher().encrypt(value)


def decrypt_model_secret(value: str | None) -> str | None:
    return model_secret_cipher().decrypt(value)


def mask_model_secret(value: str | None) -> str | None:
    plaintext = decrypt_model_secret(value)
    if not plaintext:
        return None
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:4]}****{plaintext[-4:]}"

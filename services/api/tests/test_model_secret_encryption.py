import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.models import AgentRun, ModelConfig
from app.services.model_secret_encryption import (
    ModelSecretCipher,
    ModelSecretConfigurationError,
    ModelSecretDecryptionError,
    decrypt_model_secret,
)
from app.services.model_secret_migration import migrate_model_secrets


def _new_key() -> str:
    return Fernet.generate_key().decode("ascii")


def test_model_secret_round_trip_uses_versioned_envelope():
    cipher = ModelSecretCipher(_new_key())

    encrypted = cipher.encrypt("sk-private-value")

    assert encrypted is not None
    assert encrypted.startswith(f"enc:v1:{cipher.active_key_id}:")
    assert "sk-private-value" not in encrypted
    assert cipher.decrypt(encrypted) == "sk-private-value"
    assert cipher.rotate(encrypted).changed is False


def test_model_secret_rotation_accepts_previous_key():
    old_key = _new_key()
    old_cipher = ModelSecretCipher(old_key)
    old_value = old_cipher.encrypt("sk-rotate-me")
    new_key = _new_key()
    cipher = ModelSecretCipher(new_key, [old_key])

    rotated = cipher.rotate(old_value)

    assert rotated.changed is True
    assert rotated.value != old_value
    assert cipher.decrypt(rotated.value) == "sk-rotate-me"


def test_model_secret_rejects_missing_previous_key():
    old_value = ModelSecretCipher(_new_key()).encrypt("sk-unavailable")
    cipher = ModelSecretCipher(_new_key())

    with pytest.raises(ModelSecretDecryptionError, match="not configured"):
        cipher.decrypt(old_value)


def test_model_secret_rejects_invalid_key_and_unknown_envelope():
    with pytest.raises(ModelSecretConfigurationError, match="invalid Fernet key"):
        ModelSecretCipher("not-a-fernet-key")

    cipher = ModelSecretCipher(_new_key())
    with pytest.raises(ModelSecretDecryptionError, match="unknown format"):
        cipher.decrypt("enc:v2:future-key:future-token")


def test_model_secret_rejects_tampered_ciphertext():
    cipher = ModelSecretCipher(_new_key())
    encrypted = cipher.encrypt("sk-private-value")
    assert encrypted is not None
    prefix, token = encrypted.rsplit(":", 1)
    replacement = "A" if token[10] != "A" else "B"
    tampered = f"{prefix}:{token[:10]}{replacement}{token[11:]}"

    with pytest.raises(ModelSecretDecryptionError, match="tampered"):
        cipher.decrypt(tampered)


@pytest.mark.asyncio
async def test_migrate_model_secrets_encrypts_plaintext_and_rotates_old_ciphertext(
    db_sessionmaker,
    monkeypatch,
):
    old_key = _new_key()
    new_key = _new_key()
    old_snapshot = ModelSecretCipher(old_key).encrypt("sk-old-run")
    monkeypatch.setattr(settings, "model_config_encryption_key", new_key)
    monkeypatch.setattr(settings, "model_config_encryption_previous_keys", old_key)

    async with db_sessionmaker() as db:
        model = ModelConfig(
            user_id="user-1",
            name="custom-model",
            provider="custom",
            encrypted_api_key="sk-legacy-model",
            is_default=True,
            is_available=True,
        )
        run = AgentRun(
            conversation_id="conversation-1",
            status="completed",
            title="Historical run",
            progress=100,
            model_api_key_snapshot=old_snapshot,
        )
        db.add_all([model, run])
        await db.commit()

    async with db_sessionmaker() as db:
        dry_run = await migrate_model_secrets(db, apply=False)
    assert dry_run.changed == 2
    assert dry_run.unreadable == 0
    assert dry_run.applied is False

    async with db_sessionmaker() as db:
        model_before = (await db.execute(select(ModelConfig))).scalar_one()
        assert model_before.encrypted_api_key == "sk-legacy-model"

        applied = await migrate_model_secrets(db, apply=True)
        assert applied.changed == 2
        assert applied.applied is True

    async with db_sessionmaker() as db:
        migrated_model = (await db.execute(select(ModelConfig))).scalar_one()
        migrated_run = (await db.execute(select(AgentRun))).scalar_one()
        assert migrated_model.encrypted_api_key.startswith("enc:v1:")
        assert migrated_run.model_api_key_snapshot.startswith("enc:v1:")
        assert decrypt_model_secret(migrated_model.encrypted_api_key) == "sk-legacy-model"
        assert decrypt_model_secret(migrated_run.model_api_key_snapshot) == "sk-old-run"


@pytest.mark.asyncio
async def test_migrate_model_secrets_rolls_back_when_old_key_is_missing(
    db_sessionmaker,
    monkeypatch,
):
    unavailable_value = ModelSecretCipher(_new_key()).encrypt("sk-unavailable")
    monkeypatch.setattr(settings, "model_config_encryption_key", _new_key())
    monkeypatch.setattr(settings, "model_config_encryption_previous_keys", "")

    async with db_sessionmaker() as db:
        db.add_all(
            [
                ModelConfig(
                    user_id="user-1",
                    name="legacy-model",
                    provider="custom",
                    encrypted_api_key="sk-legacy-model",
                    is_default=True,
                    is_available=True,
                ),
                AgentRun(
                    conversation_id="conversation-1",
                    status="completed",
                    title="Unreadable run",
                    progress=100,
                    model_api_key_snapshot=unavailable_value,
                ),
            ]
        )
        await db.commit()

    async with db_sessionmaker() as db:
        report = await migrate_model_secrets(db, apply=True)

    assert report.applied is False
    assert report.unreadable == 1
    async with db_sessionmaker() as db:
        model = (await db.execute(select(ModelConfig))).scalar_one()
        assert model.encrypted_api_key == "sk-legacy-model"

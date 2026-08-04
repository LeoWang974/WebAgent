from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, ModelConfig
from app.services.model_secret_encryption import (
    ModelSecretCipher,
    ModelSecretDecryptionError,
    model_secret_cipher,
)


@dataclass
class SecretCollectionMigration:
    scanned: int = 0
    changed: int = 0
    unreadable: int = 0


@dataclass
class ModelSecretMigrationReport:
    active_key_id: str
    apply_requested: bool
    applied: bool = False
    model_configs: SecretCollectionMigration = field(default_factory=SecretCollectionMigration)
    agent_runs: SecretCollectionMigration = field(default_factory=SecretCollectionMigration)

    @property
    def unreadable(self) -> int:
        return self.model_configs.unreadable + self.agent_runs.unreadable

    @property
    def changed(self) -> int:
        return self.model_configs.changed + self.agent_runs.changed


async def migrate_model_secrets(
    db: AsyncSession,
    *,
    apply: bool,
) -> ModelSecretMigrationReport:
    cipher = model_secret_cipher()
    if not cipher.active_key_id:
        raise RuntimeError("MODEL_CONFIG_ENCRYPTION_KEY is required for migration.")

    report = ModelSecretMigrationReport(
        active_key_id=cipher.active_key_id,
        apply_requested=apply,
    )
    await _migrate_collection(
        db,
        ModelConfig,
        "encrypted_api_key",
        report.model_configs,
        cipher,
        apply=apply,
    )
    await _migrate_collection(
        db,
        AgentRun,
        "model_api_key_snapshot",
        report.agent_runs,
        cipher,
        apply=apply,
    )

    if apply and not report.unreadable:
        await db.commit()
        report.applied = True
    else:
        await db.rollback()
    return report


async def _migrate_collection(
    db: AsyncSession,
    model_type,
    attribute: str,
    stats: SecretCollectionMigration,
    cipher: ModelSecretCipher,
    *,
    apply: bool,
) -> None:
    result = await db.execute(
        select(model_type).where(getattr(model_type, attribute).is_not(None))
    )
    for record in result.scalars().all():
        stats.scanned += 1
        stored_value = getattr(record, attribute)
        try:
            rotation = cipher.rotate(stored_value)
        except ModelSecretDecryptionError:
            stats.unreadable += 1
            continue
        if not rotation.changed:
            continue
        stats.changed += 1
        if apply:
            setattr(record, attribute, rotation.value)

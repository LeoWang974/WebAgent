# Model Credential Encryption and Rotation

WebAgent encrypts user-provided model API keys before storing them in
`model_configs.encrypted_api_key` or `agent_runs.model_api_key_snapshot`.
Runtime adapters receive plaintext only in their per-run environment.

## Ciphertext format

Stored values use the versioned envelope:

```text
enc:v1:<key-id>:<fernet-token>
```

`key-id` is a one-way identifier derived from the encryption key. It is safe to
log for migration diagnostics. The key and decrypted credential must never be
logged.

Legacy plaintext values remain readable only to support migration. All new
writes and Agent Run snapshots require `MODEL_CONFIG_ENCRYPTION_KEY` and are
stored encrypted.

## Key storage

Generate a Fernet key:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Production must provide:

```text
MODEL_CONFIG_ENCRYPTION_KEY=<active-fernet-key>
MODEL_CONFIG_ENCRYPTION_PREVIOUS_KEYS=<old-key-1>,<old-key-2>
```

Do not commit these values. Back up the active key separately from the database.
Losing every key that can decrypt a stored envelope makes the affected model
credentials unrecoverable.

`scripts/dev-api.ps1` creates `runtime/secrets/model-config.key` when no key is
provided. `scripts/cci-start.sh` creates or reuses
`$WEBAGENT_ROOT/secrets/model-config.key` with mode `0600`.

## Legacy migration

Back up PostgreSQL, then run a dry run from `services/api`:

```bash
python scripts/migrate_model_secrets.py
```

Apply the migration atomically:

```bash
python scripts/migrate_model_secrets.py --apply
```

The command reports counts only. If any value cannot be decrypted, the complete
transaction is rolled back and the command exits non-zero.

## Rotation procedure

1. Pause API and workers so no model credentials are written during rotation.
2. Move the current key to `MODEL_CONFIG_ENCRYPTION_PREVIOUS_KEYS` and configure
   a newly generated key as `MODEL_CONFIG_ENCRYPTION_KEY`.
3. Run `python scripts/migrate_model_secrets.py` and review counts.
4. Run `python scripts/migrate_model_secrets.py --apply`.
5. Run `python scripts/migrate_model_secrets.py --require-current`; it must
   report zero changed and zero unreadable records.
6. Restart API and workers, verify a configured model and a historical Run.
7. Remove retired keys only after backups and all deployed processes use the
   new key.

Never remove an old key before both `model_configs` and `agent_runs` have been
rotated. Agent Run snapshots are required for deterministic retries and recovery.

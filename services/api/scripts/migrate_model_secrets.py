# File purpose: Automates the migrate model secrets development, deployment, or maintenance
# workflow.
# Main declarations: parse_args parses args; run handles run.

import argparse
import asyncio

from app.db.session import AsyncSessionLocal
from app.services.model_secret_migration import migrate_model_secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Encrypt legacy model credentials and rotate old ciphertext to the active key."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the command performs a dry run.",
    )
    parser.add_argument(
        "--require-current",
        action="store_true",
        help="Exit non-zero when any credential still requires migration or rotation.",
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    async with AsyncSessionLocal() as db:
        report = await migrate_model_secrets(db, apply=args.apply)

    mode = "apply" if args.apply else "dry-run"
    print(f"Model secret migration mode={mode} active_key_id={report.active_key_id}")
    print(
        "model_configs "
        f"scanned={report.model_configs.scanned} "
        f"changed={report.model_configs.changed} "
        f"unreadable={report.model_configs.unreadable}"
    )
    print(
        "agent_runs "
        f"scanned={report.agent_runs.scanned} "
        f"changed={report.agent_runs.changed} "
        f"unreadable={report.agent_runs.unreadable}"
    )
    if report.unreadable:
        print("Migration aborted: one or more credentials could not be decrypted.")
        return 2
    if args.apply and not report.applied:
        print("Migration was not committed.")
        return 3
    if args.require_current and report.changed:
        print("Stored credentials are not all encrypted with the active key.")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

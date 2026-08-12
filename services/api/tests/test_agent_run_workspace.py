from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Artifact, Conversation, User
from app.services.agent_run_workspace import stage_conversation_artifacts


@pytest.mark.asyncio
async def test_stage_conversation_artifacts_copies_only_ready_primary_files(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
    tmp_path: Path,
):
    source = tmp_path / "report.md"
    source.write_text("# Report", encoding="utf-8")
    ignored = tmp_path / "plan.json"
    ignored.write_text("{}", encoding="utf-8")

    async with db_sessionmaker() as db:
        conversation = Conversation(user_id=seeded_users["owner"].id, title="Test")
        db.add(conversation)
        await db.flush()
        db.add_all(
            [
                Artifact(
                    conversation_id=conversation.id,
                    type="markdown_report",
                    title="Report",
                    status="ready",
                    artifact_metadata={"path": str(source)},
                    is_primary=True,
                ),
                Artifact(
                    conversation_id=conversation.id,
                    type="debug_json",
                    title="Plan",
                    status="ready",
                    artifact_metadata={"path": str(ignored)},
                    is_primary=False,
                ),
            ]
        )
        await db.commit()

        workspace = tmp_path / "run"
        workspace.mkdir()
        hermes_context = tmp_path / "hermes-home" / "context"
        staged = await stage_conversation_artifacts(
            db,
            conversation.id,
            workspace,
            mirror_dirs=(hermes_context,),
        )

    assert staged == [workspace / "context" / "report.md"]
    assert staged[0].read_text(encoding="utf-8") == "# Report"
    assert (workspace / "report.md").read_text(encoding="utf-8") == "# Report"
    assert (hermes_context / "report.md").read_text(encoding="utf-8") == "# Report"
    assert not (workspace / "context" / "plan.json").exists()


@pytest.mark.asyncio
async def test_stage_conversation_artifacts_skips_copying_a_file_onto_itself(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
    tmp_path: Path,
):
    workspace = tmp_path / "run"
    context_dir = workspace / "context"
    context_dir.mkdir(parents=True)
    source = context_dir / "report.md"
    source.write_text("# Existing report", encoding="utf-8")

    async with db_sessionmaker() as db:
        conversation = Conversation(user_id=seeded_users["owner"].id, title="Test")
        db.add(conversation)
        await db.flush()
        db.add(
            Artifact(
                conversation_id=conversation.id,
                type="markdown_report",
                title="Report",
                status="ready",
                artifact_metadata={"path": str(source)},
                is_primary=True,
            )
        )
        await db.commit()

        staged = await stage_conversation_artifacts(db, conversation.id, workspace)

    assert staged == [source]
    assert source.read_text(encoding="utf-8") == "# Existing report"

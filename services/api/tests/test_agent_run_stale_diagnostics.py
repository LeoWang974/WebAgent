from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AgentRun as DBAgentRun
from app.models import AgentRunEvent as DBAgentRunEvent
from app.models import Conversation
from app.services.agent_runs import STALE_RUN_GRACE_SECONDS, mark_stale_agent_runs


@pytest.mark.asyncio
async def test_mark_stale_agent_runs_preserves_last_event_diagnostics(
    db_sessionmaker,
    seeded_users,
):
    owner = seeded_users["owner"]
    async with db_sessionmaker() as db:
        conversation = Conversation(
            user_id=owner.id,
            title="Hermes stale diagnostics",
            type="chat",
            visibility="private",
        )
        db.add(conversation)
        await db.flush()
        run = DBAgentRun(
            conversation_id=conversation.id,
            status="running",
            title="Hermes run",
            progress=42,
            adapter_key="hermes",
        )
        db.add(run)
        await db.flush()
        db.add(
            DBAgentRunEvent(
                run_id=run.id,
                event_type="raw_activity",
                payload={
                    "eventType": "agent_stage",
                    "status": "running",
                    "progress": 42,
                    "rawLogPath": "/tmp/hermes-raw.log",
                    "stdoutTail": "Serper probe line",
                    "stderrTail": "",
                    "step": {
                        "label": "Hermes 正在执行工具调用，等待下一段运行输出...",
                        "status": "running",
                    },
                },
            )
        )
        stale_at = datetime.now(UTC) - timedelta(seconds=STALE_RUN_GRACE_SECONDS + 60)
        run.updated_at = stale_at
        await db.commit()

        await mark_stale_agent_runs(db, owner, conversation.id)

        refreshed = await db.get(DBAgentRun, run.id)
        assert refreshed is not None
        assert refreshed.status == "disconnected"
        assert "Last stage: Hermes 正在执行工具调用" in (refreshed.error or "")

        events = (
            await db.execute(
                select(DBAgentRunEvent)
                .where(DBAgentRunEvent.run_id == run.id)
                .order_by(DBAgentRunEvent.created_at.desc())
            )
        ).scalars().all()
        disconnected = next(event for event in events if event.event_type == "disconnected")
        assert disconnected.event_type == "disconnected"
        assert disconnected.payload["diagnosticType"] == "stale_run"
        assert disconnected.payload["lastEventType"] == "raw_activity"
        assert disconnected.payload["rawLogPath"] == "/tmp/hermes-raw.log"
        assert disconnected.payload["stdoutTail"] == "Serper probe line"

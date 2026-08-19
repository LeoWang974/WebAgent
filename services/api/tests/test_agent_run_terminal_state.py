# File purpose: Verifies test agent run terminal state behavior and its regression contracts.
# Main declarations: test_completed_run_ignores_late_cancellation verifies completed run ignores
# late cancellation; test_successful_completion_can_win_cancel_race verifies successful completion
# can win cancel race.

import pytest

from app.models import AgentRun, Conversation
from app.services.agent_runs import finish_db_agent_run


@pytest.mark.asyncio
async def test_completed_run_ignores_late_cancellation(db_sessionmaker, seeded_users):
    async with db_sessionmaker() as db:
        conversation = Conversation(
            user_id=seeded_users["owner"].id,
            title="Terminal state test",
            type="chat",
            visibility="private",
        )
        db.add(conversation)
        await db.flush()
        run = AgentRun(
            conversation_id=conversation.id,
            status="running",
            title="Hermes run",
            progress=90,
            adapter_key="hermes",
        )
        db.add(run)
        await db.commit()

        await finish_db_agent_run(
            db,
            run,
            status="completed",
            label="Agent run completed",
        )
        ignored_event = await finish_db_agent_run(
            db,
            run,
            status="cancelled",
            label="Agent run cancelled",
        )

        await db.refresh(run)
        assert run.status == "completed"
        assert run.progress == 100
        assert ignored_event.event_type == "terminal_transition_ignored"
        assert ignored_event.payload["status"] == "completed"
        assert ignored_event.payload["requestedStatus"] == "cancelled"
        assert ignored_event.payload["transitionIgnored"] is True


@pytest.mark.asyncio
async def test_successful_completion_can_win_cancel_race(db_sessionmaker, seeded_users):
    async with db_sessionmaker() as db:
        conversation = Conversation(
            user_id=seeded_users["owner"].id,
            title="Completion race test",
            type="chat",
            visibility="private",
        )
        db.add(conversation)
        await db.flush()
        run = AgentRun(
            conversation_id=conversation.id,
            status="cancelled",
            title="Hermes run",
            progress=90,
            adapter_key="hermes",
        )
        db.add(run)
        await db.commit()

        event = await finish_db_agent_run(
            db,
            run,
            status="completed",
            label="Agent run completed",
        )

        await db.refresh(run)
        assert run.status == "completed"
        assert run.progress == 100
        assert event.event_type == "completed"
        assert event.payload["transitionIgnored"] is False

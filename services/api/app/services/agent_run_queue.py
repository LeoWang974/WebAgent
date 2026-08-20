# File purpose: Classifies messages into priority queues without altering user prompts.
# Main declarations: is_short_chat_request classifies scheduling cost; queue_for_message selects
# a queue; estimated_queue_position reads the current Redis queue length.

import logging
import re

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Queue classification controls scheduling priority only. It never selects a skill
# or changes the prompt delivered to Hermes.
LONG_TASK_MARKERS = (
    "报告",
    "调研",
    "研究",
    "生成",
    "导出",
    "输出",
    "幻灯片",
    "演示文稿",
    "网页",
    "文件",
    "图像",
    "图片",
)
CONVERSATION_META_MARKERS = (
    "上一轮",
    "上一次",
    "刚才",
    "之前",
    "previous turn",
    "last turn",
    "earlier",
)
QUESTION_MARKERS = (
    "?",
    "？",
    "几",
    "什么",
    "是否",
    "哪",
    "how many",
    "what",
    "did i",
)

# Hyphens and underscores are identifier characters here so validation tokens
# such as ``QA-B-AFTER-PPT-OK`` do not become long artifact requests.
_ARTIFACT_TERM_PATTERN = re.compile(
    r"(?<![a-z0-9_-])(?:\.(?:md|html?|pptx?|csv|xlsx)|markdown|html|pptx?|csv|excel)"
    r"(?![a-z0-9_-])",
    re.IGNORECASE,
)


def is_short_chat_request(content: str) -> bool:
    normalized = " ".join(content.strip().split())
    if not normalized or len(normalized) > 80:
        return False
    lowered = normalized.lower()
    if any(marker in lowered for marker in CONVERSATION_META_MARKERS) and any(
        marker in lowered for marker in QUESTION_MARKERS
    ):
        return True
    has_long_intent = any(marker in lowered for marker in LONG_TASK_MARKERS)
    has_artifact_term = _ARTIFACT_TERM_PATTERN.search(lowered) is not None
    return not (has_long_intent or has_artifact_term)


def queue_for_message(content: str) -> tuple[str, str]:
    if is_short_chat_request(content):
        return settings.short_chat_queue_name, "短对话优先队列"
    return settings.agent_run_queue_name, "长任务队列"


async def estimated_queue_position(queue_name: str) -> int | None:
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            return int(await redis.llen(queue_name)) + 1
        finally:
            await redis.aclose()
    except Exception as error:
        logger.debug("Could not estimate queue position for %s: %s", queue_name, error)
        return None

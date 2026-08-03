import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

LONG_TASK_MARKERS = (
    ".html",
    ".md",
    ".ppt",
    ".pptx",
    "csv",
    "excel",
    "html",
    "markdown",
    "ppt",
    "pptx",
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


def is_short_chat_request(content: str, resolved_skill_key: str | None) -> bool:
    if resolved_skill_key:
        return False
    normalized = " ".join(content.strip().split())
    if not normalized or len(normalized) > 80:
        return False
    lowered = normalized.lower()
    return not any(marker in lowered for marker in LONG_TASK_MARKERS)


def queue_for_message(content: str, resolved_skill_key: str | None) -> tuple[str, str]:
    if is_short_chat_request(content, resolved_skill_key):
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

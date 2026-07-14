import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact

SUPPORTED_CONTEXT_SKILLS = {"data_analysis", "deep_research", "ppt_generation", "u1_image"}
MAX_CONTEXT_ARTIFACTS = {
    "data_analysis": 4,
    "deep_research": 3,
    "ppt_generation": 6,
    "u1_image": 5,
}


@dataclass(frozen=True)
class RuntimeArtifactContext:
    path: str
    score: int
    title: str
    type: str


def normalize_runtime_path(path: object) -> str:
    raw_path = str(path)
    if raw_path.startswith("\\\\wsl.localhost\\Ubuntu\\"):
        return "/" + raw_path.removeprefix("\\\\wsl.localhost\\Ubuntu\\").replace("\\", "/")
    if raw_path.startswith("\\\\wsl$\\Ubuntu\\"):
        return "/" + raw_path.removeprefix("\\\\wsl$\\Ubuntu\\").replace("\\", "/")
    match = re.match(r"^([A-Za-z]):\\(.*)$", raw_path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return raw_path.replace("\\", "/")


def artifact_path(artifact: Artifact) -> str | None:
    metadata = artifact.artifact_metadata or {}
    path = metadata.get("originalPath") or metadata.get("path")
    if not path:
        return None
    normalized = str(path).replace("\\", "/").lower()
    if "/.hermes/skills/" in normalized or "/node_modules/" in normalized:
        return None
    return normalize_runtime_path(path)


def skill_type_score(skill_key: str, artifact_type: str) -> int:
    scores = {
        "data_analysis": {
            "data_table": 100,
            "chart": 90,
            "markdown_report": 45,
            "html_page": 30,
            "ppt_deck": 10,
            "image_result": 5,
        },
        "deep_research": {
            "markdown_report": 90,
            "html_page": 70,
            "data_table": 45,
            "chart": 35,
            "ppt_deck": 20,
            "image_result": 10,
        },
        "ppt_generation": {
            "markdown_report": 100,
            "html_page": 85,
            "image_result": 60,
            "data_table": 40,
            "chart": 40,
            "ppt_deck": 20,
        },
        "u1_image": {
            "markdown_report": 100,
            "html_page": 75,
            "ppt_deck": 45,
            "image_result": 35,
            "data_table": 15,
            "chart": 15,
        },
    }
    return scores.get(skill_key, {}).get(artifact_type, 0)


def artifact_quality_score(artifact: Artifact, path: str) -> int:
    title = artifact.title.lower()
    normalized_path = path.lower()
    score = 0
    if (
        normalized_path.endswith("/report.md")
        or normalized_path.endswith("/final_report.md")
        or "深度研究报告" in title
        or "深度调研报告" in title
    ):
        score += 40
    if (
        "/sections/" in normalized_path
        or normalized_path.endswith("/plan.md")
        or normalized_path.endswith("/outline.json")
        or "task_pack" in normalized_path
        or "raw_documents" in normalized_path
    ):
        score -= 50
    return score


def title_match_score(content: str, title: str) -> int:
    normalized_content = content.lower()
    normalized_title = title.lower()
    for focus_term in re.findall(r"[《「“\"']([^》」”\"']{2,})[》」”\"']", content):
        if focus_term.lower() in normalized_title:
            return 60
    if normalized_title and normalized_title in normalized_content:
        return 60
    for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized_title):
        if token.lower() in normalized_content:
            return 20
    return 0


def instruction_for_skill(skill_key: str) -> str:
    if skill_key == "data_analysis":
        return (
            "若用户要求继续分析已有数据，请优先从下方少量相关表格、图表或报告中选择输入；"
            "不要一次读取所有历史产物。完成时输出生成的数据表、图表或报告文件路径。"
        )
    if skill_key == "deep_research":
        return (
            "若用户要求继续调研已有主题，请优先参考下方少量相关报告、HTML 或数据表；"
            "不要把历史产物全部展开。完成时输出最终 Markdown/HTML 报告文件路径。"
        )
    if skill_key == "ppt_generation":
        return (
            "若用户提到已有 Markdown/HTML/图片，请优先从下方会话产物中选择最匹配文件；"
            "生成 PPT 时需要明确输出最终 PPTX 或可转换的 HTML 页面路径。"
        )
    if skill_key == "u1_image":
        return (
            "用户提到 U1 生图时，表示调用 u1_image/sn-image-base 生图能力，"
            "不是名为 U1 的参考图片。若用户提到已有 Markdown/HTML/PPT，"
            "优先从下方会话产物中选择最匹配文件；直接生成图片，并在完成时输出图片文件路径。"
        )
    return ""


def build_context_line(index: int, artifact: RuntimeArtifactContext) -> str:
    return f"{index}. {artifact.type}: {artifact.title} -> {artifact.path}"


async def build_runtime_content(
    db: AsyncSession,
    session_id: str,
    content: str,
    skill_key: str | None,
) -> str:
    if skill_key not in SUPPORTED_CONTEXT_SKILLS:
        return content

    result = await db.execute(
        select(Artifact)
        .where(Artifact.conversation_id == session_id)
        .order_by(Artifact.created_at.desc())
        .limit(40)
    )
    candidates: list[RuntimeArtifactContext] = []
    seen_paths: set[str] = set()

    for artifact in result.scalars().all():
        path = artifact_path(artifact)
        if not path or path in seen_paths:
            continue
        base_score = skill_type_score(skill_key, artifact.type)
        if base_score <= 0:
            continue
        score = (
            base_score
            + title_match_score(content, artifact.title)
            + artifact_quality_score(artifact, path)
        )
        candidates.append(
            RuntimeArtifactContext(
                path=path,
                score=score,
                title=artifact.title,
                type=artifact.type,
            )
        )
        seen_paths.add(path)

    if not candidates:
        return content

    candidates.sort(key=lambda item: item.score, reverse=True)
    selected = candidates[: MAX_CONTEXT_ARTIFACTS.get(skill_key, 4)]
    context = " | ".join(
        build_context_line(index, artifact)
        for index, artifact in enumerate(selected, start=1)
    )
    instruction = instruction_for_skill(skill_key)
    return f"{content}\n\n[WebAgent runtime context]\n{instruction}\nAvailable artifacts: {context}"

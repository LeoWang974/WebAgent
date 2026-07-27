import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact

SUPPORTED_CONTEXT_SKILLS = {
    "data_analysis",
    "deep_research",
    "html_generation",
    "ppt_generation",
    "u1_image",
}
DEFAULT_ADAPTER_KEY = "hermes"

MAX_CONTEXT_ARTIFACTS_BY_ADAPTER = {
    "hermes": {
        "data_analysis": 4,
        "deep_research": 3,
        "html_generation": 4,
        "ppt_generation": 6,
        "u1_image": 5,
    },
    "openclaw": {
        "data_analysis": 3,
        "deep_research": 2,
        "html_generation": 2,
        "ppt_generation": 3,
        "u1_image": 2,
    },
}

TYPE_SCORES_BY_ADAPTER = {
    "hermes": {
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
        "html_generation": {
            "markdown_report": 115,
            "html_page": 45,
            "data_table": 25,
            "chart": 20,
            "ppt_deck": 10,
            "image_result": 5,
        },
        "u1_image": {
            "markdown_report": 100,
            "html_page": 75,
            "ppt_deck": 45,
            "image_result": 35,
            "data_table": 15,
            "chart": 15,
        },
    },
    "openclaw": {
        "data_analysis": {
            "data_table": 110,
            "chart": 95,
            "markdown_report": 45,
            "html_page": 25,
            "ppt_deck": 5,
            "image_result": 5,
        },
        "deep_research": {
            "markdown_report": 105,
            "html_page": 65,
            "data_table": 35,
            "chart": 25,
            "ppt_deck": 10,
            "image_result": 5,
        },
        "ppt_generation": {
            "markdown_report": 110,
            "html_page": 70,
            "ppt_deck": 45,
            "image_result": 35,
            "data_table": 15,
            "chart": 15,
        },
        "html_generation": {
            "markdown_report": 120,
            "html_page": 35,
            "data_table": 15,
            "chart": 10,
            "ppt_deck": 5,
            "image_result": 5,
        },
        "u1_image": {
            "markdown_report": 90,
            "html_page": 55,
            "image_result": 50,
            "ppt_deck": 30,
            "data_table": 5,
            "chart": 5,
        },
    },
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


def normalized_adapter_key(adapter_key: str | None) -> str:
    return adapter_key if adapter_key in TYPE_SCORES_BY_ADAPTER else DEFAULT_ADAPTER_KEY


def skill_type_score(skill_key: str, artifact_type: str, adapter_key: str | None = None) -> int:
    adapter_scores = TYPE_SCORES_BY_ADAPTER[normalized_adapter_key(adapter_key)]
    return adapter_scores.get(skill_key, {}).get(artifact_type, 0)


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
    for focus_term in re.findall(r"[《「“\"]([^》」”\"]{2,})[》」”\"]", content):
        if focus_term.lower() in normalized_title:
            return 60
    if normalized_title and normalized_title in normalized_content:
        return 60
    for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized_title):
        if token.lower() in normalized_content:
            return 20
    return 0


def instruction_for_skill(skill_key: str, adapter_key: str | None = None) -> str:
    adapter = normalized_adapter_key(adapter_key)
    if adapter == "openclaw":
        return openclaw_instruction_for_skill(skill_key)
    return hermes_instruction_for_skill(skill_key)


def hermes_instruction_for_skill(skill_key: str) -> str:
    if skill_key == "data_analysis":
        return (
            "如果用户要求继续分析已有数据，请优先从下方少量相关表格、图表或报告中选择输入。"
            "不要一次读取所有历史产物。完成时输出生成的数据表、图表或报告文件路径。"
        )
    if skill_key == "deep_research":
        return (
            "如果用户要求继续调研已有主题，请优先参考下方少量相关报告、HTML 或数据表。"
            "不要把历史产物全部展开。完成时输出最终 Markdown/HTML 报告文件路径。"
        )
    if skill_key == "ppt_generation":
        return (
            "如果用户提到已有 Markdown/HTML/图片，请优先从下方会话产物中选择最匹配文件。"
            "生成 PPT 时必须明确输出最终 PPTX 或可转换 HTML 页面路径。"
        )
    if skill_key == "html_generation":
        return (
            "If the user asks to convert or render an existing Markdown report as HTML, "
            "prefer the most relevant markdown_report path below as the source input. "
            "Generate a standalone HTML file and output the final HTML file path."
        )
    if skill_key == "u1_image":
        return (
            "用户提到 U1 生图时，表示调用 u1_image/sn-image-base 生图能力，"
            "不是名为 U1 的参考图片。若用户提到已有 Markdown/HTML/PPT，"
            "优先从下方会话产物中选择最匹配文件；直接生成图片，并在完成时输出图片文件路径。"
        )
    return ""


def openclaw_instruction_for_skill(skill_key: str) -> str:
    if skill_key == "data_analysis":
        return (
            "OpenClaw context: only use the most relevant table/chart/report paths below. "
            "Prefer CSV/XLSX inputs, perform the requested analysis, and explicitly return "
            "artifact_paths with artifact_type=data_table or markdown_report."
        )
    if skill_key == "deep_research":
        return (
            "OpenClaw context: use at most the relevant prior report/data paths below "
            "as background. Do not expand unrelated artifacts. Produce a final research "
            "report and explicitly return artifact_paths, artifact_type=markdown_report "
            "or html_page, source_dir, run_id, and title."
        )
    if skill_key == "ppt_generation":
        return (
            "OpenClaw context: prefer one source Markdown/HTML report below as the deck input. "
            "Generate a PPT deliverable when possible; if HTML slides are produced first, "
            "return both HTML paths and the final PPTX path with artifact_type=ppt_deck/html_page."
        )
    if skill_key == "html_generation":
        return (
            "OpenClaw context: prefer exactly one source markdown_report path below as input. "
            "Run the report-html-v2 workflow, do not redo research unless the source report "
            "is missing, generate a standalone HTML report, and explicitly return "
            "artifact_paths, artifact_type=html_page, source_dir, run_id, and title."
        )
    if skill_key == "u1_image":
        return (
            "OpenClaw context: use the relevant report/slide/image paths below only as reference. "
            "Generate image artifacts and explicitly return artifact_paths with "
            "artifact_type=image_result, source_dir, run_id, and title."
        )
    return ""


def build_context_line(
    index: int,
    artifact: RuntimeArtifactContext,
    adapter_key: str | None,
) -> str:
    if normalized_adapter_key(adapter_key) == "openclaw":
        return (
            f"- artifact_{index}: type={artifact.type}; title={artifact.title}; "
            f"path={artifact.path}"
        )
    return f"{index}. {artifact.type}: {artifact.title} -> {artifact.path}"


async def build_runtime_content(
    db: AsyncSession,
    session_id: str,
    content: str,
    skill_key: str | None,
    adapter_key: str | None = None,
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
        base_score = skill_type_score(skill_key, artifact.type, adapter_key)
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
    adapter = normalized_adapter_key(adapter_key)
    limit = MAX_CONTEXT_ARTIFACTS_BY_ADAPTER[adapter].get(skill_key, 4)
    selected = candidates[:limit]
    context = "\n".join(
        build_context_line(index, artifact, adapter)
        for index, artifact in enumerate(selected, start=1)
    )
    instruction = instruction_for_skill(skill_key, adapter)
    return f"{content}\n\n[WebAgent runtime context: {adapter}]\n{instruction}\n{context}"

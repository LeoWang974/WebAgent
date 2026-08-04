from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = (
    PROJECT_ROOT / "apps" / "web" / "src",
    PROJECT_ROOT / "services" / "api" / "app",
    PROJECT_ROOT / "services" / "agent-runtime" / "agent_runtime",
)
SOURCE_SUFFIXES = {".js", ".mjs", ".py", ".ts", ".tsx"}
MOJIBAKE_MARKERS = (
    "Ã",
    "Â",
    "â€",
    "ðŸ",
    "璇蜂娇鐢",
    "鎶ュ憡",
    "缃戦〉",
    "�",
)


def test_production_source_contains_no_known_mojibake() -> None:
    matches: list[str] = []
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8")
            for marker in MOJIBAKE_MARKERS:
                if marker in content:
                    matches.append(f"{path.relative_to(PROJECT_ROOT)}: {marker}")
    assert not matches, "Known mojibake found:\n" + "\n".join(matches)

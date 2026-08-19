# File purpose: Verifies that first-party source files retain concise responsibility headers.
# Main declarations: test_first_party_sources_have_responsibility_headers verifies source header
# coverage.

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = (
    PROJECT_ROOT / "apps" / "web" / "src",
    PROJECT_ROOT / "services" / "api" / "app",
    PROJECT_ROOT / "services" / "api" / "tests",
    PROJECT_ROOT / "services" / "api" / "scripts",
    PROJECT_ROOT / "services" / "api" / "alembic",
    PROJECT_ROOT / "scripts",
)
EXTRA_SOURCE_FILES = (
    PROJECT_ROOT / "apps" / "web" / "eslint.config.mjs",
    PROJECT_ROOT / "apps" / "web" / "next.config.ts",
    PROJECT_ROOT / "apps" / "web" / "postcss.config.mjs",
    PROJECT_ROOT / "apps" / "web" / "tailwind.config.ts",
)
SOURCE_SUFFIXES = {".css", ".js", ".mjs", ".ps1", ".py", ".sh", ".ts", ".tsx"}
SKIPPED_DIRECTORIES = {".next", ".next-build", ".venv", "__pycache__", "node_modules"}


def test_first_party_sources_have_responsibility_headers() -> None:
    source_files = list(EXTRA_SOURCE_FILES)
    for root in SOURCE_ROOTS:
        source_files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in SOURCE_SUFFIXES
            and not SKIPPED_DIRECTORIES.intersection(path.parts)
        )

    missing = []
    for path in source_files:
        header = "\n".join(path.read_text(encoding="utf-8-sig").splitlines()[:12])
        if "File purpose:" not in header or "Main declarations:" not in header:
            missing.append(str(path.relative_to(PROJECT_ROOT)))

    assert not missing, "Missing source responsibility headers:\n" + "\n".join(missing)

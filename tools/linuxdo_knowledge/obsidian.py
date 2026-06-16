from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FEEDBACK_HEADING = "## 我的反馈"
FEEDBACK_HEADING_PATTERN = re.compile(rf"^{re.escape(FEEDBACK_HEADING)}[ \t]*$", flags=re.MULTILINE)

VAULT_DIRECTORIES = [
    "00_Home",
    "10_Catalog/resources",
    "10_Catalog/services",
    "10_Catalog/collections",
    "10_Catalog/candidates",
    "10_Catalog/comparisons",
    "10_Catalog/workflows",
    "10_Catalog/categories",
    "10_Catalog/archive",
    "20_Knowledge/concepts",
    "20_Knowledge/components",
    "20_Knowledge/practices",
    "20_Knowledge/claims",
    "20_Knowledge/notes",
    "20_Knowledge/drafts",
    "30_Feedback/preferences",
    "30_Feedback/decisions",
    "30_Feedback/rejections",
    "90_Inbox/review-queue",
    "90_Inbox/sessions",
    "_system/sources/linuxdo",
    "_system/sources/github",
    "_system/evidence/linuxdo",
    "_system/evidence/github",
]

PAGE_TYPE_DIRECTORIES = {
    "resource": "10_Catalog/resources",
    "service": "10_Catalog/services",
    "collection": "10_Catalog/collections",
    "candidate": "10_Catalog/candidates",
    "comparison": "10_Catalog/comparisons",
    "workflow": "10_Catalog/workflows",
    "category": "10_Catalog/categories",
    "archive": "10_Catalog/archive",
    "concept": "20_Knowledge/concepts",
    "component": "20_Knowledge/components",
    "practice": "20_Knowledge/practices",
    "claim": "20_Knowledge/claims",
    "draft": "20_Knowledge/drafts",
    "note": "20_Knowledge/notes",
    "preference": "30_Feedback/preferences",
    "decision": "30_Feedback/decisions",
    "rejection": "30_Feedback/rejections",
    "review": "90_Inbox/review-queue",
    "session": "90_Inbox/sessions",
    "linuxdo_source": "_system/sources/linuxdo",
    "github_source": "_system/sources/github",
    "linuxdo_evidence": "_system/evidence/linuxdo",
    "github_evidence": "_system/evidence/github",
}

ROOT_FILES = {
    "CLAUDE.md": """# knowledge rules

- Keep generated knowledge concise and source-grounded.
- Treat Linux.do and GitHub discussion as evidence, not settled truth.
- Preserve `## 我的反馈` exactly when updating human-facing pages.
- Prefer `state/knowledge/` hot indexes before reading old topics again.
""",
    "AGENTS.md": """# knowledge rules

- Keep generated knowledge concise and source-grounded.
- Treat Linux.do and GitHub discussion as evidence, not settled truth.
- Preserve `## 我的反馈` exactly when updating human-facing pages.
- Prefer `state/knowledge/` hot indexes before reading old topics again.
""",
    "00_Home/index.md": "# Linux.do Knowledge Vault\n\n",
    "00_Home/hot.md": "# Hot\n\n",
    "00_Home/log.md": "",
}


def scaffold_vault(config: Any) -> None:
    vault_path = config.obsidian_vault_path
    for relative_path in VAULT_DIRECTORIES:
        (vault_path / relative_path).mkdir(parents=True, exist_ok=True)

    vault_path.mkdir(parents=True, exist_ok=True)
    for relative_path, content in ROOT_FILES.items():
        path = vault_path / relative_path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def write_page(
    path: Path,
    frontmatter: dict[str, Any],
    title: str,
    sections: list[tuple[str, str]],
    *,
    include_feedback: bool = True,
) -> Path:
    feedback = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        feedback = extract_feedback_body(existing)

    parts = [_format_frontmatter(frontmatter), f"# {title}\n\n"]
    for heading, body in sections:
        parts.append(f"## {heading}\n\n{body.rstrip()}\n\n")
    if include_feedback:
        parts.append(f"{FEEDBACK_HEADING}\n{feedback}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")
    return path


def extract_feedback_body(text: str) -> str:
    match = FEEDBACK_HEADING_PATTERN.search(text)
    if not match:
        return ""
    start = match.end()
    if start < len(text) and text[start] == "\n":
        start += 1
    return text[start:]


def append_log(config: Any, line: str) -> Path:
    path = config.obsidian_vault_path / "00_Home" / "log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{line.rstrip()}\n")
    return path


def page_path_for(config: Any, page_type: str, name: str) -> Path:
    if page_type not in PAGE_TYPE_DIRECTORIES:
        raise ValueError(f"unknown page type: {page_type}")
    return config.obsidian_vault_path / PAGE_TYPE_DIRECTORIES[page_type] / f"{safe_filename(name)}.md"


def page_path_for_id(config: Any, page_type: str, item_id: str, fallback_name: str) -> Path:
    if page_type not in PAGE_TYPE_DIRECTORIES:
        raise ValueError(f"unknown page type: {page_type}")
    directory = config.obsidian_vault_path / PAGE_TYPE_DIRECTORIES[page_type]
    existing = find_page_by_frontmatter_id(config.obsidian_vault_path, item_id)
    return existing if existing else directory / f"{safe_filename(fallback_name)}.md"


def find_page_by_frontmatter_id(directory: Path, item_id: str) -> Path | None:
    if not directory.exists():
        return None
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if _frontmatter_id(text) == item_id:
            return path
    return None


def _frontmatter_id(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "id":
            return value.strip().strip("\"'")
    return None


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", name)
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-. ")
    return cleaned or "untitled"


def _format_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_format_scalar(item)}")
        else:
            lines.append(f"{key}: {_format_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FEEDBACK_HEADING = "## 我的反馈"

VAULT_DIRECTORIES = [
    "wiki/concepts",
    "wiki/practices",
    "wiki/drafts",
    "wiki/notes",
    "catalog/resources",
    "catalog/candidates",
    "catalog/comparisons",
    "catalog/workflows",
    "catalog/categories",
    "catalog/archive",
    "inbox/sessions",
    "raw",
]

PAGE_TYPE_DIRECTORIES = {
    "resource": "catalog/resources",
    "candidate": "catalog/candidates",
    "comparison": "catalog/comparisons",
    "workflow": "catalog/workflows",
    "category": "catalog/categories",
    "archive": "catalog/archive",
    "concept": "wiki/concepts",
    "practice": "wiki/practices",
    "draft": "wiki/drafts",
    "note": "wiki/notes",
    "session": "inbox/sessions",
}

ROOT_FILES = {
    "CLAUDE.md": """# knowledge rules

- Keep generated knowledge concise and source-grounded.
- Preserve `## 我的反馈` exactly when updating pages.
""",
    "AGENTS.md": """# knowledge rules

- Keep generated knowledge concise and source-grounded.
- Preserve `## 我的反馈` exactly when updating pages.
""",
    "index.md": "# Linux.do Knowledge Vault\n\n",
    "log.md": "",
}


def scaffold_vault(config: Any) -> None:
    vault_path = config.obsidian_vault_path
    for relative_path in VAULT_DIRECTORIES:
        (vault_path / relative_path).mkdir(parents=True, exist_ok=True)

    vault_path.mkdir(parents=True, exist_ok=True)
    for filename, content in ROOT_FILES.items():
        path = vault_path / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def write_page(path: Path, frontmatter: dict[str, Any], title: str, sections: list[tuple[str, str]]) -> None:
    feedback = "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if FEEDBACK_HEADING in existing:
            feedback = existing.split(FEEDBACK_HEADING, 1)[1]

    parts = [_format_frontmatter(frontmatter), f"# {title}\n\n"]
    for heading, body in sections:
        parts.append(f"## {heading}\n\n{body.rstrip()}\n\n")
    parts.append(f"{FEEDBACK_HEADING}{feedback}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")


def append_log(config: Any, line: str) -> Path:
    path = config.obsidian_vault_path / "log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{line.rstrip()}\n")
    return path


def page_path_for(config: Any, page_type: str, name: str) -> Path:
    if page_type not in PAGE_TYPE_DIRECTORIES:
        raise ValueError(f"unknown page type: {page_type}")
    return config.obsidian_vault_path / PAGE_TYPE_DIRECTORIES[page_type] / f"{safe_filename(name)}.md"


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

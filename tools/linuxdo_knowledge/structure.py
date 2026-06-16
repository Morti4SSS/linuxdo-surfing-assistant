from __future__ import annotations

from pathlib import Path
from typing import Any

from .aliases import canonicalize_name
from .config import KnowledgeConfig
from .obsidian import append_log, safe_filename
from .quality import classify_knowledge_object
from .state import now_iso


PAGE_TYPE_DIRECTORIES = {
    "resource": "10_Catalog/resources",
    "service": "10_Catalog/services",
    "collection": "10_Catalog/collections",
    "workflow": "10_Catalog/workflows",
    "concept": "20_Knowledge/concepts",
    "component": "20_Knowledge/components",
}

TYPE_TAGS = {
    "resource": ["knowledge/resource", "source/linuxdo"],
    "service": ["knowledge/api-relay", "source/linuxdo"],
    "collection": ["knowledge/collection", "source/linuxdo"],
    "workflow": ["knowledge/workflow", "source/linuxdo"],
    "concept": ["knowledge/concept", "source/linuxdo"],
    "component": ["knowledge/component", "source/linuxdo"],
}

SCAN_DIRECTORIES = tuple(PAGE_TYPE_DIRECTORIES.values()) + ("10_Catalog/candidates",)


def repair_vault_structure(config: KnowledgeConfig, repaired_at: str | None = None) -> dict[str, int]:
    repaired = repaired_at or now_iso()
    moved = 0
    updated = 0
    archived = 0
    skipped = 0

    for path in _scan_pages(config.obsidian_vault_path):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        if not frontmatter:
            skipped += 1
            continue
        status = str(frontmatter.get("status", ""))
        if status == "moved" and "10_Catalog/candidates" in str(path):
            _archive_moved_candidate(config, path)
            archived += 1
            continue
        if status in {"moved", "duplicate"}:
            skipped += 1
            continue
        title = canonicalize_name(_page_title(body, path.stem))
        target_type = _target_type_for_page(frontmatter, title)
        if target_type == "candidate":
            skipped += 1
            continue

        target_dir = config.obsidian_vault_path / PAGE_TYPE_DIRECTORIES[target_type]
        target_path = target_dir / f"{safe_filename(title)}.md"
        frontmatter["type"] = target_type
        frontmatter["tags"] = TYPE_TAGS[target_type]
        new_text = _format_frontmatter(frontmatter) + body.lstrip()

        if path == target_path:
            if text != new_text:
                path.write_text(new_text, encoding="utf-8")
                updated += 1
            continue

        if target_path.exists():
            skipped += 1
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_text, encoding="utf-8")
        path.unlink()
        moved += 1

    append_log(config, f"- {repaired}: 结构归位移动 {moved} 页，更新 frontmatter {updated} 页，归档跳转 {archived} 页，跳过 {skipped} 页。")
    return {"moved_pages": moved, "updated_pages": updated, "archived_redirects": archived, "skipped_pages": skipped}


def _scan_pages(vault_path: Path) -> list[Path]:
    pages: list[Path] = []
    for relative_dir in SCAN_DIRECTORIES:
        directory = vault_path / relative_dir
        if directory.exists():
            pages.extend(path for path in directory.glob("*.md") if path.is_file())
    return sorted(pages)


def _archive_moved_candidate(config: KnowledgeConfig, path: Path) -> None:
    archive_dir = config.obsidian_vault_path / "10_Catalog" / "archive" / "moved-candidates"
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"moved-{path.name}"
    counter = 2
    while target.exists():
        target = archive_dir / f"moved-{path.stem}-{counter}.md"
        counter += 1
    path.rename(target)


def _target_type_for_page(frontmatter: dict[str, Any], title: str) -> str:
    current_type = str(frontmatter.get("type", ""))
    status = str(frontmatter.get("status", ""))
    evidence_status = str(frontmatter.get("evidence_status", ""))
    if current_type == "candidate" and (status in {"needs_source_review"} or evidence_status in {"insufficient_source_extract"}):
        return "candidate"
    classified = classify_knowledge_object(title)
    if classified in PAGE_TYPE_DIRECTORIES:
        return classified
    return current_type if current_type in PAGE_TYPE_DIRECTORIES else "candidate"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    frontmatter = _parse_frontmatter(text[4:end])
    body = text[end + len("\n---") :]
    return frontmatter, body


def _parse_frontmatter(block: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key = ""
    for line in block.splitlines():
        if line.startswith("  - ") and current_key:
            result.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        result[current_key] = [] if value == "" else value
    return result


def _format_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _page_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback

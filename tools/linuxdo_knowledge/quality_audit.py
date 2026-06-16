from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .quality import lint_human_markdown, required_sections_for_page_type


BAD_SNIPPETS = {
    "legacy_heading": ["## 来源证据"],
}

HUMAN_PREFIXES = (
    "00_Home/",
    "10_Catalog/resources/",
    "10_Catalog/services/",
    "10_Catalog/workflows/",
    "10_Catalog/comparisons/",
    "10_Catalog/collections/",
    "10_Catalog/categories/",
    "20_Knowledge/concepts/",
    "20_Knowledge/components/",
    "20_Knowledge/claims/",
    "30_Feedback/",
    "90_Inbox/review-queue/",
)

TRANSITIONAL_PREFIXES = (
    "10_Catalog/candidates/",
    "10_Catalog/archive/",
    "20_Knowledge/drafts/",
)

LEDGER_PREFIXES = (
    "_system/",
    "90_Inbox/sessions/",
)


def audit_markdown_page(relative_path: str, text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    page_type = _frontmatter_value(text, "type")

    for issue in lint_human_markdown(text, page_name=relative_path):
        issues.append({"path": relative_path, "code": issue.code, "message": issue.message})

    for code, snippets in BAD_SNIPPETS.items():
        for snippet in snippets:
            if snippet in text:
                issues.append({"path": relative_path, "code": code, "message": f"包含残留文本：{snippet}"})

    headings = set(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    for heading in required_sections_for_page_type(page_type):
        if heading not in headings:
            issues.append({"path": relative_path, "code": "missing_section", "message": f"缺少章节：{heading}"})

    return issues


def audit_ledger_page(relative_path: str, text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if relative_path.startswith("_system/sources/") and "source_id" not in text and "url:" not in text:
        issues.append({"path": relative_path, "code": "missing_ledger_identity", "message": "底账页缺少 source_id 或 url"})
    if relative_path.startswith("_system/evidence/") and "source:" not in text and "topic_id:" not in text:
        issues.append({"path": relative_path, "code": "missing_ledger_source", "message": "证据页缺少 source 或 topic_id"})
    return issues


def layer_for_path(relative_path: str) -> str:
    if relative_path.startswith(HUMAN_PREFIXES):
        return "human"
    if relative_path.startswith(TRANSITIONAL_PREFIXES):
        return "transitional"
    if relative_path.startswith(LEDGER_PREFIXES):
        return "ledger"
    return "ignored"


def audit_vault(vault_path: Path, *, layer: str = "human", paths: list[str] | None = None) -> dict[str, Any]:
    if layer not in {"human", "transitional", "ledger", "all"}:
        raise ValueError(f"unsupported audit layer: {layer}")
    issues: list[dict[str, str]] = []
    pages_scanned = 0
    report_layer = "batch" if paths is not None else layer
    layer_counts = _layer_counts(vault_path)

    for relative, path in _audit_paths(vault_path, layer=layer, paths=paths):
        page_layer = layer_for_path(relative)
        pages_scanned += 1
        text = path.read_text(encoding="utf-8")
        if page_layer == "ledger":
            issues.extend(audit_ledger_page(relative, text))
        else:
            issues.extend(audit_markdown_page(relative, text))
    return {"layer": report_layer, "pages_scanned": pages_scanned, "layer_counts": layer_counts, "issues": issues}


def write_audit_report(
    vault_path: Path,
    output_path: Path,
    *,
    layer: str = "human",
    paths: list[str] | None = None,
) -> Path:
    report = audit_vault(vault_path, layer=layer, paths=paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    if end == -1:
        return ""
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        found_key, value = line.split(":", 1)
        if found_key.strip() == key:
            return value.strip().strip("'\"")
    return ""


def _audit_paths(vault_path: Path, *, layer: str, paths: list[str] | None) -> list[tuple[str, Path]]:
    if paths is not None:
        result: list[tuple[str, Path]] = []
        for relative in paths:
            clean = relative.strip()
            if not clean or clean.startswith("#"):
                continue
            path = vault_path / clean
            if path.is_file() and path.suffix == ".md":
                result.append((clean, path))
        return sorted(result)

    result = []
    for path in sorted(vault_path.rglob("*.md")):
        relative = path.relative_to(vault_path).as_posix()
        if relative.startswith(".obsidian/"):
            continue
        page_layer = layer_for_path(relative)
        if layer == "all":
            if page_layer in {"human", "transitional", "ledger"}:
                result.append((relative, path))
        elif page_layer == layer:
            result.append((relative, path))
    return result


def _layer_counts(vault_path: Path) -> dict[str, int]:
    counts = {"human": 0, "transitional": 0, "ledger": 0, "ignored": 0}
    for path in sorted(vault_path.rglob("*.md")):
        relative = path.relative_to(vault_path).as_posix()
        if relative.startswith(".obsidian/"):
            continue
        counts[layer_for_path(relative)] += 1
    return counts

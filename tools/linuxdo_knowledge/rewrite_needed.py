from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .legacy import _load_legacy_readings
from .obsidian import FEEDBACK_HEADING, append_log, extract_feedback_body, page_path_for, page_path_for_id, safe_filename, write_page
from .quality import classify_knowledge_object, lint_human_markdown, normalize_resource_name
from .state import now_iso


HUMAN_SECTIONS = (
    "一句话判断",
    "它是什么",
    "适合什么",
    "不适合什么",
    "当前结论",
    "关键证据",
    "反方与风险",
    "相关竞品",
    "待验证",
    "来源",
)

GENERIC_PAGES = {
    "AGENTS.md",
    "CLAUDE.md",
    "SKILL.md",
    "Spec",
    "Subagent",
    "Subagents",
    "Memory",
    "MCP",
    "API",
}

ALIAS_REDIRECTS = {
    "Vibe-Coding": "Vibecoding",
    "ccswitch": "CC-Switch",
}


def rewrite_needed_candidate_pages(
    config: KnowledgeConfig,
    input_path: Path,
    *,
    rewritten_at: str | None = None,
    max_sources_per_page: int = 6,
    include_source_extract: bool = False,
) -> dict[str, int]:
    if max_sources_per_page <= 0:
        raise ValueError("max_sources_per_page must be positive")

    rewritten = rewritten_at or now_iso()
    readings = _load_legacy_readings(input_path)
    candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
    if not candidate_dir.exists():
        return {"candidate_pages": 0, "rewritten_pages": 0, "moved_pages": 0, "duplicate_pages": 0, "insufficient_pages": 0}

    candidate_paths = sorted(candidate_dir.glob("*.md"))
    rewritten_pages = 0
    duplicate_pages = 0
    insufficient_pages = 0
    moved_pages = 0
    for path in candidate_paths:
        text = path.read_text(encoding="utf-8")
        if not _needs_rewrite(text, include_source_extract=include_source_extract):
            continue
        title = _page_title(path, text)
        if title in ALIAS_REDIRECTS:
            _write_duplicate_page(config, path, title, ALIAS_REDIRECTS[title], rewritten)
            duplicate_pages += 1
            continue

        matches = _matching_readings(readings, title)
        if len(matches) < 1:
            _write_insufficient_page(config, path, title, rewritten)
            insufficient_pages += 1
            continue

        moved = _write_rewritten_page(config, path, title, matches, rewritten, max_sources_per_page)
        rewritten_pages += 1
        if moved:
            moved_pages += 1

    append_log(
        config,
        f"- {rewritten}: 重写待复核候选页 {rewritten_pages} 张，迁移 {moved_pages} 张，别名页 {duplicate_pages} 张，证据不足页 {insufficient_pages} 张。",
    )
    return {
        "candidate_pages": len(candidate_paths),
        "rewritten_pages": rewritten_pages,
        "moved_pages": moved_pages,
        "duplicate_pages": duplicate_pages,
        "insufficient_pages": insufficient_pages,
    }


def _needs_rewrite(text: str, *, include_source_extract: bool = False) -> bool:
    if "status: needs_rewrite" in text or "evidence_status: legacy_summary" in text:
        return True
    return include_source_extract and "evidence_status: source_extract" in text


def _page_title(path: Path, text: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ")


def _write_duplicate_page(
    config: KnowledgeConfig,
    path: Path,
    title: str,
    target: str,
    rewritten: str,
) -> None:
    target_slug, target_display = normalize_resource_name(target)
    frontmatter = {
        "id": f"resource:{normalize_resource_name(title)[0]}",
        "type": "candidate",
        "status": "duplicate",
        "tags": ["knowledge/linuxdo"],
        "last_verified": rewritten[:10],
        "canonical": target_slug,
    }
    write_page(
        path,
        frontmatter,
        title,
        [
            ("去看哪里", f"本页只是别名入口。后续统一维护在 [[{target_slug}|{target_display}]]。"),
            ("为什么合并", "这两个名称指向同一个对象，分开维护会让证据和反馈断裂。"),
        ],
    )


def _write_insufficient_page(
    config: KnowledgeConfig,
    path: Path,
    title: str,
    rewritten: str,
) -> bool:
    slug, display = normalize_resource_name(title)
    frontmatter = {
        "id": f"resource:{slug}",
        "type": "candidate",
        "status": "needs_source_review",
        "tags": ["knowledge/linuxdo"],
        "last_verified": rewritten[:10],
        "evidence_status": "insufficient_source_extract",
        "watchlist": False,
    }
    write_page(
        path,
        frontmatter,
        display,
        [
            ("一句话判断", "当前证据不足，不应作为采用、排除或对比依据。"),
            ("它是什么", "对象边界还不清楚，可能只是泛词、文件名、概念片段或某个帖子的临时提法。"),
            ("适合什么", "只适合作为后续搜索线索。"),
            ("不适合什么", "不适合进入正式选型、对比页或工作流结论。"),
            ("当前结论", "先保留低优先级入口；再次遇到明确来源、GitHub 项目或高信号讨论时再重写。"),
            ("关键证据", "当前没有能支撑判断的可复用来源。"),
            ("反方与风险", "把证据不足的对象写成资源卡，会让候选区继续膨胀。"),
            ("相关竞品", "暂不建立竞品关系。"),
            ("待验证", "需要至少一个明确来源说明它是什么、解决什么问题、谁在使用、有哪些限制。"),
            ("来源", "暂无可用来源。"),
        ],
    )


def _write_rewritten_page(
    config: KnowledgeConfig,
    path: Path,
    title: str,
    matches: list[dict[str, Any]],
    rewritten: str,
    max_sources_per_page: int,
) -> None:
    slug, display = normalize_resource_name(title)
    object_type = _object_type(title)
    ranked = sorted(matches, key=_reading_rank, reverse=True)
    selected = ranked[:max_sources_per_page]
    source_count = len(matches)
    source_lines = [_source_line(reading) for reading in selected]
    evidence_lines = _evidence_lines(selected)
    risk_lines = _risk_lines(ranked)
    comparison_lines = _comparison_lines(ranked, display)
    tool_lines = _tool_lines(ranked, display)
    status = "needs_source_review" if len(evidence_lines) < 2 else "watching"
    frontmatter = {
        "id": f"resource:{slug}",
        "type": object_type,
        "status": status,
        "tags": _tags_for(object_type),
        "last_verified": rewritten[:10],
        "evidence_status": "source_extract",
        "staleness_risk": _staleness_risk(object_type),
        "watchlist": status == "watching",
        "source_count": source_count,
    }
    sections = [
        ("一句话判断", _one_line(display, object_type, selected, source_count)),
        ("它是什么", _what_it_is(display, object_type, selected, tool_lines)),
        ("适合什么", _fit_for(object_type, selected)),
        ("不适合什么", _not_for(object_type, selected)),
        ("当前结论", _current_judgment(display, object_type, status)),
        ("关键证据", "\n".join(evidence_lines) if evidence_lines else "当前没有能支撑判断的可复用来源。"),
        ("反方与风险", "\n".join(risk_lines) if risk_lines else _default_risk(object_type)),
        ("相关竞品", "\n".join(comparison_lines) if comparison_lines else "暂未整理到功能相近竞品。"),
        ("待验证", _next_verification(object_type)),
        ("来源", "\n".join(source_lines)),
    ]
    text_preview = "\n".join(body for _heading, body in sections)
    if lint_human_markdown(text_preview, page_name=display):
        sections = [(heading, _sanitize(body)) for heading, body in sections]
    target_page_type = _page_type_for_object_type(object_type)
    target_path = _target_path_for_rewrite(config, path, target_page_type, f"resource:{slug}", display)
    source_feedback = extract_feedback_body(path.read_text(encoding="utf-8")) if path.exists() else ""
    write_page(target_path, frontmatter, display, sections)
    if source_feedback and target_path != path:
        _append_feedback_if_missing(target_path, source_feedback)
    if target_path != path:
        _write_moved_page(path, display, target_path, object_type, rewritten)
        return True
    return False


def _object_type(title: str) -> str:
    normalized = title.strip()
    if normalized in GENERIC_PAGES:
        return "collection"
    classified = classify_knowledge_object(normalized)
    return classified


def _page_type_for_object_type(object_type: str) -> str:
    if object_type in {"resource", "service", "collection", "workflow", "concept", "component"}:
        return object_type
    return "candidate"


def _target_path_for_rewrite(config: KnowledgeConfig, current_path: Path, page_type: str, item_id: str, display: str) -> Path:
    if page_type == "candidate":
        return current_path
    existing = page_path_for_id(config, page_type, item_id, display)
    if existing != current_path:
        return existing
    return page_path_for(config, page_type, display)


def _write_moved_page(path: Path, display: str, target_path: Path, object_type: str, rewritten: str) -> None:
    target_stem = target_path.stem
    body = f"本页已迁移到 [[{target_stem}|{display}]]。旧 candidate 位置只保留跳转，避免继续在这里堆证据。"
    write_page(
        path,
        {
            "id": f"redirect:{safe_filename(display).lower()}",
            "type": "candidate",
            "status": "moved",
            "tags": ["knowledge/candidate"],
            "last_verified": rewritten[:10],
            "target": target_stem,
            "target_type": object_type,
        },
        display,
        [
            ("去看哪里", body),
            ("为什么迁移", "目录现在按对象类型组织：具体资源、服务、集合、工作流、概念和组件不再长期混在 candidates。"),
        ],
    )


def _append_feedback_if_missing(path: Path, feedback: str) -> None:
    text = path.read_text(encoding="utf-8")
    if feedback.strip() in text:
        return
    marker = f"{FEEDBACK_HEADING}\n"
    if marker not in text:
        path.write_text(text.rstrip() + f"\n\n{marker}{feedback}", encoding="utf-8")
        return
    path.write_text(text.rstrip() + "\n" + feedback.rstrip() + "\n", encoding="utf-8")


def _tags_for(object_type: str) -> list[str]:
    if object_type == "workflow":
        return ["knowledge/workflow", "source/linuxdo"]
    if object_type == "service":
        return ["knowledge/api-relay", "source/linuxdo"]
    if object_type == "collection":
        return ["knowledge/collection", "source/linuxdo"]
    if object_type == "concept":
        return ["knowledge/concept", "source/linuxdo"]
    if object_type == "component":
        return ["knowledge/component", "source/linuxdo"]
    return ["knowledge/linuxdo", "source/linuxdo"]


def _staleness_risk(object_type: str) -> str:
    if object_type == "service":
        return "high"
    if object_type == "collection":
        return "medium"
    return "medium"


def _matching_readings(readings: list[dict[str, Any]], title: str) -> list[dict[str, Any]]:
    aliases = _aliases_for(title)
    matches = []
    for reading in readings:
        if _reading_mentions(reading, aliases):
            matches.append(reading)
    return matches


def _aliases_for(title: str) -> set[str]:
    slug, display = normalize_resource_name(title)
    raw = title.strip()
    aliases = {
        raw.lower(),
        display.lower(),
        slug.lower(),
        slug.replace("-", " ").lower(),
        raw.replace("-", " ").lower(),
        raw.replace(" ", "-").lower(),
    }
    if "/" in raw:
        aliases.add(raw.replace("/", "-").lower())
    if "-" in raw:
        parts = raw.split("-", 1)
        if len(parts) == 2:
            aliases.add("/".join(parts).lower())
    return {item for item in aliases if item}


def _reading_mentions(reading: dict[str, Any], aliases: set[str]) -> bool:
    tool_values = [str(item).lower() for item in reading.get("tools", []) or []]
    repo_values = [str(item).lower() for item in reading.get("github_repos", []) or []]
    exact_values = set(tool_values + repo_values)
    for alias in aliases:
        if alias in exact_values:
            return True
        if any(alias == value.replace("/", "-") or alias == value.replace("-", " ") for value in exact_values):
            return True
    text = " ".join(
        [
            str(reading.get("title", "")),
            str(reading.get("summary", "")),
            str(reading.get("first_post", ""))[:1200],
        ]
    ).lower()
    return any(_contains_token(text, alias) for alias in aliases if len(alias) >= 3)


def _contains_token(text: str, alias: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", alias):
        return alias in text
    pattern = rf"(?<![a-z0-9_-]){re.escape(alias)}(?![a-z0-9_-])"
    return re.search(pattern, text) is not None


def _reading_rank(reading: dict[str, Any]) -> int:
    score = 0
    value = str(reading.get("value_tag", "")).lower()
    if value in {"high", "马上试"}:
        score += 30
    elif value in {"medium", "收藏观察", "谨慎"}:
        score += 12
    score += min(len(reading.get("high_value_replies", []) or []), 6) * 6
    score += min(len(reading.get("comparison_notes", []) or []), 4) * 5
    score += min(len(reading.get("risk_notes", []) or []), 4) * 4
    score += min(int(reading.get("visible_post_count") or 0), 100) // 10
    return score


def _source_line(reading: dict[str, Any]) -> str:
    title = _sanitize(str(reading.get("title") or "未命名来源"), limit=90)
    url = str(reading.get("url") or "").strip()
    if url:
        return f"- [{title}]({url})"
    return f"- {title}"


def _evidence_lines(readings: list[dict[str, Any]]) -> list[str]:
    lines = []
    seen = set()
    for reading in readings:
        summary = _sanitize(str(reading.get("summary") or ""), limit=170)
        if not summary:
            summary = _from_key_reply(reading)
        if not summary:
            continue
        key = summary.lower()
        if key in seen:
            continue
        seen.add(key)
        title = _sanitize(str(reading.get("title") or "来源"), limit=60)
        url = str(reading.get("url") or "").strip()
        prefix = f"[{title}]({url})" if url else title
        lines.append(f"- {prefix}：{summary}")
        if len(lines) >= 5:
            break
    return lines


def _from_key_reply(reading: dict[str, Any]) -> str:
    replies = reading.get("high_value_replies") or []
    if not isinstance(replies, list) or not replies:
        return ""
    first = replies[0]
    if not isinstance(first, dict):
        return ""
    return _sanitize(str(first.get("text") or ""), limit=160)


def _risk_lines(readings: list[dict[str, Any]]) -> list[str]:
    return [f"- {_sanitize(item, limit=150)}" for item in _unique_flatten(readings, ("negative_feedback", "risk_notes"))[:5]]


def _comparison_lines(readings: list[dict[str, Any]], display: str) -> list[str]:
    lines = [f"- {_sanitize(item, limit=150)}" for item in _unique_flatten(readings, ("comparison_notes",))[:4]]
    alternatives = _common_tools(readings, display)
    if alternatives:
        lines.append("- 常被一起讨论：" + "、".join(f"[[{safe_filename(item)}|{item}]]" for item in alternatives[:6]) + "。")
    return lines


def _tool_lines(readings: list[dict[str, Any]], display: str) -> list[str]:
    return _common_tools(readings, display)[:8]


def _common_tools(readings: list[dict[str, Any]], display: str) -> list[str]:
    counter: Counter[str] = Counter()
    display_key = display.lower()
    for reading in readings[:12]:
        for item in reading.get("tools", []) or []:
            value = _sanitize(str(item), limit=60)
            if not value or value.lower() == display_key:
                continue
            counter[value] += 1
    return [item for item, _count in counter.most_common(8)]


def _unique_flatten(readings: list[dict[str, Any]], fields: tuple[str, ...]) -> list[str]:
    values = []
    seen = set()
    for reading in readings:
        for field in fields:
            raw = reading.get(field) or []
            if isinstance(raw, str):
                raw = [raw]
            for item in raw:
                text = _sanitize(str(item), limit=180)
                key = text.lower()
                if text and key not in seen:
                    seen.add(key)
                    values.append(text)
    return values


def _one_line(display: str, object_type: str, readings: list[dict[str, Any]], source_count: int) -> str:
    if object_type == "collection":
        return f"{display} 是一个集合入口，适合用来聚合线索和拆分子对象，不适合作为单一推荐结论。当前关联 {source_count} 个来源。"
    if object_type == "service":
        return f"{display} 是高时效 service / gateway 线索；采用前必须复核最新来源、权限、隐私、模型保真和稳定性。"
    if object_type == "workflow":
        return f"{display} 是工作流候选，价值主要看任务重量、上下文恢复、验证纪律和与现有工具是否重复。当前关联 {source_count} 个来源。"
    if object_type == "concept":
        return f"{display} 是概念页，用来解释边界、常见误区和它如何影响工作流判断；不要把它写成具体工具推荐。"
    if object_type == "component":
        return f"{display} 是工作流组件，价值取决于它在任务链路里的位置、触发条件、停止条件和替代方案。"
    return f"{display} 是待观察资源线索；当前证据只够说明它被讨论过，采用前需要复核来源、维护状态、失败反馈和替代方案。"


def _what_it_is(display: str, object_type: str, readings: list[dict[str, Any]], tools: list[str]) -> str:
    lead = {
        "collection": "它不是单一工具，而是一组来源、工具、概念或配置方式的入口。",
        "service": "它更接近服务、网关、路由或 API 接入层，需要单独看稳定性和隐私风险。",
        "workflow": "它更接近任务组织方式或流程包，重点不在安装本身，而在何时触发、如何恢复上下文、如何验收。",
        "concept": "它不是可安装对象，而是理解 AI coding、知识库或 agent 工作流时需要反复使用的概念边界。",
        "component": "它不是完整工作流，而是某个阶段可插拔的能力，例如澄清、计划、验证、检索或生成。",
    }.get(object_type, "它是一个从 Linux.do 讨论中抽出的候选对象，需要结合项目页和社区反馈看。")
    if tools:
        return lead + "\n\n相关上下文常出现：" + "、".join(tools[:8]) + "。"
    return lead


def _fit_for(object_type: str, readings: list[dict[str, Any]]) -> str:
    if object_type == "collection":
        return "适合当导航页：先从这里进入具体工具、服务、教程或争议 claim，再决定是否深读。"
    if object_type == "service":
        return "适合短期试用、低敏任务、模型/渠道对比和本地网关实验。"
    if object_type == "workflow":
        return "适合需求不清、任务较长、需要计划/记录/复盘/验收的工作。"
    if object_type == "concept":
        return "适合帮助阅读其他页面：判断对象层级、风险、适用范围和是否需要进一步拆分。"
    if object_type == "component":
        return "适合在明确阶段按需触发，而不是每个任务默认全开。"
    return "适合作为候选线索：当它反复出现在高信号帖子、对比讨论或 GitHub 验证中时再考虑试用。"


def _not_for(object_type: str, readings: list[dict[str, Any]]) -> str:
    if object_type == "collection":
        return "不适合直接写成“推荐这个集合”；集合里的具体对象必须拆开判断。"
    if object_type == "service":
        return "不适合高敏代码、商业密钥、长期稳定生产任务，或无法接受服务波动的场景。"
    if object_type == "workflow":
        return "不适合一两行小改、明确小 bug、只需要快速试错的任务；流程过重会浪费 token。"
    if object_type == "concept":
        return "不适合直接当成采用建议；概念页只提供判断框架，具体选择要回到资源卡或对比页。"
    if object_type == "component":
        return "不适合替代完整工作流或验证闭环；组件必须有清楚输入、输出和停止条件。"
    return "不适合在缺少维护状态、失败反馈和替代方案时直接采用。"


def _current_judgment(display: str, object_type: str, status: str) -> str:
    if status == "needs_source_review":
        return "当前只够保留线索，不够形成稳定判断；准备采用前必须补充来源和项目页验证。"
    if object_type == "collection":
        return "保留为集合入口；新证据应优先写到具体资源卡或对比页，而不是继续堆到本页。"
    if object_type == "concept":
        return "保留为解释和路由依据；新证据只在改变概念边界、常见误区或应用规则时更新。"
    if object_type == "component":
        return "保留为按需组件；新证据优先补触发条件、停止条件、风险和功能相近对比。"
    return "保留为观察对象；只有新证据改变采用判断、补足反方、出现重大版本变化或替代工具时再更新。"


def _default_risk(object_type: str) -> str:
    if object_type == "service":
        return "- 服务、价格、额度、模型质量和隐私策略变化快。\n- 论坛反馈只能说明当时可用，不代表长期稳定。"
    if object_type == "workflow":
        return "- 工作流可能带来重复计划、重复澄清和上下文占用。\n- 如果没有测试和人工验收，流程本身不能保证正确。"
    return "- 证据可能来自个人体验，迁移到你的环境前需要复核。"


def _next_verification(object_type: str) -> str:
    if object_type == "service":
        return "采用前复核最新回复、服务状态、隐私/日志说明、模型能力边界和退款/风控风险。"
    if object_type == "workflow":
        return "准备试用前看 GitHub README、最近 release/issue、安装方式、与现有 AGENTS.md/CLAUDE.md/skills 是否冲突。"
    if object_type == "collection":
        return "继续拆分成具体工具、服务、claim 或 comparison；不要把集合本身当成结论。"
    return "再次遇到相关讨论时，只补会改变判断的新证据；相同泛泛推荐不重复写入。"


def _sanitize(value: str, *, limit: int | None = None) -> str:
    if "\n" in str(value) and limit is None:
        return "\n".join(_sanitize(line) for line in str(value).splitlines())

    text = " ".join(str(value).strip().split())
    replacements = {
        "高相关。": "",
        "高相关": "",
        "中等相关。": "",
        "中等相关": "",
        "风佬巨作": "社区教程",
        "zcf": "ZCF",
        "v5.0": "某版本",
        "……": " ",
        "…": " ",
        "...": " ",
        "证据权重": "讨论信号",
        "累计权重": "讨论信号",
        "候选资源，当前记录显示它被多次提及": "待观察资源线索，当前证据只够说明它被讨论过",
        "是否值得采用要看来源证据、维护状态和反方反馈": "采用前需要复核来源、维护状态和反方反馈",
        "暂无足够可复用证据": "当前没有能支撑判断的可复用来源",
        "来源证据": "来源",
        "legacy_summary": "needs_source_review",
        "旧帖": "已读来源",
        "旧记录": "累计资料",
        "旧冲浪": "累计冲浪",
        "本批": "这组资料",
        "Batch": "阅读记录",
        "batch": "session",
        "（已截断）": "",
        "(已截断)": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s*(?:\.\.\.|…)+\s*$", "", text)
    text = text.strip(" ，。；;")
    if limit and len(text) > limit:
        clipped = text[:limit].rstrip()
        sentence_end = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind(";"))
        if sentence_end >= max(30, limit // 2):
            clipped = clipped[: sentence_end + 1]
        text = clipped.rstrip(" ，。；;") + "。"
    return text

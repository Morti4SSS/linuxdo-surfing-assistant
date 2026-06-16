from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .legacy import _load_legacy_readings
from .obsidian import append_log, page_path_for, safe_filename, scaffold_vault, write_page
from .quality import normalize_resource_name
from .state import now_iso


CATEGORY_DEFS = [
    {
        "key": "ai_coding_workflow",
        "name": "AI Coding Workflow 与 Skills",
        "comparison": "AI Coding Workflow 选型",
        "tags": ["knowledge/workflow", "source/linuxdo"],
        "description": "Spec、planning、skills、工作流纪律、vibecoding 方法和任务重量路由。",
        "keywords": [
            "superpowers",
            "trellis",
            "openspec",
            "skill",
            "skills",
            "workflow",
            "vibe",
            "vibecoding",
            "spec",
            "plan",
            "tdd",
            "工作流",
            "需求",
        ],
        "decision": "先按任务重量选择：小任务用轻流程，跨模块或高风险任务再上完整 spec / plan / verification。",
    },
    {
        "key": "agent_cli_ide",
        "name": "Agent CLI 与 IDE",
        "comparison": "Agent CLI 与 IDE 选择",
        "tags": ["knowledge/agent-cli", "source/linuxdo"],
        "description": "Claude Code、Codex CLI、OpenCode、Cursor、Windsurf、Trae 等入口和体感差异。",
        "keywords": [
            "claude code",
            "codex cli",
            "opencode",
            "gemini cli",
            "cursor",
            "windsurf",
            "trae",
            "kiro",
            "cline",
            "roo",
            "ide",
        ],
        "decision": "不要只看模型名；重点比较上下文处理、规则遵从、恢复能力、成本和插件生态。",
    },
    {
        "key": "multi_agent",
        "name": "多 Agent 编排",
        "comparison": "多 Agent 编排工作流",
        "tags": ["knowledge/multi-agent", "source/linuxdo"],
        "description": "Subagent、团队角色、并行开发、CCW/CCG/BMAD 等编排方法。",
        "keywords": [
            "subagent",
            "subagents",
            "multi-agent",
            "agent team",
            "agent teams",
            "ccw",
            "ccg",
            "bmad",
            "devin",
            "编排",
            "团队",
        ],
        "decision": "编排适合复杂任务拆分；价值来自边界、验收和恢复机制，不来自角色数量本身。",
    },
    {
        "key": "api_relay",
        "name": "API 中转与网关",
        "comparison": "API 中转与网关选择",
        "tags": ["knowledge/api-relay", "source/linuxdo"],
        "description": "中转、公益站、网关、账号池、模型路由、稳定性和安全风险。",
        "keywords": [
            "中转",
            "公益站",
            "api",
            "new api",
            "cliproxy",
            "oneapi",
            "anyrouter",
            "openrouter",
            "ccswitch",
            "sub2api",
            "网关",
            "额度",
        ],
        "decision": "这类信息变化快，先看风险和失效概率；准备采用前必须回原文和服务状态复核。",
    },
    {
        "key": "context_memory_mcp",
        "name": "上下文 Memory 与 MCP",
        "comparison": "上下文 Memory 与 MCP 选择",
        "tags": ["knowledge/context-memory", "source/linuxdo"],
        "description": "MCP、RAG、Context7、Memory、Obsidian、长期上下文和资料检索。",
        "keywords": [
            "mcp",
            "context",
            "context7",
            "memory",
            "rag",
            "obsidian",
            "graphiti",
            "上下文",
            "记忆",
            "知识库",
        ],
        "decision": "先判断是否真的减少重复劳动；MCP/Memory 越多，越要控制权限、上下文污染和维护成本。",
    },
    {
        "key": "models_routing",
        "name": "模型与路由",
        "comparison": "模型与路由选择",
        "tags": ["knowledge/models", "source/linuxdo"],
        "description": "Claude、GPT、Gemini、Qwen、Kimi、GLM、DeepSeek 等模型体感和路由策略。",
        "keywords": [
            "claude",
            "gpt",
            "gemini",
            "qwen",
            "kimi",
            "glm",
            "deepseek",
            "haiku",
            "sonnet",
            "模型",
            "路由",
        ],
        "decision": "模型评价会随时间快速变化；更适合作为路由候选，不宜沉淀成长期结论。",
    },
    {
        "key": "github_verification",
        "name": "GitHub 验证候选",
        "comparison": "第三方 Skills 来源与安全",
        "tags": ["knowledge/github-verification", "source/linuxdo"],
        "description": "论坛里出现的 repo、插件、skills 来源、维护状态和安全验证入口。",
        "keywords": [
            "github",
            "repo",
            "repository",
            "release",
            "issue",
            "开源",
            "插件",
            "安全",
        ],
        "decision": "论坛推荐只能算线索；采用前看 README、release、issues、权限范围和最近维护情况。",
    },
]


def organize_existing_readings(
    config: KnowledgeConfig,
    input_path: Path,
    *,
    generated_at: str | None = None,
    top_per_category: int = 18,
) -> dict[str, int]:
    if top_per_category <= 0:
        raise ValueError("top_per_category must be positive")

    generated = generated_at or now_iso()
    readings = _load_legacy_readings(input_path)
    scaffold_vault(config)
    classified = _classify_readings(readings)

    _write_reading_guide(config, generated)
    _write_category_overview(config, classified, generated)
    _write_resource_map(config, classified, generated)
    comparison_count = 0
    category_count = 0
    for category in CATEGORY_DEFS:
        items = classified[category["key"]]
        if not items:
            continue
        _write_category_page(config, category, items, generated, top_per_category)
        _write_comparison_page(config, category, items, generated, top_per_category)
        category_count += 1
        comparison_count += 1
    queue_count = _write_review_queue(config, classified, generated)
    _write_knowledge_concepts_page(config, generated)
    _write_feedback_semantics_pages(config, generated)
    _write_full_reading_manual(config, generated)
    _write_home_index(config, generated)
    _write_maintenance_status(config, generated, category_count=category_count, comparison_count=comparison_count, queue_count=queue_count)
    _write_hot_cache(config, generated)
    append_log(config, f"- {generated}: 刷新导览层，分类 {category_count} 个，对比页 {comparison_count} 张，复核队列 {queue_count} 条。")
    return {
        "readings": len(readings),
        "category_pages": category_count,
        "comparison_pages": comparison_count,
        "review_queue_items": queue_count,
    }


def _classify_readings(readings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    classified: dict[str, list[dict[str, Any]]] = {category["key"]: [] for category in CATEGORY_DEFS}
    for reading in readings:
        text = _reading_text(reading)
        for category in CATEGORY_DEFS:
            score = _keyword_score(text, category["keywords"])
            if score <= 0:
                continue
            classified[category["key"]].append({**reading, "_category_score": score})
    for key, items in classified.items():
        classified[key] = sorted(items, key=lambda item: (-_reading_weight(item), -int(item.get("_category_score", 0)), str(item.get("title", ""))))
    return classified


def _write_reading_guide(config: KnowledgeConfig, generated: str) -> None:
    write_page(
        config.obsidian_vault_path / "00_Home" / "怎么读这个知识库.md",
        {
            "id": "home:reading-guide",
            "type": "guide",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "怎么读这个知识库",
        [
            (
                "先读路线",
                "\n".join(
                    [
                        f"1. 从 {_wiki_link(config, '分类总览')} 选主题：workflow、agent、API 中转、模型、MCP/Memory 或 GitHub 验证。",
                        f"2. 只想找对象时看 {_wiki_link(config, '资源类型地图')}；需要取舍时看对应对比页。",
                        "3. 对比页点到具体资源、服务、工作流、概念页后，只读当前决策需要的段落。",
                        f"4. 准备安装、付费、接入、发现矛盾或页面提示复核时，再看 {_wiki_link(config, '需要回原文复核')} 和原帖。",
                    ]
                ),
            ),
            (
                "哪些目录常看",
                "\n".join(
                    [
                        "- `00_Home/`：入口和导读，只用来决定从哪里读。",
                        "- `10_Catalog/categories/`：主题入口，适合先确定方向。",
                        "- `10_Catalog/comparisons/`：选择入口，适合几个方案之间做取舍。",
                        "- `10_Catalog/resources/`、`services/`、`workflows/`：具体对象页，被对比页或搜索点名时再读。",
                        "- `30_Feedback/`：写你的偏好、采用、拒绝和观察规则。",
                    ]
                ),
            ),
            (
                "通常不用人看",
                "\n".join(
                    [
                        "- `_system/`：来源和证据底账，主要给 agent 查证据。",
                        "- `90_Inbox/sessions/`：每次冲浪的会话记录，通常不用读。",
                        "- `00_Home/log.md`：生成日志，只在排查刷新问题时看。",
                        "- `10_Catalog/candidates/`：不要从头翻；只有被分类、对比、搜索或复核队列点到时再看。",
                        "- `10_Catalog/archive/`：迁移、重复和历史跳转页，通常不用读。",
                        "- 根目录规则文件：主要给 agent 看，人只在调整规则时读。",
                    ]
                ),
            ),
            (
                "字段怎么读",
                "\n".join(
                    [
                        "人手动只管三种：",
                        "- 想追：`watchlist: true` + `status: watching`。",
                        "- 暂时不看：`watchlist: false` + `status: deprioritized`。",
                        "- 明确不要：`watchlist: false` + `status: rejected`。",
                        "其他字段由 agent 维护，不需要日常手改。",
                    ]
                ),
            ),
            (
                "怎么表达兴趣",
                "\n".join(
                    [
                        f"- 想追：写 `watchlist: true` + `status: watching`，再到 {_wiki_link(config, 'Watchlist 使用规则')} 或页面底部 `## 我的反馈` 写为什么。",
                        "- `watchlist` 是跟踪锚点：下次同步后会进入热索引，影响相关 topic 的刷新优先级。",
                    ]
                ),
            ),
            (
                "怎么表达不感兴趣",
                "\n".join(
                    [
                        "- 暂时不看：写 `watchlist: false` + `status: deprioritized`，意思是先降权，但不是拉黑。",
                        "- 明确不要：写 `watchlist: false` + `status: rejected`，并在 `## 我的反馈` 写拒绝原因。",
                        "- 下一轮任务前，agent 只同步改动过的反馈页和人类反馈区，不会全量重读 Vault。",
                    ]
                ),
            ),
        ],
    )


def _write_category_overview(config: KnowledgeConfig, classified: dict[str, list[dict[str, Any]]], generated: str) -> None:
    lines = []
    for category in CATEGORY_DEFS:
        count = len(classified[category["key"]])
        lines.append(
            f"- {_wiki_link(config, category['name'])}：{category['description']} 当前命中 {count} 条。"
        )
    write_page(
        page_path_for(config, "category", "分类总览"),
        {
            "id": "category:overview",
            "type": "category",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "分类总览",
        [
            ("分类入口", "\n".join(lines)),
            ("资源入口", f"{_wiki_link(config, '资源类型地图')} 把资源按 workflow / agent / 中转 / 模型 / memory / GitHub 验证拆开，避免在候选文件夹里从头翻。"),
            (
                "阅读建议",
                "分类页解决“这类东西有什么”；对比页解决“我该选哪个”；资源卡解决“这个具体对象值不值得继续看”；候选区只放证据不足或尚未归类的线索。底层来源和证据主要用于追溯，不是日常阅读入口。",
            ),
            (
                "分类边界",
                "同一条来源可能同时进入多个分类，例如 Superpowers 既是 skill/workflow，也可能进入 GitHub 验证；API 中转和模型路由也常常互相牵连。分类是阅读入口，不是唯一真相。",
            ),
        ],
    )


def _write_resource_map(config: KnowledgeConfig, classified: dict[str, list[dict[str, Any]]], generated: str) -> None:
    sections = []
    for category in CATEGORY_DEFS:
        resources = _top_tools(classified[category["key"]], category["key"], limit=20)
        sections.append((category["name"], _resource_lines(config, resources)))
    write_page(
        page_path_for(config, "category", "资源类型地图"),
        {
            "id": "category:resource-map",
            "type": "category",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "资源类型地图",
        [
            (
                "怎么用",
                "这页只解决“资源太混”的问题：先按类型看名字，再跳到资源卡、工作流、概念或对比页。泛称、分类词和过宽概念会被过滤，所以这里不会完整列出所有来源。",
            ),
            *sections,
        ],
    )


def _write_category_page(
    config: KnowledgeConfig,
    category: dict[str, Any],
    items: list[dict[str, Any]],
    generated: str,
    top_per_category: int,
) -> None:
    resources = _top_tools(items, category["key"], limit=16)
    source_lines = [_source_line(item) for item in items[:top_per_category]]
    write_page(
        page_path_for(config, "category", category["name"]),
        {
            "id": f"category:{category['key']}",
            "type": "category",
            "status": "active",
            "tags": category["tags"],
            "last_verified": generated[:10],
            "source_count": len(items),
        },
        category["name"],
        [
            ("这个分类看什么", category["description"]),
            ("推荐先看", _resource_lines(config, resources)),
            ("相关对比", _wiki_link(config, category["comparison"])),
            ("代表来源", "\n".join(source_lines)),
            ("当前使用建议", category["decision"]),
            ("需要注意", "这些内容来自社区讨论，适合作为线索和经验样本；涉及安装、付费、安全、模型效果和服务稳定性时，应在采用前复核。"),
        ],
    )


def _write_comparison_page(
    config: KnowledgeConfig,
    category: dict[str, Any],
    items: list[dict[str, Any]],
    generated: str,
    top_per_category: int,
) -> None:
    positives = _collect_notes(items, "positive_feedback", 5)
    negatives = _collect_notes(items, "negative_feedback", 5)
    risks = _collect_notes(items, "risk_notes", 6)
    comparisons = _collect_notes(items, "comparison_notes", 8)
    sources = [_source_line(item) for item in items[:top_per_category]]
    write_page(
        page_path_for(config, "comparison", category["comparison"]),
        {
            "id": f"comparison:{category['key']}",
            "type": "comparison",
            "status": "active",
            "tags": category["tags"],
            "last_verified": generated[:10],
            "source_count": len(items),
        },
        category["comparison"],
        [
            ("当前结论", category["decision"]),
            ("比较范围", f"在 `{category['name']}` 这一类里，如何从论坛线索中筛出值得试、值得观察、应该跳过的选项。"),
            ("入口选项", _resource_lines(config, _top_tools(items, category["key"], limit=18))),
            ("各派意见", _opinion_lines(positives, negatives, comparisons)),
            ("评价维度", _criteria_for(category["key"])),
            ("适合选择", category["decision"]),
            ("不适合选择", _not_suitable_for(category["key"])),
            ("为什么", _why_for(category["key"], positives, negatives, comparisons, risks)),
            ("待验证", "\n".join(f"- {item}" for item in risks) or "- 暂无明确风险摘要；准备采用前仍需回到来源和项目页确认。"),
            ("证据与来源", "\n".join(sources)),
        ],
    )


def _write_review_queue(config: KnowledgeConfig, classified: dict[str, list[dict[str, Any]]], generated: str) -> int:
    candidates: dict[str, dict[str, Any]] = {}
    for category in CATEGORY_DEFS:
        for item in classified[category["key"]]:
            topic_id = str(item.get("id") or item.get("topic_id") or item.get("url") or item.get("title"))
            reasons = _review_reasons(item, category["key"])
            if not reasons:
                continue
            existing = candidates.setdefault(topic_id, {**item, "_review_reasons": [], "_review_categories": []})
            existing["_review_reasons"].extend(reasons)
            existing["_review_categories"].append(category["name"])

    ranked = sorted(candidates.values(), key=lambda item: (-_review_weight(item), str(item.get("title", ""))))[:80]
    grouped_lines = {"open": [], "deferred": [], "resolved": []}
    for item in ranked:
        reason_text = "；".join(_unique_strings(item["_review_reasons"])[:3])
        category_text = "、".join(_unique_strings(item["_review_categories"])[:3])
        line = f"- {_source_line(item)}｜{category_text}｜{reason_text}"
        grouped_lines[_review_queue_status(item)].append(line)

    write_page(
        page_path_for(config, "review", "需要回原文复核"),
        {
            "id": "review:source-reread-needed",
            "type": "review",
            "status": "open",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
            "source_count": len(ranked),
        },
        "需要回原文复核",
        [
            (
                "这页怎么用",
                "这里放的是“摘要不足以支撑采用或结论”的来源。它不是必读清单；只有当你准备采用某个工具、遇到争议、或要更新某张资源页/候选页时，才从这里挑相关原文复核。",
            ),
            ("需要处理", "\n".join(grouped_lines["open"]) or "- 暂无需要优先复核的来源。"),
            ("暂时延后", "\n".join(grouped_lines["deferred"]) or "- 暂无暂时延后的复核项。"),
            ("已处理", "\n".join(grouped_lines["resolved"]) or "- 暂无已处理的复核项。"),
            (
                "触发规则",
                "\n".join(
                    [
                        "- API 中转、公益站、模型、价格、稳定性等变化快的内容。",
                        "- 有明显正反意见、替代方案或争议，但摘要不足以还原上下文。",
                        "- 候选资源可能会被采用，需要确认 GitHub、安装方式、权限和维护状态。",
                        "- 渲染、截图、教程或 UI 证据尚未核验完整。",
                    ]
                ),
            ),
        ],
    )
    return len(ranked)


def _review_queue_status(item: dict[str, Any]) -> str:
    status = str(item.get("review_status") or item.get("status") or "open").strip().lower()
    if status == "deferred":
        return "deferred"
    if status in {"resolved", "converted_to_page"}:
        return "resolved"
    return "open"


def _write_home_index(config: KnowledgeConfig, generated: str) -> None:
    write_page(
        config.obsidian_vault_path / "00_Home" / "index.md",
        {
            "id": "home:index",
            "type": "home",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "Linux.do AI 知识库",
        [
            (
                "按主题读",
                "\n".join(
                    [
                        f"- {_wiki_link(config, '分类总览')}：按主题进入。",
                        f"- {_wiki_link(config, '资源类型地图')}：按资源类型找对象。",
                        f"- {_wiki_link(config, '怎么读这个知识库')}：首次使用时看一次。",
                    ]
                ),
            ),
            (
                "按选择读",
                "\n".join(
                    [
                        *[f"- {_wiki_link(config, category['comparison'])}" for category in CATEGORY_DEFS],
                        f"- {_wiki_link(config, 'Trellis-Superpowers-CodeStable-OpenSpec-对比')}",
                        f"- {_wiki_link(config, 'CCG-CCW-多CLI编排对比')}",
                    ]
                ),
            ),
            (
                "采用前复核",
                "\n".join(
                    [
                        f"- {_wiki_link(config, '需要回原文复核')}：准备安装、付费、接入或发现矛盾时再看。",
                        f"- {_wiki_link(config, 'Watchlist 使用规则')}：决定想追、暂时不看、明确不要。",
                    ]
                ),
            ),
        ],
    )


def _write_hot_cache(config: KnowledgeConfig, generated: str) -> None:
    write_page(
        config.obsidian_vault_path / "00_Home" / "hot.md",
        {
            "type": "hot-cache",
            "updated": generated[:10],
        },
        "Hot Cache",
        [
            (
                "最近上下文",
                "\n".join(
                    [
                        "Vault 按人类阅读优先组织：Home 负责入口，Catalog 负责主题和对象，Feedback 负责你的偏好。",
                        "`_system/` 是来源和证据底账，`90_Inbox/sessions/` 是会话日志；启动时不要全量读取。",
                    ]
                ),
            ),
            (
                "下次启动",
                "\n".join(
                    [
                        "- 先读 `AGENTS.md`、本页和 `00_Home/index.md`。",
                        "- 需要用户偏好时优先读 `30_Feedback/` 和 hot indexes/context pack。",
                        "- 需要证据时再回 `_system/`、复核队列或原帖。",
                    ]
                ),
            ),
        ],
        include_feedback=False,
    )


def _write_maintenance_status(
    config: KnowledgeConfig,
    generated: str,
    *,
    category_count: int,
    comparison_count: int,
    queue_count: int,
) -> None:
    counts = _vault_layer_counts(config.obsidian_vault_path)
    review_pages = len(list((config.obsidian_vault_path / "90_Inbox" / "review-queue").glob("*.md")))
    write_page(
        config.obsidian_vault_path / "00_Home" / "维护状态.md",
        {
            "id": "home:maintenance-status",
            "type": "guide",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "维护状态",
        [
            (
                "人读页面",
                "\n".join(
                    [
                        f"- 当前人读页：{counts['human']} 张。",
                        f"- 本轮刷新分类页 {category_count} 张、对比页 {comparison_count} 张。",
                        "- 日常启动只读 context pack 和热索引，不全量读人读页。",
                    ]
                ),
            ),
            (
                "系统底账",
                "\n".join(
                    [
                        f"- 机器底账页：{counts['ledger']} 张。",
                        f"- 过渡页：{counts['transitional']} 张。",
                        "- `_system/` 和 `90_Inbox/sessions/` 默认不进首页导读，只在查证据或排错时使用。",
                    ]
                ),
            ),
            (
                "复核队列",
                "\n".join(
                    [
                        f"- 当前复核队列页：{review_pages} 张。",
                        f"- 本轮候选复核来源：{queue_count} 条。",
                        "- 采用、付费、接入、发现矛盾前，先从复核队列回原文。",
                    ]
                ),
            ),
            (
                "本轮建议",
                "\n".join(
                    [
                        "- 保持单批新建人读页 <= 20，复核队列新增 <= 80。",
                        "- context pack 目标 < 20KB；超过时优先缩短反馈预览和 topic 列表。",
                        "- 继续把 `_system/evidence` 当冷底账，不放进首页阅读路径。",
                    ]
                ),
            ),
        ],
    )


def _vault_layer_counts(vault_path: Path) -> dict[str, int]:
    from .quality_audit import layer_for_path

    counts = {"human": 0, "transitional": 0, "ledger": 0, "ignored": 0}
    for path in vault_path.rglob("*.md"):
        relative = path.relative_to(vault_path).as_posix()
        if relative.startswith(".obsidian/"):
            continue
        counts[layer_for_path(relative)] += 1
    return counts


def _write_knowledge_concepts_page(config: KnowledgeConfig, generated: str) -> None:
    write_page(
        config.obsidian_vault_path / "00_Home" / "知识库概念说明.md",
        {
            "id": "home:knowledge-concepts",
            "type": "guide",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
        },
        "知识库概念说明",
        [
            (
                "这页解决什么",
                "这页只解释知识库里的通用概念。读懂这里以后，其他页面不再重复解释相同字段和标签。",
            ),
            (
                "页面类型 type",
                "\n".join(
                    [
                        "- `home`：首页入口。",
                        "- `guide`：说明书和带读页。",
                        "- `category`：主题入口，回答“这类东西是什么范围”。",
                        "- `comparison`：对比页，回答“几个方案怎么取舍”。",
                        "- `resource`：具体工具、repo、skill、plugin、模型入口或可采用对象。",
                        "- `service`：中转、网关、API 服务、公益服务等高时效对象。",
                        "- `collection`：资源集合或导航入口，例如公益站列表，不当作单一推荐。",
                        "- `candidate`：证据不足或对象边界不清的临时线索。",
                        "- `component`：workflow 中的局部能力，例如澄清、计划、验证、恢复。",
                        "- `workflow`：可执行流程页。",
                        "- `claim`：判断页，保存一个目前需要证据支撑或仍有争议的结论。",
                        "- `draft`：草稿知识页，不当作稳定结论。",
                        "- `decision` / `preference`：你的决策和偏好，会反哺下一轮冲浪。",
                        "- `review`：复核入口，提醒哪些内容需要回原文或补证据。",
                    ]
                ),
            ),
            (
                "页面状态 status",
                "\n".join(
                    [
                        "人手动只管三种：",
                        "- 想追：`watchlist: true` + `status: watching`。",
                        "- 暂时不看：`watchlist: false` + `status: deprioritized`。",
                        "- 明确不要：`watchlist: false` + `status: rejected`。",
                        "其他页面状态和证据字段由 agent 维护，不需要日常手改。",
                    ]
                ),
            ),
            (
                "Tags 标签",
                "\n".join(
                    [
                        "这些是 Obsidian 页面 frontmatter 里的阅读标签。它们主要服务人类浏览、筛选和图谱，不是冲浪状态机的核心字段。",
                        "- `#knowledge/linuxdo`：Linux.do 知识库的说明、首页、复核入口等通用页面。",
                        "- `#knowledge/workflow`：AI coding workflow、skills、spec、vibecoding。",
                        "- `#knowledge/agent-cli`：Codex、Claude Code、OpenCode、Cursor 等入口。",
                        "- `#knowledge/multi-agent`：多 agent、subagent、编排。",
                        "- `#knowledge/api-relay`：API 中转、网关、公益站。",
                        "- `#knowledge/context-memory`：MCP、Memory、RAG、Obsidian、上下文管理。",
                        "- `#knowledge/models`：模型与路由。",
                        "- `#knowledge/github-verification`：需要去 GitHub 验证的候选。",
                        "- `#source/linuxdo`：页面的主要证据来自 Linux.do 社区。",
                    ]
                ),
            ),
            (
                "标签删掉会怎样",
                "\n".join(
                    [
                        "先分清两类 tag：",
                        "- Obsidian 页面里的 `tags`：主要给人看。删除后，页面内容、wikilink、反馈同步、已读索引通常不会坏。",
                        "- 机器状态里的 topic/bookmark tags：用于来源筛选、bookmark 优先级或 topic 摘要，不建议手动删。",
                        "",
                        "当前人读页面里的 tag，代码层面基本不依赖。`feedback-sync` 主要读取 `id`、`type`、`status` 和 `## 我的反馈`；`knowledge-organize-existing` 会重新生成页面 tag。",
                        "所以，如果你只是在 Obsidian 里手动删某个 tag：短期不会影响功能；下一次重新整理时，生成器会按规则写回来。",
                    ]
                ),
            ),
            (
                "哪些标签不再默认生成",
                "\n".join(
                    [
                        "- `#home`：首页已有目录和 `type: home`，不需要再用标签表达。",
                        "- `#guide/reading`：说明页已有 `type: guide` 和 `00_Home/` 目录。",
                        "- `#catalog/category`、`#catalog/comparison`、`#catalog/candidate`、`#catalog/workflow`：和目录、`type` 重复。",
                        "- `#catalog/resource-map`：只有资源类型地图这一页使用，标题已经足够。",
                        "- 复核类结构标签：和复核页标题/目录重复。",
                        "- `#wiki/draft`：草稿页用 `type: draft` 和目录表达即可。",
                    ]
                ),
            ),
            (
                "哪些标签建议保留",
                "\n".join(
                    [
                        "- `#knowledge/workflow`：把 workflow / skill / spec / vibecoding 主题串起来。",
                        "- `#knowledge/agent-cli`：把 Codex、Claude Code、OpenCode、Cursor 等入口串起来。",
                        "- `#knowledge/multi-agent`：把 subagent、多 agent、编排相关页面串起来。",
                        "- `#knowledge/api-relay`：把中转、网关、公益站相关页面串起来；这类内容变化快，单独筛出来有用。",
                        "- `#knowledge/context-memory`：把 MCP、Memory、RAG、Obsidian、上下文管理串起来。",
                        "- `#knowledge/models`：把模型与路由相关页面串起来。",
                        "- `#knowledge/github-verification`：提醒这些候选需要 GitHub 维护、安全、issue、release 验证。",
                        "- `#source/linuxdo`：现在看起来宽泛，但未来混入 GitHub 来源后，它能区分证据来源。",
                    ]
                ),
            ),
            (
                "如果真想精简标签",
                "\n".join(
                    [
                        "第一阶段不建议直接手删页面 tag，因为重新生成会恢复。",
                        "现在生成规则已经改成：保留主题标签和来源标签，去掉和目录/type 重复的结构标签。",
                        "推荐保留：`#knowledge/*`、`#source/linuxdo`。",
                        "不再默认生成：`#catalog/*`、`#guide/reading`、`#home`、`#review/source-*`。",
                        "这样 Obsidian 里保留真正有助于跨页面联想的主题网络，减少只是目录别名的标签噪音。",
                    ]
                ),
            ),
            (
                "证据概念",
                "\n".join(
                    [
                        "- `evidence_status: community_evidence`：主要来自社区讨论，不是官方事实。",
                        "- `staleness_risk`：过时风险。模型、价格、API、中转、插件权限通常更容易变化。",
                        "- `source_count`：关联来源数量。数量多只代表讨论多，不自动代表正确。",
                        "- `supports`：支持某个 claim 的证据。",
                        "- `related_resources`：和当前判断相关的资源。",
                        "- `watchlist`：值得后续自然遇到时继续补证据。",
                    ]
                ),
            ),
            (
                "Watchlist 策略",
                "\n".join(
                    [
                        "- 想追：`watchlist: true` + `status: watching`。",
                        "- 暂时不看：`watchlist: false` + `status: deprioritized`。",
                        "- 明确不要：`watchlist: false` + `status: rejected`。",
                        "- `deprioritized` 是“暂时不看，但不拉黑”。",
                        "- 其他字段由 agent 维护，不需要日常手改。",
                    ]
                ),
            ),
            (
                "反馈概念",
                "\n".join(
                    [
                        "- `## 我的反馈` 是你写给 agent 的地方。",
                        "- 你可以写：采用、拒绝、观察、分类不对、结论太满、想追某个方向。",
                        "- 下一轮同步只读改动过的反馈文件，不会为了反馈全量重读 Vault。",
                        "- 你的反馈不一定要标准，agent 后续会理解、归纳、必要时重写 agent 生成部分。",
                    ]
                ),
            ),
            (
                "不要误读",
                "\n".join(
                    [
                        "- 资源卡不是推荐榜，候选页更不是推荐榜。",
                        "- 社区争议不是事实结论。",
                        "- 热门不等于正确，但热门回复常常能暴露风险和反方意见。",
                        "- 准备采用、付费、安装、接入中转或改 workflow 前，要看复核队列和原文。",
                    ]
                ),
            ),
        ],
    )


def _write_full_reading_manual(config: KnowledgeConfig, generated: str) -> None:
    pages = _human_readable_pages(config.obsidian_vault_path)
    sections = [
        (
            "先读结论",
            "\n".join(
                [
                    "这不是一个需要从头读到尾的 Vault。正常阅读顺序是：Home -> 分类 -> 对比 -> 资源/服务/工作流/概念 -> 来源复核。",
                    "`_system/` 和 `90_Inbox/sessions/` 是底账，主要给 agent 做证据追溯和增量整理；人只有在查证据时才进去。",
                    "资源卡不是最终结论。论坛内容可能过时、冲突或被后续回复修正，所以准备采用前要看复核队列和原文。",
                    "页面索引只做导航；标签、字段和目录读法只在前面解释一次，后面默认相同的内容不重复。",
                ]
            ),
        ),
        (
            "先看概念",
            f"字段、状态、标签、证据和反馈这些概念统一放在 {_wiki_link(config, '知识库概念说明')}，这里不再重复统计页数。",
        ),
        ("目录带读", _directory_guide(pages)),
        (
            "怎么写反馈",
            f"在任何人读页面底部的 `## 我的反馈` 写你的判断即可：采用、拒绝、观察、觉得分类错了、觉得结论太满、想让 agent 下次追某个方向。watchlist 的细节见 {_wiki_link(config, 'Watchlist 使用规则')}。下一轮同步只读取改动过的反馈文件，不需要全量重读 Vault。",
        ),
        (
            "不做逐页索引",
            "这页只解释目录和路径，不列出每张资源卡。想找具体对象时用 Obsidian 搜索、分类页、资源类型地图、对比页或复核队列进入。",
        ),
    ]
    write_page(
        config.obsidian_vault_path / "00_Home" / "全库带读手册.md",
        {
            "id": "home:full-reading-manual",
            "type": "guide",
            "status": "active",
            "tags": ["knowledge/linuxdo"],
            "last_verified": generated[:10],
            "page_count": len(pages),
        },
        "全库带读手册",
        sections,
    )


def _write_feedback_semantics_pages(config: KnowledgeConfig, generated: str) -> None:
    write_page(
        page_path_for(config, "decision", "Watchlist 使用规则"),
        {
            "id": "feedback:decision:watchlist-semantics",
            "type": "decision",
            "status": "active",
            "tags": ["feedback/decision"],
            "last_verified": generated[:10],
        },
        "Watchlist 使用规则",
        [
            (
                "当前决定",
                "\n".join(
                    [
                        "- 想追：`watchlist: true` + `status: watching`。",
                        "- 暂时不看：`watchlist: false` + `status: deprioritized`。",
                        "- 明确不要：`watchlist: false` + `status: rejected`。",
                        "- `deprioritized` 是“暂时不看，但不拉黑”。",
                        "- 其他字段由 agent 维护，不需要日常手改。",
                    ]
                ),
            ),
            (
                "勾选会影响什么",
                "\n".join(
                    [
                        "- `watchlist: true` 是跟踪锚点；下一次 `feedback-sync` 后会进入热索引和 context pack。",
                        "- 相关 topic 有新回复、重新出现或被你的反馈点名时，计划会更愿意补读新增上下文。",
                        "- agent 不会全量重读 Vault；它优先读热索引、context pack 和改动过的反馈页。",
                    ]
                ),
            ),
            (
                "不想看怎么写",
                "\n".join(
                    [
                        "- 暂时不看就用 `watchlist: false` + `status: deprioritized`。",
                        "- 明确不要就用 `watchlist: false` + `status: rejected`，并在 `## 我的反馈` 写原因。",
                        "- 只改 `watchlist: false` 而不改状态，agent 只能知道你不想跟踪，看不到原因和强度。",
                    ]
                ),
            ),
        ],
    )
    write_page(
        page_path_for(config, "preference", "冲浪筛选偏好"),
        {
            "id": "feedback:preference:surfing-selection",
            "type": "preference",
            "status": "active",
            "tags": ["feedback/preference"],
            "last_verified": generated[:10],
        },
        "冲浪筛选偏好",
        [
            (
                "优先看",
                "\n".join(
                    [
                        "- 能提升 AI coding 工作效率和质量的 skill、插件、workflow、agent、MCP、CLI、repo。",
                        "- 有实测过程、失败反馈、替代方案、争议回复或 GitHub 维护证据的内容。",
                        "- 能解释“为什么有效、适合什么、不适合什么、和谁相比”的经验帖。",
                        "- 对 token 成本、上下文污染、流程过重、配置冲突有清楚讨论的内容。",
                    ]
                ),
            ),
            (
                "降低优先级",
                "\n".join(
                    [
                        "- 只有泛泛夸赞、收藏、mark、求链接、情绪表达的回复。",
                        "- 只有热度但没有实测、反方、更新状态或可迁移经验的帖子。",
                        "- 单纯公益站收集、账号额度、短期可用性播报；除非它影响工具链选择或风险判断。",
                        "- 已经记录过且没有新观点、新反方、新版本、新事故或新替代方案的重复内容。",
                    ]
                ),
            ),
            (
                "怎么追加偏好",
                "\n".join(
                    [
                        "- 在 `## 我的反馈` 里直接写你想多看或少看的方向。",
                        "- 想多看某方向，可以写“优先看 X，因为 Y”。",
                        "- 想少看某方向，可以写“降低 X，除非出现 Y”。",
                    ]
                ),
            ),
            (
                "对下一轮冲浪的影响",
                "\n".join(
                    [
                        "- 遇到已记录对象时，只补会改变判断的新证据。",
                        "- 热门帖子可以优先看回复，因为回复常暴露反方和替代方案，但热度不等于质量。",
                        "- 资源推荐要尽量沉淀到具体资源、服务、workflow、component 或 comparison，不堆到集合页。",
                    ]
                ),
            ),
        ],
    )
    write_page(
        page_path_for(config, "rejection", "低价值内容排除规则"),
        {
            "id": "feedback:rejection:low-value-content",
            "type": "rejection",
            "status": "active",
            "tags": ["feedback/rejection"],
            "last_verified": generated[:10],
        },
        "低价值内容排除规则",
        [
            (
                "默认跳过",
                "\n".join(
                    [
                        "- 没有新工具、新观点、新反方、新版本、新事故或新实测的重复推荐。",
                        "- 只有“mark”“蹲”“求链接”“感谢分享”“看起来不错”的浅回复。",
                        "- 纯短期资源可用性播报，且不影响服务风险判断或工具链选择。",
                        "- 标题相关但正文只是在闲聊、情绪表达或求助，没有可迁移经验。",
                    ]
                ),
            ),
            (
                "可以例外",
                "\n".join(
                    [
                        "- 热门帖回复里出现多派观点、替代方案、失败案例或作者修正。",
                        "- 已记录对象出现重大版本、维护状态、权限范围、价格额度、服务事故变化。",
                        "- 一个看似普通资源被多个高价值 workflow 或 comparison 反复引用。",
                    ]
                ),
            ),
            (
                "怎么表达拒绝",
                "\n".join(
                    [
                        "- 单页不感兴趣：在该页写 `status: deprioritized` 或反馈“不想继续看这个方向”。",
                        "- 明确拒绝某对象：写 `status: rejected`，并说明隐私、安全、维护、成本或方向不符等原因。",
                        "- 规则级排除：在本页 `## 我的反馈` 写“以后少看 X，除非 Y”。",
                        "- 只取消 watchlist 不等于拒绝，agent 不容易知道原因。",
                    ]
                ),
            ),
            (
                "对下一轮冲浪的影响",
                "\n".join(
                    [
                        "- 这些规则用于降权，不是永久封禁。",
                        "- 如果你手动把某页改成 watchlist 或写反馈，人工信号优先。",
                    ]
                ),
            ),
        ],
    )


def _reading_text(reading: dict[str, Any]) -> str:
    values = [
        reading.get("title", ""),
        reading.get("summary", ""),
        reading.get("first_post", ""),
        " ".join(str(item) for item in reading.get("tools", []) or []),
        " ".join(str(item) for item in reading.get("tags", []) or []),
        " ".join(str(item) for item in reading.get("comparison_notes", []) or []),
        " ".join(str(item) for item in reading.get("risk_notes", []) or []),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _keyword_score(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _reading_weight(reading: dict[str, Any]) -> int:
    value = str(reading.get("value_tag", "")).lower()
    base = 3 if value in {"high", "马上试"} else 2 if value in {"medium", "收藏观察", "谨慎"} else 1
    comparison_bonus = 2 if reading.get("comparison_notes") else 0
    reply_bonus = min(int(reading.get("visible_post_count") or 0), 120) // 30
    return base * 10 + comparison_bonus + reply_bonus


def _top_tools(items: list[dict[str, Any]], category_key: str, limit: int) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    for item in items:
        candidates = list(item.get("tools", []) or [])
        if category_key == "github_verification":
            candidates.extend(item.get("github_repos", []) or [])
        for tool in candidates:
            name = str(tool).strip()
            if not _is_specific_candidate(name, category_key):
                continue
            key, display = _canonical_candidate(name, category_key)
            counts[key] += _reading_weight(item)
            display_names.setdefault(key, display)
    return [(display_names[key], score) for key, score in counts.most_common(limit)]


def _is_specific_candidate(name: str, category_key: str) -> bool:
    lower = name.lower().strip()
    if not lower:
        return False
    generic = {
        "agent",
        "agents",
        "ai",
        "api",
        "api 中转",
        "cli",
        "github",
        "llm",
        "mcp",
        "model",
        "models",
        "plugin",
        "plugins",
        "prompt",
        "prompts",
        "repo",
        "repository",
        "skill",
        "skills",
        "tool",
        "tools",
        "workflow",
        "中转",
        "中转站",
        "公益站",
        "人工智能",
        "软件开发",
    }
    if lower in generic:
        return False

    if category_key == "models_routing":
        if any(word in lower for word in ["code", "workflow", "mcp", "api", "load", "hub", "cursor"]):
            return False
        model_names = {
            "claude",
            "gemini",
            "qwen",
            "kimi",
            "glm",
            "deepseek",
            "gpt",
            "haiku",
            "sonnet",
            "opus",
            "grok",
        }
        return lower in model_names or lower.startswith(("gpt-", "qwen-", "glm-", "deepseek-", "claude-", "gemini-"))

    allow_patterns = {
        "ai_coding_workflow": [
            "superpowers",
            "trellis",
            "openspec",
            "codestable",
            "bmad",
            "grill",
            "harness",
            "agents.md",
            "claude.md",
            "tdd",
            "spec",
            "vibecoding",
            "requirements-pilot",
            "kiro",
        ],
        "agent_cli_ide": [
            "claude code",
            "codex",
            "opencode",
            "gemini cli",
            "cursor",
            "windsurf",
            "trae",
            "roo",
            "cline",
            "kiro",
            "antigravity",
            "openclaw",
            "vscode",
            "vs code",
        ],
        "multi_agent": [
            "subagent",
            "agent team",
            "ccw",
            "ccg",
            "bmad",
            "maestro",
            "devin",
            "claude-code-workflow",
            "harness",
        ],
        "api_relay": [
            "openrouter",
            "new api",
            "cliproxy",
            "cliproxyapi",
            "anyrouter",
            "oneapi",
            "ccswitch",
            "cc-switch",
            "sub2api",
            "cpa",
            "cpamc",
            "router",
            "proxy",
            "gpt-load",
            "cherry studio",
        ],
        "context_memory_mcp": [
            "context7",
            "mem0",
            "memory",
            "memorymesh",
            "rag",
            "obsidian",
            "graphiti",
            "serena",
            "mcp-run",
            "think-mcp",
            "software-planning-mcp",
            "vibe-check-mcp",
        ],
        "github_verification": ["/", "github", "repo", "skills", "workflow", "opencode", "trellis", "superpowers"],
    }
    return any(pattern in lower for pattern in allow_patterns.get(category_key, []))


def _canonical_candidate(name: str, category_key: str) -> tuple[str, str]:
    display = name.strip()
    if category_key == "github_verification":
        display = display.removeprefix("https://github.com/").removeprefix("http://github.com/")
        display = display.strip("/")
    return normalize_resource_name(display)


def _resource_lines(config: KnowledgeConfig, resources: list[tuple[str, int]]) -> str:
    if not resources:
        return "- 暂无稳定入口。"
    return "\n".join(f"- {_wiki_link(config, name)}" for name, _score in resources)


def _wiki_link(config: KnowledgeConfig, name: str) -> str:
    target = safe_filename(name)
    if _is_generated_page_name(name) or _page_stem_exists(config.obsidian_vault_path, target):
        return f"[[{target}|{name}]]"
    return name


def _is_generated_page_name(name: str) -> bool:
    generated_names = {
        "怎么读这个知识库",
        "全库带读手册",
        "知识库概念说明",
        "分类总览",
        "资源类型地图",
        "需要回原文复核",
        *(category["name"] for category in CATEGORY_DEFS),
        *(category["comparison"] for category in CATEGORY_DEFS),
    }
    return name in generated_names


def _page_stem_exists(vault_path: Path, stem: str) -> bool:
    return any(path.stem == stem for path in vault_path.rglob("*.md"))


def _human_readable_pages(vault_path: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for path in sorted(vault_path.rglob("*.md")):
        rel = path.relative_to(vault_path)
        rel_text = str(rel)
        if rel_text.startswith("_system/") or rel_text.startswith("90_Inbox/sessions/"):
            continue
        if rel_text == "00_Home/全库带读手册.md":
            continue
        text = path.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(text)
        pages.append(
            {
                "path": path,
                "relative_path": rel_text,
                "title": _page_title(text, path.stem),
                "type": frontmatter.get("type", ""),
                "status": frontmatter.get("status", ""),
                "tags": frontmatter.get("tags", []),
                "frontmatter": frontmatter,
                "summary": _page_summary(text),
            }
        )
    pages.append(
        {
            "path": vault_path / "00_Home" / "全库带读手册.md",
            "relative_path": "00_Home/全库带读手册.md",
            "title": "全库带读手册",
            "type": "guide",
            "status": "active",
            "tags": ["guide/reading", "knowledge/linuxdo"],
            "frontmatter": {
                "id": "home:full-reading-manual",
                "type": "guide",
                "status": "active",
                "tags": ["guide/reading", "knowledge/linuxdo"],
            },
            "summary": "逐页解释标签、字段、目录、页面用途和阅读顺序；用于理解整个 Vault，不需要每次冲浪前都读。",
        }
    )
    pages.sort(key=lambda page: page["relative_path"])
    return pages


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    result: dict[str, Any] = {}
    current_key = ""
    for line in text[4:end].splitlines():
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


def _page_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _page_summary(text: str) -> str:
    preferred = [
        "先读结论",
        "这个分类看什么",
        "问题",
        "当前判断",
        "初步判断",
        "为什么被抓到",
        "整理结果",
        "这页怎么用",
        "入口",
        "当前使用建议",
    ]
    for heading in preferred:
        body = _section_body(text, heading)
        if body:
            return _clip(_clean_human_text(body), 130)
    paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith(("#", "---", "- ", "  - "))]
    return _clip(_clean_human_text(paragraphs[0]), 130) if paragraphs else "这页暂无摘要。"


def _section_body(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        return ""
    body_start = text.find("\n", start)
    if body_start == -1:
        return ""
    next_heading = text.find("\n## ", body_start + 1)
    body = text[body_start: next_heading if next_heading != -1 else None].strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return " ".join(lines[:4])


def _tag_counts(pages: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        for tag in _as_list(page.get("tags")):
            counts[tag] += 1
    return counts


def _field_counts(pages: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update(page.get("frontmatter", {}).keys())
    return counts


def _field_glossary(fields: Counter[str]) -> str:
    meanings = {
        "id": "稳定机器 ID，用于 agent 增量更新和避免重名页冲突。",
        "type": "页面类型。决定这页是候选、分类、对比、claim、反馈还是导览。",
        "status": "页面当前状态。`active` 可读，`candidate` 待验证，`open` 待处理，`disputed` 有争议，`draft` 尚未定稿。",
        "tags": "Obsidian 标签，也是人和 agent 的入口线索。",
        "last_verified": "最后整理或核验日期，不代表原帖内容没有更新。",
        "last_reviewed": "最后人工或 agent 判断日期，常见于 claim。",
        "evidence_status": "证据成熟度。`community_evidence` 表示主要来自社区讨论，还不是确定事实。",
        "staleness_risk": "过时风险。API、模型、中转、价格、插件权限通常风险更高。",
        "watchlist": "是否进入观察名单。true 表示下次遇到相关讨论时更值得补证据。",
        "source_count": "关联来源数量。数量高只代表讨论多，不自动等于质量高。",
        "supports": "支持某个 claim 的证据链接。",
        "related_resources": "与 claim 或页面相关的资源 ID。",
        "page_count": "本手册统计到的人读页面数量。",
    }
    lines = []
    for field, count in sorted(fields.items()):
        lines.append(f"- `{field}`（{count} 页）：{meanings.get(field, '辅助元数据，用于筛选、同步或追溯。')}")
    return "\n".join(lines) or "- 当前没有 frontmatter 字段。"


def _tag_glossary(tags: Counter[str]) -> str:
    meanings = {
        "home": "首页入口。",
        "guide/reading": "阅读说明页，解决怎么读、从哪读、哪些不用读。",
        "knowledge/linuxdo": "Linux.do 来源知识库的总入口或说明。",
        "catalog/category": "分类入口页，帮你决定进入哪个主题。",
        "catalog/resource-map": "资源地图页，按资源类型拆候选。",
        "catalog/comparison": "对比页，帮你在几个选项之间做选择。",
        "catalog/candidate": "候选资源卡，保存工具、模型、插件、workflow、repo 等线索。",
        "catalog/workflow": "可执行工作流页面。",
        "wiki/draft": "草稿知识页，暂不当作稳定结论。",
        "source/linuxdo": "内容来自 Linux.do 社区证据。",
        "knowledge/workflow": "AI coding 工作流、skills、spec、vibecoding。",
        "knowledge/api-relay": "API 中转、网关、公益站、模型路由服务。",
        "knowledge/agent-cli": "Agent CLI、IDE、编辑器入口。",
        "knowledge/multi-agent": "多 agent、subagent、角色和并行编排。",
        "knowledge/context-memory": "MCP、Memory、RAG、Obsidian、上下文管理。",
        "knowledge/models": "模型选择、路由和渠道体感。",
        "knowledge/github-verification": "需要去 GitHub 验证维护、安全、issue、release 的候选。",
        "review/source-triage": "资料整理复核入口。",
        "review/source-reread": "需要回原文复核的来源队列。",
    }
    lines = []
    for tag, count in sorted(tags.items()):
        lines.append(f"- `#{tag}`（{count} 页）：{meanings.get(tag, '当前由导入或整理流程产生的辅助标签。')}")
    return "\n".join(lines) or "- 当前没有 tags。"


def _directory_guide(pages: list[dict[str, Any]]) -> str:
    directory_meanings = {
        "00_Home": "人的第一入口。只负责告诉你今天从哪里读。",
        "10_Catalog/categories": "主题入口。先判断你关心哪一类。",
        "10_Catalog/comparisons": "选择入口。适合在多个方案之间比较。",
        "10_Catalog/resources": "具体资源。适合某个工具、repo、skill、plugin 被点名后再看。",
        "10_Catalog/services": "高时效服务。适合看中转、网关、公益服务和稳定性风险。",
        "10_Catalog/collections": "集合入口。适合承接公益站列表、资源合集这类不能当作单一资源的内容。",
        "10_Catalog/candidates": "临时候选。只放证据不足、对象边界不清或迁移跳转页。",
        "10_Catalog/archive": "历史归档。通常不用读，除非追旧链接。",
        "10_Catalog/archive/moved-candidates": "旧候选跳转页。主要防止链接断裂，通常不用读。",
        "10_Catalog/workflows": "可执行流程。适合要把方法落地时看。",
        "20_Knowledge/components": "局部能力。适合看澄清、计划、验证、恢复等可横向比较的能力。",
        "20_Knowledge/concepts": "概念解释。适合看 Vibe Coding、上下文工程、harness engineering 等概念边界。",
        "20_Knowledge/claims": "判断和争议。适合看某个结论目前站不站得住。",
        "20_Knowledge/drafts": "草稿知识。可以读，但不要当最终结论。",
        "30_Feedback/decisions": "你的采用/拒绝/观察决策，会反哺下一轮冲浪。",
        "30_Feedback/preferences": "你的偏好，会影响后续筛选。",
        "30_Feedback/rejections": "低价值和拒绝规则。用于告诉 agent 少看什么。",
        "90_Inbox/review-queue": "待复核入口。准备采用或发现矛盾时从这里回原文。",
        ".": "Vault 根目录规则文件，给 agent 看。",
    }
    counts: Counter[str] = Counter()
    for page in pages:
        rel = page["relative_path"]
        directory = str(Path(rel).parent)
        counts[directory] += 1
    lines = []
    for directory, count in sorted(counts.items()):
        meaning = directory_meanings.get(directory, "辅助页面目录。")
        lines.append(f"- `{directory}`（{count} 页）：{meaning}")
    lines.append("- `_system/`（不在逐页清单中）：来源和证据底账，主要给 agent 查证据。")
    lines.append("- `90_Inbox/sessions/`（不在逐页清单中）：会话日志，通常不需要人读。")
    return "\n".join(lines)


def _page_guide(pages: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        directory = str(Path(page["relative_path"]).parent)
        grouped.setdefault(directory, []).append(page)

    parts: list[str] = []
    for directory in sorted(grouped):
        directory_pages = grouped[directory]
        common_type = _common_value([page.get("type") or "无 type" for page in directory_pages])
        common_status = _common_value([page.get("status") or "无 status" for page in directory_pages])
        common_tags = _common_tags(directory_pages)
        default_action = _directory_reading_action(directory, common_type, common_status)
        parts.append(f"### {directory}\n")
        parts.append(f"共 {len(directory_pages)} 页。")
        parts.append(f"路径前缀：`{directory}`。")
        if common_tags:
            parts.append("默认标签：" + ", ".join(f"#{tag}" for tag in common_tags) + "。")
        if common_type or common_status:
            parts.append(f"默认类型/状态：`{common_type or '混合'}` / `{common_status or '混合'}`。")
        parts.append(f"默认读法：{default_action}")
        parts.append("")
        for page in directory_pages:
            type_text = page.get("type") or "无 type"
            status_text = page.get("status") or "无 status"
            tags = _as_list(page.get("tags"))
            notes: list[str] = []
            if common_type and type_text != common_type:
                notes.append(f"type `{type_text}`")
            if common_status and status_text != common_status:
                notes.append(f"status `{status_text}`")
            if common_tags and tags != common_tags:
                notes.append("tags " + ", ".join(f"#{tag}" for tag in tags) if tags else "无 tag")
            if not common_tags and tags:
                notes.append("tags " + ", ".join(f"#{tag}" for tag in tags))
            action = _page_reading_action(page["relative_path"], type_text, status_text)
            if action != default_action:
                notes.append(action)
            suffix = f"：{'；'.join(notes)}" if notes else ""
            parts.append(f"- [[{Path(page['relative_path']).stem}|{page['title']}]]{suffix}")
        parts.append("")
    return "\n".join(parts).strip()


def _common_value(values: list[str]) -> str:
    unique = {value for value in values if value}
    return next(iter(unique)) if len(unique) == 1 else ""


def _common_tags(pages: list[dict[str, Any]]) -> list[str]:
    tag_sets = [_as_list(page.get("tags")) for page in pages]
    if not tag_sets:
        return []
    first = tag_sets[0]
    return first if all(tags == first for tags in tag_sets) else []


def _directory_reading_action(directory: str, page_type: str, status: str) -> str:
    directory_actions = {
        ".": "规则页，主要给 agent 看；人只在调整知识库规则时读。",
        "00_Home": "入口页，迷路时从这里回到主路线。",
        "10_Catalog/resources": "只在这个资源被点名、想试、或对比页跳过来时看。",
        "10_Catalog/services": "准备接入或比较中转/网关/公益服务前看。",
        "10_Catalog/collections": "当导航入口看，不把集合页当采用建议。",
        "10_Catalog/candidates": "临时入口，重点看它是不是应该迁移、合并或补证据。",
        "10_Catalog/categories": "看这个主题的边界、推荐先看入口和代表来源。",
        "10_Catalog/comparisons": "在几个方案之间犹豫时看，重点读各派意见、评价维度、待验证。",
        "10_Catalog/workflows": "准备落地某套 workflow 时读。",
        "20_Knowledge/components": "看局部能力的边界和相关对比。",
        "20_Knowledge/concepts": "看概念边界、常见误读和相关实践。",
        "20_Knowledge/claims": "看一个判断是否有争议，重点读支持证据和待验证。",
        "20_Knowledge/drafts": "当作草稿读，不要直接当稳定知识。",
        "30_Feedback/decisions": "这是你的偏好和决策，会影响下一轮 agent 筛选。",
        "30_Feedback/preferences": "这是你的偏好和决策，会影响下一轮 agent 筛选。",
        "30_Feedback/rejections": "这是你的排除规则，会影响下一轮 agent 降权和跳过。",
        "10_Catalog/archive": "历史归档，通常不用人读。",
        "10_Catalog/archive/moved-candidates": "旧候选跳转页，通常不用人读。",
        "90_Inbox/review-queue": "准备采用或更新结论前看，用来决定是否回原文复核。",
    }
    if directory in directory_actions:
        return directory_actions[directory]
    if status == "candidate":
        return "候选状态，按需点开。"
    if page_type == "guide":
        return "导览页，按需读。"
    return "按需阅读。"


def _page_reading_action(relative_path: str, page_type: str, status: str) -> str:
    if relative_path == "00_Home/index.md":
        return "每次进 Vault 先看，用它跳到导读、分类或复核队列。"
    if relative_path.endswith("怎么读这个知识库.md"):
        return "第一次使用或迷路时看，建立最短阅读路线。"
    if relative_path.endswith("全库带读手册.md"):
        return "需要理解每个标签、字段、目录和页面时看。"
    if "categories/分类总览" in relative_path:
        return "决定今天进入哪个主题。"
    if "categories/资源类型地图" in relative_path:
        return "只想找工具、模型、插件、repo 时先看。"
    if "/categories/" in relative_path:
        return "看这个主题的边界、推荐先看入口和代表来源。"
    if "/comparisons/" in relative_path:
        return "在几个方案之间犹豫时看，重点读各派意见、评价维度、待验证。"
    if "/resources/" in relative_path:
        return "只在这个资源被点名、想试、或对比页跳过来时看。"
    if "/services/" in relative_path:
        return "准备接入或比较中转/网关/公益服务前看。"
    if "/collections/" in relative_path:
        return "当导航入口看，不把集合页当采用建议。"
    if "/candidates/" in relative_path:
        return "临时入口，重点看它是不是应该迁移、合并或补证据。"
    if "/workflows/" in relative_path:
        return "准备落地某套 workflow 时读。"
    if "/components/" in relative_path:
        return "看局部能力的边界和相关对比。"
    if "/concepts/" in relative_path:
        return "看概念边界、常见误读和相关实践。"
    if "/review-queue/" in relative_path:
        return "准备采用或更新结论前看，用来决定是否回原文复核。"
    if "/claims/" in relative_path:
        return "看一个判断是否有争议，重点读支持证据和待验证。"
    if "/drafts/" in relative_path:
        return "当作草稿读，不要直接当稳定知识。"
    if "/decisions/" in relative_path or "/preferences/" in relative_path:
        return "这是你的偏好和决策，会影响下一轮 agent 筛选。"
    if status == "candidate":
        return "候选状态，适合观察或补证据，不宜直接当最终推荐。"
    if page_type == "guide":
        return "导览页，帮助你减少无效阅读。"
    return "按需阅读；如果看不出用途，可在 `## 我的反馈` 写“这页需要重整”。"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _source_line(item: dict[str, Any]) -> str:
    title = _clean_human_text(str(item.get("title") or "未命名来源")) or "未命名来源"
    url = str(item.get("url") or "")
    summary = _clip(_clean_human_text(str(item.get("summary") or "")), 110)
    if url:
        return f"[{title}]({url})：{summary}"
    return f"{title}：{summary}"


def _collect_notes(items: list[dict[str, Any]], key: str, limit: int) -> list[str]:
    notes: list[str] = []
    for item in items:
        values = item.get(key, [])
        if isinstance(values, str):
            values = [values]
        for value in values or []:
            text = str(value).strip()
            text = _clean_human_text(text)
            if text and text not in notes:
                notes.append(text)
            if len(notes) >= limit:
                return notes
    return notes


def _opinion_lines(positives: list[str], negatives: list[str], comparisons: list[str]) -> str:
    sections = []
    if positives:
        sections.append("正向信号：\n" + "\n".join(f"- {item}" for item in positives))
    if negatives:
        sections.append("负向信号：\n" + "\n".join(f"- {item}" for item in negatives))
    if comparisons:
        sections.append("对比线索：\n" + "\n".join(f"- {item}" for item in comparisons))
    return "\n\n".join(sections) or "当前累计资料还没有形成清晰分歧。"


def _why_for(category_key: str, positives: list[str], negatives: list[str], comparisons: list[str], risks: list[str]) -> str:
    signals: list[str] = []
    if positives:
        signals.append("已有正向体验，但需要看任务场景是否一致。")
    if negatives:
        signals.append("已有负向反馈，不能只按热门程度采用。")
    if comparisons:
        signals.append("已有对比线索，适合进入 scoped comparison，而不是在分类页直接下结论。")
    if risks:
        signals.append("存在风险或过时信号，准备采用前要回来源复核。")
    if not signals:
        signals.append("目前证据更像入口排序，不足以支撑推荐结论。")
    category_notes = {
        "ai_coding_workflow": "工作流的收益取决于任务重量、澄清成本和验证闭环。",
        "agent_cli_ide": "CLI/IDE 的体验强依赖模型、上下文、插件和本机环境。",
        "multi_agent": "多 Agent 的价值来自边界和验收，不来自角色数量。",
        "api_relay": "API 中转和公益服务变化快，来源时效比历史热度更重要。",
        "context_memory_mcp": "上下文和记忆工具要看是否真的减少重复阅读，而不是只增加上下文负担。",
        "models_routing": "模型评价会快速过时，适合做路由线索，不适合沉淀成长期结论。",
        "github_verification": "论坛推荐只能算线索，最终要看维护、issue、权限和 release。",
    }
    signals.append(category_notes.get(category_key, "采用前需要把证据、场景和反方放在一起看。"))
    return "\n".join(f"- {item}" for item in signals)


def _not_suitable_for(category_key: str) -> str:
    defaults = [
        "不适合只凭热门程度或单帖推荐直接采用。",
        "不适合把不同层级的对象混在一起下结论。",
        "不适合在缺少维护状态、失败反馈和替代方案时进入稳定推荐。",
    ]
    category_notes = {
        "api_relay": "不适合高敏代码、商业密钥或无法接受服务波动的生产任务。",
        "models_routing": "不适合把过期模型体验当作长期固定结论。",
        "multi_agent": "不适合边界、权限和验收都不清楚时增加 agent 数量。",
        "context_memory_mcp": "不适合为了工具数量而增加常驻权限和上下文负担。",
        "ai_coding_workflow": "不适合小而清楚的任务直接套重流程。",
    }
    lines = defaults + ([category_notes[category_key]] if category_key in category_notes else [])
    return "\n".join(f"- {item}" for item in lines)


def _criteria_for(category_key: str) -> str:
    criteria = {
        "ai_coding_workflow": ["任务复杂度", "澄清质量", "token 成本", "验证闭环", "是否能被你稳定执行"],
        "agent_cli_ide": ["上下文可用长度", "规则遵从", "恢复能力", "成本", "插件/终端/文件体验"],
        "multi_agent": ["边界清晰度", "并行收益", "冲突处理", "验收机制", "失败后恢复"],
        "api_relay": ["稳定性", "透明度", "安全性", "价格", "模型是否缩水", "退款和失效风险"],
        "context_memory_mcp": ["是否减少重复阅读", "权限范围", "维护成本", "检索准确度", "上下文污染"],
        "models_routing": ["任务匹配", "真实上下文", "速度", "价格", "渠道差异", "最近反馈"],
        "github_verification": ["最近维护", "issue 质量", "release 节奏", "权限范围", "安装可逆性"],
    }
    return "\n".join(f"- {item}" for item in criteria.get(category_key, ["价值", "风险", "成本", "可验证性"]))


def _review_reasons(item: dict[str, Any], category_key: str) -> list[str]:
    reasons: list[str] = []
    if category_key in {"api_relay", "models_routing"}:
        reasons.append("变化快，采用前需要确认最新状态")
    if item.get("comparison_notes") and (item.get("positive_feedback") or item.get("negative_feedback")):
        reasons.append("存在对比或争议，需要还原上下文")
    if item.get("github_repos") or category_key == "github_verification":
        reasons.append("涉及项目来源，需要验证维护和权限")
    if item.get("visual_evidence_needed") and not item.get("render_checked"):
        reasons.append("视觉或教程证据未完整核验")
    if str(item.get("value_tag", "")).lower() in {"high", "马上试"} and category_key in {"ai_coding_workflow", "multi_agent", "context_memory_mcp"}:
        reasons.append("高价值实践，整理成知识前值得补足证据")
    return reasons


def _review_weight(item: dict[str, Any]) -> int:
    return _reading_weight(item) + 3 * len(set(item.get("_review_reasons", [])))


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    sentence_end = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind(";"))
    if sentence_end >= max(30, limit // 2):
        clipped = clipped[: sentence_end + 1]
    return clipped.rstrip(" ，。；;") + "。"


def _clean_human_text(text: str) -> str:
    replacements = {
        "高相关。": "",
        "高相关；": "",
        "高相关": "",
        "中等相关。": "",
        "中等相关；": "",
        "中等相关": "",
        "候选资源，当前记录显示它被多次提及": "待观察资源线索，当前证据只够说明它被讨论过",
        "是否值得采用要看来源证据、维护状态和反方反馈": "采用前需要复核来源、维护状态和反方反馈",
        "暂无足够可复用证据": "当前没有能支撑判断的可复用来源",
        "来源证据": "来源",
        "累计权重": "讨论信号",
        "证据权重": "讨论信号",
        "风佬巨作": "社区项目线索",
        "zcf": "相关项目",
        "v5.0": "对应版本",
        "……": "（标题省略）",
        "…": "（标题省略）",
        "...": "（标题省略）",
        "旧记录": "累计资料",
        "旧帖": "已读来源",
        "旧冲浪": "累计冲浪",
        "legacy": "source",
        "Legacy": "Source",
        "legacy_summary": "needs_source_review",
        "Batch": "阅读记录",
        "batch": "session",
        "本批": "这组资料",
    }
    result = text
    for source, target in replacements.items():
        result = result.replace(source, target)
    result = re.sub(r"第\s*[0-9]+\s*批", "累计资料", result)
    return result


def _unique_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

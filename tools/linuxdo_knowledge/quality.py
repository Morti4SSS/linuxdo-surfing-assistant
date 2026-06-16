from __future__ import annotations

from dataclasses import dataclass
import re

from .aliases import canonicalize_name


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    page_name: str


BANNED_PHRASES = ("高相关", "中等相关", "累计权重", "证据权重", "legacy_summary", "旧帖", "旧记录", "旧冲浪")
OPAQUE_TERMS = ("风佬巨作", "zcf", "v5.0")
ELLIPSIS_PATTERN = re.compile(r"(?:\.\.\.|…)\s*(?:$|\n)")

PAGE_REQUIRED_SECTIONS = {
    "resource": ("一句话判断", "它是什么", "适合什么", "不适合什么", "当前结论", "关键证据", "反方与风险", "相关竞品", "待验证", "来源"),
    "service": (
        "一句话判断",
        "它是什么",
        "适合什么",
        "不适合什么",
        "稳定性",
        "隐私/安全风险",
        "价格/额度变化风险",
        "当前结论",
        "关键证据",
        "反方与风险",
        "相关竞品",
        "待验证",
        "来源",
    ),
    "workflow": ("一句话判断", "它是什么", "适合什么", "不适合什么", "当前结论", "核心步骤", "关键证据", "反方与风险", "相关对比", "待验证", "来源"),
    "concept": ("一句话判断", "概念边界", "常见误读", "适合沉淀什么", "不适合沉淀什么", "关键证据", "相关页面", "待验证", "来源"),
    "component": ("一句话判断", "触发条件", "停止条件", "适合什么", "不适合什么", "关键证据", "相关对比", "待验证", "来源"),
    "comparison": ("当前结论", "比较范围", "评价维度", "各派意见", "适合选择", "不适合选择", "证据与来源", "待验证"),
    "collection": ("一句话判断", "收录范围", "不收录什么", "阅读顺序", "代表页面", "风险", "来源"),
}

TEMPLATE_RESIDUE_PHRASES = (
    "候选资源，当前记录显示它被多次提及",
    "是否值得采用要看来源证据、维护状态和反方反馈",
    "暂无足够可复用证据",
)

BROAD_COLLECTIONS = {"公益站", "中转站", "API 中转", "API-中转", "第三方 API", "third-party-api"}
SERVICES = {
    "anyrouter",
    "cc-switch",
    "cliproxyapi",
    "cpa",
    "cpamc",
    "gpt-load",
    "new-api",
    "oneapi",
    "openrouter",
    "sub2api",
}
WORKFLOWS = {
    "agent-skills",
    "bmad",
    "ccg",
    "ccw",
    "claude-code-workflow",
    "codestable",
    "maestro-flow",
    "missions",
    "openspec",
    "superpowers",
    "trellis",
}
CONCEPTS = {
    "agents.md",
    "claude.md",
    "context-engineering",
    "harness",
    "harness-engineering",
    "memory",
    "multi-agent",
    "rag",
    "skill-based-architecture",
    "skill.md",
    "spec",
    "subagent",
    "subagents",
    "tdd",
    "vibecoding",
}
COMPONENTS = {
    "brainstorming",
    "grill-me",
    "plan-mode",
    "skill-creator",
    "verification",
}


def lint_human_markdown(text: str, *, page_name: str = "") -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    lint_text = _strip_frontmatter(text)
    for phrase in BANNED_PHRASES:
        if phrase in lint_text:
            issues.append(QualityIssue("banned_phrase", f"包含旧噪音词：{phrase}", page_name))
    if ELLIPSIS_PATTERN.search(lint_text):
        issues.append(QualityIssue("trailing_ellipsis", "包含省略号结尾的摘要", page_name))
    for term in OPAQUE_TERMS:
        if term in lint_text and not _is_page_own_short_name(term, page_name):
            issues.append(QualityIssue("opaque_term", f"包含无上下文黑话：{term}", page_name))
    for phrase in TEMPLATE_RESIDUE_PHRASES:
        if phrase in lint_text:
            issues.append(QualityIssue("template_residue", f"包含模板残留：{phrase}", page_name))
    return issues


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    return text[end + 4 :]


def required_sections_for_page_type(page_type: str) -> tuple[str, ...]:
    return PAGE_REQUIRED_SECTIONS.get(page_type, ())


def _is_page_own_short_name(term: str, page_name: str) -> bool:
    stem = str(page_name).rsplit("/", 1)[-1].removesuffix(".md").lower()
    return stem == term.lower()


def normalize_resource_name(name: str) -> tuple[str, str]:
    display = " ".join(canonicalize_name(str(name)).split())
    key = display.lower().replace("_", "-")
    key = key.replace("/", "-")
    key = " ".join(key.split())
    slug_key = key.replace(" ", "-")
    return slug_key, display


def classify_knowledge_object(name: str) -> str:
    key, display = normalize_resource_name(name)
    if "路由" in display or key.endswith("-workflow") or "-workflow-" in key:
        return "workflow"
    if key in {item.lower() for item in BROAD_COLLECTIONS} or display in BROAD_COLLECTIONS:
        return "collection"
    if key in SERVICES:
        return "service"
    if key in WORKFLOWS:
        return "workflow"
    if key in CONCEPTS:
        return "concept"
    if key in COMPONENTS:
        return "component"
    return "resource"

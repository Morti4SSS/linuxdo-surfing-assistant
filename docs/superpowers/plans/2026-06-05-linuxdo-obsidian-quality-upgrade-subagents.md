# Linux.do Obsidian Quality Upgrade Subagents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Linux.do / GitHub Obsidian vault from a migrated reading archive into a source-grounded, readable, token-efficient knowledge system.

**Architecture:** Treat this as a coordinated quality upgrade with independent work streams: automated audit gates, schema enforcement, context packing, source/evidence refresh queues, and human-facing content rewrite batches. Keep machine persistence in `/Users/mortisss/Documents/linuxdo/state/knowledge/` and keep human reading pages in `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/`; never require an agent to read the whole vault to understand user feedback.

**Tech Stack:** Python standard library, `unittest`, existing `tools/linuxdo_knowledge/*` modules, `tools/linuxdo_surf.py` CLI, Obsidian Markdown, YAML-like frontmatter, Linux.do in-app browser/Chrome fallback for source verification.

---

## Quality Directions

These are the directions this plan covers. They are intentionally separated so multiple Codex threads can work in parallel without stepping on each other.

1. **Object boundary quality:** distinguish resource, service, workflow, concept, component, collection, source topic, and evidence.
2. **Alias and duplicate control:** merge `Vibe-Coding` / `Vibecoding`, `ccswitch` / `CC-Switch`, repo slug pages and display-name pages when they point to the same object.
3. **Human-facing schema quality:** every page type needs stable sections; generated template residue must not masquerade as knowledge.
4. **Evidence quality:** source pages should be canonical; resource/comparison pages should cite evidence without copying long old summaries everywhere.
5. **Comparison quality:** compare functionally similar things, not full workflows against tiny components.
6. **Content depth:** pages must explain the actual experience, tradeoffs, opposition, and adoption triggers, not just “mentioned often”.
7. **Token efficiency:** build context packs from hot indexes, watchlist, changed feedback, and targeted pages instead of loading large historical files or the whole vault.
8. **Update handling:** old topics are not polled blindly; they enter a refresh queue when watchlist, bookmark, human feedback, new reply count, or repeated rediscovery suggests value.
9. **Feedback loop quality:** user edits, `watchlist`, status, rejection, and adoption decisions should affect the next surf task through compact machine state.
10. **Source verification policy:** if live Linux.do reading fails, stop and report the exact URL and failed method; do not silently use stale extracts as if they are fresh.
11. **Vault navigation quality:** human entry pages should be simple reading surfaces; `_system/` and session logs should be agent evidence底账, not required daily reading.
12. **Automation gates:** add repeatable scans for banned phrases, truncation, generic templates, misplaced page types, broken links, missing evidence, and stale high-risk services.

## File Map

Repository files under `/Users/mortisss/Documents/linuxdo`:

- `tools/linuxdo_knowledge/quality.py`: existing quality lint, aliases, classifier; extend with page lint and evidence checks.
- `tools/linuxdo_knowledge/quality_audit.py`: new audit module that scans vault pages and emits JSON/Markdown reports.
- `tools/linuxdo_knowledge/context_pack.py`: new compact context builder for future surf tasks.
- `tools/linuxdo_knowledge/session.py`: new-session write path; enforce schemas and preserve `## 我的反馈`.
- `tools/linuxdo_knowledge/rewrite_needed.py`: legacy/source-extract rewrite path; stop producing confident pages from weak evidence.
- `tools/linuxdo_knowledge/second_pass.py`: guide/category/comparison generator; reduce noisy explanatory pages and enforce updated labels.
- `tools/linuxdo_knowledge/structure.py`: page relocation and duplicate repair.
- `tools/linuxdo_knowledge/state.py`: hot indexes and refresh queues.
- `tools/linuxdo_surf.py`: CLI entrypoints for audit, context pack, and refresh queue commands.
- `tests/test_linuxdo_knowledge.py`: unit tests for all knowledge tooling.
- `SKILL.md`: Linux.do surfing skill; update source-reading and refresh policy after code behavior exists.
- `references/linuxdo-reading-playbook.md`: reading levels and browser fallback rules.
- `docs/superpowers/specs/2026-06-05-linuxdo-obsidian-knowledge-quality-rules-design.md`: keep as design source; update only if behavior changes.

Vault files under `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge`:

- `00_Home/index.md`, `00_Home/hot.md`, `00_Home/怎么读这个知识库.md`: human entry and reading path.
- `10_Catalog/resources/*.md`: concrete tools, repos, apps, model clients, plugins.
- `10_Catalog/services/*.md`: API relay, public/free stations, gateways, routing services.
- `10_Catalog/workflows/*.md`: complete workflows and method bundles.
- `10_Catalog/comparisons/*.md`: scoped comparisons.
- `10_Catalog/collections/*.md`: broad collections such as API 中转 and 公益站.
- `20_Knowledge/concepts/*.md`: conceptual explanations.
- `20_Knowledge/components/*.md`: smaller workflow components such as `grill-me` and `Plan-mode`.
- `30_Feedback/**/*.md`: human preference, decision, and rejection inputs.
- `_system/sources/linuxdo/*.md` and `_system/evidence/linuxdo/*.md`: canonical source/evidence records.

## Subagent Operating Rules

Every subagent must follow these rules:

- Work in Chinese.
- Preserve every existing `## 我的反馈` section exactly.
- Do not invent claims from file names, old summaries, or page titles.
- If evidence is insufficient, set `status: needs_source_review` and explain what source is missing.
- Do not leave human-facing phrases like `高相关`, `中等相关`, `累计权重`, `证据权重`, `旧帖`, `旧记录`, `旧冲浪`, `legacy_summary`, `候选资源，当前记录显示它被多次提及`, or省略号结尾.
- Do not rewrite unrelated pages in the same pass.
- If live Linux.do reading fails, stop and report the URL, visible browser state, and method used.
- Run the targeted checks for the task before handing back.

---

### Task 1: Automated Vault Quality Audit

**Purpose:** Build a scanner that tells us which pages still need quality work, so content rewrite threads do not rely on vibes.

**Files:**
- Create: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality_audit.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Output: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/quality_audit_latest.json`

- [ ] **Step 1: Add failing audit tests**

Add these tests to `tests/test_linuxdo_knowledge.py` in the knowledge quality test class:

```python
    def test_quality_audit_flags_template_resource_and_source_evidence_heading(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page

        text = """---
id: resource:demo
type: resource
status: watching
---

# Demo

## 一句话判断

Demo 是候选资源，当前记录显示它被多次提及；是否值得采用要看来源证据、维护状态和反方反馈。

## 来源证据

- 高相关：这是旧摘要...

## 我的反馈
"""
        issues = audit_markdown_page("10_Catalog/resources/Demo.md", text)
        codes = {issue["code"] for issue in issues}

        self.assertIn("template_residue", codes)
        self.assertIn("legacy_heading", codes)
        self.assertIn("banned_phrase", codes)
        self.assertIn("trailing_ellipsis", codes)

    def test_quality_audit_accepts_curated_resource_shape(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page

        text = """---
id: resource:demo
type: resource
status: watching
watchlist: false
---

# Demo

## 一句话判断

Demo 是一个可继续观察的工具；当前只有少量社区体验，采用前需要确认维护状态。

## 它是什么

Demo 解决的是命令行内的任务编排，而不是模型路由或 API 中转。

## 适合什么

- 适合想把重复步骤写成显式流程的人。

## 不适合什么

- 不适合只想临时问答的人。

## 当前结论

先观察，不作为默认推荐。

## 关键证据

- [[linuxdo-topic-1]]：有用户描述了使用场景和限制。

## 反方与风险

- 维护状态需要复核。

## 相关竞品

- [[Other Demo]]

## 待验证

- 下次遇到 GitHub 链接时查 release 和 issue。

## 来源

- [[linuxdo-topic-1]]

## 我的反馈
"""
        self.assertEqual(audit_markdown_page("10_Catalog/resources/Demo.md", text), [])
```

- [ ] **Step 2: Implement `quality_audit.py`**

Implement:

```python
from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from .quality import lint_human_markdown


REQUIRED_SECTIONS = {
    "resource": ["一句话判断", "它是什么", "适合什么", "不适合什么", "当前结论", "关键证据", "反方与风险", "相关竞品", "待验证", "来源"],
    "service": ["一句话判断", "它是什么", "适合什么", "不适合什么", "稳定性", "隐私/安全风险", "价格/额度变化风险", "当前结论", "关键证据", "反方与风险", "相关竞品", "待验证", "来源"],
    "workflow": ["一句话判断", "它是什么", "适合什么", "不适合什么", "当前结论", "核心步骤", "关键证据", "反方与风险", "相关对比", "待验证", "来源"],
    "concept": ["一句话判断", "概念边界", "常见误读", "适合沉淀什么", "不适合沉淀什么", "关键证据", "相关页面", "待验证", "来源"],
    "component": ["一句话判断", "触发条件", "停止条件", "适合什么", "不适合什么", "关键证据", "相关对比", "待验证", "来源"],
    "comparison": ["当前结论", "比较范围", "评价维度", "各派意见", "适合选择", "不适合选择", "证据与来源", "待验证"],
}

BAD_SNIPPETS = {
    "template_residue": ["候选资源，当前记录显示它被多次提及", "是否值得采用要看来源证据、维护状态和反方反馈"],
    "legacy_heading": ["## 来源证据"],
}


def audit_markdown_page(relative_path: str, text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    page_type = _frontmatter_value(text, "type")
    for issue in lint_human_markdown(text, page_name=relative_path):
        issues.append({"path": relative_path, "code": issue.code, "message": issue.message})
    for code, snippets in BAD_SNIPPETS.items():
        for snippet in snippets:
            if snippet in text:
                issues.append({"path": relative_path, "code": code, "message": f"包含残留文本：{snippet}"})
    required = REQUIRED_SECTIONS.get(page_type, [])
    headings = set(re.findall(r"^##\\s+(.+?)\\s*$", text, flags=re.MULTILINE))
    for heading in required:
        if heading not in headings:
            issues.append({"path": relative_path, "code": "missing_section", "message": f"缺少章节：{heading}"})
    return issues


def audit_vault(vault_path: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    for path in sorted(vault_path.rglob("*.md")):
        relative = path.relative_to(vault_path).as_posix()
        if relative.startswith(".obsidian/"):
            continue
        text = path.read_text(encoding="utf-8")
        issues.extend(audit_markdown_page(relative, text))
    return {"pages_scanned": len(list(vault_path.rglob("*.md"))), "issues": issues}


def write_audit_report(vault_path: Path, output_path: Path) -> Path:
    report = audit_vault(vault_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---\\n"):
        return ""
    end = text.find("\\n---", 4)
    if end == -1:
        return ""
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        found_key, value = line.split(":", 1)
        if found_key.strip() == key:
            return value.strip().strip("'\\\"")
    return ""
```

- [ ] **Step 3: Add CLI command**

Add `knowledge-audit` to `tools/linuxdo_surf.py`:

```python
def run_knowledge_audit(args: argparse.Namespace) -> int:
    from tools.linuxdo_knowledge.quality_audit import write_audit_report

    config = load_config(args.config)
    path = write_audit_report(config.obsidian_vault_path, args.output)
    print(f"wrote {path}")
    return 0
```

Register parser:

```python
    knowledge_audit = subparsers.add_parser("knowledge-audit", help="扫描 Obsidian vault 的人读质量问题。")
    knowledge_audit.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_audit.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/quality_audit_latest.json"))
    knowledge_audit.set_defaults(func=run_knowledge_audit)
```

- [ ] **Step 4: Run tests and audit**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_latest.json
```

Expected: unit tests pass; audit JSON exists and lists current vault issues.

**给子线程的中文提示词：**

```text
你负责“质量审计”这一块。请在 /Users/mortisss/Documents/linuxdo 中实现任务一：自动扫描 Obsidian 知识库的人读质量问题。只改 tools/linuxdo_knowledge/quality_audit.py、tools/linuxdo_surf.py、tests/test_linuxdo_knowledge.py。目标是生成可复跑的 knowledge-audit 命令，用于扫描 /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge 里的人读页面质量问题。保留中文输出，保留已有测试风格，完成后运行计划里的两个命令，并汇报问题数量最多的前十类。
```

---

### Task 2: Page Schema and Lint Gates

**Purpose:** Turn user-facing quality expectations into enforceable page schemas and lint rules.

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality_audit.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add tests for page type schemas**

Add tests:

```python
    def test_quality_required_sections_by_page_type_are_distinct(self):
        from tools.linuxdo_knowledge.quality import required_sections_for_page_type

        self.assertIn("隐私/安全风险", required_sections_for_page_type("service"))
        self.assertIn("核心步骤", required_sections_for_page_type("workflow"))
        self.assertIn("概念边界", required_sections_for_page_type("concept"))
        self.assertIn("触发条件", required_sections_for_page_type("component"))
        self.assertIn("比较范围", required_sections_for_page_type("comparison"))
        self.assertNotIn("隐私/安全风险", required_sections_for_page_type("resource"))

    def test_quality_lint_flags_generic_template_sentences(self):
        from tools.linuxdo_knowledge.quality import lint_human_markdown

        issues = lint_human_markdown("Demo 是候选资源，当前记录显示它被多次提及。", page_name="Demo")

        self.assertIn("template_residue", {issue.code for issue in issues})
```

- [ ] **Step 2: Move schema constants into `quality.py`**

Add:

```python
PAGE_REQUIRED_SECTIONS = {
    "resource": ("一句话判断", "它是什么", "适合什么", "不适合什么", "当前结论", "关键证据", "反方与风险", "相关竞品", "待验证", "来源"),
    "service": ("一句话判断", "它是什么", "适合什么", "不适合什么", "稳定性", "隐私/安全风险", "价格/额度变化风险", "当前结论", "关键证据", "反方与风险", "相关竞品", "待验证", "来源"),
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


def required_sections_for_page_type(page_type: str) -> tuple[str, ...]:
    return PAGE_REQUIRED_SECTIONS.get(page_type, ())
```

Extend `lint_human_markdown()` so it emits `QualityIssue("template_residue", ...)` for `TEMPLATE_RESIDUE_PHRASES`.

- [ ] **Step 3: Wire audit to shared schemas**

Update `quality_audit.py` to import `required_sections_for_page_type()` instead of duplicating schema constants.

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“页面结构和规则检查”这一块。请实现任务二：把各类页面必须包含的章节、模板残留检查、旧摘要噪音检查沉淀到 tools/linuxdo_knowledge/quality.py，并让 tools/linuxdo_knowledge/quality_audit.py 复用这些规则。不要修改 Obsidian 知识库内容。完成后运行 KnowledgeQualityRulesTests，并汇报新增规则能抓住哪些用户之前提到的问题。
```

---

### Task 3: Compact Context Pack for Token Saving

**Purpose:** Let future surf tasks read only compact state: watchlist, changed feedback, hot resources, refresh queue, and focused page summaries.

**Files:**
- Create: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/context_pack.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Output: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/context_pack_latest.json`

- [ ] **Step 1: Add tests for compact pack**

Add:

```python
    def test_context_pack_uses_hot_indexes_and_changed_feedback_only(self):
        from tools.linuxdo_knowledge.context_pack import build_context_pack
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(config, "resource_index", {"resources": {"superpowers": {"title": "Superpowers", "status": "watching", "watchlist": True}}})
            save_hot_index(config, "topic_update_state", {"topics": {"2151853": {"title": "Superpowers 讨论", "reply_count": 32, "read_reply_count": 17}}})
            save_hot_index(config, "user_feedback", {"items": [{"id": "resource:superpowers", "summary": "偏好轻量，不默认重流程。"}]})

            pack = build_context_pack(config, focus="superpowers", limit=20)

        self.assertEqual(pack["focus"], "superpowers")
        self.assertEqual(pack["watchlist"][0]["title"], "Superpowers")
        self.assertEqual(pack["topic_updates"][0]["unread_replies"], 15)
        self.assertIn("偏好轻量", pack["feedback"][0]["summary"])
```

- [ ] **Step 2: Implement `context_pack.py`**

Implement:

```python
from __future__ import annotations

from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes


def build_context_pack(config: KnowledgeConfig, *, focus: str = "", limit: int = 40) -> dict[str, Any]:
    indexes = load_hot_indexes(config)
    resources = list(indexes.get("resource_index", {}).get("resources", {}).values())
    topics = list(indexes.get("topic_update_state", {}).get("topics", {}).values())
    feedback = list(indexes.get("user_feedback", {}).get("items", []))
    watchlist = [item for item in resources if item.get("watchlist") or item.get("status") in {"watching", "adopted"}]
    topic_updates = []
    for item in topics:
        reply_count = int(item.get("reply_count") or 0)
        read_reply_count = int(item.get("read_reply_count") or item.get("highest_post_number") or 0)
        unread = max(0, reply_count - read_reply_count)
        if unread:
            topic_updates.append({**item, "unread_replies": unread})
    return {
        "focus": focus,
        "watchlist": _filter_limit(watchlist, focus, limit),
        "topic_updates": _filter_limit(sorted(topic_updates, key=lambda item: -int(item.get("unread_replies", 0))), focus, limit),
        "feedback": _filter_limit(feedback, focus, limit),
    }


def _filter_limit(items: list[dict[str, Any]], focus: str, limit: int) -> list[dict[str, Any]]:
    if focus:
        needle = focus.lower()
        focused = [item for item in items if needle in str(item).lower()]
        if focused:
            return focused[:limit]
    return items[:limit]
```

- [ ] **Step 3: Add CLI command**

Add `knowledge-context-pack` to `tools/linuxdo_surf.py` with args:

```python
--config config/knowledge_sources.json
--focus ""
--limit 40
--output output/linuxdo_surf/context_pack_latest.json
```

The command writes JSON using `json.dumps(..., ensure_ascii=False, indent=2)`.

- [ ] **Step 4: Run tests and sample pack**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests.test_context_pack_uses_hot_indexes_and_changed_feedback_only
python3 tools/linuxdo_surf.py knowledge-context-pack --config config/knowledge_sources.json --focus superpowers --output output/linuxdo_surf/context_pack_latest.json
```

Expected: test passes; output JSON is compact and does not include full `readings_all.json`.

**给子线程的中文提示词：**

```text
你负责“节省 token 的轻量上下文包”这一块。请实现任务三：给下一次 Linux.do 冲浪任务生成轻量上下文包，只从 hot indexes、watchlist、topic_update_state、user_feedback 取信息，绝不读取 readings_all.json。完成后运行计划里的测试和命令行示例，并说明这个轻量上下文包后续应该在冲浪前怎么用。
```

---

### Task 4: Generator Integration and Regression Gates

**Purpose:** Stop new sessions, legacy rewrites, and organize commands from reintroducing low-quality template pages.

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/session.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/rewrite_needed.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/legacy.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add regression test for generated pages**

Add:

```python
    def test_generated_human_pages_pass_quality_audit(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page
        from tools.linuxdo_knowledge.obsidian import write_page

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            path = config.obsidian_vault_path / "10_Catalog" / "resources" / "Demo.md"
            write_page(
                path,
                {"id": "resource:demo", "type": "resource", "status": "watching", "watchlist": False},
                "Demo",
                [
                    ("一句话判断", "Demo 是一个待观察工具；当前证据只够说明它被讨论过。"),
                    ("它是什么", "Demo 是具体工具，不是概念集合。"),
                    ("适合什么", "- 适合有明确使用场景的人。"),
                    ("不适合什么", "- 不适合直接作为默认方案。"),
                    ("当前结论", "先观察。"),
                    ("关键证据", "- [[linuxdo-topic-1]]：有具体使用反馈。"),
                    ("反方与风险", "- 维护状态和安全边界未验证。"),
                    ("相关竞品", "- [[Other Demo]]"),
                    ("待验证", "- 查看项目维护状态。"),
                    ("来源", "- [[linuxdo-topic-1]]"),
                ],
            )

            issues = audit_markdown_page("10_Catalog/resources/Demo.md", path.read_text(encoding="utf-8"))

        self.assertEqual(issues, [])
```

- [ ] **Step 2: Replace generic resource wording**

In `session.py`, `rewrite_needed.py`, and `legacy.py`, replace generic sentence patterns:

```text
是候选资源，当前记录显示它被多次提及
是否值得采用要看来源证据、维护状态和反方反馈
```

with page-type-specific cautious wording from `required_sections_for_page_type()`.

- [ ] **Step 3: Rename old human headings**

Replace human-facing `## 来源证据` with `## 来源` or `## 证据与来源` depending on page type. Keep `_system/evidence/` filenames unchanged because they are internal evidence records.

- [ ] **Step 4: Run regression scans**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/90_Inbox/review-queue -S
```

Expected: tests pass; scan output only appears where a page intentionally documents bad terms as examples in a guide, and those pages should be reviewed manually.

**给子线程的中文提示词：**

```text
你负责“生成器质量门”这一块。请实现任务四：让 session、rewrite_needed、second_pass、legacy 这些生成路径不再写出旧模板句、旧标题、旧摘要噪音。不要大面积重写 Obsidian 知识库，只改生成逻辑和对应测试。完成后运行完整 unittest 和 rg 扫描，列出仍然命中的文件。
```

---

### Task 5: Object Routing, Aliases, and Structure Repair

**Purpose:** Reduce vault confusion by moving misplaced pages, merging aliases, and separating broad collections from concrete resources.

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/structure.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- May modify vault aliases/moved pages under `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/**` and `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/**`

- [ ] **Step 1: Add classifier tests for known confusing objects**

Add:

```python
    def test_quality_classifier_routes_known_confusing_objects(self):
        from tools.linuxdo_knowledge.quality import classify_knowledge_object, normalize_resource_name

        cases = {
            "公益站": "collection",
            "API 中转": "collection",
            "third-party API": "collection",
            "CPA": "service",
            "CLIProxyAPI": "service",
            "OpenRouter": "service",
            "Superpowers": "workflow",
            "Trellis": "workflow",
            "grill-me": "component",
            "Context Engineering": "concept",
            "Vibe-Coding": "concept",
            "Codex CLI": "resource",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_knowledge_object(name), expected)

        self.assertEqual(normalize_resource_name("Vibe-Coding"), ("vibecoding", "Vibecoding"))
        self.assertEqual(normalize_resource_name("CLIProxyAPI"), ("cpa", "CPA"))
```

- [ ] **Step 2: Expand alias map conservatively**

Add only aliases that are already visible in the vault:

```python
"cliproxyapi": ("cpa", "CPA")
"cli proxy api": ("cpa", "CPA")
"vibe-coding": ("vibecoding", "Vibecoding")
"vibe coding": ("vibecoding", "Vibecoding")
"opencode": ("opencode", "OpenCode")
"open code": ("opencode", "OpenCode")
```

- [ ] **Step 3: Run structure repair in dry review style**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-repair-structure --config config/knowledge_sources.json --output output/linuxdo_surf/knowledge_repair_structure_result.json
```

Expected: moved pages are alias pages or correctly routed pages; no curated page loses `## 我的反馈`.

- [ ] **Step 4: Manually inspect moved/alias pages**

Inspect:

```bash
rg -n "canonical:|本页已迁移|本页只是别名入口" /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge -S
```

Expected: aliases point to useful canonical pages and do not contain duplicated evidence.

**给子线程的中文提示词：**

```text
你负责“对象归位和别名合并”这一块。请实现任务五：解决别名、泛类、具体资源混在一起的问题。只添加当前 Obsidian 知识库里已经能确认的别名，不凭感觉扩展。运行 knowledge-repair-structure 后检查别名页和迁移页，不能覆盖任何人的反馈内容。
```

---

### Task 6: Source Refresh Queue and Incremental Update Policy

**Purpose:** Make old topic update handling practical: no全量重读, but important watched or rediscovered topics can trigger targeted refresh.

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/state.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/strategy.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/session.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Modify: `/Users/mortisss/.codex/skills/linuxdo-surfing/SKILL.md`
- Modify: `/Users/mortisss/Documents/linuxdo/references/linuxdo-reading-playbook.md`

- [ ] **Step 1: Add refresh queue test**

Add:

```python
    def test_strategy_prioritizes_watchlist_topic_with_unread_replies(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(config, "topic_update_state", {"topics": {
                "2151853": {
                    "topic_id": 2151853,
                    "title": "Superpowers 讨论",
                    "url": "https://linux.do/t/topic/2151853",
                    "reply_count": 56,
                    "read_reply_count": 32,
                    "watchlist": True,
                    "related_resources": ["superpowers"],
                }
            }})

            task = build_knowledge_task(config, batch_size=1, created_at="2026-06-05T12:00:00+08:00")

        self.assertEqual(task["items"][0]["topic_id"], 2151853)
        self.assertEqual(task["items"][0]["read_level"], 2)
        self.assertIn("unread replies", task["items"][0]["reason"])
```

- [ ] **Step 2: Update strategy behavior**

In `strategy.py`, rank refresh candidates before cold frontier candidates when:

- `watchlist: true`
- `reply_count > read_reply_count`
- user feedback references the resource or topic
- the same topic is rediscovered by search/bookmark/frontier

Set read level:

- Level 1: main post + few high-signal replies + minimal context.
- Level 2: main post + popular/disputed/linked/author replies + dialogue chain context.
- Level 3: deep read most replies for disputes, comparisons, and hands-on reports.

- [ ] **Step 3: Document browser failure policy**

Update skill/playbook:

```text
If Linux.do live reading fails:
1. Try DOM/text extraction in the in-app browser.
2. If login/challenge/state blocks content, try Chrome once when the user has already approved Chrome fallback.
3. If both fail, stop and report URL, visible state, extraction method, and what human action is needed.
4. Do not silently replace live reading with stale source extracts.
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeStrategyTests
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20 --output output/linuxdo_surf/knowledge_task_latest.json
```

Expected: strategy tests pass; generated task can include refresh candidates without loading full history.

**给子线程的中文提示词：**

```text
你负责“旧帖增量更新策略”这一块。请实现任务六：把旧帖更新变成由 watchlist、人工反馈、未读回复、重复发现触发的轻量刷新，而不是全量重读。还要更新 linuxdo-surfing skill 的失败暂停规则：如果实时阅读 Linux.do 出问题，必须停下说明网址、可见状态和失败方法，不能偷偷用旧摘要替代。完成后运行策略测试和 knowledge-plan 示例。
```

---

### Task 7: Content Batch A - Agent CLI and IDE Resource Cards

**Purpose:** Upgrade the highest-impact tool selection pages so they are actually useful to read.

**Files:**
- Modify vault pages:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/OpenCode.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Claude-Code.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Codex-CLI.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/GitHub-Copilot.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Kiro.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/VS-Code.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Windsurf.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Gemini-CLI.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/Agent-CLI-与-IDE-选择.md`
- Read only needed source/evidence files under `_system/` and compact indexes under `state/knowledge/`.

- [ ] **Step 1: Audit target pages**

Run:

```bash
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/OpenCode.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Claude-Code.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Codex-CLI.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/GitHub-Copilot.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Kiro.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/VS-Code.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Windsurf.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Gemini-CLI.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/Agent-CLI-与-IDE-选择.md -S
```

- [ ] **Step 2: Rewrite each resource card**

For each resource page, use this structure:

```md
## 一句话判断

## 它是什么

## 适合什么

## 不适合什么

## 当前结论

## 关键证据

## 反方与风险

## 相关竞品

## 待验证

## 来源

## 我的反馈
```

Rules:

- Write concrete use cases and limitations.
- Link related pages with Obsidian wikilinks.
- If evidence is weak, say what is weak and set `status: needs_source_review`.
- Do not make a recommendation just because a tool is famous or frequently mentioned.

- [ ] **Step 3: Rewrite comparison page**

`Agent-CLI-与-IDE-选择.md` should compare by:

- setup friction
- context handling
- rules/skills support
- recovery/session continuity
- model routing and cost exposure
- IDE integration
- when to choose each
- opposition and unresolved questions

- [ ] **Step 4: Verify batch**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_agent_cli.json
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/OpenCode.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Claude-Code.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Codex-CLI.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/GitHub-Copilot.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Kiro.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/VS-Code.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Windsurf.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/resources/Gemini-CLI.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/Agent-CLI-与-IDE-选择.md -S
```

Expected: no residual bad phrases in the target files.

**给子线程的中文提示词：**

```text
你负责“命令行和编辑器入口资源卡”这一批内容质量。请执行任务七。只重写计划里列出的 8 张资源卡和 1 张“Agent-CLI-与-IDE-选择”对比页。目标不是写长，而是让页面真正能帮助用户选择工具：它是什么、适合什么、不适合什么、反方风险、相关竞品、来源。不要修改无关页面。保留每页的 ## 我的反馈。证据不足就标 needs_source_review，不要编造。完成后运行计划里的 rg 检查。
```

---

### Task 8: Content Batch B - Skills and Workflow Pages

**Purpose:** Fix the most important AI coding workflow knowledge: Superpowers, grill-me, Trellis, CodeStable, OpenSpec, CCG/CCW, BMAD, and related comparisons.

**Files:**
- Modify:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/Superpowers.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/Trellis.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CodeStable.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/OpenSpec.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/BMAD.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CCG.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CCW.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/grill-me.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/Plan-mode.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/skill-creator.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/AI-Coding-Workflow-选型.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/grill-me-与-Superpowers-brainstorming-对比.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/Trellis-Superpowers-CodeStable-OpenSpec-对比.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/CCG-CCW-多CLI编排对比.md`

- [ ] **Step 1: Define comparison scopes before editing**

Use these scopes:

- Full workflow comparison: `Superpowers` vs `Trellis` vs `CodeStable` vs `OpenSpec`.
- Component comparison: `Superpowers brainstorming` vs `grill-me`.
- Multi-CLI orchestration comparison: `CCG` vs `CCW`.
- Task-weight route page: when to use no framework, light prompt, component skill, full workflow.

- [ ] **Step 2: Rewrite workflow pages**

Each workflow page must include:

```md
## 一句话判断
## 它是什么
## 适合什么
## 不适合什么
## 当前结论
## 核心步骤
## 关键证据
## 反方与风险
## 相关对比
## 待验证
## 来源
## 我的反馈
```

- [ ] **Step 3: Rewrite component pages**

Each component page must include:

```md
## 一句话判断
## 触发条件
## 停止条件
## 适合什么
## 不适合什么
## 关键证据
## 相关对比
## 待验证
## 来源
## 我的反馈
```

- [ ] **Step 4: Verify batch**

Run:

```bash
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/Superpowers.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/Trellis.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CodeStable.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/OpenSpec.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/BMAD.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CCG.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/workflows/CCW.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/grill-me.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/Plan-mode.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/components/skill-creator.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/AI-Coding-Workflow-选型.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/grill-me-与-Superpowers-brainstorming-对比.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/Trellis-Superpowers-CodeStable-OpenSpec-对比.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/CCG-CCW-多CLI编排对比.md -S
```

Expected: no residual bad phrases in the target files.

**给子线程的中文提示词：**

```text
你负责“技能和工作流页面”这一批内容质量。请执行任务八。重点解决用户指出的“完整工作流和局部技能混比”问题：完整工作流只和完整工作流比较，局部组件只和局部组件比较。只改计划里列出的工作流页、组件页、对比页。保留 ## 我的反馈。证据不足时写清楚缺口并标 needs_source_review。完成后运行计划里的 rg 检查。
```

---

### Task 9: Content Batch C - API Relay, Services, and Public Station Collections

**Purpose:** Make API relay/service pages useful without mixing in workflow, MCP, or skill evidence.

**Files:**
- Modify:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/API-中转.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/third-party-API.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/公益站.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/CPA.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/CliproxyApi.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/New-API.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/GPT-Load.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/Anyrouter.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/sub2api.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/OpenRouter.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/API-中转与网关选择.md`

- [ ] **Step 1: Keep service schema strict**

Each service page must include:

```md
## 一句话判断
## 它是什么
## 适合什么
## 不适合什么
## 稳定性
## 隐私/安全风险
## 价格/额度变化风险
## 当前结论
## 关键证据
## 反方与风险
## 相关竞品
## 待验证
## 来源
## 我的反馈
```

- [ ] **Step 2: Split collection logic**

`公益站.md` should not pretend there is one “公益站” object. It should explain:

- 公益站宣传帖
- 公益站推荐/汇总帖
- 公益站使用风险
- 与 API 管理工具、网关、模型路由的区别
- when a specific station deserves a separate service page

- [ ] **Step 3: Rewrite API comparison by layers**

`API-中转与网关选择.md` should compare:

- provider/service
- gateway/admin panel
- account pool/load balancer
- local client adapter/router
- model fidelity and model shrinking risk
- privacy and abuse risk
- freshness verification before adoption

- [ ] **Step 4: Verify batch**

Run:

```bash
rg -n "workflow|MCP|skill|候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/API-中转.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/third-party-API.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/collections/公益站.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/CPA.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/CliproxyApi.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/New-API.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/GPT-Load.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/Anyrouter.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/sub2api.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/services/OpenRouter.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/comparisons/API-中转与网关选择.md -S
```

Expected: no old-quality terms; any `workflow`, `MCP`, or `skill` matches must be contextually explaining exclusion, not evidence pollution.

**给子线程的中文提示词：**

```text
你负责“API 中转、服务和公益站集合”这一批内容质量。请执行任务九。目标是把 API 中转、公益站、网关、管理面板、客户端路由分清楚，强调稳定性、隐私安全、价格额度、模型保真和最新状态复核。不要把工作流、MCP、技能相关证据混入服务对比。只改计划里列出的页面，保留 ## 我的反馈。
```

---

### Task 10: Content Batch D - Concepts, Components, and Knowledge Folder Cleanup

**Purpose:** Make `20_Knowledge` useful instead of像资源候选夹.

**Files:**
- Modify:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/AGENTS.md.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/CLAUDE.md.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/SKILL.md.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Subagent.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Subagents.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Context-Engineering.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Harness-Engineering.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/RAG.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/memory.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/multi-agent.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Vibecoding.md`

- [ ] **Step 1: Convert generic file-name pages**

For `AGENTS.md.md`, `CLAUDE.md.md`, and `SKILL.md.md`, choose one of:

- true concept page if there is enough evidence and it explains how the file shapes agent behavior;
- alias page to a broader concept if it is not worth standalone maintenance;
- `needs_source_review` page if the current content is only a generated residue.

- [ ] **Step 2: Merge singular/plural duplicate**

Make `Subagent.md` and `Subagents.md` a canonical concept plus alias, not two pages with duplicated evidence.

- [ ] **Step 3: Keep concept schema focused**

Concept pages should explain:

- concept boundary
- common misconception
- when it is useful
- when it creates overhead
- links to workflows/resources/components where it becomes actionable

- [ ] **Step 4: Verify batch**

Run:

```bash
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/AGENTS.md.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/CLAUDE.md.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/SKILL.md.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Subagent.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Subagents.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Context-Engineering.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Harness-Engineering.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/RAG.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/memory.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/multi-agent.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/concepts/Vibecoding.md -S
```

Expected: no old-quality terms in target files.

**给子线程的中文提示词：**

```text
你负责“知识概念页清理”这一批内容质量。请执行任务十。目标是让 20_Knowledge 下的概念页解释概念边界、常见误读、适用场景和不适用场景，而不是像资源候选卡。特别处理 AGENTS.md.md、CLAUDE.md.md、SKILL.md.md、Subagent/Subagents 这些泛名或重复页。只改计划里列出的页面，保留 ## 我的反馈。
```

---

### Task 11: Human Reading Entry, Tags, Status, and Watchlist Semantics

**Purpose:** Make the vault easier to read and make user edits actionable without requiring full-vault reading.

**Files:**
- Modify:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/index.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/hot.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/怎么读这个知识库.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/全库带读手册.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/decisions/Watchlist-使用规则.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/preferences/冲浪筛选偏好.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/rejections/低价值内容排除规则.md`
- Modify generator if needed:
  - `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`

- [ ] **Step 1: Define fields in one practical page**

`怎么读这个知识库.md` should explain only the concepts the user needs while reading:

- `status`
- `watchlist`
- `evidence_status`
- `staleness_risk`
- `tags`
- `## 我的反馈`
- `_system/` versus human pages

- [ ] **Step 2: Make watchlist behavior explicit**

`Watchlist-使用规则.md` must state:

- checking `watchlist: true` means “prioritize refresh and related discovery”, not “I definitely adopt this”.
- unchecking watchlist means “do not spend refresh budget unless rediscovered with strong signal”.
- for dislike, use feedback/rejection status, not only `watchlist: false`.
- agent reads watchlist through hot indexes/context pack, not by scanning every page.

- [ ] **Step 3: Reduce permanent guide clutter**

Home/guide pages should be short. If a guide is only temporary onboarding text and not needed for normal use, move detailed explanations into one manual page and keep `index.md` as a map.

- [ ] **Step 4: Verify readability**

Run:

```bash
wc -l /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/index.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/hot.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/怎么读这个知识库.md \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/decisions/Watchlist-使用规则.md
```

Expected: entry pages are readable in one sitting; detailed manual can be longer but should not duplicate every content page.

**给子线程的中文提示词：**

```text
你负责“Obsidian 导读和反馈语义”这一块。请执行任务十一。目标是让用户知道怎么读、watchlist 勾选会影响什么、不感兴趣和感兴趣该怎么表达，以及哪些目录通常不用人看。不要重复每一页内容，只解释概念和路径。保留已有反馈内容，必要时精简说明页。
```

---

### Task 12: Final Verification, Dispatch Review, and Merge Notes

**Purpose:** Combine subagent results without hiding residual issues.

**Files:**
- Modify if needed:
  - `/Users/mortisss/Documents/linuxdo/docs/superpowers/plans/2026-06-05-linuxdo-obsidian-quality-upgrade-subagents.md`
  - `/Users/mortisss/Documents/linuxdo/docs/superpowers/specs/2026-06-05-linuxdo-obsidian-knowledge-quality-rules-design.md`

- [ ] **Step 1: Run repository tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check HEAD
```

Expected: tests pass; diff check has no output.

- [ ] **Step 2: Run full human-facing residue scan**

Run:

```bash
rg -n "候选资源，当前记录显示它被多次提及|来源证据|高相关|中等相关|累计权重|证据权重|legacy_summary|旧帖|旧记录|旧冲浪|风佬巨作|v5\\.0|\\.\\.\\.|…" \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback \
  /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/90_Inbox/review-queue -S
```

Expected: no output, except a guide page may quote a banned term as an example of what the scanner blocks. If that happens, rewrite the guide example to avoid the literal term.

- [ ] **Step 3: Run quality audit**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_latest.json
```

Expected: report exists; unresolved items are either deliberately queued in `90_Inbox/review-queue` or are listed in the final summary.

- [ ] **Step 4: Sync feedback and build context pack**

Run:

```bash
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json --output output/linuxdo_surf/feedback_sync_latest.json
python3 tools/linuxdo_surf.py knowledge-context-pack --config config/knowledge_sources.json --focus superpowers --output output/linuxdo_surf/context_pack_latest.json
```

Expected: both commands succeed; context pack is compact.

- [ ] **Step 5: Final report**

Report:

- code tests run and result
- vault scans run and result
- pages rewritten by batch
- pages downgraded to `needs_source_review`
- aliases merged
- unresolved source gaps
- next surf instructions

**给子线程的中文提示词：**

```text
你负责“最终验证”。请执行任务十二。不要做大改动，只运行测试、格式检查、残留文本扫描、质量审计、反馈同步、轻量上下文包生成。把失败项按文件路径列出，并区分为三类：必须立即修复、可以排队稍后处理、需要用户打开网页确认。
```

---

## Recommended Dispatch Order

Start these first because they create guardrails:

1. Task 1 audit
2. Task 2 schema/lint
3. Task 3 context pack
4. Task 6 refresh queue

Then run content batches in parallel:

1. Task 7 Agent CLI/IDE
2. Task 8 Skills/Workflow
3. Task 9 API/Services
4. Task 10 Concepts/Components
5. Task 11 Home/Feedback guide

Finish with:

1. Task 4 generator integration if audit/schema changed expectations.
2. Task 5 structure repair after content batches stop moving pages by hand.
3. Task 12 final verification.

## Self-Review

Spec coverage:

- Token saving is covered by Task 3 and Task 6.
- Data persistence and feedback influence are covered by Task 3, Task 6, and Task 11.
- Source/evidence quality is covered by Task 1, Task 2, Task 4, and Task 6.
- Content quality and readability are covered by Task 7 through Task 11.
- User concerns about resource cards, comparisons, workflows, knowledge folder, watchlist, and old source gaps are covered by dedicated tasks.
- Browser failure policy is covered by Task 6.

Placeholder scan:

- This plan avoids unresolved implementation markers and gives concrete files, commands, expected results, and subagent messages.

Type consistency:

- `resource`, `service`, `workflow`, `concept`, `component`, `comparison`, and `collection` are the page types used consistently across quality schemas and content batches.

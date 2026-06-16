# Linux.do Knowledge Integrity Follow-up Goal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the follow-up cleanup exposed by `knowledge-index-audit`, `batch_manifest`, and the minimal evidence edge, then only continue knowledge-base upgrades while a majority of review subagents agree the next slice has clear value and does not waste tokens.

**Architecture:** Treat this as two phases. Phase 1 is deterministic cleanup of known residual queues: metadata freshness, counter evidence, evidence payload variants, and uncategorized resources. Phase 2 is governed exploration: subagents discuss the next upgrade options in `docs/superpowers/plans/2026-06-07-linuxdo-knowledge-upgrade-options.md`, majority selects one minimal slice, implementation is followed by the same cleanup and multi-agent review loop, and the goal stops when most reviewers judge the marginal value too low.

**Tech Stack:** Python standard library, `tools/linuxdo_surf.py`, `tools/linuxdo_knowledge/*`, JSON hot indexes in `state/knowledge/`, Obsidian Markdown vault, Codex in-app Browser first, Chrome fallback only when live browser access is blocked, `unittest`, `rg`, `jq`.

---

## Files And Responsibilities

- Read: `/Users/mortisss/Documents/linuxdo/docs/superpowers/plans/2026-06-07-linuxdo-knowledge-upgrade-options.md` for phase-2 candidate directions and prior subagent consensus.
- Read/modify through CLI: `/Users/mortisss/Documents/linuxdo/state/knowledge/topic_update_state.json` for `reply_count`, `last_activity_at`, and `metadata_refresh_needed`.
- Read/modify through CLI or bounded patches: `/Users/mortisss/Documents/linuxdo/state/knowledge/counter_evidence_queue.json` for the 16 counter/risk-review items after claim review.
- Read/modify through CLI or bounded patches: `/Users/mortisss/Documents/linuxdo/state/knowledge/evidence_index.json`, `evidence_by_claim.json`, and `evidence_by_resource.json` for the 232 evidence payload variants.
- Read/modify through CLI or bounded patches: `/Users/mortisss/Documents/linuxdo/state/knowledge/resource_index.json` for the 114 `uncategorized` resources.
- Write reports and working sets under `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/`, using compact JSON/MD artifacts instead of chat transcripts.
- Modify only if the existing CLI is insufficient: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py` and focused modules under `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/`.
- Test: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py` and `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_surf.py`.

## Stop Rules

- Stop Phase 1 only when `metadata_refresh_pending`, actionable counter-evidence queue items, actionable payload-variant ambiguities, and actionable `uncategorized` resources are either resolved or explicitly parked with a reason that audit tools can preserve.
- Stop Phase 2 when at least a majority of review subagents say the next proposed upgrade has low marginal benefit or would increase token cost more than it reduces future waste.
- Do not continue adding features merely because an audit number can be made prettier. Every new slice must reduce future reading cost, increase evidence correctness, or improve reusable decision quality.
- Do not read old `readings_all.json` as a substitute for live evidence.

### Task 1: Baseline Snapshot

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_index_audit_latest.json`
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_rebuild_evidence_latest.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/followup_goal_baseline.json`

- [ ] **Step 1: Run the current machine audits**

```bash
python3 tools/linuxdo_surf.py knowledge-index-audit \
  --config config/knowledge_sources.json \
  --readings-dir output/linuxdo_surf \
  --output output/linuxdo_surf/knowledge_index_audit_followup_baseline.json

python3 tools/linuxdo_surf.py knowledge-rebuild-evidence \
  --config config/knowledge_sources.json \
  --output output/linuxdo_surf/knowledge_rebuild_evidence_followup_baseline.json
```

Expected: audit JSON exists; known residuals are approximately `metadata_refresh_pending=1277`, `duplicate_evidence_ids=649`, `broken_evidence_refs=0`.

- [ ] **Step 2: Write compact baseline summary**

```bash
python3 - <<'PY'
import json
from pathlib import Path

audit = json.loads(Path("output/linuxdo_surf/knowledge_index_audit_followup_baseline.json").read_text())
rebuild = json.loads(Path("output/linuxdo_surf/knowledge_rebuild_evidence_followup_baseline.json").read_text())
resources = json.loads(Path("state/knowledge/resource_index.json").read_text()).get("resources", {})
evidence = json.loads(Path("state/knowledge/evidence_index.json").read_text()).get("evidence", {})
counter = json.loads(Path("state/knowledge/counter_evidence_queue.json").read_text()).get("items", [])

summary = {
    "kind": "followup_goal_baseline",
    "audit_issue_counts": audit.get("issue_counts", {}),
    "rebuild_summary": {k: rebuild.get(k) for k in ["evidence_lines", "unique_evidence_ids", "duplicate_evidence_ids", "counter_queue_items", "invalid_lines"]},
    "uncategorized_resources": sum(1 for item in resources.values() if isinstance(item, dict) and item.get("category") == "uncategorized"),
    "payload_variant_evidence_ids": sum(1 for item in evidence.values() if isinstance(item, dict) and int(item.get("payload_variant_count") or 0) > 1),
    "counter_queue_items": len(counter),
}
Path("output/linuxdo_surf/followup_goal_baseline.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Expected: the summary captures the four Phase 1 queues in one place.

### Task 2: Real Metadata Refresh

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/state/knowledge/topic_update_state.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/metadata_refresh_pending_topics.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/metadata_refresh_live_items.json`
- Modify through CLI: `/Users/mortisss/Documents/linuxdo/state/knowledge/topic_update_state.json`

- [ ] **Step 1: Generate the pending topic list**

```bash
python3 - <<'PY'
import json
from pathlib import Path

updates = json.loads(Path("state/knowledge/topic_update_state.json").read_text()).get("topics", {})
items = []
for topic_id, item in sorted(updates.items(), key=lambda pair: int(pair[0]) if str(pair[0]).isdigit() else str(pair[0])):
    if isinstance(item, dict) and item.get("metadata_refresh_needed"):
        items.append({
            "topic_id": int(topic_id) if str(topic_id).isdigit() else topic_id,
            "url": item.get("url") or f"https://linux.do/t/topic/{topic_id}",
            "reason": item.get("metadata_refresh_reason", "metadata_refresh_needed"),
        })

payload = {"kind": "metadata_refresh_pending_topics", "count": len(items), "items": items}
Path("output/linuxdo_surf/metadata_refresh_pending_topics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Expected: `count` equals the current `metadata_refresh_pending` audit count.

- [ ] **Step 2: Fetch live metadata with Codex in-app Browser first**

Open `https://linux.do` in the in-app Browser and fetch `/t/<topic_id>.json` with same-origin credentials for every pending topic. Save only lightweight fields:

```json
{
  "topic_id": 697447,
  "title": "example title",
  "url": "https://linux.do/t/example/697447",
  "reply_count": 123,
  "last_activity_at": "2026-06-07T12:34:56.000Z",
  "visible": true,
  "fetch_status": 200,
  "source": "in_app_browser_topic_json"
}
```

Expected: successful items are written to `output/linuxdo_surf/metadata_refresh_live_items.json`; blocked items include `fetch_status`, `error`, and `needed_human_action`.

- [ ] **Step 3: If in-app Browser is blocked, use Chrome fallback for the blocked subset**

Use the user's Chrome session only for topics where in-app Browser returns login/challenge/permission/loading failures. Append fallback results to the same output file with `source: "chrome_topic_json_fallback"` and keep the failure evidence from Step 2.

Expected: every pending topic is either refreshed or explicitly recorded as live-access blocked. No stale summary is used as a substitute.

- [ ] **Step 4: Apply metadata refresh**

```bash
python3 tools/linuxdo_surf.py metadata-refresh \
  --config config/knowledge_sources.json \
  --input output/linuxdo_surf/metadata_refresh_live_items.json \
  --output output/linuxdo_surf/metadata_refresh_followup_result.json
```

Expected: `updated` is high enough to clear or materially reduce `metadata_refresh_pending`.

- [ ] **Step 5: Audit metadata result**

```bash
python3 tools/linuxdo_surf.py knowledge-index-audit \
  --config config/knowledge_sources.json \
  --readings-dir output/linuxdo_surf \
  --output output/linuxdo_surf/knowledge_index_audit_after_metadata_refresh.json
```

Expected: `metadata_refresh_pending` is `0`, or any remaining items have a live-access blocked artifact and are not silently treated as refreshed.

### Task 3: Counter Evidence Queue Review

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/state/knowledge/counter_evidence_queue.json`
- Read/modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/claim_index.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/counter_evidence_review_followup.json`

- [ ] **Step 1: Export the 16 queue items with target claims**

```bash
python3 - <<'PY'
import json
from pathlib import Path

queue = json.loads(Path("state/knowledge/counter_evidence_queue.json").read_text()).get("items", [])
claims = json.loads(Path("state/knowledge/claim_index.json").read_text()).get("claims", {})
items = []
for item in queue:
    if not isinstance(item, dict):
        continue
    claim_id = item.get("claim_id")
    claim = claims.get(claim_id, {}) if isinstance(claim_id, str) else {}
    items.append({
        "queue_id": item.get("id"),
        "queue_kind": item.get("queue_kind"),
        "claim_id": claim_id,
        "claim_status": claim.get("status"),
        "claim_summary": claim.get("summary") or claim.get("description") or claim.get("title"),
        "evidence_id": item.get("evidence_id"),
        "summary": item.get("summary"),
        "decision": "",
        "action": "",
        "reason": "",
    })
Path("output/linuxdo_surf/counter_evidence_review_followup.json").write_text(json.dumps({"kind": "counter_evidence_review", "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Expected: review artifact contains all queue items and enough claim context to decide status changes.

- [ ] **Step 2: Review each item and classify it**

Use these exact decision values:

```text
mark_disputed
mark_needs_retest
mark_risk_boundary
already_reflected
not_actionable
needs_live_topic_review
```

Expected: no item keeps an empty `decision`; risky or opposing evidence changes the claim status instead of only sitting in the queue.

- [ ] **Step 3: Apply bounded claim updates**

For `mark_disputed`, set claim `status` to `disputed`. For `mark_needs_retest`, set `status` to `needs_retest`. For `mark_risk_boundary`, preserve the current status and add/update `risk_boundary`. For `already_reflected` and `not_actionable`, add `counter_evidence_reviewed_at` and `counter_evidence_review_reason`.

Expected: queue review decisions become durable in `claim_index.json` without deleting evidence history.

### Task 4: Payload Variant Evidence Review

**Files:**
- Read/modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/evidence_index.json`
- Read/modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/evidence_by_claim.json`
- Read/modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/evidence_by_resource.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/evidence_payload_variant_review_followup.json`

- [ ] **Step 1: Export payload-variant candidates**

```bash
python3 - <<'PY'
import json
from pathlib import Path

evidence = json.loads(Path("state/knowledge/evidence_index.json").read_text()).get("evidence", {})
items = []
for evidence_id, item in sorted(evidence.items()):
    if isinstance(item, dict) and int(item.get("payload_variant_count") or 0) > 1:
        items.append({
            "evidence_id": evidence_id,
            "payload_variant_count": item.get("payload_variant_count"),
            "seen_count": item.get("seen_count"),
            "source_id": item.get("source_id"),
            "relation": item.get("relation"),
            "stance": item.get("stance"),
            "summary": item.get("summary"),
            "decision": "",
            "reason": "",
        })
Path("output/linuxdo_surf/evidence_payload_variant_review_followup.json").write_text(json.dumps({"kind": "evidence_payload_variant_review", "count": len(items), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Expected: `count` equals current payload-variant evidence id count, approximately `232`.

- [ ] **Step 2: Classify variants**

Use these exact decision values:

```text
append_only_replay
same_claim_updated_summary
materialize_latest_only
split_needed
needs_live_topic_review
```

Expected: replay duplicates are documented and not over-treated; genuine semantic variants are either split or marked for live topic review.

- [ ] **Step 3: Apply minimal durable annotations**

For `append_only_replay`, add `variant_review_status: "append_only_replay"` and keep `payload_hashes`. For `same_claim_updated_summary`, add `variant_review_status: "same_claim_updated_summary"`. For `materialize_latest_only`, keep the current materialized item and add `materialized_from_payload_variants: true`. For `split_needed` and `needs_live_topic_review`, add a follow-up field instead of inventing evidence.

Expected: duplicate id audit can distinguish harmful ambiguity from harmless append-only replay.

### Task 5: Uncategorised Resource Cleanup

**Files:**
- Read/modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/resource_index.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/uncategorized_resource_review_followup.json`

- [ ] **Step 1: Export resources with `category=uncategorized`**

```bash
python3 - <<'PY'
import json
from pathlib import Path

resources = json.loads(Path("state/knowledge/resource_index.json").read_text()).get("resources", {})
items = []
for resource_id, item in sorted(resources.items()):
    if isinstance(item, dict) and item.get("category") == "uncategorized":
        items.append({
            "resource_id": resource_id,
            "name": item.get("name") or item.get("title") or resource_id.replace("resource:", ""),
            "summary": item.get("summary") or item.get("description") or "",
            "current_category": item.get("category"),
            "decision_category": "",
            "reason": "",
        })
Path("output/linuxdo_surf/uncategorized_resource_review_followup.json").write_text(json.dumps({"kind": "uncategorized_resource_review", "count": len(items), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Expected: `count` equals current `uncategorized` resource count, approximately `114`.

- [ ] **Step 2: Assign conservative categories**

Allowed categories are the existing vocabulary unless a resource truly needs `needs_source_review`:

```text
workflow
tool
service
github_repo
concept
collection
skill
component
api
guide
configuration-pattern
tool-comparison
ai-api-proxy
agent-skill
risk-boundary
needs_source_review
```

Expected: generic names such as `resource:claude code` and `resource:codex cli` become `tool`; broad practices such as `resource:context engineering` become `concept`; ambiguous items become `needs_source_review`, not a fake precise category.

- [ ] **Step 3: Apply category updates**

Update only `category`, `category_reviewed_at`, and `category_review_reason`.

Expected: no resource keeps `category: "uncategorized"` unless it is intentionally converted to `needs_source_review`.

### Task 6: Phase 1 Multi-Subagent Review And Fix Loop

**Files:**
- Read: all Phase 1 artifacts under `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/`
- Read: hot indexes under `/Users/mortisss/Documents/linuxdo/state/knowledge/`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/followup_phase1_subagent_vote.md`

- [ ] **Step 1: Run audits and tests**

```bash
python3 tools/linuxdo_surf.py knowledge-index-audit \
  --config config/knowledge_sources.json \
  --readings-dir output/linuxdo_surf \
  --output output/linuxdo_surf/knowledge_index_audit_after_phase1.json

python3 tools/linuxdo_surf.py knowledge-rebuild-evidence \
  --config config/knowledge_sources.json \
  --output output/linuxdo_surf/knowledge_rebuild_evidence_after_phase1.json

python3 -m unittest tests.test_linuxdo_knowledge tests.test_linuxdo_surf
```

Expected: tests pass; audit residuals are either zero or explicitly justified in phase artifacts.

- [ ] **Step 2: Spawn at least three independent review subagents**

Reviewer A checks metadata and freshness correctness. Reviewer B checks evidence/counter-evidence correctness. Reviewer C checks token-efficiency and over-engineering risk.

Expected: every reviewer gives `approve`, `approve_with_fixes`, or `stop_and_fix`, plus concrete file/path references.

- [ ] **Step 3: Apply required fixes and re-run audits**

Fix only issues that affect correctness, repeatability, or token efficiency. Re-run Step 1 after fixes.

Expected: Phase 1 is complete only after no reviewer has `stop_and_fix`.

### Task 7: Phase 2 Majority-Governed Upgrade Slice

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/docs/superpowers/plans/2026-06-07-linuxdo-knowledge-upgrade-options.md`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/phase2_upgrade_votes_round_N.md`
- Write if implementation proceeds: focused plan/update artifacts under `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/`

- [ ] **Step 1: Spawn multiple proposal subagents**

Ask at least five subagents to independently choose the next smallest valuable upgrade slice from the upgrade-options document. Each must answer:

```text
preferred_slice:
expected_benefit:
token_cost_risk:
reuse_value:
stop_or_continue:
```

Expected: a majority winner exists, or majority says stop.

- [ ] **Step 2: Implement only the majority slice**

If the majority says continue, implement the smallest slice that satisfies the winning direction. Use TDD for code changes, keep write scope narrow, and do not start broad schema migrations.

Expected: the slice has a measurable audit/test effect and a clear reuse argument.

- [ ] **Step 3: Repeat cleanup and review after the slice**

Run the Phase 1 style audits, tests, and at least three subagent reviews. If new queues are created, resolve or park them with reasons.

Expected: the system is cleaner after the slice than before it.

- [ ] **Step 4: Decide whether to continue**

Spawn another vote round. Continue only if the majority says the next slice still has high reuse value and lowers future token waste.

Expected: the goal ends when the majority says stop or marginal benefit is low.

## Self-Review

- Spec coverage: covers real metadata refresh, 16 counter evidence items, 232 payload variants, 114 uncategorized resources, multi-subagent review, phase-2 majority voting, cleanup after each upgrade slice, and stopping at low marginal value.
- Placeholder scan: no unresolved `TBD`, vague future work, or unspecified decision vocabulary remains.
- Type consistency: consistent use of `metadata_refresh_pending`, `counter_evidence_queue`, `payload_variant_count`, `uncategorized`, `needs_source_review`, `approve_with_fixes`, and majority stop rules.

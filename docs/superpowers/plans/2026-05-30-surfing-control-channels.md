# Surfing Control Channels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Linux.do 冲浪助手增加“操控通道”参数，让每轮阅读任务明确由 Codex 内置浏览器、用户 Chrome、Mac 长任务或 computer-use 哪种方式承载。

**Architecture:** 第一版只做控制通道的参数、校验、任务元数据和阅读指令差异，不实现真实 Chrome 自动化、Mac `/goal` 或 computer-use。`tools/linuxdo_surf.py` 保持单文件 CLI 结构，`tests/test_linuxdo_surf.py` 继续使用 unittest 覆盖行为。

**Tech Stack:** Python 标准库、argparse、unittest、JSON 任务包。

---

### Task 1: Add Control Channel Validation

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing tests**

Add tests that define the accepted channel values and the unknown-channel failure message:

```python
def test_validate_channel_accepts_supported_channels(self):
    self.assertEqual(linuxdo_surf.validate_channel("codex-browser"), "codex-browser")
    self.assertEqual(linuxdo_surf.validate_channel("user-chrome"), "user-chrome")
    self.assertEqual(linuxdo_surf.validate_channel("mac-goal"), "mac-goal")
    self.assertEqual(linuxdo_surf.validate_channel("computer-use"), "computer-use")

def test_validate_channel_rejects_unknown_channel(self):
    with self.assertRaisesRegex(ValueError, "未知操控通道"):
        linuxdo_surf.validate_channel("daily")
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: FAIL or ERROR because `validate_channel` does not exist.

- [x] **Step 3: Write minimal implementation**

Add supported channel constants and a validator near the existing mode constants:

```python
CONTROL_CHANNELS = {"codex-browser", "user-chrome", "mac-goal", "computer-use"}
DEFAULT_CONTROL_CHANNEL = "codex-browser"


def validate_channel(channel: str) -> str:
    normalized = channel.strip().lower()
    if normalized not in CONTROL_CHANNELS:
        raise ValueError(f"未知操控通道：{channel}")
    return normalized
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

### Task 2: Add Channel Metadata To Browser Tasks

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing tests**

Add tests proving the default channel remains Codex browser and a Chrome-selected task carries Chrome-specific instructions:

```python
def test_build_browser_task_defaults_to_codex_browser_channel(self):
    task = linuxdo_surf.build_browser_task(
        mode="research",
        query="Codex 工作流",
        candidates=[],
        skill_names=[],
        max_topics=3,
        max_replies=5,
    )

    self.assertEqual(task["control_channel"], "codex-browser")
    self.assertIn("Codex 内置浏览器", task["instructions"])

def test_build_browser_task_adds_user_chrome_channel_instructions(self):
    task = linuxdo_surf.build_browser_task(
        mode="research",
        query="Codex 工作流",
        candidates=[],
        skill_names=[],
        max_topics=3,
        max_replies=5,
        control_channel="user-chrome",
    )

    self.assertEqual(task["control_channel"], "user-chrome")
    self.assertIn("Chrome", task["instructions"])
    self.assertIn("标签组", task["instructions"])
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: FAIL because `control_channel` is not in the task and `build_browser_task` does not accept the new argument.

- [x] **Step 3: Write minimal implementation**

Extend `build_browser_task` with an optional `control_channel` argument, validate it, write `control_channel` into the task JSON, and pass it to `_browser_instructions`.

Update `_browser_instructions` so:

```python
def _browser_instructions(mode: str, control_channel: str) -> str:
    channel_notes = {
        "codex-browser": "请使用 Codex 内置浏览器打开候选 Linux.do 帖子。首次需要登录时请让用户完成登录，后续复用已保存登录态。",
        "user-chrome": "请使用用户本机 Chrome 中已经打开或按标签组整理的 Linux.do 帖子，理解标签组和页面之间的关系；不要把这个通道当作全站搜索。",
        "mac-goal": "这是未来 Mac /goal 长任务通道。执行前必须明确停止标准、预算和阶段汇报，不要在第一版里假装已经能后台持续冲浪。",
        "computer-use": "这是实验性 computer-use 通道。仅在普通浏览器能力不足时考虑，不用于常规帖子阅读。",
    }
    return (
        channel_notes[control_channel]
        + "读取首帖和高价值回复，区分事实、观点、争议和行动建议。"
        + f"当前模式：{mode}。不要生成固定日报，只输出本轮任务结果。"
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

### Task 3: Add CLI `--channel`

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing tests**

Add tests for CLI task generation and invalid argparse choices:

```python
def test_cli_plan_writes_control_channel(self):
    with TemporaryDirectoryPath() as tmp_path:
        topics_path = tmp_path / "topics.json"
        topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")
        out_dir = tmp_path / "out"

        exit_code = linuxdo_surf.main(
            [
                "plan",
                "--mode",
                "research",
                "--channel",
                "user-chrome",
                "--topics",
                str(topics_path),
                "--output",
                str(out_dir),
                "--state",
                str(tmp_path / "state.json"),
            ]
        )

        task = json.loads((out_dir / "browser_task_research.json").read_text(encoding="utf-8"))

    self.assertEqual(exit_code, 0)
    self.assertEqual(task["control_channel"], "user-chrome")

def test_cli_plan_rejects_unknown_channel(self):
    with TemporaryDirectoryPath() as tmp_path:
        topics_path = tmp_path / "topics.json"
        topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")

        with self.assertRaises(SystemExit) as context:
            linuxdo_surf.main(["plan", "--mode", "research", "--channel", "bad", "--topics", str(topics_path)])

    self.assertEqual(context.exception.code, 2)
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: FAIL because the parser does not know `--channel`.

- [x] **Step 3: Write minimal implementation**

Add the option to the `plan` parser:

```python
plan.add_argument("--channel", choices=sorted(CONTROL_CHANNELS), default=DEFAULT_CONTROL_CHANNEL)
```

Pass it from `run_plan`:

```python
task = build_browser_task(
    args.mode,
    args.query,
    candidates,
    skill_names,
    args.max_topics,
    args.max_replies,
    args.channel,
)
```

In `main`, validate `args.channel` when present:

```python
args.channel = validate_channel(args.channel) if hasattr(args, "channel") else ""
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

### Task 4: Verify And Commit

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`
- Create: `docs/superpowers/plans/2026-05-30-surfing-control-channels.md`

- [x] **Step 1: Run the full local verification**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
git status --short
```

Expected: tests pass; only intended files are modified or created, plus ignored runtime cache if already present.

- [x] **Step 2: Commit**

Run:

```powershell
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py docs/superpowers/plans/2026-05-30-surfing-control-channels.md
git commit -m "feat: add surfing control channels"
```

Expected: commit succeeds.

- [x] **Step 3: Sync remote**

First try:

```powershell
git push origin master
```

If local network times out, sync the changed files through GitHub MCP without force-pushing and report the remote commit SHA.

---

Self-review:

- Spec coverage: covers four control channels, default Codex browser behavior, user Chrome task metadata, CLI `--channel`, and explicit non-goals for real Chrome/Mac/computer-use automation.
- Placeholder scan: no `TBD` / `TODO` / vague implementation placeholders remain.
- Type consistency: the plan consistently uses `control_channel`, `CONTROL_CHANNELS`, `DEFAULT_CONTROL_CHANNEL`, and `validate_channel`.

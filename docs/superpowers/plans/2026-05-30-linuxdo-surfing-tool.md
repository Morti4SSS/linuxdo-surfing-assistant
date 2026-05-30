# Linux.do 冲浪工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 Windows 优先的 Linux.do 任务型冲浪 CLI，支持四种模式、阅读任务包、去重状态和 skill 管理证据导出。

**Architecture:** 第一版不把本地脚本伪装成浏览器爬虫。Codex 内置浏览器负责登录态阅读，CLI 负责生成阅读任务、处理已有 topic 数据、记录已读状态、提炼结构化结果并导出给 skill 管理项目。核心逻辑集中在一个 Python 模块中，后续稳定后再拆分。

**Tech Stack:** Python 3 标准库、PowerShell 既有 CDP 脚本、JSON/JSONL 文件存储、pytest 测试。

---

## 文件结构

- Create: `tools/linuxdo_surf.py`
  - 单文件 CLI 和核心逻辑。
  - 负责四种模式、topic 加载、候选排序、状态读写、阅读任务包生成、结果提炼、skill 证据导出。
- Create: `tests/test_linuxdo_surf.py`
  - 覆盖核心纯函数和 CLI 行为。
- Create: `state/linuxdo_surf_state.json`
  - 运行时生成，不提交为固定内容。保存已读 topic 和已同步 skill 证据状态。
- Create: `output/linuxdo_surf/*.json`
  - 运行时生成，不提交为固定内容。保存阅读任务包、模式结果、skill 证据包。
- Existing reference: `docs/linuxdo-surfing-tool-design.md`
  - 需求来源。
- Existing reference: `tools/collect_linuxdo_research.ps1`
  - 后续仍用于通过已登录浏览器收集候选 topic。
- Existing reference: `tools/fetch_linuxdo_topic_details.ps1`
  - 后续仍用于通过已登录浏览器读取 topic 详情。

## 任务拆分

### Task 1: 核心模型、模式校验和 topic 排序

**Files:**
- Create: `tests/test_linuxdo_surf.py`
- Create: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 写最小实现**
- [ ] **Step 4: 运行测试确认通过**
- [ ] **Step 5: 提交**

### Task 2: 状态存储和阅读任务包生成

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 写最小实现**
- [ ] **Step 4: 运行测试确认通过**
- [ ] **Step 5: 提交**

### Task 3: 结果提炼和 skill 证据包导出

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 写最小实现**
- [ ] **Step 4: 运行测试确认通过**
- [ ] **Step 5: 提交**

### Task 4: CLI 入口和端到端文件输出

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 写最小实现**
- [ ] **Step 4: 运行测试确认通过**
- [ ] **Step 5: 运行基本 CLI 验证**
- [ ] **Step 6: 提交**

## 自检

- 规格覆盖：计划覆盖四种模式、Codex 内置浏览器阅读任务包、Windows 优先、去重状态、skill 管理证据导出、不做固定日报。
- 占位扫描：无 TBD、TODO、implement later。
- 类型一致性：核心数据都使用 `dict[str, Any]`、`list[dict[str, Any]]`、`Path`；CLI 子命令只调用已定义函数。

# Linux.do Surfing Assistant

本仓库保存 Linux.do 冲浪助手的本地脚本、状态设计和 Obsidian 知识库写入流程。

## 第一版知识库流程

1. 准备配置：

```bash
cp config/knowledge_sources.example.json config/knowledge_sources.json
```

把 `obsidian_vault_path` 和 `linuxdo_scripts_bookmarks.path` 改成本机路径。配置文件不能保存 WebDAV 密码、token 或账号凭证。

2. 初始化机器状态和 vault 结构：

```bash
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
```

3. 每次冲浪 goal 启动前同步 Obsidian 人工反馈：

```bash
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
```

4. 同步 LinuxDo Scripts 收藏入口：

```bash
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
```

5. 生成一批 20 帖阅读任务：

```bash
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20
```

6. Codex 读完后，把结构化阅读结果写入状态和 Obsidian：

```bash
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json --batch-id 001
```

7. 每 5-10 批或用户要求时做轻量维护：

```bash
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
```

## 状态原则

- 默认只加载 `state/knowledge/` 里的热索引。
- `readings_all.json` 是旧冷历史，普通启动不读取。
- 已读 topic 更新时只读对应 `topic_summaries/<topic_id>.json`。
- Obsidian 是人工阅读和反馈层，不是机器状态镜像。
- `## 我的反馈` 永远由人维护，脚本写页时保留原文。

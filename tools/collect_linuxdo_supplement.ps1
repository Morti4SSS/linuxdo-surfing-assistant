param(
  [int]$Port = 9334,
  [string]$BasePath = "output/linuxdo_skill_research/topics_raw.json",
  [string[]]$ExtraBasePaths = @(),
  [string]$OutDir = "output/linuxdo_skill_research/supplement"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BasePath)) {
  throw "Base topic file not found: $BasePath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$base = Get-Content -LiteralPath $BasePath -Encoding UTF8 -Raw | ConvertFrom-Json
$seenIds = @{}
foreach ($topic in $base.topics) {
  $seenIds[[string]$topic.id] = $true
}

foreach ($extraPath in $ExtraBasePaths) {
  if (-not (Test-Path -LiteralPath $extraPath)) {
    throw "Extra base topic file not found: $extraPath"
  }
  $extra = Get-Content -LiteralPath $extraPath -Encoding UTF8 -Raw | ConvertFrom-Json
  foreach ($topic in $extra.topics) {
    $seenIds[[string]$topic.id] = $true
  }
}

$targets = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/list"
$page = $targets | Where-Object { $_.type -eq 'page' -and $_.url -like '*linux.do*' } | Select-Object -First 1
if (-not $page) {
  throw "No linux.do page found on CDP port $Port"
}

$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
$seq = 0

function Send-Cdp($method, $params) {
  $script:seq++
  $json = (@{ id = $script:seq; method = $method; params = $params } | ConvertTo-Json -Depth 100 -Compress)
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $script:ws.SendAsync([ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()

  $parts = New-Object System.Collections.Generic.List[string]
  while ($true) {
    $buffer = New-Object byte[] 12582912
    $result = $script:ws.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    $parts.Add([Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
    if ($result.EndOfMessage) {
      $text = ($parts -join '')
      if ($text.Trim().Length -eq 0) {
        $parts.Clear()
        continue
      }
      $msg = $text | ConvertFrom-Json
      if ($msg.id -eq $script:seq) {
        return $msg
      }
      $parts.Clear()
    }
  }
}

Send-Cdp 'Runtime.enable' @{} | Out-Null

$seenJson = (($seenIds.Keys | ForEach-Object { [int]$_ }) | ConvertTo-Json -Compress)
$js = @'
(async () => {
  const seen = new Set(__SEEN_IDS__);
  const queries = [
    'AGENTS.md', 'CLAUDE.md', 'agents.md skill', 'claude.md workflow', '项目规则 AI 编程',
    'hooks Claude Code', 'Claude Code hooks', 'codex hooks', 'hook skill', 'agent hook',
    'subagent', 'sub-agent', '子代理', 'codex subagent', 'Claude Code subagent', '多agent 编程',
    'context engineering', '上下文工程', 'context 压缩', '上下文压缩', 'context 管理', '上下文管理',
    'handoff', '交接文档', '会话沉淀', 'session closeout', '跨会话', '跨对话', '项目记忆', '项目状态图',
    'project memory', 'memory skill', '本地记忆', '长期记忆', '知识沉淀', '知识管理 AI 编程',
    'CLI 替代 MCP', 'MCP 替代', 'Skill CLI', 'CLI 工具链', 'agent friendly CLI', 'JSONL CLI',
    'Slash command', 'slash commands', '自定义命令 Claude Code', 'commands skill',
    'Spec Kit', 'spec 工作流', '规格驱动 AI', 'PRD skill', 'to prd', '需求拷问', 'grill-me',
    'code review skill', '代码审查 Codex', 'Codex 审查 Claude', 'AI code review workflow',
    'architecture mentor', 'architecture skill', '架构导师', '架构体检', '架构审查 skill', '功能切片',
    'Qoder', 'Amp Code', 'Amp code 实践', 'Kiro', 'Windsurf', 'Trae AI 编程', 'OpenCode workflow',
    'Gemini CLI Codex', 'Claude Codex Gemini', '多 CLI 协作', 'multi cli',
    'browser use skill', 'Playwright skill', '网页自动化 skill', '登录态 浏览器 agent',
    '测试 skill', 'verification skill', 'debugging skill', 'TDD skill', 'review workflow',
    'AI 编程 成本', 'token 成本 workflow', 'CodeBurn', 'cache hit', '大上下文 成本',
    'OpenClaw skill', 'openclaw workflow', 'Hermes Agent', 'oh-my-opencode', 'OMO workflow',
    'workflow manager', 'project intake', 'rescue review', '状态地图', '项目接手 AI',
    'Codex 插件', 'Codex Chrome', 'Codex plugin', 'Codex 配置', 'Codex API 模式',
    'Claude Code 配置', 'CCR 配置', 'ccswitch', 'ccr', 'cc-proxy', 'ccometixline',
    'AI IDE workflow', 'AI IDE 工具', '多模型 协作 编程', 'agent 工作台', 'AI 编程 终端'
  ];

  const byId = new Map();
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  for (const q of queries) {
    for (let page = 1; page <= 6; page++) {
      let j;
      try {
        const r = await fetch('/search.json?q=' + encodeURIComponent(q) + '&page=' + page, { credentials: 'include' });
        if (!r.ok) break;
        j = await r.json();
      } catch (error) {
        break;
      }
      const topics = j.topics || [];
      if (!topics.length) break;
      for (const t of topics) {
        if (seen.has(t.id)) continue;
        const current = byId.get(t.id) || {
          id: t.id,
          title: t.title,
          url: `https://linux.do/t/topic/${t.id}`,
          tags: t.tags || [],
          posts_count: t.posts_count || 0,
          reply_count: t.reply_count || 0,
          views: t.views || 0,
          like_count: t.like_count || 0,
          created_at: t.created_at,
          bumped_at: t.bumped_at,
          queries: []
        };
        if (!current.queries.includes(q)) current.queries.push(q);
        byId.set(t.id, current);
      }
      await sleep(70);
    }
  }

  const weights = [
    ['agents.md', 6], ['claude.md', 6], ['hook', 5], ['subagent', 5], ['context', 5],
    ['上下文', 5], ['handoff', 6], ['交接', 6], ['记忆', 5], ['memory', 5], ['cli', 5],
    ['mcp', 4], ['skill', 5], ['workflow', 5], ['工作流', 5], ['review', 4], ['审查', 4],
    ['架构', 5], ['spec', 4], ['prd', 4], ['grill', 4], ['codex', 4], ['claude', 4],
    ['qoder', 3], ['amp', 3], ['kiro', 3], ['opencode', 3], ['成本', 4], ['token', 4]
  ];
  const topics = [...byId.values()].map(t => {
    const text = (t.title + ' ' + (t.tags || []).map(x => x.name || x).join(' ') + ' ' + t.queries.join(' ')).toLowerCase();
    let score = t.queries.length * 3 + Math.min(12, (t.reply_count || 0) / 6) + Math.min(10, (t.like_count || 0) / 15) + Math.min(8, (t.views || 0) / 1800);
    for (const [k, w] of weights) if (text.includes(k.toLowerCase())) score += w;
    const groups = [];
    if (/agents\.md|claude\.md|规则|配置/.test(text)) groups.push('规则与配置');
    if (/hook|subagent|子代理|多agent|agent/.test(text)) groups.push('Agent编排');
    if (/context|上下文|handoff|交接|记忆|memory|状态|沉淀/.test(text)) groups.push('上下文与记忆');
    if (/cli|mcp|command|命令|jsonl/.test(text)) groups.push('CLI与MCP');
    if (/skill|workflow|工作流|spec|prd|grill|review|debug|verification|tdd/.test(text)) groups.push('Skill与工作流');
    if (/架构|审查|功能切片|architecture/.test(text)) groups.push('架构审查');
    if (/成本|token|codeburn|cache/.test(text)) groups.push('成本治理');
    if (/qoder|amp|kiro|windsurf|trae|opencode|gemini|codex|claude/.test(text)) groups.push('工具平台');
    return { ...t, score: Math.round(score * 10) / 10, groups };
  }).sort((a, b) => b.score - a.score);

  return JSON.stringify({
    collected_at: new Date().toISOString(),
    base_seen_count: seen.size,
    query_count: queries.length,
    new_unique_count: topics.length,
    queries,
    topics
  });
})()
'@

$js = $js.Replace('__SEEN_IDS__', $seenJson)
$res = Send-Cdp 'Runtime.evaluate' @{ expression = $js; returnByValue = $true; awaitPromise = $true }
$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null

$jsonText = $res.result.result.value
if (-not $jsonText) {
  throw "No supplement result returned"
}

$rawPath = Join-Path $OutDir 'supplement_topics_raw.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\supplement_topics_raw.json', $jsonText, [Text.UTF8Encoding]::new($false))

$data = $jsonText | ConvertFrom-Json
$summary = [ordered]@{
  collected_at = $data.collected_at
  base_seen_count = $data.base_seen_count
  query_count = $data.query_count
  new_unique_count = $data.new_unique_count
  top_80 = @($data.topics | Select-Object -First 80)
}
$summaryPath = Join-Path $OutDir 'supplement_topics_summary.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\supplement_topics_summary.json', ($summary | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))

Write-Output "new_unique_count=$($data.new_unique_count)"
Write-Output "supplement_raw=$rawPath"
Write-Output "supplement_summary=$summaryPath"

param(
  [int]$Port = 9334,
  [string]$BasePath = "output/linuxdo_skill_research/topics_raw.json",
  [string[]]$ExtraBasePaths = @("output/linuxdo_skill_research/supplement/supplement_topics_raw.json"),
  [string]$OutDir = "output/linuxdo_skill_research/supplement_round2"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BasePath)) {
  throw "Base topic file not found: $BasePath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$seenIds = @{}
$base = Get-Content -LiteralPath $BasePath -Encoding UTF8 -Raw | ConvertFrom-Json
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
    'output style', 'output-style', '输出风格', '输出样式', 'Claude Code output style',
    'prompt engineering coding', '系统提示词 编程', '全局提示词 编程', '提示词模板 Claude Code',
    'Roo Code', 'RooCode', 'Cline', 'Cline workflow', 'Continue dev', 'Aider', 'aider workflow',
    'Cursor Rules', 'Cursor rules', 'cursor 工作流', 'cursor skill', 'cursor mcp',
    'Windsurf workflow', 'Windsurf rules', 'Cascade AI', 'Qwen Code', 'Qwen coder',
    'Kimi Code', 'Kimi k2 coding', 'Gemini CLI workflow', 'Gemini CLI skill',
    'Trae 编程', 'Trae AI', 'Qoder workflow', 'Qoder rules', 'Amp Code workflow',
    'Kiro spec', 'Kiro workflow', 'Devin 编程', 'Devin workflow',
    '代码地图', '项目地图', 'repo map', 'code map', 'codebase map', '代码知识图谱',
    'Graphify', 'DeepWiki', 'zread', '代码库理解', '代码检索 AI', 'AST 搜索', '向量搜索 代码',
    '测试验收 AI', '验收 skill', '自动验收', '测试策略 skill', 'E2E 测试 agent',
    'Playwright 验收', 'webapp testing', 'browser testing AI', 'UI 验收 AI',
    '任务管理 agent', 'task manager AI', '任务拆解 skill', '任务状态 AI', '看板 agent',
    '权限 控制 agent', '安全边界 AI 编程', '危险命令 AI', 'sandbox codex', 'approval workflow',
    'git worktree AI', 'worktree workflow', '多分支 agent', '并行 agent worktree',
    'PRD 生成 AI', '需求文档 AI', '产品经理 AI', '需求评审 AI', '需求澄清 skill',
    '代码质量门禁', '质量门禁 AI', 'lint agent', 'CI AI 编程', '本地验证 AI',
    '重构 skill', 'refactor skill', '架构重构 AI', '模块化 AI 编程',
    '前端 skill', 'UI skill', 'frontend design skill', '前端审美 AI', 'shadcn AI',
    '文档 skill', 'documentation skill', '项目文档 AI', 'README agent', '教程生成 skill',
    '学习编程 AI', '小白 AI 编程', '小白 vibe coding', 'AI 编程 学习路线',
    'MCP 安全', 'MCP 配置', 'MCP 推荐', 'MCP 踩坑', 'MCP 太多',
    'Claude Code router', 'ccr 踩坑', 'ccswitch 配置', 'Claude Code API 代理',
    'New API Codex', 'One API Codex', '公益站 编程', '模型路由 编程',
    '多模型路由', '模型选择 AI 编程', 'GPT 前端 差', 'Claude 后端', 'Gemini 前端',
    'Token 预算', '上下文预算', '成本优化 AI 编程', '会话成本', '长会话 AI',
    'AI 代码坏味道', 'AI 屎山', 'AI 重构 翻车', 'AI debug 循环', '补丁摞补丁',
    'open source agent workflow', 'agent framework coding', 'agentic coding workflow',
    'Spec driven development AI', 'test driven AI coding', 'review driven development AI'
  ];

  const byId = new Map();
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  for (const q of queries) {
    for (let page = 1; page <= 7; page++) {
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
      await sleep(65);
    }
  }

  const weights = [
    ['output', 4], ['输出', 4], ['prompt', 3], ['提示词', 4], ['rules', 4], ['规则', 4],
    ['roo', 4], ['cline', 4], ['cursor', 4], ['windsurf', 4], ['qwen', 4], ['kimi', 4],
    ['gemini', 4], ['trae', 4], ['qoder', 4], ['amp', 4], ['kiro', 4], ['aider', 4],
    ['代码地图', 6], ['项目地图', 6], ['repo', 4], ['codebase', 5], ['deepwiki', 5], ['graphify', 5],
    ['测试', 5], ['验收', 5], ['playwright', 4], ['browser', 3], ['任务', 4], ['prd', 4],
    ['权限', 5], ['安全', 5], ['sandbox', 4], ['worktree', 4], ['质量', 4], ['重构', 4],
    ['文档', 4], ['小白', 4], ['成本', 5], ['token', 5], ['上下文', 5], ['长会话', 5],
    ['屎山', 4], ['翻车', 4], ['debug', 4], ['workflow', 5], ['agent', 4], ['skill', 4]
  ];
  const topics = [...byId.values()].map(t => {
    const text = (t.title + ' ' + (t.tags || []).map(x => x.name || x).join(' ') + ' ' + t.queries.join(' ')).toLowerCase();
    let score = t.queries.length * 3 + Math.min(12, (t.reply_count || 0) / 6) + Math.min(10, (t.like_count || 0) / 15) + Math.min(8, (t.views || 0) / 1800);
    for (const [k, w] of weights) if (text.includes(k.toLowerCase())) score += w;
    const groups = [];
    if (/output|输出|prompt|提示词|rules|规则|claude\.md|agents\.md/.test(text)) groups.push('提示词与规则');
    if (/roo|cline|cursor|windsurf|qwen|kimi|gemini|trae|qoder|amp|kiro|aider|devin/.test(text)) groups.push('平台与IDE');
    if (/代码地图|项目地图|repo|codebase|deepwiki|graphify|zread|ast|向量|检索|知识图谱/.test(text)) groups.push('代码库理解');
    if (/测试|验收|playwright|browser|e2e|webapp|verification|tdd/.test(text)) groups.push('测试与验收');
    if (/任务|prd|需求|产品经理|看板|拆解/.test(text)) groups.push('需求与任务管理');
    if (/权限|安全|sandbox|approval|危险/.test(text)) groups.push('安全与权限');
    if (/worktree|多分支|并行/.test(text)) groups.push('并行与分支');
    if (/成本|token|预算|长会话|上下文/.test(text)) groups.push('成本与上下文');
    if (/屎山|翻车|debug|重构|坏味道|补丁/.test(text)) groups.push('反思与风险');
    if (/skill|workflow|agent|mcp|cli/.test(text)) groups.push('Skill与工作流');
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
  throw "No round2 supplement result returned"
}

$rawPath = Join-Path $OutDir 'supplement_round2_topics_raw.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\supplement_round2_topics_raw.json', $jsonText, [Text.UTF8Encoding]::new($false))

$data = $jsonText | ConvertFrom-Json
$summary = [ordered]@{
  collected_at = $data.collected_at
  base_seen_count = $data.base_seen_count
  query_count = $data.query_count
  new_unique_count = $data.new_unique_count
  top_100 = @($data.topics | Select-Object -First 100)
}
$summaryPath = Join-Path $OutDir 'supplement_round2_topics_summary.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\supplement_round2_topics_summary.json', ($summary | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))

Write-Output "new_unique_count=$($data.new_unique_count)"
Write-Output "round2_raw=$rawPath"
Write-Output "round2_summary=$summaryPath"

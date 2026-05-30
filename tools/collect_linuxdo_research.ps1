param(
  [int]$Port = 9334,
  [int]$TargetCount = 220,
  [string]$OutDir = "output/linuxdo_skill_research"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$targets = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/list"
$page = $targets | Where-Object { $_.type -eq 'page' -and $_.url -like '*linux.do*' } | Select-Object -First 1
if (-not $page) {
  throw "未找到 linux.do 页面，请先打开带 CDP 的已登录 Chrome。"
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
    $buffer = New-Object byte[] 8388608
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

$js = @'
(async () => {
  const targetCount = __TARGET_COUNT__;
  const queries = [
    'skill','skills','skill creator','skill-creator','skills.sh','skill 管理','skill 工具','skill 开源','skill 推荐',
    'Codex skill','codex 工作流','codex 工具','codex 代码审查','codex review','codex 开源','codex agent',
    'Claude Code skill','Claude Code 工作流','Claude Code 技巧','Claude Code 配置','Claude Code 开源',
    'AI Coding 工作流','AI Coding 工具','AI 编程 工具','AI 编程 方案','AI 编程 总结','AI 编程 经验','AI 编程 公司',
    'Vibe Coding','VibeCoding','vibecoding','vibe coding 心得','vibe coding 反思','vibe coding 工具','vibe coding 架构',
    'harness engineering','harness skill','harness 工程','harness 工具','harness 工作流',
    'Trellis','Superpowers','GSD','BMAD','OpenSpec','CCG','Maestro','Aegis','OpenClaw','OpenMOSS',
    'MCP skill','MCP 工作流','MCP 工具','CLI skill','CLI 工作流',
    'Agent Skill 系统','Agent 工作流','agent 编程','agent 工具','long task agent','长任务 agent','长任务 skill',
    '架构 skill','架构师 skill','项目架构 skill','架构审查 AI','架构学习 AI','项目地图 AI','代码审查 skill',
    '上下文 管理 AI','记忆 系统 agent','memory skill','项目记忆 skill','handoff skill',
    '工具推荐 AI Coding','开源推广 skill','开源自荐 skill','工作流 skill','开发常用 skill'
  ];

  const byId = new Map();
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  for (const q of queries) {
    for (let page = 1; page <= 5; page++) {
      const url = '/search.json?q=' + encodeURIComponent(q) + '&page=' + page;
      let j;
      try {
        const r = await fetch(url, { credentials: 'include' });
        if (!r.ok) break;
        j = await r.json();
      } catch (error) {
        break;
      }
      const topics = j.topics || [];
      if (!topics.length) break;
      for (const t of topics) {
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
      if (byId.size >= targetCount && page >= 2) break;
      await sleep(80);
    }
  }

  const keywordWeights = [
    ['skill', 5], ['skills', 4], ['codex', 4], ['claude', 4], ['工作流', 5], ['workflow', 5],
    ['vibe', 4], ['harness', 5], ['trellis', 5], ['superpowers', 4], ['gsd', 3], ['openspec', 3],
    ['架构', 5], ['审查', 4], ['工具', 3], ['开源', 3], ['自荐', 3], ['推荐', 3], ['经验', 3],
    ['总结', 3], ['反思', 4], ['上下文', 4], ['记忆', 4], ['长任务', 4], ['agent', 4], ['mcp', 3], ['cli', 3]
  ];

  const topics = [...byId.values()].map(t => {
    const text = (t.title + ' ' + (t.tags || []).map(x => x.name || x).join(' ') + ' ' + t.queries.join(' ')).toLowerCase();
    let score = t.queries.length * 2 + Math.min(12, (t.reply_count || 0) / 8) + Math.min(8, (t.like_count || 0) / 20) + Math.min(6, (t.views || 0) / 2500);
    for (const [k, w] of keywordWeights) {
      if (text.includes(k.toLowerCase())) score += w;
    }
    const bucket = [];
    if (/skill|skills|技能/i.test(text)) bucket.push('skill');
    if (/codex|claude|cursor|qoder|trae|opencode|openclaw/i.test(text)) bucket.push('工具');
    if (/harness|trellis|superpowers|gsd|bmad|openspec|ccg|workflow|工作流/i.test(text)) bucket.push('工作流');
    if (/架构|审查|review|项目地图|上下文|记忆|long task|长任务/i.test(text)) bucket.push('架构与长任务');
    if (/开源|自荐|推广|项目|工具/i.test(text)) bucket.push('开源项目');
    if (/反思|心得|经验|总结|公司|推行/i.test(text)) bucket.push('经验反思');
    return { ...t, score: Math.round(score * 10) / 10, bucket };
  }).sort((a, b) => b.score - a.score);

  return JSON.stringify({
    collected_at: new Date().toISOString(),
    query_count: queries.length,
    unique_count: topics.length,
    queries,
    topics
  });
})()
'@

$js = $js.Replace('__TARGET_COUNT__', [string]$TargetCount)

$res = Send-Cdp 'Runtime.evaluate' @{ expression = $js; returnByValue = $true; awaitPromise = $true }
$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null

$jsonText = $res.result.result.value
if (-not $jsonText) {
  throw "CDP 没有返回采集结果。"
}

$topicsPath = Join-Path $OutDir 'topics_raw.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\topics_raw.json', $jsonText, [Text.UTF8Encoding]::new($false))

$data = $jsonText | ConvertFrom-Json
$summary = [ordered]@{
  collected_at = $data.collected_at
  query_count = $data.query_count
  unique_count = $data.unique_count
  top_30 = @($data.topics | Select-Object -First 30 | ForEach-Object {
    [ordered]@{
      id = $_.id
      title = $_.title
      score = $_.score
      bucket = $_.bucket
      url = $_.url
      queries = $_.queries
    }
  })
}

$summaryPath = Join-Path $OutDir 'topics_summary.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\topics_summary.json', ($summary | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))

Write-Output "unique_count=$($data.unique_count)"
Write-Output "topics_raw=$topicsPath"
Write-Output "topics_summary=$summaryPath"

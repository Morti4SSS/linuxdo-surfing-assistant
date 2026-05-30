param(
  [int]$Port = 9334,
  [int]$Limit = 220,
  [string]$InPath = "output/linuxdo_skill_research/topics_raw.json",
  [string]$OutDir = "output/linuxdo_skill_research"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InPath)) {
  throw "Input file not found: $InPath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$raw = Get-Content -LiteralPath $InPath -Encoding UTF8 -Raw | ConvertFrom-Json
$ids = @($raw.topics | Select-Object -First $Limit | ForEach-Object { [int]$_.id })

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

$idsJson = ($ids | ConvertTo-Json -Compress)
$js = @'
(async () => {
  const ids = __IDS__;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const strip = html => {
    const div = document.createElement('div');
    div.innerHTML = html || '';
    return (div.innerText || div.textContent || '').replace(/\s+/g, ' ').trim();
  };
  const classify = item => {
    const text = (item.title + ' ' + (item.tags || []).map(x => x.name || x).join(' ') + ' ' + item.first_text).toLowerCase();
    const groups = [];
    if (/skill|skills|技能|skill-creator|skills\.sh/.test(text)) groups.push('skill');
    if (/codex|claude|cursor|qoder|trae|opencode|openclaw|gemini|amp|工具|tool/.test(text)) groups.push('工具与平台');
    if (/harness|trellis|superpowers|gsd|bmad|openspec|ccg|workflow|工作流|流程/.test(text)) groups.push('工作流与harness');
    if (/架构|审查|review|项目地图|上下文|记忆|long task|长任务|handoff|context/.test(text)) groups.push('架构与长期项目');
    if (/开源|自荐|推广|github|项目|仓库/.test(text)) groups.push('开源项目');
    if (/反思|心得|经验|总结|公司|推行|小白|焦虑|选择|成本|token/.test(text)) groups.push('经验反思');
    return groups.length ? groups : ['其他'];
  };
  const out = [];
  for (const id of ids) {
    try {
      const r = await fetch(`/t/${id}.json`, { credentials: 'include' });
      if (!r.ok) {
        out.push({ id, error: r.status });
        continue;
      }
      const j = await r.json();
      const posts = j.post_stream?.posts || [];
      const first = posts.find(p => p.post_number === 1) || posts[0] || {};
      const replies = posts
        .filter(p => p.post_number !== 1)
        .sort((a, b) => (b.like_count || 0) - (a.like_count || 0))
        .slice(0, 8)
        .map(p => ({
          post_number: p.post_number,
          username: p.username,
          like_count: p.like_count || 0,
          text: strip(p.cooked).slice(0, 900)
        }));
      const firstText = strip(first.cooked).slice(0, 2500);
      const item = {
        id: j.id,
        title: j.title,
        url: `https://linux.do/t/${j.slug}/${j.id}`,
        tags: j.tags || [],
        posts_count: j.posts_count || 0,
        reply_count: j.reply_count || 0,
        views: j.views || 0,
        like_count: j.like_count || 0,
        created_at: j.created_at,
        bumped_at: j.bumped_at,
        first_username: first.username,
        first_like_count: first.like_count || 0,
        first_text: firstText,
        top_replies: replies
      };
      item.groups = classify(item);
      out.push(item);
      await sleep(90);
    } catch (error) {
      out.push({ id, error: String(error && error.message || error) });
    }
  }
  return JSON.stringify({ fetched_at: new Date().toISOString(), count: out.length, topics: out });
})()
'@

$js = $js.Replace('__IDS__', $idsJson)
$res = Send-Cdp 'Runtime.evaluate' @{ expression = $js; returnByValue = $true; awaitPromise = $true }
$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null

$jsonText = $res.result.result.value
if (-not $jsonText) {
  throw "No topic detail result returned"
}

$detailsPath = Join-Path $OutDir 'topic_details_top220.json'
[IO.File]::WriteAllText((Resolve-Path $OutDir).Path + '\topic_details_top220.json', $jsonText, [Text.UTF8Encoding]::new($false))

$data = $jsonText | ConvertFrom-Json
$groupRows = @()
foreach ($topic in $data.topics) {
  foreach ($group in $topic.groups) {
    $groupRows += [pscustomobject]@{ group = $group; id = $topic.id; title = $topic.title; url = $topic.url; likes = $topic.like_count; replies = $topic.reply_count }
  }
}
$groupRows | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutDir 'topic_groups_top220.json') -Encoding UTF8

Write-Output "detail_count=$($data.count)"
Write-Output "topic_details=$detailsPath"

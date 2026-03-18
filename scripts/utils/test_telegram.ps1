# test_telegram.ps1 — Telegram 양방향 통신 테스트
# Send, Receive, Decision 기능을 검증합니다.

# Read credentials from .env
$envFile = Join-Path (Split-Path $PSScriptRoot) ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env file not found at $envFile" -ForegroundColor Red; exit 1
}
$envContent = Get-Content $envFile | Where-Object { $_ -match '=' -and $_ -notmatch '^\s*#' }
$envMap = @{}
foreach ($line in $envContent) { $p = $line -split '=', 2; $envMap[$p[0].Trim()] = $p[1].Trim() }
$tgToken  = $envMap['TELEGRAM_TOKEN']
$tgChatId = $envMap['TELEGRAM_CHAT_ID']
$tgBaseUrl = "https://api.telegram.org/bot$tgToken"
$script:tgOffset = 0
$pass = 0; $fail = 0; $total = 0

function Test-Result($name, $ok, $detail = "") {
    $script:total++
    if ($ok) { $script:pass++; Write-Host "[PASS] $name $detail" -ForegroundColor Green }
    else     { $script:fail++; Write-Host "[FAIL] $name $detail" -ForegroundColor Red }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Telegram v4 Communication Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ============================================================
# T1: Send-Telegram 기본 전송
# ============================================================
Write-Host "--- T1: Basic Send ---"
try {
    $body = @{ chat_id = $tgChatId; text = "[TEST] T1: Basic send test`nTimestamp: $(Get-Date -Format 'HH:mm:ss')" }
    $resp = Invoke-RestMethod -Uri "$tgBaseUrl/sendMessage" -Method Post -Body $body -TimeoutSec 10
    Test-Result "T1: Basic Send" $resp.ok "message_id=$($resp.result.message_id)"
} catch {
    Test-Result "T1: Basic Send" $false "$_"
}

# ============================================================
# T2: Flush (소진) 기능
# ============================================================
Write-Host "`n--- T2: Flush Old Updates ---"
try {
    $resp = Invoke-RestMethod -Uri "$tgBaseUrl/getUpdates?timeout=0" -TimeoutSec 5
    if ($resp.ok -and $resp.result.Count -gt 0) {
        $script:tgOffset = ($resp.result | Select-Object -Last 1).update_id + 1
        Test-Result "T2: Flush" $true "flushed $($resp.result.Count) updates, offset=$($script:tgOffset)"
    } else {
        Test-Result "T2: Flush" $true "no pending updates"
    }
} catch {
    Test-Result "T2: Flush" $false "$_"
}

# ============================================================
# T3: Parse-AnalysisGrade 테스트
# ============================================================
Write-Host "`n--- T3: Parse Analysis Grade ---"
$sampleText = @"
Current Iteration: 3,000 / 15,000
Mean Reward: -12.3
Reward Trend: ↘ (-15.2%)

  종합 등급: D (기립/균형 학습 중) (점수: 2/13)
"@

$result = @{ Grade = "N/A"; Score = 0; Reward = 0; Iter = 0; Trend = "N/A"; GradeLetter = "?" }
# Unicode escapes for .NET regex: \uc885\ud569=종합, \ub4f1\uae09=등급, \uc810\uc218=점수
if ($sampleText -match '\uc885\ud569\s+\ub4f1\uae09:\s*(\w)\s+\(([^)]+)\)\s+\(\uc810\uc218:\s*(\d+)/13\)') {
    $result.GradeLetter = $Matches[1]
    $result.Grade = "$($Matches[1]) ($($Matches[2]))"
    $result.Score = [int]$Matches[3]
}
if ($sampleText -match 'Mean Reward:\s*([-\d.]+)') { $result.Reward = [double]$Matches[1] }
if ($sampleText -match 'Current Iteration:\s*([\d,]+)') { $result.Iter = [int]($Matches[1] -replace ',','') }
if ($sampleText -match 'Reward Trend:\s*(.+)') { $result.Trend = $Matches[1].Trim() }

Test-Result "T3a: GradeLetter" ($result.GradeLetter -eq "D") "got: $($result.GradeLetter)"
Test-Result "T3b: Score" ($result.Score -eq 2) "got: $($result.Score)"
Test-Result "T3c: Reward" ($result.Reward -eq -12.3) "got: $($result.Reward)"
Test-Result "T3d: Iter" ($result.Iter -eq 3000) "got: $($result.Iter)"
Test-Result "T3e: Trend" ($result.Trend -like "*-15.2*") "got: $($result.Trend)"
Test-Result "T3f: Grade" ($result.Grade -like "*D*") "got: $($result.Grade)"

# ============================================================
# T4: 의사결정 시뮬레이션 (실제 텔레그램 양방향)
# ============================================================
Write-Host "`n--- T4: Interactive Decision (실제 양방향 테스트) ---"
Write-Host "텔레그램으로 질문을 보냅니다. 폰에서 '1' 또는 '2'로 답해주세요." -ForegroundColor Yellow
Write-Host "60초 내 응답 없으면 자동으로 타임아웃 테스트로 진행합니다." -ForegroundColor Yellow
Write-Host ""

# Flush before asking
try {
    $flush = Invoke-RestMethod -Uri "$tgBaseUrl/getUpdates?timeout=0" -TimeoutSec 5
    if ($flush.ok -and $flush.result.Count -gt 0) {
        $script:tgOffset = ($flush.result | Select-Object -Last 1).update_id + 1
    }
} catch {}

# Send question
$question = "[TEST] 의사결정 테스트`nClip #99 분석완료`nIter: 3000/15000`nReward: -12.3`n등급: D (기립/균형 학습 중) (2/13점)`n`n어떻게 할까요?`n1 - 계속 진행`n2 - 훈련 중단`n`n60초 내 응답 없으면 자동: 1 (계속)`n(숫자만 입력: 1 또는 2)"
try {
    $body = @{ chat_id = $tgChatId; text = $question }
    Invoke-RestMethod -Uri "$tgBaseUrl/sendMessage" -Method Post -Body $body -TimeoutSec 10 | Out-Null
    Write-Host "질문 전송 완료. 폰에서 응답 대기 중... (60초)" -ForegroundColor Cyan
} catch {
    Test-Result "T4: Send Question" $false "$_"
}

# Poll for reply (60 seconds for test)
$testTimeout = 60
$deadline = (Get-Date).AddSeconds($testTimeout)
$reply = $null
while ((Get-Date) -lt $deadline) {
    try {
        $url = "$tgBaseUrl/getUpdates?offset=$($script:tgOffset)&timeout=5"
        $resp = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 10
        if ($resp.ok -and $resp.result.Count -gt 0) {
            foreach ($update in $resp.result) {
                $script:tgOffset = $update.update_id + 1
                $text = $update.message.text
                if ($text -and $update.message.chat.id -eq [long]$tgChatId) {
                    $reply = $text.Trim()
                    break
                }
            }
            if ($reply) { break }
        }
    } catch { Start-Sleep 2 }
    $remaining = [int](($deadline - (Get-Date)).TotalSeconds)
    if ($remaining % 15 -lt 6) { Write-Host "  대기 중... ${remaining}초 남음" -ForegroundColor DarkGray }
}

if ($reply) {
    $validReply = $reply -match '^[12]$|continue|stop'
    Test-Result "T4a: Reply Received" $true "reply='$reply'"
    Test-Result "T4b: Valid Response" $validReply "parsed='$reply'"

    # Confirm back
    $confirmMsg = if ($reply -match '^1$|continue') { "[TEST OK] continue selected" } 
                  elseif ($reply -match '^2$|stop') { "[TEST OK] stop selected" }
                  else { "[TEST OK] reply received: $reply (default: continue)" }
    $body = @{ chat_id = $tgChatId; text = $confirmMsg }
    Invoke-RestMethod -Uri "$tgBaseUrl/sendMessage" -Method Post -Body $body -TimeoutSec 10 | Out-Null
} else {
    Test-Result "T4a: Timeout Auto-Decision" $true "60초 타임아웃 → 자동 계속"
    $body = @{ chat_id = $tgChatId; text = "[TEST] 응답 없음 → 자동: 계속 진행 (타임아웃 정상 작동)" }
    Invoke-RestMethod -Uri "$tgBaseUrl/sendMessage" -Method Post -Body $body -TimeoutSec 10 | Out-Null
}

# ============================================================
# SUMMARY
# ============================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  $pass PASS / $fail FAIL / $total TOTAL" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
if ($fail -eq 0) { Write-Host "  ALL TESTS PASSED" -ForegroundColor Green }
Write-Host "========================================`n" -ForegroundColor Cyan

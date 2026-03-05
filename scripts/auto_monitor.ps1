# V17.1 Auto Training Monitor v4 (Telegram Interactive)
# 3시간마다 훈련 중단 → 영상 녹화 → 상세 분석 → 텔레그램 보고/의사결정 → 훈련 재개
# v4 (Telegram):
#   [T1] 텔레그램 양방향 통신 — 진행상황 알림 + 의사결정 요청
#   [T2] 10분 응답대기 → 타임아웃 시 자동 판단 (계속 진행)
#   [T3] 분석결과 파싱 (등급/점수/reward/trend) → 상황 판단
#   [T4] 등급 D/F 또는 점수 하락 시 사용자에게 선택지 제시
# v3 base:
#   Phase별 try-catch, GPU메모리기준 Wait-GpuFree, 분석타임아웃 120s
#   conda activate (no conda run), Kill-AllPython 단순화, Ensure-GpuClean 통합
#   메인루프 외부 try-catch, 타임아웃 프로세스 강제 kill
# Usage: powershell -ExecutionPolicy Bypass -File scripts\auto_monitor.ps1

param(
    [int]$IntervalMinutes = 180,
    [int]$VideoLength = 250,
    [int]$PlayEnvs = 50,
    [int]$TrainEnvs = 24576,
    [int]$MaxIterations = 15000,
    [string]$Task = "Isaac-Velocity-Flat-SpotMicro-v0",
    [string]$IsaacLab = "C:\IsaacLab\isaaclab.bat",
    [string]$ProjectRoot = "D:\project\spot_micro_rl"
)

$ErrorActionPreference = "Continue"
$logBase = "$ProjectRoot\logs\rsl_rl\spot_micro_flat"
$monitorLog = "$ProjectRoot\logs\monitor_log.txt"
$analyzeScript = "$ProjectRoot\scripts\analyze_training.py"

# TELEGRAM CONFIG
$tgToken   = "***REDACTED_TOKEN***"
$tgChatId  = "***REDACTED_ID***"
$tgBaseUrl = "https://api.telegram.org/bot$tgToken"
$script:tgOffset = 0
$script:lastAnalysisText = ""
$script:prevScore = -1
$DecisionTimeoutSec = 600  # 10분

# ============================================================
# UTILITY
# ============================================================

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $monitorLog -Value $line
}

function Send-Telegram($msg) {
    try {
        $body = @{ chat_id = $tgChatId; text = $msg }
        Invoke-RestMethod -Uri "$tgBaseUrl/sendMessage" -Method Post -Body $body -TimeoutSec 10 -ErrorAction SilentlyContinue | Out-Null
        $preview = $msg.Substring(0, [Math]::Min(60, $msg.Length)) -replace "`n", " "
        Write-Log "[TG] Sent: $preview..."
    } catch { Write-Log "[TG] Send failed: $_" }
}

function Flush-TelegramUpdates {
    try {
        $resp = Invoke-RestMethod -Uri "$tgBaseUrl/getUpdates?timeout=0" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($resp.ok -and $resp.result.Count -gt 0) {
            $script:tgOffset = ($resp.result | Select-Object -Last 1).update_id + 1
        }
    } catch {}
}

function Get-TelegramReply([int]$timeoutSec = 600) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $url = "$tgBaseUrl/getUpdates?offset=$($script:tgOffset)&timeout=10"
            $resp = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 15 -ErrorAction SilentlyContinue
            if ($resp.ok -and $resp.result.Count -gt 0) {
                foreach ($update in $resp.result) {
                    $script:tgOffset = $update.update_id + 1
                    $text = $update.message.text
                    if ($text -and $update.message.chat.id -eq [long]$tgChatId) {
                        Write-Log "[TG] Reply received: $text"
                        return $text.Trim()
                    }
                }
            }
        } catch { Start-Sleep 5 }
        $remaining = [int](($deadline - (Get-Date)).TotalSeconds)
        if ($remaining -gt 0 -and $remaining % 60 -lt 15) {
            Write-Log "[TG] Waiting reply... ${remaining}s left"
        }
    }
    Write-Log "[TG] Reply timeout (${timeoutSec}s)"
    return $null
}

function Ask-UserDecision([string]$situation, [string]$default = "continue") {
    Flush-TelegramUpdates  # 이전 메시지 소진
    $autoLabel = if ($default -eq 'continue') { '1 (계속)' } else { '2 (중단)' }
    $question = "$situation`n`n🤔 어떻게 할까요?`n1️⃣ 계속 진행`n2️⃣ 훈련 중단`n`n⏰ ${DecisionTimeoutSec}초 내 응답 없으면 자동: $autoLabel`n(숫자만 입력: 1 또는 2)"
    Send-Telegram $question
    Write-Log "Decision requested (timeout: ${DecisionTimeoutSec}s, default: $default)"

    $reply = Get-TelegramReply -timeoutSec $DecisionTimeoutSec
    if ($null -eq $reply) {
        $autoMsg = if ($default -eq 'continue') { '계속 진행' } else { '중단' }
        Send-Telegram "🤖 응답 없음 → 자동: $autoMsg"
        Write-Log "No reply → default: $default"
        return $default
    }
    switch -Regex ($reply) {
        '^1$|continue|go|yes|ok' {
            Send-Telegram "✅ 계속 진행합니다."
            return "continue"
        }
        '^2$|stop|no|quit' {
            Send-Telegram "🛑 훈련을 중단합니다."
            return "stop"
        }
        default {
            $defLabel = if ($default -eq 'continue') { 'continue' } else { 'stop' }
            Send-Telegram "❓ '$reply' → 기본값: $defLabel"
            return $default
        }
    }
}

function Parse-AnalysisGrade([string]$text) {
    $result = @{ Grade = "N/A"; Score = 0; Reward = 0; Iter = 0; Trend = "N/A"; GradeLetter = "?" }
    if (-not $text) { return $result }
    # Unicode escapes: 종합=종합, 등급=등급, 점수=점수
    if ($text -match '\uc885\ud569\s+\ub4f1\uae09:\s*(\w)\s+\(([^)]+)\)\s+\(\uc810\uc218:\s*(\d+)/13\)') {
        $result.GradeLetter = $Matches[1]
        $result.Grade = "$($Matches[1]) ($($Matches[2]))"
        $result.Score = [int]$Matches[3]
    }
    if ($text -match 'Mean Reward:\s*([-\d.]+)') {
        $result.Reward = [double]$Matches[1]
    }
    if ($text -match 'Current Iteration:\s*([\d,]+)') {
        $result.Iter = [int]($Matches[1] -replace ',','')
    }
    if ($text -match 'Reward Trend:\s*(.+)') {
        $result.Trend = $Matches[1].Trim()
    }
    return $result
}

function Get-LatestRunDir {
    Get-ChildItem $logBase -Directory | Sort-Object Name | Select-Object -Last 1
}

function Get-LatestCheckpoint($runDir) {
    Get-ChildItem "$($runDir.FullName)\model_*.pt" -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -match '^model_\d+$' } |
        Sort-Object { [int]($_.BaseName -replace 'model_','') } |
        Select-Object -Last 1
}

# ============================================================
# RESOURCE CLEANUP
# ============================================================

function Kill-AllPython {
    param([string]$reason = "cleanup")
    Write-Log "[$reason] Killing python/Kit processes..."
    @("python", "python3", "Kit") | ForEach-Object {
        Stop-Process -Name $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 5
    $remaining = Get-Process python -ErrorAction SilentlyContinue
    if ($remaining) {
        Write-Log "[$reason] $($remaining.Count) python remaining → taskkill"
        $remaining | ForEach-Object { taskkill /F /PID $_.Id 2>$null | Out-Null }
        Start-Sleep -Seconds 5
    }
    Write-Log "[$reason] Process cleanup done."
}

function Wait-GpuFree {
    param([int]$maxWaitSec = 60, [int]$thresholdMB = 2000)
    for ($i = 0; $i -lt $maxWaitSec; $i += 5) {
        try {
            $memMB = [int](nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null).Trim()
            if ($memMB -lt $thresholdMB) {
                Write-Log "GPU free: ${memMB}MB (< ${thresholdMB}MB). Ready."
                return $true
            }
            Write-Log "GPU: ${memMB}MB, waiting... ($i/${maxWaitSec}s)"
        } catch {
            Write-Log "nvidia-smi failed, assuming clean."
            return $true
        }
        Start-Sleep -Seconds 5
    }
    Write-Log "WARNING: GPU still above ${thresholdMB}MB after ${maxWaitSec}s."
    return $false
}

function Ensure-GpuClean {
    param([string]$reason = "cleanup")
    Kill-AllPython -reason $reason
    $ok = Wait-GpuFree -maxWaitSec 60 -thresholdMB 2000
    if (-not $ok) {
        Write-Log "[$reason] Retry kill + wait..."
        Kill-AllPython -reason "$reason-retry"
        Start-Sleep -Seconds 10
        Wait-GpuFree -maxWaitSec 30 -thresholdMB 2000 | Out-Null
    }
}

# ============================================================
# VIDEO RECORDING
# ============================================================

function Record-Video($checkpointPath, $runDir, $clipNum) {
    Write-Log "Recording clip #$clipNum from: $($checkpointPath.Name)"
    $playCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\play.py --task=$Task --num_envs=$PlayEnvs --checkpoint=`"$($checkpointPath.FullName)`" --video --video_length=$VideoLength"
    $proc = Start-Process powershell -ArgumentList "-Command", $playCmd -PassThru -NoNewWindow
    $timeout = 480; $elapsed = 0
    while (-not $proc.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep 10; $elapsed += 10
        if ($elapsed % 60 -eq 0) { Write-Log "  Recording... ${elapsed}s" }
    }
    if (-not $proc.HasExited) {
        Write-Log "WARNING: Play timed out (${timeout}s), killing PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Ensure-GpuClean -reason "post-recording"

    $latestVideo = Get-ChildItem "$($runDir.FullName)\videos\play\*.mp4" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($latestVideo) {
        $iterNum = $checkpointPath.BaseName -replace 'model_',''
        $newName = "clip_${clipNum}_iter${iterNum}_$(Get-Date -Format 'yyyyMMdd_HHmmss').mp4"
        $destPath = "$($runDir.FullName)\videos\$newName"
        Copy-Item $latestVideo.FullName $destPath -ErrorAction SilentlyContinue
        $sizeMB = [math]::Round($latestVideo.Length / 1MB, 1)
        Write-Log "Video saved: $newName (${sizeMB}MB)"
        return $destPath
    }
    Write-Log "WARNING: No video file found!"
    return $null
}

# ============================================================
# ANALYSIS — conda activate + isaaclab.bat -p + 타임아웃 120s
# ============================================================

function Run-DetailedAnalysis($runDir, $checkpoint, $clipNum, $videoPath) {
    $iterNum = $checkpoint.BaseName -replace 'model_',''
    Write-Log "Running analysis (iter $iterNum)..."

    $header = @"

################################################################################
#  CLIP #$clipNum — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
#  model_${iterNum}.pt | $($runDir.Name)
#  Video: $(if($videoPath) { Split-Path $videoPath -Leaf } else { 'N/A' })
################################################################################
"@
    Add-Content -Path $monitorLog -Value $header

    if (-not (Test-Path $analyzeScript)) {
        Write-Log "analyze_training.py not found → basic analysis"
        Write-BasicAnalysis $runDir $iterNum
        return
    }

    $stdoutFile = "$ProjectRoot\logs\_analysis_out.txt"
    $stderrFile = "$ProjectRoot\logs\_analysis_err.txt"
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

    $cmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $analyzeScript --run_dir `"$($runDir.FullName)`" --clip_num $clipNum"
    $proc = Start-Process powershell -ArgumentList "-Command", $cmd `
        -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    if (-not $proc.WaitForExit(120000)) {
        Write-Log "WARNING: Analysis timed out (120s), killing PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep 3
    }

    if (Test-Path $stdoutFile) {
        $text = Get-Content $stdoutFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($text) {
            Write-Host $text
            Add-Content -Path $monitorLog -Value $text
            $script:lastAnalysisText = $text
        } else {
            $script:lastAnalysisText = ""
        }
        Remove-Item $stdoutFile -ErrorAction SilentlyContinue
    }
    if (Test-Path $stderrFile) {
        $err = Get-Content $stderrFile -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($err -and $err.Trim()) {
            Write-Log "Analysis stderr: $($err.Substring(0, [Math]::Min(500, $err.Length)))"
        }
        Remove-Item $stderrFile -ErrorAction SilentlyContinue
    }
    Write-Log "Analysis complete."

    # 분석용 python 잔존 시 정리 (GPU 미사용이므로 가볍게)
    Start-Sleep 2
    if (Get-Process python -ErrorAction SilentlyContinue) {
        Write-Log "Cleaning leftover analysis python..."
        Stop-Process -Name python -Force -ErrorAction SilentlyContinue
        Start-Sleep 3
    }
}

function Write-BasicAnalysis($runDir, $iterNum) {
    $ev = Get-ChildItem "$($runDir.FullName)\events*" -ErrorAction SilentlyContinue | Select-Object -First 1
    $evKB = if ($ev) { [math]::Round($ev.Length / 1KB) } else { 0 }
    $cpCount = (Get-ChildItem "$($runDir.FullName)\model_*.pt" -ErrorAction SilentlyContinue).Count
    $info = "[Basic] Events: ${evKB}KB | Checkpoints: $cpCount | Iter: ~$iterNum"
    Add-Content -Path $monitorLog -Value $info
    Write-Host $info
}

# ============================================================
# TRAINING RESUME
# ============================================================

function Resume-Training($runDir, $checkpoint) {
    $runName = $runDir.Name
    $cpName = $checkpoint.Name
    $iterNum = [int]($checkpoint.BaseName -replace 'model_','')

    Write-Log "Pre-resume cleanup..."
    Ensure-GpuClean -reason "pre-resume"

    Write-Log "Resuming: $runName / $cpName (iter $iterNum)"
    $trainCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\train.py --task=$Task --num_envs=$TrainEnvs --headless --max_iterations=$MaxIterations --resume --load_run=$runName --checkpoint=$cpName"
    Start-Process powershell -ArgumentList "-Command", $trainCmd -NoNewWindow

    Write-Log "Waiting for init (60s)..."
    Start-Sleep 60
    $p = Get-Process python -ErrorAction SilentlyContinue
    if ($p) {
        $mem = [math]::Round(($p | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
        Write-Log "Training running: PID=$($p.Id -join ','), Mem=${mem}MB"
    } else {
        Write-Log "WARNING: Training process not detected!"
        Send-Telegram "⚠️ 훈련 프로세스 감지 실패! 확인 필요"
    }

    Start-Sleep 30
    try {
        $gm = [int](nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null).Trim()
        Write-Log "GPU after resume: ${gm}MB"
    } catch {}

    Write-Log "Next check in $IntervalMinutes min."
}

# ============================================================
# MAIN LOOP — Phase별 try-catch + 비상 훈련 재개
# ============================================================

Write-Log "========================================="
Write-Log "V17.1 Auto Monitor v4 (Telegram Interactive)"
Write-Log "Phase에러격리 | GPU메모리기준 | 분석타임아웃"
Write-Log "Interval: ${IntervalMinutes}min | Video: ${VideoLength}steps"
Write-Log "Train: $TrainEnvs envs | Play: $PlayEnvs envs"
Write-Log "========================================="

Flush-TelegramUpdates
Send-Telegram "🤖 SpotMicro Monitor v4 시작`n`n⚙️ 설정`n├ Interval: ${IntervalMinutes}min`n├ Envs: $TrainEnvs`n├ Video: ${VideoLength}steps`n├ Max: $MaxIterations iter`n└ 의사결정 타임아웃: ${DecisionTimeoutSec}초`n`n📢 등급 D/F 시 텔레그램으로 물어봅니다`n10분 무응답 → 자동 계속"

$clipNum = 0

while ($true) {
    Write-Log "Sleeping $IntervalMinutes min..."
    Start-Sleep -Seconds ($IntervalMinutes * 60)
    $clipNum++
    Write-Log ""
    Write-Log "########## CLIP #$clipNum ##########"

    $videoPath = $null; $runDir = $null; $checkpoint = $null

    try {
        $runDir = Get-LatestRunDir
        if (-not $runDir) { Write-Log "ERROR: No run found!"; continue }
        $checkpoint = Get-LatestCheckpoint $runDir
        if (-not $checkpoint) { Write-Log "ERROR: No checkpoint!"; continue }
        $iterNum = [int]($checkpoint.BaseName -replace 'model_','')
        Write-Log "Found: $($runDir.Name) / $($checkpoint.Name) (iter $iterNum)"
        $progressPctMain = [math]::Round(($iterNum / $MaxIterations) * 100, 1)
        Send-Telegram "🎬 Clip #$clipNum 시작`n├ 📍 Iter: $iterNum / $MaxIterations ($progressPctMain%)`n└ 📂 $($runDir.Name) / $($checkpoint.Name)"

        # 훈련 완료 체크
        if ($iterNum -ge ($MaxIterations - 100)) {
            Write-Log "===== TRAINING COMPLETE (iter $iterNum) ====="
            Send-Telegram "🏆 훈련 완료! (iter $iterNum/$MaxIterations)`n최종 분석 진행합니다..."
            try { Ensure-GpuClean -reason "complete" } catch {}
            try { $videoPath = Record-Video $checkpoint $runDir $clipNum } catch { Write-Log "Video err: $_" }
            $script:lastAnalysisText = ""
            try { Run-DetailedAnalysis $runDir $checkpoint $clipNum $videoPath } catch { Write-Log "Analysis err: $_" }
            try { Ensure-GpuClean -reason "final" } catch {}
            try {
                $grade = Parse-AnalysisGrade $script:lastAnalysisText
                Send-Telegram "🏆 최종 결과`n`n📊 등급: $($grade.Grade)`n🎯 점수: $($grade.Score)/13`n💰 Reward: $($grade.Reward)`n📈 Trend: $($grade.Trend)`n`n✅ 모니터 종료"
            } catch { Send-Telegram "✅ 훈련 완료. 모니터 종료." }
            Write-Log "===== MONITOR FINISHED ====="; break
        }

        # Phase 1: 훈련 중단 + GPU 해제
        Write-Log "--- Phase 1/5: Stop Training ---"
        Send-Telegram "⏸️ P1/5: 훈련 중단 + GPU 해제"
        try { Ensure-GpuClean -reason "stop-training" }
        catch { Write-Log "P1 err: $_ (fallback)"; Kill-AllPython -reason "p1-fb"; Start-Sleep 10 }

        # Phase 2: 영상 녹화
        Write-Log "--- Phase 2/5: Record Video ---"
        Send-Telegram "🎥 P2/5: 영상 녹화 중... (${VideoLength} steps)"
        try { $videoPath = Record-Video $checkpoint $runDir $clipNum }
        catch { Write-Log "P2 err: $_ (skip)"; Kill-AllPython -reason "p2-fb"; Wait-GpuFree -maxWaitSec 30 | Out-Null }

        # Phase 3: 상세 분석
        Write-Log "--- Phase 3/5: Analysis ---"
        Send-Telegram "🔬 P3/5: 분석 중..."
        $script:lastAnalysisText = ""
        try { Run-DetailedAnalysis $runDir $checkpoint $clipNum $videoPath }
        catch { Write-Log "P3 err: $_ (skip)" }

        # Telegram 보고 + 의사결정
        Write-Log "--- Telegram Report & Decision ---"
        try {
            $grade = Parse-AnalysisGrade $script:lastAnalysisText
            $progressPct = if ($grade.Iter -gt 0) { [math]::Round(($grade.Iter / $MaxIterations) * 100, 1) } else { "?" }
            $gradeIcon = switch ($grade.GradeLetter) {
                'A' { '🌟' } 'B' { '⭐' } 'C' { '🟡' } 'D' { '🟠' } 'F' { '🔴' } default { '❓' }
            }
            $trendIcon = if ($grade.Trend -match '↗|상승|\+') { '📈' } elseif ($grade.Trend -match '↘|하락|-') { '📉' } else { '➖' }
            $summaryMsg = "📊 Clip #$clipNum 분석완료`n`n📍 Iter: $($grade.Iter) / $MaxIterations ($progressPct%)`n💰 Reward: $($grade.Reward)`n$trendIcon Trend: $($grade.Trend)`n$gradeIcon 등급: $($grade.Grade) ($($grade.Score)/13점)"

            # 등급 D/F → 사용자에게 결정 요청
            if ($grade.GradeLetter -in @("D", "F") -and $grade.Iter -gt 500) {
                $decision = Ask-UserDecision -situation "⚠️ $summaryMsg`n`n🔴 등급 $($grade.GradeLetter) — 훈련 상태 좋지 않습니다."
                if ($decision -eq "stop") {
                    Write-Log "User requested STOP."
                    Send-Telegram "🛑 사용자 요청으로 훈련 중단."
                    Ensure-GpuClean -reason "user-stop"
                    break
                }
            # 점수 하락 + 낮은 점수 → 사용자에게 결정 요청
            } elseif ($script:prevScore -ge 0 -and $grade.Score -lt $script:prevScore -and $grade.Score -lt 4) {
                $decision = Ask-UserDecision -situation "⚠️ $summaryMsg`n`n📉 점수 하락 ($($script:prevScore) → $($grade.Score))"
                if ($decision -eq "stop") {
                    Write-Log "User requested STOP (score drop)."
                    Send-Telegram "🛑 사용자 요청으로 훈련 중단 (점수하락)."
                    Ensure-GpuClean -reason "user-stop"
                    break
                }
            # 정상 → 알림만
            } else {
                Send-Telegram "✅ $summaryMsg"
            }
            $script:prevScore = $grade.Score
        } catch { Write-Log "Telegram report err: $_ (skip)" }

        # Phase 4: 최종 정리
        Write-Log "--- Phase 4/5: Cleanup ---"
        Send-Telegram "🧹 P4/5: GPU 정리 중..."
        try { Ensure-GpuClean -reason "pre-resume" }
        catch { Write-Log "P4 err: $_"; Kill-AllPython -reason "p4-fb"; Start-Sleep 15 }

        Start-Sleep 5

        # Phase 5: 훈련 재개 (반드시 실행)
        Write-Log "--- Phase 5/5: Resume Training ---"
        Send-Telegram "▶️ P5/5: 훈련 재개 중... (iter $iterNum~)`n다음 체크: ${IntervalMinutes}분 후"
        Resume-Training $runDir $checkpoint

    } catch {
        # 메인 루프 예외 → 비상 훈련 재개
        Write-Log "CRITICAL: $_"
        Send-Telegram "🚨 CRITICAL ERROR`n$($_)`n`n비상 훈련 재개 시도 중..."
        Write-Log "Emergency resume..."
        try {
            Kill-AllPython -reason "emergency"; Start-Sleep 15
            $er = if ($runDir) { $runDir } else { Get-LatestRunDir }
            $ec = if ($checkpoint) { $checkpoint } else { Get-LatestCheckpoint $er }
            if ($er -and $ec) { Resume-Training $er $ec }
            else { Write-Log "FATAL: Cannot find run/checkpoint for emergency resume!" }
        } catch { Write-Log "FATAL: Emergency resume failed: $_" }
    }

    Write-Log "########## CLIP #$clipNum DONE ##########"
    Write-Log ""
}
Send-Telegram "👋 모니터 종료. 수고하셨습니다!"
Write-Log "Monitor exiting."

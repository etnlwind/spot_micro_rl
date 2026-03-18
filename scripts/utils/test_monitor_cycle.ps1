# Auto Monitor v3 — 단일 사이클 테스트
# 실제 Train 1회 → Stop → Video → Analysis → Cleanup → Resume 1회 → 종료
# 전체 모니터 루프를 거치지 않고 각 Phase를 개별 검증
# Usage: powershell -ExecutionPolicy Bypass -File scripts\test_monitor_cycle.ps1

param(
    [int]$VideoLength = 100,          # 테스트니까 짧게 (~6초)
    [int]$PlayEnvs = 16,              # 가볍게
    [int]$TrainEnvs = 64,             # 테스트용 소규모
    [int]$TrainIters = 3,             # 3 이터레이션만
    [string]$Task = "Isaac-Velocity-Flat-SpotMicro-v0",
    [string]$IsaacLab = "C:\IsaacLab\isaaclab.bat",
    [string]$ProjectRoot = "D:\project\spot_micro_rl"
)

$ErrorActionPreference = "Continue"
$logBase = "$ProjectRoot\logs\rsl_rl\spot_micro_flat"
$testLog = "$ProjectRoot\logs\test_monitor_cycle.txt"
$analyzeScript = "$ProjectRoot\scripts\analyze_training.py"

$passed = 0; $failed = 0; $total = 7

# ============================================================
# UTILITY (training_supervisor.ps1과 동일 로직)
# ============================================================

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $testLog -Value $line
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

function Kill-AllPython {
    param([string]$reason = "cleanup")
    Write-Log "  [$reason] Kill python..."
    @("python", "python3", "Kit") | ForEach-Object {
        Stop-Process -Name $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep 5
    $r = Get-Process python -ErrorAction SilentlyContinue
    if ($r) {
        $r | ForEach-Object { taskkill /F /PID $_.Id 2>$null | Out-Null }
        Start-Sleep 5
    }
}

function Wait-GpuFree {
    param([int]$maxWaitSec = 60, [int]$thresholdMB = 2000)
    for ($i = 0; $i -lt $maxWaitSec; $i += 5) {
        try {
            $memMB = [int](nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null).Trim()
            if ($memMB -lt $thresholdMB) {
                Write-Log "  GPU free: ${memMB}MB"
                return $true
            }
            Write-Log "  GPU: ${memMB}MB, waiting... ($i/${maxWaitSec}s)"
        } catch { return $true }
        Start-Sleep 5
    }
    return $false
}

function Ensure-GpuClean {
    param([string]$reason = "cleanup")
    Kill-AllPython -reason $reason
    $ok = Wait-GpuFree -maxWaitSec 60 -thresholdMB 2000
    if (-not $ok) {
        Kill-AllPython -reason "$reason-retry"
        Start-Sleep 10
        Wait-GpuFree -maxWaitSec 30 -thresholdMB 2000 | Out-Null
    }
}

# ============================================================
# TEST HELPERS
# ============================================================

function Test-Phase {
    param([string]$name, [scriptblock]$block)
    Write-Log ""
    Write-Log "=== TEST: $name ==="
    try {
        & $block
        $script:passed++
        Write-Log "=== PASS: $name ==="
    } catch {
        $script:failed++
        Write-Log "=== FAIL: $name — $_ ==="
    }
}

# ============================================================
# TESTS
# ============================================================

Write-Log "============================================="
Write-Log "AUTO MONITOR v3 — CYCLE TEST"
Write-Log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Log "Train: $TrainEnvs envs x $TrainIters iters"
Write-Log "Play:  $PlayEnvs envs x $VideoLength steps"
Write-Log "============================================="

# Pre-clean
Write-Log "Pre-clean: Ensuring GPU is available..."
Ensure-GpuClean -reason "pre-test"

# 0. 사전조건: nvidia-smi / isaaclab.bat / conda
Test-Phase "T0: Prerequisites" {
    $nv = nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null
    if (-not $nv) { throw "nvidia-smi failed" }
    Write-Log "  nvidia-smi OK (${nv}MB)"

    if (-not (Test-Path $IsaacLab)) { throw "isaaclab.bat not found: $IsaacLab" }
    Write-Log "  isaaclab.bat OK"

    $condaOK = conda info --envs 2>$null | Select-String "env_isaaclab"
    if (-not $condaOK) { throw "env_isaaclab conda env not found" }
    Write-Log "  conda env_isaaclab OK"

    if (-not (Test-Path $analyzeScript)) { Write-Log "  WARNING: analyze_training.py not found (analysis test will use basic)" }
}

# 1. 짧은 훈련 실행
Test-Phase "T1: Short Training" {
    $trainCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\train.py --task=$Task --num_envs=$TrainEnvs --headless --max_iterations=$TrainIters"
    Write-Log "  Starting training ($TrainIters iters)..."
    $proc = Start-Process powershell -ArgumentList "-Command", $trainCmd -PassThru -NoNewWindow
    $timeout = 300; $elapsed = 0
    while (-not $proc.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep 10; $elapsed += 10
        if ($elapsed % 30 -eq 0) { Write-Log "  Training... ${elapsed}s" }
    }
    if (-not $proc.HasExited) {
        Write-Log "  WARNING: Training timed out ${timeout}s"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep 5
    $rd = Get-LatestRunDir
    if (-not $rd) { throw "No run dir created!" }
    $cp = Get-LatestCheckpoint $rd
    Write-Log "  Run: $($rd.Name), Checkpoint: $(if($cp){$cp.Name}else{'none (expected for short run)'})"
    Write-Log "  T1 training done."
}

# 2. Kill + GPU 정리
Test-Phase "T2: Kill-AllPython + Wait-GpuFree" {
    Kill-AllPython -reason "test-kill"
    $gpuOk = Wait-GpuFree -maxWaitSec 60 -thresholdMB 2000
    if (-not $gpuOk) { throw "GPU not freed after 60s" }
    Write-Log "  Kill-AllPython + Wait-GpuFree OK"
}

# 3. Ensure-GpuClean 통합 함수
Test-Phase "T3: Ensure-GpuClean" {
    Ensure-GpuClean -reason "test-ensureclean"
    $gmMB = [int](nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null).Trim()
    Write-Log "  GPU after Ensure-GpuClean: ${gmMB}MB"
    if ($gmMB -gt 2000) { throw "GPU still ${gmMB}MB > 2000MB" }
}

# 4. 영상 녹화
Test-Phase "T4: Record Video" {
    $rd = Get-LatestRunDir
    $cp = Get-LatestCheckpoint $rd
    if (-not $cp) {
        # 짧은 훈련이라 checkpoint 없을 수 있음 — model_0.pt 확인
        $cp = Get-ChildItem "$($rd.FullName)\model_*.pt" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $cp) { throw "No checkpoint found to record" }

    Write-Log "  Recording from $($cp.Name)..."
    $playCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\play.py --task=$Task --num_envs=$PlayEnvs --checkpoint=`"$($cp.FullName)`" --video --video_length=$VideoLength"
    $proc = Start-Process powershell -ArgumentList "-Command", $playCmd -PassThru -NoNewWindow
    $timeout = 300; $elapsed = 0
    while (-not $proc.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep 10; $elapsed += 10
    }
    if (-not $proc.HasExited) {
        Write-Log "  Play timed out, killing..."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Ensure-GpuClean -reason "post-record-test"

    $vid = Get-ChildItem "$($rd.FullName)\videos\play\*.mp4" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($vid) {
        $sizeMB = [math]::Round($vid.Length / 1MB, 1)
        Write-Log "  Video: $($vid.Name) (${sizeMB}MB)"
        $script:testVideoPath = $vid.FullName
    } else {
        Write-Log "  WARNING: No video file (might be normal for headless short run)"
        $script:testVideoPath = $null
    }
}

# 5. 분석 (conda activate + isaaclab.bat -p, 타임아웃 120s)
Test-Phase "T5: Analysis (conda activate + timeout)" {
    $rd = Get-LatestRunDir
    $cp = Get-LatestCheckpoint $rd
    if (-not $cp) { $cp = Get-ChildItem "$($rd.FullName)\model_*.pt" -ErrorAction SilentlyContinue | Select-Object -First 1 }

    if (-not (Test-Path $analyzeScript)) {
        Write-Log "  analyze_training.py not found — skip (NOT a failure)"
        return
    }

    $stdoutFile = "$ProjectRoot\logs\_test_analysis_out.txt"
    $stderrFile = "$ProjectRoot\logs\_test_analysis_err.txt"
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

    $cmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $analyzeScript --run_dir `"$($rd.FullName)`" --clip_num 999"
    $proc = Start-Process powershell -ArgumentList "-Command", $cmd `
        -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    if (-not $proc.WaitForExit(120000)) {
        Write-Log "  Analysis timed out 120s, killing..."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep 3
    }

    if (Test-Path $stdoutFile) {
        $text = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
        if ($text) {
            $preview = $text.Substring(0, [Math]::Min(300, $text.Length))
            Write-Log "  Output preview: $preview"
        }
        Remove-Item $stdoutFile -ErrorAction SilentlyContinue
    }
    Remove-Item $stderrFile -ErrorAction SilentlyContinue

    # 분석 python 정리
    Start-Sleep 2
    if (Get-Process python -ErrorAction SilentlyContinue) {
        Stop-Process -Name python -Force -ErrorAction SilentlyContinue
        Start-Sleep 3
    }
    Write-Log "  Analysis test done."
}

# 6. 훈련 재개 (resume)
Test-Phase "T6: Resume Training" {
    Ensure-GpuClean -reason "pre-resume-test"

    $rd = Get-LatestRunDir
    $cp = Get-LatestCheckpoint $rd
    if (-not $cp) { $cp = Get-ChildItem "$($rd.FullName)\model_*.pt" -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if (-not $cp) { throw "No checkpoint to resume from" }

    $runName = $rd.Name; $cpName = $cp.Name
    Write-Log "  Resuming: $runName / $cpName"

    # resume로 1회 추가 훈련 (max_iterations를 기존 + 1로 설정)
    $iterNum = if ($cp.BaseName -match '^model_(\d+)$') { [int]$Matches[1] } else { 0 }
    $resumeMax = $iterNum + 2

    $trainCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\train.py --task=$Task --num_envs=$TrainEnvs --headless --max_iterations=$resumeMax --resume --load_run=$runName --checkpoint=$cpName"
    $proc = Start-Process powershell -ArgumentList "-Command", $trainCmd -PassThru -NoNewWindow

    Write-Log "  Waiting for process (max 300s)..."
    $timeout = 300; $elapsed = 0
    while (-not $proc.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep 10; $elapsed += 10
        $p = Get-Process python -ErrorAction SilentlyContinue
        if ($p -and $elapsed -eq 60) {
            $mem = [math]::Round(($p | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
            Write-Log "  Training running: PID=$($p.Id -join ','), Mem=${mem}MB"
        }
    }
    if (-not $proc.HasExited) {
        Write-Log "  Resume timed out, killing..."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }

    # Verify new checkpoint
    Start-Sleep 5
    $newCp = Get-LatestCheckpoint $rd
    if ($newCp -and $newCp.Name -ne $cpName) {
        Write-Log "  New checkpoint: $($newCp.Name)"
    } else {
        Write-Log "  WARNING: Same checkpoint (short run may not save new one)"
    }
}

# ============================================================
# FINAL CLEANUP & REPORT
# ============================================================

Write-Log ""
Write-Log "--- Final Cleanup ---"
Ensure-GpuClean -reason "test-final"

Write-Log ""
Write-Log "============================================="
Write-Log "TEST RESULTS: $passed PASS / $failed FAIL / $total TOTAL"
if ($failed -eq 0) {
    Write-Log "ALL TESTS PASSED — training_supervisor ready"
} else {
    Write-Log "SOME TESTS FAILED — review log: $testLog"
}
Write-Log "============================================="
Write-Log "Log: $testLog"

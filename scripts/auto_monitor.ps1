# V17.1 Auto Training Monitor v2 (리소스 정리 강화 + 상세 분석)
# 3시간마다 훈련 중단 → 15초 영상 녹화 → 상세 분석 → 리소스 정리 → 훈련 재개
# Usage: .\scripts\auto_monitor.ps1

param(
    [int]$IntervalMinutes = 180,      # 모니터링 간격 (분) — 3시간
    [int]$VideoLength = 250,          # 영상 스텝 수 (~15초)
    [int]$PlayEnvs = 50,              # 플레이 환경 수
    [int]$TrainEnvs = 24576,          # 훈련 환경 수
    [int]$MaxIterations = 15000,      # 최대 이터레이션
    [string]$Task = "Isaac-Velocity-Flat-SpotMicro-v0",
    [string]$IsaacLab = "C:\IsaacLab\isaaclab.bat",
    [string]$ProjectRoot = "D:\project\spot_micro_rl"
)

$ErrorActionPreference = "Continue"
$logBase = "$ProjectRoot\logs\rsl_rl\spot_micro_flat"
$monitorLog = "$ProjectRoot\logs\monitor_log.txt"
$analyzeScript = "$ProjectRoot\scripts\analyze_training.py"

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $monitorLog -Value $line
}

function Get-LatestRunDir {
    Get-ChildItem $logBase -Directory | Sort-Object Name | Select-Object -Last 1
}

function Get-LatestCheckpoint($runDir) {
    $pts = Get-ChildItem "$($runDir.FullName)\model_*.pt" -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -match '^model_\d+$' } |
        Sort-Object { [int]($_.BaseName -replace 'model_','') }
    return $pts | Select-Object -Last 1
}

# ============================================================
# RESOURCE CLEANUP — 핵심: GPU 메모리 해제 보장
# ============================================================

function Kill-AllPython {
    param([string]$reason = "cleanup")
    Write-Log "[$reason] Killing all python processes..."
    
    # 1차: 일반 종료
    Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    
    # 2차: 잔존 프로세스 확인 및 강제 종료
    $remaining = Get-Process python -ErrorAction SilentlyContinue
    if ($remaining) {
        Write-Log "[$reason] $($remaining.Count) python process(es) still alive, force killing PIDs: $($remaining.Id -join ', ')"
        $remaining | ForEach-Object {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
    }
    
    # 3차: Isaac Sim 관련 프로세스 정리 (Kit 엔진 등)
    @("python", "python3", "Kit") | ForEach-Object {
        Stop-Process -Name $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    
    # 최종 확인 — taskkill 최후 수단
    $final = Get-Process python -ErrorAction SilentlyContinue
    if ($final) {
        Write-Log "[$reason] WARNING: $($final.Count) process(es) survived! Using taskkill..."
        $final | ForEach-Object {
            taskkill /F /PID $_.Id 2>$null
        }
        Start-Sleep -Seconds 3
    }
    
    # GPU 메모리 해제 대기
    Write-Log "[$reason] Waiting for GPU memory release..."
    Start-Sleep -Seconds 5
    
    $stillAlive = Get-Process python -ErrorAction SilentlyContinue
    if ($stillAlive) {
        Write-Log "[$reason] CRITICAL: Python processes STILL running after all kill attempts!"
        return $false
    }
    Write-Log "[$reason] All python processes terminated. GPU memory freed."
    return $true
}

function Verify-GpuClean {
    try {
        $smi = nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>$null
        if ($smi -and $smi.Trim()) {
            Write-Log "GPU processes still using memory:"
            $smi -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Log "  $_" } }
            return $false
        }
        Write-Log "GPU memory clean."
        return $true
    } catch {
        Write-Log "nvidia-smi check skipped."
        return $true
    }
}

# ============================================================
# VIDEO RECORDING
# ============================================================

function Record-Video($checkpointPath, $runDir, $clipNum) {
    Write-Log "Recording video clip #$clipNum from: $($checkpointPath.Name)"
    
    $playCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\play.py --task=$Task --num_envs=$PlayEnvs --checkpoint=`"$($checkpointPath.FullName)`" --video --video_length=$VideoLength"
    
    Write-Log "Running play command..."
    $proc = Start-Process -FilePath "powershell" -ArgumentList "-Command", $playCmd -PassThru -NoNewWindow
    
    # Wait for completion (max 8 minutes — 15초 영상은 충분)
    $timeout = 480
    $elapsed = 0
    while (-not $proc.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 10
        $elapsed += 10
        if ($elapsed % 60 -eq 0) {
            Write-Log "  Recording... ${elapsed}s elapsed"
        }
    }
    
    if (-not $proc.HasExited) {
        Write-Log "WARNING: Play process timed out after ${timeout}s"
    }
    
    # === 녹화 후 리소스 정리 (CRITICAL) ===
    $cleaned = Kill-AllPython -reason "post-recording"
    if (-not $cleaned) {
        Write-Log "ERROR: Failed to clean up after recording! Extra wait..."
        Start-Sleep -Seconds 15
        Kill-AllPython -reason "post-recording-retry" | Out-Null
    }
    Verify-GpuClean
    
    # Find and organize video file
    $videoFiles = Get-ChildItem "$($runDir.FullName)\videos\play\*.mp4" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime
    $latestVideo = $videoFiles | Select-Object -Last 1
    
    if ($latestVideo) {
        $iterNum = $checkpointPath.BaseName -replace 'model_',''
        $newName = "clip_${clipNum}_iter${iterNum}_$(Get-Date -Format 'yyyyMMdd_HHmmss').mp4"
        $destPath = "$($runDir.FullName)\videos\$newName"
        Copy-Item $latestVideo.FullName $destPath -ErrorAction SilentlyContinue
        Write-Log "Video saved: $newName ($([math]::Round($latestVideo.Length/1024/1024, 1))MB)"
        return $destPath
    } else {
        Write-Log "WARNING: No video file found!"
        return $null
    }
}

# ============================================================
# DETAILED ANALYSIS — Python 분석 스크립트 호출 + 로그 기록
# ============================================================

function Run-DetailedAnalysis($runDir, $checkpoint, $clipNum, $videoPath) {
    $iterNum = $checkpoint.BaseName -replace 'model_',''
    
    Write-Log "Running detailed analysis (iter $iterNum)..."
    
    # 헤더
    $header = @"

################################################################################
#  MONITOR CLIP #$clipNum — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
#  Checkpoint: model_${iterNum}.pt | Run: $($runDir.Name)
#  Video: $(if($videoPath) { Split-Path $videoPath -Leaf } else { "N/A" })
################################################################################
"@
    Add-Content -Path $monitorLog -Value $header
    
    # Python 분석 스크립트 실행 (GPU 불필요, CPU만 사용)
    if (Test-Path $analyzeScript) {
        try {
            $analysisOutput = & conda run -n env_isaaclab python $analyzeScript --run_dir "$($runDir.FullName)" --clip_num $clipNum 2>&1
            $analysisText = $analysisOutput | Out-String
            
            Write-Host $analysisText
            Add-Content -Path $monitorLog -Value $analysisText
            Write-Log "Detailed analysis complete."
        } catch {
            Write-Log "ERROR running analysis script: $_"
            Write-BasicAnalysis $runDir $iterNum
        }
        
        # === 분석 후 혹시 남은 python 정리 ===
        Start-Sleep -Seconds 2
        $analysisPython = Get-Process python -ErrorAction SilentlyContinue
        if ($analysisPython) {
            Write-Log "Cleaning up analysis python process..."
            Kill-AllPython -reason "post-analysis" | Out-Null
        }
    } else {
        Write-Log "Analysis script not found, using basic analysis."
        Write-BasicAnalysis $runDir $iterNum
    }
}

function Write-BasicAnalysis($runDir, $iterNum) {
    $ev = Get-ChildItem "$($runDir.FullName)\events*" -ErrorAction SilentlyContinue | Select-Object -First 1
    $evSize = if ($ev) { [math]::Round($ev.Length / 1024) } else { 0 }
    $cpCount = (Get-ChildItem "$($runDir.FullName)\model_*.pt" -ErrorAction SilentlyContinue).Count
    
    $basic = @"
[Basic Analysis - analyze_training.py not available]
  Event file: ${evSize}KB
  Checkpoints saved: $cpCount
  Latest iteration: ~$iterNum
"@
    Add-Content -Path $monitorLog -Value $basic
    Write-Host $basic
}

# ============================================================
# TRAINING RESUME — 리소스 완전 확인 후 재개
# ============================================================

function Resume-Training($runDir, $checkpoint) {
    $runName = $runDir.Name
    $cpName = $checkpoint.Name
    $iterNum = [int]($checkpoint.BaseName -replace 'model_','')
    
    # === 재개 전 리소스 최종 점검 ===
    Write-Log "Pre-resume: Final resource check..."
    $cleaned = Kill-AllPython -reason "pre-resume"
    $gpuClean = Verify-GpuClean
    
    if (-not $cleaned -or -not $gpuClean) {
        Write-Log "Resources not clean. Extra 30s wait..."
        Start-Sleep -Seconds 30
        Kill-AllPython -reason "pre-resume-retry" | Out-Null
        Verify-GpuClean
    }
    
    Write-Log "Resuming training: $runName / $cpName (iter $iterNum)"
    
    $trainCmd = "conda activate env_isaaclab; cd $ProjectRoot; $IsaacLab -p $ProjectRoot\scripts\rsl_rl\train.py --task=$Task --num_envs=$TrainEnvs --headless --max_iterations=$MaxIterations --resume --load_run=$runName --checkpoint=$cpName"
    
    Start-Process -FilePath "powershell" -ArgumentList "-Command", $trainCmd -NoNewWindow
    
    # 훈련 프로세스가 실제로 시작되었는지 확인 (Isaac Sim 초기화에 시간 소요)
    Write-Log "Waiting for training process to initialize..."
    Start-Sleep -Seconds 20
    $trainProc = Get-Process python -ErrorAction SilentlyContinue
    if ($trainProc) {
        $memMB = [math]::Round(($trainProc | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
        Write-Log "Training confirmed: PID=$($trainProc.Id -join ','), Mem=${memMB}MB"
    } else {
        Write-Log "WARNING: Training process not detected! Check for errors."
    }
    
    Write-Log "Next check in $IntervalMinutes minutes ($([math]::Round($IntervalMinutes/60, 1))h)."
}

# ============================================================
# MAIN LOOP
# ============================================================

Write-Log "========================================="
Write-Log "V17.1 Auto Monitor v2"
Write-Log "리소스 정리 강화 + 상세 분석"
Write-Log "Interval: ${IntervalMinutes}min, Video: ${VideoLength} steps"
Write-Log "Train envs: $TrainEnvs, Play envs: $PlayEnvs"
Write-Log "========================================="

$clipNum = 0

while ($true) {
    Write-Log "Sleeping for $IntervalMinutes minutes ($([math]::Round($IntervalMinutes/60, 1))h)..."
    Start-Sleep -Seconds ($IntervalMinutes * 60)
    
    $clipNum++
    Write-Log ""
    Write-Log "########## MONITOR CLIP #$clipNum ##########"
    
    # 1. Find latest run and checkpoint
    $runDir = Get-LatestRunDir
    if (-not $runDir) {
        Write-Log "ERROR: No training run found! Retrying next interval."
        continue
    }
    
    $checkpoint = Get-LatestCheckpoint $runDir
    if (-not $checkpoint) {
        Write-Log "ERROR: No checkpoint found in $($runDir.Name)! Retrying next interval."
        continue
    }
    
    $iterNum = [int]($checkpoint.BaseName -replace 'model_','')
    Write-Log "Latest: $($runDir.Name) / $($checkpoint.Name) (iter $iterNum)"
    
    # Training complete?
    if ($iterNum -ge ($MaxIterations - 100)) {
        Write-Log "===== TRAINING COMPLETE (iter $iterNum) ====="
        Kill-AllPython -reason "training-complete" | Out-Null
        Verify-GpuClean
        $videoPath = Record-Video $checkpoint $runDir $clipNum
        Run-DetailedAnalysis $runDir $checkpoint $clipNum $videoPath
        Kill-AllPython -reason "final-cleanup" | Out-Null
        Verify-GpuClean
        Write-Log "===== MONITOR FINISHED ====="
        break
    }
    
    # --- Phase 1: Stop Training + Resource Cleanup ---
    Write-Log "--- Phase 1/5: Stop Training ---"
    $cleaned = Kill-AllPython -reason "stop-training"
    Verify-GpuClean
    if (-not $cleaned) {
        Start-Sleep -Seconds 30
        Kill-AllPython -reason "stop-retry" | Out-Null
    }
    
    # --- Phase 2: Record Video ---
    Write-Log "--- Phase 2/5: Record Video ---"
    $videoPath = Record-Video $checkpoint $runDir $clipNum
    # (Record-Video 내부에서 정리 수행됨)
    
    # --- Phase 3: Detailed Analysis ---
    Write-Log "--- Phase 3/5: Detailed Analysis ---"
    Run-DetailedAnalysis $runDir $checkpoint $clipNum $videoPath
    
    # --- Phase 4: Pre-Resume Final Cleanup ---
    Write-Log "--- Phase 4/5: Final Cleanup ---"
    Kill-AllPython -reason "pre-resume-final" | Out-Null
    Verify-GpuClean
    Start-Sleep -Seconds 5
    
    # --- Phase 5: Resume Training ---
    Write-Log "--- Phase 5/5: Resume Training ---"
    Resume-Training $runDir $checkpoint
    
    Write-Log "########## CLIP #$clipNum COMPLETE ##########"
    Write-Log ""
}

Write-Log "Monitor process exiting."

param(
    [ValidateSet('install', 'start', 'stop', 'restart', 'status', 'uninstall')]
    [string]$Action = 'install',
    [string]$TaskName = 'SpotMicroSupervisor',
    [string]$ProjectRoot,
    [string]$PythonExe,
    [int]$Poll = 10,
    [int]$IterStep = 100,
    [int]$HeartbeatPoll = 30,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'

function Resolve-ProjectRoot {
    param([string]$InputPath)
    if ($InputPath) {
        return (Resolve-Path $InputPath).Path
    }
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Resolve-PythonExe {
    param(
        [string]$ExplicitPath,
        [string]$ProjectRootPath
    )

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    if ($env:CONDA_PREFIX) {
        $candidates += (Join-Path $env:CONDA_PREFIX 'python.exe')
    }
    $userProfile = [Environment]::GetFolderPath('UserProfile')
    foreach ($base in @('miniforge3', 'miniconda3', 'anaconda3')) {
        $candidates += (Join-Path $userProfile "$base\envs\env_isaaclab\python.exe")
    }
    $candidates += 'C:\Users\etnlw\miniforge3\envs\env_isaaclab\python.exe'

    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        try {
            $resolved = (Resolve-Path $candidate).Path
        } catch {
            continue
        }
        if (Test-Path $resolved) {
            return $resolved
        }
    }

    throw "Unable to locate env_isaaclab python.exe. Pass -PythonExe explicitly."
}

function Get-TaskActionCommand {
    param(
        [string]$ResolvedProjectRoot,
        [string]$ResolvedPythonExe,
        [int]$ResolvedPoll,
        [int]$ResolvedIterStep,
        [int]$ResolvedHeartbeatPoll
    )

    $scriptPath = Join-Path $ResolvedProjectRoot 'scripts\supervisor.py'
    if (-not (Test-Path $scriptPath)) {
        throw "supervisor.py not found: $scriptPath"
    }
    $quotedProject = '"' + $ResolvedProjectRoot + '"'
    $quotedPython = '"' + $ResolvedPythonExe + '"'
    $quotedScript = '"' + $scriptPath + '"'
    return "/d /c cd /d $quotedProject && $quotedPython $quotedScript --listen --poll $ResolvedPoll --iter-step $ResolvedIterStep --heartbeat-poll $ResolvedHeartbeatPoll"
}

function Get-SupervisorTask {
    param([string]$Name)
    try {
        return Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        return $null
    }
}

$resolvedProjectRoot = Resolve-ProjectRoot -InputPath $ProjectRoot
$resolvedPythonExe = Resolve-PythonExe -ExplicitPath $PythonExe -ProjectRootPath $resolvedProjectRoot
$taskArgs = Get-TaskActionCommand -ResolvedProjectRoot $resolvedProjectRoot -ResolvedPythonExe $resolvedPythonExe -ResolvedPoll $Poll -ResolvedIterStep $IterStep -ResolvedHeartbeatPoll $HeartbeatPoll

switch ($Action) {
    'install' {
        $actionDef = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $taskArgs
        $triggers = @(
            (New-ScheduledTaskTrigger -AtStartup),
            (New-ScheduledTaskTrigger -AtLogOn)
        )
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RestartCount 999 `
            -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
            -MultipleInstances IgnoreNew
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $existing = Get-SupervisorTask -Name $TaskName
        if ($existing) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Register-ScheduledTask -TaskName $TaskName -Action $actionDef -Trigger $triggers -Settings $settings -Principal $principal | Out-Null
        Write-Output "Installed scheduled task: $TaskName"
        Write-Output "Action: cmd.exe $taskArgs"
        if ($RunNow) {
            Start-ScheduledTask -TaskName $TaskName
            Start-Sleep -Seconds 3
            Write-Output "Started scheduled task: $TaskName"
        }
    }
    'start' {
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Write-Output "Started scheduled task: $TaskName"
    }
    'stop' {
        Stop-ScheduledTask -TaskName $TaskName
        Write-Output "Stopped scheduled task: $TaskName"
    }
    'restart' {
        try {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            Start-Sleep -Seconds 2
        } catch {
        }
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Write-Output "Restarted scheduled task: $TaskName"
    }
    'status' {
        $task = Get-SupervisorTask -Name $TaskName
        if (-not $task) {
            Write-Output "Scheduled task not found: $TaskName"
            exit 1
        }
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        [pscustomobject]@{
            TaskName = $TaskName
            State = $task.State
            LastRunTime = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime = $info.NextRunTime
            Author = $task.Author
        } | Format-List
    }
    'uninstall' {
        $task = Get-SupervisorTask -Name $TaskName
        if ($task) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Output "Uninstalled scheduled task: $TaskName"
        } else {
            Write-Output "Scheduled task not found: $TaskName"
        }
    }
}